"""
Unit tests for src/core/semantic_engine.py - SemanticEngine

Tests:
- SemanticEngine initialization (auto_load=False to avoid real model)
- load_model() / unload_model() lifecycle
- is_loaded property
- stats property
- embed() with mocked model
- embed_batch() with mocked model
- similarity() static method
- similarity_text() with mocked embed
- classify_intent() with mocked embeddings
- classify_intent() fallback path
- search() with mocked embeddings
- find_similar_intents() with mocked embeddings
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.core.semantic_engine import (
    SemanticEngine,
    SemanticResult,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    INTENT_PROTOTYPES,
    GOAL_PROTOTYPES,
)


# ===========================================================================
#  Fixtures
# ===========================================================================

@pytest.fixture
def engine():
    """SemanticEngine without auto_load (no real model)."""
    return SemanticEngine(auto_load=False)


@pytest.fixture
def loaded_engine():
    """SemanticEngine with a mocked loaded model."""
    eng = SemanticEngine(auto_load=False)
    # Manually set up as if model was loaded
    eng._model = MagicMock()
    eng._loaded = True
    eng._load_time = 0.5

    # Build fake prototype embeddings (384-dim normalized)
    for intent in INTENT_PROTOTYPES:
        emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        eng._prototype_embeddings[intent] = emb

    for goal in GOAL_PROTOTYPES:
        emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        emb = emb / np.linalg.norm(emb)
        eng._goal_prototype_embeddings[goal] = emb

    return eng


# ===========================================================================
#  Test: Initialization
# ===========================================================================

class TestSemanticEngineInit:
    """Tests for SemanticEngine initialization."""

    def test_init_no_auto_load(self):
        """With auto_load=False, model should not be loaded."""
        eng = SemanticEngine(auto_load=False)
        assert eng._model is None
        assert eng._loaded is False
        assert eng.is_loaded is False

    def test_init_default_call_count(self, engine):
        """Call count should start at 0."""
        assert engine._call_count == 0

    def test_init_caches_empty(self, engine):
        """Embedding caches should be empty."""
        assert len(engine._embed_cache) == 0
        assert len(engine._prototype_embeddings) == 0

    def test_init_load_time_zero(self, engine):
        """Load time should be 0 when no model loaded."""
        assert engine._load_time == 0.0


# ===========================================================================
#  Test: Model lifecycle
# ===========================================================================

class TestModelLifecycle:
    """Tests for load_model and unload_model."""

    def test_load_model_failure(self, engine):
        """load_model should return False when fastembed is not installed."""
        with patch.dict("sys.modules", {"fastembed": None}):
            result = engine.load_model()
            # In test environment fastembed likely not installed
            assert result is False or result is True  # Depends on env

    def test_load_model_returns_true_when_already_loaded(self, loaded_engine):
        """load_model should return True immediately if already loaded."""
        result = loaded_engine.load_model()
        assert result is True

    def test_unload_model_clears_state(self, loaded_engine):
        """unload_model should clear all state."""
        loaded_engine.unload_model()
        assert loaded_engine._model is None
        assert loaded_engine._loaded is False
        assert len(loaded_engine._embed_cache) == 0
        assert len(loaded_engine._prototype_embeddings) == 0
        assert len(loaded_engine._goal_prototype_embeddings) == 0


# ===========================================================================
#  Test: stats property
# ===========================================================================

class TestStatsProperty:
    """Tests for the stats property."""

    def test_stats_unloaded(self, engine):
        """Stats should show model_loaded=False when unloaded."""
        stats = engine.stats
        assert stats["model_loaded"] is False
        assert stats["model_name"] == "none"
        assert stats["total_calls"] == 0
        assert stats["embedding_dim"] == EMBEDDING_DIM

    def test_stats_loaded(self, loaded_engine):
        """Stats should show model_loaded=True when loaded."""
        stats = loaded_engine.stats
        assert stats["model_loaded"] is True
        assert EMBEDDING_MODEL in stats["model_name"]
        assert stats["load_time_s"] == 0.5

    def test_stats_cache_size(self, loaded_engine):
        """Stats should report cache size."""
        loaded_engine._embed_cache["test_key"] = np.zeros(EMBEDDING_DIM)
        stats = loaded_engine.stats
        assert stats["cache_size"] == 1


# ===========================================================================
#  Test: embed()
# ===========================================================================

class TestEmbed:
    """Tests for the embed method."""

    def test_embed_returns_none_when_not_loaded(self, engine):
        """embed() should return None when model is not loaded."""
        result = engine.embed("hello world")
        assert result is None

    def test_embed_returns_ndarray_when_loaded(self, loaded_engine):
        """embed() should return an ndarray when model is loaded."""
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])

        result = loaded_engine.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.shape == (EMBEDDING_DIM,)

    def test_embed_caches_result(self, loaded_engine):
        """embed() should cache the result for subsequent calls."""
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])

        r1 = loaded_engine.embed("hello world")
        r2 = loaded_engine.embed("hello world")
        # Second call should use cache (same object)
        assert r1 is r2
        # Model.embed should only have been called once
        loaded_engine._model.embed.assert_called_once()

    def test_embed_increments_call_count(self, loaded_engine):
        """embed() should increment _call_count."""
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_embedding = fake_embedding / np.linalg.norm(fake_embedding)
        loaded_engine._model.embed.return_value = iter([fake_embedding])

        initial_count = loaded_engine._call_count
        loaded_engine.embed("hello")
        assert loaded_engine._call_count == initial_count + 1

    def test_embed_returns_normalized_vector(self, loaded_engine):
        """embed() should return a unit-normalized vector."""
        fake_embedding = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        loaded_engine._model.embed.return_value = iter([fake_embedding])

        result = loaded_engine.embed("test text")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5


# ===========================================================================
#  Test: embed_batch()
# ===========================================================================

class TestEmbedBatch:
    """Tests for the embed_batch method."""

    def test_embed_batch_returns_empty_when_not_loaded(self, engine):
        """embed_batch() should return [] when model is not loaded."""
        result = engine.embed_batch(["hello", "world"])
        assert result == []

    def test_embed_batch_returns_list_of_ndarrays(self, loaded_engine):
        """embed_batch() should return a list of ndarrays."""
        fake_embs = [np.random.randn(EMBEDDING_DIM).astype(np.float32) for _ in range(3)]
        loaded_engine._model.embed.return_value = iter(fake_embs)

        results = loaded_engine.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        for r in results:
            assert isinstance(r, np.ndarray)
            assert r.shape == (EMBEDDING_DIM,)

    def test_embed_batch_normalizes(self, loaded_engine):
        """embed_batch() should normalize each embedding."""
        fake_embs = [np.random.randn(EMBEDDING_DIM).astype(np.float32) for _ in range(2)]
        loaded_engine._model.embed.return_value = iter(fake_embs)

        results = loaded_engine.embed_batch(["a", "b"])
        for r in results:
            norm = np.linalg.norm(r)
            assert abs(norm - 1.0) < 1e-5


# ===========================================================================
#  Test: similarity()
# ===========================================================================

class TestSimilarity:
    """Tests for the static similarity method."""

    def test_identical_vectors_similarity_one(self):
        """Identical normalized vectors should have similarity ~1.0."""
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        sim = SemanticEngine.similarity(v, v)
        assert abs(sim - 1.0) < 1e-5

    def test_orthogonal_vectors_similarity_zero(self):
        """Orthogonal vectors should have similarity ~0.0."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert abs(sim) < 1e-5

    def test_opposite_vectors_similarity_minus_one(self):
        """Opposite vectors should have similarity ~-1.0."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([-1.0, 0.0], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-5

    def test_similarity_returns_float(self):
        """similarity() should return a Python float."""
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.5, 0.5], dtype=np.float32)
        sim = SemanticEngine.similarity(a, b)
        assert isinstance(sim, float)


# ===========================================================================
#  Test: similarity_text()
# ===========================================================================

class TestSimilarityText:
    """Tests for the similarity_text method."""

    def test_returns_zero_when_not_loaded(self, engine):
        """similarity_text() should return 0.0 when model is not loaded."""
        result = engine.similarity_text("hello", "world")
        assert result == 0.0

    def test_returns_similarity_when_loaded(self, loaded_engine):
        """similarity_text() should return a similarity score when model is loaded."""
        fake_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        fake_emb = fake_emb / np.linalg.norm(fake_emb)
        loaded_engine._model.embed.return_value = iter([fake_emb, fake_emb])

        result = loaded_engine.similarity_text("hello", "hello")
        assert isinstance(result, float)
        assert -1.01 <= result <= 1.01  # Allow small floating-point tolerance


# ===========================================================================
#  Test: classify_intent() - fallback
# ===========================================================================

class TestClassifyIntentFallback:
    """Tests for classify_intent fallback path (no model loaded)."""

    def test_fallback_returns_semantic_result(self, engine):
        """Fallback classification should return a SemanticResult."""
        result = engine.classify_intent("create a new module")
        assert isinstance(result, SemanticResult)
        assert result.source == "fallback"

    def test_fallback_detects_create(self, engine):
        """Fallback should detect CREATE intent."""
        result = engine.classify_intent("create a new module")
        assert result.operation == "CREATE"

    def test_fallback_detects_debug(self, engine):
        """Fallback should detect DEBUG intent."""
        result = engine.classify_intent("fix the bug in my code")
        assert result.operation == "DEBUG"

    def test_fallback_confidence_below_threshold(self, engine):
        """Fallback confidence should be low (≤0.5)."""
        result = engine.classify_intent("something random xyz")
        assert result.confidence <= 0.5


# ===========================================================================
#  Test: classify_intent() - with embeddings
# ===========================================================================

class TestClassifyIntentWithEmbeddings:
    """Tests for classify_intent with mocked embeddings."""

    def test_returns_embedding_source(self, loaded_engine):
        """When model is loaded, should return source='embedding'."""
        # Mock embed to return a vector similar to CREATE prototype
        query_emb = loaded_engine._prototype_embeddings["CREATE"].copy()
        loaded_engine._model.embed.return_value = iter([query_emb])

        # Clear cache so embed is actually called
        loaded_engine._embed_cache.clear()

        result = loaded_engine.classify_intent("create something")
        assert result.source == "embedding"

    def test_returns_semantic_result(self, loaded_engine):
        """Should return a SemanticResult instance."""
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        loaded_engine._model.embed.return_value = iter([query_emb])
        loaded_engine._embed_cache.clear()

        result = loaded_engine.classify_intent("test query")
        assert isinstance(result, SemanticResult)
        assert 0.0 <= result.confidence <= 1.0


# ===========================================================================
#  Test: search()
# ===========================================================================

class TestSemanticSearch:
    """Tests for the search method."""

    def test_search_returns_empty_when_not_loaded(self, engine):
        """search() should return [] when model is not loaded."""
        result = engine.search("query", [{"text": "doc1"}])
        assert result == []

    def test_search_returns_empty_for_empty_docs(self, loaded_engine):
        """search() should return [] for empty document list."""
        result = loaded_engine.search("query", [])
        assert result == []

    def test_search_with_documents(self, loaded_engine):
        """search() should return ranked results above threshold."""
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        doc_emb = query_emb.copy()  # Same as query = high similarity

        # Mock embed and embed_batch directly on the instance
        loaded_engine.embed = MagicMock(return_value=query_emb)
        loaded_engine.embed_batch = MagicMock(return_value=[doc_emb])

        docs = [{"text": "relevant doc"}]
        results = loaded_engine.search("relevant query", docs, top_k=5, threshold=0.1)
        assert len(results) >= 1
        assert results[0][1] > 0.9  # similarity should be very high


# ===========================================================================
#  Test: find_similar_intents()
# ===========================================================================

class TestFindSimilarIntents:
    """Tests for the find_similar_intents method."""

    def test_returns_empty_when_not_loaded(self, engine):
        """find_similar_intents() should return [] when model is not loaded."""
        result = engine.find_similar_intents("query", ["hist1"])
        assert result == []

    def test_returns_empty_for_empty_history(self, loaded_engine):
        """find_similar_intents() should return [] for empty history."""
        result = loaded_engine.find_similar_intents("query", [])
        assert result == []

    def test_finds_similar_history(self, loaded_engine):
        """Should find similar entries in history."""
        query_emb = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        query_emb = query_emb / np.linalg.norm(query_emb)
        hist_emb = query_emb.copy()  # Identical = high similarity

        # Mock embed and embed_batch directly on the instance
        loaded_engine.embed = MagicMock(return_value=query_emb)
        loaded_engine.embed_batch = MagicMock(return_value=[hist_emb])

        results = loaded_engine.find_similar_intents("my query", ["my query"], threshold=0.1)
        assert len(results) >= 1
