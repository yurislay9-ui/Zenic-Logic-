"""
TITAN OMNISCALE X - Agent Framework Tests

Tests completos del framework de agentes:
  - BaseAgent (clase abstracta, utilidades)
  - AgentRunner (ejecución, fallback, retry, cache)
  - AgentCache (almacenamiento, expiración, evicción)
  - PromptBuilder (construcción de prompts)
  - Schemas (validación de datos)
  - Cableado con Orchestrator (integración)
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.runner import AgentRunner
from src.core.agents.cache import AgentCache
from src.core.agents.prompts import PromptBuilder, AgentPrompts
from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningOutput, ReasoningStep,
    BusinessInput, BusinessOutput,
    CodeInput, CodeOutput, FileSpec,
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
    ValidationInput, ValidationOutput, ValidationIssue,
)


# ============================================================
#  CONCRETE TEST AGENT (para testear BaseAgent abstracta)
# ============================================================

class SampleAgent(BaseAgent):
    """Agente concreto de prueba."""

    def __init__(self):
        super().__init__(name="test_agent")

    def build_prompt(self, input_data):
        return (
            "You are a test agent. Reply with JSON.",
            f"Process: {input_data}"
        )

    def parse_response(self, raw_response, input_data):
        try:
            data = json.loads(raw_response)
            return IntentOutput(
                operation=data.get("operation", "SEARCH"),
                goal=data.get("goal", "FEATURE_ADD"),
                confidence=data.get("confidence", 0.5),
                source="llm",
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def fallback(self, input_data):
        return IntentOutput(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,
            source="fallback",
        )


class BrokenAgent(BaseAgent):
    """Agente que siempre falla en parse_response."""

    def __init__(self):
        super().__init__(name="broken_agent")

    def build_prompt(self, input_data):
        return "system", "user"

    def parse_response(self, raw_response, input_data):
        return None  # Always fails

    def fallback(self, input_data):
        return IntentOutput(operation="SEARCH", source="fallback")


# ============================================================
#  SCHEMA TESTS
# ============================================================

class TestSchemas:
    """Tests para los esquemas de datos de los agentes."""

    def test_intent_input_defaults(self):
        inp = IntentInput()
        assert inp.message == ""
        assert inp.context == ""

    def test_intent_input_with_data(self):
        inp = IntentInput(message="Create a login page", context="web app")
        assert inp.message == "Create a login page"
        assert inp.context == "web app"

    def test_intent_output_defaults(self):
        out = IntentOutput()
        assert out.operation == "SEARCH"
        assert out.goal == "FEATURE_ADD"
        assert out.confidence == 0.0
        assert out.source == "fallback"

    def test_intent_output_with_data(self):
        out = IntentOutput(operation="CREATE", goal="FEATURE_ADD",
                          confidence=0.9, source="llm",
                          target="auth.py", language="python")
        assert out.operation == "CREATE"
        assert out.confidence == 0.9
        assert out.source == "llm"

    def test_reasoning_input_defaults(self):
        inp = ReasoningInput()
        assert inp.mode == "step_by_step"
        assert inp.max_steps == 5

    def test_reasoning_output_with_steps(self):
        steps = [
            ReasoningStep(step_number=1, description="Analyze", conclusion="Found X"),
            ReasoningStep(step_number=2, description="Verify", conclusion="Confirmed"),
        ]
        out = ReasoningOutput(answer="Yes", confidence=0.8, steps=steps, source="llm")
        assert len(out.steps) == 2
        assert out.steps[0].conclusion == "Found X"

    def test_business_input(self):
        inp = BusinessInput(
            operation_type="invoice",
            data={"amount": 100, "tax_rate": 0.21},
            description="Calculate invoice total",
        )
        assert inp.operation_type == "invoice"
        assert inp.data["amount"] == 100

    def test_business_output(self):
        out = BusinessOutput(
            success=True,
            data={"total": 121},
            side_effects=["notify_accounting"],
            insights=["Tax rate is 21%"],
        )
        assert out.success is True
        assert len(out.insights) == 1

    def test_code_input(self):
        inp = CodeInput(task="generate", requirements="FastAPI app",
                       language="python")
        assert inp.task == "generate"
        assert inp.language == "python"

    def test_code_output_with_files(self):
        files = [FileSpec(path="main.py", content="print('hi')", language="python")]
        out = CodeOutput(code="print('hi')", files=files, source="llm")
        assert len(out.files) == 1
        assert out.files[0].path == "main.py"

    def test_automation_input(self):
        inp = AutomationInput(description="Email me every Friday")
        assert inp.description == "Email me every Friday"

    def test_automation_output(self):
        triggers = [TriggerSpec(type="schedule", config={"day": "friday"})]
        actions = [ActionSpec(type="email", config={"to": "user@test.com"})]
        schedule = ScheduleSpec(type="cron", cron_expression="0 17 * * 5")

        out = AutomationOutput(
            name="friday_email",
            triggers=triggers,
            actions=actions,
            schedule=schedule,
        )
        assert out.name == "friday_email"
        assert len(out.triggers) == 1
        assert out.schedule.cron_expression == "0 17 * * 5"

    def test_validation_input(self):
        inp = ValidationInput(target="code", content="eval(input())", language="python")
        assert inp.target == "code"

    def test_validation_output(self):
        issues = [
            ValidationIssue(severity="error", code="DANGEROUS_CALL",
                           message="eval() is dangerous", suggestion="Use ast.literal_eval()"),
        ]
        out = ValidationOutput(is_valid=False, issues=issues, risk_score=0.9)
        assert out.is_valid is False
        assert len(out.issues) == 1
        assert out.issues[0].severity == "error"


# ============================================================
#  BASE AGENT TESTS
# ============================================================

class TestBaseAgent:
    """Tests para la clase BaseAgent."""

    def test_agent_creation(self):
        agent = SampleAgent()
        assert agent.name == "test_agent"
        assert agent._call_count == 0

    def test_agent_stats(self):
        agent = SampleAgent()
        stats = agent.stats
        assert stats["name"] == "test_agent"
        assert stats["total_calls"] == 0

    def test_agent_update_stats_llm(self):
        agent = SampleAgent()
        agent._update_stats("llm", 150)
        assert agent._call_count == 1
        assert agent._llm_success_count == 1
        assert agent._total_duration_ms == 150

    def test_agent_update_stats_fallback(self):
        agent = SampleAgent()
        agent._update_stats("fallback", 5)
        assert agent._fallback_count == 1

    def test_agent_update_stats_cache(self):
        agent = SampleAgent()
        agent._update_stats("cache", 0)
        assert agent._cache_hit_count == 1

    def test_agent_update_stats_with_error(self):
        agent = SampleAgent()
        agent._update_stats("fallback", 5, error="timeout")
        assert agent._last_error == "timeout"

    def test_extract_json_from_markdown(self):
        text = '```json\n{"operation": "CREATE", "goal": "FEATURE_ADD"}\n```'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["operation"] == "CREATE"

    def test_extract_json_from_raw(self):
        text = 'Here is the result: {"operation": "SEARCH"}'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["operation"] == "SEARCH"

    def test_extract_json_invalid(self):
        text = "No JSON here at all"
        result = BaseAgent.extract_json(text)
        assert result is None

    def test_extract_json_nested(self):
        text = '{"outer": {"inner": "value"}, "list": [1, 2]}'
        result = BaseAgent.extract_json(text)
        assert result is not None
        assert result["outer"]["inner"] == "value"

    def test_extract_list_numbered(self):
        text = "1. First item\n2. Second item\n3. Third item"
        result = BaseAgent.extract_list(text)
        assert len(result) == 3
        assert "First item" in result[0]

    def test_extract_list_bullets(self):
        text = "- Item one\n- Item two\n* Item three"
        result = BaseAgent.extract_list(text)
        assert len(result) == 3

    def test_extract_list_empty(self):
        result = BaseAgent.extract_list("No list items here")
        assert result == []

    def test_clean_llm_text_think_block(self):
        text = " The answer is 42"
        result = BaseAgent.clean_llm_text(text)
        assert "think" not in result
        assert "42" in result

    def test_clean_llm_text_markdown(self):
        text = "```python\ndef hello():\n    pass\n```"
        result = BaseAgent.clean_llm_text(text)
        assert "```" not in result
        assert "def hello" in result

    def test_clean_llm_text_bold(self):
        text = "This is **important** text"
        result = BaseAgent.clean_llm_text(text)
        assert "**" not in result
        assert "important" in result

    def test_validate_output_default(self):
        agent = SampleAgent()
        assert agent.validate_output("something") is True
        assert agent.validate_output(None) is False

    def test_fallback_returns_valid_output(self):
        agent = SampleAgent()
        result = agent.fallback("test input")
        assert isinstance(result, IntentOutput)
        assert result.source == "fallback"
        assert result.confidence == 0.1

    def test_build_prompt(self):
        agent = SampleAgent()
        sys_prompt, user_prompt = agent.build_prompt("Create a user")
        assert "test agent" in sys_prompt
        assert "Create a user" in user_prompt

    def test_parse_response_valid(self):
        agent = SampleAgent()
        result = agent.parse_response(
            '{"operation": "CREATE", "goal": "FEATURE_ADD", "confidence": 0.9}',
            "test"
        )
        assert result is not None
        assert result.operation == "CREATE"
        assert result.confidence == 0.9

    def test_parse_response_invalid(self):
        agent = SampleAgent()
        result = agent.parse_response("not json at all", "test")
        assert result is None


# ============================================================
#  AGENT RESULT TESTS
# ============================================================

class TestAgentResult:
    """Tests para AgentResult."""

    def test_success_result(self):
        r = AgentResult(success=True, data={"key": "value"}, source="llm", duration_ms=150)
        assert r.success is True
        assert r.data["key"] == "value"
        assert r.source == "llm"
        assert r.cache_hit is False

    def test_fallback_result(self):
        r = AgentResult(success=True, data=None, source="fallback")
        assert r.source == "fallback"

    def test_error_result(self):
        r = AgentResult(success=False, data=None, source="error", error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_cache_hit_result(self):
        r = AgentResult(success=True, data=None, source="cache", cache_hit=True)
        assert r.cache_hit is True

    def test_repr(self):
        r = AgentResult(success=True, source="llm", duration_ms=100)
        assert "success=True" in repr(r)
        assert "llm" in repr(r)


# ============================================================
#  AGENT CACHE TESTS
# ============================================================

class TestAgentCache:
    """Tests para AgentCache."""

    def test_cache_miss(self):
        cache = AgentCache()
        result = cache.get("test_agent", "hello")
        assert result is None

    def test_cache_put_and_get(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput(operation="CREATE"))
        result = cache.get("test_agent", "hello")
        assert result is not None
        assert result.operation == "CREATE"

    def test_cache_different_agents(self):
        cache = AgentCache()
        cache.put("agent_a", "hello", IntentOutput(operation="CREATE"))
        cache.put("agent_b", "hello", IntentOutput(operation="DELETE"))

        result_a = cache.get("agent_a", "hello")
        result_b = cache.get("agent_b", "hello")
        assert result_a.operation == "CREATE"
        assert result_b.operation == "DELETE"

    def test_cache_different_inputs(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput(operation="CREATE"))
        result = cache.get("test_agent", "goodbye")
        assert result is None

    def test_cache_stats(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput())
        cache.get("test_agent", "hello")   # hit
        cache.get("test_agent", "world")   # miss

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_clear(self):
        cache = AgentCache()
        cache.put("test_agent", "hello", IntentOutput())
        cache.clear()
        result = cache.get("test_agent", "hello")
        assert result is None

    def test_cache_max_size_eviction(self):
        cache = AgentCache(max_size=3)
        cache.put("a", "1", IntentOutput(operation="A1"))
        cache.put("b", "2", IntentOutput(operation="B2"))
        cache.put("c", "3", IntentOutput(operation="C3"))
        # This should trigger eviction
        cache.put("d", "4", IntentOutput(operation="D4"))
        # Cache should have max 3 entries (one was evicted)
        assert len(cache._cache) <= 3

    def test_cache_ttl_expiration(self):
        cache = AgentCache(ttl_seconds=0)  # Expira inmediatamente
        cache.put("test_agent", "hello", IntentOutput())
        time.sleep(0.01)
        result = cache.get("test_agent", "hello")
        assert result is None  # Should be expired

    def test_cache_with_dataclass_input(self):
        cache = AgentCache()
        inp = IntentInput(message="Create login", context="web")
        cache.put("intent", inp, IntentOutput(operation="CREATE"))
        result = cache.get("intent", inp)
        assert result is not None

    def test_cache_with_dict_input(self):
        cache = AgentCache()
        inp = {"key": "value", "num": 42}
        cache.put("test", inp, IntentOutput())
        result = cache.get("test", inp)
        assert result is not None


# ============================================================
#  AGENT RUNNER TESTS
# ============================================================

class TestAgentRunner:
    """Tests para AgentRunner."""

    def _make_mock_ai(self, response='{"operation": "CREATE", "goal": "FEATURE_ADD", "confidence": 0.9}'):
        """Crea un MiniAIEngine mock."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = response
        return mock_ai

    def test_runner_with_fallback_no_ai(self):
        """Runner sin IA debe usar fallback."""
        runner = AgentRunner(mini_ai=None, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "Create a user")

        assert result.success is True
        assert result.source == "fallback"
        assert result.data.operation == "SEARCH"

    def test_runner_with_llm_success(self):
        """Runner con IA que responde correctamente."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "Create a login page")

        assert result.success is True
        assert result.source == "llm"
        assert result.data.operation == "CREATE"
        assert result.data.confidence == 0.9

    def test_runner_with_llm_failure_then_fallback(self):
        """Runner donde LLM falla, debe usar fallback."""
        mock_ai = MagicMock()
        mock_ai.is_loaded = True
        mock_ai._call_llm.return_value = None  # LLM returns nothing

        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.success is True
        assert result.source == "fallback"

    def test_runner_with_invalid_response_then_fallback(self):
        """Runner donde LLM devuelve respuesta inválida."""
        mock_ai = self._make_mock_ai(response="not valid json at all")
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.source == "fallback"

    def test_runner_with_cache_hit(self):
        """Runner con cache habilitado debe hacer hit en segunda llamada."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        # Primera llamada: cache miss → LLM
        result1 = runner.run(agent, "Create a login")
        assert result1.source == "llm"
        assert result1.cache_hit is False

        # Segunda llamada: cache hit
        result2 = runner.run(agent, "Create a login")
        assert result2.source == "cache"
        assert result2.cache_hit is True

    def test_runner_with_cache_disabled(self):
        """Runner con cache deshabilitado no debe cachear."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = SampleAgent()

        result1 = runner.run(agent, "Create a login")
        result2 = runner.run(agent, "Create a login")

        # Ambas llamadas van al LLM (no hay cache)
        assert result1.source == "llm"
        assert result2.source == "llm"

    def test_runner_stats(self):
        """Runner debe trackear estadísticas."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        runner.run(agent, "test1")
        runner.run(agent, "test1")  # cache hit
        runner.run(agent, "test2")  # cache miss

        stats = runner.stats
        assert stats["total_calls"] == 3
        assert stats["cache_hits"] == 1
        assert stats["llm_calls"] >= 2

    def test_runner_clear_cache(self):
        """Runner.clear_cache debe limpiar el cache."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=True)
        agent = SampleAgent()

        runner.run(agent, "test")
        runner.clear_cache()

        result = runner.run(agent, "test")
        assert result.source == "llm"  # No cache hit

    def test_runner_update_engines(self):
        """Runner.update_engines debe actualizar referencias."""
        runner = AgentRunner(mini_ai=None)
        assert runner._mini_ai is None

        mock_ai = self._make_mock_ai()
        runner.update_engines(mini_ai=mock_ai)
        assert runner._mini_ai is mock_ai

    def test_broken_agent_always_fallback(self):
        """Agente con parse_response que siempre falla."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai, enable_cache=False)
        agent = BrokenAgent()
        result = runner.run(agent, "test")

        assert result.source == "fallback"

    def test_runner_duration_tracked(self):
        """Runner debe trackear duración."""
        runner = AgentRunner(mini_ai=None, enable_cache=False)
        agent = SampleAgent()
        result = runner.run(agent, "test")

        assert result.duration_ms >= 0

    def test_run_raw_without_ai(self):
        """run_raw sin IA debe retornar None."""
        runner = AgentRunner(mini_ai=None)
        result = runner.run_raw("system", "user")
        assert result is None

    def test_run_raw_with_ai(self):
        """run_raw con IA debe llamar al LLM."""
        mock_ai = self._make_mock_ai()
        runner = AgentRunner(mini_ai=mock_ai)
        result = runner.run_raw("system", "user")
        assert result is not None
        mock_ai._call_llm.assert_called_once()


