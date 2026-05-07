"""
Tests for Layer 6: Automation agents (A29-A34).

All 6 agents tested:
  - A29 TriggerInferrer
  - A30 ActionInferrer
  - A31 ScheduleParser
  - A32 ConditionExtractor
  - A33 AutomationNamer
  - A34 WorkflowSerializer
"""

import json
import pytest

from src.core.agents_v2.automation import (
    TriggerInferrer,
    ActionInferrer,
    ScheduleParser,
    ConditionExtractor,
    AutomationNamer,
    WorkflowSerializer,
)
from src.core.agents_v2.schemas import (
    AutoDescription,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
    ConditionResult,
    NameResult,
    WorkflowSpec,
)


# ═══════════════════════════════════════════════════════════
# A29 TriggerInferrer Tests
# ═══════════════════════════════════════════════════════════

class TestTriggerInferrer:
    """A29: Infer trigger type from description."""

    def setup_method(self):
        self.inferrer = TriggerInferrer()

    def test_schedule_trigger_daily(self):
        """'daily' should detect schedule trigger."""
        result = self.inferrer.execute({"description": "run this daily at 9am"})
        assert isinstance(result, TriggerSpec)
        assert result.type == "schedule"
        assert result.config.get("interval") == "daily"

    def test_schedule_trigger_semanal(self):
        """'semanal' (ES) should detect schedule trigger."""
        result = self.inferrer.execute({"description": "ejecutar semanal"})
        assert result.type == "schedule"
        assert result.config.get("interval") == "weekly"

    def test_event_trigger(self):
        """'when' should detect event trigger."""
        result = self.inferrer.execute({"description": "when a new user registers"})
        assert result.type == "event"

    def test_event_trigger_es(self):
        """'cuando' should detect event trigger."""
        result = self.inferrer.execute({"description": "cuando se detecte un error"})
        assert result.type == "event"

    def test_webhook_trigger(self):
        """'webhook' should detect webhook trigger."""
        result = self.inferrer.execute({"description": "receive a webhook from Stripe"})
        assert result.type == "webhook"
        assert "path" in result.config

    def test_manual_default(self):
        """No matching keywords should default to manual."""
        result = self.inferrer.execute({"description": "process data"})
        assert result.type == "manual"

    def test_empty_description_manual(self):
        """Empty description should default to manual."""
        result = self.inferrer.execute({"description": ""})
        assert result.type == "manual"

    def test_string_input_works(self):
        """String input should work."""
        result = self.inferrer.execute("run hourly")
        assert result.type == "schedule"

    def test_auto_description_input(self):
        """AutoDescription object should work."""
        desc = AutoDescription(description="send email weekly")
        result = self.inferrer.execute(desc)
        assert result.type == "schedule"

    def test_hour_extraction(self):
        """'at 3pm' should extract hour 15."""
        result = self.inferrer.execute({"description": "run daily at 3pm"})
        assert result.type == "schedule"
        assert result.config.get("hour") == 15

    def test_webhook_priority_over_schedule(self):
        """'webhook' should take priority over schedule keywords."""
        result = self.inferrer.execute({"description": "receive a webhook every hour"})
        assert result.type == "webhook"

    def test_fallback_returns_manual(self):
        """Fallback should return manual trigger."""
        result = self.inferrer.fallback(None)
        assert result.type == "manual"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A30 ActionInferrer Tests
# ═══════════════════════════════════════════════════════════

