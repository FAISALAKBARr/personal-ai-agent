from abc import ABC, abstractmethod

from pydantic import BaseModel


class InboundMessage(BaseModel):
    user_id: str  # WhatsApp number, E.164-ish, e.g. "+62812xxxxxxx"
    message_id: str
    conversation_id: str | None = None
    timestamp: str = ""
    message_type: str = "text"
    text: str | None = None
    media: dict | None = None
    metadata: dict = {}


class WhatsAppGateway(ABC):
    """
    Every concrete gateway (mock, Baileys, Cloud API) implements this.
    The rest of the app (orchestrator, API routes) only ever talks to this
    interface — swapping providers later means writing one new adapter, not
    touching the orchestrator.
    """

    @abstractmethod
    async def send_message(self, to: str, text: str) -> None: ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> InboundMessage | None:
        """Return None to silently ignore a payload (e.g. a status callback, not a message)."""
        ...

    @abstractmethod
    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool: ...
