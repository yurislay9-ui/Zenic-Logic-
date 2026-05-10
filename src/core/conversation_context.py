"""
ConversationContext — Persistent multi-turn conversation via SmartMemory.

Problem: The system treats each request independently. When a user says
"add a login endpoint", then "now add rate limiting", the system doesn't
remember the first request. Each turn starts from scratch.

Solution: ConversationContext uses SmartMemory's 6 stores to:
  1. Maintain conversation history (EpisodicMemory)
  2. Track project state across turns (ProjectMemory)
  3. Learn successful patterns (ProceduralMemory)
  4. Provide context for the next generation request

M7 Implementation: Works with SmartMemory's SQLite backend on Termux/Android.
No external APIs needed — all local.
"""

import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Maximum context entries to include in a prompt
MAX_CONTEXT_ENTRIES = 10
# Maximum characters per context snippet
MAX_SNIPPET_LEN = 500


@dataclass
class ConversationTurn:
    """A single conversation turn."""
    turn_id: int
    user_message: str
    system_response: str = ""
    intent_op: str = ""
    intent_goal: str = ""
    code_generated: str = ""
    status: str = ""  # SUCCESS, REJECTED, NO_OP, CACHED
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationContext:
    """Manage persistent conversation context using SmartMemory.

    Integrates with SmartMemory's stores:
    - EpisodicMemory: conversation history
    - ProjectMemory: project state across turns
    - ProceduralMemory: learned patterns
    - WorkingMemory: current task context
    - LongTermMemory: successful solutions
    - SemanticCache: avoid recomputation
    """

    def __init__(self, smart_memory=None, session_id: str = ""):
        """
        Args:
            smart_memory: SmartMemory instance
            session_id: Optional session identifier
        """
        self._memory = smart_memory
        self._session_id = session_id or f"session_{int(time.time())}"
        self._turn_counter = 0

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def add_turn(self, user_message: str, response: Dict[str, Any]) -> ConversationTurn:
        """Record a conversation turn in memory.

        Args:
            user_message: The user's message
            response: The system's response dict

        Returns:
            ConversationTurn with assigned turn_id
        """
        self._turn_counter += 1

        turn = ConversationTurn(
            turn_id=self._turn_counter,
            user_message=user_message,
            system_response=response.get("status", ""),
            intent_op=response.get("operation", ""),
            intent_goal=response.get("goal", ""),
            code_generated=(response.get("code", "") or "")[:MAX_SNIPPET_LEN],
            status=response.get("status", ""),
            timestamp=time.time(),
            metadata={
                "route": response.get("route", ""),
                "verdict": response.get("verdict", ""),
                "processing_time_ms": response.get("processing_time_ms", 0),
                "solver_status": response.get("solver_status", ""),
            },
        )

        # Save to SmartMemory stores
        if self._memory:
            self._save_to_memory(turn)

        return turn

    def get_context(self, current_message: str = "",
                     max_entries: int = MAX_CONTEXT_ENTRIES) -> Dict[str, Any]:
        """Get conversation context for the current request.

        Returns a dict with:
        - history: recent conversation turns
        - project_state: current project information
        - learned_patterns: relevant procedural memory
        - relevant_solutions: relevant long-term memory

        Args:
            current_message: The current user message (for relevance scoring)
            max_entries: Maximum number of context entries

        Returns:
            Context dict for injection into the pipeline
        """
        context = {
            "session_id": self._session_id,
            "turn_count": self._turn_counter,
            "history": [],
            "project_state": {},
            "learned_patterns": [],
            "relevant_solutions": [],
        }

        if not self._memory:
            return context

        # 1. Get recent conversation history from EpisodicMemory
        try:
            episodes = self._memory.recall_episodes(
                event_type="conversation_turn",
                limit=max_entries,
            )
            if episodes:
                context["history"] = [
                    {
                        "message": ep.get("description", "")[:MAX_SNIPPET_LEN],
                        "outcome": ep.get("outcome", ""),
                        "importance": ep.get("importance", 0.5),
                    }
                    for ep in episodes[:max_entries]
                ]
        except Exception as e:
            logger.debug(f"Failed to recall episodes: {e}")

        # 2. Get project state from ProjectMemory
        try:
            projects = self._memory.list_projects()
            if projects:
                # Get the most recent project
                latest = projects[0] if projects else {}
                context["project_state"] = {
                    "name": latest.get("name", ""),
                    "type": latest.get("type", ""),
                    "entities": latest.get("entities", []),
                    "endpoints": latest.get("endpoints", []),
                    "status": latest.get("status", ""),
                }
        except Exception as e:
            logger.debug(f"Failed to get project state: {e}")

        # 3. Get learned patterns from ProceduralMemory
        try:
            patterns = self._memory.recall_patterns(
                pattern_type="generation",
                limit=5,
            )
            if patterns:
                context["learned_patterns"] = [
                    {
                        "name": p.get("pattern_name", ""),
                        "steps": p.get("steps", []),
                        "success_rate": p.get("success_rate", 0.0),
                    }
                    for p in patterns[:5]
                ]
        except Exception as e:
            logger.debug(f"Failed to recall patterns: {e}")

        # 4. Get relevant solutions from LongTermMemory
        if current_message:
            try:
                solutions = self._memory.search_long_term(
                    query=current_message,
                    limit=3,
                )
                if solutions:
                    context["relevant_solutions"] = [
                        {
                            "query": s.get("query", "")[:200],
                            "solution": s.get("solution", "")[:MAX_SNIPPET_LEN],
                            "importance": s.get("importance", 0.5),
                        }
                        for s in solutions[:3]
                    ]
            except Exception as e:
                logger.debug(f"Failed to search long-term memory: {e}")

        return context

    def build_context_prompt(self, current_message: str) -> str:
        """Build a context string to prepend to the current message.

        This injects conversation history, project state, and learned
        patterns into the user's message so the pipeline can use them.

        Args:
            current_message: The current user message

        Returns:
            Enhanced message with context prefix
        """
        ctx = self.get_context(current_message)

        if not ctx["history"] and not ctx["project_state"]:
            return current_message  # No context to add

        parts = []

        # Add project state
        if ctx["project_state"] and ctx["project_state"].get("name"):
            ps = ctx["project_state"]
            parts.append(
                f"[PROJECT CONTEXT: {ps['name']} ({ps['type']}) "
                f"with entities {ps.get('entities', [])}]"
            )

        # Add recent history
        if ctx["history"]:
            recent = ctx["history"][-3:]  # Last 3 turns
            for h in recent:
                msg = h.get("message", "")
                outcome = h.get("outcome", "")
                if msg:
                    parts.append(f"[PREVIOUS: {msg[:100]} → {outcome}]")

        # Add learned patterns
        if ctx["learned_patterns"]:
            for p in ctx["learned_patterns"][:2]:
                if p.get("success_rate", 0) > 0.7:
                    parts.append(f"[LEARNED: {p['name']} works well]")

        if not parts:
            return current_message

        context_prefix = " ".join(parts)
        return f"{context_prefix}\n{current_message}"

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session.

        Returns:
            Session summary dict
        """
        return {
            "session_id": self._session_id,
            "turn_count": self._turn_counter,
            "has_memory": self._memory is not None,
        }

    # ================================================================
    #  INTERNAL
    # ================================================================

    def _save_to_memory(self, turn: ConversationTurn):
        """Save a conversation turn to SmartMemory stores."""
        if not self._memory:
            return

        # Save to EpisodicMemory (conversation history)
        try:
            importance = 0.5
            if turn.status == "SUCCESS":
                importance = 0.7
            elif turn.status == "REJECTED":
                importance = 0.3

            self._memory.save_episode(
                event_type="conversation_turn",
                description=f"Turn {turn.turn_id}: {turn.user_message[:200]}",
                context=self._session_id,
                outcome=turn.status,
                importance=importance,
            )
        except Exception as e:
            logger.debug(f"Failed to save episode: {e}")

        # Save code to WorkingMemory (current task context)
        if turn.code_generated:
            try:
                self._memory.add_working(
                    query=turn.user_message[:200],
                    response=turn.code_generated[:MAX_SNIPPET_LEN],
                    operation=turn.intent_op,
                    goal=turn.intent_goal,
                    importance=0.6,
                )
            except Exception as e:
                logger.debug(f"Failed to save working memory: {e}")

        # Learn from successful generations
        if turn.status == "SUCCESS" and turn.intent_op:
            try:
                self._memory.learn_pattern(
                    pattern_name=f"{turn.intent_op}_{turn.intent_goal}",
                    pattern_type="generation",
                    description=f"Generated code for {turn.intent_op}/{turn.intent_goal}",
                    steps=[
                        f"User: {turn.user_message[:100]}",
                        f"Result: {turn.status}",
                    ],
                    success=True,
                )
            except Exception as e:
                logger.debug(f"Failed to learn pattern: {e}")

        # Save successful solutions to LongTermMemory
        if turn.status == "SUCCESS" and turn.code_generated:
            try:
                self._memory.save_long_term(
                    query=turn.user_message[:200],
                    solution=turn.code_generated[:MAX_SNIPPET_LEN],
                    category=f"{turn.intent_op}/{turn.intent_goal}",
                    importance=0.8,
                )
            except Exception as e:
                logger.debug(f"Failed to save long-term memory: {e}")
