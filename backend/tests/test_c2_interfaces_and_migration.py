"""Tests for C2 shared integration interfaces and Alembic migration metadata."""

import importlib
import importlib.util
from pathlib import Path
from sqlalchemy import create_engine, inspect
from app.components.c2_state_aware_workflow.interfaces.shared import (
    AgentExecutionInterface,
    EvidenceIngestionInterface,
    FixtureResetInterface,
    StateObservationInterface,
    UnifiedReportExportInterface,
    WorkflowInputNormalizationInterface,
)
from app.database import Base


class TestSharedIntegrationProtocols:
    """Verifies that shared integration protocols are properly defined and runtime-checkable."""

    def test_interfaces_are_runtime_checkable(self):
        class DummyNormalizer:
            def normalize_workflow_input(self, raw_input):
                return None

        assert isinstance(DummyNormalizer(), WorkflowInputNormalizationInterface)

        class DummyReset:
            def reset_fixture(self, fixture):
                return True

        assert isinstance(DummyReset(), FixtureResetInterface)

        class DummyRunner:
            def execute_workflow_task(
                self, task, fixture_id, seed, timeout_seconds=60.0
            ):
                return "run-123"

        assert isinstance(DummyRunner(), AgentExecutionInterface)

        class DummyObserver:
            def capture_entity_observation(
                self, project_id, entity_name, entity_id, fields
            ):
                return {}

            def compute_state_diff(self, before_state, after_state):
                return {}

        assert isinstance(DummyObserver(), StateObservationInterface)

        class DummyIngestion:
            def ingest_runtime_event(self, event):
                pass

            def get_execution_evidence(self, run_id):
                return None

        assert isinstance(DummyIngestion(), EvidenceIngestionInterface)

        class DummyExporter:
            def export_evaluation_result(self, result):
                return {}

        assert isinstance(DummyExporter(), UnifiedReportExportInterface)


class TestAlembicMigrationDefinitions:
    """Verifies the Alembic migration script definitions and schema creation."""

    def test_migration_module_exports(self):
        migration_file = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "001_c2_create_workflow_models.py"
        )
        assert migration_file.exists()
        spec = importlib.util.spec_from_file_location(
            "migration_001", str(migration_file)
        )
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "c2_001_initial"
        assert mod.down_revision is None
        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")

    def test_schema_reflects_c2_workflow_models(self):
        test_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "c2_workflow_models" in tables

        columns = {
            col["name"]: col for col in inspector.get_columns("c2_workflow_models")
        }
        assert "id" in columns
        assert "model_id" in columns
        assert "version" in columns
        assert "schema_version" in columns
        assert "project_id" in columns
        assert "domain" in columns
        assert "name" in columns
        assert "definition" in columns
        assert "content_hash" in columns
        assert "lifecycle_status" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
        assert "review_notes" in columns
        assert "approved_by" in columns

        Base.metadata.drop_all(bind=test_engine)
