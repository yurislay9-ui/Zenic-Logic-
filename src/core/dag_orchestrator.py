"""
TITAN OMNISCALE X - TitanAgent (F1) + DAG Orchestrator v16

Thin facade: all implementation lives in src.core.dag_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - dag_parts.definition:  DAGNode dataclass, PIPELINE_DAG, constants
  - dag_parts.titan_agent: TitanAgent class (F1 meta-router)
  - dag_parts.node_executors:  NodeExecutorsMixin (first 10 _exec_* methods)
  - dag_parts.node_executors2: NodeExecutors2Mixin (remaining 9 _exec_* methods)
  - dag_parts.corrections: CorrectionsMixin (_apply_f5_corrections, generate_fractal_app)
  - dag_parts.orchestrator:  DAGOrchestrator class (inherits all mixins)
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
