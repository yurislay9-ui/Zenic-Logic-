"""
TITAN OMNISCALE X - Retry Pattern v16

Comprehensive retry with exponential/linear/fixed backoff, jitter,
and on_retry callbacks. Designed for Android/Termux (500MB RAM) — stdlib only.

Backoff strategies:
    exponential : delay = base_delay * (exponential_base ** (attempt - 1))
    linear      : delay = base_delay * attempt
    fixed       : delay = base_delay

Jitter: random.uniform(0, jitter_max * current_delay) added when jitter=True.
"""

import asyncio
import functools
import logging
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)

__all__ = [
    "RetryConfig",
    "with_retry",
    "with_config_retry",
]


# ============================================================
#  CONFIGURATION
# ============================================================

@dataclass
class RetryConfig:
    """
    Configuration for retry behaviour.

    Attributes:
        max_attempts: Maximum number of attempts (1 = no retry).
        base_delay: Base delay in seconds between retries.
        max_delay: Upper bound for the computed delay.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to the delay.
        jitter_max: Jitter multiplier (0..1). Jitter ∈ [0, jitter_max * delay).
        retryable_exceptions: Exception types that trigger a retry.
        on_retry: Callback invoked on each retry: (attempt, exception, delay).
        backoff_strategy: One of ``"exponential"``, ``"linear"``, ``"fixed"``.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.5
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
    backoff_strategy: str = "exponential"

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be >= 0")
        if self.max_delay < 0:
            raise ValueError("max_delay must be >= 0")
        if self.exponential_base <= 0:
            raise ValueError("exponential_base must be > 0")
        if not (0.0 <= self.jitter_max <= 1.0):
            raise ValueError("jitter_max must be in [0.0, 1.0]")
        if self.backoff_strategy not in ("exponential", "linear", "fixed"):
            raise ValueError(
                f"backoff_strategy must be 'exponential', 'linear', or 'fixed', "
                f"got {self.backoff_strategy!r}"
            )


# ============================================================
#  DELAY CALCULATION
# ============================================================

def _compute_delay(config: RetryConfig, attempt: int) -> float:
    """
    Compute the delay for the given attempt number (1-based).

    The delay is clamped to ``[0, max_delay]`` and optionally has jitter
    applied.
    """
    if config.backoff_strategy == "exponential":
        delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    elif config.backoff_strategy == "linear":
        delay = config.base_delay * attempt
    else:  # fixed
        delay = config.base_delay

    delay = min(delay, config.max_delay)

    if config.jitter and delay > 0:
        jitter_amount = random.uniform(0, config.jitter_max * delay)
        delay += jitter_amount

    return delay


# ============================================================
#  PROGRAMMATIC RETRY
# ============================================================

def with_retry(
    func: Callable[..., Any],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute *func* with retry logic according to *config*.

    Args:
        func: Synchronous callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *func*.
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception encountered after all attempts are exhausted.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except config.retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_attempts:
                logger.error(
                    "Retry exhausted for %s after %d attempts: %s",
                    getattr(func, "__name__", repr(func)),
                    attempt,
                    exc,
                )
                raise

            delay = _compute_delay(config, attempt)

            if config.on_retry is not None:
                try:
                    config.on_retry(attempt, exc, delay)
                except Exception as callback_err:
                    logger.warning(
                        "on_retry callback error: %s", callback_err,
                    )

            logger.info(
                "Retry %d/%d for %s after %.2fs: %s",
                attempt,
                config.max_attempts,
                getattr(func, "__name__", repr(func)),
                delay,
                exc,
            )
            time.sleep(delay)

    # Should be unreachable, but for type-safety:
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("with_retry: unreachable state")


# Alias: prefer ``with_config_retry`` to distinguish from
# ``src.core.shared.retry.with_retry`` (simple procedural retry)
# and ``src.core.agents_v2.resilience.with_agent_retry`` (decorator-style).
with_config_retry = with_retry


async def with_retry_async(
    func: Callable[..., Any],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute an async *func* with retry logic according to *config*.

    Args:
        func: Asynchronous callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *func*.
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception encountered after all attempts are exhausted.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as exc:
            last_exception = exc
            if attempt >= config.max_attempts:
                logger.error(
                    "Retry exhausted for %s after %d attempts: %s",
                    getattr(func, "__name__", repr(func)),
                    attempt,
                    exc,
                )
                raise

            delay = _compute_delay(config, attempt)

            if config.on_retry is not None:
                try:
                    config.on_retry(attempt, exc, delay)
                except Exception as callback_err:
                    logger.warning(
                        "on_retry callback error: %s", callback_err,
                    )

            logger.info(
                "Retry %d/%d for %s after %.2fs: %s",
                attempt,
                config.max_attempts,
                getattr(func, "__name__", repr(func)),
                delay,
                exc,
            )
            await asyncio.sleep(delay)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("with_retry_async: unreachable state")


# ============================================================
#  DECORATORS
# ============================================================

def retry(config: Optional[RetryConfig] = None) -> Callable[..., Any]:
    """
    Decorator for synchronous functions with retry logic.

    Usage::

        @retry(RetryConfig(max_attempts=5))
        def flaky_operation():
            ...

        @retry()  # uses default RetryConfig
        def another_flaky():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return with_retry(func, config, *args, **kwargs)
        return wrapper
    return decorator


