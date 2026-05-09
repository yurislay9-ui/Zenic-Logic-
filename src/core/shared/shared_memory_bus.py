"""
ZENIC LOGIC — Shared Memory Bus for Ultra-Fast Inter-Agent Communication.

This module implements the core inter-agent communication layer that replaces
slow Python dict passing with a zero-copy shared memory architecture backed
by SQLite WAL-mode for persistence.

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                     SharedMemoryBus                          │
    │                                                              │
    │  ┌────────────┐  ┌────────────┐  ┌───────────────────────┐  │
    │  │ RingBuffer │  │  AgentMail  │  │     SharedState       │  │
    │  │ 1024×4KB   │  │  boxes     │  │  KV + ReadWriteLock   │  │
    │  │ zero-copy  │  │  priority  │  │  TTL + callbacks      │  │
    │  └─────┬──────┘  └─────┬──────┘  └──────────┬────────────┘  │
    │        │               │                     │               │
    │        └───────────────┼─────────────────────┘               │
    │                        │                                     │
    │              ┌─────────▼──────────┐                          │
    │              │ PersistenceLayer   │                          │
    │              │ SQLite WAL-mode    │                          │
    │              │ Batch 50ms/100 ops │                          │
    │              └────────────────────┘                          │
    │                                                              │
    │              ┌────────────────────┐                          │
    │              │   BusMetrics       │                          │
    │              │   Lock-free cnts   │                          │
    │              └────────────────────┘                          │
    └──────────────────────────────────────────────────────────────┘

Performance targets:
    - send()        < 0.05ms  (in-memory deque + async SQLite)
    - receive()     < 0.05ms  (in-memory heapq pop)
    - set_state()   < 0.05ms  (in-memory dict + async SQLite)
    - get_state()   < 0.02ms  (in-memory dict lookup)
    - write_ring()  < 0.01ms  (pre-allocated buffer + atomic index)
    - read_ring()   < 0.01ms  (memoryview slice)
    - broadcast()   < 0.5ms   (O(N) fan-out to N mailboxes)

Thread safety:
    - Mailbox:    per-mailbox Lock (not global)
    - SharedState: ReadWriteLock (concurrent reads, exclusive writes)
    - RingBuffer:  atomic index counter, per-slot write lock
    - SQLite:     WAL mode (concurrent reads, single writer)
    - Metrics:    simple counters (minor races acceptable)
"""

import heapq
import json
import logging
import sqlite3
import struct
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.core.patterns.concurrency.read_write_lock import ReadWriteLock
from src.core.shared.db_utils import escape_sql_like

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RING_SLOT_SIZE: int = 4096  # 4 KB per slot
_DEFAULT_RING_SIZE: int = 1024  # 1024 slots → 4 MB
_MAX_MAILBOX_DEPTH: int = 100
_FLUSH_INTERVAL_S: float = 0.05  # 50 ms
_FLUSH_BATCH_SIZE: int = 100
_DB_CACHE_SIZE: int = -8192  # 8 MB
_DB_MMAP_SIZE: int = 67108864  # 64 MB

# Struct format for ring-buffer slot header:
#   4 bytes data_length (uint32)  |  4 bytes tenant_hash (uint32)
#   = 8-byte header per slot
_SLOT_HEADER_FMT = "<II"
_SLOT_HEADER_SIZE = struct.calcsize(_SLOT_HEADER_FMT)


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class MessageType(IntEnum):
    """Message type classification for agent communication."""
    DATA = 0
    CONTROL = 1
    ERROR = 2


class Priority(IntEnum):
    """Priority levels for mailbox message ordering.

    Lower numeric value = higher priority (retrieved first).
    """
    CRITICAL = 0
    HIGH = 1
    NORMAL = 5
    LOW = 10


@dataclass
class BusMessage:
    """A single message travelling through the shared memory bus.

    Attributes:
        sender: Agent ID of the sender (e.g., "A01").
        recipient: Agent ID of the recipient, or "broadcast".
        msg_type: Classification of the message.
        priority: Ordering priority (lower = higher priority).
        payload: The actual data carried by the message.
        timestamp: Monotonic timestamp when the message was created.
        tenant_id: Tenant isolation identifier.
        ttl_seconds: Time-to-live in seconds (0 = no expiry).
        correlation_id: Optional ID for request-response correlation.
    """
    sender: str
    recipient: str
    msg_type: MessageType
    priority: Priority
    payload: Any
    timestamp: float = field(default_factory=time.monotonic)
    tenant_id: str = "default"
    ttl_seconds: float = 300.0
    correlation_id: str = ""


# ---------------------------------------------------------------------------
# Ring Buffer
# ---------------------------------------------------------------------------

