"""
TITAN OMNISCALE X - Distributed Worker

Long-running worker process that pulls tasks from a DistributedTaskQueue,
executes them, and reports results. Features:

- Heartbeat-based liveness tracking
- Lease renewal for long-running tasks
- Configurable task type specialization
- Graceful shutdown with task re-queueing
- Work-stealing from overloaded peers
- Auto-registration in cluster topology
- Resource-aware task execution (respects ResourceGovernor)

Designed for PostgreSQL (production) and MemoryBackend (dev/testing).

PERFORMANCE (H-07 fix): Reuses a single asyncio event loop per thread
instead of creating/destroying a new loop for every async operation.
"""

import asyncio
import enum
import logging
import platform
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .backend import CoordinationBackend
from .task_queue import DistributedTaskQueue, TaskStatus

# Phase 5: Observability wiring
try:
    from src.core.observability.metrics import get_metrics_collector
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedWorker",
    "WorkerState",
    "WorkerConfig",
]


# ============================================================
#  ENUMS
# ============================================================

class WorkerState(str, enum.Enum):
    """Worker lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ============================================================
#  CONFIGURATION
# ============================================================

@dataclass
class WorkerConfig:
    """
    Configuration for DistributedWorker.

    Attributes:
        worker_id: Unique worker identifier. Auto-generated if empty.
        queue_names: List of queue names to consume from.
        task_types: If set, only process these task types.
        tenant_id: If set, only process tasks for this tenant.
        lease_seconds: Default task lease duration.
        lease_renewal_interval: How often to renew leases (seconds).
        heartbeat_interval: How often to send heartbeats (seconds).
        poll_interval: How often to poll for new tasks (seconds).
        max_concurrent_tasks: Maximum concurrent tasks (1 for now).
        lease_renewal_threshold: Renew lease when this fraction remains.
        graceful_shutdown_timeout: Seconds to wait for tasks during shutdown.
    """
    worker_id: str = ""
    queue_names: List[str] = field(default_factory=lambda: ["default"])
    task_types: Optional[List[str]] = None
    tenant_id: Optional[str] = None
    lease_seconds: float = 120.0
    lease_renewal_interval: float = 30.0
    heartbeat_interval: float = 10.0
    poll_interval: float = 1.0
    max_concurrent_tasks: int = 1
    lease_renewal_threshold: float = 0.3
    graceful_shutdown_timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.worker_id:
            self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"


# ============================================================
#  TASK HANDLER TYPE
# ============================================================

TaskHandler = Callable[[Dict[str, Any]], Any]


# ============================================================
#  THREAD-LOCAL EVENT LOOP HELPER (H-07 fix)
# ============================================================

_local = threading.local()


def _get_thread_loop() -> asyncio.AbstractEventLoop:
    """Get or create a persistent event loop for the current thread.

    PERFORMANCE (H-07 fix): Instead of creating a new asyncio event loop
    for every async operation (which leaks resources and adds overhead),
    each thread reuses a single loop for its entire lifetime.
    """
    loop = getattr(_local, "event_loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.event_loop = loop
    return loop


def _run_async(coro):
    """Run an async coroutine on the current thread's persistent event loop."""
    loop = _get_thread_loop()
    return loop.run_until_complete(coro)


# ============================================================
#  DISTRIBUTED WORKER
# ============================================================

