"""Shared types for multi-agent orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Patient


@dataclass
class AgentContext:
    db: AsyncSession
    conversation: Conversation
    patient: Patient | None
    conv_id: UUID
    text: str
    history: list[dict]
    patient_ctx: dict
    session: dict = field(default_factory=dict)
    tool_result: dict | None = None
    report_id: str | None = None
    is_guest: bool = False
    guest_session_id: str | None = None


@dataclass
class AgentResponse:
    reply: str
    agent: str
    emergency: bool = False
    ui: dict | None = None
    handoff_to: str | None = None
    session_patch: dict | None = None
    clear_session: bool = False
