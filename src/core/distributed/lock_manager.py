"""
TITAN OMNISCALE X - Distributed Lock Manager

Cross-node distributed locking using the CoordinationBackend.
Ensures mutual exclusion across multiple processes and nodes.

Features:
    - Named locks with configurable TTL
    - Blocking and non-blocking acquisition
    - Lock extension for long-running operations
    - Context manager protocol for automatic release
    - Deadlock prevention via TTL expiration
    - Re-entrant lock support (same holder can re-acquire)

Use Cases:
    - Exclusive database migrations
    - Singleton task execution (only one node runs)
    - Rate-limited resource access
    - Distributed file writes
    - Configuration change coordination
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from .backend import CoordinationBackend

logger = logging.getLogger(__name__)

__all__ = [
    "DistributedLockManager",
    "DistributedLock",
]


# ============================================================
#  DISTRIBUTED LOCK (Context Manager)
# ============================================================

class DistributedLock:
    """
    Distributed lock instance returned by DistributedLockManager.acquire().

    Supports the context manager protocol for automatic release::

        async with lock_manager.acquire_context("my_lock") as lock:
            # Critical section
            do_exclusive_work()
        # Lock automatically released

    Attributes:
        lock_name: Name of the lock.
        holder_id: ID of the lock holder.
        ttl_seconds: Lock time-to-live.
        acquired: Whether the lock is currently held.
    """

    def __init__(
        self,
        lock_name: str,
        holder_id: str,
        ttl_seconds: float,
        backend: CoordinationBackend,
    ) -> None:
        self._lock_name = lock_name
        self._holder_id = holder_id
        self._ttl_seconds = ttl_seconds
        self._backend = backend
        self._acquired = False
        self._extension_thread: Optional[threading.Thread] = None
        self._stop_extension = threading.Event()

    @property
    def lock_name(self) -> str:
        """Name of the lock."""
        return self._lock_name

    @property
    def holder_id(self) -> str:
        """ID of the lock holder."""
        return self._holder_id

    @property
    def ttl_seconds(self) -> float:
        """Lock TTL in seconds."""
        return self._ttl_seconds

    @property
    def acquired(self) -> bool:
        """Whether the lock is currently held."""
        return self._acquired

    # ----------------------------------------------------------
    #  CONTEXT MANAGER (sync)
    # ----------------------------------------------------------

    def __enter__(self) -> "DistributedLock":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release_sync()

    # ----------------------------------------------------------
    #  RELEASE
    # ----------------------------------------------------------

    async def release(self) -> bool:
        """
        Release the lock asynchronously.

        Returns:
            True if the lock was released.
        """
        if not self._acquired:
            return False

        self._stop_extension.set()
        success = await self._backend.release_lock(
            self._lock_name, self._holder_id,
        )

        if success:
            self._acquired = False
            logger.debug(
                "DistributedLock: Released '%s' (holder=%s)",
                self._lock_name, self._holder_id,
            )
        return success

    def release_sync(self) -> bool:
        """Synchronous release wrapper."""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.release())
            finally:
                loop.close()
        except Exception as exc:
            logger.error(
                "DistributedLock: Release error for '%s': %s",
                self._lock_name, exc,
            )
            return False

    # ----------------------------------------------------------
    #  EXTENSION
    # ----------------------------------------------------------

    async def extend(self, additional_seconds: float = 30.0) -> bool:
        """
        Extend the lock's TTL.

        Args:
            additional_seconds: Extra time to add.

        Returns:
            True if the lock was extended.
        """
        if not self._acquired:
            return False
        return await self._backend.extend_lock(
            self._lock_name, self._holder_id, additional_seconds,
        )

    def start_auto_extension(self, interval_seconds: float = 10.0) -> None:
        """
        Start a background thread that automatically extends the lock.

        Args:
            interval_seconds: How often to extend.
        """
        if self._extension_thread and self._extension_thread.is_alive():
            return

        self._stop_extension.clear()
        self._extension_thread = threading.Thread(
            target=self._auto_extend_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._extension_thread.start()

    def _auto_extend_loop(self, interval: float) -> None:
        """Background loop that extends the lock TTL."""
        while not self._stop_extension.is_set():
            if self._acquired:
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(
                            self.extend(self._ttl_seconds * 0.5)
                        )
                    finally:
                        loop.close()
                except Exception as exc:
                    logger.warning(
                        "DistributedLock: Auto-extend failed for '%s': %s",
                        self._lock_name, exc,
                    )
            self._stop_extension.wait(timeout=interval)


# ============================================================
#  DISTRIBUTED LOCK MANAGER
# ============================================================

class DistributedLockManager:
    """
    Manager for distributed locks across multiple nodes.

    Provides a simple interface for acquiring, releasing, and
    managing named distributed locks backed by the CoordinationBackend.

    Usage::

        lock_mgr = DistributedLockManager(
            backend=backend,
            default_ttl=60.0,
        )

        # Non-blocking acquire
        lock = await lock_mgr.acquire("migration_lock")
        if lock:
            try:
                run_migration()
            finally:
                await lock.release()

        # Blocking acquire with timeout
        lock = await lock_mgr.acquire(
            "migration_lock",
            timeout_seconds=30.0,
        )

        # Context manager (sync)
        with lock_mgr.acquire_sync("migration_lock"):
            run_migration()
    """

    def __init__(
        self,
        backend: CoordinationBackend,
        holder_id: Optional[str] = None,
        default_ttl: float = 60.0,
    ) -> None:
        """
        Initialize the lock manager.

        Args:
            backend: Coordination backend for lock state.
            holder_id: Default holder ID (auto-generated if empty).
            default_ttl: Default lock TTL in seconds.
        """
        self._backend = backend
        self._holder_id = holder_id or f"holder-{uuid.uuid4().hex[:8]}"
        self._default_ttl = default_ttl

        # Track held locks for cleanup
        self._held_locks: Dict[str, DistributedLock] = {}
        self._lock = threading.Lock()

    @property
    def holder_id(self) -> str:
        """Default holder ID."""
        return self._holder_id

    # ----------------------------------------------------------
    #  ACQUIRE
    # ----------------------------------------------------------

    async def acquire(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
        holder_id: Optional[str] = None,
    ) -> Optional[DistributedLock]:
        """
        Acquire a distributed lock.

        Args:
            lock_name: Name of the lock to acquire.
            ttl_seconds: Lock TTL (default from config).
            timeout_seconds: How long to wait (0 = no wait).
            holder_id: Override holder ID.

        Returns:
            DistributedLock if acquired, None if not.
        """
        ttl = ttl_seconds or self._default_ttl
        holder = holder_id or self._holder_id

        success = await self._backend.acquire_lock(
            lock_name=lock_name,
            holder_id=holder,
            ttl_seconds=ttl,
            timeout_seconds=timeout_seconds,
        )

        if not success:
            return None

        lock = DistributedLock(
            lock_name=lock_name,
            holder_id=holder,
            ttl_seconds=ttl,
            backend=self._backend,
        )
        lock._acquired = True

        with self._lock:
            self._held_locks[lock_name] = lock

        logger.debug(
            "LockManager: Acquired '%s' (holder=%s, ttl=%.0fs)",
            lock_name, holder, ttl,
        )
        return lock

    def acquire_sync(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
    ) -> Optional[DistributedLock]:
        """Synchronous acquire wrapper."""
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.acquire(lock_name, ttl_seconds, timeout_seconds)
            )
        finally:
            loop.close()

    # ----------------------------------------------------------
    #  ACQUIRE CONTEXT (ASYNC)
    # ----------------------------------------------------------

    class _AsyncLockContext:
        """Async context manager for distributed locks."""

        def __init__(self, lock: Optional[DistributedLock]) -> None:
            self._lock = lock

        async def __aenter__(self) -> Optional[DistributedLock]:
            return self._lock

        async def __aexit__(self, *args: Any) -> None:
            if self._lock and self._lock.acquired:
                await self._lock.release()

    async def acquire_context(
        self,
        lock_name: str,
        ttl_seconds: Optional[float] = None,
        timeout_seconds: float = 0.0,
    ) -> "_AsyncLockContext":
        """
        Acquire a lock as an async context manager.

        Usage::

            async with lock_mgr.acquire_context("my_lock") as lock:
                if lock:
                    do_exclusive_work()
        """
        lock = await self.acquire(lock_name, ttl_seconds, timeout_seconds)
        return self._AsyncLockContext(lock)

    # ----------------------------------------------------------
    #  QUERY
    # ----------------------------------------------------------

    async def is_locked(self, lock_name: str) -> bool:
        """Check if a lock is currently held."""
        return await self._backend.is_locked(lock_name)

    # ----------------------------------------------------------
    #  CLEANUP
    # ----------------------------------------------------------

    async def release_all(self) -> int:
        """
        Release all locks held by this manager.

        Returns:
            Number of locks released.
        """
        released = 0
        with self._lock:
            for lock_name, lock in list(self._held_locks.items()):
                if lock.acquired:
                    success = await lock.release()
                    if success:
                        released += 1
            self._held_locks.clear()
        return released

    @property
    def stats(self) -> Dict[str, Any]:
        """Lock manager statistics."""
        with self._lock:
            return {
                "holder_id": self._holder_id,
                "default_ttl": self._default_ttl,
                "held_locks": len(self._held_locks),
                "lock_names": list(self._held_locks.keys()),
            }
