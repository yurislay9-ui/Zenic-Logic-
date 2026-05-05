"""
TITAN OMNISCALE X - Coordination Backend (Abstract + Factory)

Abstract interface for distributed coordination backends and factory
method for creating the appropriate backend based on configuration.

Supports:
    - PostgreSQL: Production backend using pg_advisory_locks, SKIP LOCKED,
      and transactional coordination. Works with the existing docker-compose
      PostgreSQL service.
    - Memory: Single-process in-memory backend for development, testing,
      and graceful degradation when no DB is available.

The factory method CoordinationBackend.create(config) returns the correct
concrete backend, handling import errors gracefully.

All backend operations are protected by retry patterns from the existing
resilience layer (src.core.patterns.resilience.retry).
"""

import enum
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.patterns.resilience.retry import RetryConfig, with_retry

logger = logging.getLogger(__name__)

__all__ = [
    "CoordinationBackend",
    "BackendConfig",
    "BackendType",
]


# ============================================================
#  ENUMS
# ============================================================

class BackendType(str, enum.Enum):
    """Supported coordination backend types."""
    POSTGRESQL = "postgresql"
    MEMORY = "memory"


# ============================================================
#  CONFIGURATION
# ============================================================

@dataclass
class BackendConfig:
    """
    Configuration for the coordination backend.

    Attributes:
        backend_type: Which backend to use (postgresql or memory).
        connection_string: Database connection string (for PostgreSQL).
        pool_min: Minimum connection pool size.
        pool_max: Maximum connection pool size.
        connect_timeout: Connection timeout in seconds.
        statement_timeout: SQL statement timeout in milliseconds.
        heartbeat_interval: How often heartbeats are sent (seconds).
        lease_duration: Default task lease duration (seconds).
        node_id: Unique identifier for this node. Auto-generated if empty.
        retry_config: Retry configuration for backend operations.
    """
    backend_type: BackendType = BackendType.MEMORY
    connection_string: str = ""
    pool_min: int = 2
    pool_max: int = 10
    connect_timeout: float = 5.0
    statement_timeout: int = 5000
    heartbeat_interval: float = 10.0
    lease_duration: float = 120.0
    node_id: str = ""
    retry_config: RetryConfig = field(default_factory=lambda: RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        backoff_strategy="exponential",
        jitter=True,
        retryable_exceptions=(Exception,),
    ))

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{uuid.uuid4().hex[:8]}"


# ============================================================
#  ABSTRACT BACKEND
# ============================================================

