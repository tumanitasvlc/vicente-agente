# agent/scheduler.py — Jobs periódicos: resumen diario y alerta de silencio

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("agentkit")

ADMIN_PHONE = "+34655846061"
MADRID_TZ = ZoneInfo("Europe/Madrid")
SILENCIO_HORAS = 24


async def enviar_resumen_diario():
    """Consulta las stats del día y envía un resumen WhatsApp al administrador."""
    from agent.memory import stats_hoy
    from agent.providers import proveedor_twilio

    try:
        stats = await stats_hoy()
        fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y")

        cuerpo = (
            f"📊 Resumen diario — Tu Manitas VLC\n"
            f"📅 {fecha}\n\n"
            f"💬 Conversaciones: {stats['conversaciones']}\n"
            f"🎯 Leads captados: {stats['leads']}"
        )

        await proveedor_twilio.enviar_mensaje(ADMIN_PHONE, cuerpo)
        logger.info(f"Resumen diario enviado: {stats}")
    except Exception as e:
        logger.error(f"Error enviando resumen diario: {e}")


async def verificar_silencio():
    """
    Comprueba si el webhook lleva más de SILENCIO_HORAS sin recibir mensajes.
    Se ejecuta cada día a las 9:00. Si no hay actividad, envía alerta por email.
    """
    from agent.memory import ultimo_mensaje_recibido
    from agent.alertas import alertar_silencio

    try:
        ultimo = await ultimo_mensaje_recibido()
        ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        if ultimo is None:
            logger.warning("[SILENCIO] Sin mensajes registrados nunca — alertando")
            await alertar_silencio(SILENCIO_HORAS)
            return

        horas_transcurridas = (ahora_utc - ultimo).total_seconds() / 3600
        if horas_transcurridas >= SILENCIO_HORAS:
            horas_int = int(horas_transcurridas)
            logger.warning(f"[SILENCIO] Sin mensajes en {horas_int}h — alertando")
            await alertar_silencio(horas_int)
        else:
            logger.debug(f"[SILENCIO] Último mensaje hace {horas_transcurridas:.1f}h — OK")
    except Exception as e:
        logger.error(f"Error en verificar_silencio: {e}")


def crear_scheduler() -> AsyncIOScheduler:
    """Crea y configura el scheduler con los jobs periódicos."""
    scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
    scheduler.add_job(
        enviar_resumen_diario,
        trigger="cron",
        hour=20,
        minute=0,
        id="resumen_diario",
        replace_existing=True,
    )
    scheduler.add_job(
        verificar_silencio,
        trigger="cron",
        hour=9,
        minute=0,
        id="verificar_silencio",
        replace_existing=True,
    )
    return scheduler
