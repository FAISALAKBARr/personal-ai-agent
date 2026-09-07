from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.router import router
from .database.init_db import init_db
from .scheduler.service import scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Personal AI Agent — Phase 1", lifespan=lifespan)
app.include_router(router)
