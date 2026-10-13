"""SQLAlchemy ORM model for C2 workflow model persistence."""

import uuid
from datetime import datetime
from sqlalchemy import (
    JSON,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class C2WorkflowModel(Base):
    """Persisted behavioral FSM/EFSM reference model.

    Table prefix: c2_
    Stores versioned definition JSON, lifecycle status, content hash, and audit metadata.
    """

    __tablename__ = "c2_workflow_models"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    model_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="1.0.0",
    )
    project_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    definition: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Future review/approval metadata fields
    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "model_id",
            "version",
            name="uq_c2_model_project_model_version",
        ),
    )
