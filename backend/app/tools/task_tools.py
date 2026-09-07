import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Task
from .base import ToolResult, register_tool


@register_tool("get_tasks", "List the user's tasks, optionally filtered by status (pending/done/cancelled).")
async def get_tasks(db: AsyncSession, user_id: uuid.UUID, status: str | None = None) -> ToolResult:
    stmt = select(Task).where(Task.user_id == user_id)
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.due_at.is_(None), Task.due_at)
    rows = (await db.execute(stmt)).scalars().all()
    return ToolResult(
        success=True,
        data=[
            {
                "id": str(t.id),
                "title": t.title,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "status": t.status,
                "priority": t.priority,
            }
            for t in rows
        ],
    )


@register_tool("create_task", "Create a new task or todo item for the user. No scheduled reminder is fired for this — use create_reminder for that.")
async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    description: str | None = None,
    due_at: datetime | None = None,
    priority: str = "normal",
) -> ToolResult:
    if not title or not title.strip():
        return ToolResult(success=False, error="title is required")
    task = Task(
        id=uuid.uuid4(), user_id=user_id, title=title.strip(), description=description, due_at=due_at, priority=priority
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return ToolResult(success=True, data={"id": str(task.id), "title": task.title, "due_at": due_at.isoformat() if due_at else None})


@register_tool("update_task", "Update fields on an existing task (title, description, due_at, status, priority).")
async def update_task(db: AsyncSession, user_id: uuid.UUID, task_id: str, **fields) -> ToolResult:
    task = await db.get(Task, uuid.UUID(task_id))
    if task is None or task.user_id != user_id:
        return ToolResult(success=False, error="task not found")
    for key, value in fields.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return ToolResult(success=True, data={"id": str(task.id), "status": task.status})


@register_tool("create_reminder", "Create a task with a due time AND schedule a WhatsApp reminder to fire at that time. Use this for any 'remind me to...' request.")
async def create_reminder(db: AsyncSession, user_id: uuid.UUID, title: str, remind_at: datetime) -> ToolResult:
    task_result = await create_task(db, user_id, title=title, due_at=remind_at)
    if not task_result.success:
        return task_result

    # Local import: avoids a module-load-time cycle between tools <-> scheduler.
    from ..scheduler.service import schedule_reminder

    await schedule_reminder(task_id=uuid.UUID(task_result.data["id"]), user_id=user_id, run_at=remind_at)
    return task_result
