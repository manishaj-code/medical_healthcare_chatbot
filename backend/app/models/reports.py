import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    file_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientSummary(Base):
    __tablename__ = "patient_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("appointments.id"))
    version: Mapped[int] = mapped_column(default=1)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_artifact_ids_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DoctorNote(Base):
    __tablename__ = "doctor_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"))
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("appointments.id"))
    subjective: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
