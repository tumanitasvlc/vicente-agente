# agent/leads.py — Detección de leads, notificaciones y registro en Google Sheets

import re
import os
import json
import asyncio
import logging
import traceback
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger("agentkit")

ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+34655846061")

# ─── Regex: números móviles españoles ────────────────────────────────────────
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+34[\s]?|0034[\s]?)?"
    r"([67]\d{2}[\s\-]?\d{3}[\s\-]?\d{3})"
    r"(?!\d)"
)

# ─── Catálogo de servicios ────────────────────────────────────────────────────
_SERVICIOS: dict[str, list[str]] = {
    "Pintura": [
        "pintura", "pintar", "pintado", "pintor", "pintora", "repintar",
        "paredes", "pared", "gotelé", "gotele",
        "esmalte", "barniz", "barnizar", "lija", "lijar",
    ],
    "Fontanería": [
        "fontanería", "fontaneria", "fontanero", "fontanera", "plomero",
        "grifo", "grifos", "tubería", "tuberias", "tubería", "tubo", "tubos",
        "fuga", "fugaz", "gotera", "goteras", "pérdida de agua", "pierde agua",
        "desatascar", "desatasco", "desatasque", "atasco", "atascado", "obstruido",
        "desagüe", "desague", "sifón", "sifon",
        "fregadero", "lavabo", "lavamanos", "inodoro", "váter", "vater", "wc",
        "cisterna", "ducha", "bañera", "banyera", "bidé", "bide",
        "calentador", "termo", "termostato", "presión agua", "sin agua",
        "llave de paso", "contador agua",
    ],
    "Electricidad": [
        "electricidad", "eléctrico", "electrico", "electricista",
        "enchufe", "enchufes", "interruptor", "interruptores",
        "luz", "luces", "bombilla", "bombillas", "foco", "focos",
        "cortocircuito", "corto circuito", "cuadro eléctrico", "caja de luz",
        "diferencial", "automático", "fusible", "magnetotérmico",
        "instalación eléctrica", "cableado", "cable", "cables",
        "no hay luz", "se va la luz", "salta el diferencial", "salta la luz",
        "enchufe quemado", "chispa",
    ],
    "Montaje muebles": [
        "montar muebles", "montaje muebles", "mueble", "muebles",
        "ikea", "leroy merlin", "bricomart",
        "armario", "armarios", "estantería", "estanterias", "estante",
        "mesa", "silla", "sillas", "cama", "somier", "cómoda", "comoda",
        "librería", "libreria", "zapatero", "cajonera", "escritorio",
        "desmontar mueble", "ensamblar",
    ],
    "Reformas": [
        "reforma", "reformas", "obra", "obras", "renovación", "renovacion",
        "rehabilitación", "rehabilitacion", "remodelar", "remodelación",
        "ampliar", "ampliación", "derribar", "derribo", "tirar pared",
        "distribuir", "redistribuir", "habitación nueva",
    ],
    "Carpintería": [
        "carpintería", "carpinteria", "carpintero", "carpintera",
        "madera", "maderas", "puerta", "puertas", "ventana", "ventanas",
        "persiana", "persianas", "persiana rota", "persiana atascada",
        "marco", "marcos", "rodapié", "rodapies", "zócalo", "parqué", "parque",
        "tarima", "suelo de madera", "tablero", "bisagra", "bisagras",
    ],
    "Albañilería": [
        "albañilería", "albanileria", "albañil", "albanil",
        "cemento", "escayola", "yeso", "tabique", "tabiques",
        "azulejo", "azulejos", "baldosa", "baldosas", "gresite",
        "grieta", "grietas", "desconchado", "humedades", "humedad",
        "gotera techo", "filtraciones", "rajadura",
        "solado", "alicatado", "terracota", "microcemento",
    ],
    "Limpieza": [
        "limpieza", "limpiar", "limpieza general", "limpieza a fondo",
        "limpieza post obra", "limpieza fin de obra",
        "cristales", "ventanas sucias", "limpiacristales",
    ],
    "Jardinería": [
        "jardinería", "jardineria", "jardín", "jardin", "jardinero", "jardinera",
        "plantas", "planta", "poda", "podar", "césped", "cesped", "hierba",
        "seto", "setos", "árbol", "arboles", "riego", "sistema de riego",
        "desbroce", "desbrozar", "maleza", "tierra", "abono", "trasplantar",
    ],
    "Cerrajería": [
        "cerrajería", "cerrajeria", "cerrajero", "cerrajera",
        "cerradura", "cerraduras", "llave", "llaves", "candado",
        "cerrojo", "pestillo", "bombín", "bombin",
        "no puedo abrir", "puerta bloqueada", "puerta atascada",
        "cambiar cerradura", "duplicar llave", "copia de llave",
        "caja fuerte", "puerta acorazada",
    ],
    "Climatización": [
        "aire acondicionado", "aire acond", "aa ", "a/a",
        "calefacción", "calefaccion", "radiador", "radiadores",
        "climatización", "climatizacion", "caldera", "calderas",
        "bomba de calor", "split", "cassette", "conductos",
        "frío", "frio", "calor", "ventilación", "ventilacion",
        "extractor", "fancoil", "underfloor", "suelo radiante",
    ],
    "Pequeñas reparaciones": [
        "reparación", "reparacion", "reparar", "arreglar", "arreglo",
        "avería", "averia", "chapuza", "mantenimiento", "manitas",
        "colgar", "colgar cuadro", "colgar tv", "instalar", "instalación",
        "silicona", "sellado", "tapar agujero", "parchear",
    ],
}

