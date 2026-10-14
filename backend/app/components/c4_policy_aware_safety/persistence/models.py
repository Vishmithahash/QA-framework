"""SQLAlchemy models for C4 persistence, mapped to framework Base."""

from datetime import datetime, timezone
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.database import Base

# Use JSON that falls back gracefully across Postgres and SQLite test environments
JsonType = JSON().with_variant(JSONB, "postgresql")


class C4ArtifactModel(Base):
    __tablename__ = "c4_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_id", "version", name="uq_c4_artifacts_proj_id_ver"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    sections_json: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class C4PolicyContractModel(Base):
    __tablename__ = "c4_policy_contracts"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "contract_id", "version", name="uq_c4_contracts_proj_id_ver"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    referenced_artifact_versions_json: Mapped[dict] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    validation_issues_json: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    acceptance_metadata_json: Mapped[dict | None] = mapped_column(
        JsonType, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    rules: Mapped[list["C4PolicyRuleModel"]] = relationship(
        "C4PolicyRuleModel",
        back_populates="contract",
        cascade="all, delete-orphan",
    )


class C4PolicyRuleModel(Base):
    __tablename__ = "c4_policy_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_db_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("c4_policy_contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    family: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_boundary: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_json: Mapped[dict] = mapped_column(JsonType, nullable=False)

    contract: Mapped[C4PolicyContractModel] = relationship(
        "C4PolicyContractModel", back_populates="rules"
    )


class C4EvaluationFindingModel(Base):
    __tablename__ = "c4_evaluation_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    contract_id: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    violation_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    finding_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
