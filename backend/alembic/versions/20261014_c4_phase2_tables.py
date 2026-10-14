"""Add C4 Phase 2 tables for automated test generation and case contracts.

Revision ID: 20261014_c4_phase2
Revises: 20261013_c4_phase1
Create Date: 2026-10-14 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20261014_c4_phase2"
down_revision = "20261013_c4_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. c4_domain_bindings
    op.create_table(
        "c4_domain_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("domain_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=True),
        sa.Column(
            "binding_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "domain_id",
            "version",
            name="uq_c4_domain_bindings_proj_dom_ver",
        ),
    )
    op.create_index(
        op.f("ix_c4_domain_bindings_project_id"),
        "c4_domain_bindings",
        ["project_id"],
        unique=False,
    )

    # 2. c4_generation_batches
    op.create_table(
        "c4_generation_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.String(length=128), nullable=False),
        sa.Column("domain_binding_version", sa.String(length=64), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "report_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index(
        op.f("ix_c4_generation_batches_batch_id"),
        "c4_generation_batches",
        ["batch_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_c4_generation_batches_project_id"),
        "c4_generation_batches",
        ["project_id"],
        unique=False,
    )

    # 3. c4_test_cases
    op.create_table(
        "c4_test_cases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("domain_id", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "case_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "case_id", "version", name="uq_c4_test_cases_proj_case_ver"
        ),
    )
    op.create_index(
        op.f("ix_c4_test_cases_case_id"), "c4_test_cases", ["case_id"], unique=False
    )
    op.create_index(
        op.f("ix_c4_test_cases_batch_id"), "c4_test_cases", ["batch_id"], unique=False
    )
    op.create_index(
        op.f("ix_c4_test_cases_project_id"),
        "c4_test_cases",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c4_test_cases_lifecycle_status"),
        "c4_test_cases",
        ["lifecycle_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("c4_test_cases")
    op.drop_table("c4_generation_batches")
    op.drop_table("c4_domain_bindings")
