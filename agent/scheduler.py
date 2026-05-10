# agent/scheduler.py — Resumen diario a las 20:00 hora de Madrid

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("agentkit")

ADMIN_PHONE = "+34655846061"
MADRID_TZ = ZoneInfo("Europe/Madrid")


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


def crear_scheduler() -> AsyncIOScheduler:
    """Crea y configura el scheduler con el job del resumen diario."""
    scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
    scheduler.add_job(
        enviar_resumen_diario,
        trigger="cron",
        hour=20,
        minute=0,
        id="resumen_diario",
        replace_existing=True,
    )
    return scheduler
