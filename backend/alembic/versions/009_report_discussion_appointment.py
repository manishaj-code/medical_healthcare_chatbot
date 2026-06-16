"""Report discussion appointment fields

Revision ID: 009_report_discussion
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009_report_discussion"
down_revision = "008_lab_test_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("appointment_reason", sa.Text(), nullable=True))
    op.add_column(
        "appointments",
        sa.Column("linked_report_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_appointments_linked_report",
        "appointments",
        "reports",
        ["linked_report_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_appointments_linked_report", "appointments", type_="foreignkey")
    op.drop_column("appointments", "linked_report_id")
    op.drop_column("appointments", "appointment_reason")
