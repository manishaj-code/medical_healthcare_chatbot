"""Widen audit_logs.action for long API paths."""

from alembic import op
import sqlalchemy as sa

revision = "011_audit_log_action_length"
down_revision = "010_consultation_transcript"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "action",
        existing_type=sa.String(100),
        type_=sa.String(255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "action",
        existing_type=sa.String(255),
        type_=sa.String(100),
        existing_nullable=False,
    )
