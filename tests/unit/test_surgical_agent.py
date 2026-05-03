"""
Unit tests for SurgicalAgent (Phase F2)

Tests the surgical intent classification agent that replaces
IntentAgent + SemanticParser + SemanticEngine + MiniAI classify_intent.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.agents.surgical_agent import SurgicalAgent, VALID_OPERATIONS, VALID_GOALS
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """SurgicalAgent without external dependencies (pure fallback mode)."""
    return SurgicalAgent()


@pytest.fixture
def agent_with_semantic():
    """SurgicalAgent with mocked SemanticEngine."""
    agent = SurgicalAgent()
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
    """SurgicalAgent with mocked SmartMemory."""
    agent = SurgicalAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


@pytest.fixture
def agent_full():
    """SurgicalAgent with both SemanticEngine and SmartMemory."""
    agent = SurgicalAgent()
    mock_semantic = MagicMock()
    mock_semantic.is_loaded = True
    mock_semantic.classify_intent.return_value = MagicMock(
        operation="CREATE", goal="FEATURE_ADD",
        confidence=0.85, source="embedding",
    )
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(semantic_engine=mock_semantic, smart_memory=mock_memory)
    return agent, mock_semantic, mock_memory


# ============================================================
#  Test: Fallback Classification (TF-IDF + regex)
# ============================================================

class TestSurgicalAgentFallback:
    """Tests for deterministic fallback classification."""

    def test_create_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"
        assert result.source == "tfidf"

    def test_create_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="create new feature"))
        assert result.operation == "CREATE"

    def test_delete_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="eliminar funcion process_data"))
        assert result.operation == "DELETE"

    def test_debug_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="debug error en login"))
        assert result.operation == "DEBUG"

    def test_debug_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="fix the bug in payment"))
        assert result.operation == "DEBUG"

    def test_optimize_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="optimizar rendimiento"))
        assert result.operation == "OPTIMIZE"

    def test_search_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="buscar definicion de clase"))
        assert result.operation == "SEARCH"

    def test_refactor_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="refactor the auth module"))
        assert result.operation == "REFACTOR"

    def test_analyze_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="analyze the code quality"))
        assert result.operation == "ANALYZE"

    def test_explain_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="explain how this code works"))
        assert result.operation == "EXPLAIN"


# ============================================================
#  Test: Goal Classification
# ============================================================

class TestSurgicalAgentGoalClassification:
    """Tests for goal classification in fallback mode."""

    def test_bug_fix_goal(self, agent):
        result = agent.fallback(IntentInput(message="corregir error en login"))
        assert result.goal == "BUG_FIX"

    def test_feature_add_goal(self, agent):
        result = agent.fallback(IntentInput(message="agregar nueva funcionalidad"))
        assert result.goal == "FEATURE_ADD"

    def test_security_harden_goal(self, agent):
        result = agent.fallback(IntentInput(message="mejorar seguridad auth"))
        assert result.goal == "SECURITY_HARDEN"

    def test_performance_goal(self, agent):
        result = agent.fallback(IntentInput(message="optimizar velocidad"))
        assert result.goal == "PERFORMANCE"


# ============================================================
#  Test: Target and Language Extraction
# ============================================================

class TestSurgicalAgentExtraction:
    """Tests for target, language, and entity extraction."""

    def test_target_extraction_file(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert "auth" in result.target.lower()

    def test_target_extraction_kotlin(self, agent):
        result = agent.fallback(IntentInput(message="refactorizar UserService.kt"))
        assert result.language == "kotlin"

    def test_target_extraction_javascript(self, agent):
        result = agent.fallback(IntentInput(message="analizar codigo en app.js"))
        assert result.language == "javascript"

    def test_code_block_extraction(self, agent):
        code = "def hello():\n    print('hello')"
        result = agent.fallback(IntentInput(
            message=f"analizar ```python\n{code}\n```"
        ))
        assert result.language == "python"

    def test_entities_extraction_function(self, agent):
        result = agent.fallback(IntentInput(message="def process_data(): crear funcion"))
        assert result.entities.get("function") == "process_data"

    def test_entities_extraction_class(self, agent):
        result = agent.fallback(IntentInput(message="class UserManager: refactorizar"))
        assert result.entities.get("class") == "UserManager"


# ============================================================
#  Test: Criticality Inference
# ============================================================

class TestSurgicalAgentCriticality:
    """Tests for criticality inference."""

    def test_critical_auth(self, agent):
        result = agent.fallback(IntentInput(message="corregir error en login auth"))
        assert result.criticality == "critical"

    def test_critical_crypto(self, agent):
        result = agent.fallback(IntentInput(message="mejorar seguridad crypto"))
        assert result.criticality == "critical"

    def test_moderate_database(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo database"))
        assert result.criticality == "moderate"

    def test_standard(self, agent):
        result = agent.fallback(IntentInput(message="crear nueva funcion"))
        assert result.criticality == "standard"


# ============================================================
#  Test: IntentOutput → IntentPayload Conversion
# ============================================================

class TestSurgicalAgentConversion:
    """Tests for IntentOutput to IntentPayload conversion (pipeline compat)."""

    def test_to_intent_payload_basic(self, agent):
        output = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            target="auth.py", language="python",
            confidence=0.8, source="llm",
        )
        payload = agent.to_intent_payload(output, context="crear modulo auth.py")
        assert payload.op == "CREATE"
        assert payload.goal == "FEATURE_ADD"
        assert payload.target == "auth.py"
        assert payload.confidence == 0.8

    def test_to_intent_payload_invalid_operation(self, agent):
        output = IntentOutput(operation="INVALID", goal="FEATURE_ADD")
        payload = agent.to_intent_payload(output)
        assert payload.op == "SEARCH"

    def test_to_intent_payload_scrap_query(self, agent):
        output = IntentOutput(operation="CREATE", goal="FEATURE_ADD", language="python")
        payload = agent.to_intent_payload(output)
        assert payload.scrap_query != ""


# ============================================================
#  Test: Multi-Signal Fusion
# ============================================================

class TestSurgicalAgentFusion:
    """Tests for multi-signal fusion (core F2 innovation)."""

    def test_fusion_concordance_boosts_confidence(self, agent):
        """When TF-IDF and Semantic fully agree (op+goal), confidence should be higher than individual."""
        # TF-IDF result
        tfidf = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="tfidf",
        )
        # Semantic result (agrees on BOTH operation and goal)
        semantic = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="semantic",
        )
        fused = agent._fuse_signals(tfidf, semantic)
        # Full concordance: (0.5+0.5)/2 + 0.15 = 0.65, then cal_factor applied
        # Should be higher than individual confidences of 0.5
        assert fused.confidence > 0.5

    def test_fusion_discrepancy_reduces_confidence(self, agent):
        """When signals disagree, confidence should be reduced."""
        tfidf = IntentOutput(
            operation="SEARCH", goal="FEATURE_ADD",
            confidence=0.3, source="tfidf",
        )
        semantic = IntentOutput(
            operation="DEBUG", goal="BUG_FIX",
            confidence=0.4, source="semantic",
        )
        fused = agent._fuse_signals(tfidf, semantic)
        # Discrepancy: confidence should be less than the winner
        assert fused.confidence < semantic.confidence

    def test_fusion_secondary_none_preserves_primary(self, agent):
        """Without secondary signal, primary is preserved with calibration."""
        primary = IntentOutput(
            operation="CREATE", goal="FEATURE_ADD",
            confidence=0.5, source="tfidf",
        )
        fused = agent._fuse_signals(primary, None)
        assert fused.operation == "CREATE"
        assert fused.goal == "FEATURE_ADD"


# ============================================================
#  Test: Adaptive Calibration
# ============================================================

class TestSurgicalAgentCalibration:
    """Tests for adaptive calibration system."""

    def test_initial_calibration_is_neutral(self, agent):
        """New agent should have neutral calibration factor (1.0)."""
        factor = agent.get_calibration_factor("CREATE")
        assert factor == 1.0

    def test_good_accuracy_boosts_factor(self, agent):
        """After correct classifications, calibration should increase."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=True)
        factor = agent.get_calibration_factor("CREATE")
        assert factor > 1.0

    def test_bad_accuracy_reduces_factor(self, agent):
        """After incorrect classifications, calibration should decrease."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=False)
        factor = agent.get_calibration_factor("CREATE")
        assert factor < 1.0

    def test_calibration_is_per_operation(self, agent):
        """Calibration for one operation should not affect others."""
        for _ in range(5):
            agent.report_accuracy("CREATE", was_correct=True)
        create_factor = agent.get_calibration_factor("CREATE")
        debug_factor = agent.get_calibration_factor("DEBUG")
        assert create_factor > debug_factor


# ============================================================
#  Test: 4 Cables
# ============================================================

class TestSurgicalAgentCables:
    """Tests for the 4 classification cables."""

    def test_cable_memory_hit(self, agent_with_memory):
        """CABLE 1: SmartMemory cache hit returns immediately."""
        agent, mock_memory = agent_with_memory
        mock_memory.check_cache.return_value = {
            "operation": "CREATE", "goal": "FEATURE_ADD",
            "target": "auth.py", "language": "python",
            "importance": 0.8,
        }
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation == "CREATE"
        assert result.source == "cache"

    def test_cable_memory_miss_falls_through(self, agent_with_memory):
        """CABLE 1 miss should fall through to other cables."""
        agent, mock_memory = agent_with_memory
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"

    def test_cable_semantic_high_confidence(self, agent_with_semantic):
        """CABLE 2: SemanticEngine with high confidence."""
        agent, mock_semantic = agent_with_semantic
        result = agent.fallback(IntentInput(message="crear modulo"))
        # Should fuse semantic + tfidf
        assert result.operation == "CREATE"
        assert "+" in result.source or result.source in ("tfidf", "semantic")

    def test_cable_tfidf_always_works(self, agent):
        """CABLE 4: TF-IDF should always produce a result."""
        result = agent.fallback(IntentInput(message="hacer algo"))
        assert result is not None
        assert result.operation in VALID_OPERATIONS
        assert result.source == "tfidf"


# ============================================================
#  Test: LLM Path
# ============================================================

class TestSurgicalAgentLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_compact(self, agent):
        """SurgicalAgent should use compact prompts for 600-token limit."""
        system, user = agent.build_prompt(IntentInput(
            message="crear modulo auth.py", context=""
        ))
        assert "Classify" in system
        assert "JSON" in system
        assert "crear modulo auth.py" in user

    def test_parse_response_valid_json(self, agent):
        raw = '{"operation":"CREATE","goal":"FEATURE_ADD","target":"auth.py","language":"python","entities":{},"template_type":"api","criticality":"standard","confidence":0.9}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "CREATE"
        assert result.confidence == 0.9

    def test_parse_response_markdown_json(self, agent):
        raw = '```json\n{"operation":"DEBUG","goal":"BUG_FIX","confidence":0.75}\n```'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.operation == "DEBUG"

    def test_classify_with_runner_fuses_llm_with_tfidf(self, agent):
        """classify_with_runner should fuse LLM result with TF-IDF."""
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
        # Should be fused (source contains both)
        assert result.confidence > 0  # Fused confidence

    def test_classify_with_runner_failure_uses_fallback(self, agent):
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error", error="LLM timeout"
        )
        result = agent.classify_with_runner(mock_runner, "crear modulo auth.py")
        assert result.operation == "CREATE"


# ============================================================
#  Test: Edge Cases
# ============================================================

class TestSurgicalAgentEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_message(self, agent):
        result = agent.fallback(IntentInput(message=""))
        assert result is not None
        assert result.operation in VALID_OPERATIONS

    def test_very_long_message(self, agent):
        long_msg = "crear " + "modulo " * 500
        result = agent.fallback(IntentInput(message=long_msg))
        assert result is not None

    def test_special_characters(self, agent):
        result = agent.fallback(IntentInput(message="crear módulo auth.py con ñ y áéíóú"))
        assert result is not None

    def test_confidence_always_in_range(self, agent):
        for msg in ["crear", "debug error", "fix bug", "hello world", ""]:
            result = agent.fallback(IntentInput(message=msg))
            assert 0.0 <= result.confidence <= 1.0

    def test_fallback_confidence_is_low(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.confidence <= 0.5

    def test_smart_memory_failure_graceful(self, agent):
        mock_memory = MagicMock()
        mock_memory.check_cache.side_effect = Exception("DB error")
        agent.wire(smart_memory=mock_memory)
        result = agent.fallback(IntentInput(message="crear modulo"))
        assert result.operation in VALID_OPERATIONS


# ============================================================
#  Test: Stats & Wiring
# ============================================================

class TestSurgicalAgentStats:
    """Tests for agent statistics and wiring."""

    def test_initial_stats(self, agent):
        stats = agent.stats
        assert stats["name"] == "surgical"
        assert stats["total_calls"] == 0

    def test_stats_after_fallback(self, agent):
        agent.fallback(IntentInput(message="crear modulo"))
        stats = agent.stats
        assert stats["total_calls"] >= 1

    def test_wire_updates_semantic_engine(self, agent):
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        agent.wire(semantic_engine=mock_semantic)
        assert agent._semantic_engine is mock_semantic

    def test_wire_updates_smart_memory(self, agent):
        mock_memory = MagicMock()
        agent.wire(smart_memory=mock_memory)
        assert agent._smart_memory is mock_memory


# ============================================================
#  Test: Backward Compatibility with IntentAgent
# ============================================================

class TestSurgicalAgentBackwardCompat:
    """Tests that SurgicalAgent is a drop-in replacement for IntentAgent."""

    def test_has_classify_method(self, agent):
        """SurgicalAgent must have classify() method."""
        assert hasattr(agent, 'classify')
        assert callable(agent.classify)

    def test_has_classify_with_runner_method(self, agent):
        """SurgicalAgent must have classify_with_runner() method."""
        assert hasattr(agent, 'classify_with_runner')
        assert callable(agent.classify_with_runner)

    def test_has_to_intent_payload_method(self, agent):
        """SurgicalAgent must have to_intent_payload() method."""
        assert hasattr(agent, 'to_intent_payload')
        assert callable(agent.to_intent_payload)

    def test_has_extract_code_block_static(self):
        """SurgicalAgent must have _extract_code_block() static method."""
        assert hasattr(SurgicalAgent, '_extract_code_block')
        code = "def hello():\n    pass"
        lang, extracted = SurgicalAgent._extract_code_block(
            f"```python\n{code}\n```"
        )
        assert lang == "python"
        assert extracted is not None

    def test_intent_output_compatible(self, agent):
        """SurgicalAgent output must be compatible with IntentOutput schema."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert isinstance(result, IntentOutput)
        assert result.operation in VALID_OPERATIONS
        assert result.goal in VALID_GOALS