# ============================================================
#  PROMPT BUILDER TESTS
# ============================================================

class TestPromptBuilder:
    """Tests para PromptBuilder."""

    def test_build_simple(self):
        sys, user = PromptBuilder.build(
            "You are helpful.", "Process: {message}", {"message": "hello"}
        )
        assert sys == "You are helpful."
        assert user == "Process: hello"

    def test_build_multiple_vars(self):
        sys, user = PromptBuilder.build(
            "System", "Task: {task}, Lang: {language}",
            {"task": "generate", "language": "python"}
        )
        assert "generate" in user
        assert "python" in user

    def test_build_missing_var(self):
        """Missing vars should remain as placeholders."""
        sys, user = PromptBuilder.build(
            "System", "Task: {task}, Missing: {missing}",
            {"task": "generate"}
        )
        assert "generate" in user
        assert "{missing}" in user

    def test_build_dict_value(self):
        sys, user = PromptBuilder.build(
            "System", "Data: {data}", {"data": {"key": "value"}}
        )
        assert "key" in user
        assert "value" in user

    def test_build_list_value(self):
        sys, user = PromptBuilder.build(
            "System", "Items: {items}", {"items": ["a", "b", "c"]}
        )
        assert "a" in user

    def test_add_context_to_prompt(self):
        prompt = "Base prompt"
        context = {"language": "python", "version": "3.12"}
        result = PromptBuilder.add_context_to_prompt(prompt, context)
        assert "language" in result
        assert "python" in result

    def test_add_context_empty(self):
        prompt = "Base prompt"
        result = PromptBuilder.add_context_to_prompt(prompt, {})
        assert result == "Base prompt"

    def test_add_context_truncation(self):
        prompt = "Base prompt"
        context = {"big": "x" * 1000}
        result = PromptBuilder.add_context_to_prompt(prompt, context, max_chars=100)
        assert len(result) < 200  # Should be truncated


