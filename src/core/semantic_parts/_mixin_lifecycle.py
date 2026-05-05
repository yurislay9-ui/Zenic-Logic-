"""
Mixin: Model lifecycle methods (load, unload, stats).
"""

import time
import logging

from ._imports import EMBEDDING_MODEL, EMBEDDING_DIM, INTENT_PROTOTYPES, GOAL_PROTOTYPES, np, logger


class LifecycleMixin:
    """Model lifecycle for SemanticEngine: __init__, load, unload, stats."""

    def _init_lifecycle(self, auto_load: bool = True):
        """Initialize lifecycle state (called from SemanticEngine.__init__)."""
        self._model = None
        self._loaded = False
        self._load_time = 0.0
        self._call_count = 0
        self._embed_cache = {}  # Text -> embedding cache
        self._prototype_embeddings = {}  # Intent -> mean prototype
        self._goal_prototype_embeddings = {}

        if auto_load:
            self.load_model()

    def load_model(self) -> bool:
        """Carga el modelo de embeddings. Returns True if loaded."""
        if self._loaded and self._model is not None:
            return True

        try:
            from fastembed import TextEmbedding
            import warnings
            start = time.time()
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*mean pooling.*", category=UserWarning)
                self._model = TextEmbedding(model_name=EMBEDDING_MODEL)
            self._load_time = time.time() - start
            self._loaded = True

            # Pre-compute prototype embeddings
            self._build_prototypes()

            logger.info(f"SemanticEngine: {EMBEDDING_MODEL} loaded in {self._load_time:.1f}s")
            return True
        except ImportError:
            logger.warning("SemanticEngine: fastembed not installed. Using fallbacks.")
            return False
        except Exception as e:
            logger.warning(f"SemanticEngine: Failed to load model: {e}")
            self._model = None
            return False

    def unload_model(self):
        """Libera el modelo de memoria."""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False
            self._embed_cache.clear()
            self._prototype_embeddings.clear()
            self._goal_prototype_embeddings.clear()
            logger.info("SemanticEngine: Model unloaded")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._model is not None

    @property
    def stats(self) -> dict:
        return {
            "model_loaded": self.is_loaded,
            "model_name": EMBEDDING_MODEL if self.is_loaded else "none",
            "load_time_s": self._load_time,
            "total_calls": self._call_count,
            "cache_size": len(self._embed_cache),
            "embedding_dim": EMBEDDING_DIM,
        }
