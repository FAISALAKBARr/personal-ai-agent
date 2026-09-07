from ..core.config import Settings


def is_allowed_number(phone: str, settings: Settings) -> bool:
    """
    Phase 1 is single-user: only numbers in WHATSAPP_ALLOWED_NUMBERS get a
    response at all. Everyone else is silently ignored — no error reply,
    so an unknown sender can't even confirm the bot exists.
    """
    return phone in settings.allowed_numbers_list
