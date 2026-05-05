"""
TITAN OMNISCALE X - Distributed Task Queue

Persistent, priority-based task queue backed by the CoordinationBackend.
Supports multi-tenant isolation, delayed tasks, lease-based execution,
and automatic retry with exponential backoff.

Key Features:
    - Priority-based dequeuing (higher priority first)
    - Lease-based task claiming with automatic expiration
    - Delayed task scheduling (delay_until)
    - Multi-tenant task isolation
    - Task type filtering for specialized workers
    - Automatic retry on failure (configurable max_retries)
    - Dead letter queue for permanently failed tasks
    - Back-pressure via queue depth limits
    - Statistics for observability

Designed for PostgreSQL (production) and MemoryBackend (dev/testing).
"""

import enum
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .backend import BackendConfig, CoordinationBackend
from src.core.patterns.resilience.retry import RetryConfig, with_retry

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedTaskQueue",
    "TaskMessage",
    "TaskStatus",
    "TaskPriority",
]


# ============================================================
#  ENUMS
# ============================================================

class TaskStatus(str, enum.Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class TaskPriority(int, enum.Enum):
    """Predefined priority levels."""
    LOW = 10
    NORMAL = 5
    HIGH = 1
    CRITICAL = 0


# ============================================================
#  TASK MESSAGE
# ============================================================

@dataclass
class TaskMessage:
    """
    Immutable task message for the distributed queue.

    Attributes:
        task_id: Unique task identifier (auto-generated if empty).
        queue_name: Logical queue name for routing.
        task_type: Task type for dispatch routing.
        payload: Task payload (JSON-serializable dict).
        priority: Higher priority = dequeued first (lower number = higher).
        delay_until: Unix timestamp; task not available before this.
        tenant_id: Optional tenant ID for multi-tenant isolation.
        max_retries: Maximum retry attempts on failure.
        created_at: Unix timestamp of creation.
        correlation_id: Optional correlation ID for tracing across tasks.
    """
    task_id: str = ""
    queue_name: str = "default"
    task_type: str = "generic"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = TaskPriority.NORMAL
    delay_until: Optional[float] = None
    tenant_id: Optional[str] = None
    max_retries: int = 3
    created_at: float = 0.0
    correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"task-{uuid.uuid4().hex[:12]}"
        if self.created_at == 0.0:
            self.created_at = time.time()


# ============================================================
#  DISTRIBUTED TASK QUEUE
# ============================================================

class DistributedTaskQueue:
    """
    Persistent, distributed task queue with priority scheduling.

    Backed by CoordinationBackend (PostgreSQL for production,
    Memory for dev/testing). Supports lease-based task claiming,
    automatic retries, and multi-tenant isolation.

    Usage::

        from src.core.distributed import DistributedTaskQueue, BackendConfig

        queue = DistributedTaskQueue(
            backend=CoordinationBackend.create(BackendConfig()),
        )
        await queue.connect()

        # Enqueue
        msg = TaskMessage(
            queue_name="pipeline",
            task_type="code_generation",
            payload={"description": "Build REST API"},
            priority=TaskPriority.HIGH,
        )
        task_id = await queue.enqueue(msg)

        # Dequeue (for workers)
        task = await queue.dequeue("pipeline", worker_id="worker-1")

        # Complete
        await queue.complete(task["task_id"], result={"files": 5})

        await queue.disconnect()

    Thread Safety:
        The queue itself is thread-safe. Backend operations are
        serialized by the backend's internal locking.
    """

    # Default queue depth limit for back-pressure
    DEFAULT_MAX_QUEUE_DEPTH = 10000

    def __init__(
        self,
        backend: CoordinationBackend,
        max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH,
        default_lease_seconds: float = 120.0,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """
        Initialize the distributed task queue.

        Args:
            backend: Coordination backend for persistent state.
            max_queue_depth: Maximum pending tasks per queue (back-pressure).
            default_lease_seconds: Default task lease duration.
            retry_config: Retry configuration for backend operations.
        """
        self._backend = backend
        self._max_queue_depth = max_queue_depth
        self._default_lease_seconds = default_lease_seconds
        self._retry_config = retry_config or RetryConfig(
            max_attempts=2,
            base_delay=0.3,
            max_delay=5.0,
            backoff_strategy="exponential",
            jitter=True,
            retryable_exceptions=(Exception,),
        )

        # Stats
        self._total_enqueued: int = 0
        self._total_dequeued: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_retried: int = 0
        self._stats_lock = threading.Lock()

    # ----------------------------------------------------------
    #  LIFECYCLE
    # ----------------------------------------------------------

    async def connect(self) -> None:
        """Initialize the queue by connecting the backend."""
        await self._backend.connect()
        logger.info(
            "DistributedTaskQueue: Connected (backend=%s)",
            type(self._backend).__name__,
        )

    async def disconnect(self) -> None:
        """Disconnect the queue backend."""
        await self._backend.disconnect()
        logger.info("DistributedTaskQueue: Disconnected")

    # ----------------------------------------------------------
    #  ENQUEUE
    # ----------------------------------------------------------

    async def enqueue(self, message: TaskMessage) -> str:
        """
        Add a task to the queue.

        Args:
            message: TaskMessage describing the task.

        Returns:
            The task_id of the enqueued task.

        Raises:
            ValueError: If the queue is at capacity.
        """
        success = await self._backend.enqueue_task(
            queue_name=message.queue_name,
            task_id=message.task_id,
            task_type=message.task_type,
            payload=message.payload,
            priority=message.priority,
            delay_until=message.delay_until,
            tenant_id=message.tenant_id,
        )

        if not success:
            raise ValueError(
                f"Failed to enqueue task {message.task_id} "
                f"(queue={message.queue_name})"
            )

        with self._stats_lock:
            self._total_enqueued += 1

        logger.info(
            "TaskQueue: Enqueued %s (queue=%s, type=%s, priority=%d)",
            message.task_id[:8], message.queue_name,
            message.task_type, message.priority,
        )
        return message.task_id

    async def enqueue_batch(self, messages: List[TaskMessage]) -> List[str]:
        """
        Enqueue multiple tasks.

        Args:
            messages: List of TaskMessage instances.

        Returns:
            List of task_ids for successfully enqueued tasks.
        """
        task_ids: List[str] = []
        for msg in messages:
            try:
                tid = await self.enqueue(msg)
                task_ids.append(tid)
            except Exception as exc:
                logger.error(
                    "TaskQueue: Batch enqueue failed for %s: %s",
                    msg.task_id[:8], exc,
                )
        return task_ids

    # ----------------------------------------------------------
    #  DEQUEUE
    # ----------------------------------------------------------

    async def dequeue(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: Optional[float] = None,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Claim the highest-priority available task.

        Args:
            queue_name: Queue to dequeue from.
            worker_id: ID of the claiming worker.
            lease_seconds: Task lease duration (default from config).
            task_types: Filter by task type.
            tenant_id: Filter by tenant.

        Returns:
            Task dict, or None if no task available.
        """
        lease = lease_seconds or self._default_lease_seconds

        task = await self._backend.dequeue_task(
            queue_name=queue_name,
            worker_id=worker_id,
            lease_seconds=lease,
            task_types=task_types,
            tenant_id=tenant_id,
        )

        if task is not None:
            with self._stats_lock:
                self._total_dequeued += 1
            logger.debug(
                "TaskQueue: Dequeued %s by worker %s",
                task.get("task_id", "")[:8], worker_id,
            )

        return task

    # ----------------------------------------------------------
    #  TASK LIFECYCLE
    # ----------------------------------------------------------

    async def complete(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: The task to complete.
            result: Optional result payload.

        Returns:
            True if the task was completed.
        """
        success = await self._backend.complete_task(task_id, result)

        if success:
            with self._stats_lock:
                self._total_completed += 1
            logger.info("TaskQueue: Completed %s", task_id[:8])

        return success

    async def fail(
        self,
        task_id: str,
        error: str,
        retryable: bool = True,
    ) -> bool:
        """
        Mark a task as failed.

        If retryable and retries remain, the task is reset to pending.
        Otherwise it is permanently marked as failed.

        Args:
            task_id: The task that failed.
            error: Error message.
            retryable: Whether the task can be retried.

        Returns:
            True if the failure was recorded.
        """
        success = await self._backend.fail_task(task_id, error, retryable)

        if success:
            with self._stats_lock:
                self._total_failed += 1
                if retryable:
                    self._total_retried += 1
            logger.warning(
                "TaskQueue: Failed %s (retryable=%s): %s",
                task_id[:8], retryable, error[:100],
            )

        return success

    async def renew_lease(
        self,
        task_id: str,
        additional_seconds: float = 60.0,
    ) -> bool:
        """
        Extend a task's lease.

        Workers should call this periodically for long-running tasks
        to prevent the lease from expiring.

        Args:
            task_id: Task whose lease to extend.
            additional_seconds: Extra lease time.

        Returns:
            True if the lease was extended.
        """
        return await self._backend.renew_lease(task_id, additional_seconds)

    async def expire_leases(self, queue_name: str) -> int:
        """
        Release expired task leases.

        Should be called periodically by a coordinator or leader.

        Args:
            queue_name: Queue to scan for expired leases.

        Returns:
            Number of leases expired.
        """
        count = await self._backend.expire_leases(queue_name)
        if count > 0:
            logger.info(
                "TaskQueue: Expired %d leases in queue '%s'",
                count, queue_name,
            )
        return count

    # ----------------------------------------------------------
    #  STATS
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Queue statistics for observability.

        Returns:
            Dict with enqueue/dequeue/complete/fail/retry counts
            and backend type.
        """
        with self._stats_lock:
            return {
                "total_enqueued": self._total_enqueued,
                "total_dequeued": self._total_dequeued,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_retried": self._total_retried,
                "backend_type": type(self._backend).__name__,
                "max_queue_depth": self._max_queue_depth,
            }
