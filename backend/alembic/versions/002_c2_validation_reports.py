"""Add c2_validation_reports table and review_basis to c2_workflow_models.

Revision ID: c2_002_validation
Revises: c2_001_initial
Create Date: 2026-10-14 14:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c2_002_validation"
down_revision: Union[str, None] = "c2_001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add review_basis column to c2_workflow_models
    op.add_column(
        "c2_workflow_models",
        sa.Column("review_basis", sa.String(length=255), nullable=True),
    )

    # 2. Create c2_validation_reports table
    op.create_table(
        "c2_validation_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "validator_version",
            sa.String(length=32),
            server_default="2.0.0",
            nullable=False,
        ),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("has_blocking_issues", sa.Boolean(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_c2_validation_reports_project_id"),
        "c2_validation_reports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c2_validation_reports_model_id"),
        "c2_validation_reports",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c2_validation_reports_definition_hash"),
        "c2_validation_reports",
        ["definition_hash"],
        unique=False,
    )
    op.create_index(
        "ix_c2_val_project_model_version",
        "c2_validation_reports",
        ["project_id", "model_id", "version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_c2_val_project_model_version",
        table_name="c2_validation_reports",
    )
    op.drop_index(
        op.f("ix_c2_validation_reports_definition_hash"),
        table_name="c2_validation_reports",
    )
    op.drop_index(
        op.f("ix_c2_validation_reports_model_id"),
        table_name="c2_validation_reports",
    )
    op.drop_index(
        op.f("ix_c2_validation_reports_project_id"),
        table_name="c2_validation_reports",
    )
    op.drop_table("c2_validation_reports")
    op.drop_column("c2_workflow_models", "review_basis")
