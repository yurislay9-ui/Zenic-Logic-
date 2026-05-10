"""
TITAN OMNISCALE X - Resilience Patterns v16

Facade module — re-exports resilience pattern components
from sub-modules for convenient single-point imports.

Usage::

    from src.core.patterns.resilience import (
        CircuitBreaker, CircuitState, CircuitOpenError,
        RetryConfig, retry, retry_async, with_retry,
    )

Designed for Android/Termux (500MB RAM) — stdlib only.
"""

from .circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from .retry import RetryConfig, retry, retry_async, with_retry, with_retry_async, RetryScope

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    # Retry
    "RetryConfig",
    "retry",
    "retry_async",
    "with_retry",
    "with_retry_async",
    "RetryScope",
]
