"""
ZENIC LOGIC v18 - Orchestrator (Unified Architecture)

DEPRECATED: TitanOrchestrator is now a thin wrapper around DAGOrchestrator.
All pipeline execution is delegated to DAGOrchestrator with VerdictEngine
enabled, achieving full architectural unification.

Migration guide (recommended):
    # Before (v17):
    orch = TitanOrchestrator()
    # After (v18 — direct):
    from src.core.dag_orchestrator import DAGOrchestrator
    from src.core.verdict_engine_module import VerdictEngine
    verdict = VerdictEngine(mini_ai=ai, semantic_engine=se, smart_memory=mem)
    orch = DAGOrchestrator(verdict_engine=verdict)

    # After (v18 — drop-in replacement, same as before):
    orch = TitanOrchestrator()  # internally creates DAGOrchestrator+VerdictEngine

This class is kept for backward compatibility. It creates a DAGOrchestrator
with VerdictEngine and delegates all execute() calls to it.

Architecture v18:
  - DAGOrchestrator: Primary orchestrator (DAG pipeline + optional VerdictEngine)
  - TitanOrchestrator: Backward-compatible facade → DAGOrchestrator(verdict_engine=...)
  - Both share BaseOrchestrator (init, API, backward-compat)
  - Both use ResponseSynthesizer for pipeline results
  - Both use ConversationState + ReferenceResolver for multi-turn
"""

import logging
from typing import Dict, Any

from src.core.dag_parts.orchestrator import DAGOrchestrator

logger = logging.getLogger(__name__)


class TitanOrchestrator:
    """
    Backward-compatible facade that delegates to DAGOrchestrator.

    Creates a DAGOrchestrator with VerdictEngine enabled (v17 behavior)
    and delegates all pipeline execution to it.

    This ensures that both orchestrators follow the exact same code path,
    eliminating duplication and drift.
    """

    def __init__(self) -> None:
        import warnings
        warnings.warn(
            "TitanOrchestrator is deprecated. Use DAGOrchestrator(verdict_engine=...) instead. "
            "See TitanOrchestrator docstring for migration guide.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Create VerdictEngine for v17 verdict arbitration
        verdict_engine = None
        try:
            from src.core.semantic_engine import SemanticEngine
            from src.core.mini_ai_engine import MiniAIEngine
            from src.core.smart_memory import SmartMemory
            from src.core.verdict_engine_module import VerdictEngine

            semantic = SemanticEngine(auto_load=True)
            ai = MiniAIEngine(auto_load=True)
            memory = SmartMemory(semantic_engine=semantic)
            verdict_engine = VerdictEngine(
                mini_ai=ai,
                semantic_engine=semantic,
                smart_memory=memory,
            )
            logger.info("TitanOrchestrator: VerdictEngine created for DAGOrchestrator delegation")
        except Exception as e:
            logger.warning(
                "TitanOrchestrator: VerdictEngine creation failed (%s). "
                "Falling back to DAGOrchestrator without VerdictEngine.", e,
            )

        # Delegate to DAGOrchestrator with VerdictEngine
        self._dag_orchestrator = DAGOrchestrator(verdict_engine=verdict_engine)

        # Re-expose key attributes for backward compatibility
        # Code that accesses orchestrator._memory, orchestrator._ai, etc.
        # will find them on the underlying DAGOrchestrator instance.
        self._memory = self._dag_orchestrator._memory
        self._semantic = self._dag_orchestrator._semantic
        self._ai = self._dag_orchestrator._ai
        self._model_mgr = self._dag_orchestrator._model_mgr
        self._agent_runner = self._dag_orchestrator._agent_runner
        self._surgical_agent = self._dag_orchestrator._surgical_agent
        self._conversation_mgr = self._dag_orchestrator._conversation_mgr
        self._verdict_engine = self._dag_orchestrator._verdict_engine

        logger.info(
            "TitanOrchestrator: Delegating to DAGOrchestrator (verdict=%s)",
            "ACTIVE" if verdict_engine else "SKIP",
        )

    async def execute(
        self,
        msg: str,
        client_id: str = "default",
        **kwargs,
    ) -> Dict[str, Any]:
        """Delegate pipeline execution to DAGOrchestrator.

        All multi-turn context (ConversationState, ReferenceResolver),
        VerdictEngine arbitration, and ResponseSynthesizer formatting
        are handled by the DAG pipeline.
        """
        return await self._dag_orchestrator.execute(
            msg=msg, client_id=client_id, **kwargs,
        )

    # ── Attribute proxy for backward compatibility ──────────────
    # Any attribute not found on TitanOrchestrator is looked up on
    # the underlying DAGOrchestrator. This ensures that code like
    # `orchestrator.router`, `orchestrator.cache`, etc. still works.

    def __getattr__(self, name: str) -> Any:
        """Proxy unknown attributes to the underlying DAGOrchestrator."""
        if name.startswith('_') or name == '_dag_orchestrator':
            raise AttributeError(name)
        dag = object.__getattribute__(self, '_dag_orchestrator')
        return getattr(dag, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Proxy attribute writes to the underlying DAGOrchestrator
        for DAG-internal attributes, keep on self for facade attributes."""
        if name in ('_dag_orchestrator', '_memory', '_semantic', '_ai',
                     '_model_mgr', '_agent_runner', '_surgical_agent',
                     '_conversation_mgr', '_verdict_engine'):
            object.__setattr__(self, name, value)
        else:
            try:
                dag = object.__getattribute__(self, '_dag_orchestrator')
                setattr(dag, name, value)
            except AttributeError:
                object.__setattr__(self, name, value)

    # ── Public API delegation ───────────────────────────────────

    def set_client_id(self, client_id: str) -> None:
        """Set the client_id for multi-client isolation."""
        self._dag_orchestrator.set_client_id(client_id)

    def set_tenant_context(self, tenant_ctx) -> None:
        """Set the TenantContext for multi-tenant isolation."""
        self._dag_orchestrator.set_tenant_context(tenant_ctx)

    async def get_system_status(self) -> Dict[str, Any]:
        """Get complete system status."""
        return await self._dag_orchestrator.get_system_status()

    async def get_intelligence_status(self) -> Dict[str, Any]:
        """Get intelligence subsystem status."""
        return await self._dag_orchestrator.get_intelligence_status()