# ─── Zonas de Valencia — cobertura completa (~30 km) ─────────────────────────
_ZONAS: list[str] = [
    # Barrios de la ciudad de Valencia
    "Ruzafa", "Russafa", "Benimaclet", "El Carmen", "Cabanyal", "Malvarrosa",
    "Patraix", "Jesús", "Campanar", "Benicalap", "Nou Moles", "Torrefiel",
    "Algirós", "Algiros", "Poblats Marítims", "Quatre Carreres", "Extramurs",
    "L'Eixample", "Eixample", "La Saïdia", "Saïdia", "Zaidía", "Zaidia",
    "El Pla del Real", "Olivereta", "Mestalla", "La Creu Coberta", "Sant Marcel·lí",
    "Benimamet", "Benimàmet", "Marxalenes", "El Grao", "Natzaret",
    "La Torre", "Castellar-Oliveral", "Pinedo", "Borbotó",
    # Norte
    "Puçol", "Pucol", "El Puig", "El Puig de Santa Maria",
    "Sagunt", "Sagunto", "Puerto de Sagunto",
    "Massamagrell", "Museros", "Albalat dels Sorells",
    "Foios", "Alboraia", "Alboraya",
    # Noroeste
    "Bétera", "Betera", "La Eliana", "Serra", "Náquera", "Naquera",
    "Marines", "Olocau", "Gátova", "Gatova",
    "Llíria", "Liria", "Benissanó", "Benisano",
    "Riba-roja de Túria", "Riba-roja de Turia", "Riba-roja",
    "Paterna", "Burjassot", "Godella", "Rocafort", "Moncada",
    "Alfara del Patriarca", "Vinalesa", "Massalfassar",
    # Oeste
    "Manises", "Quart de Poblet", "Aldaia", "Alaquàs", "Alaquas",
    "Xirivella", "Mislata",
    # Sur
    "Torrent", "Picanya", "Paiporta", "Sedaví", "Sedavi",
    "Massanassa", "Catarroja", "Alfafar", "Benetússer", "Benetusser",
    "Alcàsser", "Alcasser", "Picassent", "Silla", "Albal", "Beniparrell",
    "Lloc Nou de la Corona", "Llocnou de la Corona",
]
# Las más largas primero para que coincidencias compuestas tengan prioridad
_ZONAS_SORTED = sorted(_ZONAS, key=len, reverse=True)


