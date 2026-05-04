"""
Unit tests for Agent Schemas

Tests dataclass construction, default values, field validation,
and schema relationships across all agent schemas.
"""

import pytest
from dataclasses import fields

from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningStep, ReasoningOutput,
    BusinessInput, BusinessOutput,
    CodeInput, FileSpec, CodeOutput,
    AutomationInput, TriggerSpec, ActionSpec, ScheduleSpec, AutomationOutput,
    ValidationInput, ValidationIssue, ValidationOutput,
    ContextInput, ContextEntry, ContextOutput,
    CriticalityInput, CriticalityOutput,
)


# ============================================================
#  INTENT SCHEMAS
# ============================================================

class TestIntentInput:
    """Tests for IntentInput schema."""

    def test_default_values(self):
        """Should have empty string defaults."""
        inp = IntentInput()
        assert inp.message == ""
        assert inp.context == ""

    def test_custom_values(self):
        """Should accept custom values."""
        inp = IntentInput(message="create API", context="web app")
        assert inp.message == "create API"
        assert inp.context == "web app"


class TestIntentOutput:
    """Tests for IntentOutput schema."""

    def test_default_values(self):
        """Should have valid defaults for all fields."""
        out = IntentOutput()
        assert out.operation == "SEARCH"
        assert out.goal == "FEATURE_ADD"
        assert out.target == ""
        assert out.language == "python"
        assert out.entities == {}
        assert out.template_type == "generic"
        assert out.criticality == "standard"
        assert out.confidence == 0.0
        assert out.source == "fallback"

    def test_custom_operation(self):
        """Should accept valid operation values."""
        for op in ["CREATE", "REFACTOR", "DELETE", "SEARCH", "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE"]:
            out = IntentOutput(operation=op)
            assert out.operation == op

    def test_custom_criticality(self):
        """Should accept valid criticality values."""
        for crit in ["standard", "moderate", "critical"]:
            out = IntentOutput(criticality=crit)
            assert out.criticality == crit


# ============================================================
#  REASONING SCHEMAS
# ============================================================

class TestReasoningInput:
    """Tests for ReasoningInput schema."""

    def test_default_values(self):
        """Should have sensible defaults."""
        inp = ReasoningInput()
        assert inp.query == ""
        assert inp.mode == "step_by_step"
        assert inp.context == ""
        assert inp.max_steps == 5

    def test_custom_mode(self):
        """Should accept valid mode values."""
        for mode in ["step_by_step", "self_reflect", "with_context"]:
            inp = ReasoningInput(mode=mode)
            assert inp.mode == mode


class TestReasoningStep:
    """Tests for ReasoningStep schema."""

    def test_default_values(self):
        """Should have zero/empty defaults."""
        step = ReasoningStep()
        assert step.step_number == 0
        assert step.description == ""
        assert step.conclusion == ""

    def test_custom_values(self):
        """Should accept custom values."""
        step = ReasoningStep(step_number=1, description="Analyze", conclusion="Done")
        assert step.step_number == 1
        assert step.description == "Analyze"


class TestReasoningOutput:
    """Tests for ReasoningOutput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        out = ReasoningOutput()
        assert out.answer == ""
        assert out.confidence == 0.0
        assert out.steps == []
        assert out.refinements == 0
        assert out.source == "fallback"

    def test_with_steps(self):
        """Should accept a list of ReasoningStep."""
        steps = [ReasoningStep(step_number=i, description=f"Step {i}") for i in range(3)]
        out = ReasoningOutput(answer="yes", steps=steps)
        assert len(out.steps) == 3
        assert out.steps[0].step_number == 0


# ============================================================
#  BUSINESS SCHEMAS
# ============================================================

class TestBusinessInput:
    """Tests for BusinessInput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        inp = BusinessInput()
        assert inp.operation_type == ""
        assert inp.data == {}
        assert inp.context == {}
        assert inp.description == ""

    def test_custom_values(self):
        """Should accept custom operation types and data."""
        inp = BusinessInput(operation_type="invoice", data={"amount": 100})
        assert inp.operation_type == "invoice"
        assert inp.data["amount"] == 100


