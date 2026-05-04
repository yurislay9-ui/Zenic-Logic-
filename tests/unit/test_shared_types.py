"""
Unit tests for src/core/shared/types.py - Data Types & Payloads

Tests:
- OperationType constants
- GoalType constants
- CriticalityLevel constants
- RoutePath constants
- IntentPayload construction and defaults
- RoutingPayload construction and defaults
- PlanStep construction and defaults
- ExecutionPlan construction and defaults
- SandboxResult construction and defaults
- MerkleNode construction and defaults
- ChatMessage and ChatRequest construction
- criticality_to_int conversion
- criticality_to_path conversion
- criticality_to_str conversion
- CRITICALITY_* mapping completeness
- __all__ completeness
"""

import pytest

from src.core.shared.types import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
    IntentPayload, RoutingPayload, PlanStep, ExecutionPlan,
    SandboxResult, MerkleNode, ChatMessage, ChatRequest,
    criticality_to_int, criticality_to_path, criticality_to_str,
    CRITICALITY_INT_TO_STR, CRITICALITY_STR_TO_INT,
    CRITICALITY_INT_TO_PATH, CRITICALITY_PATH_TO_INT,
)


# ===========================================================================
#  Test: OperationType
# ===========================================================================

class TestOperationType:
    """Tests for OperationType constants."""

    def test_create_constant(self):
        assert OperationType.CREATE == "CREATE"

    def test_refactor_constant(self):
        assert OperationType.REFACTOR == "REFACTOR"

    def test_delete_constant(self):
        assert OperationType.DELETE == "DELETE"

    def test_search_constant(self):
        assert OperationType.SEARCH == "SEARCH"

    def test_analyze_constant(self):
        assert OperationType.ANALYZE == "ANALYZE"

    def test_explain_constant(self):
        assert OperationType.EXPLAIN == "EXPLAIN"

    def test_debug_constant(self):
        assert OperationType.DEBUG == "DEBUG"

    def test_optimize_constant(self):
        assert OperationType.OPTIMIZE == "OPTIMIZE"

    def test_all_operations_are_strings(self):
        """All operation constants should be strings."""
        ops = [OperationType.CREATE, OperationType.REFACTOR, OperationType.DELETE,
               OperationType.SEARCH, OperationType.ANALYZE, OperationType.EXPLAIN,
               OperationType.DEBUG, OperationType.OPTIMIZE]
        assert all(isinstance(op, str) for op in ops)


# ===========================================================================
#  Test: GoalType
# ===========================================================================

class TestGoalType:
    """Tests for GoalType constants."""

    def test_complexity_reduction(self):
        assert GoalType.COMPLEXITY_REDUCTION == "COMPLEXITY_REDUCTION"

    def test_modern_pattern(self):
        assert GoalType.MODERN_PATTERN == "MODERN_PATTERN"

    def test_bug_fix(self):
        assert GoalType.BUG_FIX == "BUG_FIX"

    def test_feature_add(self):
        assert GoalType.FEATURE_ADD == "FEATURE_ADD"

    def test_security_harden(self):
        assert GoalType.SECURITY_HARDEN == "SECURITY_HARDEN"

    def test_performance(self):
        assert GoalType.PERFORMANCE == "PERFORMANCE"

    def test_readability(self):
        assert GoalType.READABILITY == "READABILITY"


# ===========================================================================
#  Test: CriticalityLevel
# ===========================================================================

class TestCriticalityLevel:
    """Tests for CriticalityLevel constants."""

    def test_fast_standard_is_1(self):
        assert CriticalityLevel.FAST_STANDARD == 1

    def test_deep_moderate_is_2(self):
        assert CriticalityLevel.DEEP_MODERATE == 2

    def test_surgical_critical_is_3(self):
        assert CriticalityLevel.SURGICAL_CRITICAL == 3

    def test_levels_are_ordered(self):
        """Criticality levels should be ordered 1 < 2 < 3."""
        assert CriticalityLevel.FAST_STANDARD < CriticalityLevel.DEEP_MODERATE
        assert CriticalityLevel.DEEP_MODERATE < CriticalityLevel.SURGICAL_CRITICAL


# ===========================================================================
#  Test: RoutePath
# ===========================================================================

