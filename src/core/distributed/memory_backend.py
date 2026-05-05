"""
TITAN OMNISCALE X - In-Memory Coordination Backend

Single-process in-memory implementation of CoordinationBackend.
Used for:
    - Development and testing without external dependencies
    - Graceful degradation when PostgreSQL is unavailable
    - Single-node deployments (Android/Termux with 500MB RAM)

Thread-safe: all operations are protected by threading.Lock.
No external dependencies beyond Python stdlib.
"""

import copy
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .backend import BackendConfig, CoordinationBackend

logger = logging.getLogger(__name__)

__all__ = ["MemoryBackend"]


class MemoryBackend(CoordinationBackend):
    """
    In-memory coordination backend for single-process deployments.

    All state is held in Python dicts protected by a threading.Lock.
    This backend provides the same API as PgBackend but without
    persistence or cross-process coordination.

    Suitable for:
        - Development and testing
        - Single-node deployments on resource-constrained devices
        - Fallback when PostgreSQL is unavailable

    Not suitable for:
        - Multi-node deployments
        - Persistent task queues
        - Production distributed coordination
    """

    def __init__(self, config: BackendConfig) -> None:
        super().__init__(config)
        self._lock = threading.Lock()

        # Task queues: queue_name -> list of task dicts
        self._tasks: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        # task_id -> task dict (index for fast lookup)
        self._task_index: Dict[str, Dict[str, Any]] = {}

        # Distributed locks: lock_name -> {holder_id, expires_at}
        self._locks: Dict[str, Dict[str, Any]] = {}

        # Leader election: election_name -> {leader_id, expires_at}
        self._elections: Dict[str, Dict[str, Any]] = {}

        # Circuit breaker state: circuit_name -> {state, version, ...}
        self._circuits: Dict[str, Dict[str, Any]] = {}

        # Saga state: saga_id -> {name, status, steps, context, ...}
        self._sagas: Dict[str, Dict[str, Any]] = {}

        # Node topology: node_id -> node_info
        self._nodes: Dict[str, Dict[str, Any]] = {}

    # ----------------------------------------------------------
    #  LIFECYCLE
    # ----------------------------------------------------------

    async def connect(self) -> None:
        """Initialize in-memory data structures."""
        self._connected = True
        logger.info("MemoryBackend: Connected (node_id=%s)", self._node_id)

    async def disconnect(self) -> None:
        """Clear all state and disconnect."""
        with self._lock:
            self._tasks.clear()
            self._task_index.clear()
            self._locks.clear()
            self._elections.clear()
            self._circuits.clear()
            self._sagas.clear()
            self._nodes.clear()
        self._connected = False
        logger.info("MemoryBackend: Disconnected")

    async def health_check(self) -> Dict[str, Any]:
        """Check backend health (always healthy for in-memory)."""
        start = time.monotonic()
        with self._lock:
            _ = len(self._tasks)  # Simple operation to measure latency
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "healthy": True,
            "backend_type": "memory",
            "latency_ms": latency_ms,
            "node_id": self._node_id,
            "tasks": len(self._task_index),
            "locks": len(self._locks),
            "nodes": len(self._nodes),
        }

    # ----------------------------------------------------------
    #  TASK QUEUE
    # ----------------------------------------------------------

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
        with self._lock:
            if task_id in self._task_index:
                logger.warning("MemoryBackend: Task %s already exists", task_id)
                return False

            task = {
                "task_id": task_id,
                "queue_name": queue_name,
                "task_type": task_type,
                "payload": payload,
                "priority": priority,
                "delay_until": delay_until,
                "tenant_id": tenant_id,
                "status": "pending",
                "worker_id": None,
                "lease_expires_at": None,
                "created_at": time.time(),
                "completed_at": None,
                "result": None,
                "error": None,
                "retry_count": 0,
                "max_retries": 3,
            }
            self._tasks[queue_name].append(task)
            self._task_index[task_id] = task
            logger.debug(
                "MemoryBackend: Enqueued task %s in queue '%s'",
                task_id[:8], queue_name,
            )
            return True

    async def dequeue_task(
        self,
        queue_name: str,
        worker_id: str,
        lease_seconds: float = 120.0,
        task_types: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            # Find highest-priority available task
            available = []
            for task in self._tasks.get(queue_name, []):
                if task["status"] != "pending":
                    continue
                if task["delay_until"] and task["delay_until"] > now:
                    continue
                if task_types and task["task_type"] not in task_types:
                    continue
                if tenant_id and task.get("tenant_id") != tenant_id:
                    continue
                available.append(task)

            if not available:
                return None

            # Sort by priority (higher first), then by created_at (earlier first)
            available.sort(key=lambda t: (-t["priority"], t["created_at"]))
            task = available[0]

            # Claim it
            task["status"] = "running"
            task["worker_id"] = worker_id
            task["lease_expires_at"] = now + lease_seconds

            return copy.deepcopy(task)

    async def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None:
                return False
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["result"] = result
            task["lease_expires_at"] = None
            return True

    async def fail_task(self, task_id: str, error: str, retryable: bool = True) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None:
                return False

            if retryable and task["retry_count"] < task["max_retries"]:
                task["status"] = "pending"
                task["retry_count"] += 1
                task["worker_id"] = None
                task["lease_expires_at"] = None
                task["error"] = error
                logger.info(
                    "MemoryBackend: Task %s failed (retry %d/%d): %s",
                    task_id[:8], task["retry_count"], task["max_retries"], error,
                )
            else:
                task["status"] = "failed"
                task["completed_at"] = time.time()
                task["error"] = error
                task["lease_expires_at"] = None
                logger.warning(
                    "MemoryBackend: Task %s permanently failed: %s",
                    task_id[:8], error,
                )
            return True

    async def renew_lease(self, task_id: str, additional_seconds: float = 60.0) -> bool:
        with self._lock:
            task = self._task_index.get(task_id)
            if task is None or task["status"] != "running":
                return False
            task["lease_expires_at"] = time.time() + additional_seconds
            return True

    async def expire_leases(self, queue_name: str) -> int:
        now = time.time()
        expired_count = 0
        with self._lock:
            for task in self._tasks.get(queue_name, []):
                if (
                    task["status"] == "running"
                    and task["lease_expires_at"]
                    and task["lease_expires_at"] < now
                ):
                    task["status"] = "pending"
                    task["worker_id"] = None
                    task["lease_expires_at"] = None
                    expired_count += 1
                    logger.info(
                        "MemoryBackend: Expired lease for task %s",
                        task["task_id"][:8],
                    )
        return expired_count

    # ----------------------------------------------------------
    #  DISTRIBUTED LOCKS
    # ----------------------------------------------------------

    async def acquire_lock(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 0.0,
    ) -> bool:
        deadline = time.time() + timeout_seconds
        while True:
            with self._lock:
                lock = self._locks.get(lock_name)
                now = time.time()

                if lock is None or lock["expires_at"] < now:
                    # Lock is free or expired
                    self._locks[lock_name] = {
                        "holder_id": holder_id,
                        "expires_at": now + ttl_seconds,
                        "acquired_at": now,
                    }
                    return True

                if lock["holder_id"] == holder_id:
                    # Already held by us — extend
                    lock["expires_at"] = now + ttl_seconds
                    return True

            if now >= deadline:
                return False

            # Brief sleep before retry
            time.sleep(min(0.1, deadline - now))

    async def release_lock(self, lock_name: str, holder_id: str) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None:
                return False
            if lock["holder_id"] != holder_id:
                return False
            del self._locks[lock_name]
            return True

    async def extend_lock(self, lock_name: str, holder_id: str, additional_seconds: float = 30.0) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None or lock["holder_id"] != holder_id:
                return False
            lock["expires_at"] = time.time() + additional_seconds
            return True

    async def is_locked(self, lock_name: str) -> bool:
        with self._lock:
            lock = self._locks.get(lock_name)
            if lock is None:
                return False
            if lock["expires_at"] < time.time():
                del self._locks[lock_name]
                return False
            return True

    # ----------------------------------------------------------
    #  LEADER ELECTION
    # ----------------------------------------------------------

    async def campaign(self, election_name: str, candidate_id: str, ttl_seconds: float = 30.0) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            now = time.time()

            if election is None or election["expires_at"] < now:
                self._elections[election_name] = {
                    "leader_id": candidate_id,
                    "expires_at": now + ttl_seconds,
                    "acquired_at": now,
                }
                return True

            if election["leader_id"] == candidate_id:
                # Renew our own leadership
                election["expires_at"] = now + ttl_seconds
                return True

            return False

    async def abdicate(self, election_name: str, leader_id: str) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None or election["leader_id"] != leader_id:
                return False
            del self._elections[election_name]
            return True

    async def get_leader(self, election_name: str) -> Optional[str]:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None:
                return None
            if election["expires_at"] < time.time():
                del self._elections[election_name]
                return None
            return election["leader_id"]

    async def renew_leadership(self, election_name: str, leader_id: str, ttl_seconds: float = 30.0) -> bool:
        with self._lock:
            election = self._elections.get(election_name)
            if election is None or election["leader_id"] != leader_id:
                return False
            election["expires_at"] = time.time() + ttl_seconds
            return True

    # ----------------------------------------------------------
    #  CIRCUIT BREAKER STATE
    # ----------------------------------------------------------

    async def get_circuit_state(self, circuit_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._circuits.get(circuit_name))

    async def update_circuit_state(
        self,
        circuit_name: str,
        state: Dict[str, Any],
        expected_version: Optional[int] = None,
    ) -> bool:
        with self._lock:
            current = self._circuits.get(circuit_name)
            if current is not None and expected_version is not None:
                if current.get("version", 0) != expected_version:
                    return False
            state_copy = copy.deepcopy(state)
            state_copy["version"] = (current.get("version", 0) + 1) if current else 1
            state_copy["updated_at"] = time.time()
            self._circuits[circuit_name] = state_copy
            return True

    # ----------------------------------------------------------
    #  SAGA STATE
    # ----------------------------------------------------------

    async def create_saga(
        self,
        saga_id: str,
        name: str,
        steps: List[Dict[str, Any]],
        initial_context: Dict[str, Any],
    ) -> bool:
        with self._lock:
            if saga_id in self._sagas:
                return False
            self._sagas[saga_id] = {
                "saga_id": saga_id,
                "name": name,
                "status": "PENDING",
                "steps": steps,
                "context": copy.deepcopy(initial_context),
                "created_at": time.time(),
                "updated_at": time.time(),
                "error": None,
            }
            return True

    async def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            saga = self._sagas.get(saga_id)
            return copy.deepcopy(saga) if saga else None

    async def update_saga_step(
        self,
        saga_id: str,
        step_name: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return False
            for step in saga["steps"]:
                if step["name"] == step_name:
                    step["status"] = status
                    step["result"] = result
                    step["error"] = error
                    step["updated_at"] = time.time()
                    break
            saga["updated_at"] = time.time()
            return True

    async def update_saga_status(
        self,
        saga_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            saga = self._sagas.get(saga_id)
            if saga is None:
                return False
            saga["status"] = status
            saga["error"] = error
            saga["updated_at"] = time.time()
            return True

    # ----------------------------------------------------------
    #  NODE TOPOLOGY
    # ----------------------------------------------------------

    async def register_node(self, node_info: Dict[str, Any]) -> bool:
        with self._lock:
            node_id = node_info.get("node_id", "")
            self._nodes[node_id] = {
                **copy.deepcopy(node_info),
                "registered_at": time.time(),
                "last_heartbeat": time.time(),
            }
            return True

    async def heartbeat(self, node_id: str, status: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            node["last_heartbeat"] = time.time()
            if status:
                node["status"] = copy.deepcopy(status)
            return True

    async def deregister_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                return True
            return False

    async def list_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            result = []
            for node in self._nodes.values():
                if active_only:
                    # Consider active if heartbeat within 3x heartbeat_interval
                    hb_interval = self._config.heartbeat_interval
                    if now - node.get("last_heartbeat", 0) > hb_interval * 3:
                        continue
                result.append(copy.deepcopy(node))
            return result
