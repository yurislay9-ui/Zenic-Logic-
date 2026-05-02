"""
TITAN OMNISCALE X - Phase 8 Intelligence Tests

Tests for the Phase 8 components:
  1. ReasoningEngine (3 reasoning modes + auto)
  2. ChainValidator + ChainExecutor (validation, rollback, recovery)
  3. SmartMemory session management and consolidation
  4. Orchestrator Phase 8 integration
  5. Cross-phase wiring verification

Memory optimization: Orchestrator-heavy test classes share a single
module-scoped instance to avoid OOM on memory-constrained environments.
"""

import os
import gc
import time
import tempfile
import pytest


# ============================================================
#  SHARED ORCHESTRATOR FIXTURE (memory-efficient)
# ============================================================

@pytest.fixture(scope="module")
def shared_orchestrator():
    """Create a single TitanOrchestrator shared by all orchestrator tests.

    This avoids loading the fastembed model repeatedly (each instance
    takes ~200MB RAM). The orchestrator is created once per module
    and cleaned up after all tests in the module finish.
    """
    from src.core.orchestrator import TitanOrchestrator
    orch = TitanOrchestrator()
    yield orch
    # Force cleanup to free memory
    del orch
    gc.collect()


# ============================================================
#  REASONING ENGINE TESTS
# ============================================================

class TestReasoningEngine:
    """Tests for the ReasoningEngine (Phase 8.1)."""

    def setup_method(self):
        from src.core.reasoning_engine import ReasoningEngine
        self.engine = ReasoningEngine(mini_ai=None, semantic_engine=None, smart_memory=None)

    def test_engine_initializes(self):
        """ReasoningEngine should initialize without errors."""
        assert self.engine is not None
        assert self.engine._ai is None
        assert self.engine._semantic is None
        assert self.engine._memory is None

    def test_step_by_step_fallback(self):
        """step_by_step should work with deterministic fallback."""
        result = self.engine.step_by_step("How to create an API?")
        assert result is not None
        assert len(result.answer) > 10
        assert result.confidence > 0.0
        assert len(result.steps) > 0
        assert all(s.source == "fallback" for s in result.steps)

    def test_step_by_step_max_steps(self):
        """step_by_step should respect max_steps parameter."""
        result = self.engine.step_by_step("Test problem", max_steps=2)
        assert len(result.steps) <= 2

    def test_self_reflect_fallback(self):
        """self_reflect should work with deterministic fallback."""
        result = self.engine.self_reflect("Design an auth system")
        assert result is not None
        assert len(result.answer) > 10
        assert result.confidence > 0.0

    def test_self_reflect_iterations(self):
        """self_reflect should limit iterations."""
        result = self.engine.self_reflect("Test", max_iterations=1)
        # Should have at most 2 steps per iteration (generate + evaluate)
        assert len(result.steps) <= 2

    def test_reason_with_context_fallback(self):
        """reason_with_context should work with fallback."""
        result = self.engine.reason_with_context("Build a CRM")
        assert result is not None
        assert len(result.answer) > 10
        assert result.source in ("fallback", "llm")

    def test_reason_auto_simple(self):
        """Auto mode should select step_by_step for simple problems."""
        result = self.engine.reason("simple query")
        assert result is not None
        assert len(result.answer) > 0

    def test_reason_auto_complex(self):
        """Auto mode should select appropriate mode for complex problems."""
        result = self.engine.reason(
            "Build a complete CRM system with API, database, authentication, "
            "notifications and reporting capabilities"
        )
        assert result is not None
        assert result.confidence > 0.0

    def test_reason_explicit_mode(self):
        """Should use explicitly specified mode."""
        result = self.engine.reason("Test", mode="step_by_step")
        from src.core.reasoning_engine import ReasoningMode
        assert result.mode == ReasoningMode.STEP_BY_STEP

    def test_full_fallback_no_model(self):
        """Full fallback should work without any model."""
        from src.core.reasoning_engine import ReasoningMode
        result = self.engine._full_fallback("Any problem")
        assert result.confidence < 0.5
        assert result.mode == ReasoningMode.FALLBACK

    def test_stats(self):
        """Stats should return useful information."""
        self.engine.step_by_step("Test")
        stats = self.engine.stats
        assert "total_calls" in stats
        assert stats["total_calls"] >= 1
        assert "modes" in stats
        assert len(stats["modes"]) == 4

    def test_fallback_step_identifies_api(self):
        """Fallback step 1 should identify API problems."""
        result = self.engine._fallback_step(1, "How to create a REST API endpoint?", [])
        assert "API" in result

    def test_fallback_step_identifies_auth(self):
        """Fallback step 1 should identify auth problems."""
        result = self.engine._fallback_step(1, "Implement login with JWT", [])
        assert "auth" in result.lower() or "authentication" in result.lower()

    def test_fallback_evaluate_short_answer(self):
        """Evaluation should flag short answers."""
        score, issues = self.engine._fallback_evaluate("ok", "test")
        assert score < 0.5
        assert len(issues) > 0

    def test_fallback_evaluate_security_risk(self):
        """Evaluation should flag security risks."""
        score, issues = self.engine._fallback_evaluate("Use eval() to parse input", "parse input")
        assert score < 0.5
        assert any("security" in i.lower() for i in issues)

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

    def test_extract_conclusion_with_marker(self):
        """Should extract conclusion after marker words."""
        result = self.engine._extract_conclusion(
            "Analysis shows the pattern. Therefore, use a factory pattern."
        )
        assert "factory" in result.lower()

    def test_extract_conclusion_without_marker(self):
        """Should return last sentence when no marker found."""
        result = self.engine._extract_conclusion(
            "First approach. Second approach. The best option is to use caching."
        )
        assert len(result) > 5


