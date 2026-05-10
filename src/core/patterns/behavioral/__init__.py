"""
TITAN OMNISCALE X - Behavioral Patterns Facade

Re-exports the public API of the behavioral pattern sub-package.
"""

from src.core.patterns.behavioral.strategy import StrategyRegistry

__all__ = [
    # Strategy
    "StrategyRegistry",
]
