from fastapi import APIRouter

from .routes import approvals, messages, tasks

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


router.include_router(messages.router)
router.include_router(tasks.router)
router.include_router(approvals.router)