class RingBuffer:
    """Fixed-size circular buffer for hot-path data.

    Pre-allocates *ring_size* slots, each *slot_size* bytes. Writes are
    O(1) via an atomic counter; reads are O(1) by slot index. Zero-copy
    reads are provided via ``memoryview`` slices.

    Args:
        ring_size: Number of slots in the ring (default 1024).
        slot_size: Bytes per slot (default 4096).
    """

    def __init__(self, ring_size: int = _DEFAULT_RING_SIZE,
                 slot_size: int = _RING_SLOT_SIZE) -> None:
        self._ring_size = ring_size
        self._slot_size = slot_size
        # Pre-allocated flat buffer: ring_size × slot_size
        self._buffer = bytearray(ring_size * slot_size)
        self._view = memoryview(self._buffer)
        # Atomic write index (monotonically increasing)
        self._write_idx: int = 0
        self._idx_lock = threading.Lock()
        # Per-slot write locks to avoid global contention
        self._slot_locks = [threading.Lock() for _ in range(ring_size)]
        # Track which slots are occupied: slot→(timestamp, tenant_id)
        self._slot_meta: Dict[int, Tuple[float, str]] = {}

    # ── Write ──

    def write(self, data: bytes, tenant_id: str = "default") -> int:
        """Write *data* to the next available slot.

        Returns:
            The absolute slot index (wrap-aware).

        Raises:
            ValueError: If *data* exceeds slot capacity.
        """
        max_payload = self._slot_size - _SLOT_HEADER_SIZE
        if len(data) > max_payload:
            raise ValueError(
                f"Data size {len(data)} exceeds max payload {max_payload} bytes"
            )

        with self._idx_lock:
            abs_idx = self._write_idx
            self._write_idx += 1

        slot_idx = abs_idx % self._ring_size
        tenant_hash = hash(tenant_id) & 0xFFFFFFFF

        with self._slot_locks[slot_idx]:
            offset = slot_idx * self._slot_size
            # Write header
            struct.pack_into(
                _SLOT_HEADER_FMT,
                self._buffer,
                offset,
                len(data),
                tenant_hash,
            )
            # Write payload
            start = offset + _SLOT_HEADER_SIZE
            self._buffer[start:start + len(data)] = data
            self._slot_meta[slot_idx] = (time.monotonic(), tenant_id)

        return abs_idx

    # ── Read ──

    def read(self, slot_index: int) -> Optional[bytes]:
        """Read data from a slot by absolute index.

        Returns:
            The payload bytes, or ``None`` if the slot is empty / expired.
        """
        slot_idx = slot_index % self._ring_size
        offset = slot_idx * self._slot_size

        with self._slot_locks[slot_idx]:
            data_len, tenant_hash = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len == 0:
                return None
            start = offset + _SLOT_HEADER_SIZE
            return bytes(self._view[start:start + data_len])

    def read_memoryview(self, slot_index: int) -> Optional[memoryview]:
        """Zero-copy read via memoryview slice.

        The caller **must not** modify the returned view.
        """
        slot_idx = slot_index % self._ring_size
        offset = slot_idx * self._slot_size

        with self._slot_locks[slot_idx]:
            data_len, _tenant_hash = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len == 0:
                return None
            start = offset + _SLOT_HEADER_SIZE
            return self._view[start:start + data_len]

    # ── Introspection ──

    @property
    def utilization(self) -> float:
        """Fraction of slots currently occupied (0.0–1.0)."""
        return len(self._slot_meta) / self._ring_size if self._ring_size else 0.0

    @property
    def write_index(self) -> int:
        """Current absolute write index."""
        return self._write_idx

    def snapshot_dirty_slots(self) -> List[Tuple[int, bytes, str, float]]:
        """Return all occupied slots for persistence.

        Returns:
            List of (slot_index, data_blob, tenant_id, timestamp).
        """
        result: List[Tuple[int, bytes, str, float]] = []
        for slot_idx, (ts, tenant_id) in list(self._slot_meta.items()):
            offset = slot_idx * self._slot_size
            data_len, _ = struct.unpack_from(
                _SLOT_HEADER_FMT, self._buffer, offset
            )
            if data_len > 0:
                start = offset + _SLOT_HEADER_SIZE
                blob = bytes(self._buffer[start:start + data_len])
                result.append((slot_idx, blob, tenant_id, ts))
        return result


# ---------------------------------------------------------------------------
# Agent Mailbox
# ---------------------------------------------------------------------------

