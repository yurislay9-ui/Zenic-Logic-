"""
Unit tests for IntentAgent (Phase F2)

Tests the unified intent classification agent that replaces
SemanticParser + SemanticEngine + MiniAIEngine classify_intent.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.intent_agent import IntentAgent, VALID_OPERATIONS, VALID_GOALS
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """IntentAgent without external dependencies (pure fallback mode)."""
    return IntentAgent()


@pytest.fixture
def agent_with_semantic():
    """IntentAgent with mocked SemanticEngine."""
    agent = IntentAgent()
    mock_semantic = MagicMock()
    mock_semantic.is_loaded = True
    mock_semantic.classify_intent.return_value = MagicMock(
        operation="CREATE",
        goal="FEATURE_ADD",
        confidence=0.85,
        source="embedding",
    )
    agent.wire(semantic_engine=mock_semantic)
    return agent, mock_semantic


@pytest.fixture
def agent_with_memory():
    """IntentAgent with mocked SmartMemory."""
    agent = IntentAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


# ============================================================
#  Test: Fallback Classification (TF-IDF + regex)
# ============================================================

class TestIntentAgentFallback:
    """Tests for deterministic fallback classification."""

    def test_create_operation_es(self, agent):
        """Should detect CREATE from Spanish messages."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"
        assert result.source == "fallback"

    def test_create_operation_en(self, agent):
        """Should detect CREATE from English messages."""
        result = agent.fallback(IntentInput(message="create new feature"))
        assert result.operation == "CREATE"

    def test_delete_operation_es(self, agent):
        """Should detect DELETE from Spanish messages."""
        result = agent.fallback(IntentInput(message="eliminar funcion process_data"))
        assert result.operation == "DELETE"

    def test_delete_operation_en(self, agent):
        """Should detect DELETE from English messages."""
        result = agent.fallback(IntentInput(message="delete unused code"))
        assert result.operation == "DELETE"

    def test_refactor_operation_es(self, agent):
        """Should detect REFACTOR from Spanish messages."""
        result = agent.fallback(IntentInput(message="refactorizar clase UserManager"))
        assert result.operation == "REFACTOR"

    def test_refactor_operation_en(self, agent):
        """Should detect REFACTOR from English messages."""
        result = agent.fallback(IntentInput(message="refactor the authentication module"))
        assert result.operation == "REFACTOR"

    def test_analyze_operation_es(self, agent):
        """Should detect ANALYZE from Spanish messages."""
        result = agent.fallback(IntentInput(message="analizar codigo"))
        assert result.operation == "ANALYZE"

    def test_analyze_operation_en(self, agent):
        """Should detect ANALYZE from English messages."""
        result = agent.fallback(IntentInput(message="analyze the code quality"))
        assert result.operation == "ANALYZE"

    def test_explain_operation_es(self, agent):
        """Should detect EXPLAIN from Spanish messages."""
        result = agent.fallback(IntentInput(message="explicar que hace esta funcion"))
        assert result.operation == "EXPLAIN"

    def test_explain_operation_en(self, agent):
        """Should detect EXPLAIN from English messages."""
        result = agent.fallback(IntentInput(message="explain how this code works"))
        assert result.operation == "EXPLAIN"

    def test_debug_operation_es(self, agent):
        """Should detect DEBUG from Spanish messages."""
        result = agent.fallback(IntentInput(message="debug error en login"))
        assert result.operation == "DEBUG"

    def test_debug_operation_en(self, agent):
        """Should detect DEBUG from English messages."""
        result = agent.fallback(IntentInput(message="fix the bug in payment"))
        assert result.operation == "DEBUG"

    def test_optimize_operation_es(self, agent):
        """Should detect OPTIMIZE from Spanish messages."""
        result = agent.fallback(IntentInput(message="optimizar rendimiento de query"))
        assert result.operation == "OPTIMIZE"

    def test_optimize_operation_en(self, agent):
        """Should detect OPTIMIZE from English messages."""
        result = agent.fallback(IntentInput(message="optimize performance of the module"))
        assert result.operation == "OPTIMIZE"

    def test_search_operation_es(self, agent):
        """Should detect SEARCH from Spanish messages."""
        result = agent.fallback(IntentInput(message="buscar definicion de clase"))
        assert result.operation == "SEARCH"

    def test_search_operation_en(self, agent):
        """Should detect SEARCH from English messages."""
        result = agent.fallback(IntentInput(message="find where this function is used"))
        assert result.operation == "SEARCH"


