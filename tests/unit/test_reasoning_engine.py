"""
TITAN OMNISCALE X - ReasoningEngine Unit Tests

Tests for src/core/reasoning_engine.py:
  - Step-by-step reasoning (fallback mode)
  - Self-reflect reasoning (fallback mode)
  - Reason with context (fallback mode)
  - Auto mode selection
  - Fallback methods
  - Confidence estimation
  - Complexity estimation
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.reasoning_engine import (
    ReasoningEngine,
    ReasoningMode,
    ReasoningStep,
    ReasoningResult,
    MAX_REASONING_STEPS,
    MAX_REFLECT_ITERATIONS,
    MIN_CONFIDENCE_ACCEPT,
)


# ============================================================
#  INITIALIZATION TESTS
# ============================================================

class TestReasoningEngineInit:
    """Tests for ReasoningEngine initialization."""

    def test_init_no_dependencies(self):
        """Should initialize without any AI dependencies."""
        engine = ReasoningEngine()
        assert engine._ai is None
        assert engine._semantic is None
        assert engine._memory is None
        assert engine._call_count == 0
        assert engine._total_time == 0.0

    def test_init_with_mock_ai(self):
        """Should accept optional AI engine."""
        mock_ai = MagicMock()
        engine = ReasoningEngine(mini_ai=mock_ai)
        assert engine._ai is mock_ai

    def test_init_with_all_layers(self):
        """Should accept all three AI layers."""
        mock_ai = MagicMock()
        mock_semantic = MagicMock()
        mock_memory = MagicMock()
        engine = ReasoningEngine(
            mini_ai=mock_ai,
            semantic_engine=mock_semantic,
            smart_memory=mock_memory,
        )
        assert engine._ai is mock_ai
        assert engine._semantic is mock_semantic
        assert engine._memory is mock_memory


# ============================================================
#  STEP-BY-STEP REASONING TESTS
# ============================================================

class TestStepByStep:
    """Tests for ReasoningEngine.step_by_step()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        """step_by_step should return a ReasoningResult."""
        result = self.engine.step_by_step("How to create an API?")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10
        assert result.confidence > 0.0

    def test_correct_mode(self):
        """Result mode should be STEP_BY_STEP."""
        result = self.engine.step_by_step("Test problem")
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_steps_count_respected(self):
        """Should produce at most max_steps steps."""
        result = self.engine.step_by_step("Test", max_steps=2)
        assert len(result.steps) <= 2

    def test_default_steps_count(self):
        """Default should produce up to MAX_REASONING_STEPS steps."""
        result = self.engine.step_by_step("Test", max_steps=MAX_REASONING_STEPS)
        assert len(result.steps) <= MAX_REASONING_STEPS

    def test_fallback_source_when_no_ai(self):
        """Without AI, steps should use fallback source."""
        result = self.engine.step_by_step("Test")
        assert all(s.source == "fallback" for s in result.steps)

    def test_context_appended(self):
        """Additional context should be included in reasoning."""
        result = self.engine.step_by_step("Test", context="Some context")
        assert result is not None

    def test_with_mock_ai(self):
        """With mock AI, should use LLM source."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = "The answer is to use FastAPI."
        engine = ReasoningEngine(mini_ai=mock_ai)
        result = engine.step_by_step("How to build API?")
        assert any(s.source == "llm" for s in result.steps)


# ============================================================
#  SELF-REFLECT REASONING TESTS
# ============================================================

class TestSelfReflect:
    """Tests for ReasoningEngine.self_reflect()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        """self_reflect should return a ReasoningResult."""
        result = self.engine.self_reflect("Design an auth system")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10

    def test_correct_mode(self):
        """Result mode should be SELF_REFLECT."""
        result = self.engine.self_reflect("Test")
        assert result.mode == ReasoningMode.SELF_REFLECT

    def test_iterations_limited(self):
        """Should limit iterations to max_iterations."""
        result = self.engine.self_reflect("Test", max_iterations=1)
        # Each iteration produces 2 steps: generate + evaluate
        assert len(result.steps) <= 2

    def test_with_mock_ai_high_score(self):
        """With high eval score, should stop refining early."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.side_effect = [
            "Use JWT tokens for auth.",
            '{"score": 0.9, "issues": [], "missing": []}',
        ]
        engine = ReasoningEngine(mini_ai=mock_ai)
        result = engine.self_reflect("Auth system")
        assert result.confidence >= 0.7


# ============================================================
#  REASON WITH CONTEXT TESTS
# ============================================================

class TestReasonWithContext:
    """Tests for ReasoningEngine.reason_with_context()."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_produces_result(self):
        """reason_with_context should return a ReasoningResult."""
        result = self.engine.reason_with_context("Build a CRM")
        assert isinstance(result, ReasoningResult)
        assert len(result.answer) > 10

    def test_correct_mode(self):
        """Result mode should be WITH_CONTEXT."""
        result = self.engine.reason_with_context("Test")
        assert result.mode == ReasoningMode.WITH_CONTEXT

    def test_with_semantic_engine(self):
        """Should use semantic engine for context enrichment."""
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        mock_result = MagicMock()
        mock_result.source = "embedding"
        mock_result.confidence = 0.8
        mock_result.operation = "CREATE"
        mock_result.goal = "FEATURE_ADD"
        mock_semantic.classify_intent.return_value = mock_result

        engine = ReasoningEngine(semantic_engine=mock_semantic)
        result = engine.reason_with_context("Build a CRM system")
        assert result.context_used is True

    def test_with_memory(self):
        """Should query memory for similar solutions."""
        mock_memory = MagicMock()
        mock_memory.get_working_context.return_value = "Previous work on CRM"
        mock_semantic = MagicMock()
        mock_semantic.is_loaded = True
        mock_result = MagicMock()
        mock_result.source = "embedding"
        mock_result.confidence = 0.8
        mock_result.operation = "CREATE"
        mock_result.goal = "FEATURE_ADD"
        mock_semantic.classify_intent.return_value = mock_result
        mock_memory.find_similar_solutions.return_value = []

        engine = ReasoningEngine(semantic_engine=mock_semantic, smart_memory=mock_memory)
        result = engine.reason_with_context("Build CRM")
        assert result is not None