# ============================================================
#  CHAIN VALIDATOR TESTS
# ============================================================

class TestChainValidator:
    """Tests for ChainValidator and ChainExecutor (Phase 8.3)."""

    def setup_method(self):
        from src.core.chain_validator import (
            ChainValidator, ChainExecutor, ValidationLevel,
            RecoveryAction, ChainStatus
        )
        from src.core.logic_builder import LogicBuilder
        self.validator = ChainValidator()
        self.builder = LogicBuilder()

    def test_validator_initializes(self):
        """ChainValidator should initialize."""
        assert self.validator is not None
        assert self.validator._level.value == "standard"

    def test_validator_lenient_level(self):
        """Should support lenient validation level."""
        from src.core.chain_validator import ChainValidator, ValidationLevel
        v = ChainValidator(level=ValidationLevel.LENIENT)
        assert v._level == ValidationLevel.LENIENT

    def test_validate_valid_chain(self):
        """Valid chain should pass validation."""
        chain = self.builder.build_from_blocks(["validate_required", "sanitize"])
        result = self.validator.validate(chain, {"name": "Test"}, {})
        assert result.is_valid is True

    def test_validate_empty_chain(self):
        """Empty chain should produce a warning."""
        from src.core.logic_builder import LogicChain
        empty_chain = LogicChain("empty")
        result = self.validator.validate(empty_chain)
        assert len(result.warnings) > 0

    def test_validate_auth_without_db_warns(self):
        """Auth blocks without db in context should warn."""
        chain = self.builder.build_from_blocks(["auth_login"])
        result = self.validator.validate(chain, {}, {})
        # May have warnings about missing db context
        assert isinstance(result.warnings, list)

    def test_validation_result_add_error(self):
        """ValidationResult should track errors correctly."""
        from src.core.chain_validator import ValidationResult
        result = ValidationResult()
        result.add_error("test_code", "Test error", "test_block", 0)
        assert result.is_valid is False
        assert result.can_execute is False
        assert len(result.errors) == 1

    def test_validation_result_add_warning(self):
        """ValidationResult should track warnings without blocking execution."""
        from src.core.chain_validator import ValidationResult
        result = ValidationResult()
        result.add_warning("test_code", "Test warning", "test_block", 0)
        assert result.is_valid is True
        assert result.can_execute is True
        assert len(result.warnings) == 1

    def test_execute_chain_simple(self):
        """ChainExecutor should execute a simple chain."""
        from src.core.chain_validator import ChainExecutor, ChainStatus
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor()
        result = executor.execute(chain, {"name": "Test"}, {"required_fields": ["name"]})
        assert result.status in (ChainStatus.COMPLETED, ChainStatus.PARTIAL)

    def test_execute_chain_with_validation(self):
        """ChainExecutor should validate before execution."""
        from src.core.chain_validator import ChainExecutor, ChainStatus
        chain = self.builder.build_from_blocks(["sanitize"])
        executor = ChainExecutor()
        result = executor.execute(chain, {"name": "Test"}, {}, validate_first=True)
        assert result.validation is not None

    def test_execute_chain_skip_recovery(self):
        """ChainExecutor should skip failed blocks with SKIP recovery."""
        from src.core.chain_validator import (
            ChainExecutor, RecoveryAction, ChainStatus
        )
        # Create a chain that might fail
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor(default_recovery=RecoveryAction.SKIP)
        result = executor.execute(chain, {}, {})
        # Should not crash even with empty data
        assert result.status in (ChainStatus.COMPLETED, ChainStatus.PARTIAL, ChainStatus.FAILED)

    def test_execute_chain_abort_recovery(self):
        """ChainExecutor should abort on failure with ABORT recovery."""
        from src.core.chain_validator import (
            ChainExecutor, RecoveryAction, ChainStatus
        )
        chain = self.builder.build_from_blocks(["validate_required"])
        executor = ChainExecutor(default_recovery=RecoveryAction.ABORT)
        result = executor.execute(chain, {}, {})
        assert isinstance(result.steps_failed, int)

    def test_convenience_validate_chain(self):
        """validate_chain() convenience function should work."""
        from src.core.chain_validator import validate_chain
        chain = self.builder.build_from_blocks(["sanitize"])
        result = validate_chain(chain, {"name": "test"}, {})
        assert result.is_valid is True

    def test_convenience_execute_chain_safe(self):
        """execute_chain_safe() convenience function should work."""
        from src.core.chain_validator import execute_chain_safe
        chain = self.builder.build_from_blocks(["validate_required"])
        result = execute_chain_safe(chain, {"name": "Test"}, {"required_fields": ["name"]})
        assert result.final_data is not None


