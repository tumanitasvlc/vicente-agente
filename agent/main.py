# agent/main.py — Servidor FastAPI + Webhook de WhatsApp (Meta + Twilio)

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import proveedor_meta, proveedor_twilio

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

PORT = int(os.getenv("PORT", 8000))


def _detectar_proveedor(request: Request):
    """
    Detecta el origen del webhook por Content-Type:
    - application/json              → Meta Cloud API
    - application/x-www-form-urlencoded → Twilio
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return proveedor_meta
    return proveedor_twilio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info("Proveedores activos: Meta Cloud API + Twilio")
    yield


app = FastAPI(
    title="Tu Manitas VLC — Agente WhatsApp (Vicente)",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "agente": "Vicente", "negocio": "Tu Manitas VLC"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """
    Verificación GET requerida por Meta Cloud API.
    Comprueba hub.verify_token y devuelve hub.challenge en texto plano.
    """
    resultado = await proveedor_meta.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp desde Meta o Twilio.
    Detecta el origen por Content-Type y usa el proveedor correspondiente
    tanto para parsear el payload como para enviar la respuesta.
    """
    proveedor = _detectar_proveedor(request)
    origen = proveedor.__class__.__name__
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"[{origen}] Mensaje de {msg.telefono}: {msg.texto}")

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial)

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"[{origen}] Respuesta a {msg.telefono}: {respuesta}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"[{origen}] Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