# ============================================================
#  AGENT PROMPTS TESTS
# ============================================================

class TestAgentPrompts:
    """Tests para los system prompts predefinidos."""

    def test_intent_prompt_exists(self):
        assert AgentPrompts.INTENT_SYSTEM != ""
        assert AgentPrompts.INTENT_USER != ""

    def test_reasoning_prompts_exist(self):
        assert AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP != ""
        assert AgentPrompts.REASONING_SYSTEM_SELF_REFLECT != ""
        assert AgentPrompts.REASONING_SYSTEM_WITH_CONTEXT != ""

    def test_business_prompt_exists(self):
        assert AgentPrompts.BUSINESS_SYSTEM != ""

    def test_code_prompts_exist(self):
        assert AgentPrompts.CODE_SYSTEM_GENERATE != ""
        assert AgentPrompts.CODE_SYSTEM_TRANSFORM != ""
        assert AgentPrompts.CODE_SYSTEM_SCAFFOLD != ""

    def test_automation_prompt_exists(self):
        assert AgentPrompts.AUTOMATION_SYSTEM != ""

    def test_validation_prompt_exists(self):
        assert AgentPrompts.VALIDATION_SYSTEM != ""

    def test_intent_prompt_contains_json_instruction(self):
        assert "JSON" in AgentPrompts.INTENT_SYSTEM

    def test_validation_prompt_contains_risk_score(self):
        assert "risk_score" in AgentPrompts.VALIDATION_SYSTEM


