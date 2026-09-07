from ..core.config import Settings
from .base import WhatsAppGateway
from .baileys import BaileysGateway
from .mock import MockGateway

_gateway_instance: WhatsAppGateway | None = None


def get_gateway(settings: Settings) -> WhatsAppGateway:
    """Cached singleton — one gateway instance per process."""
    global _gateway_instance
    if _gateway_instance is None:
        if settings.whatsapp_provider == "baileys":
            _gateway_instance = BaileysGateway(settings.baileys_bridge_url, settings.whatsapp_webhook_secret)
        else:
            _gateway_instance = MockGateway()
    return _gateway_instance
