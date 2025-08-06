"""
Configuración de cliente por nombre
"""
from config.clients.walmart import WalmartConfig
from config.clients.cencosud import CencosudConfig
from config.clients.disvet import DisvetConfig

CLIENT_CONFIG_MAP = {
    "walmart": WalmartConfig,
    "cencosud": CencosudConfig,
    "disvet": DisvetConfig,
}

def get_client_config(client):
    """Si el cliente no está configurado, devuelve conf genérica"""
    client_name = client.lower()
    return CLIENT_CONFIG_MAP.get(client_name)