class CoordinationBackend(ABC):
    """
    Abstract coordination backend for distributed state management.

    All methods are async to support both PostgreSQL and in-memory
    backends uniformly. The backend manages:

    - Task queue operations (enqueue, dequeue, complete, fail)
    - Distributed locking (acquire, release, extend)
    - Leader election (campaign, abdicate, check)
    - Circuit breaker state (get, set, compare-and-swap)
    - Saga state (create, update, list steps)
    - Node topology (register, heartbeat, deregister, list)
    """

    def __init__(self, config: BackendConfig) -> None:
        self._config = config
        self._node_id = config.node_id
        self._connected = False

    @property
    def node_id(self) -> str:
        """Unique identifier for this node."""
        return self._node_id

    @property
    def config(self) -> BackendConfig:
        """Backend configuration."""
        return self._config

    @property
    def is_connected(self) -> bool:
        """Whether the backend is currently connected."""
        return self._connected

    # ----------------------------------------------------------
    #  FACTORY
    # ----------------------------------------------------------

    @staticmethod
    def create(config: BackendConfig) -> "CoordinationBackend":
        """
        Factory method: create the appropriate backend from config.

        Falls back to MemoryBackend if PostgreSQL is requested but
        dependencies are unavailable.

        Args:
            config: Backend configuration.

        Returns:
            A concrete CoordinationBackend instance.
        """
        if config.backend_type == BackendType.POSTGRESQL:
            try:
                from .pg_backend import PgBackend
                backend = PgBackend(config)
                logger.info(
                    "CoordinationBackend: Created PostgreSQL backend "
                    "(node_id=%s)", config.node_id,
                )
                return backend
            except ImportError as exc:
                logger.warning(
                    "CoordinationBackend: PostgreSQL dependencies not "
                    "available (%s), falling back to MemoryBackend", exc,
                )
            except Exception as exc:
                logger.warning(
                    "CoordinationBackend: PostgreSQL backend creation "
                    "failed (%s), falling back to MemoryBackend", exc,
                )

        # Memory backend (explicit or fallback)
        from .memory_backend import MemoryBackend
        logger.info(
            "CoordinationBackend: Created Memory backend "
            "(node_id=%s)", config.node_id,
        )
        return MemoryBackend(config)

    # ----------------------------------------------------------
    #  LIFECYCLE
    # ----------------------------------------------------------

    @abstractmethod
    async def connect(self) -> None:
        """
        Initialize the backend connection.

        For PostgreSQL: establishes connection pool and creates
        coordination tables if they don't exist.

        For Memory: initializes in-memory data structures.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the backend connection and release resources."""

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Check backend health.

        Returns:
            Dict with at minimum:
            - healthy: bool
            - backend_type: str
            - latency_ms: float (round-trip time for a simple operation)
        """

    # ----------------------------------------------------------
    #  TASK QUEUE OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def enqueue_task(
        self,
        queue_name: str,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        delay_until: Optional[float] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        Add a task to the named queue.

        Args:
            queue_name: Logical queue name (e.g., "pipeline", "generation").
            task_id: Unique task identifier.
            task_type: Task type for dispatch routing.
            payload: Task payload (JSON-serializable dict).
            priority: Higher priority = dequeued first (default 0).
            delay_until: Unix timestamp; task not available before this time.
            tenant_id: Optional tenant for multi-tenant isolation.

        Returns:
            True if the task was enqueued successfully.
        """

    @abstractmethod
    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the highest-priority available task from the queue.

        Uses SELECT ... FOR UPDATE SKIP LOCKED (PostgreSQL) or equivalent
        to ensure exactly-once task assignment.

        Args:
            queue_name: Logical queue to dequeue from.
            worker_id: ID of the worker claiming the task.
            lease_seconds: How long the lease lasts before the task
                           becomes available again.
            task_types: If set, only dequeue tasks matching these types.
            tenant_id: If set, only dequeue tasks for this tenant.

        Returns:
            Dict with task details, or None if no task is available.
        """

    @abstractmethod
    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: The task to complete.
            result: Optional result payload.

        Returns:
            True if the task was found and completed.
        """

    @abstractmethod
    async def fail_task(
        self,
        task_id: str,
        error: str,
        retryable: bool = True,
    ) -> bool:
        """
        Mark a task as failed.

        Args:
            task_id: The task that failed.
            error: Error message.
            retryable: If True, the task may be re-attempted.

        Returns:
            True if the task was found and marked as failed.
        """

    @abstractmethod
    async def renew_lease(self, task_id: str, additional_seconds: float = 60.0) -> bool:
        """
        Extend the lease on a currently-leased task.

        Args:
            task_id: The task whose lease to extend.
            additional_seconds: How much more time to add.

        Returns:
            True if the lease was extended successfully.
        """

    @abstractmethod
    async def expire_leases(self, queue_name: str) -> int:
        """
        Find and release expired task leases, making them available again.

        Should be called periodically by a coordinator or leader.

        Args:
            queue_name: The queue to scan for expired leases.

        Returns:
            Number of leases that were expired.
        """

    # ----------------------------------------------------------
    #  DISTRIBUTED LOCK OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def acquire_lock(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 0.0,
    ) -> bool:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock.
            holder_id: ID of the lock holder (usually node_id).
            ttl_seconds: Lock time-to-live before automatic release.
            timeout_seconds: How long to wait for the lock (0 = no wait).

        Returns:
            True if the lock was acquired.
        """

    @abstractmethod
    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        """
        Release a distributed lock.

        Args:
            lock_name: Name of the lock.
            holder_id: Must match the current holder.

        Returns:
            True if the lock was released (holder matched).
        """

    @abstractmethod
    async def extend_lock(self, lock_name: str, holder_id: str, additional_seconds: float = 30.0) -> bool:
        """
        Extend a held lock's TTL.

        Args:
            lock_name: Name of the lock.
            holder_id: Must match the current holder.
            additional_seconds: Extra time to add.

        Returns:
            True if the lock was extended.
        """

    @abstractmethod
    async def is_locked(self, lock_name: str) -> bool:
        """
        Check if a lock is currently held.

        Args:
            lock_name: Name of the lock.

        Returns:
            True if the lock is currently held by someone.
        """

    # ----------------------------------------------------------
    #  LEADER ELECTION OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def campaign(self, election_name: str, candidate_id: str, ttl_seconds: float = 30.0) -> bool:
        """
        Attempt to become leader for the given election.

        Args:
            election_name: Name of the leadership position.
            candidate_id: ID of the candidate (usually node_id).
            ttl_seconds: Leadership duration before re-campaign needed.

        Returns:
            True if leadership was acquired.
        """

    @abstractmethod
    async def abdicate(self, election_name: str, leader_id: str) -> bool:
        """
        Voluntarily step down as leader.

        Args:
            election_name: Name of the leadership position.
            leader_id: Must match the current leader.

        Returns:
            True if leadership was relinquished.
        """

    @abstractmethod
    async def get_leader(self, election_name: str) -> Optional[str]:
        """
        Get the current leader for an election.

        Args:
            election_name: Name of the leadership position.

        Returns:
            Leader ID, or None if no leader.
        """

    @abstractmethod
    async def renew_leadership(self, election_name: str, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        """
        Renew leadership before it expires.

        Args:
            election_name: Name of the leadership position.
            leader_id: Must match the current leader.
            ttl_seconds: New TTL from now.

        Returns:
            True if leadership was renewed.
        """

    # ----------------------------------------------------------
    #  CIRCUIT BREAKER STATE OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def get_circuit_state(self, circuit_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the shared state of a circuit breaker.

        Args:
            circuit_name: Name of the circuit breaker.

        Returns:
            Dict with circuit state, or None if not found.
        """

    @abstractmethod
    async def update_circuit_state(
        self,
        circuit_name: str,
        state: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> bool:
        """
        Update circuit breaker state with optimistic concurrency.

        Args:
            circuit_name: Name of the circuit breaker.
            state: New state to write.
            expected_version: If set, update only if current version matches.

        Returns:
            True if the update succeeded (version matched if specified).
        """

    # ----------------------------------------------------------
    #  SAGA STATE OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def create_saga(
        self,
        saga_id: str,
        name: str,
        steps: List[Dict[str, Any]],
        initial_context: Dict[str, Any],
    ) -> bool:
        """
        Persist a new saga with its steps and initial context.

        Args:
            saga_id: Unique saga identifier.
            name: Human-readable saga name.
            steps: List of step definitions (each with name, action_type,
                   compensation_type, timeout).
            initial_context: Initial context data.

        Returns:
            True if the saga was created.
        """

    @abstractmethod
    async def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        """
        Get saga state by ID.

        Args:
            saga_id: Unique saga identifier.

        Returns:
            Dict with saga state, or None if not found.
        """

    @abstractmethod
    async def update_saga_step(
        self,
        saga_id: str,
        step_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update the status of a specific saga step.

        Args:
            saga_id: Unique saga identifier.
            step_name: Step to update.
            status: New step status (PENDING/RUNNING/COMPLETED/COMPENSATING/COMPENSATED/FAILED).
            result: Optional step result payload.
            error: Optional error message.

        Returns:
            True if the step was updated.
        """

    @abstractmethod
    async def update_saga_status(
        self,
        saga_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update the overall saga status.

        Args:
            saga_id: Unique saga identifier.
            status: New saga status.
            error: Optional error message.

        Returns:
            True if the saga was updated.
        """

    # ----------------------------------------------------------
    #  NODE TOPOLOGY OPERATIONS
    # ----------------------------------------------------------

    @abstractmethod
    async def register_node(self, node_info: Dict[str, Any]) -> bool:
        """
        Register this node in the cluster topology.

        Args:
            node_info: Node registration data (id, hostname, capabilities, etc.).

        Returns:
            True if registration succeeded.
        """

    @abstractmethod
    async def heartbeat(self, node_id: str, status: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send a heartbeat for this node.

        Args:
            node_id: Node ID sending the heartbeat.
            status: Optional current status data (load, queue depth, etc.).

        Returns:
            True if the heartbeat was recorded.
        """

    @abstractmethod
    async def deregister_node(self, node_id: str) -> bool:
        """
        Remove a node from the cluster topology.

        Args:
            node_id: Node to remove.

        Returns:
            True if the node was found and removed.
        """

    @abstractmethod
    async def list_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        List nodes in the cluster.

        Args:
            active_only: If True, only return nodes with recent heartbeats.

        Returns:
            List of node info dicts.
        """
