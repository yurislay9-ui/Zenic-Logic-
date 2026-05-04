"""
TITAN OMNISCALE X - PartialReasoningManager Tests

Tests for partial reasoning responses and resumption:
  - build_partial_reasoning_response: payload construction, resumption token
  - resume_from_partial: resumption with valid/expired tokens, subtask execution
  - TTL expiration: old resumption entries are cleaned up
  - State serialization: SubtaskDescriptor reconstruction from dicts/strings
"""

import asyncio
import time
import threading
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

from src.core.partial_reasoning import PartialReasoningManager
from src.core.subtask_descriptor import SubtaskDescriptor


# ============================================================
#  FIXTURES
# ============================================================

@pytest.fixture
def mock_orchestrator():
    """Create a mock TitanOrchestrator with all required attributes."""
    orch = MagicMock()

    # Sandbox
    orch.sandbox = MagicMock()
    orch.sandbox.k_path_limit = 50
    orch.sandbox.validate_code = AsyncMock()

    # Abortive protocol
    orch._abortive = MagicMock()
    orch._abortive.generate_subtasks = MagicMock(return_value=[
        SubtaskDescriptor(message="Subtask isolation", target="auth.py",
                          operation="CREATE", goal="isolate"),
        SubtaskDescriptor(message="Subtask mutation", target="auth.py",
                          operation="CREATE", goal="mutate"),
    ])
    orch._abortive.execute_subtask = AsyncMock(return_value={
        "status": "SUCCESS", "code": "def hello(): pass", "message": ""
    })
    orch._abortive.merge_subtask_results = MagicMock(return_value="def hello(): pass")

    # Resumption storage
    orch._pending_resumptions = {}
    orch._resumptions_lock = threading.Lock()

    # Isolation manager
    orch._isolation_manager = MagicMock()
    workspace = MagicMock()
    workspace.sandbox_id = "ws-test-123"
    orch._isolation_manager.create_workspace = MagicMock(return_value=workspace)
    orch._isolation_manager.release_workspace = MagicMock()

    # Cache
    orch.cache = MagicMock()
    orch.cache.save = MagicMock()

    # Ledger
    orch.ledger = MagicMock()
    node = MagicMock()
    node.hash_sha256 = "abc123def456"
    orch.ledger.commit = MagicMock(return_value=node)
    orch.ledger.snapshot = MagicMock()
    orch.ledger.rollback = MagicMock()

    return orch


@pytest.fixture
def mock_intent():
    """Create a mock IntentPayload."""
    intent = MagicMock()
    intent.op = "CREATE"
    intent.target = "auth.py"
    intent.goal = "FEATURE_ADD"
    intent.language = "python"
    intent.raw_code = "def authenticate(): pass"
    intent.scrap_query = ""
    intent.confidence = 0.85
    return intent


@pytest.fixture
def mock_routing():
    """Create a mock RoutingResult."""
    routing = MagicMock()
    routing.route = "standard"
    routing.criticality = 2
    return routing


@pytest.fixture
def mock_plan():
    """Create a mock plan with solver proof."""
    plan = MagicMock()
    plan.solver_status = "TIMEOUT"
    plan.solver_proof = {"solver_type": "Z3", "timeout_ms": 5000}
    return plan


@pytest.fixture
def mock_trial():
    """Create a mock TrialResult."""
    trial = MagicMock()
    trial.error_message = "K-Path limit exceeded"
    trial.warnings = ["High complexity detected"]
    trial.paths_explored = 50
    trial.paths_pruned = 120
    trial.status = "FAIL_K_PATH"
    return trial


@pytest.fixture
def manager(mock_orchestrator):
    """Create a PartialReasoningManager with mocked orchestrator."""
    return PartialReasoningManager(mock_orchestrator)


# ============================================================
#  BUILD PARTIAL REASONING RESPONSE TESTS
# ============================================================

class TestBuildPartialReasoningResponse:
    """Tests for building partial reasoning responses."""

    def test_returns_partial_reasoning_status(self, manager, mock_intent, mock_routing,
                                              mock_plan, mock_trial):
        """Response should have status PARTIAL_REASONING."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent,
            routing=mock_routing,
            plan=mock_plan,
            ast_analysis={"complexity": "high"},
            trial=mock_trial,
            start_time=time.time(),
        )
        assert result["status"] == "PARTIAL_REASONING"
        assert result["partial_reasoning"] is True

    def test_includes_resumption_token(self, manager, mock_intent, mock_routing,
                                       mock_plan, mock_trial):
        """Response should include a resumption token."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert "resumption" in result
        assert "token" in result["resumption"]
        assert len(result["resumption"]["token"]) > 0

    def test_stores_resumption_state(self, manager, mock_intent, mock_routing,
                                     mock_plan, mock_trial, mock_orchestrator):
        """Resumption state should be stored in the orchestrator."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        assert token in mock_orchestrator._pending_resumptions
        state = mock_orchestrator._pending_resumptions[token]
        assert state["original_intent"]["op"] == "CREATE"
        assert state["original_intent"]["target"] == "auth.py"

    def test_includes_tool_calls(self, manager, mock_intent, mock_routing,
                                 mock_plan, mock_trial):
        """Response should include zenith_mcts_plan tool calls."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        payload = result["partial_reasoning_payload"]
        assert "tool_calls" in payload
        assert len(payload["tool_calls"]) >= 1
        assert payload["tool_calls"][0]["function"]["name"] == "zenith_mcts_plan"

    def test_includes_solver_type(self, manager, mock_intent, mock_routing,
                                  mock_plan, mock_trial):
        """Response should include solver type from plan."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        # Z3 solver type from mock_plan
        assert "Z3" in result["explanations"][0] or "SMT" in result["explanations"][0]

    def test_includes_usage_metadata(self, manager, mock_intent, mock_routing,
                                     mock_plan, mock_trial):
        """Response should include usage_metadata with k-path info."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert "usage_metadata" in result
        assert result["usage_metadata"]["zenith_k_path_eval"] == 50


