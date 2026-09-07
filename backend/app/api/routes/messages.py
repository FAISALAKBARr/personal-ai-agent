import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agents.orchestrator import handle_message
from ...agents.providers import get_provider
from ...auth.security import is_allowed_number
from ...core.config import settings
from ...database.session import get_db
from ...models.models import Conversation, Message, SystemState, User
from ...whatsapp import get_gateway

router = APIRouter()
_gateway = get_gateway(settings)
_provider = get_provider(settings)


@router.post("/messages")
async def receive_message(request: Request, db: AsyncSession = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Signature")
    if not _gateway.verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = await request.json()
    inbound = _gateway.parse_webhook(payload)
    if inbound is None:
        return {"status": "ignored"}

    if not is_allowed_number(inbound.user_id, settings):
        return {"status": "ignored"}  # no reply at all — don't confirm the bot exists to strangers

    # Idempotency: WhatsApp (and any webhook sender) can and will redeliver.
    existing = await db.execute(select(Message).where(Message.whatsapp_message_id == inbound.message_id))
    if existing.scalar_one_or_none() is not None:
        return {"status": "duplicate_ignored"}

    paused = await db.get(SystemState, "paused")
    if paused is not None and paused.value == "true":
        return {"status": "paused"}

    user = await _get_or_create_user(db, inbound.user_id)
    conversation = await _get_or_create_conversation(db, user.id)

    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            whatsapp_message_id=inbound.message_id,
            direction="in",
            content=inbound.text or "",
            message_type=inbound.message_type,
        )
    )
    conversation.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    now_iso = datetime.now(timezone.utc).isoformat()
    reply_text = await handle_message(db, user, inbound.text or "", _provider, now_iso)

    await _gateway.send_message(to=user.whatsapp_number, text=reply_text)
    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            whatsapp_message_id=f"out-{uuid.uuid4()}",
            direction="out",
            content=reply_text,
        )
    )
    await db.commit()

    return {"status": "ok"}


async def _get_or_create_user(db: AsyncSession, whatsapp_number: str) -> User:
    result = await db.execute(select(User).where(User.whatsapp_number == whatsapp_number))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=uuid.uuid4(), whatsapp_number=whatsapp_number)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _get_or_create_conversation(db: AsyncSession, user_id: uuid.UUID) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.started_at.desc())
    )
    conversation = result.scalars().first()
    if conversation is None:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
    return conversation
