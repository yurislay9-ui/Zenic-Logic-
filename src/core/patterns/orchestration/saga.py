"""
TITAN OMNISCALE X - Saga Pattern (Multi-Step Rollback)

Formal SAGA pattern implementation for distributed multi-step operations
with automatic compensation on failure.

When a step fails, all previously completed steps are compensated in
reverse order. This is critical for the TITAN pipeline where operations
like AST surgery, code generation, and file writes must be rolled back
if a downstream step fails.

Features:
- Sequential step execution with automatic compensation on failure
- Reverse-order compensation for completed steps
- Per-step timeout support
- Shared context for inter-step communication
- Sync and async execution
- Thread-safe
- Detailed logging at each step/compensation boundary
- Status tracking (PENDING -> RUNNING -> COMPLETED/COMPENSATING/FAILED)

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import asyncio
import enum
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "SagaStatus",
    "SagaStep",
    "SagaContext",
    "Saga",
]


# ============================================================
#  SAGA STATUS
# ============================================================

class SagaStatus(str, enum.Enum):
    """
    Lifecycle states of a Saga execution.

    State transitions:
        PENDING -> RUNNING -> COMPLETED
                          |-> COMPENSATING -> COMPENSATED
                                            |-> FAILED
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"


# ============================================================
#  SAGA STEP
# ============================================================

@dataclass
class SagaStep:
    """
    A single step in a Saga with optional compensation.

    Attributes:
        name: Human-readable step name for logging.
        action: Callable that executes the step. Receives SagaContext
                as its only argument. May return a value that is
                stored in context.results[name].
        compensation: Optional callable to undo the step's effects.
                     Receives SagaContext as its only argument.
                     Called in reverse order if a subsequent step fails.
        timeout: Optional timeout in seconds. If the step (action or
                compensation) exceeds this duration, it is considered
                failed.
    """
    name: str
    action: Callable[[Any], Any]
    compensation: Optional[Callable[[Any], Any]] = None
    timeout: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SagaStep name must not be empty")
        if self.action is None:
            raise ValueError("SagaStep action must not be None")


# ============================================================
#  SAGA CONTEXT
# ============================================================

class SagaContext:
    """
    Shared mutable context passed through all saga steps.

    Provides a dict-like interface for inter-step communication,
    plus dedicated storage for step results and accumulated errors.

    Attributes:
        saga_id: Unique identifier for the saga execution.
        results: Dict mapping step names to their return values.
        errors: List of error messages accumulated during execution.

    Usage::

        ctx = SagaContext(saga_id="order-123", steps=[...])
        ctx.set("user_id", 42)
        user_id = ctx.get("user_id")  # 42
        ctx.has("user_id")  # True
    """

    def __init__(self, saga_id: str, steps: Optional[List[SagaStep]] = None) -> None:
        if not saga_id:
            raise ValueError("saga_id must not be empty")

        self.saga_id: str = saga_id
        self._state: Dict[str, Any] = {}
        self.results: Dict[str, Any] = {}
        self.errors: List[str] = []
        self._steps: List[SagaStep] = steps or []
        self._completed_steps: List[SagaStep] = []

    def set(self, key: str, value: Any) -> None:
        """
        Store a value in the shared context.

        Args:
            key: Context key.
            value: Value to store.
        """
        self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the shared context.

        Args:
            key: Context key.
            default: Value to return if key is not found.

        Returns:
            The stored value, or default if not found.
        """
        return self._state.get(key, default)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the shared context.

        Args:
            key: Context key to check.

        Returns:
            True if the key exists.
        """
        return key in self._state

    @property
    def state(self) -> Dict[str, Any]:
        """Read-only snapshot of the current context state."""
        return dict(self._state)

    def mark_step_completed(self, step: SagaStep) -> None:
        """
        Record that a step has completed successfully.

        Completed steps are tracked for compensation in reverse order.

        Args:
            step: The completed SagaStep.
        """
        self._completed_steps.append(step)

    @property
    def completed_steps(self) -> List[SagaStep]:
        """
        Steps that completed successfully, in execution order.

        During compensation, these are reversed.
        """
        return list(self._completed_steps)

    def add_error(self, error: str) -> None:
        """
        Append an error message to the accumulated errors list.

        Args:
            error: Error message string.
        """
        self.errors.append(error)


# ============================================================
#  SAGA
# ============================================================

