from uuid import UUID
from typing import Any
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime

class FieldUpdate(SQLModel, table=True):
    id: UUID = Field(primary_key=True)
    event: UUID
    field: str
    setter: str
    subject_type: str
    subject_identifier: str
    body: Any = Field(sa_column=Column(JSON, nullable=False))
    updated_at: datetime
    params: dict[str, str] = Field(sa_column=Column(JSON, nullable=False))

    # needed for Column(JSON)
    class Config:
        arbitrary_types_allowed = True