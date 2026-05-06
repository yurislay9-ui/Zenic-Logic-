"""
Tests for Layer 9: Infrastructure & Resilience agents (A44-A48).

All 5 agents tested:
  - A44 AgentRunner (agent execution with resilience)
  - A45 HealthMonitorAgent (health tracking)
  - A46 AuditLoggerAgent (audit logging)
  - A47 CircuitBreakerManagerAgent (circuit breaker management)
  - A48 BilingualRouter (language detection)
"""

import pytest
import time
import threading

from src.core.agents_v2.infrastructure import (
    AgentRunner,
    HealthMonitorAgent,
    AuditLoggerAgent,
    CircuitBreakerManagerAgent,
)
from src.core.agents_v2.understanding import BilingualRouter
from src.core.agents_v2.resilience import (
    BaseAgent,
    CircuitBreakerManager,
    GlobalHealthMonitor,
    AuditLogger,
    AuditEntry,
    AgentCircuitBreaker,
    CircuitState,
    BulkheadManager,
    AgentRetryConfig,
)
from src.core.agents_v2.schemas import (
    AgentResult,
    HealthSnapshot,
    LanguageResult,
)


# ======================================================================
# Helper: Simple test agent
# ======================================================================

class EchoAgent(BaseAgent[AgentResult]):
    """Simple agent that echoes input for testing."""

    def __init__(self, name="EchoAgent", **kwargs):
        super().__init__(name=name, **kwargs)

    def execute(self, input_data):
        return AgentResult(success=True, data=input_data, source="deterministic")

    def fallback(self, input_data):
        return AgentResult(success=False, source="fallback")


class FailingAgent(BaseAgent[AgentResult]):
    """Agent that always fails for testing."""

    def __init__(self, name="FailingAgent", **kwargs):
        # Use zero-delay retry config for tests
        if "retry_config" not in kwargs:
            kwargs["retry_config"] = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        super().__init__(name=name, **kwargs)

    def execute(self, input_data):
        raise RuntimeError("Intentional failure for testing")

    def fallback(self, input_data):
        return AgentResult(success=False, source="fallback", error="Intentional failure")


# ======================================================================
# A44 AgentRunner Tests
# ======================================================================