class TestBusinessOutput:
    """Tests for BusinessOutput schema."""

    def test_default_values(self):
        """Should have failure-safe defaults."""
        out = BusinessOutput()
        assert out.success is False
        assert out.data == {}
        assert out.side_effects == []
        assert out.insights == []
        assert out.errors == []
        assert out.source == "fallback"

    def test_successful_output(self):
        """Should accept successful output data."""
        out = BusinessOutput(success=True, data={"total": 150.0}, insights=["tax applied"])
        assert out.success is True
        assert out.data["total"] == 150.0


# ============================================================
#  CODE SCHEMAS
# ============================================================

class TestCodeInput:
    """Tests for CodeInput schema."""

    def test_default_values(self):
        """Should have generate/python as defaults."""
        inp = CodeInput()
        assert inp.task == "generate"
        assert inp.language == "python"
        assert inp.requirements == ""
        assert inp.existing_code == ""
        assert inp.constraints == {}

    def test_custom_task(self):
        """Should accept valid task types."""
        for task in ["generate", "transform", "scaffold", "optimize", "fix"]:
            inp = CodeInput(task=task)
            assert inp.task == task


class TestFileSpec:
    """Tests for FileSpec schema."""

    def test_default_values(self):
        """Should have empty string defaults."""
        spec = FileSpec()
        assert spec.path == ""
        assert spec.content == ""
        assert spec.language == ""

    def test_custom_values(self):
        """Should accept file specification data."""
        spec = FileSpec(path="main.py", content="print('hi')", language="python")
        assert spec.path == "main.py"
        assert spec.content == "print('hi')"


