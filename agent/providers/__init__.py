# agent/providers/__init__.py — Proveedores de WhatsApp (Meta + Twilio en paralelo)

from agent.providers.meta import ProveedorMeta
from agent.providers.twilio import ProveedorTwilio

# Instancias únicas reutilizables
proveedor_meta = ProveedorMeta()
proveedor_twilio = ProveedorTwilio()
