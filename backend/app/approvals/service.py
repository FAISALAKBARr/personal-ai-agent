import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Approval

APPROVAL_TTL_MINUTES = 15


async def create_approval(
    db: AsyncSession, *, user_id: uuid.UUID, action: str, target: str | None, parameters: dict
) -> Approval:
    approval = Approval(
        id=uuid.uuid4(),
        user_id=user_id,
        action=action,
        target=target,
        parameters=parameters,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=APPROVAL_TTL_MINUTES),
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def get_pending_approval(db: AsyncSession, user_id: uuid.UUID) -> Approval | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Approval).where(Approval.user_id == user_id, Approval.status == "pending", Approval.expires_at > now)
    )
    return result.scalars().first()


async def resolve_approval(db: AsyncSession, approval: Approval, *, approved: bool) -> Approval:
    approval.status = "approved" if approved else "rejected"
    approval.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)
    return approval


async def get_approval(db: AsyncSession, approval_id: uuid.UUID) -> Approval | None:
    return await db.get(Approval, approval_id)