class AgentMailbox:
    """Per-agent priority message queue.

    Messages are stored in a heap ordered by ``(priority, timestamp)`` so
    that the highest-priority (lowest numeric) message is always dequeued
    first. Non-blocking reads are O(log N) via ``heapq``.

    When the mailbox exceeds *_MAX_MAILBOX_DEPTH*, the lowest-priority
    (highest numeric value) message is evicted (LRU by priority).

    Args:
        agent_id: The owning agent's identifier.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._lock = threading.Lock()
        # Heap of (priority, timestamp, sequence, BusMessage)
        self._heap: List[Tuple[int, float, int, BusMessage]] = []
        self._seq = 0  # Tie-breaker to maintain FIFO within same priority
        self._not_empty = threading.Condition(self._lock)

    # ── Enqueue ──

    def push(self, msg: BusMessage) -> None:
        """Push a message into the mailbox."""
        with self._not_empty:
            if len(self._heap) >= _MAX_MAILBOX_DEPTH:
                self._evict_one()
            self._seq += 1
            heapq.heappush(
                self._heap,
                (int(msg.priority), msg.timestamp, self._seq, msg),
            )
            self._not_empty.notify()

    def _evict_one(self) -> None:
        """Evict the lowest-priority (highest numeric) message."""
        if not self._heap:
            return
        # Find max-priority item (highest numeric value = lowest priority)
        max_idx = max(range(len(self._heap)),
                      key=lambda i: self._heap[i][0])
        evicted = self._heap.pop(max_idx)
        if evicted is not None:
            heapq.heapify(self._heap)
            logger.debug(
                "Mailbox %s evicted message from %s (priority=%d)",
                self.agent_id, evicted[3].sender, evicted[0],
            )

    # ── Dequeue ──

    def pop(self, timeout_ms: float = 0) -> Optional[BusMessage]:
        """Non-blocking (or timed) pop of the highest-priority message.

        Args:
            timeout_ms: Maximum time to wait in milliseconds.
                0 = non-blocking (default).

        Returns:
            The highest-priority :class:`BusMessage`, or ``None``.
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._not_empty:
            while not self._heap:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                if not self._not_empty.wait(timeout=remaining):
                    return None
            _, _, _, msg = heapq.heappop(self._heap)
            return msg

    # ── Introspection ──

    @property
    def depth(self) -> int:
        """Current number of messages in the mailbox."""
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """Whether the mailbox has no messages."""
        with self._lock:
            return len(self._heap) == 0

    def peek_all(self) -> List[BusMessage]:
        """Return a snapshot of all messages without removing them."""
        with self._lock:
            return [item[3] for item in sorted(self._heap)]


# ---------------------------------------------------------------------------
# Shared State
# ---------------------------------------------------------------------------

