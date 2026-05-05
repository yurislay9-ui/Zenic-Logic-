"""
TITAN OMNISCALE X - Distributed Circuit Breaker

Circuit breaker with shared state across multiple nodes/processes.
Unlike the single-process CircuitBreaker in patterns/resilience/,
this implementation:

- Persists circuit state to the CoordinationBackend (PostgreSQL)
- Uses optimistic concurrency control (version-based CAS) for updates
- Allows all nodes to see the same circuit state
- Supports local caching with configurable sync interval
- Gracefully falls back to local-only mode if backend is unavailable

State Machine (same as single-process):
    CLOSED  -> OPEN       (failure_threshold reached)
    OPEN    -> HALF_OPEN  (recovery_timeout elapsed)
    HALF_OPEN -> CLOSED   (success_threshold reached)
    HALF_OPEN -> OPEN     (any failure in half-open)

Integration:
    Designed to be used as a drop-in replacement for the single-process
    CircuitBreaker in the FastAPI app and other components.
"""

import enum
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .backend import CoordinationBackend
from src.core.patterns.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedCircuitBreaker",
    "SharedCircuitState",
]


# ============================================================
#  SHARED CIRCUIT STATE
# ============================================================

class SharedCircuitState:
    """
    Snapshot of circuit breaker state shared across nodes.

    Attributes:
        name: Circuit breaker name.
        state: Current state (CLOSED/OPEN/HALF_OPEN).
        failure_count: Consecutive failures in CLOSED state.
        success_count: Consecutive successes in HALF_OPEN state.
        half_open_call_count: Calls made in HALF_OPEN state.
        opened_at: Timestamp when circuit was opened.
        version: Optimistic concurrency version number.
    """
    __slots__ = (
        "name", "state", "failure_count", "success_count",
        "half_open_call_count", "opened_at", "version",
    )

    def __init__(
        self,
        name: str,
        state: str = "closed",
        failure_count: int = 0,
        success_count: int = 0,
        half_open_call_count: int = 0,
        opened_at: Optional[float] = None,
        version: int = 0,
    ) -> None:
        self.name = name
        self.state = state
        self.failure_count = failure_count
        self.success_count = success_count
        self.half_open_call_count = half_open_call_count
        self.opened_at = opened_at
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for backend storage."""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_call_count": self.half_open_call_count,
            "opened_at": self.opened_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], version: int = 0) -> "SharedCircuitState":
        """Deserialize from backend dict."""
        return cls(
            name=data.get("name", ""),
            state=data.get("state", "closed"),
            failure_count=data.get("failure_count", 0),
            success_count=data.get("success_count", 0),
            half_open_call_count=data.get("half_open_call_count", 0),
            opened_at=data.get("opened_at"),
            version=version,
        )


# ============================================================
#  DISTRIBUTED CIRCUIT BREAKER
# ============================================================

class DistributedCircuitBreaker:
    """
    Circuit breaker with shared state across distributed nodes.

    Maintains local state for fast reads and periodically syncs
    with the CoordinationBackend. Writes (state transitions) are
    persisted immediately to ensure all nodes see consistent state.

    Falls back to a local CircuitBreaker if the backend is unavailable,
    ensuring graceful degradation in single-process or disconnected mode.

    Usage::

        breaker = DistributedCircuitBreaker(
            name="orchestrator",
            backend=backend,
            failure_threshold=5,
            recovery_timeout=30.0,
        )

        # Same API as single-process CircuitBreaker
        result = breaker.call(my_function, arg1, arg2)
    """

    # How often to sync local cache from backend (seconds)
    DEFAULT_SYNC_INTERVAL = 5.0

    def __init__(
        self,
        name: str,
        backend: CoordinationBackend,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 3,
        sync_interval: float = DEFAULT_SYNC_INTERVAL,
    ) -> None:
        """
        Initialize the distributed circuit breaker.

        Args:
            name: Circuit breaker name (unique per service).
            backend: Coordination backend for shared state.
            failure_threshold: Consecutive failures before OPEN.
            recovery_timeout: Seconds before OPEN -> HALF_OPEN.
            half_open_max_calls: Max calls in HALF_OPEN.
            success_threshold: Successes in HALF_OPEN to close.
            sync_interval: How often to sync from backend.
        """
        self._name = name
        self._backend = backend
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold
        self._sync_interval = sync_interval

        # Local fallback circuit breaker (used when backend is unavailable)
        self._local_breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            success_threshold=success_threshold,
        )

        # Local cache of shared state
        self._local_state = SharedCircuitState(name=name, state="closed")
        self._last_sync: float = 0.0
        self._lock = threading.Lock()

        # Stats
        self._total_syncs: int = 0
        self._sync_errors: int = 0

    # ----------------------------------------------------------
    #  PROPERTIES
    # ----------------------------------------------------------

    @property
    def name(self) -> str:
        """Circuit breaker name."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """
        Current circuit state, synced from backend if stale.

        Returns the locally-cached state, refreshing from the backend
        if the sync interval has elapsed.
        """
        self._maybe_sync()
        state_str = self._local_state.state
        try:
            return CircuitState(state_str)
        except ValueError:
            return CircuitState.CLOSED

    @property
    def stats(self) -> Dict[str, Any]:
        """Circuit breaker statistics."""
        self._maybe_sync()
        with self._lock:
            remaining = 0.0
            if (
                self._local_state.state == "open"
                and self._local_state.opened_at is not None
            ):
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)

            return {
                "name": self._name,
                "current_state": self._local_state.state,
                "consecutive_failures": self._local_state.failure_count,
                "consecutive_successes": self._local_state.success_count,
                "half_open_call_count": self._local_state.half_open_call_count,
                "version": self._local_state.version,
                "total_syncs": self._total_syncs,
                "sync_errors": self._sync_errors,
                "remaining_timeout": remaining,
                "backend_type": type(self._backend).__name__,
            }

    # ----------------------------------------------------------
    #  RECORD OPERATIONS
    # ----------------------------------------------------------

    def record_success(self) -> None:
        """
        Record a successful call and potentially close the circuit.

        Updates both local state and persisted shared state.
        """
        with self._lock:
            state = self._local_state
            if state.state == "half_open":
                state.success_count += 1
                state.half_open_call_count += 1
                if state.success_count >= self._success_threshold:
                    state.state = "closed"
                    state.failure_count = 0
                    state.success_count = 0
                    state.half_open_call_count = 0
                    state.opened_at = None
                    logger.info(
                        "DistCircuit '%s': HALF_OPEN -> CLOSED "
                        "(%d successes)",
                        self._name, state.success_count,
                    )
            elif state.state == "closed":
                state.failure_count = 0
                state.success_count += 1

        # Also update local fallback
        self._local_breaker.record_success()

        # Persist to backend
        self._persist_state()

    def record_failure(self) -> None:
        """
        Record a failed call and potentially open the circuit.

        Updates both local state and persisted shared state.
        """
        with self._lock:
            state = self._local_state
            state.failure_count += 1
            state.success_count = 0

            if state.state == "half_open":
                state.half_open_call_count += 1
                state.state = "open"
                state.opened_at = time.monotonic()
                logger.warning(
                    "DistCircuit '%s': HALF_OPEN -> OPEN (failure in half-open)",
                    self._name,
                )
            elif state.state == "closed":
                if state.failure_count >= self._failure_threshold:
                    state.state = "open"
                    state.opened_at = time.monotonic()
                    logger.warning(
                        "DistCircuit '%s': CLOSED -> OPEN "
                        "(%d consecutive failures)",
                        self._name, state.failure_count,
                    )

        # Also update local fallback
        self._local_breaker.record_failure()

        # Persist to backend
        self._persist_state()

    # ----------------------------------------------------------
    #  CALL THROUGH BREAKER
    # ----------------------------------------------------------

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute func through the distributed circuit breaker.

        Checks shared state from backend (with local cache) before
        allowing the call. Falls back to local breaker if backend
        is unavailable.

        Args:
            func: The callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The result of func(*args, **kwargs).

        Raises:
            CircuitOpenError: If the circuit is OPEN.
        """
        # Check state (may sync from backend)
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = 0.0
            if self._local_state.opened_at is not None:
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            raise CircuitOpenError(self._name, remaining)

        if (
            current_state == CircuitState.HALF_OPEN
            and self._local_state.half_open_call_count >= self._half_open_max_calls
        ):
            raise CircuitOpenError(self._name, 0.0)

        try:
            result = func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    async def call_async(
        self, coro_func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """
        Execute an async function through the distributed circuit breaker.

        Same semantics as call() but supports async callables.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = 0.0
            if self._local_state.opened_at is not None:
                elapsed = time.monotonic() - self._local_state.opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            raise CircuitOpenError(self._name, remaining)

        if (
            current_state == CircuitState.HALF_OPEN
            and self._local_state.half_open_call_count >= self._half_open_max_calls
        ):
            raise CircuitOpenError(self._name, 0.0)

        try:
            result = await coro_func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    # ----------------------------------------------------------
    #  MANUAL CONTROL
    # ----------------------------------------------------------

    def reset(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._local_state.state = "closed"
            self._local_state.failure_count = 0
            self._local_state.success_count = 0
            self._local_state.half_open_call_count = 0
            self._local_state.opened_at = None
        self._local_breaker.reset()
        self._persist_state()
        logger.info("DistCircuit '%s': Reset to CLOSED", self._name)

    def force_open(self) -> None:
        """Force the circuit into OPEN state."""
        with self._lock:
            self._local_state.state = "open"
            self._local_state.opened_at = time.monotonic()
        self._local_breaker.force_open()
        self._persist_state()
        logger.info("DistCircuit '%s': Forced OPEN", self._name)

    def force_close(self) -> None:
        """Force the circuit into CLOSED state."""
        with self._lock:
            self._local_state.state = "closed"
            self._local_state.failure_count = 0
            self._local_state.success_count = 0
            self._local_state.half_open_call_count = 0
            self._local_state.opened_at = None
        self._local_breaker.force_close()
        self._persist_state()
        logger.info("DistCircuit '%s': Forced CLOSED", self._name)

    # ----------------------------------------------------------
    #  STATE SYNC
    # ----------------------------------------------------------

    def _maybe_sync(self) -> None:
        """
        Sync local state from backend if the sync interval has elapsed.

        Handles the OPEN -> HALF_OPEN transition based on recovery_timeout.
        """
        now = time.time()
        if now - self._last_sync < self._sync_interval:
            return

        with self._lock:
            if now - self._last_sync < self._sync_interval:
                return  # Another thread synced while we waited
            self._last_sync = now

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                remote_state = loop.run_until_complete(
                    self._backend.get_circuit_state(self._name)
                )
            finally:
                loop.close()

            if remote_state is not None:
                version = remote_state.pop("version", 0)
                with self._lock:
                    # Only update if remote is newer
                    if version >= self._local_state.version:
                        self._local_state = SharedCircuitState.from_dict(
                            remote_state, version=version,
                        )

                        # Check OPEN -> HALF_OPEN transition
                        if self._local_state.state == "open":
                            if self._local_state.opened_at is not None:
                                elapsed = time.monotonic() - self._local_state.opened_at
                                if elapsed >= self._recovery_timeout:
                                    self._local_state.state = "half_open"
                                    self._local_state.failure_count = 0
                                    self._local_state.success_count = 0
                                    self._local_state.half_open_call_count = 0
                                    logger.info(
                                        "DistCircuit '%s': OPEN -> HALF_OPEN "
                                        "(recovery timeout elapsed)",
                                        self._name,
                                    )

                self._total_syncs += 1

        except Exception as exc:
            self._sync_errors += 1
            logger.debug(
                "DistCircuit '%s': Sync failed, using local state: %s",
                self._name, exc,
            )

    def _persist_state(self) -> None:
        """Persist current local state to the backend."""
        with self._lock:
            state_dict = self._local_state.to_dict()
            version = self._local_state.version

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    self._backend.update_circuit_state(
                        self._name,
                        state_dict,
                        expected_version=version if version > 0 else None,
                    )
                )
            finally:
                loop.close()
        except Exception as exc:
            logger.debug(
                "DistCircuit '%s': Persist failed: %s", self._name, exc,
            )

    def __repr__(self) -> str:
        return (
            f"DistributedCircuitBreaker(name={self._name!r}, "
            f"state={self._local_state.state!r}, "
            f"version={self._local_state.version})"
        )
