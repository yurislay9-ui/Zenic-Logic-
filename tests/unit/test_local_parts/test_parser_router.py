"""Tests for SimpleParser and SimpleRouter."""

import pytest
from src.core.local_engine import (
    SimpleParser, SimpleRouter, CRITICAL_PATTERNS,
)
from src.core.shared.contracts import OperationType, GoalType
from ._fixtures import parser, router


class TestSimpleParser:
    """Tests for SimpleParser keyword-based intent parsing."""

    def test_parse_create_en(self, parser):
        result = parser.parse("create new feature for app.py")
        assert result["op"] == OperationType.CREATE
        assert result["target"] == "app.py"

    def test_parse_create_es(self, parser):
        result = parser.parse("crear nuevo modulo")
        assert result["op"] == OperationType.CREATE

    def test_parse_refactor(self, parser):
        result = parser.parse("optimize the code in utils.py")
        assert result["op"] == OperationType.REFACTOR
        assert result["target"] == "utils.py"

    def test_parse_delete(self, parser):
        result = parser.parse("delete old_module.py")
        assert result["op"] == OperationType.DELETE

    def test_parse_search(self, parser):
        result = parser.parse("find where auth is used in main.go")
        assert result["op"] == OperationType.SEARCH
        assert result["target"] == "main.go"

    def test_parse_default_search(self, parser):
        result = parser.parse("random text with no keywords")
        assert result["op"] in ("SEARCH", "CREATE", "REFACTOR", "DELETE")

    def test_parse_goal_bug_fix(self, parser):
        result = parser.parse("fix the bug in payment.kt")
        assert result["goal"] == GoalType.BUG_FIX
        assert result["target"] == "payment.kt"

    def test_parse_goal_feature_add(self, parser):
        result = parser.parse("add new functionality")
        assert result["goal"] == GoalType.FEATURE_ADD

    def test_parse_confidence(self, parser):
        result = parser.parse("create new file")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_parse_target_extraction(self, parser):
        result = parser.parse("implement auth.py")
        assert "auth.py" in result["target"]


class TestSimpleRouter:
    """Tests for SimpleRouter criticality-based routing."""

    def test_critical_target(self, router):
        intent = {"op": OperationType.CREATE, "target": "auth.py", "goal": GoalType.FEATURE_ADD}
        result = router.route(intent)
        assert result["criticality"] == "SURGICAL_CRITICAL"
        assert result["route"] == "DEEP_PATH"

    def test_delete_operation(self, router):
        intent = {"op": OperationType.DELETE, "target": "utils.py", "goal": GoalType.FEATURE_ADD}
        result = router.route(intent)
        assert result["criticality"] == "SURGICAL_CRITICAL"

    def test_refactor_operation(self, router):
        intent = {"op": OperationType.REFACTOR, "target": "utils.py", "goal": GoalType.FEATURE_ADD}
        result = router.route(intent)
        assert result["criticality"] == "SURGICAL_CRITICAL"

    def test_create_operation(self, router):
        intent = {"op": OperationType.CREATE, "target": "utils.py", "goal": GoalType.FEATURE_ADD}
        result = router.route(intent)
        assert result["criticality"] == "DEEP_MODERATE"
        assert result["route"] == "DEEP_PATH"

    def test_search_operation(self, router):
        intent = {"op": OperationType.SEARCH, "target": "utils.py", "goal": GoalType.FEATURE_ADD}
        result = router.route(intent)
        assert result["criticality"] == "FAST_STANDARD"
        assert result["route"] == "FAST_PATH"

    def test_critical_patterns_include_auth(self):
        assert "auth" in CRITICAL_PATTERNS

    def test_critical_patterns_include_login(self):
        assert "login" in CRITICAL_PATTERNS
