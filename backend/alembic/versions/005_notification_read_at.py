"""Add read_at to notifications for unread tracking."""
from alembic import op
import sqlalchemy as sa

revision = "005_notification_read_at"
down_revision = "004_doctor_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "read_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_column("notifications", "read_at")
