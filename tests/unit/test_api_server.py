"""
Unit tests for src/api/server.py - FastAPI Server (Conditional Import)

Tests:
- get_app() lazy initialization
- Route registration
- Fallback when FastAPI is not installed
- openai_mock endpoint logic
- resume_partial endpoint logic
- models endpoint logic
"""

import json
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock


# ---------------------------------------------------------------------------
#  Helper: Build a mock FastAPI module so server.py can be imported even
#  when the real fastapi package is absent.
# ---------------------------------------------------------------------------

def _make_mock_fastapi_module():
    """Return a fake 'fastapi' module with FastAPI and HTTPException."""
    mod = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self):
            self._routes = []

        def post(self, path, **kw):
            def decorator(func):
                self._routes.append(("POST", path, func))
                return func
            return decorator

        def get(self, path, **kw):
            def decorator(func):
                self._routes.append(("GET", path, func))
                return func
            return decorator

    class _HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail

    mod.FastAPI = _FastAPI
    mod.HTTPException = _HTTPException
    return mod


# ---------------------------------------------------------------------------
#  Patch fastapi into sys.modules BEFORE importing server, so the conditional
#  import succeeds.
# ---------------------------------------------------------------------------

_mock_fastapi = _make_mock_fastapi_module()
_fastapi_patched = False


def _ensure_fastapi_in_sys():
    global _fastapi_patched
    if "fastapi" not in sys.modules:
        sys.modules["fastapi"] = _mock_fastapi
        _fastapi_patched = True


_ensure_fastapi_in_sys()

# Now we can import the module under test
from src.api import server as api_server  # noqa: E402


# ---------------------------------------------------------------------------
#  Helper: create an app with a fully mocked orchestrator
# ---------------------------------------------------------------------------

def _make_app_with_mock_orch():
    """Create the FastAPI app with a mocked orchestrator, avoiding real init."""
    if not api_server.HAS_FASTAPI:
        return None, None

    # Patch _Orchestrator so get_app() creates a mock instead of a real one
    mock_orch = AsyncMock()
    mock_orch.execute = AsyncMock(return_value={
        "status": "SUCCESS", "hash": "test", "error": "",
        "code": "", "usage_metadata": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })
    mock_orch.resume_from_partial = AsyncMock(return_value={
        "status": "SUCCESS", "hash": "test", "error": "",
        "code": "", "usage_metadata": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })

    api_server._app = None
    api_server._orch = None

    with patch.object(api_server, "_Orchestrator", return_value=mock_orch):
        app = api_server.get_app()

    return app, mock_orch


# ===========================================================================
#  Test: get_app() lazy initialization
# ===========================================================================

class TestGetAppLazyInit:
    """Tests for the get_app() lazy factory function."""

    def setup_method(self):
        """Reset module-level globals before each test."""
        if api_server.HAS_FASTAPI:
            api_server._app = None
            api_server._orch = None

    def test_returns_app_instance(self):
        """get_app() should return a FastAPI app instance."""
        if not api_server.HAS_FASTAPI:
            pytest.skip("FastAPI not available")
        with patch.object(api_server, "_Orchestrator", return_value=AsyncMock()):
            app = api_server.get_app()
        assert app is not None

    def test_lazy_singleton(self):
        """get_app() should return the same instance on repeated calls."""
        if not api_server.HAS_FASTAPI:
            pytest.skip("FastAPI not available")
        with patch.object(api_server, "_Orchestrator", return_value=AsyncMock()):
            app1 = api_server.get_app()
            app2 = api_server.get_app()
        assert app1 is app2

    def test_initializes_orchestrator(self):
        """get_app() should also create an Orchestrator instance."""
        if not api_server.HAS_FASTAPI:
            pytest.skip("FastAPI not available")
        api_server._app = None
        api_server._orch = None
        with patch.object(api_server, "_Orchestrator", return_value=AsyncMock()):
            api_server.get_app()
        assert api_server._orch is not None


# ===========================================================================
#  Test: Route registration
# ===========================================================================