class Saga:
    """
    Orchestrator for multi-step operations with automatic rollback.

    Executes steps sequentially. If any step fails (raises an exception
    or exceeds its timeout), all previously completed steps are
    compensated in reverse order.

    Usage::

        saga = Saga(
            name="create_order",
            steps=[
                SagaStep(
                    name="reserve_inventory",
                    action=lambda ctx: reserve(ctx),
                    compensation=lambda ctx: release(ctx),
                ),
                SagaStep(
                    name="charge_payment",
                    action=lambda ctx: charge(ctx),
                    compensation=lambda ctx: refund(ctx),
                ),
                SagaStep(
                    name="ship_order",
                    action=lambda ctx: ship(ctx),
                ),
            ],
        )

        context = saga.execute()
        if saga.status == SagaStatus.COMPLETED:
            print("All steps succeeded!")
        else:
            print("Saga failed, compensations executed")

    Thread Safety:
        A single Saga instance should not be executed concurrently.
        Create separate Saga instances for concurrent executions.
    """

    def __init__(self, name: str, steps: List[SagaStep]) -> None:
        """
        Initialize the Saga.

        Args:
            name: Human-readable saga name for logging.
            steps: Ordered list of SagaStep instances.

        Raises:
            ValueError: If name is empty or steps is empty.
        """
        if not name:
            raise ValueError("Saga name must not be empty")
        if not steps:
            raise ValueError("Saga must have at least one step")

        self._name: str = name
        self._steps: List[SagaStep] = list(steps)
        self._status: SagaStatus = SagaStatus.PENDING
        self._lock = threading.Lock()
        self._saga_id: str = str(uuid.uuid4())

        # Stats
        self._execution_count: int = 0
        self._compensation_count: int = 0
        self._error_count: int = 0
        self._last_execution_time_ms: float = 0.0

    # ----------------------------------------------------------
    #  PROPERTIES
    # ----------------------------------------------------------

    @property
    def status(self) -> SagaStatus:
        """Current lifecycle status of the saga."""
        return self._status

    @property
    def name(self) -> str:
        """Human-readable saga name."""
        return self._name

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with:
            - name: Saga name
            - saga_id: Unique execution ID
            - status: Current SagaStatus
            - step_count: Total number of steps
            - execution_count: Number of times execute was called
            - compensation_count: Number of compensations performed
            - error_count: Number of errors encountered
            - last_execution_time_ms: Duration of last execution
        """
        with self._lock:
            return {
                "name": self._name,
                "saga_id": self._saga_id,
                "status": self._status.value,
                "step_count": len(self._steps),
                "execution_count": self._execution_count,
                "compensation_count": self._compensation_count,
                "error_count": self._error_count,
                "last_execution_time_ms": self._last_execution_time_ms,
            }

    # ----------------------------------------------------------
    #  SYNC EXECUTION
    # ----------------------------------------------------------

    def execute(self, context: Optional[SagaContext] = None) -> SagaContext:
        """
        Execute all saga steps sequentially with automatic compensation.

        If any step fails (raises or times out), all previously completed
        steps are compensated in REVERSE order. The saga status transitions
        through: PENDING -> RUNNING -> COMPLETED (or COMPENSATING ->
        COMPENSATED/FAILED).

        Args:
            context: Optional pre-populated SagaContext. If None,
                     a new one is created with a generated saga_id.

        Returns:
            The SagaContext with results, errors, and state after
            execution (and possible compensation).
        """
        start_time = time.time()

        # Initialize context if not provided
        if context is None:
            context = SagaContext(saga_id=self._saga_id, steps=self._steps)

        with self._lock:
            self._execution_count += 1
            self._status = SagaStatus.RUNNING

        logger.info(
            "Saga[%s]: Starting execution (saga_id=%s, steps=%d)",
            self._name, context.saga_id[:8], len(self._steps),
        )

        try:
            for step in self._steps:
                self._execute_step(step, context)

            # All steps succeeded
            with self._lock:
                self._status = SagaStatus.COMPLETED
                self._last_execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                "Saga[%s]: Completed successfully (saga_id=%s, "
                "steps=%d, time=%.1fms)",
                self._name, context.saga_id[:8], len(self._steps),
                self._last_execution_time_ms,
            )

        except Exception as exc:
            logger.error(
                "Saga[%s]: Step failed (saga_id=%s): %s",
                self._name, context.saga_id[:8], exc,
            )
            context.add_error(str(exc))

            with self._lock:
                self._error_count += 1
                self._status = SagaStatus.COMPENSATING

            # Compensate completed steps in reverse order
            self._compensate(context)

        return context

    # ----------------------------------------------------------
    #  ASYNC EXECUTION
    # ----------------------------------------------------------

    async def execute_async(
        self, context: Optional[SagaContext] = None
    ) -> SagaContext:
        """
        Asynchronously execute all saga steps with automatic compensation.

        Same semantics as execute() but supports async step actions.
        Sync actions are automatically wrapped.

        Args:
            context: Optional pre-populated SagaContext.

        Returns:
            The SagaContext with results, errors, and state.
        """
        start_time = time.time()

        if context is None:
            context = SagaContext(saga_id=self._saga_id, steps=self._steps)

        with self._lock:
            self._execution_count += 1
            self._status = SagaStatus.RUNNING

        logger.info(
            "Saga[%s][async]: Starting execution (saga_id=%s, steps=%d)",
            self._name, context.saga_id[:8], len(self._steps),
        )

        try:
            for step in self._steps:
                await self._execute_step_async(step, context)

            with self._lock:
                self._status = SagaStatus.COMPLETED
                self._last_execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                "Saga[%s][async]: Completed successfully (saga_id=%s, "
                "time=%.1fms)",
                self._name, context.saga_id[:8],
                self._last_execution_time_ms,
            )

        except Exception as exc:
            logger.error(
                "Saga[%s][async]: Step failed (saga_id=%s): %s",
                self._name, context.saga_id[:8], exc,
            )
            context.add_error(str(exc))

            with self._lock:
                self._error_count += 1
                self._status = SagaStatus.COMPENSATING

            await self._compensate_async(context)

        return context

    # ----------------------------------------------------------
    #  STEP EXECUTION (SYNC)
    # ----------------------------------------------------------

    def _execute_step(self, step: SagaStep, context: SagaContext) -> None:
        """
        Execute a single saga step with optional timeout.

        Args:
            step: The SagaStep to execute.
            context: The shared SagaContext.

        Raises:
            Exception: If the step action raises or times out.
        """
        logger.info(
            "Saga[%s]: Executing step '%s' (timeout=%s)",
            self._name, step.name,
            f"{step.timeout}s" if step.timeout else "none",
        )

        if step.timeout is not None:
            self._execute_step_with_timeout(step, context)
        else:
            result = step.action(context)
            context.results[step.name] = result
            context.mark_step_completed(step)

        logger.info(
            "Saga[%s]: Step '%s' completed successfully",
            self._name, step.name,
        )

    def _execute_step_with_timeout(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Execute a step with timeout enforcement.

        Uses a threading-based timeout mechanism since the step action
        may not be async-aware.

        Args:
            step: The SagaStep with timeout set.
            context: The shared SagaContext.

        Raises:
            TimeoutError: If the step exceeds its timeout.
        """
        result_holder: Dict[str, Any] = {"result": None, "error": None}

        def _target() -> None:
            try:
                result_holder["result"] = step.action(context)
            except Exception as exc:
                result_holder["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=step.timeout)

        if worker.is_alive():
            # Thread is still running; it timed out
            raise TimeoutError(
                f"Saga step '{step.name}' exceeded timeout of "
                f"{step.timeout}s"
            )

        if result_holder["error"] is not None:
            raise result_holder["error"]

        context.results[step.name] = result_holder["result"]
        context.mark_step_completed(step)

    # ----------------------------------------------------------
    #  STEP EXECUTION (ASYNC)
    # ----------------------------------------------------------

    async def _execute_step_async(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Asynchronously execute a single saga step with optional timeout.

        Args:
            step: The SagaStep to execute.
            context: The shared SagaContext.

        Raises:
            Exception: If the step action raises or times out.
        """
        logger.info(
            "Saga[%s][async]: Executing step '%s'",
            self._name, step.name,
        )

        try:
            if step.timeout is not None:
                result = await asyncio.wait_for(
                    self._call_action_async(step.action, context),
                    timeout=step.timeout,
                )
            else:
                result = await self._call_action_async(step.action, context)

            context.results[step.name] = result
            context.mark_step_completed(step)

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Saga step '{step.name}' exceeded timeout of "
                f"{step.timeout}s"
            )

        logger.info(
            "Saga[%s][async]: Step '%s' completed successfully",
            self._name, step.name,
        )

    async def _call_action_async(
        self, action: Callable[[Any], Any], context: SagaContext
    ) -> Any:
        """
        Call an action, handling both sync and async callables.

        Args:
            action: The step action callable.
            context: The shared SagaContext.

        Returns:
            The result of the action.
        """
        result = action(context)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    # ----------------------------------------------------------
    #  COMPENSATION (SYNC)
    # ----------------------------------------------------------

    def _compensate(self, context: SagaContext) -> None:
        """
        Run compensations for all completed steps in REVERSE order.

        Compensation failures are logged but do not stop the
        compensation process — all completed steps will have their
        compensations attempted.

        Args:
            context: The SagaContext with completed steps.
        """
        completed = context.completed_steps
        if not completed:
            logger.info(
                "Saga[%s]: No steps to compensate", self._name,
            )
            with self._lock:
                self._status = SagaStatus.FAILED
            return

        logger.info(
            "Saga[%s]: Compensating %d steps in reverse order",
            self._name, len(completed),
        )

        compensation_errors: List[str] = []

        # Reverse order compensation
        for step in reversed(completed):
            if step.compensation is not None:
                logger.info(
                    "Saga[%s]: Compensating step '%s'",
                    self._name, step.name,
                )
                try:
                    if step.timeout is not None:
                        self._compensate_step_with_timeout(step, context)
                    else:
                        step.compensation(context)

                    with self._lock:
                        self._compensation_count += 1

                    logger.info(
                        "Saga[%s]: Step '%s' compensated successfully",
                        self._name, step.name,
                    )
                except Exception as exc:
                    error_msg = (
                        f"Compensation failed for step '{step.name}': {exc}"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1
                    logger.error(
                        "Saga[%s]: %s", self._name, error_msg,
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "Saga[%s]: Step '%s' has no compensation defined",
                    self._name, step.name,
                )

        # Determine final status
        with self._lock:
            if compensation_errors:
                self._status = SagaStatus.FAILED
            else:
                self._status = SagaStatus.COMPENSATED

        final_status = self._status
        logger.info(
            "Saga[%s]: Compensation complete (status=%s, errors=%d)",
            self._name, final_status.value, len(compensation_errors),
        )

    def _compensate_step_with_timeout(
        self, step: SagaStep, context: SagaContext
    ) -> None:
        """
        Run a step's compensation with timeout enforcement.

        Args:
            step: The SagaStep with compensation and timeout.
            context: The shared SagaContext.

        Raises:
            TimeoutError: If compensation exceeds timeout.
        """
        if step.compensation is None:
            return

        error_holder: Dict[str, Any] = {"error": None}

        def _target() -> None:
            try:
                step.compensation(context)  # type: ignore[misc]
            except Exception as exc:
                error_holder["error"] = exc

        worker = threading.Thread(target=_target, daemon=True)
        worker.start()
        worker.join(timeout=step.timeout)

        if worker.is_alive():
            raise TimeoutError(
                f"Compensation for step '{step.name}' exceeded timeout "
                f"of {step.timeout}s"
            )

        if error_holder["error"] is not None:
            raise error_holder["error"]

    # ----------------------------------------------------------
    #  COMPENSATION (ASYNC)
    # ----------------------------------------------------------

    async def _compensate_async(self, context: SagaContext) -> None:
        """
        Asynchronously run compensations for all completed steps.

        Same semantics as _compensate() but supports async compensation
        callables.

        Args:
            context: The SagaContext with completed steps.
        """
        completed = context.completed_steps
        if not completed:
            with self._lock:
                self._status = SagaStatus.FAILED
            return

        logger.info(
            "Saga[%s][async]: Compensating %d steps in reverse order",
            self._name, len(completed),
        )

        compensation_errors: List[str] = []

        for step in reversed(completed):
            if step.compensation is not None:
                logger.info(
                    "Saga[%s][async]: Compensating step '%s'",
                    self._name, step.name,
                )
                try:
                    if step.timeout is not None:
                        await asyncio.wait_for(
                            self._call_action_async(
                                step.compensation, context
                            ),
                            timeout=step.timeout,
                        )
                    else:
                        await self._call_action_async(
                            step.compensation, context
                        )

                    with self._lock:
                        self._compensation_count += 1

                except asyncio.TimeoutError:
                    error_msg = (
                        f"Compensation timeout for step '{step.name}'"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1

                except Exception as exc:
                    error_msg = (
                        f"Compensation failed for step '{step.name}': {exc}"
                    )
                    compensation_errors.append(error_msg)
                    context.add_error(error_msg)
                    with self._lock:
                        self._error_count += 1
                    logger.error(
                        "Saga[%s][async]: %s", self._name, error_msg,
                    )
            else:
                logger.warning(
                    "Saga[%s][async]: Step '%s' has no compensation",
                    self._name, step.name,
                )

        with self._lock:
            if compensation_errors:
                self._status = SagaStatus.FAILED
            else:
                self._status = SagaStatus.COMPENSATED

        logger.info(
            "Saga[%s][async]: Compensation complete (status=%s)",
            self._name, self._status.value,
        )
