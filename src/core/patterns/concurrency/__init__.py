"""
TITAN OMNISCALE X - Concurrency Patterns Facade

Re-exports the public API of the concurrency pattern sub-package.
"""

from src.core.patterns.concurrency.read_write_lock import ReadWriteLock

__all__ = [
    "ReadWriteLock",
]