class SharedState:
    """Thread-safe key-value store for pipeline context.

    Features:
        - ReadWriteLock for concurrent reads / exclusive writes
        - Namespaced by agent_id and tenant_id
        - TTL support (auto-expire stale context)
        - Change notification via callback registration
        - Atomic get-and-set for conditional updates

    Internal structure::

        _data[namespace][key] = (value, updated_at, ttl_seconds)
    """

    def __init__(self) -> None:
        self._rw_lock = ReadWriteLock()
        # namespace → key → (value, updated_at, ttl_seconds)
        self._data: Dict[str, Dict[str, Tuple[Any, float, float]]] = {}
        # Change callbacks: list of (namespace_pattern, callback)
        self._callbacks: List[Tuple[str, Callable[[str, str, Any], None]]] = []

    # ── Core Operations ──

    def set(self, namespace: str, key: str, value: Any,
            ttl: float = 0, tenant_id: str = "default") -> None:
        """Set a value. Overwrites existing. O(1) in-memory."""
        ns_key = f"{tenant_id}:{namespace}"
        now = time.monotonic()
        with self._rw_lock.acquire_write():
            if ns_key not in self._data:
                self._data[ns_key] = {}
            self._data[ns_key][key] = (value, now, ttl)
        self._notify_callbacks(namespace, key, value)

    def get(self, namespace: str, key: str, default: Any = None,
            tenant_id: str = "default") -> Any:
        """Get a value. Returns *default* if missing or expired. O(1)."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_read():
            ns = self._data.get(ns_key)
            if ns is None:
                return default
            entry = ns.get(key)
            if entry is None:
                return default
            value, updated_at, ttl = entry
            if ttl > 0:
                if time.monotonic() - updated_at > ttl:
                    # Expired — caller should clean up via delete
                    return default
            return value

    def get_and_set(self, namespace: str, key: str, value: Any,
                    ttl: float = 0, tenant_id: str = "default") -> Any:
        """Atomic get-and-set. Returns the previous value (or *default*)."""
        ns_key = f"{tenant_id}:{namespace}"
        now = time.monotonic()
        old_value = None
        with self._rw_lock.acquire_write():
            if ns_key not in self._data:
                self._data[ns_key] = {}
            old_entry = self._data[ns_key].get(key)
            if old_entry is not None:
                old_value = old_entry[0]
            self._data[ns_key][key] = (value, now, ttl)
        self._notify_callbacks(namespace, key, value)
        return old_value

    def delete(self, namespace: str, key: str,
               tenant_id: str = "default") -> None:
        """Delete a key from the namespace."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_write():
            ns = self._data.get(ns_key)
            if ns is not None and key in ns:
                del ns[key]

    def list_keys(self, namespace: str, prefix: str = "",
                  tenant_id: str = "default") -> List[str]:
        """List keys in a namespace, optionally filtered by *prefix*."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_read():
            ns = self._data.get(ns_key)
            if ns is None:
                return []
            if prefix:
                return [k for k in ns.keys() if k.startswith(prefix)]
            return list(ns.keys())

    # ── Callbacks ──

    def register_callback(self, namespace: str,
                          callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback invoked when a key in *namespace* changes."""
        self._callbacks.append((namespace, callback))

    def _notify_callbacks(self, namespace: str, key: str, value: Any) -> None:
        """Fire registered callbacks (outside write lock)."""
        for ns_pattern, cb in self._callbacks:
            if ns_pattern == "*" or ns_pattern == namespace:
                try:
                    cb(namespace, key, value)
                except Exception:
                    logger.exception("SharedState callback error for ns=%s key=%s",
                                     namespace, key)

    # ── Expiry ──

    def purge_expired(self) -> int:
        """Remove all expired entries across all namespaces.

        Returns:
            Number of entries purged.
        """
        purged = 0
        now = time.monotonic()
        with self._rw_lock.acquire_write():
            for ns_key in list(self._data.keys()):
                ns = self._data[ns_key]
                for k in list(ns.keys()):
                    _, updated_at, ttl = ns[k]
                    if ttl > 0 and now - updated_at > ttl:
                        del ns[k]
                        purged += 1
        return purged

    # ── Snapshot for Persistence ──

    def snapshot(self) -> List[Tuple[str, str, str, str, float, float]]:
        """Return all non-expired entries for persistence.

        Returns:
            List of (namespace, key, json_value, tenant_id, updated_at, ttl).
        """
        result: List[Tuple[str, str, str, str, float, float]] = []
        now = time.monotonic()
        with self._rw_lock.acquire_read():
            for ns_key, ns in self._data.items():
                # ns_key = "tenant_id:namespace"
                parts = ns_key.split(":", 1)
                tenant_id = parts[0] if len(parts) == 2 else "default"
                namespace = parts[1] if len(parts) == 2 else ns_key
                for k, (v, updated_at, ttl) in ns.items():
                    if ttl > 0 and now - updated_at > ttl:
                        continue
                    result.append((
                        namespace, k,
                        json.dumps(v, default=str),
                        tenant_id, updated_at, ttl,
                    ))
        return result


# ---------------------------------------------------------------------------
# Persistence Layer
# ---------------------------------------------------------------------------

