import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.session import get_db
from ...schemas.schemas import TaskCreate, TaskOut, TaskUpdate
from ...tools.task_tools import create_task, get_tasks, update_task

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Phase 1 is single-user with no dashboard auth yet, so user_id is passed
# explicitly for now — replace with a real auth dependency in Phase 7.


@router.get("", response_model=list[TaskOut])
async def list_tasks(user_id: uuid.UUID, status: str | None = None, db: AsyncSession = Depends(get_db)):
    result = await get_tasks(db=db, user_id=user_id, status=status)
    return result.data


@router.post("", response_model=dict)
async def create_task_endpoint(user_id: uuid.UUID, payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    result = await create_task(db=db, user_id=user_id, **payload.model_dump())
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.patch("/{task_id}", response_model=dict)
async def update_task_endpoint(user_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await update_task(db=db, user_id=user_id, task_id=str(task_id), **payload.model_dump(exclude_unset=True))
    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data
