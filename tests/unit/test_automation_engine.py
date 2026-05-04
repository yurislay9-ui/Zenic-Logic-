"""
TITAN OMNISCALE X - AutomationEngine Tests

Tests for the workflow automation engine:
  - Workflow CRUD: create, list, get, toggle, delete
  - Workflow execution: sync and async execution paths
  - Trigger inference: schedule, event, webhook patterns
  - Action inference: email, report, notification, etc.
  - Stats and execution history
"""

import os
import time
import sqlite3
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

from src.core.automation_engine import (
    AutomationEngine,
    Workflow,
    WorkflowExecution,
    Trigger,
    Action,
    TriggerType,
    ActionType,
)


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Redirect the automation DB to a temp directory."""
    db_dir = str(tmp_path / "db")
    db_path = os.path.join(db_dir, "automation.sqlite")
    projects_dir = str(tmp_path / "projects")
    os.makedirs(db_dir, exist_ok=True)

    monkeypatch.setattr("src.core.automation_parts.types.DB_DIR", db_dir)
    monkeypatch.setattr("src.core.automation_parts.types.DB_PATH", db_path)
    monkeypatch.setattr("src.core.automation_parts.types.PROJECTS_DIR", projects_dir)
    # Also patch the facade for backward compatibility
    monkeypatch.setattr("src.core.automation_engine.DB_DIR", db_dir)
    monkeypatch.setattr("src.core.automation_engine.DB_PATH", db_path)
    monkeypatch.setattr("src.core.automation_engine.PROJECTS_DIR", projects_dir)

    return db_path


@pytest.fixture
def engine(temp_db):
    """Create an AutomationEngine with a temp DB."""
    with patch("src.core.automation_engine.AutomationEngine._init_db") as mock_init, \
         patch("src.core.automation_engine.AutomationEngine._load_workflows") as mock_load:
        eng = AutomationEngine(
            thinking_engine=None,
            template_engine=None,
            executor_registry=None,
        )

    # Actually init the DB now with the temp path
    eng._init_db()
    eng._workflows = {}
    return eng


@pytest.fixture
def sample_workflow(engine):
    """Create a sample workflow via the engine."""
    return engine.create_workflow(
        name="Daily Sales Report",
        description="Send daily sales report by email",
        trigger=Trigger(
            type=TriggerType.SCHEDULE,
            config={"interval": "daily", "hour": 9, "minute": 0},
        ),
        actions=[
            Action(type=ActionType.GENERATE_REPORT, config={"template": "sales", "format": "html"}),
            Action(type=ActionType.SEND_EMAIL, config={"to": "admin@co.com", "subject": "Sales"}),
        ],
    )


# ============================================================
#  WORKFLOW DATA MODEL TESTS
# ============================================================

class TestWorkflowDataModel:
    """Tests for Workflow, Trigger, Action dataclasses."""

    def test_trigger_defaults(self):
        trigger = Trigger()
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config == {}

    def test_action_defaults(self):
        action = Action()
        assert action.type == ActionType.SEND_NOTIFICATION
        assert action.config == {}

    def test_workflow_defaults(self):
        wf = Workflow()
        assert wf.id == ""
        assert wf.name == ""
        assert wf.enabled is True
        assert wf.status == "active"
        assert wf.run_count == 0

    def test_trigger_type_enum(self):
        assert TriggerType.SCHEDULE.value == "schedule"
        assert TriggerType.EVENT.value == "event"
        assert TriggerType.WEBHOOK.value == "webhook"
        assert TriggerType.FILE_CHANGE.value == "file_change"
        assert TriggerType.DATA_CHANGE.value == "data_change"

    def test_action_type_enum(self):
        assert ActionType.SEND_EMAIL.value == "send_email"
        assert ActionType.RUN_SCRIPT.value == "run_script"
        assert ActionType.GENERATE_REPORT.value == "generate_report"
        assert ActionType.DATA_SYNC.value == "data_sync"


# ============================================================
#  WORKFLOW CREATION TESTS
# ============================================================

class TestWorkflowCreation:
    """Tests for creating workflows."""

    def test_create_workflow_basic(self, engine):
        """create_workflow should return a Workflow with an ID."""
        wf = engine.create_workflow(name="Test Workflow")
        assert wf.id != ""
        assert wf.name == "Test Workflow"
        assert wf.created_at > 0
        assert wf.enabled is True

    def test_create_workflow_with_trigger_and_actions(self, engine):
        """create_workflow should preserve trigger and actions."""
        trigger = Trigger(type=TriggerType.EVENT, config={"event_type": "stock_low"})
        actions = [Action(type=ActionType.SEND_NOTIFICATION, config={"message": "Low stock"})]

        wf = engine.create_workflow(
            name="Stock Alert",
            trigger=trigger,
            actions=actions,
        )
        assert wf.trigger.type == TriggerType.EVENT
        assert len(wf.actions) == 1
        assert wf.actions[0].type == ActionType.SEND_NOTIFICATION

    def test_create_workflow_stored_in_engine(self, engine):
        """Created workflow should be stored in the engine's dict."""
        wf = engine.create_workflow(name="Stored Test")
        assert wf.id in engine._workflows

    def test_create_from_description_email(self, engine):
        """create_from_description should detect email patterns."""
        wf = engine.create_from_description("Enviar reporte semanal por email cada lunes")
        assert wf.name != ""
        assert len(wf.actions) > 0
        # Should detect email action
        action_types = [a.type for a in wf.actions]
        assert ActionType.SEND_EMAIL in action_types

    def test_create_from_description_schedule(self, engine):
        """create_from_description should detect schedule keywords."""
        wf = engine.create_from_description("Backup diario de la base de datos")
        assert wf.trigger.type == TriggerType.SCHEDULE

    def test_create_from_description_event(self, engine):
        """create_from_description should detect event keywords."""
        wf = engine.create_from_description("Cuando se agote el stock, notificar")
        assert wf.trigger.type == TriggerType.EVENT

    def test_create_from_description_webhook(self, engine):
        """create_from_description should detect webhook keywords."""
        wf = engine.create_from_description("Recibir notificaciones via webhook endpoint")
        assert wf.trigger.type == TriggerType.WEBHOOK