class TestRoutePath:
    """Tests for RoutePath constants."""

    def test_fast_path(self):
        assert RoutePath.FAST_PATH == "FAST_PATH_REGEX"

    def test_deep_path(self):
        assert RoutePath.DEEP_PATH == "DEEP_PATH_CONSTRAINT"

    def test_surgical_path(self):
        assert RoutePath.SURGICAL_PATH == "SURGICAL_PATH_FULL"

    def test_paths_are_strings(self):
        """All route path constants should be strings."""
        paths = [RoutePath.FAST_PATH, RoutePath.DEEP_PATH, RoutePath.SURGICAL_PATH]
        assert all(isinstance(p, str) for p in paths)


# ===========================================================================
#  Test: IntentPayload
# ===========================================================================

class TestIntentPayload:
    """Tests for IntentPayload data class."""

    def test_default_values(self):
        """Default values should match OperationType.SEARCH, etc."""
        payload = IntentPayload()
        assert payload.op == OperationType.SEARCH
        assert payload.target == "unknown"
        assert payload.goal == GoalType.FEATURE_ADD
        assert payload.scrap_query == ""
        assert payload.confidence == 0.0
        assert payload.language == "python"
        assert payload.raw_code == ""
        assert payload.context == ""

    def test_custom_values(self):
        """Should accept custom values."""
        payload = IntentPayload(
            op="CREATE", target="auth.py", goal="BUG_FIX",
            scrap_query="test", confidence=0.9,
            language="go", raw_code="func main(){}",
            context="debug"
        )
        assert payload.op == "CREATE"
        assert payload.target == "auth.py"
        assert payload.goal == "BUG_FIX"
        assert payload.confidence == 0.9
        assert payload.language == "go"

    def test_attributes_mutable(self):
        """IntentPayload attributes should be mutable."""
        payload = IntentPayload()
        payload.op = "DEBUG"
        assert payload.op == "DEBUG"


# ===========================================================================
#  Test: RoutingPayload
# ===========================================================================

class TestRoutingPayload:
    """Tests for RoutingPayload data class."""

    def test_default_values(self):
        """Default values should match CriticalityLevel.FAST_STANDARD."""
        payload = RoutingPayload()
        assert payload.criticality == CriticalityLevel.FAST_STANDARD
        assert payload.route == RoutePath.FAST_PATH
        assert payload.reason == ""
        assert isinstance(payload.intent, IntentPayload)

    def test_custom_intent(self):
        """Should accept a custom IntentPayload."""
        intent = IntentPayload(op="DEBUG")
        payload = RoutingPayload(intent=intent, criticality=3, route="SURGICAL")
        assert payload.intent.op == "DEBUG"
        assert payload.criticality == 3

    def test_reason_field(self):
        """Reason field should be settable."""
        payload = RoutingPayload(reason="High complexity")
        assert payload.reason == "High complexity"


# ===========================================================================
#  Test: PlanStep
# ===========================================================================

class TestPlanStep:
    """Tests for PlanStep data class."""

    def test_default_values(self):
        payload = PlanStep()
        assert payload.step_id == 0
        assert payload.action == "ANALYZE_CODE"
        assert payload.target_node_name == ""
        assert payload.source == "LOCAL_GRAPH"
        assert payload.constraints == {}

    def test_custom_values(self):
        payload = PlanStep(step_id=5, action="REPLACE_NODE",
                           target_node_name="auth.py:login",
                           source="REMOTE_GRAPH",
                           constraints={"max_complexity": 10})
        assert payload.step_id == 5
        assert payload.action == "REPLACE_NODE"
        assert payload.constraints == {"max_complexity": 10}

    def test_constraints_default_empty_dict(self):
        """Each PlanStep should have its own constraints dict."""
        p1 = PlanStep()
        p2 = PlanStep()
        p1.constraints["key"] = "val"
        assert "key" not in p2.constraints


# ===========================================================================
#  Test: ExecutionPlan
# ===========================================================================

