"""
Zenic-Logic v18 — Core Engine Package.

This package contains the entire AI pipeline: orchestrators, agents,
memory, reasoning, code generation, and all supporting infrastructure.

Key entry points:
    - DAGOrchestrator: Primary orchestrator (DAG-based pipeline)
    - TitanOrchestrator: Deprecated facade → DAGOrchestrator
    - BaseOrchestrator: Shared base class for both orchestrators

Sub-packages:
    core.shared       — Contracts, ResponseSynthesizer, ConversationState, ReferenceResolver
    core.dag_parts    — DAG pipeline decomposition (DAGNode, TitanAgent, node executors)
    core.orch_base_parts — BaseOrchestrator decomposition (InitMixin, APIMixin, etc.)
    core.agents       — Agent framework (SurgicalAgent, ContextAgent, CodeAgent, etc.)
    core.memory_parts — SmartMemory decomposition (CacheMixin, LongTermMixin, etc.)
    core.model_mgr_parts — ModelManager (hybrid lazy loading for SemanticEngine + MiniAI)
    core.shared.z3_parts — Z3 solver decomposition
    core.shared.governor_parts — ResourceGovernor decomposition
    core.shared.sandbox_parts — SandboxIsolationManager decomposition

Lazy imports are used for heavy modules (DAGOrchestrator, patterns) to
keep startup time fast on resource-constrained ARM/Termux environments.
"""

__all__ = []


def __getattr__(name):
    """Lazy import for heavy sub-modules."""
    if name == "DAGOrchestrator":
        from src.core.dag_orchestrator import DAGOrchestrator
        return DAGOrchestrator
    if name == "patterns":
        from src.core import patterns
        return patterns
    raise AttributeError(f"module 'src.core' has no attribute {name!r}")
