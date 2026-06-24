"""Alembic migration: rag_chunks vector table."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "012_rag_chunks"
down_revision = "011_audit_log_action_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("index_type", sa.String(40), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rag_chunks_index_patient", "rag_chunks", ["index_type", "patient_id"])
    op.create_index("ix_rag_chunks_source", "rag_chunks", ["index_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_source", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_index_patient", table_name="rag_chunks")
    op.drop_table("rag_chunks")
