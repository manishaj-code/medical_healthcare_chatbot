"""In-person consultation workflow tables

Revision ID: 007_in_person_consultation
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_in_person_consultation"
down_revision = "006_urgent_consult"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultation_intakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("structured_intake", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ai_risk_level", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), server_default="ready"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("appointment_id", name="uq_consultation_intake_appointment"),
    )
    op.create_index("ix_consultation_intakes_patient", "consultation_intakes", ["patient_id"])

    op.create_table(
        "consultations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("consultation_mode", sa.String(20), server_default="in_person"),
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("clinical_findings", sa.Text, nullable=True),
        sa.Column("diagnosis", sa.Text, nullable=True),
        sa.Column("doctor_notes", sa.Text, nullable=True),
        sa.Column("treatment_plan", sa.Text, nullable=True),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("doctor_signature_json", postgresql.JSONB, nullable=True),
        sa.Column("ai_summary_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("ai_suggestion_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("appointment_id", name="uq_consultation_appointment"),
    )
    op.create_index("ix_consultations_patient", "consultations", ["patient_id"])
    op.create_index("ix_consultations_doctor", "consultations", ["doctor_id"])
    op.create_index("ix_consultations_status", "consultations", ["status"])

    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_prescriptions_consultation", "prescriptions", ["consultation_id"])

    op.create_table(
        "prescription_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prescription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("prescriptions.id"), nullable=False),
        sa.Column("medicine_name", sa.String(255), nullable=False),
        sa.Column("strength", sa.String(100), nullable=True),
        sa.Column("frequency", sa.String(100), nullable=True),
        sa.Column("duration", sa.String(100), nullable=True),
        sa.Column("instructions", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("source", sa.String(30), server_default="manual"),
    )
    op.create_index("ix_prescription_items_prescription", "prescription_items", ["prescription_id"])

    op.create_table(
        "lab_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id"), nullable=False),
        sa.Column("test_code", sa.String(50), nullable=False),
        sa.Column("test_name", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="ordered"),
    )
    op.create_index("ix_lab_orders_consultation", "lab_orders", ["consultation_id"])

    op.create_table(
        "consultation_ai_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id"), nullable=False),
        sa.Column("suggestion_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_type", sa.String(50), nullable=False),
        sa.Column("ai_payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("doctor_action", sa.String(30), nullable=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consultation_ai_audit_consultation", "consultation_ai_audit", ["consultation_id"])


def downgrade() -> None:
    op.drop_table("consultation_ai_audit")
    op.drop_table("lab_orders")
    op.drop_table("prescription_items")
    op.drop_table("prescriptions")
    op.drop_table("consultations")
    op.drop_table("consultation_intakes")