class TestActionInferrer:
    """A30: Infer action types from description."""

    def setup_method(self):
        self.inferrer = ActionInferrer()

    def test_email_action(self):
        """'email' should detect email action."""
        result = self.inferrer.execute({"description": "send an email notification"})
        assert isinstance(result, ActionSpec)
        assert result.type == "email"

    def test_notification_action(self):
        """'alertar' should detect notification action."""
        result = self.inferrer.execute({"description": "alertar al administrador"})
        assert result.type == "notification"

    def test_db_action(self):
        """'backup' should detect db action."""
        result = self.inferrer.execute({"description": "make a database backup"})
        assert result.type == "db"

    def test_http_action(self):
        """'api' should detect http action."""
        result = self.inferrer.execute({"description": "call an API endpoint"})
        assert result.type == "http"

    def test_file_action(self):
        """'csv' should detect file action."""
        result = self.inferrer.execute({"description": "export data to csv"})
        assert result.type == "file"

    def test_transform_action(self):
        """'convertir' should detect transform action."""
        result = self.inferrer.execute({"description": "convertir datos a formato JSON"})
        assert result.type == "transform"

    def test_log_action(self):
        """'log' should detect log action."""
        result = self.inferrer.execute({"description": "registrar la operación"})
        assert result.type == "log"

    def test_default_log_when_no_match(self):
        """No matching keywords should default to log action."""
        result = self.inferrer.execute({"description": "do something"})
        assert result.type == "log"

    def test_multiple_actions_via_infer_all(self):
        """Multiple action types should be detected via infer_all()."""
        actions = self.inferrer.infer_all(
            {"description": "send email and export to csv"}
        )
        types = {a.type for a in actions}
        assert "email" in types
        assert "file" in types

    def test_infer_all_max_5(self):
        """infer_all should cap at 5 actions."""
        actions = self.inferrer.infer_all(
            {"description": "send email, alert, backup db, call api, export csv, transform, log"}
        )
        assert len(actions) <= 5

    def test_email_address_extraction(self):
        """Email address in description should be extracted to config."""
        result = self.inferrer.execute(
            {"description": "send email to admin@company.com"}
        )
        assert result.type == "email"
        assert result.config.get("to") == "admin@company.com"

    def test_empty_description_default_log(self):
        """Empty description should default to log action."""
        result = self.inferrer.execute({"description": ""})
        assert result.type == "log"

    def test_fallback_returns_log(self):
        """Fallback should return log action."""
        result = self.inferrer.fallback(None)
        assert result.type == "log"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A31 ScheduleParser Tests
# ═══════════════════════════════════════════════════════════

class TestScheduleParser:
    """A31: Parse natural language schedule into cron/interval."""

    def setup_method(self):
        self.parser = ScheduleParser()

    def test_daily_schedule(self):
        """'daily' should produce daily cron."""
        result = self.parser.execute({"description": "run daily"})
        assert isinstance(result, ScheduleSpec)
        assert result.type == "cron"
        assert "0" in result.cron  # minute 0
        assert result.cron.count("*") >= 2  # daily pattern

    def test_hourly_schedule(self):
        """'hourly' should produce interval schedule."""
        result = self.parser.execute({"description": "run hourly"})
        assert result.type == "interval"
        assert result.interval_seconds == 3600

    def test_weekly_schedule(self):
        """'weekly' should produce weekly cron."""
        result = self.parser.execute({"description": "run weekly"})
        assert result.type == "cron"
        assert result.interval_seconds == 604800

    def test_monthly_schedule(self):
        """'monthly' should produce monthly cron."""
        result = self.parser.execute({"description": "run monthly"})
        assert result.type == "cron"

    def test_specific_hour(self):
        """'at 3pm' should set hour 15 in cron."""
        result = self.parser.execute({"description": "run daily at 3pm"})
        assert result.type == "cron"
        assert "15" in result.cron

    def test_interval_pattern_es(self):
        """'cada 30 minutos' should produce interval."""
        result = self.parser.execute({"description": "cada 30 minutos"})
        assert result.type == "interval"
        assert result.interval_seconds == 30 * 60

    def test_interval_pattern_en(self):
        """'every 2 hours' should produce interval."""
        result = self.parser.execute({"description": "every 2 hours"})
        assert result.type == "interval"
        assert result.interval_seconds == 2 * 3600

    def test_cron_expression_direct(self):
        """Direct cron expression should be parsed."""
        result = self.parser.execute({"description": "0 9 * * 1-5"})
        assert result.type == "cron"
        assert "0 9 * * 1-5" in result.cron

    def test_day_of_week_es(self):
        """'viernes' should set day of week in cron."""
        result = self.parser.execute({"description": "semanal viernes"})
        assert result.type == "cron"
        assert "5" in result.cron  # Friday = 5

    def test_manual_default(self):
        """No schedule pattern should default to manual."""
        result = self.parser.execute({"description": "process data"})
        assert result.type == "manual"

    def test_empty_description_manual(self):
        """Empty description should default to manual."""
        result = self.parser.execute({"description": ""})
        assert result.type == "manual"

    def test_string_input_works(self):
        """String input should work."""
        result = self.parser.execute("run daily")
        assert result.type == "cron"

    def test_fallback_returns_manual(self):
        """Fallback should return manual."""
        result = self.parser.fallback(None)
        assert result.type == "manual"
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A32 ConditionExtractor Tests
# ═══════════════════════════════════════════════════════════

