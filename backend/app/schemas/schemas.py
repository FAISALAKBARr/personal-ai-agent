import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    priority: str | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    due_at: datetime | None
    status: str
    priority: str

    model_config = {"from_attributes": True}


class ApprovalOut(BaseModel):
    id: uuid.UUID
    action: str
    target: str | None
    parameters: dict
    status: str
    expires_at: datetime | None

    model_config = {"from_attributes": True}
