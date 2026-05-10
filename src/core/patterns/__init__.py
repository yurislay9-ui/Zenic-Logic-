"""
TITAN OMNISCALE X - Design Patterns Package

Active design pattern library for the Zenic-Logic AI code
generation system, optimized for resource-constrained devices
(Android/Termux, 500MB RAM).

All patterns use only Python stdlib — no external dependencies.
All pattern classes are thread-safe.

Active Patterns (used by the pipeline):

  Resilience Patterns
  -------------------
    CircuitBreaker      — Thread-safe circuit breaker with state machine
    CircuitState        — Enum for CLOSED/OPEN/HALF_OPEN states
    CircuitOpenError    — Exception when circuit is open
    RetryConfig         — Retry configuration dataclass
    retry               — Synchronous retry decorator
    retry_async         — Async retry decorator
    with_retry          — Synchronous retry context manager
    with_retry_async    — Async retry context manager
    RetryScope          — Scoped retry with counting

  Behavioral Patterns
  -------------------
    StrategyRegistry    — Named strategy registry with defaults

  Concurrency Patterns
  --------------------
    ReadWriteLock       — RW lock with writer preference (sync + async)

  Orchestration Patterns
  ----------------------
    EventBus            — Observer/Pub-Sub for decoupled events
    Event               — Event dataclass
    EventHandler        — ABC for event handlers
    Mediator            — Centralized request/response dispatcher
    Request             — Request dataclass for mediator
    Response            — Response dataclass for mediator
    RequestHandler      — ABC for request handlers
"""

# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------
from src.core.patterns.resilience import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryConfig,
    retry,
    retry_async,
    with_retry,
    with_retry_async,
    RetryScope,
)

# ---------------------------------------------------------------------------
# Behavioral
# ---------------------------------------------------------------------------
from src.core.patterns.behavioral import (
    StrategyRegistry,
)

# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
from src.core.patterns.concurrency import (
    ReadWriteLock,
)

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
from src.core.patterns.orchestration import (
    EventBus,
    Event,
    EventHandler,
    Mediator,
    Request,
    Response,
    RequestHandler,
)

__all__ = [
    # Resilience
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "RetryConfig",
    "retry",
    "retry_async",
    "with_retry",
    "with_retry_async",
    "RetryScope",
    # Behavioral
    "StrategyRegistry",
    # Concurrency
    "ReadWriteLock",
    # Orchestration
    "EventBus",
    "Event",
    "EventHandler",
    "Mediator",
    "Request",
    "Response",
    "RequestHandler",
]
