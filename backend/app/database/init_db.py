"""
Phase 1 uses Base.metadata.create_all() on startup instead of Alembic.
Deliberate simplification: the schema is still moving, and for a
single-developer personal project, versioned migrations earn their keep
once the schema stabilizes — not before. When you're ready, `alembic init`
here and generate the first migration from these same models.
"""

from .base import Base
from .session import engine

# Import models so they're registered on Base.metadata before create_all runs.
from ..models import models as _models  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