def retry_async(config: Optional[RetryConfig] = None) -> Callable[..., Any]:
    """
    Decorator for asynchronous functions with retry logic.

    Usage::

        @retry_async(RetryConfig(max_attempts=5))
        async def flaky_async():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_retry_async(func, config, *args, **kwargs)
        return wrapper
    return decorator


# ============================================================
#  CONTEXT MANAGER — RetryScope
# ============================================================

class RetryScope:
    """
    Context manager that provides a shared retry configuration for
    multiple operations.

    Usage::

        with RetryScope(RetryConfig(max_attempts=3)) as scope:
            scope.execute(flaky_func, arg1, arg2)
            scope.execute(another_func, kwarg=42)

    The scope collects stats across all operations.
    """

    def __init__(self, config: Optional[RetryConfig] = None) -> None:
        self._config = config or RetryConfig()
        self._total_operations: int = 0
        self._total_retries: int = 0
        self._total_failures: int = 0

    # ----------------------------------------------------------
    #  Context manager protocol
    # ----------------------------------------------------------

    def __enter__(self) -> "RetryScope":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        logger.debug(
            "RetryScope exiting: %d operations, %d retries, %d failures",
            self._total_operations,
            self._total_retries,
            self._total_failures,
        )

    # ----------------------------------------------------------
    #  Execution
    # ----------------------------------------------------------

    def execute(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute *func* within this scope's retry configuration."""
        self._total_operations += 1
        retry_count_holder = [0]

        original_on_retry = self._config.on_retry

        def counting_on_retry(
            attempt: int, exc: Exception, delay: float
        ) -> None:
            retry_count_holder[0] += 1
            self._total_retries += 1
            if original_on_retry is not None:
                original_on_retry(attempt, exc, delay)

        # Temporarily override on_retry to count retries
        saved_on_retry = self._config.on_retry
        self._config.on_retry = counting_on_retry
        try:
            result = with_retry(func, self._config, *args, **kwargs)
        except Exception:
            self._total_failures += 1
            raise
        finally:
            self._config.on_retry = saved_on_retry

        return result

    async def execute_async(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an async *func* within this scope's retry configuration."""
        self._total_operations += 1
        retry_count_holder = [0]

        original_on_retry = self._config.on_retry

        def counting_on_retry(
            attempt: int, exc: Exception, delay: float
        ) -> None:
            retry_count_holder[0] += 1
            self._total_retries += 1
            if original_on_retry is not None:
                original_on_retry(attempt, exc, delay)

        saved_on_retry = self._config.on_retry
        self._config.on_retry = counting_on_retry
        try:
            result = await with_retry_async(func, self._config, *args, **kwargs)
        except Exception:
            self._total_failures += 1
            raise
        finally:
            self._config.on_retry = saved_on_retry

        return result

    # ----------------------------------------------------------
    #  Stats
    # ----------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Snapshot of scope statistics."""
        return {
            "total_operations": self._total_operations,
            "total_retries": self._total_retries,
            "total_failures": self._total_failures,
            "config": {
                "max_attempts": self._config.max_attempts,
                "backoff_strategy": self._config.backoff_strategy,
                "base_delay": self._config.base_delay,
                "max_delay": self._config.max_delay,
            },
        }

    def __repr__(self) -> str:
        return (
            f"RetryScope(ops={self._total_operations}, "
            f"retries={self._total_retries}, "
            f"failures={self._total_failures})"
        )
