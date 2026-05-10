"""
dag_orchestrator — Thin facade re-exporting DAGOrchestrator and DAG components.

This module exists for backward compatibility:
    from src.core.dag_orchestrator import DAGOrchestrator

All implementation lives in src.core.dag_parts sub-modules:
  - dag_parts.definition:  DAGNode dataclass, PIPELINE_DAG, constants
  - dag_parts.titan_agent: TitanAgent class (F1 meta-router)
  - dag_parts.node_executors:  NodeExecutorsMixin (first 12 _exec_* methods)
  - dag_parts.node_executors2: NodeExecutors2Mixin (remaining 9 _exec_* methods)
  - dag_parts.corrections: CorrectionsMixin (_apply_f5_corrections, generate_fractal_app)
  - dag_parts.orchestrator:  DAGOrchestrator class (inherits all mixins)

Usage:
    # Primary orchestrator (no VerdictEngine):
    orch = DAGOrchestrator()

    # With VerdictEngine (v17 verdict arbitration):
    from src.core.verdict_engine_module import VerdictEngine
    verdict = VerdictEngine(mini_ai=ai, semantic_engine=se, smart_memory=mem)
    orch = DAGOrchestrator(verdict_engine=verdict)
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
from src.core.dag_parts.orchestrator import DAGOrchestrator

__all__ = [
    "DAGNode",
    "PIPELINE_DAG",
    "MAX_MEMORY_SNIPPET_LEN",
    "SANDBOX_TTL_MULTIPLIER",
    "SANDBOX_TTL_MIN",
    "MAX_CODE_SNIPPET_LEN",
    "TitanAgent",
    "DAGOrchestrator",
]
