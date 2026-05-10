"""
ZENIC LOGIC — Shared Memory Bus for Inter-Agent Communication.

Simplified lightweight in-process communication layer for the
v16 DAG pipeline. Provides per-agent priority mailboxes and
a thread-safe shared state store.

Optimized for resource-constrained devices (Android/Termux, 500MB RAM).
All operations are in-memory — no SQLite, no ring buffer, no background threads.
"""

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_MAILBOX_DEPTH: int = 100


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
# Agent Mailbox
# ---------------------------------------------------------------------------

class AgentMailbox:
    """Per-agent priority message queue.

    Messages are stored in a heap ordered by ``(priority, timestamp)`` so
    that the highest-priority (lowest numeric) message is always dequeued
    first. Non-blocking reads are O(log N) via ``heapq``.

    When the mailbox exceeds *_MAX_MAILBOX_DEPTH*, the lowest-priority
    (highest numeric value) message is evicted.

    Args:
        agent_id: The owning agent's identifier.
    """

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._lock = threading.Lock()
        self._heap: List[Tuple[int, float, int, BusMessage]] = []
        self._seq = 0
        self._not_empty = threading.Condition(self._lock)

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
        max_idx = max(range(len(self._heap)),
                      key=lambda i: self._heap[i][0])
        self._heap.pop(max_idx)
        heapq.heapify(self._heap)

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


# ---------------------------------------------------------------------------
# Shared Memory Bus (main class)
# ---------------------------------------------------------------------------

class SharedMemoryBus:
    """Lightweight in-process inter-agent communication bus.

    Provides:
        - Per-agent priority mailboxes (heapq-based)
        - Thread-safe shared state (namespaced KV store with TTL)
        - Agent registration for broadcast delivery

    No SQLite, no ring buffer, no background threads.
    All operations are in-memory for minimal resource usage on ARM.

    Args:
        tenant_id: Default tenant for all operations.

    Example::

        bus = SharedMemoryBus(tenant_id="acme")
        bus.send("A01", "A02", {"action": "classify"}, priority=Priority.HIGH)
        msg = bus.receive("A02")
        bus.close()
    """

    def __init__(self, tenant_id: str = "default") -> None:
        self._tenant_id = tenant_id

        # Shared state: namespace → key → (value, updated_at, ttl_seconds)
        self._state_lock = threading.Lock()
        self._state: Dict[str, Dict[str, Tuple[Any, float, float]]] = {}

        # Agent mailboxes: agent_id → AgentMailbox
        self._mailboxes: Dict[str, AgentMailbox] = {}
        self._mailboxes_lock = threading.Lock()

        # Registered agents for broadcast
        self._registered_agents: Dict[str, str] = {}
        self._agents_lock = threading.Lock()

        logger.info("SharedMemoryBus initialised (lightweight): tenant=%s", tenant_id)

    # ── Mailbox API ──

    def send(self, sender: str, recipient: str, payload: Any,
             msg_type: MessageType = MessageType.DATA,
             priority: Priority = Priority.NORMAL,
             correlation_id: str = "",
             ttl_seconds: float = 300.0) -> bool:
        """Send a message to an agent's mailbox.

        Args:
            sender: Agent ID of the sender.
            recipient: Agent ID of the recipient.
            payload: Data to send.
            msg_type: Message classification.
            priority: Ordering priority.
            correlation_id: Optional correlation ID for request-response.
            ttl_seconds: Message time-to-live in seconds.

        Returns:
            ``True`` if the message was delivered.
        """
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
        if msg is not None and msg.ttl_seconds > 0:
            age = time.monotonic() - msg.timestamp
            if age > msg.ttl_seconds:
                return self.receive(agent_id, timeout_ms=0)
        return msg

    def broadcast(self, sender: str, payload: Any,
                  msg_type: MessageType = MessageType.DATA,
                  priority: Priority = Priority.NORMAL) -> int:
        """Broadcast a message to all registered agents.

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
        """Register an agent for broadcast delivery."""
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
        """Set a value in shared state.

        Args:
            namespace: Dot-separated namespace (e.g., "A01.context").
            key: Key within the namespace.
            value: Value to store.
            ttl: Time-to-live in seconds (0 = no expiry).
        """
        ns_key = f"{self._tenant_id}:{namespace}"
        now = time.monotonic()
        with self._state_lock:
            if ns_key not in self._state:
                self._state[ns_key] = {}
            self._state[ns_key][key] = (value, now, ttl)

    def get_state(self, namespace: str, key: str,
                  default: Any = None) -> Any:
        """Get a value from shared state.

        Args:
            namespace: Dot-separated namespace.
            key: Key within the namespace.
            default: Value returned if key is missing or expired.

        Returns:
            The stored value, or *default*.
        """
        ns_key = f"{self._tenant_id}:{namespace}"
        with self._state_lock:
            ns = self._state.get(ns_key)
            if ns is None:
                return default
            entry = ns.get(key)
            if entry is None:
                return default
            value, updated_at, ttl = entry
            if ttl > 0 and time.monotonic() - updated_at > ttl:
                return default
            return value

    def get_and_set(self, namespace: str, key: str, value: Any) -> Any:
        """Atomic get-and-set. Returns the previous value."""
        ns_key = f"{self._tenant_id}:{namespace}"
        now = time.monotonic()
        old_value = None
        with self._state_lock:
            if ns_key not in self._state:
                self._state[ns_key] = {}
            old_entry = self._state[ns_key].get(key)
            if old_entry is not None:
                old_value = old_entry[0]
            self._state[ns_key][key] = (value, now, 0)
        return old_value

    def delete_state(self, namespace: str, key: str) -> None:
        """Delete a key from shared state."""
        ns_key = f"{self._tenant_id}:{namespace}"
        with self._state_lock:
            ns = self._state.get(ns_key)
            if ns is not None and key in ns:
                del ns[key]

    def list_keys(self, namespace: str, prefix: str = "") -> List[str]:
        """List keys in a namespace, optionally filtered by prefix."""
        ns_key = f"{self._tenant_id}:{namespace}"
        with self._state_lock:
            ns = self._state.get(ns_key)
            if ns is None:
                return []
            if prefix:
                return [k for k in ns.keys() if k.startswith(prefix)]
            return list(ns.keys())

    # ── Lifecycle ──

    def close(self) -> None:
        """Shut down the bus and release resources."""
        with self._mailboxes_lock:
            self._mailboxes.clear()
        with self._state_lock:
            self._state.clear()
        logger.info("SharedMemoryBus closed")

    # ── Internal ──

    def _get_or_create_mailbox(self, agent_id: str) -> AgentMailbox:
        with self._mailboxes_lock:
            if agent_id not in self._mailboxes:
                self._mailboxes[agent_id] = AgentMailbox(agent_id)
            return self._mailboxes[agent_id]
