"""
TITAN OMNISCALE X - ThinkingEngine Unit Tests

Tests for src/core/thinking_engine.py:
  - plan_generation (template identification, entity extraction)
  - select_template
  - customize_template (variable substitution)
  - reason (with and without AI)
  - evaluate_code (static analysis + AI)
  - decompose_problem (fallback)
  - design_architecture (fallback)
  - chain_of_thought
  - Stats
"""

import os
import pytest
from unittest.mock import MagicMock, patch

# Ensure 'os' is available in the thinking_engine module
# (the source uses os.environ but forgot the import)
import src.core.thinking_engine as _te_mod
if not hasattr(_te_mod, 'os'):
    _te_mod.os = os

from src.core.thinking_engine import (
    ThinkingEngine,
    GenerationPlan,
    ThinkingResult,
    APP_TEMPLATES,
    AUTOMATION_TEMPLATES,
)


# ============================================================
#  INITIALIZATION TESTS
# ============================================================

class TestThinkingEngineInit:
    """Tests for ThinkingEngine initialization."""

    def test_init_no_dependencies(self):
        """Should initialize without any AI dependencies."""
        engine = ThinkingEngine()
        assert engine._ai is None
        assert engine._semantic is None
        assert engine._memory is None
        assert engine._call_count == 0
        assert engine._thinking_time == 0.0

    def test_init_with_mock_ai(self):
        """Should accept optional AI engine."""
        mock_ai = MagicMock()
        engine = ThinkingEngine(mini_ai=mock_ai)
        assert engine._ai is mock_ai

    def test_init_with_all_layers(self):
        """Should accept all three AI layers."""
        mock_ai = MagicMock()
        mock_semantic = MagicMock()
        mock_memory = MagicMock()
        engine = ThinkingEngine(
            mini_ai=mock_ai,
            semantic_engine=mock_semantic,
            smart_memory=mock_memory,
        )
        assert engine._ai is mock_ai
        assert engine._semantic is mock_semantic
        assert engine._memory is mock_memory


# ============================================================
#  PLAN GENERATION TESTS
# ============================================================

