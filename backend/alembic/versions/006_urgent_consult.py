"""Urgent consult requests and doctor offers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_urgent_consult"
down_revision = "005_notification_read_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "urgent_consult_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("symptoms_json", postgresql.JSONB, nullable=False),
        sa.Column("specialty", sa.String(120), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("accepted_doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("patient_message", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_urgent_consult_requests_patient", "urgent_consult_requests", ["patient_id"])
    op.create_index("ix_urgent_consult_requests_status", "urgent_consult_requests", ["status"])

    op.create_table(
        "urgent_consult_offers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("urgent_consult_requests.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="notified"),
        sa.Column("notified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("request_id", "doctor_id", name="uq_urgent_consult_offer"),
    )
    op.create_index("ix_urgent_consult_offers_request", "urgent_consult_offers", ["request_id"])
    op.create_index("ix_urgent_consult_offers_doctor", "urgent_consult_offers", ["doctor_id"])


def downgrade() -> None:
    op.drop_table("urgent_consult_offers")
    op.drop_table("urgent_consult_requests")
