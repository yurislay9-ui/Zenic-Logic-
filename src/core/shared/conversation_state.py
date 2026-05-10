"""
TITAN OMNISCALE X - ConversationState

Tracks the state of a multi-turn conversation so that follow-up messages
like "haz lo mismo en Kotlin" can be resolved to concrete values from
the previous interaction.

This is the missing piece that connects:
  Working Memory (stores what happened) → SurgicalAgent (needs to know context)

Without ConversationState, every request is treated in isolation and
anaphoric references like "lo mismo", "otro", "ahora en Go" are lost.

Design principles:
  - Lightweight: only stores the last interaction's key fields
  - Thread-safe: uses a lock for concurrent access
  - Auto-expiring: stale state (>5 min) is ignored
  - Zero-dependency: no LLM calls, pure data structure
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# State is considered stale after 5 minutes of inactivity
_STATE_TTL_SECONDS = 300.0


@dataclass
class ConversationState:
    """Snapshot of the last successful interaction's key metadata.

    This dataclass is persisted across DAG execute() calls so that
    follow-up messages can inherit context from the previous turn.

    Fields:
        last_operation:  The operation performed (CREATE, REFACTOR, etc.)
        last_target:     The target component/file (e.g. "login", "auth.py")
        last_language:   The language used (e.g. "python", "kotlin")
        last_goal:       The goal (FEATURE_ADD, BUG_FIX, etc.)
        last_template:   The template type (api, web, cli, etc.)
        last_criticality:The criticality level (1=low, 2=mod, 3=high)
        last_query:      The user's original message (truncated)
        turn_count:      How many interactions in this conversation
        timestamp:       When this state was last updated
    """
    last_operation: str = ""
    last_target: str = ""
    last_language: str = ""
    last_goal: str = ""
    last_template: str = ""
    last_criticality: int = 0
    last_query: str = ""
    turn_count: int = 0
    timestamp: float = 0.0

    def is_fresh(self, max_age: float = _STATE_TTL_SECONDS) -> bool:
        """Check if the state is still relevant (not stale)."""
        if self.timestamp == 0.0:
            return False
        return (time.time() - self.timestamp) < max_age

    def has_context(self) -> bool:
        """Check if there's useful context to inherit from."""
        return bool(self.last_operation or self.last_target or self.last_language)

    def update_from_intent(self, operation: str, target: str, language: str,
                           goal: str = "", template: str = "",
                           criticality: int = 0, query: str = "") -> None:
        """Update state from a completed intent classification.

        Only called after a SUCCESSFUL pipeline execution, so that
        follow-up messages can reference what was just completed.
        """
        self.last_operation = operation
        self.last_target = target
        self.last_language = language
        self.last_goal = goal
        self.last_template = template
        self.last_criticality = criticality
        self.last_query = query[:200]  # Truncate to avoid memory bloat
        self.turn_count += 1
        self.timestamp = time.time()

    def clear(self) -> None:
        """Reset all state (e.g. on explicit new conversation)."""
        self.last_operation = ""
        self.last_target = ""
        self.last_language = ""
        self.last_goal = ""
        self.last_template = ""
        self.last_criticality = 0
        self.last_query = ""
        self.turn_count = 0
        self.timestamp = 0.0

    def to_context_string(self) -> str:
        """Serialize to a compact string suitable for SurgicalAgent context.

        Format: "prev: CREATE/login/python (FEATURE_ADD, turn=2)"
        This string is passed as the `context` parameter to
        SurgicalAgent.classify_with_runner() so the LLM knows
        what the user was just working on.
        """
        if not self.has_context():
            return ""
        parts = []
        if self.last_operation:
            parts.append(self.last_operation)
        if self.last_target:
            parts.append(self.last_target)
        if self.last_language:
            parts.append(self.last_language)
        core = "/".join(parts)
        extras = []
        if self.last_goal:
            extras.append(self.last_goal)
        extras.append(f"turn={self.turn_count}")
        return f"prev: {core} ({', '.join(extras)})"


class ConversationStateManager:
    """Thread-safe manager for ConversationState per client+tenant.

    The DAGOrchestrator holds one instance of this manager. Each
    request provides client_id + tenant_id, and the manager returns
    the appropriate ConversationState.

    This enables multi-client isolation: two different Cline sessions
    talking to the same server won't cross their conversation states.
    """

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(client_id: str, tenant_id: str) -> str:
        return f"{client_id}:{tenant_id}"

    def get_state(self, client_id: str = "default",
                  tenant_id: str = "__anonymous__") -> ConversationState:
        """Get the ConversationState for a given client+tenant.

        Returns a fresh state if none exists yet.
        """
        k = self._key(client_id, tenant_id)
        with self._lock:
            if k not in self._states:
                self._states[k] = ConversationState()
            return self._states[k]

    def update_state(self, client_id: str, tenant_id: str,
                     **kwargs) -> None:
        """Update the ConversationState for a given client+tenant."""
        state = self.get_state(client_id, tenant_id)
        state.update_from_intent(**kwargs)

    def clear_state(self, client_id: str = "default",
                    tenant_id: str = "__anonymous__") -> None:
        """Clear the ConversationState for a given client+tenant."""
        k = self._key(client_id, tenant_id)
        with self._lock:
            if k in self._states:
                self._states[k].clear()

    def cleanup_stale(self, max_age: float = _STATE_TTL_SECONDS) -> int:
        """Remove all states that have expired. Returns count removed."""
        removed = 0
        with self._lock:
            stale_keys = [
                k for k, s in self._states.items()
                if s.timestamp > 0 and not s.is_fresh(max_age)
            ]
            for k in stale_keys:
                del self._states[k]
                removed += 1
        if removed:
            logger.debug("ConversationStateManager: cleaned %d stale states", removed)
        return removed
