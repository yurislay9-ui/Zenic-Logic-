"""
TITAN OMNISCALE X - Cluster Topology

Node registration, heartbeat tracking, and cluster topology management.
Provides a real-time view of all active nodes in the distributed system.

Features:
    - Node registration with capabilities
    - Periodic heartbeat with status updates
    - Automatic detection of dead nodes (missed heartbeats)
    - Node capability queries (find workers by task type)
    - Cluster-wide statistics
    - Graceful node departure (deregistration)

Use Cases:
    - Service discovery (find available workers)
    - Load monitoring (track node utilization)
    - Work distribution (route tasks to capable nodes)
    - Failure detection (identify dead nodes)
"""

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

logger = logging.getLogger(__name__)

__all__ = [
    "ClusterTopology",
    "NodeInfo",
    "NodeState",
]


# ============================================================
#  ENUMS
# ============================================================

class NodeState(str, enum.Enum):
    """Node states."""
    JOINING = "joining"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    LEAVING = "leaving"
    DEAD = "dead"


# ============================================================
#  NODE INFO
# ============================================================

@dataclass
class NodeInfo:
    """
    Information about a node in the cluster.

    Attributes:
        node_id: Unique node identifier.
        hostname: Machine hostname.
        ip_address: Node IP address.
        capabilities: Dict of node capabilities (task types, resources).
        state: Current node state.
        registered_at: Timestamp of registration.
        last_heartbeat: Timestamp of last heartbeat.
        status: Current status payload (load, queue depth, etc.).
    """
    node_id: str = ""
    hostname: str = ""
    ip_address: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    state: NodeState = NodeState.JOINING
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    status: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{uuid.uuid4().hex[:8]}"
        if not self.hostname:
            self.hostname = socket.gethostname()
        if self.registered_at == 0.0:
            self.registered_at = time.time()
        if self.last_heartbeat == 0.0:
            self.last_heartbeat = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for backend storage."""
        return {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "capabilities": self.capabilities,
            "state": self.state.value,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeInfo":
        """Deserialize from backend dict."""
        state_str = data.get("state", "joining")
        try:
            state = NodeState(state_str)
        except ValueError:
            state = NodeState.JOINING

        return cls(
            node_id=data.get("node_id", ""),
            hostname=data.get("hostname", ""),
            ip_address=data.get("ip_address", ""),
            capabilities=data.get("capabilities", {}),
            state=state,
            registered_at=data.get("registered_at", 0.0),
            last_heartbeat=data.get("last_heartbeat", 0.0),
            status=data.get("status", {}),
        )


# ============================================================
#  CLUSTER TOPOLOGY
# ============================================================

class ClusterTopology:
    """
    Cluster topology manager for node registration and discovery.

    Each node registers itself on startup, sends periodic heartbeats,
    and deregisters on shutdown. Other nodes can query the topology
    to discover available workers and their capabilities.

    Usage::

        topology = ClusterTopology(
            backend=backend,
            node_info=NodeInfo(
                capabilities={"task_types": ["code_generation", "reasoning"]},
            ),
        )

        # Register this node
        await topology.join()

        # Start background heartbeat
        topology.start_heartbeat()

        # Discover workers
        nodes = await topology.find_capable_nodes("code_generation")

        # List all active nodes
        nodes = await topology.list_active_nodes()

        # Graceful departure
        await topology.leave()
    """

    # How many missed heartbeats before a node is considered dead
    DEAD_THRESHOLD_MULTIPLIER = 3

    def __init__(
        self,
        backend: CoordinationBackend,
        node_info: Optional[NodeInfo] = None,
        heartbeat_interval: float = 10.0,
    ) -> None:
        """
        Initialize the cluster topology manager.

        Args:
            backend: Coordination backend for persistent state.
            node_info: This node's information.
            heartbeat_interval: Seconds between heartbeats.
        """
        self._backend = backend
        self._node_info = node_info or NodeInfo()
        self._heartbeat_interval = heartbeat_interval

        # Ensure IP address is set
        if not self._node_info.ip_address:
            self._node_info.ip_address = self._get_local_ip()

        # Background threads
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._joined = False

    # ----------------------------------------------------------
    #  JOIN / LEAVE
    # ----------------------------------------------------------

    async def join(self) -> bool:
        """
        Register this node in the cluster.

        Returns:
            True if registration succeeded.
        """
        self._node_info.state = NodeState.ACTIVE
        success = await self._backend.register_node(
            self._node_info.to_dict()
        )

        if success:
            self._joined = True
            logger.info(
                "ClusterTopology: Node %s joined cluster "
                "(hostname=%s, ip=%s)",
                self._node_info.node_id,
                self._node_info.hostname,
                self._node_info.ip_address,
            )

        return success

    async def leave(self) -> bool:
        """
        Deregister this node from the cluster.

        Returns:
            True if deregistration succeeded.
        """
        self.stop_heartbeat()

        success = await self._backend.deregister_node(
            self._node_info.node_id
        )

        if success:
            self._joined = False
            logger.info(
                "ClusterTopology: Node %s left cluster",
                self._node_info.node_id,
            )

        return success

    # ----------------------------------------------------------
    #  HEARTBEAT
    # ----------------------------------------------------------

    async def send_heartbeat(self, status: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send a heartbeat for this node.

        Args:
            status: Optional status payload (load, queue depth, etc.).

        Returns:
            True if the heartbeat was recorded.
        """
        return await self._backend.heartbeat(
            self._node_info.node_id, status,
        )

    def start_heartbeat(self) -> None:
        """Start the background heartbeat thread."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"topology-heartbeat-{self._node_info.node_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()
        logger.debug(
            "ClusterTopology: Heartbeat started for %s "
            "(interval=%.1fs)",
            self._node_info.node_id, self._heartbeat_interval,
        )

    def stop_heartbeat(self) -> None:
        """Stop the background heartbeat thread."""
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)

    def _heartbeat_loop(self) -> None:
        """Background loop that sends periodic heartbeats."""
        while not self._stop_event.is_set():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(
                        self.send_heartbeat({
                            "state": self._node_info.state.value,
                        })
                    )
                finally:
                    loop.close()
            except Exception as exc:
                logger.debug(
                    "ClusterTopology: Heartbeat error for %s: %s",
                    self._node_info.node_id, exc,
                )

            self._stop_event.wait(timeout=self._heartbeat_interval)

    # ----------------------------------------------------------
    #  DISCOVERY
    # ----------------------------------------------------------

    async def list_active_nodes(self) -> List[NodeInfo]:
        """
        List all active nodes in the cluster.

        Returns:
            List of NodeInfo for active nodes.
        """
        nodes_data = await self._backend.list_nodes(active_only=True)
        return [NodeInfo.from_dict(d) for d in nodes_data]

    async def list_all_nodes(self) -> List[NodeInfo]:
        """
        List all registered nodes (including potentially dead ones).

        Returns:
            List of NodeInfo for all nodes.
        """
        nodes_data = await self._backend.list_nodes(active_only=False)
        return [NodeInfo.from_dict(d) for d in nodes_data]

    async def find_capable_nodes(self, task_type: str) -> List[NodeInfo]:
        """
        Find nodes capable of handling a specific task type.

        Args:
            task_type: The task type to search for.

        Returns:
            List of active nodes that support the given task type.
        """
        active = await self.list_active_nodes()
        capable = []
        for node in active:
            caps = node.capabilities
            if not isinstance(caps, dict):
                continue
            supported = caps.get("task_types", [])
            if isinstance(supported, list) and task_type in supported:
                capable.append(node)
        return capable

    async def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """
        Get information about a specific node.

        Args:
            node_id: The node to look up.

        Returns:
            NodeInfo, or None if not found.
        """
        all_nodes = await self.list_all_nodes()
        for node in all_nodes:
            if node.node_id == node_id:
                return node
        return None

    async def get_cluster_size(self) -> int:
        """
        Get the number of active nodes in the cluster.

        Returns:
            Active node count.
        """
        active = await self.list_active_nodes()
        return len(active)

    # ----------------------------------------------------------
    #  DEAD NODE DETECTION
    # ----------------------------------------------------------

    async def detect_dead_nodes(self) -> List[NodeInfo]:
        """
        Find nodes that have missed their heartbeats.

        Returns:
            List of nodes considered dead (no recent heartbeat).
        """
        all_nodes = await self.list_all_nodes()
        now = time.time()
        threshold = self._heartbeat_interval * self.DEAD_THRESHOLD_MULTIPLIER
        dead = []

        for node in all_nodes:
            if node.state in (NodeState.LEAVING, NodeState.DEAD):
                continue
            if now - node.last_heartbeat > threshold:
                dead.append(node)

        return dead

    async def cleanup_dead_nodes(self) -> int:
        """
        Remove dead nodes from the topology.

        Returns:
            Number of nodes removed.
        """
        dead = await self.detect_dead_nodes()
        removed = 0
        for node in dead:
            success = await self._backend.deregister_node(node.node_id)
            if success:
                removed += 1
                logger.info(
                    "ClusterTopology: Removed dead node %s "
                    "(last_heartbeat=%.0fs ago)",
                    node.node_id,
                    time.time() - node.last_heartbeat,
                )
        return removed

    # ----------------------------------------------------------
    #  PROPERTIES / STATS
    # ----------------------------------------------------------

    @property
    def node_info(self) -> NodeInfo:
        """This node's information."""
        return self._node_info

    @property
    def is_joined(self) -> bool:
        """Whether this node is registered in the cluster."""
        return self._joined

    @property
    def stats(self) -> Dict[str, Any]:
        """Topology manager statistics."""
        return {
            "node_id": self._node_info.node_id,
            "hostname": self._node_info.hostname,
            "ip_address": self._node_info.ip_address,
            "is_joined": self._joined,
            "heartbeat_interval": self._heartbeat_interval,
            "capabilities": self._node_info.capabilities,
        }

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local IP address (best effort)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
