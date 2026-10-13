"""Create c2_workflow_models table for Component 2.

Revision ID: c2_001_initial
Revises: None
Create Date: 2026-10-13 12:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c2_001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "c2_workflow_models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=32),
            server_default="1.0.0",
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "model_id",
            "version",
            name="uq_c2_model_project_model_version",
        ),
    )
    op.create_index(
        op.f("ix_c2_workflow_models_model_id"),
        "c2_workflow_models",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c2_workflow_models_project_id"),
        "c2_workflow_models",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c2_workflow_models_domain"),
        "c2_workflow_models",
        ["domain"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c2_workflow_models_lifecycle_status"),
        "c2_workflow_models",
        ["lifecycle_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_c2_workflow_models_lifecycle_status"),
        table_name="c2_workflow_models",
    )
    op.drop_index(
        op.f("ix_c2_workflow_models_domain"),
        table_name="c2_workflow_models",
    )
    op.drop_index(
        op.f("ix_c2_workflow_models_project_id"),
        table_name="c2_workflow_models",
    )
    op.drop_index(
        op.f("ix_c2_workflow_models_model_id"),
        table_name="c2_workflow_models",
    )
    op.drop_table("c2_workflow_models")
