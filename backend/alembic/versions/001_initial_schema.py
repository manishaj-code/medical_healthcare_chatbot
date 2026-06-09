"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("last_login", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True),
        sa.Column("dob", sa.Date()),
        sa.Column("gender", sa.String(20)),
        sa.Column("blood_group", sa.String(10)),
        sa.Column("phone", sa.String(20)),
        sa.Column("preferred_language", sa.String(10), server_default="en"),
    )

    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True),
        sa.Column("experience_years", sa.Integer(), default=0),
        sa.Column("bio", sa.Text()),
        sa.Column("rating", sa.Numeric(3, 2), default=4.5),
        sa.Column("is_verified", sa.Boolean(), default=True),
    )

    op.create_table(
        "specializations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text()),
    )

    op.create_table(
        "doctor_specializations",
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), primary_key=True),
        sa.Column("specialization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("specializations.id"), primary_key=True),
    )

    op.create_table(
        "doctor_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id")),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("slot_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(20), default="available"),
        sa.UniqueConstraint("doctor_id", "slot_date", "slot_time", name="uq_doctor_slot"),
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id")),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("slot_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(20), default="confirmed"),
        sa.Column("rescheduled_from_id", postgresql.UUID(as_uuid=True)),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("title", sa.String(255)),
        sa.Column("emergency_flag", sa.Boolean(), default=False),
        sa.Column("active_agent", sa.String(50)),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id")),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.String(50)),
        sa.Column("tool_calls_json", postgresql.JSONB()),
        sa.Column("safety_flags", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "symptom_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id")),
        sa.Column("symptoms_json", postgresql.JSONB()),
        sa.Column("duration", sa.String(100)),
        sa.Column("severity", sa.String(50)),
        sa.Column("risk_level", sa.String(20)),
        sa.Column("recommended_specialty", sa.String(100)),
        sa.Column("recommendation_text", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "medical_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("condition", sa.String(255), nullable=False),
        sa.Column("diagnosed_year", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "medications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dosage", sa.String(100)),
        sa.Column("frequency", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "allergies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("allergen", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(50), default="moderate"),
        sa.Column("reaction", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), default="application/pdf"),
        sa.Column("file_checksum", sa.String(64)),
        sa.Column("ocr_text", sa.Text()),
        sa.Column("analysis_json", postgresql.JSONB()),
        sa.Column("is_encrypted", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "patient_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id")),
        sa.Column("version", sa.Integer(), default=1),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("source_artifact_ids_json", postgresql.JSONB()),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "doctor_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id")),
        sa.Column("subjective", sa.Text()),
        sa.Column("objective", sa.Text()),
        sa.Column("assessment", sa.Text()),
        sa.Column("plan", sa.Text()),
        sa.Column("private_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), default=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("status_code", sa.Integer()),
        sa.Column("metadata_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "conversation_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id")),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("source_conversation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in [
        "conversation_memory", "audit_logs", "notifications", "refresh_tokens",
        "doctor_notes", "patient_summaries", "reports", "allergies", "medications",
        "medical_history", "symptom_assessments", "messages", "conversations",
        "appointments", "doctor_availability", "doctor_specializations",
        "specializations", "doctors", "patients", "users",
    ]:
        op.drop_table(table)
