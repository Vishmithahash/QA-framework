"""Add C4 Phase 1 tables for policy-aware safety and prompt-injection testing.

Revision ID: 20261013_c4_phase1
Revises:
Create Date: 2026-10-13 22:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20261013_c4_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. c4_artifacts
    op.create_table(
        "c4_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=False),
        sa.Column(
            "sections_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "artifact_id", "version", name="uq_c4_artifacts_proj_id_ver"
        ),
    )
    op.create_index(
        op.f("ix_c4_artifacts_project_id"), "c4_artifacts", ["project_id"], unique=False
    )

    # 2. c4_policy_contracts
    op.create_table(
        "c4_policy_contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "referenced_artifact_versions_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "validation_issues_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "acceptance_metadata_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "contract_id", "version", name="uq_c4_contracts_proj_id_ver"
        ),
    )
    op.create_index(
        op.f("ix_c4_policy_contracts_project_id"),
        "c4_policy_contracts",
        ["project_id"],
        unique=False,
    )

    # 3. c4_policy_rules
    op.create_table(
        "c4_policy_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_db_id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("family", sa.String(length=64), nullable=False),
        sa.Column("evaluation_boundary", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "rule_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["contract_db_id"], ["c4_policy_contracts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_c4_policy_rules_contract_db_id"),
        "c4_policy_rules",
        ["contract_db_id"],
        unique=False,
    )

    # 4. c4_evaluation_findings
    op.create_table(
        "c4_evaluation_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("finding_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("contract_id", sa.String(length=128), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("violation_stage", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column(
            "finding_json",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id"),
    )
    op.create_index(
        op.f("ix_c4_evaluation_findings_case_id"),
        "c4_evaluation_findings",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c4_evaluation_findings_finding_id"),
        "c4_evaluation_findings",
        ["finding_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_c4_evaluation_findings_project_id"),
        "c4_evaluation_findings",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c4_evaluation_findings_run_id"),
        "c4_evaluation_findings",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_c4_evaluation_findings_verdict"),
        "c4_evaluation_findings",
        ["verdict"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("c4_evaluation_findings")
    op.drop_table("c4_policy_rules")
    op.drop_table("c4_policy_contracts")
    op.drop_table("c4_artifacts")