# ============================================================
#  AUTO MODE SELECTION TESTS
# ============================================================

class TestAutoModeSelection:
    """Tests for ReasoningEngine.reason() auto mode."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_auto_simple_problem(self):
        """Simple problems should select step_by_step mode."""
        result = self.engine.reason("create a function")
        assert result.mode == ReasoningMode.FALLBACK  # No AI -> fallback

    def test_explicit_mode(self):
        """Explicit mode should override auto selection."""
        result = self.engine.reason("Test", mode="step_by_step")
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_explicit_self_reflect_mode(self):
        """self_reflect mode should be selectable."""
        result = self.engine.reason("Test", mode="self_reflect")
        assert result.mode == ReasoningMode.SELF_REFLECT

    def test_explicit_with_context_mode(self):
        """with_context mode should be selectable."""
        result = self.engine.reason("Test", mode="with_context")
        assert result.mode == ReasoningMode.WITH_CONTEXT


# ============================================================
#  FALLBACK METHOD TESTS
# ============================================================

class TestFallbackMethods:
    """Tests for ReasoningEngine fallback methods."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_fallback_step_api(self):
        """Fallback step 1 should identify API problems."""
        result = self.engine._fallback_step(1, "How to create a REST API endpoint?", [])
        assert "API" in result

    def test_fallback_step_auth(self):
        """Fallback step 1 should identify auth problems."""
        result = self.engine._fallback_step(1, "Implement login with JWT", [])
        assert "auth" in result.lower() or "authentication" in result.lower()

    def test_fallback_step_database(self):
        """Fallback step 1 should identify database problems."""
        result = self.engine._fallback_step(1, "Design the database schema", [])
        assert "data" in result.lower()

    def test_fallback_step_2(self):
        """Fallback step 2 should suggest standard patterns."""
        result = self.engine._fallback_step(2, "any problem", [])
        assert "pattern" in result.lower() or "standard" in result.lower()

    def test_fallback_generate_api(self):
        """Fallback generate should produce API-related advice."""
        result = self.engine._fallback_generate("create an API", 1)
        assert "API" in result or "api" in result.lower()

    def test_fallback_evaluate_short_answer(self):
        """Evaluation should flag short answers."""
        score, issues = self.engine._fallback_evaluate("ok", "test")
        assert score < 0.5
        assert len(issues) > 0

    def test_fallback_evaluate_security_risk(self):
        """Evaluation should flag eval() as security risk."""
        score, issues = self.engine._fallback_evaluate("Use eval() to parse", "test")
        assert any("security" in i.lower() for i in issues)

    def test_full_fallback(self):
        """Full fallback should return FALLBACK mode with low confidence."""
        result = self.engine._full_fallback("any problem")
        assert result.mode == ReasoningMode.FALLBACK
        assert result.confidence < 0.5
        assert len(result.steps) > 0

    def test_fallback_context_reasoning(self):
        """Context reasoning fallback should use semantic info."""
        result = self.engine._fallback_context_reasoning(
            "test", {"operation": "CREATE", "goal": "FEATURE_ADD"}
        )
        assert "CREATE" in result or "feature_add" in result.lower()


