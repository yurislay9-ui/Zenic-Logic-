"""
Unit tests for CriticalityAgent (F4).

Tests the agent that unifies criticality routing:
  - normalize_criticality() (type mismatch resolution)
  - level_to_path() (DAG path mapping)
  - Keyword signal analysis
  - Operation/Goal baseline signal
  - History signal
  - Confidence computation
  - Fallback multi-signal fusion
  - LLM response parsing
  - assess_deterministic() direct API
  - assess_with_runner() AgentRunner integration
  - Elevation rules (MacroRouter signal)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.criticality_agent import (
    CriticalityAgent,
    LEVEL_FAST,
    LEVEL_MODERATE,
    LEVEL_SURGICAL,
    STR_TO_LEVEL,
    LEVEL_TO_PATH,
    CRITICAL_KEYWORDS,
    MODERATE_KEYWORDS,
    GOAL_CRITICALITY_MAP,
    OP_CRITICALITY_MAP,
    CRITICALITY_ADJUSTMENTS,
)
from src.core.agents.schemas import (
    CriticalityInput,
    CriticalityOutput,
    IntentOutput,
)
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """CriticalityAgent without external dependencies."""
    return CriticalityAgent()


@pytest.fixture
def agent_with_history():
    """CriticalityAgent with pre-populated history."""
    agent = CriticalityAgent()
    agent._history = [
        {"op": "DELETE", "goal": "SECURITY_HARDEN", "target": "auth.py", "level": 3},
        {"op": "CREATE", "goal": "FEATURE_ADD", "target": "utils.py", "level": 1},
        {"op": "REFACTOR", "goal": "BUG_FIX", "target": "auth.py", "level": 3},
    ]
    return agent


# ============================================================
#  Test: Static Utility Methods
# ============================================================

class TestCriticalityStaticMethods:
    """Tests for static utility methods."""

    def test_normalize_none(self):
        """Should return LEVEL_MODERATE for None."""
        assert CriticalityAgent.normalize_criticality(None) == LEVEL_MODERATE

    def test_normalize_int(self):
        """Should pass through valid int values."""
        assert CriticalityAgent.normalize_criticality(1) == 1
        assert CriticalityAgent.normalize_criticality(2) == 2
        assert CriticalityAgent.normalize_criticality(3) == 3

    def test_normalize_int_clamped(self):
        """Should clamp int values to 1-3 range."""
        assert CriticalityAgent.normalize_criticality(0) == 1
        assert CriticalityAgent.normalize_criticality(5) == 3
        assert CriticalityAgent.normalize_criticality(-1) == 1

    def test_normalize_string_standard(self):
        """Should normalize 'standard' to 1."""
        assert CriticalityAgent.normalize_criticality("standard") == 1
        assert CriticalityAgent.normalize_criticality("fast") == 1
        assert CriticalityAgent.normalize_criticality("low") == 1

    def test_normalize_string_moderate(self):
        """Should normalize 'moderate' to 2."""
        assert CriticalityAgent.normalize_criticality("moderate") == 2
        assert CriticalityAgent.normalize_criticality("deep") == 2
        assert CriticalityAgent.normalize_criticality("medium") == 2

    def test_normalize_string_critical(self):
        """Should normalize 'critical' to 3."""
        assert CriticalityAgent.normalize_criticality("critical") == 3
        assert CriticalityAgent.normalize_criticality("surgical") == 3
        assert CriticalityAgent.normalize_criticality("high") == 3

    def test_normalize_canonical_names(self):
        """Should normalize canonical FAST_STANDARD, DEEP_MODERATE, SURGICAL_CRITICAL."""
        assert CriticalityAgent.normalize_criticality("fast_standard") == 1
        assert CriticalityAgent.normalize_criticality("deep_moderate") == 2
        assert CriticalityAgent.normalize_criticality("surgical_critical") == 3

    def test_normalize_string_digit(self):
        """Should normalize string digits."""
        assert CriticalityAgent.normalize_criticality("1") == 1
        assert CriticalityAgent.normalize_criticality("2") == 2
        assert CriticalityAgent.normalize_criticality("3") == 3

    def test_normalize_unknown_defaults_moderate(self):
        """Should default to moderate for unknown values."""
        assert CriticalityAgent.normalize_criticality("unknown") == LEVEL_MODERATE

    def test_level_to_path(self):
        """Should map levels to DAG paths."""
        assert CriticalityAgent.level_to_path(1) == "low_crit"
        assert CriticalityAgent.level_to_path(2) == "standard"
        assert CriticalityAgent.level_to_path(3) == "high_crit"


# ============================================================
#  Test: Keyword Signal
# ============================================================

class TestCriticalityKeywordSignal:
    """Tests for _keyword_signal() analysis."""

    def test_multiple_critical_keywords_surgical(self, agent):
        """Should return SURGICAL for 2+ critical keyword hits."""
        # "auth" and "token" are both in CRITICAL_KEYWORDS
        level = agent._keyword_signal("auth token module")
        assert level == LEVEL_SURGICAL

    def test_single_critical_keyword_moderate(self, agent):
        """Should return MODERATE for 1 critical keyword hit."""
        level = agent._keyword_signal("auth module")
        assert level == LEVEL_MODERATE

    def test_multiple_moderate_keywords_moderate(self, agent):
        """Should return MODERATE for 2+ moderate keyword hits."""
        level = agent._keyword_signal("api endpoint handler")
        assert level == LEVEL_MODERATE

    def test_no_keywords_fast(self, agent):
        """Should return FAST for no keyword hits."""
        level = agent._keyword_signal("simple utility function")
        assert level == LEVEL_FAST


# ============================================================
#  Test: Fallback Multi-Signal Fusion
# ============================================================

class TestCriticalityFallback:
    """Tests for deterministic multi-signal fusion fallback."""

    def test_critical_target_elevates(self, agent):
        """Should elevate criticality for critical targets (auth, payment)."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
            target="auth.py",
            context="implement login",
        ))
        assert result.level >= LEVEL_MODERATE
        assert result.source == "fallback"

    def test_delete_operation_elevates(self, agent):
        """Should elevate criticality for DELETE operations."""
        result = agent.fallback(CriticalityInput(
            operation="DELETE",
            goal="FEATURE_ADD",
            target="user_handler.py",
        ))
        assert result.level >= LEVEL_MODERATE

    def test_safe_search_stays_fast(self, agent):
        """Should stay FAST for safe SEARCH + READABILITY."""
        result = agent.fallback(CriticalityInput(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
        ))
        assert result.level == LEVEL_FAST

    def test_security_harden_elevates(self, agent):
        """Should elevate for SECURITY_HARDEN goal."""
        result = agent.fallback(CriticalityInput(
            operation="REFACTOR",
            goal="SECURITY_HARDEN",
            target="auth.py",
        ))
        # SECURITY_HARDEN has GOAL_CRITICALITY_MAP=3, but fusion may produce 2 or 3
        assert result.level >= LEVEL_MODERATE

    def test_existing_level_not_lowered(self, agent):
        """Should not lower criticality below existing_level."""
        result = agent.fallback(CriticalityInput(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
            existing_level=3,
        ))
        assert result.level >= 3

    def test_result_has_path(self, agent):
        """Should include DAG path in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert result.path in ["low_crit", "standard", "high_crit"]

    def test_result_has_reason(self, agent):
        """Should include explanatory reason in result."""
        result = agent.fallback(CriticalityInput(
            operation="DELETE",
            goal="SECURITY_HARDEN",
        ))
        assert result.reason != ""

    def test_result_has_confidence(self, agent):
        """Should include confidence score in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert 0.0 <= result.confidence <= 1.0

    def test_result_has_adjustments(self, agent):
        """Should include behavioral adjustments in result."""
        result = agent.fallback(CriticalityInput(
            operation="CREATE",
            goal="FEATURE_ADD",
        ))
        assert isinstance(result.adjustments, dict)
        assert "code_agent" in result.adjustments
        assert "business_agent" in result.adjustments


