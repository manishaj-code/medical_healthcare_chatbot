from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MessageRole
from app.schemas.common import ORMBase


class ConversationCreate(BaseModel):
    title: str | None = None
    language: str = "en"
    local_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    tz_offset_minutes: int | None = Field(default=None, description="Minutes east of UTC (e.g. 330 for IST)")


class TodayConversationEnsure(BaseModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    tz_offset_minutes: int = Field(description="Minutes east of UTC (e.g. 330 for IST)")
    title: str | None = None
    language: str = "en"


class MessageCreate(BaseModel):
    message: str = Field(min_length=1)
    report_id: UUID | None = None
    attachment_filename: str | None = None
    attachment_size_bytes: int | None = Field(default=None, ge=0)


class ReportUploadCreate(BaseModel):
    report_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int | None = Field(default=None, ge=0)


class MessageResponse(ORMBase):
    id: UUID
    role: MessageRole
    content: str
    agent_name: str | None
    created_at: datetime
    ui: dict[str, Any] | None = None
    attachment: dict[str, Any] | None = None
    report_ack: bool = False
    emergency: bool = False


class ConversationResponse(ORMBase):
    id: UUID
    title: str | None
    emergency_flag: bool
    active_agent: str | None
    language: str
    created_at: datetime


class ChatReply(BaseModel):
    reply: str
    agent: str
    emergency: bool = False
    message_id: UUID | None = None
    ui: dict[str, Any] | None = None
