"""Consultation live transcript tables

Revision ID: 010_consultation_transcript
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_consultation_transcript"
down_revision = "009_report_discussion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultation_transcript_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consultation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultations.id"), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("room_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("full_transcript_text", sa.Text(), nullable=True),
        sa.Column("last_insights", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_consultation_transcript_sessions_consultation",
        "consultation_transcript_sessions",
        ["consultation_id"],
    )
    op.create_index(
        "ix_consultation_transcript_sessions_appointment",
        "consultation_transcript_sessions",
        ["appointment_id"],
    )
    op.create_index(
        "ix_consultation_transcript_sessions_status",
        "consultation_transcript_sessions",
        ["status"],
    )

    op.create_table(
        "consultation_transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultation_transcript_sessions.id"),
            nullable=False,
        ),
        sa.Column("speaker_role", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("speaker_label", sa.String(120), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_consultation_transcript_segments_session",
        "consultation_transcript_segments",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_table("consultation_transcript_segments")
    op.drop_table("consultation_transcript_sessions")
