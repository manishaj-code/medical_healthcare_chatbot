"""Lab test catalog for consultation orders

Revision ID: 008_lab_test_catalog
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = "008_lab_test_catalog"
down_revision = "007_in_person_consultation"
branch_labels = None
depends_on = None

DEFAULT_TESTS = [
    {
        "id": str(uuid.uuid4()),
        "test_code": "cbc",
        "test_name": "CBC",
        "keywords": ["cbc", "complete blood", "blood count", "hemogram"],
        "category": "hematology",
        "description": "Complete blood count",
        "sort_order": 1,
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "test_code": "hba1c",
        "test_name": "HbA1c",
        "keywords": ["hba1c", "a1c", "glycated", "glycosylated"],
        "category": "metabolic",
        "description": "Glycated hemoglobin — diabetes monitoring",
        "sort_order": 2,
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "test_code": "lft",
        "test_name": "LFT",
        "keywords": ["lft", "liver", "liver function", "alt", "ast"],
        "category": "biochemistry",
        "description": "Liver function tests",
        "sort_order": 3,
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "test_code": "kft",
        "test_name": "KFT",
        "keywords": ["kft", "kidney", "renal", "creatinine", "urea"],
        "category": "biochemistry",
        "description": "Kidney function tests",
        "sort_order": 4,
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "test_code": "thyroid",
        "test_name": "Thyroid",
        "keywords": ["thyroid", "tsh", "t3", "t4"],
        "category": "endocrine",
        "description": "Thyroid panel",
        "sort_order": 5,
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "test_code": "vitamin_d",
        "test_name": "Vitamin D",
        "keywords": ["vitamin d", "vit d", "25-oh", "25 hydroxy"],
        "category": "vitamins",
        "description": "Vitamin D level",
        "sort_order": 6,
        "is_active": True,
    },
]


def upgrade() -> None:
    op.create_table(
        "lab_test_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("test_code", sa.String(50), nullable=False, unique=True),
        sa.Column("test_name", sa.String(255), nullable=False),
        sa.Column("keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_lab_test_catalog_active", "lab_test_catalog", ["is_active"])

    catalog = sa.table(
        "lab_test_catalog",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("test_code", sa.String),
        sa.column("test_name", sa.String),
        sa.column("keywords", postgresql.JSONB),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        catalog,
        [
            {
                "id": row["id"],
                "test_code": row["test_code"],
                "test_name": row["test_name"],
                "keywords": row["keywords"],
                "category": row["category"],
                "description": row["description"],
                "sort_order": row["sort_order"],
                "is_active": row["is_active"],
            }
            for row in DEFAULT_TESTS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_lab_test_catalog_active", table_name="lab_test_catalog")
    op.drop_table("lab_test_catalog")