class TestExecutionPlan:
    """Tests for ExecutionPlan data class."""

    def test_default_values(self):
        plan = ExecutionPlan()
        assert plan.plan_id == ""
        assert plan.steps == []
        assert plan.solver_status == "HEURISTIC_FALLBACK"
        assert plan.solver_proof is None
        assert plan.mcts_simulations == 0
        assert plan.mcts_depth_reached == 0

    def test_custom_values(self):
        steps = [PlanStep(step_id=1), PlanStep(step_id=2)]
        plan = ExecutionPlan(plan_id="p1", steps=steps,
                             solver_status="SAT", solver_proof="proof",
                             mcts_simulations=50, mcts_depth_reached=3)
        assert len(plan.steps) == 2
        assert plan.solver_status == "SAT"
        assert plan.mcts_simulations == 50


# ===========================================================================
#  Test: SandboxResult
# ===========================================================================

class TestSandboxResult:
    """Tests for SandboxResult data class."""

    def test_default_values(self):
        result = SandboxResult()
        assert result.status == "PASS"
        assert result.error_message == ""
        assert result.error_node is None
        assert result.warnings == []
        assert result.metrics == {}
        assert result.paths_explored == 0
        assert result.paths_pruned == 0

    def test_failure_result(self):
        result = SandboxResult(status="FAIL_SYNTAX", error_message="SyntaxError",
                               error_node="line 5", warnings=["deprecated"])
        assert result.status == "FAIL_SYNTAX"
        assert result.error_message == "SyntaxError"


# ===========================================================================
#  Test: MerkleNode
# ===========================================================================

class TestMerkleNode:
    """Tests for MerkleNode data class."""

    def test_default_values(self):
        node = MerkleNode()
        assert node.file_path == ""
        assert node.hash_sha256 == ""
        assert node.parent_hash == ""
        assert node.timestamp == 0
        assert node.operation == ""

    def test_custom_values(self):
        node = MerkleNode(file_path="/app/main.py", hash_sha256="abc123",
                          parent_hash="def456", timestamp=1700000000,
                          operation="CREATE")
        assert node.file_path == "/app/main.py"
        assert node.hash_sha256 == "abc123"


# ===========================================================================
#  Test: ChatMessage and ChatRequest
# ===========================================================================

class TestChatTypes:
    """Tests for ChatMessage and ChatRequest."""

    def test_chat_message_defaults(self):
        msg = ChatMessage()
        assert msg.role == "user"
        assert msg.content == ""

    def test_chat_message_custom(self):
        msg = ChatMessage(role="assistant", content="Hello!")
        assert msg.role == "assistant"
        assert msg.content == "Hello!"

    def test_chat_request_defaults(self):
        req = ChatRequest()
        assert req.model == "titan-omniscale-x"
        assert req.messages == []
        assert req.temperature == 0.1
        assert req.max_tokens == 2000
        assert req.stream is False

    def test_chat_request_with_messages(self):
        msgs = [ChatMessage(role="user", content="hi")]
        req = ChatRequest(messages=msgs, temperature=0.7, max_tokens=500, stream=True)
        assert len(req.messages) == 1
        assert req.temperature == 0.7
        assert req.max_tokens == 500
        assert req.stream is True


# ===========================================================================
#  Test: criticality_to_int conversion
# ===========================================================================

class TestCriticalityToInt:
    """Tests for criticality_to_int conversion function."""

    def test_int_passthrough(self):
        """Integer values should be clamped to 1-3 range."""
        assert criticality_to_int(1) == 1
        assert criticality_to_int(2) == 2
        assert criticality_to_int(3) == 3

    def test_int_clamping_low(self):
        """Values below 1 should be clamped to 1."""
        assert criticality_to_int(0) == 1
        assert criticality_to_int(-5) == 1

    def test_int_clamping_high(self):
        """Values above 3 should be clamped to 3."""
        assert criticality_to_int(10) == 3
        assert criticality_to_int(100) == 3

    def test_str_standard(self):
        assert criticality_to_int("standard") == 1

    def test_str_moderate(self):
        assert criticality_to_int("moderate") == 2

    def test_str_critical(self):
        assert criticality_to_int("critical") == 3

    def test_path_str_low_crit(self):
        assert criticality_to_int("low_crit") == 1

    def test_path_str_standard(self):
        assert criticality_to_int("standard") == 1  # also in CRITICALITY_STR_TO_INT

    def test_path_str_high_crit(self):
        assert criticality_to_int("high_crit") == 3

    def test_unknown_defaults_to_2(self):
        """Unknown values should default to DEEP_MODERATE (2)."""
        assert criticality_to_int("unknown_value") == 2
        assert criticality_to_int(None) == 2
        assert criticality_to_int(3.14) == 2  # float is not int, not str


