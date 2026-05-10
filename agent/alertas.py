# agent/alertas.py — Alertas cuando Vicente no puede responder a un cliente

import os
import smtplib
import asyncio
import logging
import traceback
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger("agentkit")

ALERT_EMAIL = "aleparisi@mac.com"
ERROR_LOG = Path("agent/errors.log")


def _enviar_email_sync(asunto: str, cuerpo: str) -> bool:
    """Envía email via Gmail SMTP con SSL. Bloqueante — se llama con asyncio.to_thread."""
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        logger.warning("[ALERTA] GMAIL_USER o GMAIL_APP_PASSWORD no configurados — solo log")
        return False

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = gmail_user
    msg["To"] = ALERT_EMAIL
    msg.set_content(cuerpo)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_password)
            smtp.send_message(msg)
        logger.info(f"[ALERTA] Email enviado a {ALERT_EMAIL}: {asunto}")
        return True
    except Exception:
        logger.error(f"[ALERTA] Error al enviar email:\n{traceback.format_exc()}")
        return False


def _guardar_en_error_log(linea: str):
    """Añade una línea a agent/errors.log como fallback cuando el email falla."""
    try:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
        logger.info(f"[ALERTA] Error guardado en {ERROR_LOG}")
    except Exception:
        logger.error(f"[ALERTA] No se pudo escribir en {ERROR_LOG}:\n{traceback.format_exc()}")


async def alertar_fallo_envio(telefono: str, status_code: int, detalle: str):
    """
    Alerta cuando Vicente no puede enviar un mensaje a un cliente.
    Intenta email (Gmail SMTP); si falla, escribe en agent/errors.log.

    Variables de entorno necesarias para email:
      GMAIL_USER         — cuenta Gmail desde la que se envía
      GMAIL_APP_PASSWORD — contraseña de aplicación de Google (no la contraseña normal)
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tipo = "Rate limit (429)" if status_code == 429 else f"Error HTTP {status_code}"

    asunto = f"[Vicente] Fallo de envío — {tipo} — {telefono}"
    cuerpo = (
        f"Vicente no pudo responder a un cliente.\n\n"
        f"Fecha/hora : {ahora}\n"
        f"Teléfono   : {telefono}\n"
        f"Código HTTP: {status_code}\n"
        f"Tipo       : {tipo}\n"
        f"Detalle    : {detalle}\n\n"
        f"Revisa la conversación y responde manualmente si es necesario.\n"
        f"Panel Twilio: https://console.twilio.com"
    )

    linea_log = f"{ahora} | {tipo} | telefono={telefono} | {detalle[:300]}"

    email_ok = await asyncio.to_thread(_enviar_email_sync, asunto, cuerpo)
    if not email_ok:
        _guardar_en_error_log(linea_log)