# ============================================================
#  Test: History Signal
# ============================================================

class TestCriticalityHistorySignal:
    """Tests for historical pattern signal."""

    def test_history_elevates_for_matching_target(self, agent_with_history):
        """Should elevate criticality based on history of same target."""
        level = agent_with_history._history_signal("DELETE", "auth.py")
        assert level >= LEVEL_MODERATE

    def test_history_fast_for_new_target(self, agent_with_history):
        """Should return FAST for targets not in history."""
        level = agent_with_history._history_signal("SEARCH", "brand_new.py")
        assert level == LEVEL_FAST

    def test_no_history_returns_fast(self, agent):
        """Should return FAST when no history exists."""
        level = agent._history_signal("CREATE", "test.py")
        assert level == LEVEL_FAST


# ============================================================
#  Test: Confidence Computation
# ============================================================

class TestCriticalityConfidence:
    """Tests for confidence computation."""

    def test_all_signals_agree_high_confidence(self, agent):
        """Should have high confidence when all signals agree."""
        signals = [(3, 0.3), (3, 0.25), (3, 0.2), (3, 0.15), (3, 0.1)]
        confidence = agent._compute_confidence(signals, 3)
        assert confidence >= 0.9

    def test_signals_disagree_lower_confidence(self, agent):
        """Should have lower confidence when signals disagree."""
        signals = [(1, 0.3), (3, 0.25), (2, 0.2), (1, 0.15), (3, 0.1)]
        confidence = agent._compute_confidence(signals, 2)
        assert confidence < 0.9


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestCriticalityLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_with_criticality_input(self, agent):
        """Should build prompt from CriticalityInput."""
        system, user = agent.build_prompt(CriticalityInput(
            operation="DELETE",
            goal="SECURITY_HARDEN",
            target="auth.py",
        ))
        assert "criticality" in system.lower()
        assert "DELETE" in user

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"level":3,"reason":"Auth target detected","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 3
        assert result.path == "high_crit"
        assert result.confidence == 0.9
        assert result.source == "llm"

    def test_parse_response_string_level(self, agent):
        """Should normalize string level in JSON response."""
        raw = '{"level":"critical","reason":"Security","confidence":0.8}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 3

    def test_parse_response_just_number(self, agent):
        """Should parse a bare number response from LLM."""
        raw = "The criticality level is 2 for this operation"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.level == 2

    def test_parse_response_empty(self, agent):
        """Should return None for unparseable response."""
        raw = "xyzzy foo bar baz quux"
        result = agent.parse_response(raw, None)
        assert result is None

    def test_parse_response_level_clamped(self, agent):
        """Should clamp level to 1-3 range."""
        raw = '{"level":5,"reason":"test","confidence":0.5}'
        result = agent.parse_response(raw, None)
        assert result.level == 3