class TestAgentRunner:
    """A44: Execute agents with full resilience."""

    def setup_method(self):
        self.runner = AgentRunner()
        self.echo = EchoAgent()
        self.runner.register(self.echo)

    def test_register_agent(self):
        assert "EchoAgent" in self.runner.registered_names

    def test_register_many(self):
        another = EchoAgent(name="AnotherAgent")
        self.runner.register_many([another])
        assert "AnotherAgent" in self.runner.registered_names

    def test_get_agent(self):
        agent = self.runner.get_agent("EchoAgent")
        assert agent is not None
        assert agent.name == "EchoAgent"

    def test_get_agent_not_found(self):
        agent = self.runner.get_agent("NonExistent")
        assert agent is None

    def test_execute_by_name(self):
        result = self.runner.execute({
            "agent_name": "EchoAgent",
            "input": "hello world",
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_execute_by_instance(self):
        direct_echo = EchoAgent(name="DirectEcho")
        result = self.runner.execute({
            "agent": direct_echo,
            "input": "direct test",
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_execute_nonexistent_agent(self):
        result = self.runner.execute({
            "agent_name": "GhostAgent",
            "input": "test",
        })
        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_execute_invalid_input(self):
        result = self.runner.execute("not a dict")
        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_run_agent_convenience(self):
        raw = self.runner.run_agent("EchoAgent", "convenience test")
        assert isinstance(raw, dict)
        assert raw.get("success") is True

    def test_run_agent_not_registered(self):
        raw = self.runner.run_agent("GhostAgent", "test")
        assert raw["success"] is False
        assert "not registered" in raw["error"].lower()

    def test_fallback_returns_failure(self):
        result = self.runner.fallback(None)
        assert isinstance(result, AgentResult)
        assert result.success is False
        assert result.source == "fallback"


# ======================================================================
# A45 HealthMonitorAgent Tests
# ======================================================================

class TestHealthMonitorAgent:
    """A45: Track health of all agents and LLM."""

    def setup_method(self):
        self.monitor = HealthMonitorAgent()

    def test_system_snapshot(self):
        result = self.monitor.execute(None)
        assert isinstance(result, HealthSnapshot)
        assert result.healthy is True  # No data = healthy by default

    def test_system_snapshot_dict_input(self):
        result = self.monitor.execute({"action": "system"})
        assert isinstance(result, HealthSnapshot)

    def test_system_snapshot_all_string(self):
        result = self.monitor.execute("all")
        assert isinstance(result, HealthSnapshot)

    def test_agent_snapshot(self):
        # Record some data first
        self.monitor.record_call("TestAgent", success=True, latency_s=0.1)
        result = self.monitor.execute({"action": "agent", "agent_name": "TestAgent"})
        assert isinstance(result, HealthSnapshot)
        assert "TestAgent" in result.success_rates
        assert result.success_rates["TestAgent"] == 1.0

    def test_agent_snapshot_by_string(self):
        self.monitor.record_call("MyAgent", success=True, latency_s=0.05)
        result = self.monitor.execute("MyAgent")
        assert isinstance(result, HealthSnapshot)
        assert "MyAgent" in result.success_rates

    def test_unhealthy_snapshot(self):
        # Record failures
        for _ in range(10):
            self.monitor.record_call("SickAgent", success=False, latency_s=1.0)
        result = self.monitor.execute({"action": "unhealthy"})
        assert isinstance(result, HealthSnapshot)

    def test_record_call_and_check_health(self):
        self.monitor.record_call("GoodAgent", success=True, latency_s=0.01)
        assert self.monitor.is_healthy("GoodAgent") is True

    def test_is_healthy_unknown_agent(self):
        assert self.monitor.is_healthy("UnknownAgent") is True  # No data = healthy

    def test_fallback_returns_healthy(self):
        result = self.monitor.fallback(None)
        assert isinstance(result, HealthSnapshot)
        assert result.healthy is True

    def test_snapshot_has_timestamp(self):
        result = self.monitor.execute("all")
        assert result.timestamp > 0


# ======================================================================
# A46 AuditLoggerAgent Tests
# ======================================================================

class TestAuditLoggerAgent:
    """A46: Log all agent decisions for post-mortem analysis."""

    def setup_method(self):
        self.auditor = AuditLoggerAgent()

    def test_record_entry(self):
        result = self.auditor.execute({
            "action": "record",
            "agent": "TestAgent",
            "source": "deterministic",
            "duration_ms": 10.5,
            "retry_count": 0,
        })
        assert isinstance(result, AgentResult)
        assert result.success is True

    def test_record_entry_with_dict(self):
        result = self.auditor.execute({
            "action": "record",
            "entry": {
                "agent": "TestAgent2",
                "source": "fallback",
                "duration_ms": 5.0,
            },
        })
        assert result.success is True

    def test_record_audit_entry_object(self):
        entry = AuditEntry(
            agent="DirectEntry",
            source="deterministic",
            duration_ms=3.0,
        )
        result = self.auditor.execute({
            "action": "record",
            "entry": entry,
        })
        assert result.success is True

    def test_query_entries(self):
        # Record some entries first
        for i in range(5):
            self.auditor.execute({
                "action": "record",
                "agent": f"QueryAgent_{i}",
                "source": "deterministic",
                "duration_ms": float(i),
            })

        result = self.auditor.execute({
            "action": "query",
            "count": 3,
        })
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) <= 3

    def test_query_by_agent(self):
        self.auditor.record_decision(
            agent_name="SpecificAgent",
            source="deterministic",
            duration_ms=10.0,
        )

        result = self.auditor.execute({
            "action": "query",
            "agent_name": "SpecificAgent",
            "count": 10,
        })
        assert result.success is True
        assert isinstance(result.data, list)

    def test_analyze_failure_pattern(self):
        # Record some failures
        for _ in range(5):
            self.auditor.record_decision(
                agent_name="FailingAgent",
                source="fallback",
                duration_ms=100.0,
            )

        result = self.auditor.execute({
            "action": "analyze",
            "agent_name": "FailingAgent",
        })
        assert result.success is True
        assert "risk_level" in result.data
        assert "failure_rate" in result.data

    def test_stats(self):
        self.auditor.record_decision(
            agent_name="StatsAgent",
            source="deterministic",
            duration_ms=5.0,
        )

        result = self.auditor.execute({"action": "stats"})
        assert result.success is True
        assert "agents_tracked" in result.data
        assert "total_entries" in result.data

    def test_unknown_action(self):
        result = self.auditor.execute({"action": "invalid_action"})
        assert result.success is False
        assert "unknown" in result.error.lower()

    def test_non_dict_input(self):
        result = self.auditor.execute("not a dict")
        assert isinstance(result, AgentResult)
        assert result.success is True  # Fallback is non-fatal

    def test_record_decision_convenience(self):
        self.auditor.record_decision(
            agent_name="ConvenienceAgent",
            source="deterministic",
            duration_ms=7.5,
            retry_count=0,
            circuit_breaker_state="CLOSED",
        )
        # Verify it was recorded
        recent = self.auditor.get_recent("ConvenienceAgent", 1)
        assert len(recent) >= 1
        assert recent[0].agent == "ConvenienceAgent"

    def test_get_failure_pattern_convenience(self):
        pattern = self.auditor.get_failure_pattern()
        assert "risk_level" in pattern

    def test_fallback_non_fatal(self):
        result = self.auditor.fallback(None)
        assert result.success is True
        assert result.source == "fallback"


# ======================================================================
# A47 CircuitBreakerManagerAgent Tests
# ======================================================================

class TestCircuitBreakerManagerAgent:
    """A47: Manage circuit breakers per agent."""

    def setup_method(self):
        self.cb_agent = CircuitBreakerManagerAgent()

    def test_check_initial_state(self):
        result = self.cb_agent.execute({
            "action": "check",
            "agent_name": "NewAgent",
        })
        assert result.success is True
        assert result.data["can_call"] is True

    def test_check_no_agent_name(self):
        result = self.cb_agent.execute({"action": "check"})
        assert result.success is False

    def test_record_success(self):
        result = self.cb_agent.execute({
            "action": "record_success",
            "agent_name": "TestAgent",
        })
        assert result.success is True

    def test_record_failure(self):
        result = self.cb_agent.execute({
            "action": "record_failure",
            "agent_name": "TestAgent",
        })
        assert result.success is True

    def test_circuit_opens_after_failures(self):
        """Circuit should open after failure_threshold consecutive failures."""
        # Use a name that maps to "understanding" group (threshold=3)
        agent_name = "A01_IntentClassifier"
        for _ in range(3):
            self.cb_agent.execute({
                "action": "record_failure",
                "agent_name": agent_name,
            })

        result = self.cb_agent.execute({
            "action": "check",
            "agent_name": agent_name,
        })
        assert result.data["can_call"] is False

    def test_reset_breaker(self):
        agent_name = "A02_EntityExtractor"  # understanding group, threshold=3
        # Trip the breaker
        for _ in range(3):
            self.cb_agent.execute({
                "action": "record_failure",
                "agent_name": agent_name,
            })

        # Reset it
        result = self.cb_agent.execute({
            "action": "reset",
            "agent_name": agent_name,
        })
        assert result.success is True

        # Should be available again
        check = self.cb_agent.execute({
            "action": "check",
            "agent_name": agent_name,
        })
        assert check.data["can_call"] is True

    def test_reset_all(self):
        # Trip some breakers (use understanding group names, threshold=3)
        for _ in range(3):
            self.cb_agent.execute({"action": "record_failure", "agent_name": "A01_Intent"})
            self.cb_agent.execute({"action": "record_failure", "agent_name": "A02_Entity"})

        # Reset all
        result = self.cb_agent.execute({"action": "reset_all"})
        assert result.success is True

    def test_stats_per_agent(self):
        self.cb_agent.execute({"action": "record_success", "agent_name": "StatsAgent"})
        result = self.cb_agent.execute({
            "action": "stats",
            "agent_name": "StatsAgent",
        })
        assert result.success is True
        assert "state" in result.data

    def test_stats_all(self):
        self.cb_agent.execute({"action": "record_success", "agent_name": "AgentA"})
        result = self.cb_agent.execute({"action": "stats"})
        assert result.success is True
        assert isinstance(result.data, dict)

    def test_state_query(self):
        result = self.cb_agent.execute({
            "action": "state",
            "agent_name": "StateAgent",
        })
        assert result.success is True
        assert result.data["state"] in ("CLOSED", "OPEN", "HALF_OPEN")

    def test_state_no_agent_name(self):
        result = self.cb_agent.execute({"action": "state"})
        assert result.success is False

    def test_unknown_action(self):
        result = self.cb_agent.execute({"action": "fly_to_moon"})
        assert result.success is False
        assert "unknown" in result.error.lower()

    def test_non_dict_input(self):
        result = self.cb_agent.execute("bad input")
        assert isinstance(result, AgentResult)
        assert result.success is True  # Fallback assumes CLOSED

    def test_can_call_convenience(self):
        assert self.cb_agent.can_call("AnyAgent") is True

    def test_get_breaker_state_convenience(self):
        state = self.cb_agent.get_breaker_state("AnyAgent")
        assert state in ("CLOSED", "OPEN", "HALF_OPEN")

    def test_fallback_returns_closed(self):
        result = self.cb_agent.fallback(None)
        assert result.success is True
        assert result.data["state"] == "CLOSED"


# ======================================================================
# A48 BilingualRouter Tests
# ======================================================================

class TestBilingualRouter:
    """A48: Detect language and route to EN/ES handlers."""

    def setup_method(self):
        self.router = BilingualRouter()

    def test_detect_english(self):
        result = self.router.execute("Create a new feature for the application")
        assert isinstance(result, LanguageResult)
        assert result.lang == "en"
        assert result.source == "deterministic"

    def test_detect_spanish(self):
        result = self.router.execute("Crear una nueva funcionalidad para la aplicación")
        assert isinstance(result, LanguageResult)
        assert result.lang == "es"

    def test_detect_spanish_common_words(self):
        result = self.router.execute("Necesito crear un proyecto de base de datos")
        assert result.lang == "es"

    def test_detect_english_short(self):
        result = self.router.execute("Fix the bug")
        assert result.lang == "en"

    def test_empty_input_fallback(self):
        result = self.router.execute("")
        assert isinstance(result, LanguageResult)
        assert result.source == "fallback"
        assert result.lang == "en"

    def test_none_input_fallback(self):
        result = self.router.execute(None)
        assert isinstance(result, LanguageResult)
        assert result.lang == "en"

    def test_numeric_input(self):
        result = self.router.execute(12345)
        assert isinstance(result, LanguageResult)

    def test_confidence_range(self):
        result = self.router.execute("Create a new module")
        assert 0.0 <= result.confidence <= 1.0

    def test_text_preserved(self):
        text = "Hello world this is a test"
        result = self.router.execute(text)
        assert result.text == text

    def test_fallback_returns_english(self):
        result = self.router.fallback(None)
        assert result.lang == "en"
        assert result.confidence == 0.5
        assert result.source == "fallback"


# ======================================================================
# Integration: Full Infrastructure Pipeline Test
# ======================================================================

class TestInfrastructurePipeline:
    """End-to-end infrastructure pipeline through all Layer 9 agents."""

    def test_full_resilience_pipeline(self):
        """Agent execution → health check → audit → circuit breaker verification."""
        # 1. Set up shared infrastructure
        fast_retry = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        cb_manager = CircuitBreakerManager()
        health_monitor = GlobalHealthMonitor()
        audit_logger = AuditLogger()

        # 2. Create agents with shared infrastructure
        echo = EchoAgent(
            name="PipelineEcho",
            circuit_breaker_manager=cb_manager,
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )

        runner = AgentRunner(
            circuit_breaker_manager=cb_manager,
            bulkhead_manager=BulkheadManager(),
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )
        runner.register(echo)

        # 3. Execute agent through runner
        result = runner.execute({
            "agent_name": "PipelineEcho",
            "input": "pipeline test",
        })
        assert result.success is True

        # 4. Check health
        health_agent = HealthMonitorAgent(health_monitor=health_monitor)
        health_snap = health_agent.execute("PipelineEcho")
        assert isinstance(health_snap, HealthSnapshot)

        # 5. Check audit trail
        audit_agent = AuditLoggerAgent(audit_logger=audit_logger)
        audit_result = audit_agent.execute({"action": "query", "count": 5})
        assert audit_result.success is True

        # 6. Check circuit breaker state
        cb_agent = CircuitBreakerManagerAgent(circuit_breaker_manager=cb_manager)
        cb_result = cb_agent.execute({
            "action": "check",
            "agent_name": "PipelineEcho",
        })
        assert cb_result.data["can_call"] is True

    def test_circuit_breaker_blocks_failing_agent(self):
        """Circuit breaker should block agent after consecutive failures."""
        fast_retry = AgentRetryConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=False)
        cb_manager = CircuitBreakerManager()
        health_monitor = GlobalHealthMonitor()
        audit_logger = AuditLogger()

        # Use a name that maps to "understanding" group (threshold=3)
        failing = FailingAgent(
            name="A01_IntentClassifier",
            circuit_breaker_manager=cb_manager,
            health_monitor=health_monitor,
            audit_logger=audit_logger,
            retry_config=fast_retry,
        )

        # Run the failing agent multiple times to trip the breaker
        for _ in range(5):
            failing.run("test input")

        # Check circuit breaker using the SAME manager
        cb_agent = CircuitBreakerManagerAgent(circuit_breaker_manager=cb_manager)
        cb_result = cb_agent.execute({
            "action": "check",
            "agent_name": "A01_IntentClassifier",
        })
        assert cb_result.data["can_call"] is False

    def test_bilingual_router_in_pipeline(self):
        """BilingualRouter should correctly route mixed-language inputs."""
        router = BilingualRouter()

        # English input
        en_result = router.execute("Create a payment module")
        assert en_result.lang == "en"

        # Spanish input
        es_result = router.execute("Crear un módulo de pago")
        assert es_result.lang == "es"
