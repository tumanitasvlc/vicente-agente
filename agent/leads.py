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
    import gspread
    from google.oauth2.service_account import Credentials

    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.debug("Google Sheets no configurado — saltando registro")
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/google_credentials.json")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    if os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    elif creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        logger.debug("Google Sheets no configurado — saltando registro")
        return

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
    logger.info(f"[LEAD] Registrado en Google Sheets: {telefono}")


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
