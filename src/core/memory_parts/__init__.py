"""
SmartMemory Sub-package — Multi-layer memory system for Zenic-Logic v18.

SmartMemory composes four focused mixins:

    SmartMemory(DatabaseMixin, EpisodesMixin, LongTermMixin, CacheMixin)

Memory layers:
    Working Memory   — Short-term context for the current request (in-memory)
    Semantic Cache   — Embedding-based cache for similar query detection
    Long-term Memory — Persistent storage of successful patterns/solutions
    Episodic Memory  — Session-scoped interaction history

Facade import (backward-compatible):
    from src.core.smart_memory import SmartMemory

Re-exports all public symbols from the modularized SmartMemory components.
"""

from .types import (
    MemoryEntry,
    DB_DIR,
    DB_PATH,
    MAX_WORKING_ENTRIES,
    MAX_COMPRESSED_TOKENS,
    IMPORTANCE_THRESHOLD,
    SEMANTIC_CACHE_THRESHOLD,
    MAX_LONG_TERM_ENTRIES,
    MAX_EPISODIC_ENTRIES,
    MAX_PROCEDURAL_ENTRIES,
    MAX_PROJECT_ENTRIES,
    HAS_NUMPY,
    logger,
)
from .database import DatabaseMixin
from .cache import CacheMixin
from .longterm import LongTermMixin
from .episodes import EpisodesMixin
from .memory import SmartMemory

__all__ = [
    # Main class
    "SmartMemory",
    # Data types
    "MemoryEntry",
    # Mixins
    "DatabaseMixin",
    "CacheMixin",
    "LongTermMixin",
    "EpisodesMixin",
    # Constants
    "DB_DIR",
    "DB_PATH",
    "MAX_WORKING_ENTRIES",
    "MAX_COMPRESSED_TOKENS",
    "IMPORTANCE_THRESHOLD",
    "SEMANTIC_CACHE_THRESHOLD",
    "MAX_LONG_TERM_ENTRIES",
    "MAX_EPISODIC_ENTRIES",
    "MAX_PROCEDURAL_ENTRIES",
    "MAX_PROJECT_ENTRIES",
    # Module-level flags
    "HAS_NUMPY",
    # Logger
    "logger",
]