# ===========================================================================
#  Test: criticality_to_path conversion
# ===========================================================================

class TestCriticalityToPath:
    """Tests for criticality_to_path conversion function."""

    def test_int_1_to_low_crit(self):
        assert criticality_to_path(1) == "low_crit"

    def test_int_2_to_standard(self):
        assert criticality_to_path(2) == "standard"

    def test_int_3_to_high_crit(self):
        assert criticality_to_path(3) == "high_crit"

    def test_str_to_path(self):
        assert criticality_to_path("critical") == "high_crit"
        assert criticality_to_path("standard") == "low_crit"

    def test_unknown_defaults_to_standard(self):
        assert criticality_to_path("unknown") == "standard"


# ===========================================================================
#  Test: criticality_to_str conversion
# ===========================================================================

class TestCriticalityToStr:
    """Tests for criticality_to_str conversion function."""

    def test_int_1_to_standard(self):
        assert criticality_to_str(1) == "standard"

    def test_int_2_to_moderate(self):
        assert criticality_to_str(2) == "moderate"

    def test_int_3_to_critical(self):
        assert criticality_to_str(3) == "critical"

    def test_path_to_str(self):
        assert criticality_to_str("high_crit") == "critical"

    def test_unknown_defaults_to_moderate(self):
        assert criticality_to_str("unknown") == "moderate"


# ===========================================================================
#  Test: CRITICALITY mapping dictionaries
# ===========================================================================

class TestCriticalityMappings:
    """Tests for CRITICALITY_* mapping dictionaries."""

    def test_int_to_str_completeness(self):
        assert CRITICALITY_INT_TO_STR == {1: "standard", 2: "moderate", 3: "critical"}

    def test_str_to_int_is_inverse(self):
        """CRITICALITY_STR_TO_INT should be the inverse of INT_TO_STR."""
        for k, v in CRITICALITY_INT_TO_STR.items():
            assert CRITICALITY_STR_TO_INT[v] == k

    def test_int_to_path_completeness(self):
        assert CRITICALITY_INT_TO_PATH == {1: "low_crit", 2: "standard", 3: "high_crit"}

    def test_path_to_int_is_inverse(self):
        """CRITICALITY_PATH_TO_INT should be the inverse of INT_TO_PATH."""
        for k, v in CRITICALITY_INT_TO_PATH.items():
            assert CRITICALITY_PATH_TO_INT[v] == k

    def test_all_mappings_have_3_entries(self):
        """All mappings should have exactly 3 entries."""
        assert len(CRITICALITY_INT_TO_STR) == 3
        assert len(CRITICALITY_STR_TO_INT) == 3
        assert len(CRITICALITY_INT_TO_PATH) == 3
        assert len(CRITICALITY_PATH_TO_INT) == 3


# ===========================================================================
#  Test: __all__ completeness
# ===========================================================================

class TestAllCompleteness:
    """Tests that __all__ covers all public names."""

    def test_all_names_importable(self):
        """Every name in __all__ should be accessible."""
        from src.core.shared import types as types_mod
        for name in types_mod.__all__:
            assert hasattr(types_mod, name), f"{name} not accessible in types"

    def test_all_covers_core_classes(self):
        """__all__ should include all core classes."""
        from src.core.shared.types import __all__ as all_names
        expected = {"OperationType", "GoalType", "CriticalityLevel", "RoutePath",
                    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
                    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest"}
        assert expected.issubset(set(all_names)), f"Missing: {expected - set(all_names)}"

    def test_all_covers_conversion_utils(self):
        """__all__ should include conversion functions and mappings."""
        from src.core.shared.types import __all__ as all_names
        expected = {"criticality_to_int", "criticality_to_path", "criticality_to_str",
                    "CRITICALITY_INT_TO_STR", "CRITICALITY_STR_TO_INT",
                    "CRITICALITY_INT_TO_PATH", "CRITICALITY_PATH_TO_INT"}
        assert expected.issubset(set(all_names)), f"Missing: {expected - set(all_names)}"
