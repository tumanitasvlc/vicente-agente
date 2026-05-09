# agent/tools.py — Herramientas del agente Tu Manitas VLC
# Generado por AgentKit

import os
import yaml
import logging

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención de Tu Manitas VLC."""
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
    }


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


def registrar_solicitud_presupuesto(telefono: str, descripcion: str, zona: str) -> dict:
    """
    Registra una solicitud de presupuesto.
    El equipo llamará al cliente para confirmar precio y disponibilidad.

    Args:
        telefono: Número del cliente
        descripcion: Descripción del trabajo a realizar
        zona: Barrio o municipio donde se realizará el trabajo

    Returns:
        Confirmación de que la solicitud fue registrada
    """
    logger.info(f"[PRESUPUESTO] Teléfono: {telefono} | Zona: {zona} | Trabajo: {descripcion}")
    return {
        "registrado": True,
        "mensaje": "Solicitud registrada. El equipo llamará para confirmar precio y disponibilidad."
    }


def verificar_zona_cobertura(zona: str) -> dict:
    """
    Verifica si una zona está dentro del área de cobertura de Tu Manitas VLC.

    Args:
        zona: Barrio o municipio consultado

    Returns:
        Si está cubierta y si hay suplemento de desplazamiento
    """
    zonas_capital = ["valencia", "ruzafa", "benimaclet", "campanar", "patraix",
                     "extramurs", "poblats", "quatre carreres", "algiros"]

    zonas_metropolitanas = ["paterna", "burjassot", "mislata", "torrent", "sedaví",
                            "sedavi", "xirivella", "alboraya"]

    zona_lower = zona.lower()

    if any(z in zona_lower for z in zonas_capital) or any(z in zona_lower for z in zonas_metropolitanas):
        return {"cobertura": True, "suplemento": False, "nota": "Zona cubierta, desplazamiento incluido."}
    else:
        return {"cobertura": None, "suplemento": None, "nota": "Zona fuera del radio habitual. Puede aplicar suplemento de 10-15 €. Confirmar con el equipo."}