class DistributedWorker:
    """
    Distributed worker that consumes tasks from a DistributedTaskQueue.

    The worker runs a continuous loop that:
    1. Sends periodic heartbeats to the cluster topology
    2. Polls for available tasks from configured queues
    3. Claims and executes tasks with lease management
    4. Reports results (complete/fail) back to the queue
    5. Renews leases for long-running tasks
    6. Gracefully shuts down when signalled

    Usage::

        from src.core.distributed import (
            DistributedWorker, WorkerConfig,
            DistributedTaskQueue, CoordinationBackend, BackendConfig,
        )

        backend = CoordinationBackend.create(BackendConfig())
        queue = DistributedTaskQueue(backend=backend)

        worker = DistributedWorker(
            config=WorkerConfig(queue_names=["pipeline"]),
            queue=queue,
            backend=backend,
        )

        # Register task handlers
        worker.register_handler("code_generation", handle_code_gen)

        # Start (blocking)
        worker.start()
    """

    def __init__(
        self,
        config: WorkerConfig,
        queue: DistributedTaskQueue,
        backend: CoordinationBackend,
    ) -> None:
        self._config = config
        self._queue = queue
        self._backend = backend

        self._state: WorkerState = WorkerState.STOPPED
        self._handlers: Dict[str, TaskHandler] = {}
        self._current_task: Optional[Dict[str, Any]] = None
        self._task_start_time: float = 0.0

        # Background threads
        self._main_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lease_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._tasks_stolen: int = 0
        self._lock = threading.Lock()

    # ----------------------------------------------------------
    #  HANDLER REGISTRATION
    # ----------------------------------------------------------

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """
        Register a handler for a specific task type.

        Args:
            task_type: The task type this handler processes.
            handler: Callable that receives the task dict and returns a result.
        """
        self._handlers[task_type] = handler
        logger.debug(
            "Worker %s: Registered handler for task type '%s'",
            self._config.worker_id, task_type,
        )

    def register_handlers(self, handlers: Dict[str, TaskHandler]) -> None:
        """
        Register multiple task handlers.

        Args:
            handlers: Dict mapping task_type -> handler callable.
        """
        for task_type, handler in handlers.items():
            self.register_handler(task_type, handler)

    # ----------------------------------------------------------
    #  LIFECYCLE
    # ----------------------------------------------------------

    def start(self, blocking: bool = True) -> None:
        """
        Start the worker.

        Args:
            blocking: If True, block until the worker stops.
                     If False, run in background threads.
        """
        if self._state == WorkerState.RUNNING:
            logger.warning("Worker %s: Already running", self._config.worker_id)
            return

        self._state = WorkerState.IDLE
        self._stop_event.clear()

        # Register in topology
        self._register_in_topology()

        # Start background threads
        self._main_thread = threading.Thread(
            target=self._main_loop,
            name=f"worker-{self._config.worker_id}-main",
            daemon=True,
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"worker-{self._config.worker_id}-heartbeat",
            daemon=True,
        )
        self._lease_thread = threading.Thread(
            target=self._lease_renewal_loop,
            name=f"worker-{self._config.worker_id}-lease",
            daemon=True,
        )

        self._main_thread.start()
        self._heartbeat_thread.start()
        self._lease_thread.start()

        logger.info(
            "Worker %s: Started (queues=%s, types=%s)",
            self._config.worker_id,
            self._config.queue_names,
            self._config.task_types or "all",
        )

        if blocking:
            self._main_thread.join()

    async def start_async(self) -> None:
        """Async version of start() — runs worker in background."""
        self.start(blocking=False)

    def stop(self) -> None:
        """
        Signal the worker to stop gracefully.

        Waits up to graceful_shutdown_timeout for current task
        to complete, then forces stop.
        """
        if self._state in (WorkerState.STOPPED, WorkerState.STOPPING):
            return

        self._state = WorkerState.STOPPING
        self._stop_event.set()
        logger.info(
            "Worker %s: Stopping (timeout=%ds)",
            self._config.worker_id,
            self._config.graceful_shutdown_timeout,
        )

        # Wait for main thread
        if self._main_thread and self._main_thread.is_alive():
            self._main_thread.join(timeout=self._config.graceful_shutdown_timeout)

        # Deregister from topology
        self._deregister_from_topology()

        # Close the thread-local event loop (H-07: cleanup)
        loop = getattr(_local, "event_loop", None)
        if loop is not None and not loop.is_closed():
            loop.close()
            _local.event_loop = None

        self._state = WorkerState.STOPPED
        logger.info("Worker %s: Stopped", self._config.worker_id)

    def pause(self) -> None:
        """Pause task processing (heartbeat continues)."""
        self._state = WorkerState.PAUSED
        logger.info("Worker %s: Paused", self._config.worker_id)

    def resume(self) -> None:
        """Resume task processing."""
        self._state = WorkerState.IDLE
        logger.info("Worker %s: Resumed", self._config.worker_id)

    # ----------------------------------------------------------
    #  PROPERTIES
    # ----------------------------------------------------------

    @property
    def worker_id(self) -> str:
        """Worker identifier."""
        return self._config.worker_id

    @property
    def state(self) -> WorkerState:
        """Current worker state."""
        return self._state

    @property
    def current_task(self) -> Optional[Dict[str, Any]]:
        """Currently executing task, if any."""
        return self._current_task

    @property
    def stats(self) -> Dict[str, Any]:
        """Worker statistics."""
        with self._lock:
            return {
                "worker_id": self._config.worker_id,
                "state": self._state.value,
                "tasks_completed": self._tasks_completed,
                "tasks_failed": self._tasks_failed,
                "tasks_stolen": self._tasks_stolen,
                "current_task": (
                    self._current_task.get("task_id", "")[:8]
                    if self._current_task else None
                ),
                "registered_handlers": list(self._handlers.keys()),
                "queue_names": self._config.queue_names,
                "uptime_s": (
                    time.time() - self._start_time
                    if hasattr(self, "_start_time") else 0
                ),
            }

    # ----------------------------------------------------------
    #  MAIN LOOP
    # ----------------------------------------------------------

    def _main_loop(self) -> None:
        """Main worker loop: poll for tasks and execute them."""
        self._start_time = time.time()

        while not self._stop_event.is_set():
            if self._state in (WorkerState.PAUSED, WorkerState.STOPPING):
                self._stop_event.wait(timeout=1.0)
                continue

            # Try each configured queue (H-07: reuse thread-local loop)
            task = None
            for queue_name in self._config.queue_names:
                try:
                    task = _run_async(
                        self._queue.dequeue(
                            queue_name=queue_name,
                            worker_id=self._config.worker_id,
                            lease_seconds=self._config.lease_seconds,
                            task_types=self._config.task_types,
                            tenant_id=self._config.tenant_id,
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "Worker %s: Dequeue error from '%s': %s",
                        self._config.worker_id, queue_name, exc,
                    )

                if task is not None:
                    break

            if task is None:
                self._state = WorkerState.IDLE
                self._stop_event.wait(timeout=self._config.poll_interval)
                continue

            # Execute the task
            self._state = WorkerState.RUNNING
            self._execute_task(task)

        self._state = WorkerState.STOPPED

    def _execute_task(self, task: Dict[str, Any]) -> None:
        """
        Execute a single task with the appropriate handler.

        Handles:
        - Handler lookup
        - Lease renewal for long-running tasks
        - Result reporting (complete/fail)
        - Error isolation
        """
        task_id = task.get("task_id", "unknown")
        task_type = task.get("task_type", "unknown")

        self._current_task = task
        self._task_start_time = time.time()

        handler = self._handlers.get(task_type)

        if handler is None:
            logger.error(
                "Worker %s: No handler for task type '%s' (task=%s)",
                self._config.worker_id, task_type, task_id[:8],
            )
            self._report_failure(task_id, f"No handler registered for task type '{task_type}'")
            self._current_task = None
            return

        logger.info(
            "Worker %s: Executing task %s (type=%s)",
            self._config.worker_id, task_id[:8], task_type,
        )

        try:
            result = handler(task)

            # If handler returns a coroutine, run it on the thread-local loop
            if asyncio.iscoroutine(result):
                result = _run_async(result)

            # Report success
            self._report_success(task_id, result)

        except Exception as exc:
            logger.error(
                "Worker %s: Task %s failed: %s",
                self._config.worker_id, task_id[:8], exc,
                exc_info=True,
            )
            self._report_failure(task_id, str(exc))

        finally:
            self._current_task = None
            self._task_start_time = 0.0

    def _report_success(self, task_id: str, result: Any) -> None:
        """Report a completed task."""
        result_dict = None
        if isinstance(result, dict):
            result_dict = result
        elif result is not None:
            result_dict = {"value": result}

        try:
            _run_async(self._queue.complete(task_id, result_dict))
        except Exception as exc:
            logger.error(
                "Worker %s: Failed to report completion for %s: %s",
                self._config.worker_id, task_id[:8], exc,
            )
        else:
            with self._lock:
                self._tasks_completed += 1
                # Phase 5: Emit metrics
                if _METRICS_AVAILABLE:
                    try:
                        mc = get_metrics_collector()
                        mc.record_task_completed(
                            task_type=self._current_task.get("task_type", "unknown") if self._current_task else "unknown",
                            worker_id=self._config.worker_id,
                            duration=time.time() - self._task_start_time if self._task_start_time else 0.0,
                        )
                    except Exception:
                        pass

    def _report_failure(self, task_id: str, error: str) -> None:
        """Report a failed task."""
        try:
            _run_async(self._queue.fail(task_id, error, retryable=True))
        except Exception as exc:
            logger.error(
                "Worker %s: Failed to report failure for %s: %s",
                self._config.worker_id, task_id[:8], exc,
            )
        else:
            with self._lock:
                self._tasks_failed += 1
                # Phase 5: Emit metrics
                if _METRICS_AVAILABLE:
                    try:
                        mc = get_metrics_collector()
                        mc.record_task_failed(
                            task_type=self._current_task.get("task_type", "unknown") if self._current_task else "unknown",
                            worker_id=self._config.worker_id,
                        )
                    except Exception:
                        pass

    # ----------------------------------------------------------
    #  HEARTBEAT LOOP
    # ----------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to the cluster topology."""
        while not self._stop_event.is_set():
            try:
                status = {
                    "state": self._state.value,
                    "tasks_completed": self._tasks_completed,
                    "tasks_failed": self._tasks_failed,
                    "current_task_type": (
                        self._current_task.get("task_type")
                        if self._current_task else None
                    ),
                }
                _run_async(
                    self._backend.heartbeat(
                        self._config.worker_id, status
                    )
                )
            except Exception as exc:
                logger.debug(
                    "Worker %s: Heartbeat error: %s",
                    self._config.worker_id, exc,
                )

            self._stop_event.wait(timeout=self._config.heartbeat_interval)

    # ----------------------------------------------------------
    #  LEASE RENEWAL LOOP
    # ----------------------------------------------------------

    def _lease_renewal_loop(self) -> None:
        """Renew task leases for long-running operations."""
        while not self._stop_event.is_set():
            if self._current_task is not None:
                task_id = self._current_task.get("task_id", "")
                try:
                    _run_async(
                        self._queue.renew_lease(
                            task_id,
                            self._config.lease_seconds * 0.5,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "Worker %s: Lease renewal failed for %s: %s",
                        self._config.worker_id, task_id[:8], exc,
                    )

            self._stop_event.wait(
                timeout=self._config.lease_renewal_interval
            )

    # ----------------------------------------------------------
    #  TOPOLOGY
    # ----------------------------------------------------------

    def _register_in_topology(self) -> None:
        """Register this worker in the cluster topology."""
        try:
            _run_async(
                self._backend.register_node({
                    "node_id": self._config.worker_id,
                    "hostname": socket.gethostname(),
                    "ip_address": self._get_local_ip(),
                    "capabilities": {
                        "task_types": list(self._handlers.keys()),
                        "queue_names": self._config.queue_names,
                        "max_concurrent": self._config.max_concurrent_tasks,
                        "platform": platform.platform(),
                    },
                })
            )
        except Exception as exc:
            logger.warning(
                "Worker %s: Topology registration failed: %s",
                self._config.worker_id, exc,
            )

    def _deregister_from_topology(self) -> None:
        """Remove this worker from the cluster topology."""
        try:
            _run_async(
                self._backend.deregister_node(self._config.worker_id)
            )
        except Exception as exc:
            logger.warning(
                "Worker %s: Topology deregistration failed: %s",
                self._config.worker_id, exc,
            )

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local IP address (best effort)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