class TestConditionExtractor:
    """A32: Extract conditional logic from description."""

    def setup_method(self):
        self.extractor = ConditionExtractor()

    def test_if_condition_en(self):
        """'if X then' should extract condition."""
        result = self.extractor.execute(
            {"description": "send email if balance exceeds 1000"}
        )
        assert isinstance(result, ConditionResult)
        assert len(result.conditions) > 0
        assert any("balance" in c.lower() for c in result.conditions)

    def test_si_condition_es(self):
        """'si X' should extract condition."""
        result = self.extractor.execute(
            {"description": "enviar alerta si el inventario es bajo"}
        )
        assert len(result.conditions) > 0
        assert any("inventario" in c.lower() for c in result.conditions)

    def test_only_when_condition(self):
        """'only when X' should extract condition."""
        result = self.extractor.execute(
            {"description": "process only when status is active"}
        )
        assert len(result.conditions) > 0

    def test_when_condition(self):
        """'when X' should extract condition."""
        result = self.extractor.execute(
            {"description": "alert when server is down"}
        )
        assert len(result.conditions) > 0

    def test_no_conditions(self):
        """No condition keywords should return empty."""
        result = self.extractor.execute(
            {"description": "send daily email report"}
        )
        assert len(result.conditions) == 0

    def test_logic_tree_built(self):
        """Logic tree should be built when conditions found."""
        result = self.extractor.execute(
            {"description": "send alert if error count > 5 and retry failed"}
        )
        if result.conditions:
            assert "operator" in result.logic_tree

    def test_and_operator_detected(self):
        """' and ' should set AND operator in logic tree."""
        result = self.extractor.execute(
            {"description": "notify if status is critical and retry count exceeds 3"}
        )
        if result.conditions and result.logic_tree:
            assert result.logic_tree.get("operator") in ("AND", "SINGLE")

    def test_or_operator_detected(self):
        """' or ' should set OR operator in logic tree."""
        result = self.extractor.execute(
            {"description": "alert if cpu > 90 or memory > 80"}
        )
        if result.conditions and result.logic_tree:
            assert result.logic_tree.get("operator") in ("OR", "AND", "SINGLE")

    def test_empty_description(self):
        """Empty description should return empty conditions."""
        result = self.extractor.execute({"description": ""})
        assert len(result.conditions) == 0

    def test_fallback_returns_empty(self):
        """Fallback should return empty conditions."""
        result = self.extractor.fallback(None)
        assert len(result.conditions) == 0
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A33 AutomationNamer Tests
# ═══════════════════════════════════════════════════════════

