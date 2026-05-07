"""
dag_parts - Sub-package for the DAG orchestrator modularization.

Re-exports all public symbols for convenient access.
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

# Unified DAG (v16 + v18 merge)
from src.core.dag_parts.unified_definition import (
    UnifiedDAGNode,
    ParallelGroup,
    ExecutionMode,
    UNIFIED_PIPELINE_DAG,
    PARALLEL_GROUPS,
    CODE_PIPELINE,
    CODE_TO_DEFENSIVE,
    BIZ_AGENTS,
    AUTO_PIPELINE,
    REASON_PIPELINE,
    INTENT_TO_CODE_OP,
    INTENT_TO_BIZ_TYPE,
    V16_TO_UNIFIED_NODE_MAP,
    count_unified_nodes,
)
from src.core.dag_parts.unified_orchestrator import UnifiedDAGOrchestrator

__all__ = [
    # DAG v16
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
    # Unified DAG
    "UnifiedDAGNode",
    "ParallelGroup",
    "ExecutionMode",
    "UNIFIED_PIPELINE_DAG",
    "PARALLEL_GROUPS",
    "CODE_PIPELINE",
    "CODE_TO_DEFENSIVE",
    "BIZ_AGENTS",
    "AUTO_PIPELINE",
    "REASON_PIPELINE",
    "INTENT_TO_CODE_OP",
    "INTENT_TO_BIZ_TYPE",
    "V16_TO_UNIFIED_NODE_MAP",
    "count_unified_nodes",
    "UnifiedDAGOrchestrator",
]
