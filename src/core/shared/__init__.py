"""
src.core.shared — Shared utilities, contracts, and cross-cutting concerns.

This package provides the foundational data types, response synthesis,
conversation tracking, reference resolution, and sandbox isolation that
all orchestrators and agents depend on.

Re-exports all public symbols for convenient access:
    from src.core.shared import ResponseSynthesizer, ConversationState
"""

# ── Data contracts (types, payloads, solvers) ──────────────────────
from .contracts import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
    IntentPayload, RoutingPayload, PlanStep, ExecutionPlan,
    SandboxResult, MerkleNode, ChatMessage, ChatRequest,
    MCTSNode, MCTSPlanner, ConstraintSolver, Constraint,
    TimeoutEnforcer, CodeConstraintBuilder, Z3Solver, HAS_Z3,
    SymbolicExecutor, KPathAnalyzer,
    criticality_to_int, criticality_to_path, criticality_to_str,
    CRITICALITY_INT_TO_STR, CRITICALITY_INT_TO_PATH,
    CRITICALITY_STR_TO_INT, CRITICALITY_PATH_TO_INT,
)

# ── Response synthesis (single source of truth for pipeline results) ──
from .response_synthesizer import ResponseSynthesizer

# ── Conversation tracking (multi-turn reference resolution) ────────
from .conversation_state import ConversationState, ConversationStateManager

# ── Reference resolution (anaphora / ellipsis) ─────────────────────
from .reference_resolver import resolve_references

# ── Sandbox isolation ──────────────────────────────────────────────
from .sandbox_isolation import (
    SandboxWorkspace, SandboxIsolationManager,
    get_isolation_manager, shutdown_isolation,
    create_sandbox_builtins, create_sandbox_globals,
)

# ── Version ────────────────────────────────────────────────────────
from ._version import TITAN_VERSION, TITAN_VERSION_STR, TITAN_FULL_NAME

__all__ = [
    # From contracts
    "OperationType", "GoalType", "CriticalityLevel", "RoutePath",
    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest",
    "MCTSNode", "MCTSPlanner", "ConstraintSolver", "Constraint",
    "TimeoutEnforcer", "CodeConstraintBuilder", "Z3Solver", "HAS_Z3",
    "SymbolicExecutor", "KPathAnalyzer",
    "criticality_to_int", "criticality_to_path", "criticality_to_str",
    "CRITICALITY_INT_TO_STR", "CRITICALITY_INT_TO_PATH",
    "CRITICALITY_STR_TO_INT", "CRITICALITY_PATH_TO_INT",
    # From response_synthesizer
    "ResponseSynthesizer",
    # From conversation_state
    "ConversationState", "ConversationStateManager",
    # From reference_resolver
    "resolve_references",
    # From sandbox_isolation
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
    # From _version
    "TITAN_VERSION", "TITAN_VERSION_STR", "TITAN_FULL_NAME",
]