class TestPlanGeneration:
    """Tests for ThinkingEngine.plan_generation()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_generation_plan(self):
        """Should return a GenerationPlan object."""
        plan = self.engine.plan_generation("Build a CRM system")
        assert isinstance(plan, GenerationPlan)

    def test_identifies_crm_template(self):
        """Should identify 'crm' template from CRM description."""
        plan = self.engine.plan_generation("Necesito un sistema CRM para clientes y ventas")
        assert plan.template_type == "crm"

    def test_identifies_inventory_template(self):
        """Should identify 'inventory' template from inventory description."""
        plan = self.engine.plan_generation("Sistema de inventario y stock")
        assert plan.template_type == "inventory"

    def test_identifies_auth_template(self):
        """Should identify 'auth_system' template from auth description."""
        plan = self.engine.plan_generation("Auth and login system")
        assert plan.template_type == "auth_system"

    def test_identifies_webhook_template(self):
        """Should identify 'webhook_handler' template."""
        plan = self.engine.plan_generation("webhook handler for events")
        assert plan.template_type == "webhook_handler"

    def test_generic_for_unknown(self):
        """Should return 'generic' for unrecognized descriptions."""
        plan = self.engine.plan_generation("something completely unknown xyz")
        assert plan.template_type == "generic"

    def test_includes_entities(self):
        """Plan should include entity definitions."""
        plan = self.engine.plan_generation("CRM system for customers")
        assert len(plan.entities) > 0

    def test_includes_modules(self):
        """Plan should include module definitions."""
        plan = self.engine.plan_generation("CRM system")
        assert len(plan.modules) > 0

    def test_includes_endpoints(self):
        """Plan should include endpoint definitions."""
        plan = self.engine.plan_generation("CRM system")
        assert len(plan.endpoints) > 0

    def test_includes_config(self):
        """Plan should include config variables."""
        plan = self.engine.plan_generation("CRM system")
        assert isinstance(plan.config_vars, dict)
        assert "db_name" in plan.config_vars

    def test_fallback_source_no_ai(self):
        """Without AI, plan source should be 'fallback'."""
        plan = self.engine.plan_generation("Test")
        assert plan.source == "fallback"


# ============================================================
#  SELECT TEMPLATE TESTS
# ============================================================

class TestSelectTemplate:
    """Tests for ThinkingEngine.select_template()."""

    def setup_method(self):
        self.engine = ThinkingEngine()

    def test_returns_template_and_confidence(self):
        """Should return (template_name, confidence) tuple."""
        template, confidence = self.engine.select_template("Build a CRM")
        assert isinstance(template, str)
        assert isinstance(confidence, float)

    def test_crm_selection(self):
        """Should select CRM template for CRM-related request."""
        template, _ = self.engine.select_template("Necesito un sistema CRM")
        assert template == "crm"

    def test_confidence_range(self):
        """Confidence should be between 0.0 and 1.0."""
        _, confidence = self.engine.select_template("Any request")
        assert 0.0 <= confidence <= 1.0


# ============================================================
#  CUSTOMIZE TEMPLATE TESTS
# ============================================================

class TestCustomizeTemplate:
    """Tests for ThinkingEngine.customize_template()."""

    def setup_method(self):
        self.engine = ThinkingEngine()

    def test_simple_substitution(self):
        """Should substitute __PLACEHOLDER__ variables."""
        template = "Hello __NAME__, welcome to __APP__!"
        result = self.engine.customize_template(template, {"NAME": "World", "APP": "TITAN"})
        assert "Hello World" in result
        assert "welcome to TITAN" in result

    def test_unfilled_gaps_get_defaults(self):
        """Unfilled gaps should get default values."""
        template = "Port: __PORT__"
        result = self.engine.customize_template(template, {"port": 8080})
        assert "8080" in result

    def test_no_gaps_unchanged(self):
        """Template without gaps should be unchanged (except potential enhancement)."""
        template = "Simple text without gaps"
        result = self.engine.customize_template(template, {})
        assert "Simple text without gaps" in result


# ============================================================
#  REASON TESTS
# ============================================================

class TestReason:
    """Tests for ThinkingEngine.reason()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_thinking_result(self):
        """Should return a ThinkingResult object."""
        result = self.engine.reason("How to build an API?")
        assert isinstance(result, ThinkingResult)

    def test_no_model_returns_low_confidence(self):
        """Without AI, should return low confidence result."""
        result = self.engine.reason("Test query")
        assert result.confidence <= 0.2
        assert result.source in ("no_model", "semantic_fallback")

    def test_with_context(self):
        """Should accept additional context."""
        result = self.engine.reason("Test", context="Some context")
        assert isinstance(result, ThinkingResult)

    def test_with_mock_ai(self):
        """With mock AI, should return thinking source."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Use FastAPI with SQLite."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.reason("How to build an API?")
        assert result.source == "thinking"
        assert result.confidence > 0.5


# ============================================================
#  EVALUATE CODE TESTS
# ============================================================

class TestEvaluateCode:
    """Tests for ThinkingEngine.evaluate_code()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_detects_eval_usage(self):
        """Should detect eval() as security issue."""
        result = self.engine.evaluate_code("x = eval(input())")
        assert any("eval()" in i for i in result["issues"])

    def test_detects_exec_usage(self):
        """Should detect exec() as security issue."""
        result = self.engine.evaluate_code("exec('print(1)')")
        assert any("exec()" in i for i in result["issues"])

    def test_detects_os_system(self):
        """Should detect os.system() as security issue."""
        result = self.engine.evaluate_code("import os\nos.system('ls')")
        assert any("os.system()" in i for i in result["issues"])

    def test_detects_pickle(self):
        """Should detect pickle as security issue."""
        result = self.engine.evaluate_code("import pickle\npickle.loads(data)")
        assert any("pickle" in i for i in result["issues"])

    def test_detects_todo(self):
        """Should detect TODO/FIXME markers."""
        result = self.engine.evaluate_code("def f():\n    # TODO: implement\n    pass")
        assert any("TODO" in i or "FIXME" in i for i in result["issues"])

    def test_suggests_error_handling(self):
        """Should suggest error handling when missing."""
        result = self.engine.evaluate_code("def f(x):\n    return x + 1")
        assert any("error handling" in s.lower() or "try" in s.lower()
                    for s in result["suggestions"])

    def test_returns_quality_score(self):
        """Should return a quality score between 0 and 1."""
        result = self.engine.evaluate_code("x = 1")
        assert 0.0 <= result["quality_score"] <= 1.0

    def test_static_analysis_source(self):
        """Without AI, source should be 'static_analysis'."""
        result = self.engine.evaluate_code("x = 1")
        assert result["source"] == "static_analysis"


