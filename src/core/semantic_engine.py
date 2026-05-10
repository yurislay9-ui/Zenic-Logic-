"""
TITAN OMNISCALE X - SemanticEngine (Facade)

Thin facade: all implementation lives in semantic_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - semantic_parts._imports:          Constants, SemanticResult dataclass, numpy helpers
  - semantic_parts._mixin_lifecycle:  LifecycleMixin (init, shutdown, health check)
  - semantic_parts._mixin_embed:      EmbedMixin (embedding generation, similarity)
  - semantic_parts._mixin_classify:   ClassifyMixin (intent/goal classification)
  - semantic_parts._mixin_search:     SearchMixin (semantic search, nearest neighbors)
  - semantic_parts.engine:            SemanticEngine class (inherits all mixins)

Public API:
  Classes:    SemanticEngine, SemanticResult
  Constants:  EMBEDDING_MODEL, EMBEDDING_DIM, INTENT_PROTOTYPES, GOAL_PROTOTYPES
"""

from .semantic_parts import *  # noqa: F401,F403
from .semantic_parts import SemanticEngine, SemanticResult

__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "INTENT_PROTOTYPES",
    "GOAL_PROTOTYPES",
    "SemanticResult",
    "SemanticEngine",
]
