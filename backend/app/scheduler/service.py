import uuid

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..core.config import settings

# NOTE: SQLAlchemyJobStore needs a *sync* driver (psycopg2), not asyncpg —
# that's why config.py carries both database_url and database_url_sync.
scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=settings.database_url_sync)})


def start_scheduler() -> None:
    scheduler.start()


async def schedule_reminder(task_id: uuid.UUID, user_id: uuid.UUID, run_at) -> None:
    scheduler.add_job(
        fire_reminder,
        trigger="date",
        run_date=run_at,
        args=[str(task_id), str(user_id)],
        id=f"reminder-{task_id}",
        replace_existing=True,
        misfire_grace_time=3600,  # if we were down when it should've fired, still fire within 1h of restart
    )


async def fire_reminder(task_id: str, user_id: str) -> None:
    """
    Runs inside APScheduler's own event loop — AsyncIOScheduler supports
    coroutine job functions directly. Because the jobstore is persisted to
    Postgres, this job survives a container restart: on boot, APScheduler
    reloads it from the DB and still fires it (or immediately, if the time
    already passed and it's within misfire_grace_time).
    """
    # Local imports: avoids a module-load-time cycle (scheduler <-> whatsapp/db).
    from sqlalchemy import select

    from ..database.session import SessionLocal
    from ..models.models import SystemState, Task, User
    from ..whatsapp import get_gateway

    async with SessionLocal() as db:
        paused = await db.get(SystemState, "paused")
        if paused is not None and paused.value == "true":
            return  # kill switch is on — don't send, don't reschedule

        task = await db.get(Task, uuid.UUID(task_id))
        user = await db.get(User, uuid.UUID(user_id))
        if task is None or user is None or task.status == "cancelled":
            return

        gateway = get_gateway(settings)
        await gateway.send_message(to=user.whatsapp_number, text=f"⏰ Reminder: {task.title}")

        task.status = "done"
        await db.commit()