# ============================================================
#  Test: High-Level API
# ============================================================

class TestCriticalityHighLevelAPI:
    """Tests for assess_deterministic and assess_with_runner."""

    def test_assess_deterministic(self, agent):
        """Should assess criticality directly without LLM."""
        result = agent.assess_deterministic(
            operation="DELETE",
            goal="SECURITY_HARDEN",
            target="auth.py",
        )
        assert result.level >= LEVEL_MODERATE
        assert result.source == "fallback"

    def test_assess_deterministic_with_existing(self, agent):
        """Should not lower criticality below existing level."""
        result = agent.assess_deterministic(
            operation="SEARCH",
            goal="READABILITY",
            target="utils.py",
            existing_criticality=3,
        )
        assert result.level >= 3

    def test_assess_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = CriticalityOutput(
            level=3, path="high_crit", reason="Auth detected",
            confidence=0.9, source="llm",
            adjustments=CRITICALITY_ADJUSTMENTS[3],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        intent_output = IntentOutput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        )
        result = agent.assess_with_runner(mock_runner, intent_output)
        assert result.level == 3
        assert result.source == "llm"

    def test_assess_with_runner_failure_falls_back(self, agent):
        """Should fall back when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        intent_output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD", target="utils.py"
        )
        result = agent.assess_with_runner(mock_runner, intent_output)
        assert result.source == "fallback"

    def test_assess_with_runner_elevation(self, agent):
        """Should not let LLM lower criticality below MacroRouter signal."""
        mock_runner = MagicMock()
        llm_output = CriticalityOutput(
            level=1, path="low_crit", reason="Looks safe",
            confidence=0.6, source="llm",
            adjustments=CRITICALITY_ADJUSTMENTS[1],
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        intent_output = IntentOutput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        )
        result = agent.assess_with_runner(
            mock_runner, intent_output, existing_criticality=3
        )
        # Should be elevated to at least 3
        assert result.level >= 3


# ============================================================
#  Test: Constants and Adjustments
# ============================================================

class TestCriticalityConstants:
    """Tests for constants integrity."""

    def test_str_to_level_coverage(self):
        """STR_TO_LEVEL should map all expected strings."""
        assert STR_TO_LEVEL["standard"] == 1
        assert STR_TO_LEVEL["moderate"] == 2
        assert STR_TO_LEVEL["critical"] == 3

    def test_level_to_path_coverage(self):
        """LEVEL_TO_PATH should map all levels."""
        assert LEVEL_TO_PATH[1] == "low_crit"
        assert LEVEL_TO_PATH[2] == "standard"
        assert LEVEL_TO_PATH[3] == "high_crit"

    def test_criticality_adjustments_all_levels(self):
        """CRITICALITY_ADJUSTMENTS should have entries for levels 1, 2, 3."""
        assert 1 in CRITICALITY_ADJUSTMENTS
        assert 2 in CRITICALITY_ADJUSTMENTS
        assert 3 in CRITICALITY_ADJUSTMENTS

    def test_adjustments_code_agent_keys(self):
        """Each level should have code_agent adjustments."""
        for level in [1, 2, 3]:
            assert "code_agent" in CRITICALITY_ADJUSTMENTS[level]

    def test_adjustments_business_agent_keys(self):
        """Each level should have business_agent adjustments."""
        for level in [1, 2, 3]:
            assert "business_agent" in CRITICALITY_ADJUSTMENTS[level]

    def test_goal_criticality_map_security(self):
        """SECURITY_HARDEN should map to level 3."""
        assert GOAL_CRITICALITY_MAP["SECURITY_HARDEN"] == 3

    def test_op_criticality_map_delete(self):
        """DELETE should map to level 3."""
        assert OP_CRITICALITY_MAP["DELETE"] == 3


# ============================================================
#  Test: Wire and History Recording
# ============================================================

class TestCriticalityWireAndHistory:
    """Tests for wire() and history recording."""

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

    def test_wire_macro_router(self, agent):
        """Should update macro router reference via wire()."""
        mock_router = MagicMock()
        agent.wire(macro_router=mock_router)
        assert agent._macro_router is mock_router

    def test_history_recording(self, agent):
        """Should record history after fallback evaluation."""
        agent.fallback(CriticalityInput(
            operation="DELETE", goal="SECURITY_HARDEN", target="auth.py"
        ))
        assert len(agent._history) == 1
        assert agent._history[0]["op"] == "DELETE"

    def test_history_max_size(self, agent):
        """Should not exceed _history_max entries."""
        agent._history_max = 3
        for i in range(5):
            agent.fallback(CriticalityInput(
                operation="CREATE", goal="FEATURE_ADD", target=f"file_{i}.py"
            ))
        assert len(agent._history) <= 3