class TestCodeOutput:
    """Tests for CodeOutput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        out = CodeOutput()
        assert out.code == ""
        assert out.language == "python"
        assert out.files == []
        assert out.test_code == ""
        assert out.explanation == ""

    def test_with_files(self):
        """Should accept a list of FileSpec."""
        files = [FileSpec(path="a.py", content="code", language="python")]
        out = CodeOutput(code="main()", files=files)
        assert len(out.files) == 1
        assert out.files[0].path == "a.py"


# ============================================================
#  AUTOMATION SCHEMAS
# ============================================================

class TestAutomationInput:
    """Tests for AutomationInput schema."""

    def test_default_values(self):
        """Should have empty defaults."""
        inp = AutomationInput()
        assert inp.description == ""
        assert inp.context == {}


class TestTriggerSpec:
    """Tests for TriggerSpec schema."""

    def test_default_type_is_manual(self):
        """Should default to manual trigger."""
        t = TriggerSpec()
        assert t.type == "manual"
        assert t.config == {}

    def test_valid_trigger_types(self):
        """Should accept valid trigger types."""
        for tt in ["manual", "schedule", "event", "webhook"]:
            t = TriggerSpec(type=tt)
            assert t.type == tt


class TestActionSpec:
    """Tests for ActionSpec schema."""

    def test_default_type_is_log(self):
        """Should default to log action."""
        a = ActionSpec()
        assert a.type == "log"


class TestScheduleSpec:
    """Tests for ScheduleSpec schema."""

    def test_default_values(self):
        """Should have manual/zero defaults."""
        s = ScheduleSpec()
        assert s.type == "manual"
        assert s.interval_seconds == 0
        assert s.cron_expression == ""


class TestAutomationOutput:
    """Tests for AutomationOutput schema."""

    def test_default_values(self):
        """Should have unnamed automation defaults."""
        out = AutomationOutput()
        assert out.name == "unnamed_automation"
        assert out.triggers == []
        assert out.actions == []
        assert isinstance(out.schedule, ScheduleSpec)
        assert out.conditions == []

    def test_with_triggers_and_actions(self):
        """Should accept lists of TriggerSpec and ActionSpec."""
        out = AutomationOutput(
            name="daily_report",
            triggers=[TriggerSpec(type="schedule")],
            actions=[ActionSpec(type="email")],
        )
        assert out.name == "daily_report"
        assert len(out.triggers) == 1
        assert len(out.actions) == 1


# ============================================================
#  VALIDATION SCHEMAS
# ============================================================

class TestValidationInput:
    """Tests for ValidationInput schema."""

    def test_default_values(self):
        """Should default to code target with python language."""
        inp = ValidationInput()
        assert inp.target == "code"
        assert inp.content == ""
        assert inp.rules == []
        assert inp.language == "python"


class TestValidationIssue:
    """Tests for ValidationIssue schema."""

    def test_default_values(self):
        """Should default to warning severity."""
        issue = ValidationIssue()
        assert issue.severity == "warning"
        assert issue.code == ""
        assert issue.message == ""
        assert issue.line == 0

    def test_custom_severity(self):
        """Should accept valid severity levels."""
        for sev in ["error", "warning", "info"]:
            issue = ValidationIssue(severity=sev)
            assert issue.severity == sev


class TestValidationOutput:
    """Tests for ValidationOutput schema."""

    def test_default_is_valid(self):
        """Should default to valid with no issues."""
        out = ValidationOutput()
        assert out.is_valid is True
        assert out.issues == []
        assert out.suggestions == []
        assert out.risk_score == 0.0

    def test_with_issues(self):
        """Should accept validation issues."""
        issues = [ValidationIssue(severity="error", message="SQL injection")]
        out = ValidationOutput(is_valid=False, issues=issues, risk_score=0.9)
        assert out.is_valid is False
        assert len(out.issues) == 1
        assert out.issues[0].severity == "error"


# ============================================================
#  CONTEXT SCHEMAS
# ============================================================

class TestContextInput:
    """Tests for ContextInput schema."""

    def test_default_values(self):
        """Should have empty/None defaults."""
        inp = ContextInput()
        assert inp.message == ""
        assert inp.intent_output is None
        assert inp.max_tokens == 500

    def test_with_intent_output(self):
        """Should accept IntentOutput as intent_output."""
        intent = IntentOutput(operation="CREATE")
        inp = ContextInput(message="test", intent_output=intent)
        assert inp.intent_output.operation == "CREATE"


class TestContextEntry:
    """Tests for ContextEntry schema."""

    def test_default_values(self):
        """Should have sensible defaults."""
        entry = ContextEntry()
        assert entry.content == ""
        assert entry.importance == 0.5
        assert entry.recency == 1.0
        assert entry.relevance_score == 0.0

    def test_custom_values(self):
        """Should accept custom relevance and importance."""
        entry = ContextEntry(content="test", importance=0.9, recency=0.3)
        assert entry.importance == 0.9
        assert entry.recency == 0.3


class TestContextOutput:
    """Tests for ContextOutput schema."""

    def test_default_values(self):
        """Should have empty defaults and compression_ratio of 1.0."""
        out = ContextOutput()
        assert out.compressed_context == ""
        assert out.relevant_memories == []
        assert out.entries_used == 0
        assert out.compression_ratio == 1.0
        assert out.source == "fallback"


# ============================================================
#  CRITICALITY SCHEMAS
# ============================================================

class TestCriticalityInput:
    """Tests for CriticalityInput schema."""

    def test_default_values(self):
        """Should have SEARCH/FEATURE_ADD defaults."""
        inp = CriticalityInput()
        assert inp.operation == "SEARCH"
        assert inp.goal == "FEATURE_ADD"
        assert inp.target == ""
        assert inp.context == ""
        assert inp.code_snippet == ""
        assert inp.existing_level is None

    def test_custom_values(self):
        """Should accept custom criticality input."""
        inp = CriticalityInput(
            operation="DELETE", goal="SECURITY_HARDEN",
            target="auth.py", existing_level=2,
        )
        assert inp.operation == "DELETE"
        assert inp.target == "auth.py"
        assert inp.existing_level == 2


class TestCriticalityOutput:
    """Tests for CriticalityOutput schema."""

    def test_default_values(self):
        """Should default to level 2 standard path."""
        out = CriticalityOutput()
        assert out.level == 2
        assert out.path == "standard"
        assert out.confidence == 0.0
        assert out.source == "fallback"
        assert out.adjustments == {}

    def test_critical_level(self):
        """Should accept critical level 3."""
        out = CriticalityOutput(
            level=3, path="high_crit",
            reason="auth module", confidence=0.95,
        )
        assert out.level == 3
        assert out.path == "high_crit"
        assert out.confidence == 0.95

    def test_valid_levels(self):
        """Should accept levels 1, 2, and 3."""
        for level in [1, 2, 3]:
            out = CriticalityOutput(level=level)
            assert out.level == level