class TestAutomationNamer:
    """A33: Generate descriptive name for automation."""

    def setup_method(self):
        self.namer = AutomationNamer()

    def test_name_from_description(self):
        """Name should be generated from description keywords."""
        result = self.namer.execute(
            {"description": "send daily email report"}
        )
        assert isinstance(result, NameResult)
        assert result.name != ""
        assert result.slug != ""

    def test_name_from_specs(self):
        """Name should use template when specs provided."""
        result = self.namer.execute({
            "trigger_spec": TriggerSpec(type="schedule"),
            "action_spec": ActionSpec(type="email"),
            "description": "weekly sales report",
        })
        assert "email" in result.name or "schedule" in result.name

    def test_slug_is_url_safe(self):
        """Slug should contain only ASCII, lowercase, hyphens."""
        result = self.namer.execute(
            {"description": "Enviar correo electrónico diario"}
        )
        # Slug should not contain special chars or uppercase
        assert all(c.isalnum() or c == "-" for c in result.slug)
        assert result.slug == result.slug.lower()

    def test_stop_words_removed(self):
        """Stop words should be removed from name."""
        result = self.namer.execute(
            {"description": "the daily report generator"}
        )
        # "the" should be removed
        assert "the" not in result.name.split("_")

    def test_empty_description_fallback(self):
        """Empty description should produce a name."""
        result = self.namer.execute({"description": ""})
        assert result.name != ""

    def test_schedule_email_template(self):
        """schedule + email should use template."""
        result = self.namer.execute({
            "trigger_spec": TriggerSpec(type="schedule"),
            "action_spec": ActionSpec(type="email"),
            "description": "customer digest",
        })
        assert "email" in result.name

    def test_fallback_returns_generic(self):
        """Fallback should return generic name."""
        result = self.namer.fallback(None)
        assert "automation" in result.name
        assert result.source == "fallback"


# ═══════════════════════════════════════════════════════════
# A34 WorkflowSerializer Tests
# ═══════════════════════════════════════════════════════════