# ============================================================
#  WORKFLOW EXECUTION TESTS
# ============================================================

class TestWorkflowExecution:
    """Tests for workflow execution."""

    def test_execute_nonexistent_workflow(self, engine):
        """Executing a nonexistent workflow should return error."""
        result = engine._execute_workflow_sync("nonexistent_id")
        assert result.status == "failed"
        assert "not found" in result.error.lower()

    def test_execute_disabled_workflow(self, engine):
        """Executing a disabled workflow should return error."""
        wf = engine.create_workflow(name="Disabled Test")
        wf.enabled = False

        result = engine._execute_workflow_sync(wf.id)
        assert result.status == "failed"
        assert "disabled" in result.error.lower()

    def test_execute_workflow_sync_success(self, engine, sample_workflow):
        """Sync execution with no executor_registry should use legacy stubs."""
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.status in ("success", "partial")
        assert result.started_at > 0
        assert result.finished_at >= result.started_at

    def test_execute_updates_run_count(self, engine, sample_workflow):
        """Execution should increment the workflow's run_count."""
        initial_count = sample_workflow.run_count
        engine._execute_workflow_sync(sample_workflow.id)
        assert sample_workflow.run_count == initial_count + 1

    def test_execute_with_executor_registry(self, engine, sample_workflow):
        """When executor_registry is available, it should be used."""
        mock_registry = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.duration_ms = 100.0
        mock_result.error = ""
        mock_registry.execute_action = MagicMock(return_value=mock_result)

        engine._executor_registry = mock_registry
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.actions_executed > 0

    def test_execute_with_executor_failure(self, engine, sample_workflow):
        """When executor fails, action should be counted as failed."""
        mock_registry = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.duration_ms = 50.0
        mock_result.error = "Connection refused"
        mock_registry.execute_action = MagicMock(return_value=mock_result)

        engine._executor_registry = mock_registry
        result = engine._execute_workflow_sync(sample_workflow.id)
        assert result.actions_failed > 0

    def test_execute_logs_execution(self, engine, sample_workflow, temp_db):
        """Execution should be logged to the execution_log table."""
        engine._execute_workflow_sync(sample_workflow.id)
        history = engine.get_execution_history(sample_workflow.id)
        assert len(history) >= 1


# ============================================================
#  WORKFLOW MANAGEMENT TESTS
# ============================================================

