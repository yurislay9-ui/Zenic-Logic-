"""
semantic_parts — Modularized SemanticEngine components.
"""

from ._imports import (
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    INTENT_PROTOTYPES,
    GOAL_PROTOTYPES,
    SemanticResult,
)
from .engine import SemanticEngine

__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "INTENT_PROTOTYPES",
    "GOAL_PROTOTYPES",
    "SemanticResult",
    "SemanticEngine",
]
