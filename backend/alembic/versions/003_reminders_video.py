"""Phase 3: scheduled reminders and video consultations

Revision ID: 003_reminders_video
Revises: 002_refill_requests
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_reminders_video"
down_revision = "002_refill_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("consultation_mode", sa.String(20), nullable=False, server_default="in_person"),
    )
    op.add_column("appointments", sa.Column("video_room_id", sa.String(64), nullable=True))
    op.add_column("appointments", sa.Column("video_enabled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "appointment_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes_before", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_appointment_reminders_remind_at", "appointment_reminders", ["remind_at"])
    op.create_index("ix_appointment_reminders_appointment_id", "appointment_reminders", ["appointment_id"])


def downgrade() -> None:
    op.drop_table("appointment_reminders")
    op.drop_column("appointments", "video_enabled_at")
    op.drop_column("appointments", "video_room_id")
    op.drop_column("appointments", "consultation_mode")
