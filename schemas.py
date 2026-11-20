from datetime import datetime
from pydantic import BaseModel


class DepartmentOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ComplaintOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    location: str | None = None
    status: str
    created_at: datetime | None = None
    department_id: int | None = None

    model_config = {"from_attributes": True}

class ComplaintCreate(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    department_id: int | None = None


class StatusUpdate(BaseModel):
    status: str