# ============================================================
#  Test: Goal Classification
# ============================================================

class TestIntentAgentGoalClassification:
    """Tests for goal classification in fallback mode."""

    def test_bug_fix_goal(self, agent):
        """Should classify bug fix goals."""
        result = agent.fallback(IntentInput(message="corregir error en login"))
        assert result.goal == "BUG_FIX"

    def test_feature_add_goal(self, agent):
        """Should classify feature add goals."""
        result = agent.fallback(IntentInput(message="agregar nueva funcionalidad"))
        assert result.goal == "FEATURE_ADD"

    def test_security_harden_goal(self, agent):
        """Should classify security hardening goals."""
        result = agent.fallback(IntentInput(message="mejorar seguridad de auth"))
        assert result.goal == "SECURITY_HARDEN"

    def test_performance_goal(self, agent):
        """Should classify performance goals."""
        result = agent.fallback(IntentInput(message="optimizar velocidad"))
        assert result.goal == "PERFORMANCE"


# ============================================================
#  Test: Target and Language Extraction
# ============================================================

class TestIntentAgentExtraction:
    """Tests for target, language, and entity extraction."""

    def test_target_extraction_file(self, agent):
        """Should extract file targets from messages."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert "auth" in result.target.lower()

    def test_target_extraction_kotlin(self, agent):
        """Should extract Kotlin file targets."""
        result = agent.fallback(IntentInput(message="refactorizar archivo UserService.kt"))
        assert result.language == "kotlin"

    def test_target_extraction_javascript(self, agent):
        """Should extract JavaScript file targets."""
        result = agent.fallback(IntentInput(message="analizar codigo en app.js"))
        assert result.language == "javascript"

    def test_target_extraction_typescript(self, agent):
        """Should extract TypeScript file targets."""
        result = agent.fallback(IntentInput(message="revisar modulo api.ts"))
        assert result.language == "typescript"

    def test_code_block_extraction(self, agent):
        """Should extract code from markdown blocks."""
        code = "def hello():\n    print('hello')"
        result = agent.fallback(IntentInput(
            message=f"analizar ```python\n{code}\n```"
        ))
        assert result.language == "python"

    def test_default_language(self, agent):
        """Should default to python when no language detected."""
        result = agent.fallback(IntentInput(message="hacer algo"))
        assert result.language in ["python", ""]

    def test_entities_extraction_function(self, agent):
        """Should extract function entities."""
        result = agent.fallback(IntentInput(message="def process_data(): crear funcion"))
        assert result.entities.get("function") == "process_data"

    def test_entities_extraction_class(self, agent):
        """Should extract class entities."""
        result = agent.fallback(IntentInput(message="class UserManager: refactorizar"))
        assert result.entities.get("class") == "UserManager"


# ============================================================
#  Test: Criticality Inference
# ============================================================

class TestIntentAgentCriticality:
    """Tests for criticality inference."""

    def test_critical_auth(self, agent):
        """Should detect critical for auth-related requests."""
        result = agent.fallback(IntentInput(message="corregir error en login auth"))
        assert result.criticality == "critical"

    def test_critical_crypto(self, agent):
        """Should detect critical for crypto-related requests."""
        result = agent.fallback(IntentInput(message="mejorar seguridad crypto"))
        assert result.criticality == "critical"

    def test_moderate_database(self, agent):
        """Should detect moderate for database-related requests."""
        result = agent.fallback(IntentInput(message="crear modulo database"))
        assert result.criticality == "moderate"

    def test_standard(self, agent):
        """Should default to standard for normal requests."""
        result = agent.fallback(IntentInput(message="crear nueva funcion"))
        assert result.criticality == "standard"


# ============================================================
#  Test: IntentOutput → IntentPayload Conversion
# ============================================================

class TestIntentAgentConversion:
    """Tests for IntentOutput to IntentPayload conversion (pipeline compat)."""

    def test_to_intent_payload_basic(self, agent):
        """Should convert IntentOutput to IntentPayload correctly."""
        output = IntentOutput(
            operation="CREATE",
            goal="FEATURE_ADD",
            target="auth.py",
            language="python",
            confidence=0.8,
            source="llm",
        )
        payload = agent.to_intent_payload(output, context="crear modulo auth.py")

        assert payload.op == "CREATE"
        assert payload.goal == "FEATURE_ADD"
        assert payload.target == "auth.py"
        assert payload.confidence == 0.8
        assert payload.language == "python"
        assert payload.context == "crear modulo auth.py"

    def test_to_intent_payload_invalid_operation(self, agent):
        """Should default to SEARCH for invalid operations."""
        output = IntentOutput(operation="INVALID", goal="FEATURE_ADD")
        payload = agent.to_intent_payload(output)
        assert payload.op == "SEARCH"

    def test_to_intent_payload_scrap_query(self, agent):
        """Should generate scrap_query for CREATE/OPTIMIZE/REFACTOR."""
        output = IntentOutput(operation="CREATE", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query != ""

    def test_to_intent_payload_no_scrap_query_for_search(self, agent):
        """Should not generate scrap_query for SEARCH/EXPLAIN/ANALYZE."""
        output = IntentOutput(operation="SEARCH", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query == ""


# ============================================================
#  Test: build_prompt + parse_response (LLM path)
# ============================================================

class TestIntentAgentLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_with_intent_input(self, agent):
        """Should build system + user prompt from IntentInput."""
        system, user = agent.build_prompt(IntentInput(
            message="crear modulo auth.py", context="previous conversation"
        ))
        assert "intent classification" in system.lower()
        assert "crear modulo auth.py" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("fix bug in login")
        assert "intent classification" in system.lower()
        assert "fix bug in login" in user

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"operation":"CREATE","goal":"FEATURE_ADD","target":"auth.py","language":"python","entities":{},"template_type":"api","criticality":"standard","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.goal == "FEATURE_ADD"
        assert result.target == "auth.py"
        assert result.confidence == 0.9
        assert result.source == "llm"

    def test_parse_response_markdown_json(self, agent):
        """Should parse JSON from markdown code block."""
        raw = '```json\n{"operation":"DEBUG","goal":"BUG_FIX","target":"login.py","language":"python","confidence":0.75}\n```'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "DEBUG"
        assert result.goal == "BUG_FIX"

    def test_parse_response_invalid_operation(self, agent):
        """Should default invalid operations to SEARCH."""
        raw = '{"operation":"INVALID_OP","goal":"FEATURE_ADD","confidence":0.5}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "SEARCH"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "The operation is CREATE and the goal is FEATURE_ADD"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.goal == "FEATURE_ADD"

    def test_parse_response_empty(self, agent):
        """Should handle empty or unparseable response."""
        raw = "xyzzy foo bar baz"
        result = agent.parse_response(raw, None)
        # Free text fallback should still return something
        assert result is not None


# ============================================================
#  Test: SemanticEngine Integration
# ============================================================

class TestIntentAgentSemanticEngine:
    """Tests for SemanticEngine integration in fallback path."""

    def test_semantic_engine_classification(self, agent_with_semantic):
        """Should use SemanticEngine when available and confident."""
        agent, mock_semantic = agent_with_semantic
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.confidence > 0.3

    def test_semantic_engine_low_confidence_falls_to_tfidf(self, agent_with_semantic):
        """Should fall back to TF-IDF when SemanticEngine has low confidence."""
        agent, mock_semantic = agent_with_semantic
        mock_semantic.classify_intent.return_value = MagicMock(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,  # Too low
            source="embedding",
        )
        result = agent.fallback(IntentInput(message="crear modulo"))
        # Should still classify, but may differ from SemanticEngine
        assert result.operation in VALID_OPERATIONS

    def test_semantic_engine_unavailable(self, agent):
        """Should use TF-IDF when SemanticEngine is not loaded."""
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = False
        agent.wire(semantic_engine=mock_semantic)
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.source == "fallback"


# ============================================================
#  Test: SmartMemory Integration
# ============================================================

class TestIntentAgentSmartMemory:
    """Tests for SmartMemory cache integration."""

    def test_smart_memory_cache_hit(self, agent_with_memory):
        """Should return cached result from SmartMemory."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "operation": "CREATE",
            "goal": "FEATURE_ADD",
            "target": "auth.py",
            "language": "python",
            "importance": 0.8,
        }
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.source == "fallback"  # SmartMemory is part of fallback

    def test_smart_memory_save_on_result(self, agent_with_memory):
        """Should save classification result to SmartMemory."""
        agent, mock_memory = agent_with_memory
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        # SmartMemory.save_to_cache should have been called
        assert mock_memory.save_to_cache.called

    def test_smart_memory_failure_graceful(self, agent):
        """Should handle SmartMemory failures gracefully."""
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        # Should not raise, should fall through to TF-IDF
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: classify_with_runner (full AgentRunner integration)
# ============================================================

