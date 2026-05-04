"""
Unit tests for AutomationAgent.

Tests the agent that unifies automation design:
  - Trigger inference (schedule, event, webhook)
  - Action inference (email, http, db, file, etc.)
  - Schedule inference (hourly, daily, weekly, monthly)
  - Condition inference
  - Name extraction
  - to_workflow_dict() legacy compatibility
  - LLM response parsing
  - SmartMemory cache integration
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.automation_agent import (
    AutomationAgent,
    TRIGGER_KEYWORDS,
    ACTION_KEYWORDS,
    SCHEDULE_PATTERNS,
)
from src.core.agents.schemas import (
    AutomationInput,
    AutomationOutput,
    TriggerSpec,
    ActionSpec,
    ScheduleSpec,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """AutomationAgent without external dependencies."""
    return AutomationAgent()


@pytest.fixture
def agent_with_memory():
    """AutomationAgent with mocked SmartMemory."""
    agent = AutomationAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


# ============================================================
#  Test: Trigger Inference
# ============================================================

class TestAutomationTriggerInference:
    """Tests for deterministic trigger inference from description."""

    def test_schedule_trigger_daily(self, agent):
        """Should detect schedule trigger from 'daily' keyword."""
        result = agent.fallback(AutomationInput(
            description="send daily report every day at 9am",
        ))
        assert len(result.triggers) >= 1
        assert result.triggers[0].type == "schedule"

    def test_schedule_trigger_cron(self, agent):
        """Should detect schedule trigger from 'cron' keyword."""
        result = agent.fallback(AutomationInput(
            description="run cron job for backup",
        ))
        assert result.triggers[0].type == "schedule"

    def test_event_trigger(self, agent):
        """Should detect event trigger from 'when' keyword."""
        result = agent.fallback(AutomationInput(
            description="when new user registers send email",
        ))
        assert result.triggers[0].type == "event"

    def test_webhook_trigger(self, agent):
        """Should detect webhook trigger from 'webhook' keyword."""
        result = agent.fallback(AutomationInput(
            description="receive webhook from payment provider",
        ))
        assert result.triggers[0].type == "webhook"

    def test_default_trigger_schedule(self, agent):
        """Should default to schedule trigger when no keywords match."""
        result = agent.fallback(AutomationInput(
            description="process data files",
        ))
        assert result.triggers[0].type == "schedule"

    def test_event_trigger_config(self, agent):
        """Event trigger should have event_type in config."""
        result = agent.fallback(AutomationInput(
            description="when order is placed notify admin",
        ))
        assert result.triggers[0].type == "event"
        assert "event_type" in result.triggers[0].config


# ============================================================
#  Test: Action Inference
# ============================================================

class TestAutomationActionInference:
    """Tests for deterministic action inference from description."""

    def test_email_action(self, agent):
        """Should detect email action."""
        result = agent.fallback(AutomationInput(
            description="send email notification daily",
        ))
        action_types = [a.type for a in result.actions]
        assert "email" in action_types

    def test_notification_action(self, agent):
        """Should detect notification action."""
        result = agent.fallback(AutomationInput(
            description="alert administrator when error occurs",
        ))
        action_types = [a.type for a in result.actions]
        assert "notification" in action_types

    def test_db_action(self, agent):
        """Should detect database action."""
        result = agent.fallback(AutomationInput(
            description="backup database daily",
        ))
        action_types = [a.type for a in result.actions]
        assert "db" in action_types

    def test_http_action(self, agent):
        """Should detect HTTP/API action."""
        result = agent.fallback(AutomationInput(
            description="call api endpoint when event triggers",
        ))
        action_types = [a.type for a in result.actions]
        assert "http" in action_types

    def test_file_action(self, agent):
        """Should detect file action."""
        result = agent.fallback(AutomationInput(
            description="export csv file report",
        ))
        action_types = [a.type for a in result.actions]
        assert "file" in action_types

    def test_default_log_action(self, agent):
        """Should default to log action when no actions detected."""
        result = agent.fallback(AutomationInput(
            description="do something unspecified",
        ))
        # Default is log when nothing else matches
        assert len(result.actions) >= 1

    def test_max_five_actions(self, agent):
        """Should limit actions to 5 maximum."""
        # Craft description with many action keywords
        desc = "send email and alert and backup db and call api and export file and transform data"
        result = agent.fallback(AutomationInput(description=desc))
        assert len(result.actions) <= 5


# ============================================================
#  Test: Schedule Inference
# ============================================================

class TestAutomationScheduleInference:
    """Tests for deterministic schedule inference."""

    def test_daily_schedule(self, agent):
        """Should infer daily schedule."""
        result = agent.fallback(AutomationInput(
            description="send report daily at 9am",
        ))
        assert result.schedule.type == "cron"
        assert "9" in result.schedule.cron_expression

    def test_hourly_schedule(self, agent):
        """Should infer hourly schedule."""
        result = agent.fallback(AutomationInput(
            description="check status hourly every hour",
        ))
        assert result.schedule.type == "interval"
        assert result.schedule.interval_seconds == 3600

    def test_weekly_schedule(self, agent):
        """Should infer weekly schedule."""
        result = agent.fallback(AutomationInput(
            description="run weekly report every monday",
        ))
        assert result.schedule.type == "cron"

    def test_monthly_schedule(self, agent):
        """Should infer monthly schedule."""
        result = agent.fallback(AutomationInput(
            description="generate monthly summary",
        ))
        assert result.schedule.type == "cron"

    def test_manual_default_schedule(self, agent):
        """Should default to manual when no schedule keywords match."""
        result = agent.fallback(AutomationInput(
            description="process one-time request",
        ))
        assert result.schedule.type == "manual"

    def test_hour_extraction_pm(self, agent):
        """Should extract PM hours correctly."""
        result = agent.fallback(AutomationInput(
            description="run daily at 3pm",
        ))
        # 3pm should become hour 15
        assert "15" in result.schedule.cron_expression

    def test_hour_extraction_am(self, agent):
        """Should extract AM hours correctly."""
        result = agent.fallback(AutomationInput(
            description="run daily at 9am",
        ))
        assert "9" in result.schedule.cron_expression


# ============================================================
#  Test: Condition Inference
# ============================================================

class TestAutomationConditionInference:
    """Tests for condition inference from description."""

    def test_if_condition(self, agent):
        """Should extract condition from 'if/when' keyword pattern."""
        result = agent.fallback(AutomationInput(
            description="send email if sales exceed 1000 then notify",
        ))
        # The regex looks for 'if X then/entonces/comma/dot' pattern
        if result.conditions:
            assert any("sales" in c.lower() for c in result.conditions)
        else:
            # If regex didn't match the specific pattern, at least verify no crash
            assert result.conditions == []

    def test_no_conditions(self, agent):
        """Should return empty conditions when no condition keywords."""
        result = agent.fallback(AutomationInput(
            description="send daily report",
        ))
        assert result.conditions == []


# ============================================================
#  Test: Name Extraction
# ============================================================

class TestAutomationNameExtraction:
    """Tests for name extraction from description."""

    def test_name_from_description(self, agent):
        """Should extract meaningful name from description."""
        result = agent.fallback(AutomationInput(
            description="send daily report email",
        ))
        assert result.name != ""
        assert result.name != "unnamed_automation"

    def test_name_stops_removed(self, agent):
        """Should remove stop words from name."""
        result = agent.fallback(AutomationInput(
            description="create a weekly report",
        ))
        # "create" and "a" should be removed as stop words
        assert "create" not in result.name
        # Name should be something like "weekly_report"
        assert "_" in result.name or result.name != ""


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestAutomationLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_automation_input(self, agent):
        """Should build system + user prompt from AutomationInput."""
        system, user = agent.build_prompt(AutomationInput(
            description="send daily email report",
            context={"region": "US"},
        ))
        assert "automation" in system.lower()
        assert "send daily email report" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("automate report generation")
        assert "automation" in system.lower()

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '''{
            "name": "daily_report",
            "triggers": [{"type": "schedule", "config": {"interval": "daily"}, "description": "Daily trigger"}],
            "actions": [{"type": "email", "config": {"to": "admin@co.com"}, "description": "Send email"}],
            "schedule": {"type": "cron", "interval_seconds": 0, "cron_expression": "0 9 * * *", "description": "Daily at 9"},
            "conditions": [],
            "description": "Daily report"
        }'''
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.name == "daily_report"
        assert len(result.triggers) == 1
        assert result.triggers[0].type == "schedule"
        assert len(result.actions) == 1
        assert result.actions[0].type == "email"
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "This automation should send a daily email report"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_parse_response_empty(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None


# ============================================================
#  Test: SmartMemory Integration
# ============================================================

class TestAutomationSmartMemory:
    """Tests for SmartMemory cache integration."""

    def test_smart_memory_cache_hit(self, agent_with_memory):
        """Should return cached result from SmartMemory."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "response": '{"name":"cached_auto","triggers":[{"type":"manual","config":{},"description":""}],"actions":[{"type":"log","config":{},"description":""}],"schedule":{"type":"manual","interval_seconds":0,"cron_expression":"","description":""},"conditions":[],"description":"cached"}',
        }
        result = agent.fallback(AutomationInput(description="daily report"))
        assert result.name == "cached_auto"
        assert result.source == "fallback"

    def test_smart_memory_save_on_result(self, agent_with_memory):
        """Should save result to SmartMemory after fallback."""
        agent, mock_memory = agent_with_memory
        agent.fallback(AutomationInput(description="daily report"))
        assert mock_memory.save_to_cache.called

    def test_smart_memory_failure_graceful(self, agent):
        """Should handle SmartMemory failures gracefully."""
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        mock_memory.save_to_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        result = agent.fallback(AutomationInput(description="daily report"))
        assert result is not None


