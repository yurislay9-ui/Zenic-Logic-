"""Tests for SimplePlanner, SimpleSandbox, SimpleLedger, SimpleCache, TitanEngine, and utils."""

import pytest
from src.core.local_engine import (
    SimplePlanner, SimpleSandbox, SimpleCache, TitanEngine,
    INTENT_KEYWORDS, GOAL_KEYWORDS, get_data_dir, get_db_path,
    initialize_databases,
)
from src.core.shared.contracts import OperationType, GoalType
from pathlib import Path
from ._fixtures import planner, sandbox, ledger


class TestSimplePlanner:
    """Tests for SimplePlanner execution plan generation."""

    def test_create_plan(self, planner):
        routing = {"criticality": "DEEP_MODERATE"}
        intent = {"op": OperationType.CREATE, "target": "auth.py",
                  "goal": GoalType.FEATURE_ADD, "scrap_query": "test"}
        steps = planner.generate_plan(routing, intent)
        assert len(steps) >= 1
        actions = [s["action"] for s in steps]
        assert "SCRAPE_GITHUB" in actions
        assert "INSERT_AST_NODE" in actions

    def test_refactor_plan(self, planner):
        routing = {"criticality": "SURGICAL_CRITICAL"}
        intent = {"op": OperationType.REFACTOR, "target": "utils.py",
                  "goal": GoalType.COMPLEXITY_REDUCTION}
        steps = planner.generate_plan(routing, intent)
        assert steps[0]["action"] == "REPLACE_AST_NODE"

    def test_delete_plan(self, planner):
        routing = {"criticality": "SURGICAL_CRITICAL"}
        intent = {"op": OperationType.DELETE, "target": "old.py",
                  "goal": GoalType.FEATURE_ADD}
        steps = planner.generate_plan(routing, intent)
        assert steps[0]["action"] == "DELETE_AST_NODE"


class TestSimpleSandbox:
    """Tests for SimpleSandbox Python code validation."""

    def test_valid_python_code(self, sandbox):
        result = sandbox.validate_code("x = 1 + 2\nprint(x)", "python", "test.py")
        assert result["status"] == "PASS"
        assert result["error_message"] == ""

    def test_invalid_python_code(self, sandbox):
        result = sandbox.validate_code("def foo(\n    x = 1", "python", "test.py")
        assert result["status"] == "FAIL_SYNTAX"
        assert "sintaxis" in result["error_message"].lower() or "syntax" in result["error_message"].lower()

    def test_non_python_non_empty(self, sandbox):
        result = sandbox.validate_code("fun main() {}", "kotlin", "Main.kt")
        assert result["status"] == "PASS"

    def test_empty_code(self, sandbox):
        result = sandbox.validate_code("", "python", "test.py")
        assert result["status"] in ["FAIL_SYNTAX", "PASS"]


class TestSimpleLedger:
    """Tests for SimpleLedger snapshot/commit/rollback operations."""

    def test_commit_creates_file(self, ledger, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        content = "print('hello')"
        result = ledger.commit("test.py", content, str(project_dir))
        assert "hash_sha256" in result
        assert len(result["hash_sha256"]) == 64
        assert (project_dir / "test.py").exists()
        assert (project_dir / "test.py").read_text() == content

    def test_snapshot_and_rollback(self, ledger, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        original = "original content"
        (project_dir / "test.py").write_text(original)
        ledger.snapshot("test.py", str(project_dir))
        (project_dir / "test.py").write_text("modified content")
        ledger.rollback("test.py", str(project_dir))
        assert (project_dir / "test.py").read_text() == original

    def test_commit_creates_parent_dirs(self, ledger, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        content = "nested file content"
        result = ledger.commit("sub/dir/test.py", content, str(project_dir))
        assert (project_dir / "sub" / "dir" / "test.py").exists()


class TestSimpleCache:
    """Tests for SimpleCache SQLite theorem caching."""

    def test_lookup_returns_none_when_empty(self):
        cache = SimpleCache()
        intent = {"op": OperationType.CREATE, "goal": GoalType.FEATURE_ADD, "target": "nonexistent_unique_999.py"}
        result = cache.lookup(intent)
        assert result is None

    def test_save_and_lookup(self):
        initialize_databases()
        cache = SimpleCache()
        intent = {"op": OperationType.CREATE, "goal": GoalType.FEATURE_ADD, "target": "test.py"}
        proof = "PROVEN"
        solution = {"h": "abc12345", "code": "x = 1"}
        cache.save(intent, proof, solution)
        result = cache.lookup(intent)
        assert result is not None
        assert result["h"] == "abc12345"


class TestTitanEngine:
    """Tests for the full TitanEngine pipeline."""

    def test_engine_initialization(self):
        engine = TitanEngine()
        assert engine.parser is not None
        assert engine.router is not None
        assert engine.planner is not None
        assert engine.cache is not None
        assert engine.ledger is not None
        assert engine.sandbox is not None

    def test_execute_create(self):
        engine = TitanEngine()
        result = engine.execute("create new feature for app.py")
        assert result["status"] in ["SUCCESS", "CACHED", "NO_OP", "ROLLBACK"]
        if result["status"] == "SUCCESS":
            assert result["code"] != ""
            assert result["hash"] != "N/A"

    def test_execute_search(self):
        engine = TitanEngine()
        result = engine.execute("search for auth.py")
        assert result["status"] in ["SUCCESS", "CACHED", "NO_OP", "ROLLBACK"]

    def test_execute_returns_dict(self):
        engine = TitanEngine()
        result = engine.execute("create feature")
        assert isinstance(result, dict)
        assert "status" in result

    def test_template_generation_python(self):
        engine = TitanEngine()
        template = engine._generate_template("app.py", "python")
        assert "def main" in template
        assert "app.py" in template

    def test_template_generation_kotlin(self):
        engine = TitanEngine()
        template = engine._generate_template("App.kt", "kotlin")
        assert "fun main" in template

    def test_template_generation_go(self):
        engine = TitanEngine()
        template = engine._generate_template("main.go", "go")
        assert "package main" in template
        assert "fmt" in template


class TestLocalEngineUtils:
    """Tests for utility functions."""

    def test_get_data_dir_returns_path(self):
        result = get_data_dir()
        assert isinstance(result, Path)

    def test_get_db_path_returns_string(self):
        result = get_db_path("test.sqlite")
        assert isinstance(result, str)
        assert "test.sqlite" in result

    def test_intent_keywords_coverage(self):
        assert OperationType.CREATE in INTENT_KEYWORDS
        assert OperationType.REFACTOR in INTENT_KEYWORDS
        assert OperationType.DELETE in INTENT_KEYWORDS
        assert OperationType.SEARCH in INTENT_KEYWORDS

    def test_goal_keywords_coverage(self):
        assert GoalType.MODERN_PATTERN in GOAL_KEYWORDS
        assert GoalType.COMPLEXITY_REDUCTION in GOAL_KEYWORDS
        assert GoalType.BUG_FIX in GOAL_KEYWORDS
        assert GoalType.FEATURE_ADD in GOAL_KEYWORDS