class PersistenceLayer:
    """SQLite WAL-mode backend for durable storage.

    Manages three tables: ``mailbox_messages``, ``shared_state``,
    ``ring_buffer_snapshots``. Writes are batched (50 ms or 100 entries)
    to minimise fsync overhead.

    Args:
        db_path: Path to the SQLite database file.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS mailbox_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        recipient TEXT NOT NULL,
        msg_type INTEGER NOT NULL,
        priority INTEGER NOT NULL,
        payload TEXT NOT NULL,
        timestamp REAL NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        ttl_seconds REAL NOT NULL DEFAULT 300.0,
        correlation_id TEXT DEFAULT '',
        created_at REAL DEFAULT (strftime('%s','now'))
    );
    CREATE INDEX IF NOT EXISTS idx_mm_recipient_priority
        ON mailbox_messages(recipient, priority);
    CREATE INDEX IF NOT EXISTS idx_mm_tenant
        ON mailbox_messages(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_mm_timestamp
        ON mailbox_messages(timestamp);

    CREATE TABLE IF NOT EXISTS shared_state (
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        updated_at REAL NOT NULL,
        ttl_seconds REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (namespace, key, tenant_id)
    );

    CREATE TABLE IF NOT EXISTS ring_buffer_snapshots (
        slot_index INTEGER PRIMARY KEY,
        data BLOB,
        tenant_id TEXT NOT NULL DEFAULT 'default',
        timestamp REAL NOT NULL
    );
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()  # guards pending queues
        self._db_lock = threading.Lock()  # guards SQLite connection
        # Pending batches
        self._pending_messages: List[BusMessage] = []
        self._pending_state: List[Tuple[str, str, str, str, float, float]] = []
        self._pending_ring: List[Tuple[int, bytes, str, float]] = []
        self._conn = self._open()
        self._init_schema()

    # ── Connection ──

    def _open(self) -> sqlite3.Connection:
        """Open a connection with WAL-mode and tuned PRAGMAs."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA cache_size={_DB_CACHE_SIZE}")
        conn.execute(f"PRAGMA mmap_size={_DB_MMAP_SIZE}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist."""
        self._conn.executescript(self._SCHEMA)
        self._conn.commit()

    # ── Enqueue ──

    def enqueue_message(self, msg: BusMessage) -> None:
        """Stage a message for batched write."""
        with self._write_lock:
            self._pending_messages.append(msg)

    def enqueue_state(self, entry: Tuple[str, str, str, str, float, float]) -> None:
        """Stage a state entry for batched write."""
        with self._write_lock:
            self._pending_state.append(entry)

    def enqueue_ring(self, entry: Tuple[int, bytes, str, float]) -> None:
        """Stage a ring-buffer slot for batched write."""
        with self._write_lock:
            self._pending_ring.append(entry)

    # ── Flush ──

    def flush(self) -> None:
        """Flush all pending writes to SQLite in batched transactions."""
        with self._write_lock:
            msgs = self._pending_messages[:]
            states = self._pending_state[:]
            rings = self._pending_ring[:]
            self._pending_messages.clear()
            self._pending_state.clear()
            self._pending_ring.clear()

        if not msgs and not states and not rings:
            return

        # Serialise messages outside the DB lock to minimise contention
        msg_rows = [
            (
                m.sender, m.recipient, int(m.msg_type),
                int(m.priority),
                json.dumps(m.payload, default=str),
                m.timestamp, m.tenant_id,
                m.ttl_seconds, m.correlation_id,
            )
            for m in msgs
        ]

        with self._db_lock:
            try:
                # Mailbox messages — chunked to avoid huge transactions
                for offset in range(0, len(msg_rows), _FLUSH_BATCH_SIZE):
                    chunk = msg_rows[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT INTO mailbox_messages
                           (sender, recipient, msg_type, priority, payload,
                            timestamp, tenant_id, ttl_seconds, correlation_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        chunk,
                    )
                    self._conn.commit()

                # Shared state (upsert) — chunked
                for offset in range(0, len(states), _FLUSH_BATCH_SIZE):
                    chunk = states[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT INTO shared_state
                           (namespace, key, value, tenant_id, updated_at, ttl_seconds)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(namespace, key, tenant_id)
                           DO UPDATE SET value=excluded.value,
                                         updated_at=excluded.updated_at,
                                         ttl_seconds=excluded.ttl_seconds""",
                        chunk,
                    )
                    self._conn.commit()

                # Ring buffer snapshots — chunked
                for offset in range(0, len(rings), _FLUSH_BATCH_SIZE):
                    chunk = rings[offset:offset + _FLUSH_BATCH_SIZE]
                    self._conn.executemany(
                        """INSERT OR REPLACE INTO ring_buffer_snapshots
                           (slot_index, data, tenant_id, timestamp)
                           VALUES (?, ?, ?, ?)""",
                        chunk,
                    )
                    self._conn.commit()
            except Exception:
                logger.exception("PersistenceLayer flush failed")

    # ── Checkpoint ──

    def checkpoint(self) -> None:
        """Run WAL checkpoint to truncate the WAL file."""
        with self._db_lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                logger.exception("WAL checkpoint failed")

    # ── Purge ──

    def purge_tenant(self, tenant_id: str) -> int:
        """Delete all data for a tenant (GDPR compliance).

        Returns:
            Total number of rows deleted.
        """
        with self._db_lock:
            total = 0
            for table in ("mailbox_messages", "shared_state", "ring_buffer_snapshots"):
                try:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE tenant_id=?", (tenant_id,)
                    )
                    total += cursor.rowcount
                except Exception:
                    logger.exception("Purge failed for tenant=%s table=%s",
                                     tenant_id, table)
            self._conn.commit()
            return total

    # ── Lifecycle ──

    def close(self) -> None:
        """Flush remaining data and close the connection."""
        self.flush()
        with self._db_lock:
            try:
                self._conn.close()
            except Exception:
                logger.exception("Error closing PersistenceLayer connection")


# ---------------------------------------------------------------------------
# Bus Metrics
# ---------------------------------------------------------------------------

class BusMetrics:
    """Performance counters for the shared memory bus.

    Uses simple integer counters with a threading Lock for correctness.
    Minor races are acceptable for observability data.

    Tracks:
        - Per-agent: messages_sent, messages_received, total_latency_us
        - Global: total_throughput, buffer_utilization, db_flush_count
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Per-agent counters
        self._agent_sent: Dict[str, int] = {}
        self._agent_received: Dict[str, int] = {}
        self._agent_latency_us: Dict[str, float] = {}
        # Global counters
        self.total_throughput: int = 0
        self.db_flush_count: int = 0

    def record_send(self, agent_id: str, latency_us: float = 0.0) -> None:
        """Record a message sent by *agent_id*."""
        with self._lock:
            self._agent_sent[agent_id] = self._agent_sent.get(agent_id, 0) + 1
            self._agent_latency_us[agent_id] = (
                self._agent_latency_us.get(agent_id, 0.0) + latency_us
            )
            self.total_throughput += 1

    def record_receive(self, agent_id: str) -> None:
        """Record a message received by *agent_id*."""
        with self._lock:
            self._agent_received[agent_id] = (
                self._agent_received.get(agent_id, 0) + 1
            )

    def record_flush(self) -> None:
        """Record a database flush cycle."""
        with self._lock:
            self.db_flush_count += 1

    def snapshot(self, buffer_utilization: float = 0.0) -> Dict[str, Any]:
        """Return a point-in-time metrics snapshot."""
        with self._lock:
            per_agent: Dict[str, Dict[str, Any]] = {}
            all_agents = set(self._agent_sent) | set(self._agent_received)
            for aid in all_agents:
                sent = self._agent_sent.get(aid, 0)
                received = self._agent_received.get(aid, 0)
                total_lat = self._agent_latency_us.get(aid, 0.0)
                avg_lat = (total_lat / sent) if sent > 0 else 0.0
                per_agent[aid] = {
                    "messages_sent": sent,
                    "messages_received": received,
                    "avg_latency_us": round(avg_lat, 2),
                }
            return {
                "total_throughput": self.total_throughput,
                "buffer_utilization": round(buffer_utilization, 4),
                "db_flush_count": self.db_flush_count,
                "per_agent": per_agent,
            }


# ---------------------------------------------------------------------------
# Shared Memory Bus (main class)
# ---------------------------------------------------------------------------

class SharedMemoryBus:
    """Ultra-fast inter-agent communication bus.

    Combines:
        - In-memory ring buffer for hot data (O(1) read/write)
        - SQLite WAL-mode for persistence and cross-process access
        - Zero-copy where possible via memoryview
        - Per-agent write locks, lock-free reads

    Design goals:
        - < 0.1 ms inter-agent data transfer
        - Support 42+ agents simultaneously
        - Thread-safe with minimal lock contention
        - Tenant-isolated (multi-tenant support)

    Args:
        db_path: Path to the SQLite database file.  Defaults to
            ``shared_bus.sqlite`` in the current working directory.
        ring_size: Number of ring buffer slots (default 1024).
        tenant_id: Default tenant for all operations.

    Example::

        bus = SharedMemoryBus(tenant_id="acme")
        bus.send("A01", "A02", {"action": "classify"}, priority=Priority.HIGH)
        msg = bus.receive("A02")
        bus.close()
    """

    def __init__(self, db_path: Optional[str] = None,
                 ring_size: int = _DEFAULT_RING_SIZE,
                 tenant_id: str = "default") -> None:
        self._tenant_id = tenant_id
        self._db_path = db_path or "shared_bus.sqlite"

        # Core components
        self._ring = RingBuffer(ring_size=ring_size)
        self._state = SharedState()
        self._metrics = BusMetrics()
        self._persistence = PersistenceLayer(self._db_path)

        # Agent mailboxes: agent_id → AgentMailbox
        self._mailboxes: Dict[str, AgentMailbox] = {}
        self._mailboxes_lock = threading.Lock()

        # Registered agents for broadcast
        self._registered_agents: Dict[str, str] = {}  # agent_id → tenant_id
        self._agents_lock = threading.Lock()

        # Background flush thread
        self._stop_event = threading.Event()
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="SharedMemoryBus-Flush",
            daemon=True,
        )
        self._flush_thread.start()

        # TTL reaper thread (runs every 5 s)
        self._reaper_thread = threading.Thread(
            target=self._reaper_loop,
            name="SharedMemoryBus-Reaper",
            daemon=True,
        )
        self._reaper_thread.start()

        logger.info(
            "SharedMemoryBus initialised: db=%s ring=%d slots tenant=%s",
            self._db_path, ring_size, tenant_id,
        )

    # ── Mailbox API ──

    def send(self, sender: str, recipient: str, payload: Any,
             msg_type: MessageType = MessageType.DATA,
             priority: Priority = Priority.NORMAL,
             correlation_id: str = "",
             ttl_seconds: float = 300.0) -> bool:
        """Send a message to an agent's mailbox.

        O(1) for in-memory delivery; the message is asynchronously
        flushed to SQLite by the background thread.

        Args:
            sender: Agent ID of the sender.
            recipient: Agent ID of the recipient.
            payload: Data to send.
            msg_type: Message classification.
            priority: Ordering priority.
            correlation_id: Optional correlation ID for request-response.
            ttl_seconds: Message time-to-live in seconds.

        Returns:
            ``True`` if the message was delivered, ``False`` otherwise.
        """
        start = time.monotonic()
        msg = BusMessage(
            sender=sender,
            recipient=recipient,
            msg_type=msg_type,
            priority=priority,
            payload=payload,
            tenant_id=self._tenant_id,
            ttl_seconds=ttl_seconds,
            correlation_id=correlation_id,
        )

        mailbox = self._get_or_create_mailbox(recipient)
        mailbox.push(msg)

        # Async persistence
        self._persistence.enqueue_message(msg)

        latency_us = (time.monotonic() - start) * 1_000_000
        self._metrics.record_send(sender, latency_us)
        return True

    def receive(self, agent_id: str, timeout_ms: float = 0) -> Optional[BusMessage]:
        """Non-blocking (or timed) receive from agent's mailbox.

        Returns the highest-priority message first.

        Args:
            agent_id: The receiving agent's ID.
            timeout_ms: Max wait in milliseconds (0 = non-blocking).

        Returns:
            A :class:`BusMessage` or ``None`` if no message is available.
        """
        mailbox = self._get_or_create_mailbox(agent_id)
        msg = mailbox.pop(timeout_ms=timeout_ms)
        if msg is not None:
            # Check TTL
            if msg.ttl_seconds > 0:
                age = time.monotonic() - msg.timestamp
                if age > msg.ttl_seconds:
                    # Expired — discard and try again
                    return self.receive(agent_id, timeout_ms=0)
            self._metrics.record_receive(agent_id)
        return msg

    def broadcast(self, sender: str, payload: Any,
                  msg_type: MessageType = MessageType.DATA,
                  priority: Priority = Priority.NORMAL) -> int:
        """Broadcast a message to all registered agents.

        Args:
            sender: Agent ID of the sender.
            payload: Data to broadcast.
            msg_type: Message classification.
            priority: Ordering priority.

        Returns:
            Number of agents that received the message.
        """
        with self._agents_lock:
            targets = list(self._registered_agents.keys())

        count = 0
        for agent_id in targets:
            if agent_id == sender:
                continue
            if self.send(sender, agent_id, payload, msg_type, priority):
                count += 1
        return count

    def register_agent(self, agent_id: str, tenant_id: Optional[str] = None) -> None:
        """Register an agent for broadcast delivery.

        Args:
            agent_id: Unique agent identifier.
            tenant_id: Override tenant (defaults to bus tenant).
        """
        tid = tenant_id or self._tenant_id
        with self._agents_lock:
            self._registered_agents[agent_id] = tid
        self._get_or_create_mailbox(agent_id)
        logger.debug("Agent %s registered (tenant=%s)", agent_id, tid)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from broadcast delivery."""
        with self._agents_lock:
            self._registered_agents.pop(agent_id, None)
        with self._mailboxes_lock:
            self._mailboxes.pop(agent_id, None)

    # ── Shared State API ──

    def set_state(self, namespace: str, key: str, value: Any,
                  ttl: float = 0) -> None:
        """Set a value in shared state. O(1) in-memory, async flush.

        Args:
            namespace: Dot-separated namespace (e.g., "A01.context").
            key: Key within the namespace.
            value: Value to store (must be JSON-serialisable for persistence).
            ttl: Time-to-live in seconds (0 = no expiry).
        """
        self._state.set(namespace, key, value, ttl=ttl, tenant_id=self._tenant_id)
        self._persistence.enqueue_state((
            namespace, key,
            json.dumps(value, default=str),
            self._tenant_id,
            time.monotonic(),
            ttl,
        ))

    def get_state(self, namespace: str, key: str,
                  default: Any = None) -> Any:
        """Get a value from shared state. O(1) in-memory lookup.

        Args:
            namespace: Dot-separated namespace.
            key: Key within the namespace.
            default: Value returned if key is missing or expired.

        Returns:
            The stored value, or *default*.
        """
        return self._state.get(namespace, key, default=default,
                               tenant_id=self._tenant_id)

    def get_and_set(self, namespace: str, key: str, value: Any) -> Any:
        """Atomic get-and-set. Returns the previous value.

        Args:
            namespace: Dot-separated namespace.
            key: Key within the namespace.
            value: New value to store.

        Returns:
            The previous value (or ``None`` if the key didn't exist).
        """
        old = self._state.get_and_set(namespace, key, value,
                                       tenant_id=self._tenant_id)
        self._persistence.enqueue_state((
            namespace, key,
            json.dumps(value, default=str),
            self._tenant_id,
            time.monotonic(),
            0,
        ))
        return old

    def delete_state(self, namespace: str, key: str) -> None:
        """Delete a key from shared state.

        Args:
            namespace: Dot-separated namespace.
            key: Key within the namespace.
        """
        self._state.delete(namespace, key, tenant_id=self._tenant_id)

    def list_keys(self, namespace: str, prefix: str = "") -> List[str]:
        """List keys in a namespace with optional prefix filter.

        Args:
            namespace: Dot-separated namespace.
            prefix: Optional key prefix to filter by.

        Returns:
            Sorted list of matching keys.
        """
        return self._state.list_keys(namespace, prefix=prefix,
                                      tenant_id=self._tenant_id)

    def register_state_callback(self, namespace: str,
                                callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback for state changes in a namespace.

        Args:
            namespace: Namespace to watch ("*" for all).
            callback: Called with (namespace, key, new_value).
        """
        self._state.register_callback(namespace, callback)

    # ── Ring Buffer API ──

    def write_ring(self, data: bytes, tenant_id: Optional[str] = None) -> int:
        """Write data to the ring buffer. Returns absolute slot index. O(1).

        Args:
            data: Bytes to write (max ~4088 bytes per slot).
            tenant_id: Override tenant (defaults to bus tenant).

        Returns:
            Absolute slot index for later retrieval.
        """
        tid = tenant_id or self._tenant_id
        idx = self._ring.write(data, tenant_id=tid)
        # Queue for async persistence (simplified — snapshot on flush)
        return idx

    def read_ring(self, slot_index: int) -> Optional[bytes]:
        """Read data from a ring buffer slot. O(1).

        Args:
            slot_index: Absolute slot index returned by :meth:`write_ring`.

        Returns:
            Payload bytes, or ``None`` if the slot is empty.
        """
        return self._ring.read(slot_index)

    def read_ring_zero_copy(self, slot_index: int) -> Optional[memoryview]:
        """Zero-copy read via memoryview.

        The caller **must not** modify the returned view.
        """
        return self._ring.read_memoryview(slot_index)

    # ── Persistence ──

    def flush(self) -> None:
        """Force flush all pending writes to SQLite."""
        # Also flush ring buffer snapshot
        for slot_idx, blob, tenant_hint, ts in self._ring.snapshot_dirty_slots():
            tid = tenant_hint or self._tenant_id
            self._persistence.enqueue_ring((slot_idx, blob, tid, ts))
        self._persistence.flush()
        self._metrics.record_flush()

    def checkpoint(self) -> None:
        """Run WAL checkpoint to truncate the WAL file."""
        self._persistence.checkpoint()

    # ── Metrics ──

    def metrics(self) -> Dict[str, Any]:
        """Get bus performance metrics.

        Returns:
            Dictionary with global and per-agent metrics.
        """
        return self._metrics.snapshot(buffer_utilization=self._ring.utilization)

    # ── Lifecycle ──

    def close(self) -> None:
        """Flush pending data, stop background threads, and close resources."""
        logger.info("SharedMemoryBus shutting down")
        self._stop_event.set()
        self.flush()
        self._persistence.close()
        # Wait for threads (with timeout)
        self._flush_thread.join(timeout=2.0)
        self._reaper_thread.join(timeout=2.0)
        logger.info("SharedMemoryBus closed")

    def purge_tenant(self, tenant_id: str) -> int:
        """Remove all persisted data for a tenant (GDPR compliance).

        Also clears in-memory mailboxes and state for the tenant.

        Args:
            tenant_id: Tenant identifier to purge.

        Returns:
            Number of database rows deleted.
        """
        # In-memory cleanup
        with self._mailboxes_lock:
            # Remove mailboxes belonging to this tenant
            with self._agents_lock:
                to_remove = [
                    aid for aid, tid in self._registered_agents.items()
                    if tid == tenant_id
                ]
                for aid in to_remove:
                    self._registered_agents.pop(aid, None)
                    self._mailboxes.pop(aid, None)

        # Persistence cleanup
        return self._persistence.purge_tenant(tenant_id)

    # ── Internals ──

    def _get_or_create_mailbox(self, agent_id: str) -> AgentMailbox:
        """Return the mailbox for *agent_id*, creating one if needed."""
        with self._mailboxes_lock:
            if agent_id not in self._mailboxes:
                self._mailboxes[agent_id] = AgentMailbox(agent_id)
            return self._mailboxes[agent_id]

    def _flush_loop(self) -> None:
        """Background thread that flushes pending data every 50 ms."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=_FLUSH_INTERVAL_S)
            if self._stop_event.is_set():
                break
            try:
                self.flush()
            except Exception:
                logger.exception("Flush loop error")

    def _reaper_loop(self) -> None:
        """Background thread that purges expired state entries every 5 s."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=5.0)
            if self._stop_event.is_set():
                break
            try:
                purged = self._state.purge_expired()
                if purged > 0:
                    logger.debug("Reaper purged %d expired state entries", purged)
            except Exception:
                logger.exception("Reaper loop error")


# ---------------------------------------------------------------------------
# Public Exports
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "MessageType",
    "Priority",
    # Data classes
    "BusMessage",
    # Components
    "RingBuffer",
    "AgentMailbox",
    "SharedState",
    "PersistenceLayer",
    "BusMetrics",
    # Main class
    "SharedMemoryBus",
]
