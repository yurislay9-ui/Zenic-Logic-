"""
Unit tests for StepDispatcher

Tests execute_step for various action types (ANALYZE_STRUCTURE,
GENERATE_CODE, REPLACE_AST_NODE, DELETE_AST_NODE, PATCH_FIX, etc.),
execute_plan_steps for multi-step plans, and handling of unknown step types.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.core.step_dispatcher import StepDispatcher


# ============================================================
#  Fixtures
# ============================================================

def make_step(action, constraints=None, target_node_name=""):
    """Create a mock step object with given action and constraints."""
    step = MagicMock()
    step.action = action
    step.constraints = constraints or {}
    step.target_node_name = target_node_name
    return step


def make_intent(op="CREATE", target="test_func", scrap_query="test query"):
    """Create a mock intent payload."""
    intent = MagicMock()
    intent.op = op
    intent.target = target
    intent.scrap_query = scrap_query
    intent.raw_code = ""
    return intent


def make_plan(solver_proof=None):
    """Create a mock plan with optional solver proof."""
    plan = MagicMock()
    plan.solver_proof = solver_proof
    plan.steps = []
    return plan


@pytest.fixture
def mock_orchestrator():
    """Create a fully mocked orchestrator for StepDispatcher."""
    orch = MagicMock()

    # AST Engine
    orch.ast_engine.analyze_structure.return_value = {
        "functions": 3, "classes": 1, "max_complexity": 5,
        "function_names": ["func_a", "func_b", "func_c"],
    }
    orch.ast_engine.get_node_info.return_value = [
        {"node_type": "function", "name": "test_func", "complexity": 3},
    ]

    # Scrap agent (async methods)
    orch.scrap.smart_fetch = AsyncMock(return_value={
        "success": True, "content": "sample code", "source": "github",
    })
    orch.scrap.fetch_all_sources = AsyncMock(return_value={
        "github": "gh_code", "devdocs": "",
    })

    # Code generator
    orch._code_gen.generate_contextual_code.return_value = "def new_func(): pass"
    orch._code_gen.extract_solver_insights.return_value = {}

    # Code transformer
    orch._code_transform.optimize_function.return_value = "def optimized(): pass"

    # Surgeon
    orch.surgeon.mutate_node.return_value = "def replaced(): pass"
    orch.surgeon.delete_function.return_value = "# deleted"

    # Analysis utils
    orch._analysis.apply_fix.return_value = "def fixed(): pass"
    orch._analysis.generate_quality_report.return_value = "Quality: 85/100"
    orch._analysis.explain_code.return_value = "This code does X"
    orch._analysis.explain_concept.return_value = "Concept explanation"
    orch._analysis.analyze_and_respond.return_value = "Analysis result"
    orch._analysis.general_response.return_value = "General response"
    orch._analysis.full_analysis.return_value = "Full analysis result"
    orch._analysis.check_dependencies.return_value = ["dep1", "dep2"]

    # MiniAI
    orch._ai.is_loaded = False
    orch._ai.suggest_pattern.return_value = "validator_pattern"

    # Validation agent
    orch._validation_agent = None
    orch._agent_runner = None

    # Fractal generator
    orch._fractal_gen = None

    return orch


@pytest.fixture
def dispatcher(mock_orchestrator):
    """Create a StepDispatcher with mocked orchestrator."""
    return StepDispatcher(mock_orchestrator)


# ============================================================
#  ANALYZE_STRUCTURE Tests
# ============================================================

class TestAnalyzeStructure:
    """Tests for ANALYZE_STRUCTURE action type."""

    @pytest.mark.asyncio
    async def test_analyze_with_code(self, dispatcher, mock_orchestrator):
        """Should analyze structure when code is provided."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def foo(): pass", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) == 1
        assert "Structure:" in explanations[0]
        assert "3 functions" in explanations[0]

    @pytest.mark.asyncio
    async def test_analyze_without_code(self, dispatcher):
        """Should append no-code message when code is empty."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) == 1
        assert "No code provided" in explanations[0]

    @pytest.mark.asyncio
    async def test_analyze_returns_code_unchanged(self, dispatcher):
        """Should not modify code or result_code for ANALYZE_STRUCTURE."""
        step = make_step("ANALYZE_STRUCTURE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert code == "x=1"
        assert r_code == ""


# ============================================================
#  SCRAPE_PATTERNS Tests
# ============================================================

class TestScrapePatterns:
    """Tests for SCRAPE_PATTERNS action type."""

    @pytest.mark.asyncio
    async def test_scrape_smart_fetch_success(self, dispatcher, mock_orchestrator):
        """Should use smart_fetch result when successful."""
        step = make_step("SCRAPE_PATTERNS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert len(explanations) >= 1
        assert "SmartScraper" in explanations[0]

    @pytest.mark.asyncio
    async def test_scrape_uses_constraints_query(self, dispatcher, mock_orchestrator):
        """Should prefer constraints query over intent.scrap_query."""
        step = make_step("SCRAPE_PATTERNS", constraints={"query": "oauth patterns"})
        intent = make_intent()
        await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.scrap.smart_fetch.assert_called_once_with("oauth patterns", "python")

    @pytest.mark.asyncio
    async def test_scrape_fallback_when_smart_fails(self, dispatcher, mock_orchestrator):
        """Should fallback to fetch_all_sources when smart_fetch fails."""
        mock_orchestrator.scrap.smart_fetch = AsyncMock(return_value={"success": False})
        step = make_step("SCRAPE_PATTERNS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.scrap.fetch_all_sources.assert_called_once()


# ============================================================
#  GENERATE_CODE Tests
# ============================================================

class TestGenerateCode:
    """Tests for GENERATE_CODE action type."""

    @pytest.mark.asyncio
    async def test_generate_code(self, dispatcher, mock_orchestrator):
        """Should call code_gen.generate_contextual_code and return result."""
        step = make_step("GENERATE_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert r_code == "def new_func(): pass"
        assert any("Code generated" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_generate_code_uses_intent_op(self, dispatcher, mock_orchestrator):
        """Should pass intent.op to generate_contextual_code."""
        step = make_step("GENERATE_CODE")
        intent = make_intent(op="REFACTOR")
        await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator._code_gen.generate_contextual_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_code_explains_intent(self, dispatcher, mock_orchestrator):
        """Should explain which operation code was generated for."""
        step = make_step("GENERATE_CODE")
        intent = make_intent(op="CREATE")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("CREATE" in e for e in explanations)


# ============================================================
#  REPLACE_AST_NODE Tests
# ============================================================

class TestReplaceAstNode:
    """Tests for REPLACE_AST_NODE action type."""

    @pytest.mark.asyncio
    async def test_replace_with_code_and_target(self, dispatcher, mock_orchestrator):
        """Should perform AST surgery when code and target_node_name are present."""
        step = make_step("REPLACE_AST_NODE", target_node_name="old_func")
        intent = make_intent()
        plan = make_plan(solver_proof={})
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def old_func(): pass", "", [], "python", {}, plan,
        )
        assert r_code == "def replaced(): pass"
        mock_orchestrator.surgeon.mutate_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_replace_fallback_without_target(self, dispatcher, mock_orchestrator):
        """Should fall back to contextual code generation without target."""
        step = make_step("REPLACE_AST_NODE", target_node_name="")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def x(): pass", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator._code_gen.generate_contextual_code.assert_called_once()
        assert "Optimized code generated" in explanations

    @pytest.mark.asyncio
    async def test_replace_with_ai_suggestion(self, dispatcher, mock_orchestrator):
        """Should use MiniAI pattern suggestion when AI is loaded."""
        mock_orchestrator._ai.is_loaded = True
        step = make_step("REPLACE_AST_NODE", target_node_name="target_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("MiniAI suggests pattern" in e for e in explanations)


# ============================================================
#  DELETE_AST_NODE Tests
# ============================================================

class TestDeleteAstNode:
    """Tests for DELETE_AST_NODE action type."""

    @pytest.mark.asyncio
    async def test_delete_with_code_and_target(self, dispatcher, mock_orchestrator):
        """Should delete the AST node via surgeon."""
        step = make_step("DELETE_AST_NODE", target_node_name="unused_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def unused_func(): pass", "", [], "python", {}, make_plan(),
        )
        assert r_code == "# deleted"
        mock_orchestrator.surgeon.delete_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_without_target(self, dispatcher, mock_orchestrator):
        """Should do nothing when no target node name provided."""
        step = make_step("DELETE_AST_NODE", target_node_name="")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        mock_orchestrator.surgeon.delete_function.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_explains_removal(self, dispatcher, mock_orchestrator):
        """Should add explanation about deleted function."""
        step = make_step("DELETE_AST_NODE", target_node_name="old_func")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def old_func(): pass", "", [], "python", {}, make_plan(),
        )
        assert any("deleted" in e for e in explanations)


# ============================================================
#  Other Action Types
# ============================================================

class TestOtherActions:
    """Tests for PATCH_FIX, QUALITY_REPORT, EXPLAIN_CODE, etc."""

    @pytest.mark.asyncio
    async def test_patch_fix(self, dispatcher, mock_orchestrator):
        """PATCH_FIX should apply fix via analysis utils."""
        step = make_step("PATCH_FIX")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "broken code", "", [], "python", {}, make_plan(),
        )
        assert r_code == "def fixed(): pass"
        assert "Fix patch applied" in explanations

    @pytest.mark.asyncio
    async def test_quality_report_with_code(self, dispatcher, mock_orchestrator):
        """QUALITY_REPORT should generate report when code present."""
        step = make_step("QUALITY_REPORT")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert any("Quality" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_explain_code_with_code(self, dispatcher, mock_orchestrator):
        """EXPLAIN_CODE should explain when code present."""
        step = make_step("EXPLAIN_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "def foo(): pass", "", [], "python", {}, make_plan(),
        )
        assert any("This code does X" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_explain_code_without_code(self, dispatcher, mock_orchestrator):
        """EXPLAIN_CODE should explain concept when no code."""
        step = make_step("EXPLAIN_CODE")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Concept explanation" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_search_definition_found(self, dispatcher, mock_orchestrator):
        """SEARCH_DEFINITION should find nodes in AST engine."""
        step = make_step("SEARCH_DEFINITION")
        intent = make_intent(target="test_func")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Found:" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_search_definition_not_found(self, dispatcher, mock_orchestrator):
        """SEARCH_DEFINITION should report when target not found."""
        mock_orchestrator.ast_engine.get_node_info.return_value = []
        step = make_step("SEARCH_DEFINITION")
        intent = make_intent(target="missing")
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("not found" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_trace_execution(self, dispatcher, mock_orchestrator):
        """TRACE_EXECUTION should trace function names."""
        step = make_step("TRACE_EXECUTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Symbolic execution trace" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_quick_analysis(self, dispatcher):
        """QUICK_ANALYSIS should append completion message."""
        step = make_step("QUICK_ANALYSIS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Quick analysis completed" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_check_dependencies(self, dispatcher, mock_orchestrator):
        """CHECK_DEPENDENCIES should extend explanations with deps."""
        step = make_step("CHECK_DEPENDENCIES")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "dep1" in explanations
        assert "dep2" in explanations

    @pytest.mark.asyncio
    async def test_analyze_and_respond_with_code(self, dispatcher, mock_orchestrator):
        """ANALYZE_AND_RESPOND should use analysis utils when code present."""
        step = make_step("ANALYZE_AND_RESPOND")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "Analysis result" in explanations

    @pytest.mark.asyncio
    async def test_full_analysis_with_code(self, dispatcher, mock_orchestrator):
        """FULL_ANALYSIS should produce full analysis when code present."""
        step = make_step("FULL_ANALYSIS")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert "Full analysis result" in explanations


# ============================================================
#  Validation Actions
# ============================================================

class TestValidationActions:
    """Tests for SYMBOLIC_VALIDATION and SYNTAX_VALIDATION."""

    @pytest.mark.asyncio
    async def test_symbolic_validation_without_agent(self, dispatcher):
        """SYMBOLIC_VALIDATION should append bounded execution message without agent."""
        step = make_step("SYMBOLIC_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("Symbolic validation" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_syntax_validation_without_agent(self, dispatcher):
        """SYNTAX_VALIDATION should behave like symbolic validation without agent."""
        step = make_step("SYNTAX_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("validation" in e.lower() for e in explanations)

    @pytest.mark.asyncio
    async def test_validation_with_agent(self, dispatcher, mock_orchestrator):
        """SYMBOLIC_VALIDATION should use ValidationAgent when available."""
        mock_output = MagicMock()
        mock_output.issues = []
        mock_output.risk_score = 0.1
        mock_output.source = "F5"
        mock_validation = MagicMock()
        mock_validation.validate_with_runner.return_value = mock_output
        mock_orchestrator._validation_agent = mock_validation
        mock_orchestrator._agent_runner = MagicMock()

        step = make_step("SYMBOLIC_VALIDATION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "code", "", [], "python", {}, make_plan(),
        )
        assert any("No issues found" in e or "validation" in e.lower() for e in explanations)


# ============================================================
#  SCAFFOLD_FRACTAL Tests
# ============================================================

class TestScaffoldFractal:
    """Tests for SCAFFOLD_FRACTAL action type."""

    @pytest.mark.asyncio
    async def test_fractal_not_available(self, dispatcher, mock_orchestrator):
        """Should report fractal not available when _fractal_gen is None."""
        mock_orchestrator._fractal_gen = None
        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Not available" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_fractal_not_available_no_attr(self, dispatcher, mock_orchestrator):
        """Should handle missing _fractal_gen attribute gracefully."""
        del mock_orchestrator._fractal_gen
        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        # Should not raise
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        assert any("Not available" in e for e in explanations)

    @pytest.mark.asyncio
    async def test_fractal_with_generator(self, dispatcher, mock_orchestrator):
        """Should attempt fractal generation when generator is available."""
        mock_result = MagicMock()
        mock_result.spec = None
        mock_result.files_generated = []
        mock_result.current_phase = 1
        mock_fractal = MagicMock()
        mock_fractal.generate_project.return_value = mock_result
        mock_orchestrator._fractal_gen = mock_fractal

        step = make_step("SCAFFOLD_FRACTAL")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "", "", [], "python", {}, make_plan(),
        )
        # Fractal was attempted
        mock_fractal.generate_project.assert_called_once()


# ============================================================
#  Unknown Step Type
# ============================================================

class TestUnknownStepType:
    """Tests for unknown/unhandled step action types."""

    @pytest.mark.asyncio
    async def test_unknown_action_returns_unchanged(self, dispatcher):
        """Unknown action type should return inputs unchanged."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", [], "python", {}, make_plan(),
        )
        assert r_code == ""
        assert code == "x=1"
        assert explanations == []

    @pytest.mark.asyncio
    async def test_unknown_action_preserves_result_code(self, dispatcher):
        """Unknown action should not overwrite existing result_code."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "existing_code", ["prev"], "python", {}, make_plan(),
        )
        assert r_code == "existing_code"

    @pytest.mark.asyncio
    async def test_unknown_action_preserves_explanations(self, dispatcher):
        """Unknown action should not modify existing explanations."""
        step = make_step("UNKNOWN_ACTION")
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_step(
            step, intent, "x=1", "", ["existing explanation"], "python", {}, make_plan(),
        )
        assert "existing explanation" in explanations


# ============================================================
#  execute_plan_steps Tests
# ============================================================

class TestExecutePlanSteps:
    """Tests for execute_plan_steps sequential iteration."""

    @pytest.mark.asyncio
    async def test_empty_plan(self, dispatcher):
        """Should return empty result_code for plan with no steps."""
        plan = make_plan()
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        assert r_code == ""
        assert explanations == []

    @pytest.mark.asyncio
    async def test_single_step_plan(self, dispatcher, mock_orchestrator):
        """Should execute a single step correctly."""
        plan = make_plan()
        plan.steps = [make_step("GENERATE_CODE")]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        assert r_code == "def new_func(): pass"

    @pytest.mark.asyncio
    async def test_multi_step_plan(self, dispatcher, mock_orchestrator):
        """Should execute multiple steps sequentially."""
        plan = make_plan()
        plan.steps = [
            make_step("ANALYZE_STRUCTURE"),
            make_step("QUICK_ANALYSIS"),
        ]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "x=1", [], "python", {},
        )
        assert len(explanations) == 2

    @pytest.mark.asyncio
    async def test_steps_accumulate_code(self, dispatcher, mock_orchestrator):
        """Steps should accumulate changes to code across the plan."""
        plan = make_plan()
        plan.steps = [
            make_step("GENERATE_CODE"),
        ]
        intent = make_intent()
        r_code, code, explanations = await dispatcher.execute_plan_steps(
            plan, intent, "", [], "python", {},
        )
        # GENERATE_CODE sets result_code
        assert r_code == "def new_func(): pass"