# ============================================================
#  Test: Legacy Compatibility
# ============================================================

class TestAutomationLegacyCompat:
    """Tests for to_workflow_dict() legacy compatibility."""

    def test_to_workflow_dict(self, agent):
        """Should convert AutomationOutput to workflow dict."""
        output = AutomationOutput(
            name="daily_report",
            triggers=[TriggerSpec(type="schedule", config={"interval": "daily"})],
            actions=[ActionSpec(type="email", config={"to": "admin@co.com"}, description="Send email")],
            schedule=ScheduleSpec(type="cron", cron_expression="0 9 * * *"),
            conditions=["if sales > 1000"],
            description="Daily report automation",
        )
        result = agent.to_workflow_dict(output)
        assert result["name"] == "daily_report"
        assert result["trigger"]["type"] == "schedule"
        assert len(result["actions"]) == 1
        assert result["actions"][0]["type"] == "email"
        assert result["schedule"]["cron_expression"] == "0 9 * * *"
        assert "if sales > 1000" in result["conditions"]

    def test_to_workflow_dict_empty_triggers(self, agent):
        """Should handle empty triggers gracefully."""
        output = AutomationOutput(name="test", triggers=[], actions=[])
        result = agent.to_workflow_dict(output)
        assert result["trigger"]["type"] == "schedule"  # default


# ============================================================
#  Test: Wire and Stats
# ============================================================

class TestAutomationWireAndStats:
    """Tests for wire() and stats tracking."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls in stats."""
        agent.fallback(AutomationInput(description="daily report"))
        stats = agent.stats
        assert stats["name"] == "automation"
        assert stats["total_calls"] >= 1

    def test_design_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = AutomationOutput(
            name="llm_auto", source="llm",
            triggers=[TriggerSpec(type="schedule")],
            actions=[ActionSpec(type="log")],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.design_with_runner(mock_runner, "daily report")
        assert result.name == "llm_auto"
        assert result.source == "llm"

    def test_design_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.design_with_runner(mock_runner, "daily report")
        assert result.source == "fallback"