class TestIntentAgentWithRunner:
    """Tests for classify_with_runner using AgentRunner."""

    def test_runner_llm_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            target="auth.py", confidence=0.9, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"
        assert result.source == "llm"

    def test_runner_failure_uses_fallback(self, agent):
        """Should use fallback when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error", error="LLM timeout"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"
        assert result.source == "fallback"


# ============================================================
#  Test: Edge Cases
# ============================================================

class TestIntentAgentEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_message(self, agent):
        """Should handle empty messages gracefully."""
        result = agent.fallback(IntentInput(message=""))
        assert result is not None
        assert result.operation in VALID_OPERATIONS

    def test_very_long_message(self, agent):
        """Should handle very long messages without crashing."""
        long_msg = "crear " + "modulo " * 500
        result = agent.fallback(IntentInput(message=long_msg))
        assert result is not None

    def test_special_characters(self, agent):
        """Should handle special characters in messages."""
        result = agent.fallback(IntentInput(message="crear módulo auth.py con ñ y áéíóú"))
        assert result is not None

    def test_message_with_only_code(self, agent):
        """Should handle messages that are mostly code."""
        result = agent.fallback(IntentInput(
            message="def process_data(data):\n    return data.filter(lambda x: x > 0)"
        ))
        assert result is not None

    def test_confidence_always_in_range(self, agent):
        """Confidence should always be between 0 and 1."""
        for msg in ["crear", "debug error", "fix bug", "hello world", ""]:
            result = agent.fallback(IntentInput(message=msg))
            assert 0.0 <= result.confidence <= 1.0

    def test_fallback_confidence_is_low(self, agent):
        """Fallback confidence should be in the 0-0.5 range."""
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.confidence <= 0.5

    def test_multiple_operations_in_message(self, agent):
        """Should pick the best matching operation when multiple match."""
        result = agent.fallback(IntentInput(message="debug y crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: Stats Tracking
# ============================================================

class TestIntentAgentStats:
    """Tests for agent statistics tracking."""

    def test_initial_stats(self, agent):
        """Should have zero stats initially."""
        stats = agent.stats
        assert stats["name"] == "intent"
        assert stats["total_calls"] == 0

    def test_stats_after_fallback(self, agent):
        """Should track fallback calls."""
        agent.fallback(IntentInput(message="crear modulo"))
        stats = agent.stats
        assert stats["total_calls"] >= 1

    def test_wire_updates_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        agent.wire(semantic_engine=mock_semantic)
        assert agent._semantic_engine is mock_semantic

    def test_wire_updates_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_memory = MagicMock()
        agent.wire(smart_memory=mock_memory)
        assert agent._smart_memory is mock_memory