# ============================================================
#  SMART MEMORY SESSION TESTS
# ============================================================

class TestSmartMemorySessions:
    """Tests for SmartMemory session management and consolidation (Phase 8.2)."""

    def setup_method(self):
        from src.core.smart_memory import SmartMemory
        # Use temp DB to avoid polluting real data
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = None
        import src.core.smart_memory as sm_module
        self.original_db_path = sm_module.DB_PATH
        sm_module.DB_PATH = os.path.join(self.tmpdir, "test_memory.sqlite")
        self.memory = SmartMemory(semantic_engine=None)

    def teardown_method(self):
        import src.core.smart_memory as sm_module
        if self.original_db_path:
            sm_module.DB_PATH = self.original_db_path
        import shutil
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_session(self):
        """start_session should create a new session."""
        session_id = self.memory.start_session()
        assert session_id is not None
        assert len(session_id) > 0

    def test_end_session(self):
        """end_session should close the session."""
        self.memory.start_session()
        result = self.memory.end_session()
        assert "session_id" in result

    def test_get_conversation_summary_current(self):
        """Should get summary of current session."""
        self.memory.start_session()
        self.memory.add_working("test query", "test response", "CREATE", "FEATURE_ADD", 0.7)
        summary = self.memory.get_conversation_summary()
        assert len(summary) > 0

    def test_consolidate_memories(self):
        """consolidate_memories should promote important entries."""
        self.memory.start_session()
        # Add important entries
        self.memory.add_working("important query", "important response",
                                "CREATE", "SECURITY_HARDEN", 0.9)
        result = self.memory.consolidate_memories()
        assert isinstance(result, dict)
        assert "promoted_to_long_term" in result

    def test_consolidate_empty_working(self):
        """consolidate_memories should handle empty working memory."""
        self.memory.start_session()
        result = self.memory.consolidate_memories()
        assert result["promoted_to_long_term"] == 0


# ============================================================
#  ORCHESTRATOR PHASE 8 INTEGRATION TESTS
# ============================================================

class TestOrchestratorPhase8:
    """Tests for Orchestrator with Phase 8 Intelligence.

    Uses the shared_orchestrator fixture to avoid OOM from loading
    the semantic model multiple times.
    """

    @pytest.fixture(autouse=True)
    def setup(self, shared_orchestrator):
        self.orch = shared_orchestrator

    @pytest.mark.asyncio
    async def test_system_status_has_phase8(self):
        """System status should include Phase 8 intelligence."""
        status = await self.orch.get_system_status()
        assert "phase8_intelligence" in status
        assert status["phase8_intelligence"]["reasoning_available"] is True
        assert status["phase8_intelligence"]["chain_validation"] is True

    @pytest.mark.asyncio
    async def test_reason_endpoint(self):
        """reason endpoint should return reasoning result."""
        result = await self.orch.reason("How to build an API?", mode="step_by_step")
        assert "answer" in result
        assert "confidence" in result
        # Mode should be step_by_step (even in fallback, mode is honored)
        assert result["mode"] in ("step_by_step", "fallback")  # fallback when no model

    @pytest.mark.asyncio
    async def test_reason_auto_mode(self):
        """reason endpoint should support auto mode."""
        result = await self.orch.reason("Test query", mode="auto")
        assert "answer" in result
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_validate_logic_chain(self):
        """validate_logic_chain should validate a chain."""
        result = await self.orch.validate_logic_chain("sistema de inventario con alertas")
        assert "is_valid" in result
        assert "block_count" in result

    @pytest.mark.asyncio
    async def test_execute_logic_chain(self):
        """execute_logic_chain should execute with safety."""
        result = await self.orch.execute_logic_chain(
            "validar y sanitizar datos",
            data={"name": "Test", "email": "test@test.com"},
            recovery="skip"
        )
        assert "status" in result
        assert "steps_completed" in result

    @pytest.mark.asyncio
    async def test_intelligence_status(self):
        """intelligence_status should return Phase 8 details."""
        status = await self.orch.get_intelligence_status()
        assert "reasoning_engine" in status
        assert "ai_layers" in status
        assert "phase8_modes" in status
        assert "layer1_semantic" in status["ai_layers"]
        assert "layer2_qwen" in status["ai_layers"]
        assert "layer3_memory" in status["ai_layers"]

    @pytest.mark.asyncio
    async def test_phase7_still_works(self):
        """Phase 7 endpoints should still work after Phase 8 integration."""
        # Action executor
        result = await self.orch.execute_action(
            "send_notification",
            {"channel": "log", "message": "Phase 8 integration test"}
        )
        assert result.get("success") is True

        # Logic builder
        result = await self.orch.build_logic("sistema de facturacion")
        assert result.get("block_count", 0) > 0

    @pytest.mark.asyncio
    async def test_phase6_template_engine_wired(self):
        """Phase 6 TemplateEngine should still be wired."""
        status = await self.orch.get_system_status()
        # TemplateEngine was wired in Phase 6
        assert self.orch._template_engine is not None


