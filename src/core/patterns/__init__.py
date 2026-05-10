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
    CircuitOpenError    — Exception when circuit is open
    RetryConfig         — Retry configuration dataclass
    with_retry          — Synchronous retry with config

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
    Mediator            — Centralized request/response dispatcher
    Request             — Request dataclass for mediator
    Response            — Response dataclass for mediator
"""

# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------
from src.core.patterns.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryConfig,
    with_retry,
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
    Mediator,
    Request,
    Response,
)

__all__ = [
    # Resilience
    "CircuitBreaker",
    "CircuitOpenError",
    "RetryConfig",
    "with_retry",
    # Behavioral
    "StrategyRegistry",
    # Concurrency
    "ReadWriteLock",
    # Orchestration
    "EventBus",
    "Event",
    "Mediator",
    "Request",
    "Response",
]
