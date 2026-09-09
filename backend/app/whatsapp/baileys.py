"""
Baileys itself is a TypeScript/Node.js library — it can't be called directly
from Python. This adapter is an HTTP-bridge client: it assumes a small
companion Node service (not built yet — that's the next piece) exposing:

    POST /send   { "to": "<number>", "text": "<message>" }
    -> and that service forwards *inbound* WhatsApp messages to our
       FastAPI POST /messages webhook, in whatever shape it chooses,
       which is why parse_webhook() below is intentionally minimal.

Wiring this up for real: build the bridge service (Baileys + a tiny Express
or Fastify app), point BAILEYS_BRIDGE_URL at it, set WHATSAPP_PROVIDER=baileys,
then adjust parse_webhook() to match whatever payload shape the bridge sends.
"""

import hashlib
import hmac

import httpx

from .base import InboundMessage, WhatsAppGateway


class BaileysGateway(WhatsAppGateway):
    def __init__(self, bridge_url: str, webhook_secret: str):
        self.bridge_url = bridge_url.rstrip("/")
        self.webhook_secret = webhook_secret

    async def send_message(self, to: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.bridge_url}/send",
                json={"to": to, "text": text},
                headers={"X-Bridge-Secret": self.webhook_secret},
            )
            resp.raise_for_status()

    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        if payload.get("type") != "message":
            return None
        return InboundMessage(
            user_id=payload["from"],
            message_id=payload["id"],
            timestamp=str(payload.get("timestamp", "")),
            text=payload.get("text"),
        )

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        if not signature_header:
            return False
        expected = hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header)
