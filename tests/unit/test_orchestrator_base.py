"""
Unit tests for BaseOrchestrator

Tests shared initialization (_init_common_state, _init_pipeline_components),
shared public API methods (auth, logic builder, system status),
and backward-compat delegation / properties.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.orchestrator_base import BaseOrchestrator


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def mock_settings():
    """Return mock settings dict."""
    return {"project_dir": "/tmp/test_project"}


@pytest.fixture
def base_orch(mock_settings):
    """Create a BaseOrchestrator with mocked pipeline components."""
    with patch("src.core.orchestrator_base.initialize_databases"), \
         patch("src.core.orchestrator_base.SemanticParser"), \
         patch("src.core.orchestrator_base.MacroRouter"), \
         patch("src.core.orchestrator_base.GraphASTEngine"), \
         patch("src.core.orchestrator_base.APAPlanner"), \
         patch("src.core.orchestrator_base.GitHubScrapAgent"), \
         patch("src.core.orchestrator_base.ASTSurgeon"), \
         patch("src.core.orchestrator_base.ReflexionSandbox"), \
         patch("src.core.orchestrator_base.MerkleLedger"), \
         patch("src.core.orchestrator_base.TheoremCache"), \
         patch("src.core.orchestrator_base.get_isolation_manager"):
        orch = BaseOrchestrator()
        orch._init_pipeline_components(mock_settings)
        return orch


@pytest.fixture
def fully_mocked_orch(mock_settings):
    """Create a BaseOrchestrator with all sub-systems mocked."""
    with patch("src.core.orchestrator_base.initialize_databases"), \
         patch("src.core.orchestrator_base.SemanticParser"), \
         patch("src.core.orchestrator_base.MacroRouter"), \
         patch("src.core.orchestrator_base.GraphASTEngine"), \
         patch("src.core.orchestrator_base.APAPlanner"), \
         patch("src.core.orchestrator_base.GitHubScrapAgent"), \
         patch("src.core.orchestrator_base.ASTSurgeon"), \
         patch("src.core.orchestrator_base.ReflexionSandbox"), \
         patch("src.core.orchestrator_base.MerkleLedger"), \
         patch("src.core.orchestrator_base.TheoremCache"), \
         patch("src.core.orchestrator_base.get_isolation_manager"):
        orch = BaseOrchestrator()
        orch._init_pipeline_components(mock_settings)

        # Mock AI architecture layers
        orch._semantic = MagicMock()
        orch._semantic.is_loaded = True
        orch._ai = MagicMock()
        orch._ai.is_loaded = True
        orch._memory = MagicMock()
        orch._memory.enhanced_stats = {}

        # Mock extended architecture
        orch._thinking = MagicMock()
        orch._thinking.stats = {}
        orch._thinking.reason.return_value = MagicMock(
            answer="test", confidence=0.9, source="test",
            context_used=[], thinking_time_s=0.1,
        )
        orch._template_engine = MagicMock()
        orch._executor_registry = MagicMock()
        orch._executor_registry._executors = {}
        orch._executor_registry.list_types.return_value = ["http_request", "file_write"]
        orch._logic_builder = MagicMock()
        orch._logic_builder.list_blocks.return_value = []
        orch._chain_validator = MagicMock()
        orch._chain_executor = MagicMock()
        orch._app_gen = MagicMock()
        orch._app_gen.list_templates.return_value = []
        orch._automation = MagicMock()
        orch._automation.stats = {}
        orch._automation.list_workflows.return_value = []
        orch._schema_designer = MagicMock()

        # Mock Phase 7 engines
        orch._auth = MagicMock()
        orch._reasoning = MagicMock()
        orch._reasoning.stats = {}

        # Mock common state
        orch.request_count = 0

        # Mock agent framework
        orch._agent_runner = MagicMock()
        orch._agent_runner.stats = {}
        orch._agent_runner._cache = MagicMock()
        orch._agent_runner._cache.stats = {}
        orch._intent_agent = MagicMock()
        orch._intent_agent.stats = {}
        orch._reasoning_agent = MagicMock()
        orch._reasoning_agent.stats = {}
        orch._business_logic_agent = MagicMock()
        orch._business_logic_agent.stats = {}
        orch._code_agent = MagicMock()
        orch._code_agent.stats = {}
        orch._automation_agent = None
        orch._validation_agent = MagicMock()
        orch._validation_agent.stats = {}
        orch._context_agent = None
        orch._criticality_agent = None
        orch._titan_agent = None
        orch._fractal_gen = None

        return orch


# ============================================================
#  _init_common_state Tests
# ============================================================

class TestInitCommonState:
    """Tests for _init_common_state method."""

    def test_request_count_initialized(self):
        """request_count should start at 0."""
        orch = BaseOrchestrator()
        with patch("src.core.orchestrator_base.get_isolation_manager"):
            orch._init_common_state()
        assert orch.request_count == 0

    def test_pending_resumptions_empty(self):
        """_pending_resumptions should start as empty dict."""
        orch = BaseOrchestrator()
        with patch("src.core.orchestrator_base.get_isolation_manager"):
            orch._init_common_state()
        assert orch._pending_resumptions == {}

    def test_current_client_id_default(self):
        """_current_client_id should default to 'default'."""
        orch = BaseOrchestrator()
        with patch("src.core.orchestrator_base.get_isolation_manager"):
            orch._init_common_state()
        assert orch._current_client_id == "default"

    def test_isolation_manager_assigned(self):
        """_isolation_manager should be assigned from get_isolation_manager."""
        mock_mgr = MagicMock()
        orch = BaseOrchestrator()
        with patch("src.core.orchestrator_base.get_isolation_manager", return_value=mock_mgr):
            orch._init_common_state()
        assert orch._isolation_manager is mock_mgr


# ============================================================
#  _init_pipeline_components Tests
# ============================================================

class TestInitPipelineComponents:
    """Tests for _init_pipeline_components method."""

    def test_settings_stored(self, base_orch, mock_settings):
        """Settings should be stored on the instance."""
        assert base_orch.settings == mock_settings

    def test_project_dir_set(self, base_orch):
        """p_dir should be set from settings."""
        assert base_orch.p_dir == "/tmp/test_project"

    def test_parser_created(self, base_orch):
        """Parser component should be created."""
        assert base_orch.parser is not None

    def test_router_created(self, base_orch):
        """Router component should be created."""
        assert base_orch.router is not None

    def test_all_pipeline_components_created(self, base_orch):
        """All 8 pipeline components should be created."""
        assert base_orch.parser is not None
        assert base_orch.router is not None
        assert base_orch.ast_engine is not None
        assert base_orch.planner is not None
        assert base_orch.scrap is not None
        assert base_orch.surgeon is not None
        assert base_orch.sandbox is not None
        assert base_orch.ledger is not None
        assert base_orch.cache is not None

    def test_default_project_dir(self):
        """p_dir should default to '.' when not in settings."""
        with patch("src.core.orchestrator_base.initialize_databases"), \
             patch("src.core.orchestrator_base.SemanticParser"), \
             patch("src.core.orchestrator_base.MacroRouter"), \
             patch("src.core.orchestrator_base.GraphASTEngine"), \
             patch("src.core.orchestrator_base.APAPlanner"), \
             patch("src.core.orchestrator_base.GitHubScrapAgent"), \
             patch("src.core.orchestrator_base.ASTSurgeon"), \
             patch("src.core.orchestrator_base.ReflexionSandbox"), \
             patch("src.core.orchestrator_base.MerkleLedger"), \
             patch("src.core.orchestrator_base.TheoremCache"), \
             patch("src.core.orchestrator_base.get_isolation_manager"):
            orch = BaseOrchestrator()
            orch._init_pipeline_components({})
            assert orch.p_dir == "."


# ============================================================
#  _init_extended_architecture Tests
# ============================================================

class TestInitExtendedArchitecture:
    """Tests for _init_extended_architecture method."""

    def test_assigns_thinking_engine(self):
        """Should store the thinking engine reference."""
        orch = BaseOrchestrator()
        mock_thinking = MagicMock()
        orch._init_extended_architecture(thinking_engine=mock_thinking)
        assert orch._thinking is mock_thinking

    def test_assigns_auth(self):
        """Should store the auth service reference."""
        orch = BaseOrchestrator()
        mock_auth = MagicMock()
        orch._init_extended_architecture(auth=mock_auth)
        assert orch._auth is mock_auth

    def test_defaults_to_none(self):
        """Unspecified components should default to None."""
        orch = BaseOrchestrator()
        orch._init_extended_architecture()
        assert orch._thinking is None
        assert orch._template_engine is None
        assert orch._auth is None
        assert orch._reasoning is None


# ============================================================
#  Public API Tests
# ============================================================

class TestPublicAPI:
    """Tests for shared public API methods."""

    @pytest.mark.asyncio
    async def test_register_user_no_auth(self):
        """register_user should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.register_user("user", "e@e.com", "pass")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_register_user_with_auth(self):
        """register_user should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.register_user.return_value = {"username": "test"}
        result = await orch.register_user("user", "e@e.com", "pass")
        orch._auth.register_user.assert_called_once_with("user", "e@e.com", "pass", "user")
        assert result["username"] == "test"

    @pytest.mark.asyncio
    async def test_login_user_no_auth(self):
        """login_user should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.login_user("user", "pass")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_login_user_with_auth(self):
        """login_user should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.login_user.return_value = {"access_token": "tok"}
        result = await orch.login_user("user", "pass")
        assert "access_token" in result

    @pytest.mark.asyncio
    async def test_verify_token_no_auth(self):
        """verify_token should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.verify_token("token")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_verify_token_with_auth(self):
        """verify_token should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.verify_token.return_value = {"sub": "1"}
        result = await orch.verify_token("token")
        assert "sub" in result

    @pytest.mark.asyncio
    async def test_verify_token_exception(self):
        """verify_token should handle exceptions from auth."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.verify_token.side_effect = Exception("bad token")
        result = await orch.verify_token("bad")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_action_no_registry(self):
        """execute_action should return error when registry not available."""
        orch = BaseOrchestrator()
        orch._executor_registry = None
        result = await orch.execute_action("http_request", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_action_with_registry(self):
        """execute_action should delegate to executor registry."""
        orch = BaseOrchestrator()
        orch._executor_registry = MagicMock()
        mock_result = MagicMock(success=True, data={"key": "val"}, error=None, duration_ms=10)
        orch._executor_registry.execute_action = AsyncMock(return_value=mock_result)
        result = await orch.execute_action("http_request", {"url": "http://test.com"})
        assert result["success"] is True
        assert result["data"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_list_projects_with_memory(self, fully_mocked_orch):
        """list_projects should delegate to memory when available."""
        fully_mocked_orch._memory.list_projects.return_value = [{"name": "proj1"}]
        result = await fully_mocked_orch.list_projects()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_projects_no_memory(self):
        """list_projects should return empty list when memory not available."""
        orch = BaseOrchestrator()
        orch._memory = None
        result = await orch.list_projects()
        assert result == []

    @pytest.mark.asyncio
    async def test_build_logic_no_agents(self):
        """build_logic should return error when no builder or agent."""
        orch = BaseOrchestrator()
        orch._business_logic_agent = None
        orch._logic_builder = None
        result = await orch.build_logic("create user auth")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_logic_blocks_no_builder(self):
        """list_logic_blocks should return empty list when no builder."""
        orch = BaseOrchestrator()
        orch._logic_builder = None
        result = await orch.list_logic_blocks()
        assert result == []


# ============================================================
#  Properties Tests
# ============================================================

class TestProperties:
    """Tests for shared properties."""

    def test_low_power_mode_none(self):
        """low_power_mode should be None when not initialized."""
        orch = BaseOrchestrator()
        orch._low_power_mode = None
        assert orch.low_power_mode is None

    def test_low_power_mode_set(self):
        """low_power_mode should return the mode object."""
        orch = BaseOrchestrator()
        mock_mode = MagicMock()
        orch._low_power_mode = mock_mode
        assert orch.low_power_mode is mock_mode

    def test_model_manager_none(self):
        """model_manager should be None when not initialized."""
        orch = BaseOrchestrator()
        orch._model_mgr = None
        assert orch.model_manager is None

    def test_model_manager_set(self):
        """model_manager should return the manager object."""
        orch = BaseOrchestrator()
        mock_mgr = MagicMock()
        orch._model_mgr = mock_mgr
        assert orch.model_manager is mock_mgr

    def test_project_dir_property(self, base_orch, mock_settings):
        """project_dir property should return p_dir."""
        assert base_orch.project_dir == "/tmp/test_project"


# ============================================================
#  System Status Tests
# ============================================================

class TestSystemStatus:
    """Tests for get_system_status and get_intelligence_status."""

    @pytest.mark.asyncio
    async def test_get_system_status_structure(self, fully_mocked_orch):
        """get_system_status should return all expected keys."""
        status = await fully_mocked_orch.get_system_status()
        assert "pipeline" in status
        assert "ai" in status
        assert "phase7_engines" in status
        assert "phase8_intelligence" in status
        assert "agent_framework" in status
        assert "request_count" in status

    @pytest.mark.asyncio
    async def test_get_intelligence_status_structure(self, fully_mocked_orch):
        """get_intelligence_status should return intelligence info."""
        status = await fully_mocked_orch.get_intelligence_status()
        assert "reasoning_engine" in status
        assert "ai_layers" in status
        assert "thinking_engine" in status
        assert "phase8_modes" in status

    @pytest.mark.asyncio
    async def test_get_intelligence_status_ai_layers(self, fully_mocked_orch):
        """get_intelligence_status should report AI layer availability."""
        status = await fully_mocked_orch.get_intelligence_status()
        layers = status["ai_layers"]
        assert "layer1_semantic" in layers
        assert "layer2_qwen" in layers
        assert "layer3_memory" in layers