# ============================================================
#  INTEGRATION: ORCHESTRATOR CABLEADO
# ============================================================

class TestOrchestratorCableado:
    """Tests de integración del Agent Framework con el Orchestrator."""

    def test_orchestrator_has_agent_runner(self):
        """El orchestrator debe tener _agent_runner cableado."""
        from src.core.orchestrator import TitanOrchestrator
        orch = TitanOrchestrator()
        assert hasattr(orch, '_agent_runner')
        assert isinstance(orch._agent_runner, AgentRunner)

    def test_orchestrator_agent_runner_has_ai(self):
        """El AgentRunner del orchestrator debe tener MiniAI cableado."""
        from src.core.orchestrator import TitanOrchestrator
        orch = TitanOrchestrator()
        # MiniAI puede estar loaded o no, pero debe existir la referencia
        assert orch._agent_runner._mini_ai is not None or orch._ai is not None

    def test_orchestrator_agent_runner_has_cache(self):
        """El AgentRunner del orchestrator debe tener cache habilitado."""
        from src.core.orchestrator import TitanOrchestrator
        orch = TitanOrchestrator()
        assert orch._agent_runner._cache is not None
        assert orch._agent_runner._enable_cache is True

    def test_orchestrator_status_includes_agent_framework(self):
        """get_system_status() debe incluir agent_framework stats."""
        from src.core.orchestrator import TitanOrchestrator
        import asyncio
        orch = TitanOrchestrator()
        status = asyncio.get_event_loop().run_until_complete(orch.get_system_status())
        assert "agent_framework" in status
        assert "runner_stats" in status["agent_framework"]
        assert "cache_stats" in status["agent_framework"]