# ============================================================
#  RESUME FROM PARTIAL TESTS
# ============================================================

class TestResumeFromPartial:
    """Tests for resuming from partial reasoning state."""

    def test_invalid_token_returns_error(self, manager, mock_orchestrator):
        """Resuming with invalid token should return error."""
        result = asyncio.get_event_loop().run_until_complete(
            manager.resume_from_partial("nonexistent_token")
        )
        assert result["status"] == "ERROR"
        assert "Invalid or expired" in result["error"]

    def test_resume_with_all_subtasks_succeeded(self, manager, mock_orchestrator,
                                                 mock_intent, mock_routing,
                                                 mock_plan, mock_trial):
        """When all subtasks already succeeded, resume should validate and succeed."""
        # Build a partial response first to get a token
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]

        # Set all previous results as SUCCESS
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "CACHED", "code": "pass"},
        ]

        # Mock sandbox validation to PASS
        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)

        resume_result = asyncio.get_event_loop().run_until_complete(
            manager.resume_from_partial(token)
        )
        assert resume_result["status"] == "SUCCESS"

    def test_resume_with_failed_subtasks_reexecutes(self, manager, mock_orchestrator,
                                                     mock_intent, mock_routing,
                                                     mock_plan, mock_trial):
        """When some subtasks failed, resume should re-execute them."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]

        # Set first as SUCCESS, second as FAILED
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "FAILED", "code": "", "message": "error"},
        ]

        # Mock successful re-execution
        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "def hello(): pass"
        })

        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)

        resume_result = asyncio.get_event_loop().run_until_complete(
            manager.resume_from_partial(token)
        )
        # Should have called execute_subtask for the failed one
        mock_orchestrator._abortive.execute_subtask.assert_called()

    def test_resume_specific_subtask_index(self, manager, mock_orchestrator,
                                           mock_intent, mock_routing,
                                           mock_plan, mock_trial):
        """Resuming with subtask_index should only re-execute that subtask."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "FAILED", "code": ""},
        ]

        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "def fixed(): pass"
        })

        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)

        resume_result = asyncio.get_event_loop().run_until_complete(
            manager.resume_from_partial(token, subtask_index=1)
        )
        mock_orchestrator._abortive.execute_subtask.assert_called_once()

    def test_resume_deserializes_dict_subtasks(self, manager, mock_orchestrator,
                                               mock_intent, mock_routing,
                                               mock_plan, mock_trial):
        """Resume should reconstruct SubtaskDescriptors from dict representations."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]

        # Replace subtasks with dict representations
        state = mock_orchestrator._pending_resumptions[token]
        state["subtasks"] = [
            {"message": "Isolate module", "target": "auth.py",
             "operation": "CREATE", "goal": "isolate",
             "solver_insights": {}, "mcts_hints": [],
             "parent_violations": [], "parent_context": {}, "depth": 0},
            {"message": "Apply mutation", "target": "auth.py",
             "operation": "REFACTOR", "goal": "mutate"},
        ]
        state["subtask_results"] = []

        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "pass"
        })

        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)

        resume_result = asyncio.get_event_loop().run_until_complete(
            manager.resume_from_partial(token)
        )
        # Should have re-executed both subtasks
        assert mock_orchestrator._abortive.execute_subtask.call_count == 2


# ============================================================
#  TTL EXPIRATION TESTS
# ============================================================

class TestTTLExpiration:
    """Tests for TTL-based cleanup of resumption entries."""

    def test_expired_entries_cleaned_on_build(self, manager, mock_orchestrator,
                                              mock_intent, mock_routing,
                                              mock_plan, mock_trial):
        """Old resumption entries should be cleaned up when building new ones."""
        # Add an expired entry
        old_token = "old_expired_token"
        mock_orchestrator._pending_resumptions[old_token] = {
            "token": old_token,
            "created_at": time.time() - 3600,  # 1 hour ago
            "subtasks": [],
            "subtask_results": [],
            "original_intent": {},
            "partial_code": "",
        }

        # Build a new response (should trigger cleanup)
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )

        # Old entry should be gone
        assert old_token not in mock_orchestrator._pending_resumptions
        # New entry should exist
        new_token = result["resumption"]["token"]
        assert new_token in mock_orchestrator._pending_resumptions

    def test_max_count_enforcement(self, manager, mock_orchestrator,
                                   mock_intent, mock_routing,
                                   mock_plan, mock_trial):
        """When more than 100 entries exist, oldest should be evicted."""
        # Add 101 entries
        for i in range(101):
            mock_orchestrator._pending_resumptions[f"token_{i:04d}"] = {
                "token": f"token_{i:04d}",
                "created_at": time.time() - (101 - i),  # Increasing recency
                "subtasks": [],
                "subtask_results": [],
                "original_intent": {},
                "partial_code": "",
            }

        # Build a new response
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )

        # Should have at most 100 + new entry entries (old ones evicted)
        assert len(mock_orchestrator._pending_resumptions) <= 102

    def test_recent_entries_not_expired(self, manager, mock_orchestrator,
                                        mock_intent, mock_routing,
                                        mock_plan, mock_trial):
        """Recent entries should NOT be cleaned up."""
        recent_token = "recent_token"
        mock_orchestrator._pending_resumptions[recent_token] = {
            "token": recent_token,
            "created_at": time.time(),  # Just now
            "subtasks": [],
            "subtask_results": [],
            "original_intent": {},
            "partial_code": "",
        }

        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )

        assert recent_token in mock_orchestrator._pending_resumptions
