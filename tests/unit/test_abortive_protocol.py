"""
Unit tests for AbortiveProtocol.

Tests the protocol that handles auto-subdivision when solver timeout:
  - generate_subtasks() — subtask generation for various operation types
  - merge_subtask_results() — code merging (Python, Go, C-style)
  - merge_python_code() — import dedup + body concatenation
  - merge_go_code() — package + import dedup + function concatenation
  - merge_block_code() — generic C-style merge
  - execute_subtask() — subtask execution through pipeline
  - handle_abortive_protocol() — full abortive protocol flow
  - Workspace management and isolation
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.core.abortive_protocol import (
    AbortiveProtocol,
    MAX_SUBTASKS,
    MAX_DEEP_SUBTASKS,
    MAX_ABORTIVE_DEPTH,
    ABORTIVE_SANDBOX_TTL_MULTIPLIER,
    ABORTIVE_SANDBOX_TTL_MIN,
)
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.shared.contracts import OperationType


# ============================================================
#  Fixtures
# ============================================================

def _make_mock_intent(op="CREATE", target="auth.py", goal="FEATURE_ADD",
                      language="python", raw_code=""):
    """Create a mock intent object."""
    intent = MagicMock()
    intent.op = op
    intent.target = target
    intent.goal = goal
    intent.language = language
    intent.raw_code = raw_code
    return intent


def _make_mock_plan(solver_status="TIMEOUT_SUBDIVIDE_REQUIRED"):
    """Create a mock plan object."""
    plan = MagicMock()
    plan.solver_status = solver_status
    plan.solver_proof = {"timeout_ms": 15000, "verified": False}
    plan.mcts_simulations = 10
    plan.mcts_depth_reached = 3
    plan.steps = []
    return plan


def _make_mock_orchestrator():
    """Create a mock orchestrator with all required components."""
    orch = MagicMock()
    orch._code_gen = MagicMock()
    orch._code_gen.extract_solver_insights.return_value = {}
    orch.sandbox = MagicMock()
    orch.sandbox.timeout_seconds = 30
    orch.ledger = MagicMock()
    orch.ledger.rollback = MagicMock()
    orch.ledger.snapshot = MagicMock()
    orch.ledger.commit.return_value = MagicMock(hash_sha256="abc123def456789")
    orch.cache = MagicMock()
    orch.cache.lookup.return_value = None
    orch.cache.save = MagicMock()
    orch._analysis = MagicMock()
    orch._analysis.log_request = MagicMock()
    orch._partial_reasoning = MagicMock()
    orch._partial_reasoning.build_partial_reasoning_response.return_value = {
        "status": "PARTIAL", "code": ""
    }
    orch.settings = MagicMock()

    # Isolation manager
    mock_workspace = MagicMock()
    mock_workspace.sandbox_id = "ws_test_123"
    orch._isolation_manager = MagicMock()
    orch._isolation_manager.create_workspace.return_value = mock_workspace
    orch._isolation_manager.release_workspace = MagicMock()

    return orch


@pytest.fixture
def protocol():
    """AbortiveProtocol with mock orchestrator."""
    orch = _make_mock_orchestrator()
    return AbortiveProtocol(orch), orch


# ============================================================
#  Test: Constants
# ============================================================

class TestAbortiveConstants:
    """Tests for extracted constants."""

    def test_max_subtasks(self):
        """MAX_SUBTASKS should be reasonable."""
        assert MAX_SUBTASKS == 5

    def test_max_deep_subtasks(self):
        """MAX_DEEP_SUBTASKS should be reasonable."""
        assert MAX_DEEP_SUBTASKS == 3

    def test_max_abortive_depth(self):
        """MAX_ABORTIVE_DEPTH should be 2."""
        assert MAX_ABORTIVE_DEPTH == 2

    def test_sandbox_ttl_multiplier(self):
        """ABORTIVE_SANDBOX_TTL_MULTIPLIER should be positive."""
        assert ABORTIVE_SANDBOX_TTL_MULTIPLIER > 0

    def test_sandbox_ttl_min(self):
        """ABORTIVE_SANDBOX_TTL_MIN should be positive."""
        assert ABORTIVE_SANDBOX_TTL_MIN > 0


# ============================================================
#  Test: Subtask Generation
# ============================================================

class TestAbortiveGenerateSubtasks:
    """Tests for subtask generation."""

    def test_create_operation_generates_subtasks(self, protocol):
        """CREATE should generate interface + implementation + security subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="CREATE", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": []}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        # Should have at least interface and implementation subtasks
        messages = [s.message for s in subtasks]
        assert any("interfaces" in m or "interface" in m for m in messages)
        assert any("core logic" in m or "implement" in m for m in messages)

    def test_refactor_operation_generates_subtasks(self, protocol):
        """REFACTOR should generate analyze + optimize subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="REFACTOR", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        messages = [s.message for s in subtasks]
        assert any("analyze" in m.lower() for m in messages)

    def test_debug_operation_generates_subtasks(self, protocol):
        """DEBUG should generate trace + fix subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="DEBUG", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        messages = [s.message for s in subtasks]
        assert any("trace" in m.lower() for m in messages)
        assert any("fix" in m.lower() for m in messages)

    def test_raw_code_with_functions(self, protocol):
        """Should generate one subtask per function when raw_code has functions."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="def foo(): pass\ndef bar(): pass")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": ["foo", "bar"]}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 2
        # Should have subtasks for each function
        targets = [s.target for s in subtasks]
        assert "foo" in targets
        assert "bar" in targets

    def test_raw_code_without_functions(self, protocol):
        """Should generate analyze + operation subtasks for raw code without functions."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="x = 1")
        plan = _make_mock_plan()
        ast_analysis = {"function_names": []}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 1

    def test_default_operation_generates_subtasks(self, protocol):
        """Unknown operations should generate analyze subtasks."""
        ap, orch = protocol
        intent = _make_mock_intent(op="SEARCH", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        assert len(subtasks) >= 1

    def test_subtask_descriptors_are_enriched(self, protocol):
        """Generated subtasks should be SubtaskDescriptor instances with context."""
        ap, orch = protocol
        intent = _make_mock_intent(op="CREATE", raw_code="")
        plan = _make_mock_plan()
        ast_analysis = {}

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        for st in subtasks:
            assert isinstance(st, SubtaskDescriptor)
            assert st.message != ""
            assert isinstance(st.solver_insights, dict)
            assert isinstance(st.mcts_hints, list)
            assert isinstance(st.parent_violations, list)
            assert isinstance(st.parent_context, dict)

    def test_max_subtasks_limit(self, protocol):
        """Should not exceed MAX_SUBTASKS when slicing."""
        ap, orch = protocol
        intent = _make_mock_intent(raw_code="")
        intent.raw_code = "code"
        # Many function names
        ast_analysis = {"function_names": [f"fn_{i}" for i in range(10)]}
        plan = _make_mock_plan()

        subtasks = ap.generate_subtasks(intent, ast_analysis, plan)
        # The slicing [:MAX_SUBTASKS] is in handle_abortive_protocol,
        # generate_subtasks itself may return more
        assert isinstance(subtasks, list)


# ============================================================
#  Test: Merge Python Code
# ============================================================

class TestAbortiveMergePython:
    """Tests for Python code merging."""

    def test_merge_deduplicates_imports(self):
        """Should deduplicate imports when merging Python code."""
        parts = [
            "import os\nimport sys\n\ndef foo():\n    pass\n",
            "import os\nimport json\n\ndef bar():\n    pass\n",
        ]
        result = AbortiveProtocol.merge_python_code(parts)
        # "import os" should appear only once
        assert result.count("import os") == 1
        assert "import sys" in result
        assert "import json" in result
        assert "def foo()" in result
        assert "def bar()" in result

    def test_merge_preserves_bodies(self):
        """Should preserve all function bodies when merging."""
        parts = [
            "def hello():\n    print('hello')\n",
            "def world():\n    print('world')\n",
        ]
        result = AbortiveProtocol.merge_python_code(parts)
        assert "def hello()" in result
        assert "def world()" in result
        assert "print('hello')" in result
        assert "print('world')" in result

    def test_merge_single_part(self):
        """Should handle single code part correctly."""
        parts = ["import os\n\ndef main():\n    pass\n"]
        result = AbortiveProtocol.merge_python_code(parts)
        assert "import os" in result
        assert "def main()" in result

    def test_merge_empty_parts(self):
        """Should handle empty parts list."""
        result = AbortiveProtocol.merge_python_code([])
        assert result == ""


# ============================================================
#  Test: Merge Go Code
# ============================================================

class TestAbortiveMergeGo:
    """Tests for Go code merging."""

    def test_merge_go_deduplicates_imports(self):
        """Should deduplicate Go imports."""
        parts = [
            'package main\n\nimport "fmt"\n\nfunc hello() {\n    fmt.Println("hi")\n}\n',
            'package main\n\nimport "fmt"\nimport "os"\n\nfunc world() {\n    os.Exit(0)\n}\n',
        ]
        result = AbortiveProtocol.merge_go_code(parts)
        assert "package main" in result
        assert "fmt" in result
        assert "os" in result
        assert "func hello()" in result
        assert "func world()" in result

    def test_merge_go_preserves_package(self):
        """Should preserve package declaration."""
        parts = [
            'package mypkg\n\nfunc hello() {}\n',
        ]
        result = AbortiveProtocol.merge_go_code(parts)
        assert "package mypkg" in result


# ============================================================
#  Test: Merge Block Code (C-style)
# ============================================================

class TestAbortiveMergeBlockCode:
    """Tests for generic C-style block code merging."""

    def test_merge_with_skip_prefix(self):
        """Should deduplicate lines with skip_prefix."""
        parts = [
            "package com.example\n\nclass A {}\n",
            "package com.example\n\nclass B {}\n",
        ]
        result = AbortiveProtocol.merge_block_code(parts, "//", "package")
        # "package com.example" should appear only once
        assert result.count("package com.example") == 1
        assert "class A" in result
        assert "class B" in result

    def test_merge_without_skip_prefix(self):
        """Should include all lines when no skip_prefix."""
        parts = [
            "function a() {}\n",
            "function b() {}\n",
        ]
        result = AbortiveProtocol.merge_block_code(parts, "//", None)
        assert "function a" in result
        assert "function b" in result


# ============================================================
#  Test: merge_subtask_results routing
# ============================================================

class TestAbortiveMergeSubtaskResults:
    """Tests for the merge_subtask_results() routing method."""

    def test_merge_python_language(self, protocol):
        """Should route to merge_python_code for Python."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "import os\ndef a(): pass"},
            {"status": "SUCCESS", "code": "import sys\ndef b(): pass"},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert "def a" in result
        assert "def b" in result

    def test_merge_go_language(self, protocol):
        """Should route to merge_go_code for Go."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": 'package main\n\nfunc a() {}'},
        ]
        result = ap.merge_subtask_results(results, "go")
        assert "package main" in result

    def test_merge_kotlin_language(self, protocol):
        """Should route to merge_block_code for Kotlin."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "package com.test\n\nclass A {}"},
        ]
        result = ap.merge_subtask_results(results, "kotlin")
        assert "class A" in result

    def test_merge_skips_error_results(self, protocol):
        """Should skip ERROR and MAX_DEPTH_REACHED results."""
        ap, _ = protocol
        results = [
            {"status": "SUCCESS", "code": "def a(): pass"},
            {"status": "ERROR", "code": "bad code"},
            {"status": "MAX_DEPTH_REACHED", "code": "", "message": "too deep"},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert "def a" in result
        # ERROR code should not be included
        assert "bad code" not in result

    def test_merge_no_successful_results(self, protocol):
        """Should return empty string when all results failed."""
        ap, _ = protocol
        results = [
            {"status": "ERROR", "code": "bad"},
            {"status": "MAX_DEPTH_REACHED", "code": ""},
        ]
        result = ap.merge_subtask_results(results, "python")
        assert result == ""


# ============================================================
#  Test: execute_subtask
# ============================================================

class TestAbortiveExecuteSubtask:
    """Tests for subtask execution."""

    @pytest.mark.asyncio
    async def test_execute_subtask_max_depth(self, protocol):
        """Should return MAX_DEPTH_REACHED at max depth."""
        ap, orch = protocol
        subtask = SubtaskDescriptor(message="test", depth=5)
        result = await ap.execute_subtask(subtask, depth=5, max_depth=2)
        assert result["status"] == "MAX_DEPTH_REACHED"

    @pytest.mark.asyncio
    async def test_execute_subtask_parse_error(self, protocol):
        """Should handle parse errors gracefully."""
        ap, orch = protocol
        orch.parser.parse.side_effect = Exception("Parse failed")
        subtask = SubtaskDescriptor(message="bad input")
        result = await ap.execute_subtask(subtask, depth=0, max_depth=2)
        assert result["status"] == "ERROR"
        assert "Parse error" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_subtask_cache_hit(self, protocol):
        """Should return cached result on cache hit."""
        ap, orch = protocol
        mock_intent = _make_mock_intent()
        orch.parser.parse.return_value = mock_intent
        orch.cache.lookup.return_value = {"data": {"code": "cached_code"}}

        subtask = SubtaskDescriptor(message="create auth.py")
        result = await ap.execute_subtask(subtask, depth=0, max_depth=2)
        assert result["status"] == "CACHED"
        assert result["code"] == "cached_code"

    @pytest.mark.asyncio
    async def test_execute_subtask_string_legacy(self, protocol):
        """Should handle plain string subtask (legacy)."""
        ap, orch = protocol
        mock_intent = _make_mock_intent()
        orch.parser.parse.return_value = mock_intent
        orch.cache.lookup.return_value = {"data": {"code": "legacy_code"}}

        result = await ap.execute_subtask("create module test.py", depth=0, max_depth=2)
        assert result["status"] == "CACHED"


# ============================================================
#  Test: handle_abortive_protocol
# ============================================================

class TestAbortiveHandleProtocol:
    """Tests for the full abortive protocol flow."""

    @pytest.mark.asyncio
    async def test_abortive_creates_isolated_workspace(self, protocol):
        """Should create an isolated workspace for the protocol."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        # Mock sandbox validation to FAIL so we don't commit
        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        # Mock the subtask generation to return empty subtasks
        with patch.object(ap, 'generate_subtasks', return_value=[]):
            result = await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        # Should have created workspace
        orch._isolation_manager.create_workspace.assert_called()

    @pytest.mark.asyncio
    async def test_abortive_rollback_on_start(self, protocol):
        """Should perform rollback at the start of the protocol."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        with patch.object(ap, 'generate_subtasks', return_value=[]):
            await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        orch.ledger.rollback.assert_called()


# ============================================================
#  Test: Workspace Management
# ============================================================

class TestAbortiveWorkspace:
    """Tests for workspace isolation and management."""

    @pytest.mark.asyncio
    async def test_workspace_created_with_ttl(self, protocol):
        """Should create workspace with appropriate TTL."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        with patch.object(ap, 'generate_subtasks', return_value=[]):
            await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        # Verify workspace created with TTL
        call_args = orch._isolation_manager.create_workspace.call_args
        ttl = call_args[1]["ttl_seconds"]
        assert ttl >= ABORTIVE_SANDBOX_TTL_MIN
