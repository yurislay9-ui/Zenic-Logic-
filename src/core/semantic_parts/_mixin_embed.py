"""
Mixin: Core embedding and similarity methods.
"""

import hashlib
import logging

from ._imports import np, logger


class EmbedMixin:
    """Core embedding and similarity methods for SemanticEngine."""

    def embed(self, text: str):
        """Genera embedding para un texto. Cached."""
        if not self.is_loaded:
            return None

        # Check cache — use full hash to avoid collisions from truncated keys
        cache_key = hashlib.sha256(text.encode()).hexdigest()
        if cache_key in self._embed_cache:
            return self._embed_cache[cache_key]

        self._call_count += 1
        try:
            result = list(self._model.embed([text]))
            if result:
                emb = np.array(result[0], dtype=np.float32)
                # Normalize for cosine similarity (faster dot product)
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                self._embed_cache[cache_key] = emb
                # Limit cache size — evict oldest 100 entries when over 500
                if len(self._embed_cache) > 500:
                    keys = list(self._embed_cache.keys())[:100]
                    for k in keys:
                        del self._embed_cache[k]
                return emb
        except Exception as e:
            logger.warning(f"SemanticEngine: Embedding failed: {e}")
        return None

    def embed_batch(self, texts: list):
        """Genera embeddings para múltiples textos. Más eficiente."""
        if not self.is_loaded:
            return []

        self._call_count += 1
        try:
            results = list(self._model.embed(texts))
            embeddings = []
            for r in results:
                emb = np.array(r, dtype=np.float32)
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                embeddings.append(emb)
            return embeddings
        except Exception as e:
            logger.warning(f"SemanticEngine: Batch embedding failed: {e}")
            return []

    @staticmethod
    def similarity(a, b) -> float:
        """Similitud coseno entre dos embeddings normalizados (= dot product)."""
        return float(np.dot(a, b))

    def similarity_text(self, text_a: str, text_b: str) -> float:
        """Similitud semántica entre dos textos."""
        emb_a = self.embed(text_a)
        emb_b = self.embed(text_b)
        if emb_a is not None and emb_b is not None:
            return self.similarity(emb_a, emb_b)
        return 0.0
