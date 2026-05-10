"""
TITAN OMNISCALE X - Resilience Patterns v16

Facade module — re-exports resilience pattern components
from sub-modules for convenient single-point imports.

Usage::

    from src.core.patterns.resilience import (
        CircuitBreaker, CircuitOpenError,
        RetryConfig, with_retry,
    )

Designed for Android/Termux (500MB RAM) — stdlib only.
"""

from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .retry import RetryConfig, with_retry

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitOpenError",
    # Retry
    "RetryConfig",
    "with_retry",
]