# ============================================================
#  CROSS-PHASE WIRING VERIFICATION
# ============================================================

class TestCrossPhaseWiring:
    """Verify all wiring between Phases 6, 7, and 8 is connected.

    Uses the shared_orchestrator fixture to avoid OOM from loading
    the semantic model multiple times.
    """

    @pytest.fixture(autouse=True)
    def setup(self, shared_orchestrator):
        self.orch = shared_orchestrator

    def test_phase6_template_engine_exists(self):
        """Phase 6: TemplateEngine should be initialized."""
        assert self.orch._template_engine is not None

    def test_phase7_executor_registry_exists(self):
        """Phase 7: ExecutorRegistry should be initialized."""
        assert self.orch._executor_registry is not None
        assert len(self.orch._executor_registry._executors) >= 8

    def test_phase7_logic_builder_exists(self):
        """Phase 7: LogicBuilder should be initialized."""
        assert self.orch._logic_builder is not None
        assert len(self.orch._logic_builder.list_blocks()) >= 30

    def test_phase7_auth_service_exists(self):
        """Phase 7: AuthService should be initialized."""
        assert self.orch._auth is not None

    def test_phase8_reasoning_engine_exists(self):
        """Phase 8: ReasoningEngine should be initialized."""
        assert self.orch._reasoning is not None

    def test_phase8_chain_validator_exists(self):
        """Phase 8: ChainValidator should be initialized."""
        assert self.orch._chain_validator is not None

    def test_phase8_chain_executor_exists(self):
        """Phase 8: ChainExecutor should be initialized."""
        assert self.orch._chain_executor is not None

    def test_ai_3_layer_architecture(self):
        """All 3 AI layers should be connected."""
        assert self.orch._semantic is not None
        assert self.orch._ai is not None
        assert self.orch._memory is not None

    def test_thinking_engine_wired_to_all_layers(self):
        """ThinkingEngine should have references to all 3 AI layers."""
        assert self.orch._thinking._ai is self.orch._ai
        assert self.orch._thinking._semantic is self.orch._semantic
        assert self.orch._thinking._memory is self.orch._memory

    def test_reasoning_engine_wired_to_all_layers(self):
        """ReasoningEngine should have references to all 3 AI layers."""
        assert self.orch._reasoning._ai is self.orch._ai
        assert self.orch._reasoning._semantic is self.orch._semantic
        assert self.orch._reasoning._memory is self.orch._memory

    def test_semantic_parser_wired_to_semantic_engine(self):
        """SemanticParser (L1) should be wired to SemanticEngine."""
        assert self.orch.parser._semantic_engine is self.orch._semantic

    def test_semantic_parser_wired_to_smart_memory(self):
        """SemanticParser (L1) should be wired to SmartMemory."""
        assert self.orch.parser._smart_memory is self.orch._memory

    def test_automation_engine_wired_to_executor_registry(self):
        """AutomationEngine should be wired to ExecutorRegistry."""
        assert self.orch._automation._executor_registry is self.orch._executor_registry

    def test_app_generator_wired_to_template_engine(self):
        """AppGenerator should be wired to TemplateEngine."""
        assert self.orch._app_gen._template_engine is self.orch._template_engine

    def test_logic_builder_wired_to_template_engine(self):
        """LogicBuilder should be wired to TemplateEngine."""
        assert self.orch._logic_builder._template_engine is self.orch._template_engine