class TestWorkflowManagement:
    """Tests for listing, toggling, and deleting workflows."""

    def test_list_workflows(self, engine, sample_workflow):
        """list_workflows should return all workflows."""
        workflows = engine.list_workflows()
        assert len(workflows) >= 1
        assert any(w["name"] == "Daily Sales Report" for w in workflows)

    def test_get_workflow(self, engine, sample_workflow):
        """get_workflow should return the workflow by ID."""
        result = engine.get_workflow(sample_workflow.id)
        assert result is not None
        assert result["name"] == "Daily Sales Report"

    def test_get_nonexistent_workflow(self, engine):
        """get_workflow with invalid ID should return None."""
        result = engine.get_workflow("nonexistent")
        assert result is None

    def test_toggle_workflow(self, engine, sample_workflow):
        """toggle_workflow should switch enabled/disabled."""
        assert sample_workflow.enabled is True
        new_state = engine.toggle_workflow(sample_workflow.id)
        assert new_state is False
        assert sample_workflow.status == "paused"

        new_state = engine.toggle_workflow(sample_workflow.id)
        assert new_state is True
        assert sample_workflow.status == "active"

    def test_toggle_nonexistent_workflow(self, engine):
        """toggle_workflow with invalid ID should return False."""
        result = engine.toggle_workflow("nonexistent")
        assert result is False

    def test_delete_workflow(self, engine, sample_workflow):
        """delete_workflow should remove the workflow."""
        wf_id = sample_workflow.id
        result = engine.delete_workflow(wf_id)
        assert result is True
        assert wf_id not in engine._workflows

    def test_delete_nonexistent_workflow(self, engine):
        """delete_workflow with invalid ID should return False."""
        result = engine.delete_workflow("nonexistent")
        assert result is False


# ============================================================
#  TRIGGER & ACTION INFERENCE TESTS
# ============================================================

class TestTriggerActionInference:
    """Tests for trigger and action inference from descriptions."""

    def test_infer_schedule_daily(self, engine):
        """Daily keywords should produce daily schedule trigger."""
        trigger = engine._infer_trigger("Enviar reporte diario cada dia")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "daily"

    def test_infer_schedule_weekly(self, engine):
        """Weekly keywords should produce weekly schedule trigger."""
        trigger = engine._infer_trigger("Enviar reporte semanal cada lunes")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "weekly"

    def test_infer_schedule_monthly(self, engine):
        """Monthly keywords should produce monthly schedule trigger."""
        trigger = engine._infer_trigger("Enviar reporte mensual")
        assert trigger.type == TriggerType.SCHEDULE
        assert trigger.config["interval"] == "monthly"

    def test_infer_event(self, engine):
        """Event keywords should produce event trigger."""
        trigger = engine._infer_trigger("Cuando el stock baje de 5 unidades")
        assert trigger.type == TriggerType.EVENT

    def test_infer_webhook(self, engine):
        """Webhook keywords should produce webhook trigger."""
        trigger = engine._infer_trigger("Recibir datos via webhook callback")
        assert trigger.type == TriggerType.WEBHOOK

    def test_infer_actions_email(self, engine):
        """Email keywords should produce email action."""
        actions = engine._infer_actions("Enviar correo con el reporte")
        assert any(a.type == ActionType.SEND_EMAIL for a in actions)

    def test_infer_actions_report(self, engine):
        """Report keywords should produce report action."""
        actions = engine._infer_actions("Generar reporte de ventas")
        assert any(a.type == ActionType.GENERATE_REPORT for a in actions)

    def test_infer_actions_backup(self, engine):
        """Backup keywords should produce database action."""
        actions = engine._infer_actions("Backup de la base de datos")
        assert any(a.type == ActionType.DATABASE_OPERATION for a in actions)

    def test_infer_actions_notification(self, engine):
        """Notification keywords should produce notification action."""
        actions = engine._infer_actions("Notificar cuando haya error")
        assert any(a.type == ActionType.SEND_NOTIFICATION for a in actions)

    def test_infer_actions_default_notification(self, engine):
        """No matching keywords should produce a default notification."""
        actions = engine._infer_actions("Do something random xyz")
        assert len(actions) >= 1
        assert any(a.type == ActionType.SEND_NOTIFICATION for a in actions)

    def test_infer_actions_data_sync(self, engine):
        """Sync keywords should produce data_sync action."""
        actions = engine._infer_actions("Sincronizar datos del CRM")
        assert any(a.type == ActionType.DATA_SYNC for a in actions)

    def test_extract_name(self, engine):
        """_extract_name should produce a short name from description."""
        name = engine._extract_name("Enviar reporte semanal por email")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_extract_name_empty_description(self, engine):
        """_extract_name with empty description should return 'automation'."""
        name = engine._extract_name("")
        assert name == "automation"


# ============================================================
#  STATS TESTS
# ============================================================

class TestAutomationStats:
    """Tests for stats reporting."""

    def test_stats_initial(self, engine):
        """Initial stats should show zero workflows."""
        stats = engine.stats
        assert stats["total_workflows"] == 0
        assert stats["active_workflows"] == 0

    def test_stats_after_creation(self, engine, sample_workflow):
        """Stats should reflect created workflows."""
        stats = engine.stats
        assert stats["total_workflows"] >= 1
        assert stats["active_workflows"] >= 1

    def test_stats_after_execution(self, engine, sample_workflow):
        """Stats should reflect executions."""
        engine._execute_workflow_sync(sample_workflow.id)
        stats = engine.stats
        assert stats["total_executions"] >= 1