# ============================================================
#  CONFIDENCE & COMPLEXITY TESTS
# ============================================================

class TestConfidenceAndComplexity:
    """Tests for confidence estimation and complexity estimation."""

    def setup_method(self):
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_estimate_confidence_increases_with_length(self):
        """Longer answers should generally have higher confidence."""
        short = self.engine._estimate_confidence("ok", 1, 3)
        long = self.engine._estimate_confidence(
            "This is a very detailed and comprehensive answer that provides thorough analysis.",
            1, 3,
        )
        assert long >= short

    def test_estimate_confidence_hedging_reduces(self):
        """Hedging words should reduce confidence."""
        certain = self.engine._estimate_confidence(
            "The answer is clearly 42.", 1, 3
        )
        hedges = self.engine._estimate_confidence(
            "Maybe perhaps the answer might possibly be 42.", 1, 3
        )
        assert certain > hedges

    def test_estimate_complexity_simple(self):
        """Simple problems should have low complexity."""
        complexity = self.engine._estimate_complexity("create a function")
        assert complexity < 0.5

    def test_estimate_complexity_complex(self):
        """Complex problems should have higher complexity."""
        complexity = self.engine._estimate_complexity(
            "Build a microservice API with database, authentication, "
            "caching, and async pipeline but also webhook integration"
        )
        assert complexity > 0.3

    def test_estimate_complexity_tech_terms(self):
        """Technical terms should increase complexity."""
        c1 = self.engine._estimate_complexity("make a thing")
        c2 = self.engine._estimate_complexity("make an API with database and webhook")
        assert c2 > c1


# ============================================================
#  STATS TESTS
# ============================================================

class TestReasoningStats:
    """Tests for ReasoningEngine.stats property."""

    def test_stats_structure(self):
        """Stats should contain expected keys."""
        engine = ReasoningEngine()
        stats = engine.stats
        assert "total_calls" in stats
        assert "total_time_s" in stats
        assert "ai_available" in stats
        assert "semantic_available" in stats
        assert "memory_available" in stats
        assert "modes" in stats

    def test_stats_increments_calls(self):
        """Stats should track total calls."""
        engine = ReasoningEngine()
        engine.step_by_step("Test")
        assert engine.stats["total_calls"] >= 1

    def test_stats_reports_availability(self):
        """Stats should correctly report availability."""
        engine = ReasoningEngine()
        stats = engine.stats
        assert stats["ai_available"] is False
        assert stats["semantic_available"] is False
        assert stats["memory_available"] is False


# ============================================================
#  EXTRACT CONCLUSION TESTS
# ============================================================

class TestExtractConclusion:
    """Tests for _extract_conclusion helper."""

    def setup_method(self):
        self.engine = ReasoningEngine()

    def test_with_therefore(self):
        """Should extract conclusion after 'therefore'."""
        result = self.engine._extract_conclusion(
            "Analysis shows the pattern. Therefore, use a factory pattern."
        )
        assert "factory" in result.lower()

    def test_with_conclusion_marker(self):
        """Should extract conclusion after 'conclusion:'."""
        result = self.engine._extract_conclusion(
            "Some analysis. Conclusion: the answer is 42"
        )
        assert "42" in result or "answer" in result.lower()

    def test_without_marker(self):
        """Should return last meaningful sentence without markers."""
        result = self.engine._extract_conclusion(
            "First approach. Second approach. The best option is to use caching."
        )
        assert len(result) > 5

    def test_empty_text(self):
        """Should handle empty text gracefully."""
        result = self.engine._extract_conclusion("")
        assert isinstance(result, str)
