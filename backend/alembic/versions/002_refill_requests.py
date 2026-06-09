"""Add refill_requests table

Revision ID: 002_refill_requests
Revises: 001_initial_schema
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_refill_requests"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refill_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("medication_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medications.id"), nullable=True),
        sa.Column("medication_name", sa.String(255), nullable=False),
        sa.Column("medication_dosage", sa.String(100), nullable=True),
        sa.Column("medication_frequency", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_refill_requests_patient_id", "refill_requests", ["patient_id"])
    op.create_index("ix_refill_requests_doctor_id", "refill_requests", ["doctor_id"])
    op.create_index("ix_refill_requests_status", "refill_requests", ["status"])


def downgrade() -> None:
    op.drop_table("refill_requests")