class TestRouteRegistration:
    """Tests that _register_routes registers expected endpoints."""

    def test_post_chat_completions_registered(self):
        """The /v1/chat/completions POST route should be registered."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")
        paths = [r[1] for r in app._routes]
        assert "/v1/chat/completions" in paths

    def test_post_resume_registered(self):
        """The /v1/resume POST route should be registered."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")
        paths = [r[1] for r in app._routes]
        assert "/v1/resume" in paths

    def test_get_models_registered(self):
        """The /v1/models GET route should be registered."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")
        paths = [r[1] for r in app._routes]
        assert "/v1/models" in paths


# ===========================================================================
#  Test: HAS_FASTAPI flag and no-fastapi fallback
# ===========================================================================

class TestFastAPIFlag:
    """Tests for the HAS_FASTAPI conditional import flag."""

    def test_has_fastapi_is_bool(self):
        """HAS_FASTAPI should be a boolean."""
        assert isinstance(api_server.HAS_FASTAPI, bool)

    def test_get_app_defined_when_fastapi(self):
        """When HAS_FASTAPI is True, get_app should exist."""
        if api_server.HAS_FASTAPI:
            assert hasattr(api_server, "get_app")
            assert callable(api_server.get_app)

    def test_get_app_absent_when_no_fastapi(self):
        """When HAS_FASTAPI is False, get_app should not be defined."""
        if not api_server.HAS_FASTAPI:
            assert not hasattr(api_server, "get_app")


# ===========================================================================
#  Test: openai_mock endpoint logic (mocked)
# ===========================================================================

class TestOpenAIMockEndpoint:
    """Tests for the openai_mock route handler logic via mocked orchestrator."""

    @pytest.mark.asyncio
    async def test_basic_execution(self):
        """openai_mock should call orchestrator.execute and return a response."""
        app, mock_orch = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        mock_orch.execute.return_value = {
            "status": "SUCCESS",
            "hash": "deadbeef",
            "error": "",
            "code": "print('hi')",
            "usage_metadata": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        msg = MagicMock()
        msg.role = "user"
        msg.content = "hello world"

        req = MagicMock()
        req.messages = [msg]

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/chat/completions" and method == "POST":
                handler = func
                break
        assert handler is not None

        result = await handler(req)
        assert result["object"] == "chat.completion"
        assert result["model"] == "titan-omniscale-x"
        assert "choices" in result

    @pytest.mark.asyncio
    async def test_no_user_message_raises(self):
        """openai_mock should raise HTTPException if no user message present."""
        app, mock_orch = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        msg = MagicMock()
        msg.role = "assistant"
        msg.content = "no user here"

        req = MagicMock()
        req.messages = [msg]

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/chat/completions" and method == "POST":
                handler = func
                break

        with pytest.raises(api_server.HTTPException) as exc_info:
            await handler(req)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_resumption_token_triggers_resume(self):
        """When tool_calls contain zenith_mcts_plan, resume_from_partial is called."""
        app, mock_orch = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        mock_orch.resume_from_partial.return_value = {
            "status": "SUCCESS",
            "hash": "resume123",
            "error": "",
            "code": "print('resumed')",
            "usage_metadata": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        tc_func = MagicMock()
        tc_func.name = "zenith_mcts_plan"
        tc_func.arguments = json.dumps({"resumption_token": "abc123"})

        tc = MagicMock()
        tc.function = tc_func

        assistant_msg = MagicMock()
        assistant_msg.role = "assistant"
        assistant_msg.tool_calls = [tc]
        assistant_msg.content = None

        user_msg = MagicMock()
        user_msg.role = "user"
        user_msg.content = "continue"

        tool_msg = MagicMock()
        tool_msg.role = "tool"
        tool_msg.content = json.dumps({})

        req = MagicMock()
        req.messages = [assistant_msg, tool_msg, user_msg]

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/chat/completions" and method == "POST":
                handler = func
                break

        result = await handler(req)
        mock_orch.resume_from_partial.assert_called_once_with("abc123")
        assert result["object"] == "chat.completion"


# ===========================================================================
#  Test: models endpoint
# ===========================================================================

class TestModelsEndpoint:
    """Tests for the /v1/models GET handler."""

    @pytest.mark.asyncio
    async def test_returns_model_list(self):
        """models() should return the model list."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/models" and method == "GET":
                handler = func
                break
        assert handler is not None

        result = await handler()
        assert result["object"] == "list"
        assert len(result["data"]) >= 1
        assert result["data"][0]["id"] == "titan-omniscale-x"

    @pytest.mark.asyncio
    async def test_model_owned_by_local(self):
        """models() should indicate owned_by = local."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/models" and method == "GET":
                handler = func
                break

        result = await handler()
        assert result["data"][0]["owned_by"] == "local"

    @pytest.mark.asyncio
    async def test_model_object_type(self):
        """Each model entry should have object = model."""
        app, _ = _make_app_with_mock_orch()
        if app is None:
            pytest.skip("FastAPI not available")

        handler = None
        for method, path, func in app._routes:
            if path == "/v1/models" and method == "GET":
                handler = func
                break

        result = await handler()
        assert result["data"][0]["object"] == "model"
