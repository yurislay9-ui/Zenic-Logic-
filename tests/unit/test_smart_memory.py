"""
Unit tests for SmartMemory

Tests initialization, episodic memory (add_episode/find_episodes),
procedural memory (learn_pattern/find_patterns), working memory,
semantic cache, thread safety, and utility methods.
"""

import os
import time
import json
import sqlite3
import tempfile
import threading
import pytest
from unittest.mock import MagicMock, patch

import numpy as np

from src.core.smart_memory import (
    SmartMemory, MemoryEntry, DB_PATH,
    MAX_WORKING_ENTRIES, IMPORTANCE_THRESHOLD,
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect SmartMemory DB to a temporary directory for isolation."""
    tmp_db_dir = str(tmp_path / "smart_mem_test")
    os.makedirs(tmp_db_dir, exist_ok=True)
    tmp_db_path = os.path.join(tmp_db_dir, "smart_memory.sqlite")

    monkeypatch.setattr("src.core.smart_memory.DB_DIR", tmp_db_dir)
    monkeypatch.setattr("src.core.smart_memory.DB_PATH", tmp_db_path)
    yield tmp_db_path


@pytest.fixture
def memory():
    """Create a SmartMemory instance with no semantic engine (fallback mode)."""
    return SmartMemory(semantic_engine=None)


@pytest.fixture
def memory_with_semantic():
    """Create a SmartMemory with a mocked semantic engine."""
    sem = MagicMock()
    sem.is_loaded = True
    dummy_emb = np.random.randn(384).astype(np.float32)
    dummy_emb = dummy_emb / np.linalg.norm(dummy_emb)
    sem.embed.return_value = dummy_emb
    sem.similarity.return_value = 0.9
    mem = SmartMemory(semantic_engine=sem)
    return mem


# ============================================================
#  Initialization Tests
# ============================================================

class TestInitialization:
    """Tests for SmartMemory initialization."""

    def test_session_id_generated(self, memory):
        """Session ID should be an 8-char hex string."""
        assert len(memory._session_id) == 8
        assert all(c in "0123456789abcdef" for c in memory._session_id)

    def test_default_client_id(self, memory):
        """Default client_id should be 'default'."""
        assert memory._client_id == "default"

    def test_working_memory_empty(self, memory):
        """Working memory should start empty."""
        assert len(memory._working_memory) == 0

    def test_db_tables_created(self, memory, temp_db):
        """All required DB tables should be created on init."""
        with sqlite3.connect(temp_db) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "semantic_cache" in tables, f"semantic_cache not in {tables}"
        assert "long_term_memory" in tables, f"long_term_memory not in {tables}"
        assert "episodic_memory" in tables, f"episodic_memory not in {tables}"
        assert "procedural_memory" in tables, f"procedural_memory not in {tables}"
        assert "project_memory" in tables, f"project_memory not in {tables}"

    def test_semantic_engine_none(self, memory):
        """Semantic engine should be None when not provided."""
        assert memory._semantic is None


# ============================================================
#  Client ID Tests
# ============================================================

class TestClientId:
    """Tests for multi-client isolation."""

    def test_set_valid_client_id(self, memory):
        """Should accept valid client_id strings."""
        memory.set_client_id("client_abc")
        assert memory._client_id == "client_abc"

    def test_set_empty_client_id_raises(self, memory):
        """Should raise ValueError for empty client_id."""
        with pytest.raises(ValueError):
            memory.set_client_id("")

    def test_set_nonstring_client_id_raises(self, memory):
        """Should raise ValueError for non-string client_id."""
        with pytest.raises(ValueError):
            memory.set_client_id(123)

    def test_set_whitespace_client_id_raises(self, memory):
        """Should raise ValueError for whitespace-only client_id."""
        with pytest.raises(ValueError):
            memory.set_client_id("   ")


# ============================================================
#  Working Memory Tests
# ============================================================

class TestWorkingMemory:
    """Tests for working memory (short-term context)."""

    def test_add_working_entry(self, memory):
        """Should add entry to working memory."""
        memory.add_working("test query", "test response", operation="CREATE")
        assert len(memory._working_memory) == 1
        assert memory._working_memory[0].query == "test query"

    def test_working_context_format(self, memory):
        """get_working_context should return formatted string."""
        memory.add_working("q1", "r1", operation="CREATE", goal="FEATURE_ADD")
        ctx = memory.get_working_context()
        assert "Previous context:" in ctx
        assert "CREATE" in ctx

    def test_working_context_empty(self, memory):
        """Should return empty string when no entries."""
        assert memory.get_working_context() == ""

    def test_eviction_on_overflow(self, memory):
        """Should evict lowest importance entry when over MAX_WORKING_ENTRIES."""
        for i in range(MAX_WORKING_ENTRIES + 5):
            memory.add_working(f"q{i}", f"r{i}", importance=0.1 + i * 0.01)
        assert len(memory._working_memory) <= MAX_WORKING_ENTRIES

    def test_get_recent_operations(self, memory):
        """Should return last N operations."""
        for op in ["CREATE", "REFACTOR", "DEBUG"]:
            memory.add_working("q", "r", operation=op)
        recent = memory.get_recent_operations(2)
        assert recent == ["REFACTOR", "DEBUG"]


# ============================================================
#  Semantic Cache Tests
# ============================================================

class TestSemanticCache:
    """Tests for semantic cache (exact + semantic matching)."""

    def test_save_and_check_cache_exact(self, memory):
        """Should retrieve from cache with exact hash match."""
        memory.save_to_cache("hello world", "Hello!", operation="GREET")
        result = memory.check_cache("hello world")
        assert result is not None
        assert result["source"] == "cache_exact"
        assert result["response"] == "Hello!"

    def test_cache_miss(self, memory):
        """Should return None for uncached queries."""
        result = memory.check_cache("uncached query")
        assert result is None

    def test_cache_case_insensitive(self, memory):
        """Should match regardless of case differences."""
        memory.save_to_cache("Hello World", "response")
        result = memory.check_cache("hello world")
        assert result is not None

    def test_high_importance_promotes_to_long_term(self, memory):
        """Entries with importance >= threshold should promote to long-term."""
        memory.save_to_cache("critical query", "critical response",
                             importance=IMPORTANCE_THRESHOLD)
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
        assert count >= 1

    def test_cache_semantic_match(self, memory_with_semantic):
        """Should retrieve from cache via semantic similarity."""
        memory_with_semantic.save_to_cache("authentication module", "auth code")
        result = memory_with_semantic.check_cache("auth module")
        # With mock similarity=0.9, should get a semantic match
        assert result is not None
        assert result["source"] == "cache_semantic"


# ============================================================
#  Episodic Memory Tests
# ============================================================

class TestEpisodicMemory:
    """Tests for episodic memory (event history)."""

    def test_save_and_find_by_type(self, memory):
        """Should save and retrieve episodes by event type."""
        memory.save_episode("app_generated", "Generated auth app",
                            importance=0.8)
        results = memory.find_episodes(event_type="app_generated")
        assert len(results) == 1
        assert results[0]["event_type"] == "app_generated"
        assert results[0]["description"] == "Generated auth app"

    def test_find_episodes_no_match(self, memory):
        """Should return empty list for non-matching event type."""
        memory.save_episode("app_generated", "test")
        results = memory.find_episodes(event_type="nonexistent")
        assert results == []

    def test_find_episodes_limit(self, memory):
        """Should respect the limit parameter."""
        for i in range(10):
            memory.save_episode("app_generated", f"app {i}")
        results = memory.find_episodes(event_type="app_generated", limit=3)
        assert len(results) <= 3

    def test_find_episodes_by_semantic_query(self, memory_with_semantic):
        """Should find episodes via semantic similarity query."""
        memory_with_semantic.save_episode("deployment", "Deployed to production")
        results = memory_with_semantic.find_episodes(query="production deploy")
        # With mock similarity=0.9, should find results
        assert len(results) >= 1


# ============================================================
#  Procedural Memory Tests
# ============================================================

class TestProceduralMemory:
    """Tests for procedural memory (learned patterns)."""

    def test_learn_and_find_pattern(self, memory):
        """Should learn a pattern and find it by type."""
        memory.learn_pattern("auth_jwt", "strategy", "JWT authentication pattern",
                             steps=["create token", "verify token"], success=True)
        results = memory.find_patterns(pattern_type="strategy")
        assert len(results) == 1
        assert results[0]["pattern_name"] == "auth_jwt"

    def test_learn_pattern_updates_success_rate(self, memory):
        """Should update success rate when pattern is learned again."""
        memory.learn_pattern("cache_pattern", "strategy", "Caching pattern",
                             success=True)
        memory.learn_pattern("cache_pattern", "strategy", "Caching pattern",
                             success=False)
        results = memory.find_patterns(pattern_type="strategy")
        assert len(results) == 1
        assert results[0]["success_rate"] == 0.5

    def test_find_patterns_min_success_rate(self, memory):
        """Should filter patterns by minimum success rate."""
        memory.learn_pattern("failing", "strategy", "Bad pattern", success=False)
        results = memory.find_patterns(min_success_rate=0.5)
        # failing pattern has 0% success rate
        assert not any(r["pattern_name"] == "failing" for r in results)

    def test_find_patterns_by_semantic_query(self, memory_with_semantic):
        """Should find patterns via semantic similarity query."""
        memory_with_semantic.learn_pattern("auth_pattern", "strategy",
                                           "Authentication pattern", success=True)
        results = memory_with_semantic.find_patterns(query="login auth")
        assert len(results) >= 1


# ============================================================
#  Project Memory Tests
# ============================================================

class TestProjectMemory:
    """Tests for project memory (project continuity)."""

    def test_save_and_get_project(self, memory):
        """Should save and retrieve project details."""
        memory.save_project("myapp", project_type="fastapi",
                            description="Auth service", status="active")
        proj = memory.get_project("myapp")
        assert proj is not None
        assert proj["project_name"] == "myapp"
        assert proj["project_type"] == "fastapi"

    def test_get_nonexistent_project(self, memory):
        """Should return None for non-existent project."""
        result = memory.get_project("nonexistent")
        assert result is None

    def test_update_existing_project(self, memory):
        """Should update an existing project instead of duplicating."""
        memory.save_project("myapp", project_type="flask", status="active")
        memory.save_project("myapp", project_type="fastapi", status="generated")
        proj = memory.get_project("myapp")
        assert proj["project_type"] == "fastapi"
        assert proj["status"] == "generated"

    def test_list_projects(self, memory):
        """Should list all projects."""
        memory.save_project("proj_a", project_type="flask")
        memory.save_project("proj_b", project_type="fastapi")
        projects = memory.list_projects()
        assert len(projects) == 2

    def test_list_projects_by_status(self, memory):
        """Should filter projects by status."""
        memory.save_project("proj_a", status="active")
        memory.save_project("proj_b", status="generated")
        active = memory.list_projects(status="active")
        assert len(active) == 1
        assert active[0]["project_name"] == "proj_a"


# ============================================================
#  Importance Scoring Tests
# ============================================================

class TestImportanceScoring:
    """Tests for compute_importance static method."""

    def test_base_score(self):
        """Default importance should be around 0.5."""
        score = SmartMemory.compute_importance("query", "EXPLAIN", "READABILITY",
                                                True, 100)
        assert 0.0 <= score <= 1.0

    def test_delete_operation_higher(self):
        """DELETE operation should score higher than EXPLAIN."""
        del_score = SmartMemory.compute_importance("q", "DELETE", "BUG_FIX",
                                                     True, 100)
        explain_score = SmartMemory.compute_importance("q", "EXPLAIN", "READABILITY",
                                                        True, 100)
        assert del_score > explain_score

    def test_security_goal_higher(self):
        """SECURITY_HARDEN goal should score higher than READABILITY."""
        sec_score = SmartMemory.compute_importance("q", "CREATE", "SECURITY_HARDEN",
                                                    True, 100)
        read_score = SmartMemory.compute_importance("q", "CREATE", "READABILITY",
                                                      True, 100)
        assert sec_score > read_score

    def test_long_response_bonus(self):
        """Long responses should get a small bonus."""
        short = SmartMemory.compute_importance("q", "CREATE", "FEATURE_ADD",
                                                True, 100)
        long = SmartMemory.compute_importance("q", "CREATE", "FEATURE_ADD",
                                               True, 2000)
        assert long > short

    def test_score_bounded(self):
        """Score should always be between 0.0 and 1.0."""
        # Push score very high
        score = SmartMemory.compute_importance("q", "DELETE", "SECURITY_HARDEN",
                                                True, 5000)
        assert score <= 1.0
        # Push score very low
        score = SmartMemory.compute_importance("q", "SEARCH", "MODERN_PATTERN",
                                                False, 10)
        assert score >= 0.0


# ============================================================
#  Embedding Serialization Tests
# ============================================================

class TestEmbeddingSerialization:
    """Tests for embedding serialize/deserialize round-trip."""

    def test_round_trip(self):
        """Should preserve embedding direction through serialization (normalizes on deserialize)."""
        emb = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        blob = SmartMemory._serialize_embedding(emb)
        result = SmartMemory._deserialize_embedding(blob)
        # _deserialize_embedding normalizes the vector, so check direction (cosine similarity)
        # rather than exact values
        norm_orig = emb / np.linalg.norm(emb)
        np.testing.assert_allclose(result, norm_orig, atol=1e-6)

    def test_deserialize_none(self):
        """Should return None for None input."""
        assert SmartMemory._deserialize_embedding(None) is None

    def test_deserialize_empty(self):
        """Should return None for empty bytes."""
        assert SmartMemory._deserialize_embedding(b"") is None


# ============================================================
#  Thread Safety Tests
# ============================================================

class TestThreadSafety:
    """Tests for thread safety of working memory operations."""

    def test_concurrent_add_working(self, memory):
        """Should handle concurrent additions safely."""
        errors = []

        def add_entries(start):
            try:
                for i in range(50):
                    memory.add_working(f"q_{start}_{i}", f"r_{start}_{i}",
                                       importance=0.5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_entries, args=(j,)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(memory._working_memory) > 0

    def test_concurrent_cache_operations(self, memory):
        """Should handle concurrent cache save/check safely."""
        errors = []

        def cache_ops(thread_id):
            try:
                for i in range(20):
                    memory.save_to_cache(f"query_{thread_id}_{i}", f"resp_{i}",
                                         importance=0.5)
                    memory.check_cache(f"query_{thread_id}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=cache_ops, args=(j,)) for j in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_episode_operations(self, memory):
        """Should handle concurrent episode save/find safely."""
        errors = []

        def episode_ops(thread_id):
            try:
                for i in range(10):
                    memory.save_episode(f"event_{thread_id}", f"desc_{i}",
                                         importance=0.5)
                memory.find_episodes(event_type=f"event_{thread_id}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=episode_ops, args=(j,)) for j in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ============================================================
#  Stats Tests
# ============================================================

class TestStats:
    """Tests for stats and enhanced_stats properties."""

    def test_stats_structure(self, memory):
        """Stats should contain expected keys."""
        stats = memory.stats
        assert "session_id" in stats
        assert "client_id" in stats
        assert "working_memory_size" in stats
        assert "semantic_cache_size" in stats
        assert "long_term_memory_size" in stats

    def test_enhanced_stats_structure(self, memory):
        """Enhanced stats should contain all memory type counts."""
        stats = memory.enhanced_stats
        assert "working_memory_size" in stats
        assert "semantic_cache_size" in stats
        assert "episodic_memory_size" in stats
        assert "procedural_memory_size" in stats
        assert "project_memory_size" in stats

    def test_stats_reflects_working_memory(self, memory):
        """Working memory size should reflect added entries."""
        memory.add_working("q1", "r1")
        memory.add_working("q2", "r2")
        assert memory.stats["working_memory_size"] == 2
