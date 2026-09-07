import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...approvals.service import get_approval, resolve_approval
from ...database.session import get_db
from ...schemas.schemas import ApprovalOut

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{approval_id}/approve", response_model=ApprovalOut)
async def approve(approval_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    approval = await get_approval(db, approval_id)
    if approval is None or approval.status != "pending":
        raise HTTPException(status_code=404, detail="no pending approval with that id")
    return await resolve_approval(db, approval, approved=True)


@router.post("/{approval_id}/reject", response_model=ApprovalOut)
async def reject(approval_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    approval = await get_approval(db, approval_id)
    if approval is None or approval.status != "pending":
        raise HTTPException(status_code=404, detail="no pending approval with that id")
    return await resolve_approval(db, approval, approved=False)
