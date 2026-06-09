import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MessageRole, RiskLevel


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    active_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tool_calls_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    safety_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SymptomAssessment(Base):
    __tablename__ = "symptom_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    symptoms_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(String(20), nullable=True)
    recommended_specialty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recommendation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
