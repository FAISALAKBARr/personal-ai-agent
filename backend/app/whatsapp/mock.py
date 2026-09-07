from .base import InboundMessage, WhatsAppGateway


class MockGateway(WhatsAppGateway):
    """
    No real WhatsApp connection. Outgoing messages just get printed to the
    backend's console. POST /messages with a JSON body matching
    InboundMessage directly to exercise the full orchestrator -> firewall ->
    tools -> scheduler -> audit loop before Baileys is wired up.
    """

    async def send_message(self, to: str, text: str) -> None:
        print(f"[MOCK WHATSAPP -> {to}]\n{text}\n")

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        return InboundMessage(**payload)

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        return True  # nothing to verify in mock mode
