"""
Unit tests for Response Builder

Tests the OpenAI-compatible response builder functions:
- build_normal_response
- build_partial_reasoning_response
- build_error_response
- build_overloaded_response
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def sample_data():
    """Sample request data dict."""
    return {"model": "titan-omniscale-x", "messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture
def sample_result():
    """Sample orchestrator result dict."""
    return {
        "status": "PASS",
        "explanations": ["Code generated successfully"],
        "code": "def hello():\n    return 'world'",
        "warnings": [],
        "cache_source": "",
        "cache_hits": 0,
        "processing_time_ms": 150,
        "route": "FAST_PATH",
        "hash": "abc123",
        "solver_status": "PROVEN",
        "mcts_simulations": 50,
        "mcts_depth_reached": 3,
        "paths_explored": 10,
        "paths_pruned": 2,
        "solver_proof": "All constraints satisfied",
        "criticality": 1,
        "ast_analysis": {"language": "python"},
    }


@pytest.fixture
def sample_user_msg():
    """Sample user message."""
    return "Generate a hello world function"


# ============================================================
#  build_normal_response Tests
# ============================================================

class TestBuildNormalResponse:
    """Tests for build_normal_response function."""

    def test_returns_dict(self, sample_data, sample_result, sample_user_msg):
        """Should return a dictionary."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self, sample_data, sample_result, sample_user_msg):
        """Should include OpenAI-compatible response fields."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert "id" in response
        assert "object" in response
        assert "created" in response
        assert "model" in response
        assert "choices" in response
        assert "usage" in response

    def test_object_type(self, sample_data, sample_result, sample_user_msg):
        """object field should be 'chat.completion'."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["object"] == "chat.completion"

    def test_model_field(self, sample_data, sample_result, sample_user_msg):
        """model field should match data model or default."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["model"] == "titan-omniscale-x"

    def test_model_default(self, sample_result, sample_user_msg):
        """Should default to 'titan-omniscale-x' when data has no model."""
        data = {}
        response = build_normal_response(data, sample_result, sample_user_msg)
        assert response["model"] == "titan-omniscale-x"

    def test_choices_structure(self, sample_data, sample_result, sample_user_msg):
        """choices should be a list with proper structure."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert isinstance(response["choices"], list)
        assert len(response["choices"]) >= 1
        choice = response["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        assert choice["finish_reason"] == "stop"

    def test_message_structure(self, sample_data, sample_result, sample_user_msg):
        """message should have role and content."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert msg["role"] == "assistant"
        assert isinstance(msg["content"], str)
        assert len(msg["content"]) > 0

    def test_usage_structure(self, sample_data, sample_result, sample_user_msg):
        """usage should have prompt_tokens, completion_tokens, total_tokens."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        usage = response["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_titan_metadata_present(self, sample_data, sample_result, sample_user_msg):
        """Should include titan_metadata in response."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert "titan_metadata" in response
        meta = response["titan_metadata"]
        assert meta["status"] == "PASS"
        assert meta["hash"] == "abc123"
        assert meta["processing_time_ms"] == 150

    def test_titan_metadata_solver_info(self, sample_data, sample_result, sample_user_msg):
        """titan_metadata should include solver type and status."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        meta = response["titan_metadata"]
        assert "solver_type" in meta
        assert meta["solver_status"] == "PROVEN"

    def test_titan_metadata_mcts_info(self, sample_data, sample_result, sample_user_msg):
        """titan_metadata should include MCTS simulation info."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        meta = response["titan_metadata"]
        assert meta["mcts_simulations"] == 50
        assert meta["mcts_depth_reached"] == 3

    def test_titan_metadata_symbolic_execution(self, sample_data, sample_result, sample_user_msg):
        """titan_metadata should flag symbolic_execution as True."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["titan_metadata"]["symbolic_execution"] is True

    def test_content_includes_status(self, sample_data, sample_result, sample_user_msg):
        """Response content should include the status."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "PASS" in content

    def test_content_includes_code(self, sample_data, sample_result, sample_user_msg):
        """Response content should include generated code block."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "```" in content
        assert "hello" in content

    def test_content_includes_explanations(self, sample_data, sample_result, sample_user_msg):
        """Response content should include explanations."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Code generated successfully" in content

    def test_with_warnings(self, sample_data, sample_user_msg):
        """Should include warnings in response content."""
        result = {
            "status": "PASS",
            "warnings": ["Potential issue detected"],
            "processing_time_ms": 100,
            "route": "FAST_PATH",
            "hash": "xyz",
            "solver_status": "HEURISTIC",
            "mcts_simulations": 0,
            "mcts_depth_reached": 0,
            "paths_explored": 0,
            "paths_pruned": 0,
            "criticality": 1,
        }
        response = build_normal_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Warning" in content

    def test_with_cache_hit(self, sample_data, sample_user_msg):
        """Should include cache hit info when present."""
        result = {
            "status": "PASS",
            "cache_source": "memory",
            "cache_hits": 5,
            "processing_time_ms": 10,
            "route": "FAST_PATH",
            "hash": "h1",
            "solver_status": "N/A",
            "mcts_simulations": 0,
            "mcts_depth_reached": 0,
            "paths_explored": 0,
            "paths_pruned": 0,
            "criticality": 1,
        }
        response = build_normal_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Cache hit" in content

    def test_with_governor(self, sample_data, sample_result, sample_user_msg):
        """Should include resource info when governor is provided."""
        class MockGovernor:
            def get_status(self):
                return {
                    "ram_usage_mb": 500,
                    "ram_limit_mb": 2048,
                    "cpu_usage_pct": 30.0,
                }

        response = build_normal_response(
            sample_data, sample_result, sample_user_msg, governor=MockGovernor()
        )
        content = response["choices"][0]["message"]["content"]
        assert "RAM" in content
        assert "CPU" in content
        assert response["titan_metadata"]["platform"] == "termux-proot"

    def test_without_governor(self, sample_data, sample_result, sample_user_msg):
        """Should not include resource info when no governor."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "platform" not in response["titan_metadata"]

    def test_id_starts_with_titan(self, sample_data, sample_result, sample_user_msg):
        """Response ID should start with 'titan-'."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["id"].startswith("titan-")

    def test_created_is_timestamp(self, sample_data, sample_result, sample_user_msg):
        """created field should be a valid timestamp."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        now = int(time.time())
        assert abs(response["created"] - now) <= 5


# ============================================================
#  build_partial_reasoning_response Tests
# ============================================================

class TestBuildPartialReasoningResponse:
    """Tests for build_partial_reasoning_response function."""

    def test_returns_dict(self, sample_data, sample_user_msg):
        """Should return a dictionary."""
        result = {"processing_time_ms": 100, "route": "DEEP_PATH", "criticality": 2}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self, sample_data, sample_user_msg):
        """Should include OpenAI-compatible response fields."""
        result = {"partial_reasoning_payload": {"content": "Thinking..."}}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert "id" in response
        assert "object" in response
        assert "choices" in response

    def test_tool_calls_in_message(self, sample_data, sample_user_msg):
        """Should include tool_calls in message when provided."""
        tool_calls = [{"id": "tc1", "type": "function", "function": {"name": "subdivide"}}]
        result = {
            "partial_reasoning_payload": {
                "tool_calls": tool_calls,
            },
            "processing_time_ms": 100,
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) == 1

    def test_finish_reason_tool_calls(self, sample_data, sample_user_msg):
        """finish_reason should default to 'tool_calls'."""
        result = {"partial_reasoning_payload": {}}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["choices"][0]["finish_reason"] == "tool_calls"

    def test_custom_finish_reason(self, sample_data, sample_user_msg):
        """Should respect custom finish_reason from payload."""
        result = {
            "partial_reasoning_payload": {
                "finish_reason": "stop",
            }
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["choices"][0]["finish_reason"] == "stop"

    def test_titan_metadata_partial_reasoning(self, sample_data, sample_user_msg):
        """titan_metadata should indicate partial_reasoning."""
        result = {"processing_time_ms": 50, "route": "SURGICAL_PATH", "criticality": 3}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        meta = response["titan_metadata"]
        assert meta["partial_reasoning"] is True
        assert meta["status"] == "PARTIAL_REASONING"

    def test_content_from_payload(self, sample_data, sample_user_msg):
        """Should use content from partial_reasoning_payload."""
        result = {
            "partial_reasoning_payload": {
                "content": "Analyzing code structure...",
            }
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert msg["content"] == "Analyzing code structure..."

    def test_content_fallback_to_explanations(self, sample_data, sample_user_msg):
        """Should fallback to explanations when no content in payload."""
        result = {
            "partial_reasoning_payload": {},
            "explanations": ["Step 1 done"],
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert content == "Step 1 done"

    def test_usage_metadata(self, sample_data, sample_user_msg):
        """Should use usage_metadata from result if available."""
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        result = {
            "partial_reasoning_payload": {},
            "usage_metadata": usage,
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["usage"] == usage


# ============================================================
#  build_error_response Tests
# ============================================================

class TestBuildErrorResponse:
    """Tests for build_error_response function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        response = build_error_response("Something went wrong")
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self):
        """Should include OpenAI-compatible response fields."""
        response = build_error_response("Error occurred")
        assert "id" in response
        assert "object" in response
        assert "created" in response
        assert "model" in response
        assert "choices" in response
        assert "usage" in response

    def test_object_type(self):
        """object field should be 'chat.completion'."""
        response = build_error_response("Error")
        assert response["object"] == "chat.completion"

    def test_error_in_content(self):
        """Error message should appear in response content."""
        response = build_error_response("Division by zero")
        content = response["choices"][0]["message"]["content"]
        assert "Division by zero" in content

    def test_content_includes_error_header(self):
        """Content should include the internal error header."""
        response = build_error_response("Test error")
        content = response["choices"][0]["message"]["content"]
        assert "Internal Error" in content

    def test_content_includes_retry_suggestion(self):
        """Content should suggest reformulating the request."""
        response = build_error_response("Failed")
        content = response["choices"][0]["message"]["content"]
        assert "reformulating" in content.lower()

    def test_model_is_titan(self):
        """model should be 'titan-omniscale-x'."""
        response = build_error_response("Error")
        assert response["model"] == "titan-omniscale-x"

    def test_finish_reason_stop(self):
        """finish_reason should be 'stop'."""
        response = build_error_response("Error")
        assert response["choices"][0]["finish_reason"] == "stop"

    def test_usage_zero_tokens(self):
        """usage should have zero tokens for errors."""
        response = build_error_response("Error")
        assert response["usage"]["prompt_tokens"] == 0
        assert response["usage"]["completion_tokens"] == 0
        assert response["usage"]["total_tokens"] == 0

    def test_role_assistant(self):
        """message role should be 'assistant'."""
        response = build_error_response("Error")
        assert response["choices"][0]["message"]["role"] == "assistant"

    def test_empty_error_message(self):
        """Should handle empty error message."""
        response = build_error_response("")
        assert isinstance(response, dict)
        assert "choices" in response

    def test_long_error_message(self):
        """Should handle very long error messages."""
        long_msg = "Error: " + "x" * 10000
        response = build_error_response(long_msg)
        assert isinstance(response, dict)


# ============================================================
#  build_overloaded_response Tests
# ============================================================

class TestBuildOverloadedResponse:
    """Tests for build_overloaded_response function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        response = build_overloaded_response()
        assert isinstance(response, dict)

    def test_has_error_field(self):
        """Should include 'error' key."""
        response = build_overloaded_response()
        assert "error" in response

    def test_error_type_server_overloaded(self):
        """Error type should be 'server_overloaded'."""
        response = build_overloaded_response()
        assert response["error"]["type"] == "server_overloaded"

    def test_error_message_mentions_ram(self):
        """Error message should mention RAM critical."""
        response = build_overloaded_response()
        assert "RAM" in response["error"]["message"]

    def test_error_message_mentions_retry(self):
        """Error message should suggest retrying."""
        response = build_overloaded_response()
        assert "retry" in response["error"]["message"].lower()

    def test_no_choices_field(self):
        """Overloaded response should not have choices (it's an error, not a completion)."""
        response = build_overloaded_response()
        assert "choices" not in response

    def test_consistent_structure(self):
        """Should have consistent structure across calls."""
        r1 = build_overloaded_response()
        r2 = build_overloaded_response()
        assert r1.keys() == r2.keys()
        assert r1["error"].keys() == r2["error"].keys()
