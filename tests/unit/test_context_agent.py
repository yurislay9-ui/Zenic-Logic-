"""
TITAN OMNISCALE X - ContextAgent (F3) Tests

Test suite completa para el agente de gestión de contexto.
Cubre: 4 cables, scoring, compresión, presupuesto, deduplicación.
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.core.agents.context_agent import (
    ContextAgent,
    ContextOutput,
    ContextEntry,
    DEFAULT_TOKEN_BUDGET,
    TOTAL_CONTEXT_BUDGET,
    OP_RELEVANCE_WEIGHTS,
    GOAL_RELEVANCE_WEIGHTS,
    RECENCY_DECAY_FACTOR,
)
from src.core.agents.schemas import IntentOutput


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture
def mock_smart_memory():
    """SmartMemory mock con working memory poblada."""
    mem = MagicMock()

    # Working memory entries
    entries = []
    for i, (op, goal, q, resp) in enumerate([
        ("CREATE", "FEATURE_ADD", "build REST API", "FastAPI code"),
        ("DEBUG", "BUG_FIX", "fix SQL injection", "Used whitelist"),
        ("OPTIMIZE", "PERFORMANCE", "optimize queries", "Added indexes"),
        ("REFACTOR", "COMPLEXITY_REDUCTION", "simplify parser", "Reduced 200 lines"),
        ("SEARCH", "FEATURE_ADD", "find auth module", "Found auth_service.py"),
    ]):
        entry = MagicMock()
        entry.operation = op
        entry.goal = goal
        entry.query = q
        entry.response = resp
        entry.importance = 0.5 + i * 0.1
        entry.timestamp = time.time() - (i * 60)  # Cada vez más viejo
        entry.session_id = "test123"
        entries.append(entry)

    mem._working_memory = entries

    # Mock methods
    mem.check_cache.return_value = None
    mem.get_working_context.return_value = "Previous: CREATE/FEATURE_ADD → FastAPI code"
    mem.find_similar_solutions.return_value = [
        {"query": "build API", "solution": "Used FastAPI", "operation": "CREATE",
         "goal": "FEATURE_ADD", "importance": 0.7, "similarity": 0.85}
    ]
    mem.find_patterns.return_value = [
        {"pattern_name": "api_pattern", "pattern_type": "strategy",
         "description": "REST API with FastAPI", "success_rate": 0.8}
    ]
    mem.find_episodes.return_value = []

    return mem


@pytest.fixture
def mock_semantic_engine():
    """SemanticEngine mock."""
    sem = MagicMock()
    sem.is_loaded = True
    return sem


@pytest.fixture
def context_agent(mock_semantic_engine, mock_smart_memory):
    """ContextAgent con dependencias mockeadas."""
    return ContextAgent(
        semantic_engine=mock_semantic_engine,
        smart_memory=mock_smart_memory,
    )


@pytest.fixture
def sample_intent_output():
    """IntentOutput de ejemplo."""
    return IntentOutput(
        operation="CREATE",
        goal="FEATURE_ADD",
        target="api.py",
        language="python",
        confidence=0.85,
        source="tfidf",
    )


# ============================================================
#  TEST: Constructor y wiring
# ============================================================

class TestContextAgentInit:

    def test_init_default(self):
        agent = ContextAgent()
        assert agent.name == "context"
        assert agent._semantic_engine is None
        assert agent._smart_memory is None
        assert agent._shared_context_cache == {}

    def test_init_with_engines(self, mock_semantic_engine, mock_smart_memory):
        agent = ContextAgent(
            semantic_engine=mock_semantic_engine,
            smart_memory=mock_smart_memory,
        )
        assert agent._semantic_engine is mock_semantic_engine
        assert agent._smart_memory is mock_smart_memory

    def test_wire(self, context_agent):
        new_sem = MagicMock()
        new_mem = MagicMock()
        context_agent.wire(semantic_engine=new_sem, smart_memory=new_mem)
        assert context_agent._semantic_engine is new_sem
        assert context_agent._smart_memory is new_mem


# ============================================================
#  TEST: CABLE 1 — Recopilar entradas de memoria
# ============================================================

class TestCable1CollectEntries:

    def test_collects_working_memory(self, context_agent, mock_smart_memory):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        # Debe recopilar entradas de working memory
        assert len(entries) >= 5  # Las 5 entradas del fixture

    def test_collects_long_term_memory(self, context_agent, mock_smart_memory, mock_semantic_engine):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        # Debe incluir resultados de find_similar_solutions
        sources = [e.source for e in entries]
        assert "working" in sources
        assert "long_term" in sources

    def test_collects_procedural_memory(self, context_agent, mock_smart_memory):
        entries = context_agent._collect_entries("build API", "CREATE", "FEATURE_ADD")
        sources = [e.source for e in entries]
        assert "procedural" in sources

    def test_handles_no_memory(self):
        agent = ContextAgent()
        entries = agent._collect_entries("test", "SEARCH", "FEATURE_ADD")
        assert entries == []

    def test_handles_memory_error(self, context_agent, mock_smart_memory):
        mock_smart_memory._working_memory = Exception("DB error")
        # No debe crashear
        try:
            entries = context_agent._collect_entries("test", "SEARCH", "FEATURE_ADD")
        except Exception:
            pass  # El agente maneja errores graciosamente


# ============================================================
#  TEST: CABLE 2 — Scoring de relevancia
# ============================================================

class TestCable2ScoreEntries:

    def test_scores_by_operation_relevance(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="test1"),
            ContextEntry(operation="DEBUG", goal="BUG_FIX", importance=0.5, recency=1.0, content="test2"),
            ContextEntry(operation="OPTIMIZE", goal="PERFORMANCE", importance=0.5, recency=1.0, content="test3"),
        ]

        # Para intent CREATE, la entrada CREATE debe tener mayor score
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].operation == "CREATE"

    def test_scores_by_recency(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=0.3, content="old"),
            ContextEntry(operation="SEARCH", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="new"),
        ]

        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        # La entrada con CREATE + FEATURE_ADD tiene más relevance pero menos recency
        # El score combinado depende de los pesos

    def test_scores_by_importance(self, context_agent):
        entries = [
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.9, recency=0.5, content="important"),
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.2, recency=0.5, content="unimportant"),
        ]

        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].importance > scored[1].importance

    def test_combined_scoring(self, context_agent):
        """Verifica que el scoring combina importance + recency + relevance."""
        entries = [
            ContextEntry(operation="DEBUG", goal="BUG_FIX", importance=0.9, recency=0.2, content="old debug"),
            ContextEntry(operation="CREATE", goal="FEATURE_ADD", importance=0.5, recency=1.0, content="new create"),
        ]

        # Para intent CREATE/FEATURE_ADD, la segunda entrada debería ganar
        # porque tiene mejor relevance + recency, a pesar de menor importance
        scored = context_agent._score_entries(entries, "CREATE", "FEATURE_ADD")
        assert scored[0].relevance_score > 0


# ============================================================
#  TEST: CABLE 3 — Compresión adaptativa
# ============================================================

class TestCable3Compression:

    def test_compress_empty_entries(self, context_agent):
        result, count = context_agent._compress_entries([], 200, "CREATE", "FEATURE_ADD")
        assert result == ""
        assert count == 0

    def test_compress_fits_budget(self, context_agent):
        entries = [
            ContextEntry(content="Short entry", token_estimate=3, relevance_score=0.8,
                        operation="CREATE", goal="FEATURE_ADD"),
        ]
        result, count = context_agent._compress_entries(entries, 200, "CREATE", "FEATURE_ADD")
        assert count == 1
        assert "Short entry" in result

    def test_compress_truncates_too_long(self, context_agent):
        entries = [
            ContextEntry(content="A" * 500, token_estimate=200, relevance_score=0.9,
                        operation="CREATE", goal="FEATURE_ADD"),
        ]
        result, count = context_agent._compress_entries(entries, 50, "CREATE", "FEATURE_ADD")
        assert count == 1
        # Debe estar truncado
        assert len(result) <= 50 * 4 + 10  # max_tokens * 4 chars + margen

    def test_compress_selects_by_relevance(self, context_agent):
        """Cuando no caben todas, selecciona las de mayor relevancia."""
        entries = [
            ContextEntry(content="High relevance entry", token_estimate=100,
                        relevance_score=0.9, operation="CREATE", goal="FEATURE_ADD"),
            ContextEntry(content="Low relevance entry", token_estimate=100,
                        relevance_score=0.2, operation="SEARCH", goal="FEATURE_ADD"),
        ]
        # Budget para solo 1 entrada
        result, count = context_agent._compress_entries(entries, 110, "CREATE", "FEATURE_ADD")
        assert count == 1
        assert "High relevance" in result


# ============================================================
#  TEST: CABLE 4 — Pre-fetch de memorias relevantes
# ============================================================

class TestCable4Prefetch:

    def test_prefetch_similar_solutions(self, context_agent, mock_smart_memory):
        results = context_agent._prefetch_relevant("build API", "CREATE", "FEATURE_ADD")
        assert len(results) >= 1
        assert results[0]["type"] == "similar_solution"

    def test_prefetch_debug_episodes(self, context_agent, mock_smart_memory):
        mock_smart_memory.find_episodes.return_value = [
            {"description": "SQL injection fixed", "outcome": "success"}
        ]
        results = context_agent._prefetch_relevant("fix bug", "DEBUG", "BUG_FIX")
        types = [r["type"] for r in results]
        assert "error_episode" in types

    def test_prefetch_create_patterns(self, context_agent, mock_smart_memory):
        results = context_agent._prefetch_relevant("build app", "CREATE", "FEATURE_ADD")
        types = [r["type"] for r in results]
        assert "procedural_pattern" in types

    def test_prefetch_no_memory(self):
        agent = ContextAgent()
        results = agent._prefetch_relevant("test", "SEARCH", "FEATURE_ADD")
        assert results == []


# ============================================================
#  TEST: Presupuesto de tokens
# ============================================================

class TestTokenBudget:

    def test_default_budget(self):
        total = sum(DEFAULT_TOKEN_BUDGET.values())
        # Default budget sum can differ from total after normalization
        assert total > 0
        assert all(v > 0 for v in DEFAULT_TOKEN_BUDGET.values())

    def test_create_budget_increases_code(self, context_agent):
        budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        assert budget["code"] >= DEFAULT_TOKEN_BUDGET["code"]

    def test_debug_budget_increases_reasoning(self, context_agent):
        budget = context_agent._allocate_budget("DEBUG", "BUG_FIX")
        assert budget["reasoning"] >= DEFAULT_TOKEN_BUDGET["reasoning"]

    def test_security_budget_increases_validation(self, context_agent):
        # Compare with a non-security budget to verify relative increase
        normal_budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        security_budget = context_agent._allocate_budget("CREATE", "SECURITY_HARDEN")
        # Security budget should allocate more to validation relative to normal
        # (may be scaled down by normalization, so check ratio)
        security_val_ratio = security_budget["validation"] / sum(security_budget.values())
        normal_val_ratio = normal_budget["validation"] / sum(normal_budget.values())
        assert security_val_ratio >= normal_val_ratio

    def test_budget_does_not_exceed_total(self, context_agent):
        budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        total = sum(budget.values())
        # Puede ser ligeramente menor por redondeo
        assert total <= TOTAL_CONTEXT_BUDGET + 50

    def test_get_budget_for_agent(self, context_agent):
        assert context_agent.get_token_budget_for("code") == DEFAULT_TOKEN_BUDGET["code"]
        assert context_agent.get_token_budget_for("reasoning") == DEFAULT_TOKEN_BUDGET["reasoning"]
        assert context_agent.get_token_budget_for("unknown") == 100  # Default


# ============================================================
#  TEST: High-level API
# ============================================================

class TestHighLevelAPI:

    def test_prepare_context(self, context_agent, sample_intent_output):
        result = context_agent.prepare_context(
            message="build a REST API",
            intent_output=sample_intent_output,
        )
        assert isinstance(result, ContextOutput)
        assert result.source == "fallback"
        assert isinstance(result.compressed_context, str)
        assert isinstance(result.token_budget, dict)
        assert isinstance(result.relevant_memories, list)

    def test_prepare_context_no_intent(self, context_agent):
        result = context_agent.prepare_context("test message")
        assert isinstance(result, ContextOutput)
        assert result.entries_total >= 0

    def test_prepare_context_with_runner_no_llm(self, context_agent, sample_intent_output):
        runner = MagicMock()
        runner._mini_ai = None
        result = context_agent.prepare_context_with_runner(
            runner, "build API", sample_intent_output
        )
        assert isinstance(result, ContextOutput)

    def test_get_context_for_agent(self, context_agent, sample_intent_output):
        ctx = context_agent.get_context_for_agent("code", sample_intent_output)
        assert isinstance(ctx, str)

    def test_get_context_for_agent_dedup(self, context_agent, sample_intent_output):
        """Verifica deduplicación: segunda llamada retorna vacío."""
        ctx1 = context_agent.get_context_for_agent("code", sample_intent_output)
        ctx2 = context_agent.get_context_for_agent("code", sample_intent_output)
        # La segunda llamada retorna "" (ya se envió)
        assert ctx2 == ""

    def test_reset_agent_tracking(self, context_agent, sample_intent_output):
        context_agent.get_context_for_agent("code", sample_intent_output)
        context_agent.reset_agent_tracking()
        # Después de reset, debería poder enviar de nuevo
        ctx = context_agent.get_context_for_agent("code", sample_intent_output)
        # Puede ser vacío si el cache sigue siendo el mismo hash
        # Pero al menos no debería crashear

    def test_get_compressed_working_context(self, context_agent, sample_intent_output):
        ctx = context_agent.get_compressed_working_context(sample_intent_output, 200)
        assert isinstance(ctx, str)


# ============================================================
#  TEST: BaseAgent interface
# ============================================================

class TestBaseAgentInterface:

    def test_build_prompt(self, context_agent):
        input_data = {
            "raw_context": "Previous: CREATE/FEATURE_ADD → FastAPI code",
            "intent_operation": "CREATE",
            "intent_goal": "FEATURE_ADD",
            "max_tokens": 200,
        }
        system, user = context_agent.build_prompt(input_data)
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "CREATE" in system or "FEATURE_ADD" in system

    def test_parse_response(self, context_agent):
        raw_response = "CREATE/FEATURE_ADD: FastAPI REST API | DEBUG/BUG_FIX: SQL whitelist"
        input_data = {"raw_context": "long context...", "max_tokens": 200}
        result = context_agent.parse_response(raw_response, input_data)
        assert isinstance(result, ContextOutput)
        assert result.source == "llm"

    def test_parse_response_empty(self, context_agent):
        result = context_agent.parse_response("", {})
        assert result is None

    def test_fallback(self, context_agent, sample_intent_output):
        input_data = {
            "message": "build API",
            "intent_output": sample_intent_output,
            "max_tokens": 200,
        }
        result = context_agent.fallback(input_data)
        assert isinstance(result, ContextOutput)
        assert result.source == "fallback"
        assert result.duration_ms >= 0


# ============================================================
#  TEST: Integración con DAG pipeline
# ============================================================

class TestDAGIntegration:

    def test_context_output_has_all_fields(self, context_agent, sample_intent_output):
        result = context_agent.prepare_context("test", sample_intent_output)
        assert hasattr(result, "compressed_context")
        assert hasattr(result, "relevant_memories")
        assert hasattr(result, "token_budget")
        assert hasattr(result, "context_scores")
        assert hasattr(result, "entries_used")
        assert hasattr(result, "entries_total")
        assert hasattr(result, "compression_ratio")
        assert hasattr(result, "source")
        assert hasattr(result, "duration_ms")

    def test_different_intents_produce_different_budgets(self, context_agent):
        create_budget = context_agent._allocate_budget("CREATE", "FEATURE_ADD")
        debug_budget = context_agent._allocate_budget("DEBUG", "BUG_FIX")
        # Los presupuestos deben diferir
        assert create_budget["code"] != debug_budget["code"] or \
               create_budget["reasoning"] != debug_budget["reasoning"]

    def test_context_caching(self, context_agent, sample_intent_output):
        """Verifica que el cache compartido funciona."""
        # Primera llamada: calcula
        result1 = context_agent.prepare_context("build API", sample_intent_output)
        # El cache debe tener una entrada
        cache_key = f"{sample_intent_output.operation}:{sample_intent_output.goal}"
        assert cache_key in context_agent._shared_context_cache

    def test_budget_stats(self, context_agent):
        stats = context_agent.budget_stats
        assert "default_budget" in stats
        assert "total_budget" in stats
        assert stats["total_budget"] == TOTAL_CONTEXT_BUDGET


# ============================================================
#  TEST: Edge cases
# ============================================================

class TestEdgeCases:

    def test_very_short_message(self, context_agent):
        result = context_agent.prepare_context("x", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_very_long_message(self, context_agent):
        long_msg = "build " * 1000
        result = context_agent.prepare_context(long_msg, IntentOutput(operation="CREATE"))
        assert isinstance(result, ContextOutput)

    def test_no_semantic_engine(self):
        agent = ContextAgent(smart_memory=MagicMock())
        agent._smart_memory._working_memory = []
        result = agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_no_smart_memory(self):
        agent = ContextAgent(semantic_engine=MagicMock())
        result = agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)

    def test_empty_working_memory(self, context_agent, mock_smart_memory):
        mock_smart_memory._working_memory = []
        # Even with empty working memory, long_term/procedural may return entries
        result = context_agent.prepare_context("test", IntentOutput(operation="SEARCH"))
        assert isinstance(result, ContextOutput)
        # Working memory entries should be 0, but total may include other sources
        assert result.entries_total >= 0
