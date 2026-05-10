# agent/leads.py — Detección de leads, notificaciones y registro en Google Sheets

import re
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("agentkit")

ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+34655846061")

# Números móviles españoles (6xx / 7xx), con o sin prefijo +34 / 0034 y espacios
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+34[\s]?|0034[\s]?)?"
    r"([67]\d{2}[\s\-]?\d{3}[\s\-]?\d{3})"
    r"(?!\d)"
)


def detectar_telefono(texto: str) -> str | None:
    """Devuelve el primer número móvil español encontrado en texto, normalizado sin espacios."""
    match = _PHONE_RE.search(texto)
    if match:
        return re.sub(r"[\s\-]", "", match.group(1))
    return None


async def notificar_lead(telefono_cliente: str, ultimo_mensaje: str) -> bool:
    """Envía alerta WhatsApp a ADMIN_PHONE via Twilio."""
    from agent.providers import proveedor_twilio

    hora = datetime.now().strftime("%H:%M")
    cuerpo = (
        "🔔 Nuevo lead de Tu Manitas VLC\n"
        f"📱 Cliente: {telefono_cliente}\n"
        f"💬 Mensaje: {ultimo_mensaje}\n"
        f"🕐 {hora}"
    )
    ok = await proveedor_twilio.enviar_mensaje(ADMIN_PHONE, cuerpo)
    if ok:
        logger.info(f"[LEAD] Notificación enviada a {ADMIN_PHONE} (cliente: {telefono_cliente})")
    return ok


def _registrar_en_sheets_sync(telefono: str, mensaje: str):
    """Añade una fila al Google Sheet configurado. Bloqueante — llamar con asyncio.to_thread."""
    import json
    import traceback
    import gspread
    from google.oauth2.service_account import Credentials

    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("[SHEETS] GOOGLE_SHEETS_ID no configurado — saltando registro")
        return

    logger.debug(f"[SHEETS] Iniciando registro para {telefono}, sheet_id={sheets_id}")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/google_credentials.json")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    creds = None
    if os.path.exists(creds_path):
        logger.debug(f"[SHEETS] Cargando credenciales desde archivo: {creds_path}")
        try:
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        except Exception:
            logger.error(f"[SHEETS] Error al leer credenciales desde archivo {creds_path}:\n{traceback.format_exc()}")
            return
    elif creds_json:
        logger.debug("[SHEETS] Cargando credenciales desde variable de entorno GOOGLE_CREDENTIALS_JSON")
        try:
            creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
        except json.JSONDecodeError:
            logger.error(f"[SHEETS] GOOGLE_CREDENTIALS_JSON no es JSON válido:\n{traceback.format_exc()}")
            return
        except Exception:
            logger.error(f"[SHEETS] Error al parsear credenciales desde variable de entorno:\n{traceback.format_exc()}")
            return
    else:
        logger.warning(
            "[SHEETS] No se encontraron credenciales: "
            f"archivo '{creds_path}' no existe y GOOGLE_CREDENTIALS_JSON no está definido"
        )
        return

    try:
        gc = gspread.authorize(creds)
        ws = gc.open_by_key(sheets_id).sheet1
        now = datetime.now()
        ws.append_row([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            telefono,
            mensaje,
            "Nuevo",
        ])
        logger.info(f"[SHEETS] Fila añadida correctamente para {telefono}")
    except gspread.exceptions.APIError as e:
        logger.error(f"[SHEETS] Error de API de Google Sheets (status={e.response.status_code}):\n{traceback.format_exc()}")
    except Exception:
        logger.error(f"[SHEETS] Error inesperado al escribir en Sheets:\n{traceback.format_exc()}")


async def registrar_lead_sheets(telefono: str, mensaje: str):
    """Wrapper async para el registro en Google Sheets (evita bloquear el event loop)."""
    try:
        await asyncio.to_thread(_registrar_en_sheets_sync, telefono, mensaje)
    except Exception as e:
        logger.error(f"Error Google Sheets: {e}")


async def procesar_posible_lead(telefono_cliente: str, mensaje: str):
    """
    Punto de entrada principal. Detecta si el mensaje contiene un número de teléfono.
    Si lo encuentra, dispara en paralelo: guardar en DB, notificar por WhatsApp y registrar en Sheets.
    """
    if not detectar_telefono(mensaje):
        return

    logger.info(f"[LEAD] Teléfono detectado en mensaje de {telefono_cliente}")

    from agent.memory import guardar_lead

    await asyncio.gather(
        guardar_lead(telefono_cliente, mensaje),
        notificar_lead(telefono_cliente, mensaje),
        registrar_lead_sheets(telefono_cliente, mensaje),
    )
