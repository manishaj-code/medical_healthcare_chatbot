"""Add extended doctor profile fields."""
from alembic import op
import sqlalchemy as sa

revision = "004_doctor_profiles"
down_revision = "003_reminders_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("doctors", sa.Column("qualifications", sa.String(255), nullable=True))
    op.add_column("doctors", sa.Column("profile_image_url", sa.String(512), nullable=True))
    op.add_column("doctors", sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=True))
    op.add_column("doctors", sa.Column("hospital_name", sa.String(255), nullable=True))
    op.add_column("doctors", sa.Column("clinic_address", sa.Text(), nullable=True))
    op.add_column("doctors", sa.Column("professional_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("doctors", "professional_summary")
    op.drop_column("doctors", "clinic_address")
    op.drop_column("doctors", "hospital_name")
    op.drop_column("doctors", "consultation_fee")
    op.drop_column("doctors", "profile_image_url")
    op.drop_column("doctors", "qualifications")