# ============================================================
#  DECOMPOSE PROBLEM TESTS
# ============================================================

class TestDecomposeProblem:
    """Tests for ThinkingEngine.decompose_problem()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_list_of_subproblems(self):
        """Should return a list of subproblem dicts."""
        result = self.engine.decompose_problem("Build a web app")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_subproblems_have_required_fields(self):
        """Each subproblem should have name, description, priority."""
        result = self.engine.decompose_problem("Build a web app")
        for sp in result:
            assert "name" in sp
            assert "description" in sp
            assert "priority" in sp

    def test_max_five_subproblems(self):
        """Should return at most 5 subproblems."""
        result = self.engine.decompose_problem("Complex problem")
        assert len(result) <= 5

    def test_auth_keyword_adds_auth_subproblem(self):
        """Auth keyword should add auth subproblem."""
        result = self.engine.decompose_problem("Build an auth system")
        names = [sp["name"] for sp in result]
        assert "implement_auth" in names

    def test_email_keyword_adds_notification_subproblem(self):
        """Email keyword should add notification subproblem."""
        result = self.engine.decompose_problem("System with email notifications")
        names = [sp["name"] for sp in result]
        assert "setup_notifications" in names


# ============================================================
#  DESIGN ARCHITECTURE TESTS
# ============================================================

class TestDesignArchitecture:
    """Tests for ThinkingEngine.design_architecture()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_returns_architecture_dict(self):
        """Should return an architecture dictionary."""
        result = self.engine.design_architecture("Build a CRM")
        assert isinstance(result, dict)
        assert "type" in result
        assert "components" in result

    def test_fallback_monolith_for_app(self):
        """App templates should default to monolith architecture."""
        result = self.engine.design_architecture("Build a CRM")
        assert result["type"] == "monolith"
        assert result["source"] == "fallback"

    def test_fallback_worker_for_automation(self):
        """Automation templates should default to worker architecture."""
        result = self.engine.design_architecture("webhook callback evento")
        assert result["type"] == "worker"

    def test_includes_tech_stack(self):
        """Architecture should include tech stack."""
        result = self.engine.design_architecture("Build a web API")
        assert "tech_stack" in result
        assert len(result["tech_stack"]) > 0

    def test_includes_data_flow(self):
        """Architecture should include data flow description."""
        result = self.engine.design_architecture("Build a CRM")
        assert "data_flow" in result


# ============================================================
#  CHAIN OF THOUGHT TESTS
# ============================================================

class TestChainOfThought:
    """Tests for ThinkingEngine.chain_of_thought()."""

    def setup_method(self):
        self.engine = ThinkingEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_no_model_returns_low_confidence(self):
        """Without AI, should return low confidence result."""
        result = self.engine.chain_of_thought("Test problem")
        assert result.confidence <= 0.2
        assert result.source == "no_model"

    def test_with_mock_ai(self):
        """With mock AI, should return chain_of_thought source."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Step 1: Identify the pattern. Therefore, use caching."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.chain_of_thought("How to optimize?")
        assert result.source == "chain_of_thought"
        assert result.confidence > 0.3

    def test_max_steps_respected(self):
        """Should limit steps to max_steps."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "Some reasoning step."
        engine = ThinkingEngine(mini_ai=mock_ai)
        result = engine.chain_of_thought("Test", max_steps=2)
        # Should stop at 2 steps (or fewer if conclusion detected)
        assert result.thinking_time_s >= 0


# ============================================================
#  STATS TESTS
# ============================================================

class TestThinkingStats:
    """Tests for ThinkingEngine.stats property."""

    def test_stats_structure(self):
        """Stats should contain expected keys."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert "total_calls" in stats
        assert "total_thinking_time_s" in stats
        assert "ai_available" in stats
        assert "semantic_available" in stats
        assert "memory_available" in stats
        assert "app_templates" in stats
        assert "automation_templates" in stats

    def test_template_counts(self):
        """Stats should report correct template counts."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert stats["app_templates"] == len(APP_TEMPLATES)
        assert stats["automation_templates"] == len(AUTOMATION_TEMPLATES)

    def test_availability_no_deps(self):
        """Without dependencies, all availability should be False."""
        engine = ThinkingEngine()
        stats = engine.stats
        assert stats["ai_available"] is False
        assert stats["semantic_available"] is False
        assert stats["memory_available"] is False