# ─── Detección de datos ───────────────────────────────────────────────────────

def detectar_telefono(texto: str) -> str | None:
    """Devuelve el primer número móvil español encontrado, normalizado sin espacios."""
    match = _PHONE_RE.search(texto)
    if match:
        return re.sub(r"[\s\-]", "", match.group(1))
    return None


def detectar_servicio(texto: str) -> str:
    """
    Extrae el tipo de servicio mencionado en el texto.
    Retorna la etiqueta del servicio o cadena vacía si no se reconoce.
    """
    texto_lower = texto.lower()
    for servicio, palabras in _SERVICIOS.items():
        for palabra in palabras:
            if palabra in texto_lower:
                return servicio
    return ""


def detectar_zona(texto: str) -> str | None:
    """
    Detecta si el texto menciona un barrio o municipio de Valencia.
    Retorna el nombre normalizado o None.
    """
    texto_lower = texto.lower()
    for zona in _ZONAS_SORTED:
        if zona.lower() in texto_lower:
            return zona
    return None


# ─── Helpers de Google Sheets ─────────────────────────────────────────────────

def _abrir_hoja_sync() -> gspread.Worksheet | None:
    """
    Carga credenciales y abre la primera hoja del Sheet configurado.
    Retorna el Worksheet o None si algo falla.
    """
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.warning("[SHEETS] GOOGLE_SHEETS_ID no configurado — saltando")
        return None

    logger.debug(f"[SHEETS] Abriendo sheet_id={sheets_id}")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/google_credentials.json")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

    creds = None
    if os.path.exists(creds_path):
        logger.debug(f"[SHEETS] Credenciales desde archivo: {creds_path}")
        try:
            creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        except Exception:
            logger.error(f"[SHEETS] Error al leer {creds_path}:\n{traceback.format_exc()}")
            return None
    elif creds_json:
        logger.debug("[SHEETS] Credenciales desde GOOGLE_CREDENTIALS_JSON")
        try:
            creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
        except Exception:
            logger.error(f"[SHEETS] Error al parsear credenciales:\n{traceback.format_exc()}")
            return None
    else:
        logger.warning(
            f"[SHEETS] Sin credenciales: '{creds_path}' no existe y GOOGLE_CREDENTIALS_JSON no definido"
        )
        return None

    try:
        gc = gspread.authorize(creds)
        return gc.open_by_key(sheets_id).sheet1
    except gspread.exceptions.APIError as e:
        logger.error(f"[SHEETS] No se pudo abrir la hoja (status={e.response.status_code}):\n{traceback.format_exc()}")
        return None
    except Exception:
        logger.error(f"[SHEETS] Error inesperado al abrir la hoja:\n{traceback.format_exc()}")
        return None


def _registrar_en_sheets_sync(telefono: str, mensaje: str, servicio: str = "", zona: str = ""):
    """Añade una fila de lead al Google Sheet. Bloqueante — llamar con asyncio.to_thread."""
    ws = _abrir_hoja_sync()
    if ws is None:
        return

    try:
        if not ws.get_all_values():
            ws.append_row(["Fecha", "Hora", "Teléfono", "Servicio", "Zona", "Mensaje", "Estado"])
            logger.info("[SHEETS] Cabeceras añadidas")

        now = datetime.now()
        ws.append_row([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            telefono,
            servicio,
            zona,
            mensaje,
            "Nuevo",
        ])
        logger.info(f"[SHEETS] Fila añadida para {telefono} | servicio={servicio or '—'} | zona={zona or '—'}")
    except gspread.exceptions.APIError as e:
        logger.error(f"[SHEETS] Error de API (status={e.response.status_code}):\n{traceback.format_exc()}")
    except Exception:
        logger.error(f"[SHEETS] Error inesperado al escribir en Sheets:\n{traceback.format_exc()}")