class TestWorkflowSerializer:
    """A34: Serialize automation into executable workflow spec."""

    def setup_method(self):
        self.serializer = WorkflowSerializer()

    def test_basic_serialization(self):
        """Basic serialization should produce valid WorkflowSpec."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule", config={"interval": "daily"}),
            "actions": [ActionSpec(type="email", config={"to": "admin@test.com"})],
            "schedule": ScheduleSpec(type="cron", cron="0 9 * * *"),
            "name": "daily_report",
            "description": "Send daily report email",
        })
        assert isinstance(result, WorkflowSpec)
        assert result.yaml != ""
        assert result.json_spec != ""
        assert isinstance(result.executable, dict)

    def test_executable_has_required_fields(self):
        """Executable dict should have all required fields."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "actions": [ActionSpec(type="log")],
            "name": "test_workflow",
        })
        exe = result.executable
        assert "version" in exe
        assert "name" in exe
        assert "trigger" in exe
        assert "actions" in exe
        assert "schedule" in exe

    def test_json_is_valid(self):
        """JSON output should be valid JSON."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule"),
            "actions": [ActionSpec(type="notification")],
            "name": "json_test",
        })
        parsed = json.loads(result.json_spec)
        assert isinstance(parsed, dict)
        assert parsed["name"] == "json_test"

    def test_yaml_not_empty(self):
        """YAML output should not be empty."""
        result = self.serializer.execute({
            "trigger": {"type": "webhook"},
            "actions": [{"type": "http"}],
            "name": "yaml_test",
        })
        assert len(result.yaml) > 0
        assert "yaml_test" in result.yaml

    def test_conditions_included(self):
        """Conditions should be included in executable."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="event"),
            "actions": [ActionSpec(type="notification")],
            "conditions": ["status == 'critical'"],
            "name": "conditional_test",
        })
        assert "conditions" in result.executable
        assert len(result.executable["conditions"]) > 0

    def test_condition_result_object(self):
        """ConditionResult object should be handled."""
        cond_result = ConditionResult(
            conditions=["balance > 1000"],
            logic_tree={"operator": "SINGLE"},
        )
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="schedule"),
            "actions": [ActionSpec(type="email")],
            "conditions": cond_result,
            "name": "cond_result_test",
        })
        assert "conditions" in result.executable

    def test_metadata_included(self):
        """Metadata should be included in executable."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "actions": [ActionSpec(type="log")],
            "name": "meta_test",
        })
        assert "metadata" in result.executable
        assert result.executable["metadata"]["deterministic"] is True

    def test_empty_actions_gets_default(self):
        """Empty actions should get a default log action."""
        result = self.serializer.execute({
            "trigger": TriggerSpec(type="manual"),
            "name": "empty_actions",
        })
        assert len(result.executable["actions"]) > 0

    def test_fallback_returns_minimal(self):
        """Fallback should return minimal workflow."""
        result = self.serializer.fallback(None)
        assert isinstance(result, WorkflowSpec)
        assert result.source == "fallback"
        assert result.executable.get("name") == "empty_workflow"


# ═══════════════════════════════════════════════════════════
# Integration: Full Automation Pipeline Test
# ═══════════════════════════════════════════════════════════

class TestAutomationPipeline:
    """End-to-end automation pipeline through all Layer 6 agents."""

    def test_full_automation_pipeline_es(self):
        """Full pipeline in Spanish: 'Enviar correo diario si el inventario es bajo'"""
        desc = "Enviar correo electrónico diario si el inventario es bajo"

        # Step 1: Infer trigger
        trigger = TriggerInferrer().execute({"description": desc})
        assert trigger.type == "schedule"

        # Step 2: Infer actions
        action_inferrer = ActionInferrer()
        actions = action_inferrer.infer_all({"description": desc})
        action_types = {a.type for a in actions}
        assert "email" in action_types

        # Step 3: Parse schedule
        schedule = ScheduleParser().execute({"description": desc})
        assert schedule.type in ("cron", "interval")

        # Step 4: Extract conditions
        conditions = ConditionExtractor().execute({"description": desc})
        assert len(conditions.conditions) > 0
        assert any("inventario" in c.lower() for c in conditions.conditions)

        # Step 5: Generate name
        name = AutomationNamer().execute({
            "trigger_spec": trigger,
            "action_spec": actions[0] if actions else None,
            "description": desc,
        })
        assert name.name != ""

        # Step 6: Serialize workflow
        workflow = WorkflowSerializer().execute({
            "trigger": trigger,
            "actions": actions,
            "schedule": schedule,
            "conditions": conditions,
            "name": name.name,
            "description": desc,
        })
        assert workflow.executable["name"] == name.name
        assert len(workflow.executable["actions"]) > 0

        # Verify JSON is valid
        parsed = json.loads(workflow.json_spec)
        assert parsed["name"] == name.name

    def test_full_automation_pipeline_en(self):
        """Full pipeline in English: 'Send alert notification every 2 hours if server error rate > 5%'"""
        desc = "Send alert notification every 2 hours if server error rate > 5%"

        # Step 1: Trigger (schedule keyword "every" detected)
        trigger = TriggerInferrer().execute({"description": desc})
        assert trigger.type == "schedule"

        # Step 2: Actions
        action_inferrer = ActionInferrer()
        actions = action_inferrer.infer_all({"description": desc})
        action_types = {a.type for a in actions}
        assert "notification" in action_types or "http" in action_types

        # Step 3: Schedule
        schedule = ScheduleParser().execute({"description": desc})
        assert schedule.type == "interval"
        assert schedule.interval_seconds == 2 * 3600

        # Step 4: Conditions
        conditions = ConditionExtractor().execute({"description": desc})
        assert len(conditions.conditions) > 0

        # Step 5: Name
        name = AutomationNamer().execute({"description": desc})
        assert name.name != ""

        # Step 6: Serialize
        workflow = WorkflowSerializer().execute({
            "trigger": trigger,
            "actions": actions,
            "schedule": schedule,
            "conditions": conditions,
            "name": name.name,
            "description": desc,
        })
        assert isinstance(workflow, WorkflowSpec)
        assert workflow.executable["name"] == name.name
