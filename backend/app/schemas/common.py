from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str | None = None
    timestamp: datetime | None = None


class ResponseEnvelope(BaseModel, Generic[T]):
    data: T
    meta: Meta | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IDResponse(BaseModel):
    id: UUID
