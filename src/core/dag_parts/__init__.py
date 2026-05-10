"""
dag_parts — DAG-based Pipeline Sub-package for Zenic-Logic v18.

This sub-package implements the Directed Acyclic Graph (DAG) pipeline that
drives the entire code generation, analysis, and transformation workflow.

Architecture:
    DAGOrchestrator composes multiple mixins via MRO:

        DAGOrchestrator(CorrectionsMixin, NodeExecutors2Mixin,
                        NodeExecutorsMixin, BaseOrchestrator)

    Each mixin provides a focused set of DAG node executor methods (_exec_*),
    keeping the orchestrator class manageable despite 22+ DAG nodes.

Modules:
    definition.py    — DAGNode dataclass, PIPELINE_DAG dict, constants
    titan_agent.py   — TitanAgent (F1 meta-router) — LLM-driven DAG transitions
    node_executors.py — NodeExecutorsMixin (first 12 _exec_* methods)
    node_executors2.py — NodeExecutors2Mixin (remaining 9 _exec_* methods)
    corrections.py   — CorrectionsMixin (_apply_f5_corrections, generate_fractal_app)
    orchestrator.py  — DAGOrchestrator class (inherits all mixins + BaseOrchestrator)

Pipeline Flow (v18):
    CACHE_CHECK → CHAT_DETECT → INTENT → CONTEXT_PREPARE →
    AST_ANALYZE → THEOREM_CACHE → ROUTE → CRITICALITY_ROUTE →
    PLAN → [SOLVER_VERIFY | VISUAL_BYPASS] → EXECUTE_STEPS →
    VALIDATE → [VERDICT] → SANDBOX → [LEDGER_COMMIT | LEDGER_ROLLBACK] →
    THEOREM_SAVE → MEMORY_SAVE → DONE

Key Design Decisions:
    - TitanAgent (F1) provides LLM-driven transition resolution with
      static fallback tables for when the LLM is unavailable
    - ConversationState + ReferenceResolver enable multi-turn context
      (anaphora resolution for "lo mismo", "en Kotlin", etc.)
    - ResponseSynthesizer is the single source of truth for pipeline results
    - VerdictEngine (v17 integration) arbitrates code before sandbox validation
    - Open Design visual requests bypass Z3/AC-3 solver (VISUAL_BYPASS node)

Re-exports all public symbols for convenient access:
    from src.core.dag_parts import DAGOrchestrator, PIPELINE_DAG
"""

from src.core.dag_parts.definition import (
    DAGNode,
    PIPELINE_DAG,
    MAX_MEMORY_SNIPPET_LEN,
    SANDBOX_TTL_MULTIPLIER,
    SANDBOX_TTL_MIN,
    MAX_CODE_SNIPPET_LEN,
)
from src.core.dag_parts.titan_agent import TitanAgent
from src.core.dag_parts.node_executors import NodeExecutorsMixin
from src.core.dag_parts.node_executors2 import NodeExecutors2Mixin
from src.core.dag_parts.corrections import CorrectionsMixin
from src.core.dag_parts.orchestrator import DAGOrchestrator

__all__ = [
    "DAGNode",
    "PIPELINE_DAG",
    "MAX_MEMORY_SNIPPET_LEN",
    "SANDBOX_TTL_MULTIPLIER",
    "SANDBOX_TTL_MIN",
    "MAX_CODE_SNIPPET_LEN",
    "TitanAgent",
    "NodeExecutorsMixin",
    "NodeExecutors2Mixin",
    "CorrectionsMixin",
    "DAGOrchestrator",
]