def _actualizar_zona_sheets_sync(telefono: str, zona: str):
    """
    Busca filas del teléfono en columna C y rellena Zona (columna E) si está vacía.
    Bloqueante — llamar con asyncio.to_thread.
    """
    ws = _abrir_hoja_sync()
    if ws is None:
        return

    try:
        celdas = ws.findall(telefono, in_column=3)
        if not celdas:
            logger.debug(f"[SHEETS] No hay fila para {telefono} — zona no guardada aún")
            return

        for celda in celdas:
            zona_actual = ws.cell(celda.row, 5).value or ""
            if not zona_actual:
                ws.update_cell(celda.row, 5, zona)
                logger.info(f"[SHEETS] Zona '{zona}' guardada en fila {celda.row} para {telefono}")
    except gspread.exceptions.APIError as e:
        logger.error(f"[SHEETS] Error de API al actualizar zona (status={e.response.status_code}):\n{traceback.format_exc()}")
    except Exception:
        logger.error(f"[SHEETS] Error inesperado al actualizar zona:\n{traceback.format_exc()}")


# ─── Wrappers async ───────────────────────────────────────────────────────────

async def registrar_lead_sheets(telefono: str, mensaje: str, servicio: str = "", zona: str = ""):
    """Wrapper async para el registro de lead en Google Sheets."""
    try:
        await asyncio.to_thread(_registrar_en_sheets_sync, telefono, mensaje, servicio, zona)
    except Exception as e:
        logger.error(f"Error Google Sheets: {e}")


async def actualizar_zona_sheets(telefono: str, zona: str):
    """Wrapper async para actualizar la zona en Google Sheets."""
    try:
        await asyncio.to_thread(_actualizar_zona_sheets_sync, telefono, zona)
    except Exception as e:
        logger.error(f"Error Google Sheets (zona): {e}")


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


# ─── Puntos de entrada ────────────────────────────────────────────────────────

async def procesar_posible_lead(
    telefono_cliente: str,
    mensaje: str,
    historial: list[dict] | None = None,
):
    """
    Detecta si el mensaje contiene un número de teléfono.
    Si lo encuentra, extrae servicio y zona (del mensaje actual y del historial previo)
    y registra el lead (DB + notificación + Sheets).
    """
    if not detectar_telefono(mensaje):
        return

    logger.info(f"[LEAD] Teléfono detectado en mensaje de {telefono_cliente}")

    servicio = detectar_servicio(mensaje)

    # Buscar zona en el mensaje actual; si no hay, escanear historial hacia atrás
    zona = detectar_zona(mensaje)
    if not zona and historial:
        for msg in reversed(historial):
            zona = detectar_zona(msg["content"])
            if zona:
                logger.info(f"[LEAD] Zona rescatada del historial: {zona}")
                break

    if servicio:
        logger.info(f"[LEAD] Servicio detectado: {servicio}")
    if zona:
        logger.info(f"[LEAD] Zona detectada: {zona}")

    from agent.memory import guardar_lead

    await asyncio.gather(
        guardar_lead(telefono_cliente, mensaje),
        notificar_lead(telefono_cliente, mensaje),
        registrar_lead_sheets(telefono_cliente, mensaje, servicio, zona or ""),
    )


async def procesar_mensaje_zona(telefono_cliente: str, mensaje: str):
    """
    Detecta si el mensaje menciona una zona de Valencia.
    Si la encuentra y existe fila del cliente en Sheets, actualiza la columna Zona.
    """
    zona = detectar_zona(mensaje)
    if not zona:
        return

    logger.info(f"[ZONA] '{zona}' detectada en mensaje de {telefono_cliente}")
    await actualizar_zona_sheets(telefono_cliente, zona)
