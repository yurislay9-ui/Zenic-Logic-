"""
UnifiedDAGOrchestrator — Merges DAG v16 + Pipeline v18 into a single parallel DAG.

Key improvements over DAGOrchestrator v16:
  - 47+ agent nodes (was 19)
  - Parallel group execution via asyncio.gather (was fully sequential)
  - SharedMemoryBus for ultra-fast inter-agent communication
  - TitanAgent routing cache (OrderedDict, max 100, TTL 5 min)
  - Per-node latency tracking (deque, last 100 per node)
  - Backward compatible with existing DAG v16 nodes

Architecture:
  CACHE_CHECK → BILINGUAL_ROUTE → INTENT_CLASSIFY
  → [ENTITY_EXTRACT ∥ TARGET_RESOLVE]
  → CRITICALITY_SCORE → [MEMORY_COLLECT ∥ SEMANTIC_PREP]
  → RELEVANCE_SCORE → CONTEXT_COMPRESS → CONTEXT_PREFETCH
  → AST_ANALYZE → THEOREM_CACHE → ROUTE → ROUTE_DECISION
  → {CODE_PATH | BIZ_PATH | AUTO_PATH | REASON_PATH}
  → SECURITY_SCAN → SYNTAX_VALIDATE → RISK_CALC → FIX_SUGGEST
  → EVIDENCE_COLLECT → CONSENSUS_RESOLVE → VERDICT
  → SANDBOX → LEDGER_COMMIT/ROLLBACK → THEOREM_SAVE → MEMORY_SAVE → DONE

Usage:
    orch = UnifiedDAGOrchestrator()
    result = await orch.execute("Create a payment module")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict, deque
from typing import Any, Deque, Dict, List, Optional, Tuple

# ── Core imports ──
from src.config.loader import load_settings
from src.core.shared.types import GoalType
from src.core.tenant._context import (
    TenantContext,
    set_current_tenant,
    get_current_tenant,
    clear_current_tenant,
)

# ── DAG v16 base ──
from src.core.dag_parts.orchestrator import DAGOrchestrator
from src.core.dag_parts.definition import PIPELINE_DAG

# ── Unified DAG definition ──
from src.core.dag_parts.unified_definition import (
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
    UnifiedDAGNode,
    ParallelGroup,
    ExecutionMode,
    count_unified_nodes,
)

# ── SharedMemoryBus (graceful import) ──
_bus_cls = None
try:
    from src.core.shared.shared_memory_bus import SharedMemoryBus as _bus_cls
except ImportError:
    _bus_cls = None

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  FALLBACK: In-process SharedMemoryBus
# ═══════════════════════════════════════════════════════════════

class _InProcessSharedMemoryBus:
    """In-process shared memory bus for ultra-fast inter-agent communication.

    Provides a publish/subscribe channel per (sender, recipient) pair with
    topic-based routing.  Falls back to simple dict storage when the
    production SharedMemoryBus is not available.

    Thread-safety: This implementation is designed for single-process
    async usage. For multi-process scenarios, use the production
    SharedMemoryBus from ``src.core.shared.shared_memory_bus``.
    """

    def __init__(self, max_channels: int = 256, max_size: int = 1000) -> None:
        self._channels: Dict[str, Dict[str, Any]] = {}
        self._max_channels = max_channels
        self._max_size = max_size
        self._stats = {"sends": 0, "receives": 0, "drops": 0}

    def send(self, sender: str, recipient: str, topic: str,
             payload: Any) -> None:
        """Publish a message to a channel identified by (sender, recipient, topic)."""
        key = f"{sender}→{recipient}:{topic}"
        if len(self._channels) >= self._max_channels and key not in self._channels:
            # Evict oldest
            self._channels.pop(next(iter(self._channels)), None)
            self._stats["drops"] += 1
        self._channels[key] = payload
        self._stats["sends"] += 1

    def receive(self, recipient: str, sender: str = "*",
                topic: str = "*") -> Optional[Any]:
        """Retrieve the latest payload for a channel.

        If sender or topic is ``"*"``, performs prefix/wildcard match
        and returns the first matching payload.
        """
        if sender == "*" and topic == "*":
            # Return first channel addressed to recipient
            for k, v in self._channels.items():
                # key format: "sender→recipient:topic"
                if f"→{recipient}:" in k:
                    self._stats["receives"] += 1
                    return v
            return None

        if sender != "*" and topic != "*":
            key = f"{sender}→{recipient}:{topic}"
            payload = self._channels.get(key)
            if payload is not None:
                self._stats["receives"] += 1
            return payload

        # Partial wildcard
        prefix = ""
        if sender != "*":
            prefix = f"{sender}→{recipient}"
        else:
            prefix = f"→{recipient}:"

        for k, v in self._channels.items():
            if k.startswith(prefix) or (sender == "*" and f"→{recipient}:" in k):
                self._stats["receives"] += 1
                return v
        return None

    def clear(self, pattern: str = "*") -> int:
        """Clear channels matching a pattern. Returns count of cleared channels."""
        if pattern == "*":
            n = len(self._channels)
            self._channels.clear()
            return n
        to_del = [k for k in self._channels if pattern in k]
        for k in to_del:
            del self._channels[k]
        return len(to_del)

    @property
    def stats(self) -> Dict[str, int]:
        return {**self._stats, "channels": len(self._channels)}


# ═══════════════════════════════════════════════════════════════
#  ROUTING CACHE
# ═══════════════════════════════════════════════════════════════

class _RoutingCache:
    """LRU cache for TitanAgent routing decisions with TTL.

    Avoids redundant LLM calls for similar routing queries within
    the TTL window (default 5 minutes).

    Args:
        max_size: Maximum number of entries.
        ttl_seconds: Time-to-live for each entry in seconds.
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 300.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, str]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[str]:
        """Look up a cached routing decision. Returns None on miss or expiry."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    def put(self, key: str, value: str) -> None:
        """Store a routing decision."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # evict oldest

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1),
        }


# ═══════════════════════════════════════════════════════════════
#  UNIFIED DAG ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

class UnifiedDAGOrchestrator(DAGOrchestrator):
    """Unified DAG Orchestrator — Merges DAG v16 + Pipeline v18.

    Extends DAGOrchestrator with:
      - 47+ agent nodes (was 19 in v16)
      - Parallel group execution (was fully sequential)
      - SharedMemoryBus for inter-agent communication
      - TitanAgent routing cache
      - Per-node latency tracking
      - Backward compatible with existing DAG v16 nodes

    Usage::

        orch = UnifiedDAGOrchestrator()
        result = await orch.execute("Create a payment module")
        report = orch.get_performance_report()
    """

    # ── Version identifier ──
    VERSION = "unified-v1.0"

    def __init__(self) -> None:
        # Initialize the full DAG v16 orchestrator (all v16 methods available)
        super().__init__()

        # ── Unified DAG (replaces v16 pipeline_dag) ──
        self._unified_dag: Dict[str, UnifiedDAGNode] = dict(UNIFIED_PIPELINE_DAG)

        # ── SharedMemoryBus ──
        if _bus_cls is not None:
            self._bus = _bus_cls()
            logger.info("UnifiedDAGOrchestrator: Using production SharedMemoryBus")
        else:
            self._bus = _InProcessSharedMemoryBus()
            logger.info(
                "UnifiedDAGOrchestrator: Using in-process SharedMemoryBus "
                "(production bus not available)"
            )

        # ── Routing cache ──
        self._routing_cache = _RoutingCache(max_size=100, ttl_seconds=300.0)

        # ── Per-node latency tracking ──
        self._node_latencies: Dict[str, Deque[float]] = {}
        for node_name in self._unified_dag:
            self._node_latencies[node_name] = deque(maxlen=100)

        # ── Pipeline v18 agent instances (lazy-initialized on first use) ──
        self._v18_agents: Dict[str, Any] = {}
        self._v18_agents_initialized = False

        # ── Execution statistics ──
        self._unified_stats = {
            "total_executions": 0,
            "parallel_group_executions": 0,
            "routing_cache_hits": 0,
            "v16_fallback_count": 0,
            "v18_agent_count": 0,
        }

        node_counts = count_unified_nodes()
        logger.info(
            f"UnifiedDAGOrchestrator {self.VERSION}: "
            f"{node_counts['total']} nodes across {len(PARALLEL_GROUPS)} parallel groups | "
            f"SharedMemoryBus=ready | RoutingCache=100/5min | "
            f"DAG v16 compat={len(V16_TO_UNIFIED_NODE_MAP)} nodes"
        )

    # ══════════════════════════════════════════════════════════
    #  V18 AGENT LAZY INITIALIZATION
    # ══════════════════════════════════════════════════════════

    def _ensure_v18_agents(self) -> None:
        """Lazily initialize Pipeline v18 agents on first use.

        This avoids importing all agent modules at startup and allows
        the orchestrator to function even if some v18 agents are missing.
        """
        if self._v18_agents_initialized:
            return
        self._v18_agents_initialized = True

        try:
            from src.core.agents_v2.understanding import (
                IntentClassifier, EntityExtractor, TargetResolver,
                CriticalityScorer, BilingualRouter,
            )
            from src.core.agents_v2.memory import (
                MemoryCollector, RelevanceScorer,
                ContextCompressor, ContextPrefetcher,
            )
            from src.core.agents_v2.business import (
                InvoiceProcessor, InventoryManager, CRMPipeline,
                TaskScheduler, ReportGenerator, NotificationDispatcher,
                DataAnalyzer, OperationRouter,
            )
            from src.core.agents_v2.code_ops import (
                CodeGenerator, CodeRefactorer, CodeOptimizer,
                CodeFixer, ProjectScaffolder, DefensiveInjector,
            )
            from src.core.agents_v2.validation import (
                SecurityScanner, SyntaxValidator,
                RiskCalculator, FixSuggester,
            )
            from src.core.agents_v2.automation import (
                TriggerInferrer, ActionInferrer, ScheduleParser,
                ConditionExtractor, AutomationNamer, WorkflowSerializer,
            )
            from src.core.agents_v2.reasoning import (
                ProblemDetector, StepDecomposer, TemplateReasoner,
                ConfidenceEstimator, ConclusionExtractor,
            )
            from src.core.agents_v2.verdict import (
                VerdictEngineV18, EvidenceCollectorV18, ConsensusResolverV18,
            )
            from src.core.agents_v2.resilience import (
                CircuitBreakerManager, BulkheadManager,
                GlobalHealthMonitor, AuditLogger,
            )

            # Shared infrastructure for v18 agents
            ik = dict(
                circuit_breaker_manager=CircuitBreakerManager(),
                bulkhead_manager=BulkheadManager(),
                health_monitor=GlobalHealthMonitor(),
                audit_logger=AuditLogger(),
            )

            # Phase 1: Understanding
            self._v18_agents["BilingualRouter"] = BilingualRouter(**ik)
            self._v18_agents["IntentClassifier"] = IntentClassifier(**ik)
            self._v18_agents["EntityExtractor"] = EntityExtractor(**ik)
            self._v18_agents["TargetResolver"] = TargetResolver(**ik)
            self._v18_agents["CriticalityScorer"] = CriticalityScorer(**ik)

            # Phase 2: Memory/Context
            mc = MemoryCollector(**ik)
            mc.wire(self._memory, self._semantic)
            self._v18_agents["MemoryCollector"] = mc
            self._v18_agents["RelevanceScorer"] = RelevanceScorer(**ik)
            self._v18_agents["ContextCompressor"] = ContextCompressor(**ik)
            cp = ContextPrefetcher(**ik)
            cp.wire(smart_memory=self._memory, semantic_engine=self._semantic)
            self._v18_agents["ContextPrefetcher"] = cp

            # Phase 3: Business
            self._v18_agents["OperationRouter"] = OperationRouter(**ik)
            self._v18_agents["InvoiceProcessor"] = InvoiceProcessor(**ik)
            self._v18_agents["InventoryManager"] = InventoryManager(**ik)
            self._v18_agents["CRMPipeline"] = CRMPipeline(**ik)
            self._v18_agents["TaskScheduler"] = TaskScheduler(**ik)
            self._v18_agents["ReportGenerator"] = ReportGenerator(**ik)
            self._v18_agents["NotificationDispatcher"] = NotificationDispatcher(**ik)
            self._v18_agents["DataAnalyzer"] = DataAnalyzer(**ik)

            # Phase 3: Code
            self._v18_agents["CodeGenerator"] = CodeGenerator(**ik)
            self._v18_agents["CodeRefactorer"] = CodeRefactorer(**ik)
            self._v18_agents["CodeOptimizer"] = CodeOptimizer(**ik)
            self._v18_agents["CodeFixer"] = CodeFixer(**ik)
            self._v18_agents["ProjectScaffolder"] = ProjectScaffolder(**ik)
            self._v18_agents["DefensiveInjector"] = DefensiveInjector(**ik)

            # Phase 4: Validation
            self._v18_agents["SecurityScanner"] = SecurityScanner(**ik)
            self._v18_agents["SyntaxValidator"] = SyntaxValidator(**ik)
            self._v18_agents["RiskCalculator"] = RiskCalculator(**ik)
            self._v18_agents["FixSuggester"] = FixSuggester(**ik)

            # Phase 3: Automation
            self._v18_agents["TriggerInferrer"] = TriggerInferrer(**ik)
            self._v18_agents["ActionInferrer"] = ActionInferrer(**ik)
            self._v18_agents["ScheduleParser"] = ScheduleParser(**ik)
            self._v18_agents["ConditionExtractor"] = ConditionExtractor(**ik)
            self._v18_agents["AutomationNamer"] = AutomationNamer(**ik)
            self._v18_agents["WorkflowSerializer"] = WorkflowSerializer(**ik)

            # Phase 3: Reasoning
            self._v18_agents["ProblemDetector"] = ProblemDetector(**ik)
            self._v18_agents["StepDecomposer"] = StepDecomposer(**ik)
            self._v18_agents["TemplateReasoner"] = TemplateReasoner(**ik)
            self._v18_agents["ConfidenceEstimator"] = ConfidenceEstimator(**ik)
            self._v18_agents["ConclusionExtractor"] = ConclusionExtractor(**ik)

            # Phase 5: Verdict
            self._v18_agents["EvidenceCollectorV18"] = EvidenceCollectorV18(**ik)
            self._v18_agents["ConsensusResolverV18"] = ConsensusResolverV18(**ik)
            self._v18_agents["VerdictEngineV18"] = VerdictEngineV18(
                mini_ai=self._ai, **ik
            )

            self._unified_stats["v18_agent_count"] = len(self._v18_agents)
            logger.info(
                f"UnifiedDAGOrchestrator: {len(self._v18_agents)} v18 agents initialized"
            )

        except ImportError as e:
            logger.warning(
                f"UnifiedDAGOrchestrator: Some v18 agents unavailable: {e}. "
                f"Falling back to v16 executors for those nodes."
            )
        except Exception as e:
            logger.error(
                f"UnifiedDAGOrchestrator: v18 agent init failed: {e}. "
                f"Continuing with v16 fallback."
            )

    def _run_v18_agent(self, agent_name: str, input_data: Any) -> Any:
        """Run a v18 agent and extract data from the result envelope.

        Falls back to None if the agent is not available.
        """
        agent = self._v18_agents.get(agent_name)
        if agent is None:
            logger.debug(f"v18 agent '{agent_name}' not available, skipping")
            return None
        try:
            result = agent.run(input_data)
            if isinstance(result, dict):
                return result.get("data")
            return result
        except Exception as e:
            logger.warning(f"v18 agent '{agent_name}' execution failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════
    #  MAIN EXECUTION ENTRY POINT
    # ══════════════════════════════════════════════════════════

    async def execute(
        self,
        msg: str,
        client_id: str = "default",
        tenant_ctx: Optional[TenantContext] = None,
    ) -> Dict[str, Any]:
        """Execute the unified DAG pipeline.

        Follows the same signature as DAGOrchestrator.execute() for
        backward compatibility, but uses the unified DAG with parallelism.

        Args:
            msg: User message/request.
            client_id: Client identifier for multi-client isolation.
            tenant_ctx: TenantContext for Phase 2 multitenancy.

        Returns:
            Dict with status, code, metrics, and execution details.
        """
        start_time = time.time()

        # Ensure v18 agents are available
        self._ensure_v18_agents()

        # Increment execution counter
        with self._request_count_lock:
            self._request_count += 1
        self._unified_stats["total_executions"] += 1

        # Phase 2: Set TenantContext
        if tenant_ctx is None:
            tenant_ctx = get_current_tenant()
        else:
            set_current_tenant(tenant_ctx)

        # Ensure AI models are loaded (hybrid lazy loading)
        self._semantic = self._model_mgr.semantic_engine
        self._ai = self._model_mgr.mini_ai_engine

        # Propagate tenant_id
        self._memory.set_tenant_id(tenant_ctx.effective_tenant_id)
        self._memory.set_client_id(client_id)
        self._current_client_id = client_id
        self._current_tenant_ctx = tenant_ctx

        if hasattr(self, 'ledger') and self.ledger:
            self.ledger.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'cache') and self.cache:
            self.cache.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'ast_engine') and self.ast_engine:
            self.ast_engine.set_tenant_id(tenant_ctx.effective_tenant_id)

        # Reset context tracking
        if self._context_agent:
            self._context_agent.reset_agent_tracking()

        # Open Design detection
        _od_detection = None
        _is_visual_request = False
        try:
            from src.core.open_design import OpenDesignDetector, get_open_design_config
            od_config = get_open_design_config()
            if od_config.visual_bypass_enabled:
                _od_detection = OpenDesignDetector.detect(
                    messages=[{"role": "user", "content": msg}],
                    headers={},
                    body={},
                )
                _is_visual_request = _od_detection.get("is_visual_request", False)
                if _is_visual_request:
                    logger.info(
                        "OpenDesign: visual request detected — "
                        "bypassing Z3/AC-3 (signals=%s)",
                        _od_detection.get("detection_signals", []),
                    )
                    if self._context_agent and _od_detection.get("has_design_system"):
                        self._context_agent.set_design_system_mode(
                            enabled=True,
                            budget_multiplier=od_config.design_system_budget_multiplier,
                        )
        except ImportError:
            pass
        except Exception as e:
            logger.debug("OpenDesign: detection failed: %s", e)

        # ── Build execution context ──
        ctx: Dict[str, Any] = {
            "msg": msg,
            "client_id": client_id,
            "start_time": start_time,
            "tenant": tenant_ctx.to_pipeline_context()["tenant"],
            "tenant_ctx": tenant_ctx,
            "is_visual_request": _is_visual_request,
            "open_design_detection": _od_detection,
            # Phase 1: Understanding
            "intent": None,
            "intent_output": None,
            "intent_result": None,
            "entity_result": None,
            "target_result": None,
            "criticality_result": None,
            # Phase 2: Context
            "context_output": None,
            "compressed_context": "",
            "token_budget": {},
            "memory_entries": None,
            "scored_entries": None,
            "semantic_prep_result": None,
            # v16 compat
            "ast_analysis": {},
            "routing": None,
            "plan": None,
            "code": "",
            "result_code": "",
            "explanations": [],
            "lang": "python",
            "final_code": "",
            "sandbox_workspace": None,
            "trial": None,
            "node_result": None,
            "iteration_counts": {},
            "validation_output": None,
            "validation_risk_score": 0.0,
            "validation_issues": [],
            "correction_loop": False,
            "correction_count": 0,
            # v18 new
            "execution_path": "",
            "security_result": None,
            "syntax_result": None,
            "risk_result": None,
            "fix_result": None,
            "evidence": None,
            "consensus": None,
            "verdict_result": None,
        }

        # ── Clear shared memory bus for this request ──
        self._bus.clear()

        # ── Execute unified DAG ──
        current_node = "CACHE_CHECK"
        max_total_steps = 35  # More steps for the larger DAG

        for step in range(max_total_steps):
            # Check for terminal node
            if current_node == "DONE" or current_node not in self._unified_dag:
                break

            dag_node = self._unified_dag[current_node]

            # Anti-loop: track iterations per node
            ctx["iteration_counts"][current_node] = (
                ctx["iteration_counts"].get(current_node, 0) + 1
            )
            if ctx["iteration_counts"][current_node] > dag_node.max_retries + 1:
                logger.warning(
                    f"UnifiedDAG: Max iterations reached for {current_node}, forcing DONE"
                )
                break

            # ── Check if this is a parallel group gate ──
            if dag_node.parallel_group and dag_node.exec_method == "_exec_parallel_gate":
                group_name = dag_node.parallel_group
                pg = PARALLEL_GROUPS.get(group_name)
                if pg:
                    current_node = await self._execute_parallel_group(pg, ctx)
                    continue

            # ── Execute node ──
            node_result = await self._execute_node(current_node, ctx)
            ctx["node_result"] = node_result

            # If result signals immediate termination
            if isinstance(node_result, dict) and node_result.get("_dag_done"):
                result = {k: v for k, v in node_result.items() if k != "_dag_done"}
                return result

            # ── Resolve transition ──
            result_key = node_result if isinstance(node_result, str) else "*"
            current_node = self._resolve_unified_transition(
                current_node, result_key, ctx
            )

        # ── Final: Execute DONE node ──
        if current_node == "DONE":
            done_result = await self._exec_done(ctx)
            if isinstance(done_result, dict):
                return done_result
            elapsed = int((time.time() - start_time) * 1000)
            return self._build_response(ctx, "COMPLETED", elapsed)

        elapsed = int((time.time() - start_time) * 1000)
        return self._build_response(ctx, "COMPLETED", elapsed)

    # ══════════════════════════════════════════════════════════
    #  PARALLEL GROUP EXECUTION
    # ══════════════════════════════════════════════════════════

    async def _execute_parallel_group(
        self, group: ParallelGroup, ctx: Dict
    ) -> str:
        """Execute a parallel group of nodes concurrently.

        Uses asyncio.gather() with return_exceptions=True so that
        one node's failure does not crash the others. Results are
        merged into ctx before continuing to the merge node.

        Args:
            group: ParallelGroup definition with nodes and merge target.
            ctx: Pipeline context dict.

        Returns:
            Name of the next node (typically the merge_node).
        """
        self._unified_stats["parallel_group_executions"] += 1
        logger.info(
            f"UnifiedDAG: Executing parallel group '{group.name}' "
            f"with {len(group.nodes)} nodes → merge at '{group.merge_node}'"
        )

        # Build coroutines for each node in the group
        coroutines = []
        for node_name in group.nodes:
            coroutines.append(self._execute_node(node_name, ctx))

        # Execute all concurrently
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*coroutines, return_exceptions=True),
                timeout=group.timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"UnifiedDAG: Parallel group '{group.name}' timed out "
                f"after {group.timeout_ms}ms"
            )
            results = [None] * len(group.nodes)

        # Merge results into ctx
        for i, node_name in enumerate(group.nodes):
            result = results[i]
            if isinstance(result, Exception):
                logger.warning(
                    f"UnifiedDAG: Node '{node_name}' in group '{group.name}' "
                    f"failed: {result}"
                )
                if group.cancel_on_error:
                    logger.warning(
                        f"UnifiedDAG: cancel_on_error=True for group "
                        f"'{group.name}', but other nodes already completed"
                    )
            elif result is not None:
                # Store result in ctx keyed by node name
                ctx[f"_parallel_{node_name}"] = result

                # Also push to shared memory bus
                self._bus.send(
                    sender=node_name,
                    recipient=group.merge_node,
                    topic="result",
                    payload=result,
                )

        # Record latency for group
        group_latency_key = f"_group_{group.name}"
        if group_latency_key not in self._node_latencies:
            self._node_latencies[group_latency_key] = deque(maxlen=100)

        logger.info(
            f"UnifiedDAG: Parallel group '{group.name}' completed, "
            f"merging at '{group.merge_node}'"
        )

        return group.merge_node

    # ══════════════════════════════════════════════════════════
    #  SINGLE NODE EXECUTION
    # ══════════════════════════════════════════════════════════

    async def _execute_node(self, node_name: str, ctx: Dict) -> Any:
        """Execute a single DAG node with timeout and metrics.

        Tries the unified executor first, falls back to v16 executor
        if the unified method is not available.

        Args:
            node_name: Name of the DAG node to execute.
            ctx: Pipeline context dict.

        Returns:
            Node execution result (string or dict).
        """
        dag_node = self._unified_dag.get(node_name)
        if dag_node is None:
            logger.error(f"UnifiedDAG: Unknown node '{node_name}'")
            return "*"

        t_start = time.monotonic()
        timeout_s = dag_node.timeout_ms / 1000.0

        # Try unified executor method first
        exec_method = getattr(self, dag_node.exec_method, None)

        if exec_method is None:
            # Try v16 fallback (e.g., _exec_cache_check from DAGOrchestrator)
            v16_node_name = None
            for v16_name, unified_name in V16_TO_UNIFIED_NODE_MAP.items():
                if unified_name == node_name:
                    v16_node_name = v16_name
                    break

            if v16_node_name and v16_node_name in self._pipeline_dag:
                v16_exec_method_name = self._pipeline_dag[v16_node_name].exec_method
                exec_method = getattr(self, v16_exec_method_name, None)
                if exec_method is not None:
                    self._unified_stats["v16_fallback_count"] += 1
                    logger.debug(
                        f"UnifiedDAG: Using v16 fallback '{v16_exec_method_name}' "
                        f"for unified node '{node_name}'"
                    )

        if exec_method is None:
            logger.warning(
                f"UnifiedDAG: No executor for node '{node_name}' "
                f"(method '{dag_node.exec_method}'), skipping"
            )
            return "*"

        # Execute with timeout
        try:
            result = await asyncio.wait_for(exec_method(ctx), timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                f"UnifiedDAG: Node '{node_name}' timed out after "
                f"{dag_node.timeout_ms}ms"
            )
            result = "timeout"
        except Exception as e:
            logger.error(f"UnifiedDAG: Node '{node_name}' failed: {e}")
            result = "error"

        # Record latency
        elapsed_ms = (time.monotonic() - t_start) * 1000.0
        self._node_latencies[node_name].append(elapsed_ms)

        # Publish to shared memory bus
        if dag_node.requires_memory_bus and isinstance(result, (str, dict)):
            self._bus.send(
                sender=node_name,
                recipient="*",
                topic="result",
                payload=result,
            )

        return result

    # ══════════════════════════════════════════════════════════
    #  TRANSITION RESOLUTION
    # ══════════════════════════════════════════════════════════

    def _resolve_unified_transition(
        self, current_node: str, result_key: str, ctx: Dict
    ) -> str:
        """Resolve the next node in the unified DAG.

        Extends the v16 transition resolution with:
          - Unified DAG transition tables
          - Routing cache for ROUTE_DECISION
          - Visual bypass detection
          - Conditional execution path routing

        Args:
            current_node: Current DAG node name.
            result_key: Result key from node execution.
            ctx: Pipeline context dict.

        Returns:
            Name of the next DAG node.
        """
        dag_node = self._unified_dag.get(current_node)
        if not dag_node:
            return "DONE"

        # ── Open Design visual bypass ──
        if current_node in ("PLAN", "ROUTE_DECISION") and ctx.get("is_visual_request"):
            logger.info("OpenDesign: routing to VISUAL_BYPASS (skipping Z3/AC-3)")
            return "VISUAL_BYPASS"

        # ── Direct transition lookup ──
        if result_key in dag_node.transitions:
            return dag_node.transitions[result_key]
        if "*" in dag_node.transitions:
            return dag_node.transitions["*"]

        # ── ROUTE_DECISION: dynamic routing with cache ──
        if current_node == "ROUTE_DECISION":
            return self._resolve_route(ctx)

        # ── PLAN: dynamic routing (v16 compat) ──
        if current_node == "PLAN":
            return self._resolve_plan_transition(ctx, result_key)

        # ── OP_ROUTE: business routing ──
        if current_node == "OP_ROUTE":
            biz_type = ctx.get("biz_type", "custom")
            if biz_type in dag_node.transitions:
                return dag_node.transitions[biz_type]
            return dag_node.default_next

        # ── Try TitanAgent LLM for dynamic transitions ──
        if current_node in ("INTENT_CLASSIFY", "PLAN", "ROUTE_DECISION"):
            cache_key = self._get_routing_cache_key(ctx)
            cached = self._routing_cache.get(cache_key)
            if cached and cached in self._unified_dag:
                self._unified_stats["routing_cache_hits"] += 1
                return cached

            # Try LLM
            from src.core.agents.schemas import IntentOutput
            titan_ctx = {
                "operation": (
                    ctx.get("intent_output", IntentOutput()).operation
                    if ctx.get("intent_output") else "SEARCH"
                ),
                "goal": (
                    ctx.get("intent_output", IntentOutput()).goal
                    if ctx.get("intent_output") else ""
                ),
                "criticality": (
                    ctx.get("routing").criticality
                    if ctx.get("routing") else "standard"
                ),
                "is_visual_request": ctx.get("is_visual_request", False),
            }

            if self._ai and self._ai.is_loaded:
                try:
                    titan_input = {
                        "current_node": current_node,
                        "result": result_key,
                        "context": titan_ctx,
                    }
                    if hasattr(self, '_agent_runner') and self._agent_runner:
                        llm_result = self._agent_runner.run(
                            self._titan_agent, titan_input
                        )
                    else:
                        llm_result = self._titan_agent.fallback(titan_input)
                    if llm_result and llm_result in self._unified_dag:
                        self._routing_cache.put(cache_key, llm_result)
                        return llm_result
                except Exception as e:
                    logger.debug(f"TitanAgent LLM fallback: {e}")

            # Static fallback
            fallback = self._titan_agent.fallback({
                "current_node": current_node,
                "result": result_key,
                "context": titan_ctx,
            })
            if fallback in self._unified_dag:
                self._routing_cache.put(cache_key, fallback)
                return fallback

        # ── Default ──
        return dag_node.default_next or "DONE"

    # ══════════════════════════════════════════════════════════
    #  ROUTING LOGIC
    # ══════════════════════════════════════════════════════════

    def _resolve_route(self, ctx: Dict) -> str:
        """Resolve which execution path to take (code/biz/auto/reason).

        Uses intent classification, criticality, and message keywords
        to determine the optimal execution path.

        Args:
            ctx: Pipeline context dict with intent and routing info.

        Returns:
            Name of the first node on the selected execution path.
        """
        # Check routing cache first
        cache_key = self._get_routing_cache_key(ctx)
        cached = self._routing_cache.get(cache_key)
        if cached:
            self._unified_stats["routing_cache_hits"] += 1
            return cached

        msg = ctx.get("msg", "").lower()
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        crit_result = ctx.get("criticality_result") or ctx.get("criticality_output")
        routing = ctx.get("routing")

        # Determine operation and goal
        operation = "SEARCH"
        goal = "FEATURE_ADD"
        if intent_result:
            operation = getattr(intent_result, "operation", "SEARCH")
            goal = getattr(intent_result, "goal", "FEATURE_ADD")

        # Check criticality for solver bypass
        crit_level = 2
        crit_path = "standard"
        if crit_result:
            crit_level = getattr(crit_result, "level", 2)
            crit_path = getattr(crit_result, "path", "standard")
        elif routing:
            crit_level = getattr(routing, "criticality", 2)

        # High criticality → SOLVER_VERIFY
        if crit_level >= 3 or crit_path == "high_crit":
            route = "high_crit"
            self._routing_cache.put(cache_key, route)
            return route

        # Visual bypass
        if ctx.get("is_visual_request"):
            route = "visual"
            self._routing_cache.put(cache_key, route)
            return route

        # Automation intent
        if self._is_automation_intent(msg, intent_result):
            route = "auto"
            self._routing_cache.put(cache_key, route)
            return route

        # Reasoning intent
        if self._is_reasoning_intent(msg, intent_result):
            route = "reason"
            self._routing_cache.put(cache_key, route)
            return route

        # Code operations
        if operation in ("CREATE", "OPTIMIZE", "REFACTOR", "DEBUG"):
            route = "code"
            self._routing_cache.put(cache_key, route)
            return route

        # Default: business path
        route = "biz"
        self._routing_cache.put(cache_key, route)
        return route

    def _resolve_plan_transition(self, ctx: Dict, result_key: str) -> str:
        """Resolve PLAN node transitions (v16 compat + unified).

        In the unified DAG, PLAN transitions determine which code
        operation agent to use, or if solver verification is needed.

        Args:
            ctx: Pipeline context dict.
            result_key: Result from PLAN execution.

        Returns:
            Name of the next DAG node.
        """
        from src.core.agents.schemas import CriticalityOutput

        crit_output = ctx.get("criticality_output") or ctx.get("criticality_result")

        if crit_output and isinstance(crit_output, CriticalityOutput):
            path = crit_output.path
            if path == "high_crit":
                return "SOLVER_VERIFY"
            if path == "low_crit":
                # Determine specific code operation
                return self._resolve_code_operation(ctx)

        # Check routing
        routing = ctx.get("routing")
        crit = routing.criticality if routing else 2

        if crit >= 3:
            return "SOLVER_VERIFY"

        # Default: determine code operation
        return self._resolve_code_operation(ctx)

    def _resolve_code_operation(self, ctx: Dict) -> str:
        """Determine which code operation agent to use.

        Args:
            ctx: Pipeline context with intent information.

        Returns:
            Name of the code operation node.
        """
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        operation = "SEARCH"
        if intent_result:
            operation = getattr(intent_result, "operation", "SEARCH")

        code_op = INTENT_TO_CODE_OP.get(operation, "CODE_GENERATE")
        return code_op

    def _get_routing_cache_key(self, ctx: Dict) -> str:
        """Generate a cache key for routing decisions.

        Uses a hash of the message, operation, goal, and criticality
        to create a deterministic key.

        Args:
            ctx: Pipeline context dict.

        Returns:
            SHA-256 hash string for cache lookup.
        """
        msg = ctx.get("msg", "")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        operation = getattr(intent_result, "operation", "SEARCH") if intent_result else "SEARCH"
        goal = getattr(intent_result, "goal", "FEATURE_ADD") if intent_result else "FEATURE_ADD"
        crit = "standard"
        routing = ctx.get("routing")
        if routing:
            crit = str(getattr(routing, "criticality", "standard"))
        is_visual = str(ctx.get("is_visual_request", False))

        key_str = f"{msg}|{operation}|{goal}|{crit}|{is_visual}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    # ══════════════════════════════════════════════════════════
    #  INTENT DETECTION HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _is_automation_intent(message: str, intent_result: Any = None) -> bool:
        """Detect if the user wants an automation/workflow."""
        automation_keywords = [
            "automate", "automation", "workflow", "trigger", "schedule",
            "cron", "webhook", "automatizar", "automatización", "flujo",
            "programar", "tarea programada", "notificación automática",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in automation_keywords):
            return True
        if intent_result and hasattr(intent_result, "goal"):
            if intent_result.goal == "AUTOMATION" or intent_result.goal == GoalType.AUTOMATION:
                return True
        return False

    @staticmethod
    def _is_reasoning_intent(message: str, intent_result: Any = None) -> bool:
        """Detect if the user needs reasoning/problem-solving."""
        reasoning_keywords = [
            "why does", "explain why", "how to solve", "what causes",
            "root cause", "investigate", "troubleshoot", "reasoning",
            "por qué", "como resolver", "causa raíz", "investigar",
            "analyze problem", "problem solve", "decompose",
        ]
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in reasoning_keywords):
            return True
        return False

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 1: Understanding
    # ══════════════════════════════════════════════════════════

    async def _exec_bilingual_route(self, ctx: Dict) -> str:
        """BILINGUAL_ROUTE (A48): Detect language and normalize input."""
        msg = ctx.get("msg", "")
        lang_result = self._run_v18_agent("BilingualRouter", msg)

        if lang_result:
            ctx["detected_lang"] = getattr(lang_result, "lang", "en")
            ctx["bilingual_result"] = lang_result
            # Push to shared memory bus
            self._bus.send("BILINGUAL_ROUTE", "INTENT_CLASSIFY", "lang", lang_result)
        else:
            ctx["detected_lang"] = "en"

        return "*"

    async def _exec_intent_classify(self, ctx: Dict) -> str:
        """INTENT_CLASSIFY (A01): Classify intent via v18 + v16 SurgicalAgent."""
        msg = ctx.get("msg", "")

        # Try v18 IntentClassifier first
        v18_result = self._run_v18_agent("IntentClassifier", msg)
        if v18_result:
            ctx["intent_result"] = v18_result
            # Map to v16-compatible intent_output for downstream
            from src.core.agents_v2.schemas import IntentResult
            if isinstance(v18_result, IntentResult):
                self._bus.send(
                    "INTENT_CLASSIFY", "*", "intent",
                    {"operation": v18_result.operation, "goal": v18_result.goal}
                )

        # Always run v16 SurgicalAgent for backward compat
        intent_output = self._surgical_agent.classify_with_runner(
            self._agent_runner, msg, context=""
        )
        intent = self._surgical_agent.to_intent_payload(
            intent_output, context=msg
        )

        from src.core.agents.surgical_agent import SurgicalAgent
        code_lang, raw_code = SurgicalAgent._extract_code_block(msg)
        if raw_code:
            intent.raw_code = raw_code
            if code_lang:
                intent.language = code_lang

        ctx["intent"] = intent
        ctx["intent_output"] = intent_output
        ctx["lang"] = intent.language
        ctx["code"] = intent.raw_code or ""

        logger.info(
            f"IntentClassify: {intent_output.operation}/{intent_output.goal} "
            f"(source={intent_output.source}, conf={intent_output.confidence:.2f})"
        )
        return "*"

    async def _exec_entity_extract(self, ctx: Dict) -> str:
        """ENTITY_EXTRACT (A02): Extract entities from user message."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("EntityExtractor", msg)
        if result:
            ctx["entity_result"] = result
            self._bus.send("ENTITY_EXTRACT", "CRITICALITY_SCORE", "entities", result)
        return "*"

    async def _exec_target_resolve(self, ctx: Dict) -> str:
        """TARGET_RESOLVE (A03): Resolve target file/scope."""
        msg = ctx.get("msg", "")
        entity_result = ctx.get("entity_result")
        result = self._run_v18_agent("TargetResolver", {
            "entity_result": entity_result,
            "message": msg,
        })
        if result:
            ctx["target_result"] = result
            self._bus.send("TARGET_RESOLVE", "CRITICALITY_SCORE", "target", result)
        return "*"

    async def _exec_criticality_score(self, ctx: Dict) -> str:
        """CRITICALITY_SCORE (A04): Score criticality via v18 + v16."""
        msg = ctx.get("msg", "")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        target_result = ctx.get("target_result")

        # Try v18 CriticalityScorer
        v18_result = self._run_v18_agent("CriticalityScorer", {
            "intent_result": intent_result,
            "target_result": target_result,
            "message": msg,
        })
        if v18_result:
            ctx["criticality_result"] = v18_result
            self._bus.send("CRITICALITY_SCORE", "*", "criticality", v18_result)

        # Also run v16 CriticalityAgent for backward compat
        if self._criticality_agent:
            intent_output = ctx.get("intent_output")
            routing = ctx.get("routing")
            router_crit = routing.criticality if routing else 2
            crit_output = self._criticality_agent.assess_with_runner(
                runner=self._agent_runner,
                intent_output=intent_output,
                message=msg,
                existing_criticality=router_crit,
            )
            ctx["criticality_output"] = crit_output
            ctx["criticality_adjustments"] = crit_output.adjustments

        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 2: Context
    # ══════════════════════════════════════════════════════════

    async def _exec_parallel_gate(self, ctx: Dict) -> str:
        """Parallel gate: this is handled by _execute_parallel_group."""
        return "*"

    async def _exec_memory_collect(self, ctx: Dict) -> str:
        """MEMORY_COLLECT (A05): Collect memory entries."""
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        target_result = ctx.get("target_result")

        result = self._run_v18_agent("MemoryCollector", {
            "intent_result": intent_result,
            "target_result": target_result,
        })
        if result:
            ctx["memory_entries"] = result
            self._bus.send("MEMORY_COLLECT", "RELEVANCE_SCORE", "entries", result)
        return "*"

    async def _exec_semantic_prep(self, ctx: Dict) -> str:
        """SEMANTIC_PREP: Prepare semantic embeddings and similarity indexes."""
        msg = ctx.get("msg", "")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")

        result = None
        if self._semantic and self._semantic.is_loaded:
            try:
                # Generate embeddings for the message
                embedding = self._semantic.encode(msg)
                result = {
                    "embedding": embedding,
                    "intent_operation": (
                        getattr(intent_result, "operation", "SEARCH")
                        if intent_result else "SEARCH"
                    ),
                    "intent_goal": (
                        getattr(intent_result, "goal", "FEATURE_ADD")
                        if intent_result else "FEATURE_ADD"
                    ),
                }
            except Exception as e:
                logger.debug(f"SEMANTIC_PREP: embedding failed: {e}")

        if result:
            ctx["semantic_prep_result"] = result
            self._bus.send("SEMANTIC_PREP", "RELEVANCE_SCORE", "embedding", result)
        return "*"

    async def _exec_relevance_score(self, ctx: Dict) -> str:
        """RELEVANCE_SCORE (A06): Score and rank memory entries."""
        memory_entries = ctx.get("memory_entries")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")

        result = self._run_v18_agent("RelevanceScorer", {
            "memory_entries": memory_entries,
            "intent_result": intent_result,
        })
        if result:
            ctx["scored_entries"] = result
            self._bus.send("RELEVANCE_SCORE", "CONTEXT_COMPRESS", "scored", result)
        return "*"

    async def _exec_context_compress(self, ctx: Dict) -> str:
        """CONTEXT_COMPRESS (A07): Compress context into token budget.

        Also runs v16 ContextAgent for backward compatibility.
        """
        # Try v18 first
        scored_entries = ctx.get("scored_entries")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        operation = getattr(intent_result, "operation", "SEARCH") if intent_result else "SEARCH"
        goal = getattr(intent_result, "goal", "FEATURE_ADD") if intent_result else "FEATURE_ADD"

        v18_result = self._run_v18_agent("ContextCompressor", {
            "scored_entries": scored_entries,
            "operation": operation,
            "goal": goal,
        })

        # Also run v16 ContextAgent for backward compat
        if self._context_agent:
            intent_output = ctx.get("intent_output")
            msg = ctx.get("msg", "")
            context_result = self._context_agent.prepare_context(
                message=msg,
                intent_output=intent_output,
            )
            ctx["context_output"] = context_result
            ctx["compressed_context"] = context_result.compressed_context
            ctx["token_budget"] = context_result.token_budget
        elif v18_result:
            ctx["compressed_context"] = getattr(v18_result, "text", "")
            ctx["token_budget"] = {"total": getattr(v18_result, "budget", 500)}

        return "*"

    async def _exec_context_prefetch(self, ctx: Dict) -> str:
        """CONTEXT_PREFETCH (A08): Prefetch related context entries."""
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        memory_entries = ctx.get("memory_entries")

        result = self._run_v18_agent("ContextPrefetcher", {
            "intent_result": intent_result,
            "memory_entries": memory_entries,
        })
        if result:
            ctx["prefetch_result"] = result
            self._bus.send("CONTEXT_PREFETCH", "AST_ANALYZE", "hints", result)
        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 3: Code Path
    # ══════════════════════════════════════════════════════════

    async def _exec_code_generate(self, ctx: Dict) -> str:
        """CODE_GENERATE (A17): Generate code from requirements."""
        msg = ctx.get("msg", "")
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("CodeGenerator", {
            "requirements": msg,
            "language": lang,
        })
        if v18_result and hasattr(v18_result, "code") and v18_result.code:
            ctx["final_code"] = v18_result.code
            ctx["code"] = v18_result.code
            ctx["execution_path"] = "code:generate"
            self._bus.send("CODE_GENERATE", "DEFENSIVE_INJECT", "code", v18_result.code)
            return "*"

        # Fallback to v16 StepDispatcher
        return await self._exec_steps(ctx)

    async def _exec_code_refactor(self, ctx: Dict) -> str:
        """CODE_REFACTOR (A18): Refactor existing code."""
        code = ctx.get("code", ctx.get("final_code", ""))
        msg = ctx.get("msg", "")
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("CodeRefactorer", {
            "existing_code": code,
            "requirements": msg,
            "language": lang,
        })
        if v18_result and hasattr(v18_result, "code") and v18_result.code:
            ctx["final_code"] = v18_result.code
            ctx["execution_path"] = "code:refactor"
            self._bus.send("CODE_REFACTOR", "DEFENSIVE_INJECT", "code", v18_result.code)
            return "*"

        return await self._exec_steps(ctx)

    async def _exec_code_optimize(self, ctx: Dict) -> str:
        """CODE_OPTIMIZE (A19): Optimize existing code."""
        code = ctx.get("code", ctx.get("final_code", ""))
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("CodeOptimizer", {
            "existing_code": code,
            "language": lang,
        })
        if v18_result and hasattr(v18_result, "code") and v18_result.code:
            ctx["final_code"] = v18_result.code
            ctx["execution_path"] = "code:optimize"
            self._bus.send("CODE_OPTIMIZE", "DEFENSIVE_INJECT", "code", v18_result.code)
            return "*"

        return await self._exec_steps(ctx)

    async def _exec_code_fix(self, ctx: Dict) -> str:
        """CODE_FIX (A20): Fix bugs/issues in code."""
        code = ctx.get("code", ctx.get("final_code", ""))
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("CodeFixer", {
            "existing_code": code,
            "language": lang,
        })
        if v18_result and hasattr(v18_result, "code") and v18_result.code:
            ctx["final_code"] = v18_result.code
            ctx["execution_path"] = "code:fix"
            self._bus.send("CODE_FIX", "DEFENSIVE_INJECT", "code", v18_result.code)
            return "*"

        return await self._exec_steps(ctx)

    async def _exec_code_scaffold(self, ctx: Dict) -> str:
        """CODE_SCAFFOLD (A21): Scaffold a new project."""
        msg = ctx.get("msg", "")
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("ProjectScaffolder", {
            "requirements": msg,
            "language": lang,
        })
        if v18_result:
            ctx["execution_path"] = "code:scaffold"
            if hasattr(v18_result, "files") and v18_result.files:
                # Combine all files into final_code
                combined = "\n\n".join(
                    f"# --- {f.get('path', 'unknown')} ---\n{f.get('content', '')}"
                    for f in v18_result.files
                )
                ctx["final_code"] = combined
                ctx["code"] = combined
            self._bus.send("CODE_SCAFFOLD", "DEFENSIVE_INJECT", "scaffold", v18_result)
            return "*"

        return await self._exec_steps(ctx)

    async def _exec_defensive_inject(self, ctx: Dict) -> str:
        """DEFENSIVE_INJECT (A22): Inject defensive patterns."""
        code = ctx.get("final_code", ctx.get("code", ""))
        lang = ctx.get("lang", "python")
        crit_result = ctx.get("criticality_result") or ctx.get("criticality_output")
        crit_level = getattr(crit_result, "level", 2) if crit_result else 2
        adjustments = getattr(crit_result, "adjustments", {}) if crit_result else {}

        v18_result = self._run_v18_agent("DefensiveInjector", {
            "code": code,
            "language": lang,
            "criticality_level": crit_level,
            "adjustments": adjustments,
        })
        if v18_result and hasattr(v18_result, "code") and v18_result.code:
            ctx["final_code"] = v18_result.code
            ctx["code"] = v18_result.code

        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 3: Business Path
    # ══════════════════════════════════════════════════════════

    async def _exec_op_route(self, ctx: Dict) -> str:
        """OP_ROUTE (A16): Route to business domain agent."""
        msg = ctx.get("msg", "")

        # Infer business type
        biz_type = self._infer_business_type(msg)
        ctx["biz_type"] = biz_type

        v18_result = self._run_v18_agent("OperationRouter", {
            "type": biz_type,
            "data": {"description": msg},
            "context": {},
            "description": msg,
        })

        if v18_result and hasattr(v18_result, "target_agent"):
            ctx["op_route_result"] = v18_result
            # Return the transition key (matches OP_ROUTE transitions)
            agent_key = v18_result.target_agent.replace("A09_", "").replace("A10_", "").replace("A11_", "").replace("A12_", "").replace("A13_", "").replace("A14_", "").replace("A15_", "").lower()
            if agent_key in ("invoiceprocessor",):
                return "invoice"
            elif agent_key in ("inventorymanager",):
                return "inventory"
            elif agent_key in ("crmpipeline",):
                return "crm"
            elif agent_key in ("taskscheduler",):
                return "task"
            elif agent_key in ("reportgenerator",):
                return "report"
            elif agent_key in ("notificationdispatcher",):
                return "notification"
            elif agent_key in ("dataanalyzer",):
                return "analytics"

        return biz_type

    async def _exec_invoice(self, ctx: Dict) -> str:
        """INVOICE (A09): Process invoice."""
        msg = ctx.get("msg", "")
        op_route = ctx.get("op_route_result")
        data = {}
        if op_route and hasattr(op_route, "transformed_input"):
            data = op_route.transformed_input.get("data", {})

        result = self._run_v18_agent("InvoiceProcessor", data or {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:invoice"
        return "*"

    async def _exec_inventory(self, ctx: Dict) -> str:
        """INVENTORY (A10): Manage inventory."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("InventoryManager", {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:inventory"
        return "*"

    async def _exec_crm(self, ctx: Dict) -> str:
        """CRM (A11): Process CRM pipeline."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("CRMPipeline", {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:crm"
        return "*"

    async def _exec_task(self, ctx: Dict) -> str:
        """TASK (A12): Schedule tasks."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("TaskScheduler", {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:task"
        return "*"

    async def _exec_report(self, ctx: Dict) -> str:
        """REPORT (A13): Generate report."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("ReportGenerator", {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:report"
        return "*"

    async def _exec_notification(self, ctx: Dict) -> str:
        """NOTIFICATION (A14): Dispatch notification."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("NotificationDispatcher", {"description": msg})
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:notification"
        return "*"

    async def _exec_analytics(self, ctx: Dict) -> str:
        """ANALYTICS (A15): Compute analytics."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("DataAnalyzer", {
            "data": [msg],
            "metrics": ["count"],
        })
        if result:
            ctx["business_result"] = result
            ctx["execution_path"] = "business:analytics"
        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 3: Automation Path
    # ══════════════════════════════════════════════════════════

    async def _exec_trigger(self, ctx: Dict) -> str:
        """TRIGGER (A29): Infer trigger type."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("TriggerInferrer", msg)
        if result:
            ctx["trigger_result"] = result
            ctx["execution_path"] = "automation"
        return "*"

    async def _exec_action(self, ctx: Dict) -> str:
        """ACTION (A30): Infer action type."""
        msg = ctx.get("msg", "")
        trigger_result = ctx.get("trigger_result")
        result = self._run_v18_agent("ActionInferrer", {
            "description": msg,
            "trigger_type": getattr(trigger_result, "type", "manual") if trigger_result else "manual",
        })
        if result:
            ctx["action_result"] = result
        return "*"

    async def _exec_schedule(self, ctx: Dict) -> str:
        """SCHEDULE (A31): Parse schedule."""
        msg = ctx.get("msg", "")
        trigger_result = ctx.get("trigger_result")
        result = self._run_v18_agent("ScheduleParser", {
            "description": msg,
            "trigger_type": getattr(trigger_result, "type", "manual") if trigger_result else "manual",
        })
        if result:
            ctx["schedule_result"] = result
        return "*"

    async def _exec_condition(self, ctx: Dict) -> str:
        """CONDITION (A32): Extract conditions."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("ConditionExtractor", {"description": msg})
        if result:
            ctx["condition_result"] = result
        return "*"

    async def _exec_auto_name(self, ctx: Dict) -> str:
        """AUTO_NAME (A33): Generate workflow name."""
        msg = ctx.get("msg", "")
        trigger_result = ctx.get("trigger_result")
        action_result = ctx.get("action_result")
        result = self._run_v18_agent("AutomationNamer", {
            "description": msg,
            "trigger_type": getattr(trigger_result, "type", "manual") if trigger_result else "manual",
            "action_type": getattr(action_result, "type", "log") if action_result else "log",
        })
        if result:
            ctx["name_result"] = result
        return "*"

    async def _exec_workflow_serial(self, ctx: Dict) -> str:
        """WORKFLOW_SERIAL (A34): Serialize workflow."""
        trigger_result = ctx.get("trigger_result")
        action_result = ctx.get("action_result")
        schedule_result = ctx.get("schedule_result")
        condition_result = ctx.get("condition_result")
        name_result = ctx.get("name_result")

        result = self._run_v18_agent("WorkflowSerializer", {
            "name": getattr(name_result, "name", "unnamed_workflow") if name_result else "unnamed_workflow",
            "slug": getattr(name_result, "slug", "unnamed_workflow") if name_result else "unnamed_workflow",
            "trigger": trigger_result,
            "action": action_result,
            "schedule": schedule_result,
            "conditions": getattr(condition_result, "conditions", []) if condition_result else [],
        })
        if result:
            ctx["workflow_result"] = result
        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 3: Reasoning Path
    # ══════════════════════════════════════════════════════════

    async def _exec_problem_detect(self, ctx: Dict) -> str:
        """PROBLEM_DETECT (A35): Detect problem type."""
        msg = ctx.get("msg", "")
        result = self._run_v18_agent("ProblemDetector", msg)
        if result:
            ctx["problem_result"] = result
            ctx["execution_path"] = "reasoning"
        return "*"

    async def _exec_step_decompose(self, ctx: Dict) -> str:
        """STEP_DECOMPOSE (A36): Decompose problem into steps."""
        msg = ctx.get("msg", "")
        problem_result = ctx.get("problem_result")
        result = self._run_v18_agent("StepDecomposer", {
            "query": msg,
            "problem_type": getattr(problem_result, "type", "general") if problem_result else "general",
            "complexity": getattr(problem_result, "complexity", 0.5) if problem_result else 0.5,
        })
        if result:
            ctx["steps_result"] = result
        return "*"

    async def _exec_template_reason(self, ctx: Dict) -> str:
        """TEMPLATE_REASON (A37): Apply template reasoning."""
        msg = ctx.get("msg", "")
        problem_result = ctx.get("problem_result")
        steps_result = ctx.get("steps_result")
        result = self._run_v18_agent("TemplateReasoner", {
            "query": msg,
            "problem_type": getattr(problem_result, "type", "general") if problem_result else "general",
            "steps": getattr(steps_result, "steps", []) if steps_result else [],
        })
        if result:
            ctx["reasoning_result"] = result
        return "*"

    async def _exec_confidence(self, ctx: Dict) -> str:
        """CONFIDENCE (A38): Estimate confidence."""
        reasoning_result = ctx.get("reasoning_result")
        problem_result = ctx.get("problem_result")
        result = self._run_v18_agent("ConfidenceEstimator", {
            "reasoning_result": reasoning_result,
            "problem_type": getattr(problem_result, "type", "general") if problem_result else "general",
        })
        if result:
            ctx["confidence_result"] = result
        return "*"

    async def _exec_conclusion(self, ctx: Dict) -> str:
        """CONCLUSION (A39): Extract conclusion."""
        reasoning_result = ctx.get("reasoning_result")
        confidence_result = ctx.get("confidence_result")
        result = self._run_v18_agent("ConclusionExtractor", {
            "reasoning_result": reasoning_result,
            "confidence_score": getattr(confidence_result, "score", 0.0) if confidence_result else 0.0,
        })
        if result:
            ctx["conclusion_result"] = result
        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 4: Validation
    # ══════════════════════════════════════════════════════════

    async def _exec_security_scan(self, ctx: Dict) -> str:
        """SECURITY_SCAN (A23): Scan for security vulnerabilities."""
        code = ctx.get("final_code", ctx.get("code", ""))
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("SecurityScanner", {
            "code": code,
            "language": lang,
        })
        if v18_result:
            ctx["security_result"] = v18_result
        return "*"

    async def _exec_syntax_validate(self, ctx: Dict) -> str:
        """SYNTAX_VALIDATE (A24): Validate syntax.

        Also runs v16 ValidationAgent for backward compatibility.
        """
        code = ctx.get("final_code", ctx.get("code", ""))
        lang = ctx.get("lang", "python")

        v18_result = self._run_v18_agent("SyntaxValidator", {
            "code": code,
            "language": lang,
        })
        if v18_result:
            ctx["syntax_result"] = v18_result

        # Also run v16 VALIDATE for backward compat + correction loops
        if code and code.strip():
            v_out = self._validation_agent.validate_with_runner(
                self._agent_runner,
                target="code",
                content=code,
                rules=["security", "quality"],
                language=lang,
            )
            ctx["validation_output"] = v_out
            ctx["validation_risk_score"] = v_out.risk_score
            ctx["validation_issues"] = v_out.issues

        return "*"

    async def _exec_risk_calc(self, ctx: Dict) -> str:
        """RISK_CALC (A27): Calculate aggregate risk score."""
        security_result = ctx.get("security_result")
        syntax_result = ctx.get("syntax_result")

        v18_result = self._run_v18_agent("RiskCalculator", {
            "security_result": security_result,
            "syntax_result": syntax_result,
        })
        if v18_result:
            ctx["risk_result"] = v18_result
        return "*"

    async def _exec_fix_suggest(self, ctx: Dict) -> str:
        """FIX_SUGGEST (A28): Suggest fixes for detected issues."""
        from src.core.agents_v2.schemas import SecurityResult, SyntaxResult

        all_issues = []
        security_result = ctx.get("security_result")
        syntax_result = ctx.get("syntax_result")

        if security_result and isinstance(security_result, SecurityResult):
            all_issues.extend(security_result.threats)
        if syntax_result and isinstance(syntax_result, SyntaxResult):
            all_issues.extend(syntax_result.errors)

        # Also include v16 validation issues
        v16_issues = ctx.get("validation_issues", [])
        if v16_issues:
            all_issues.extend(v16_issues)

        v18_result = self._run_v18_agent("FixSuggester", {
            "issues": all_issues,
        })
        if v18_result:
            ctx["fix_result"] = v18_result
        return "*"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — Phase 5: Verdict
    # ══════════════════════════════════════════════════════════

    async def _exec_evidence_collect(self, ctx: Dict) -> str:
        """EVIDENCE_COLLECT (A41): Collect evidence for/against."""
        security_result = ctx.get("security_result")
        syntax_result = ctx.get("syntax_result")
        criticality_result = ctx.get("criticality_result") or ctx.get("criticality_output")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")

        v18_result = self._run_v18_agent("EvidenceCollectorV18", {
            "security_result": security_result,
            "syntax_result": syntax_result,
            "criticality_result": criticality_result,
            "intent_result": intent_result,
        })
        if v18_result:
            ctx["evidence"] = v18_result
        return "*"

    async def _exec_consensus_resolve(self, ctx: Dict) -> str:
        """CONSENSUS_RESOLVE (A42): Resolve consensus from evidence."""
        evidence = ctx.get("evidence")

        v18_result = self._run_v18_agent("ConsensusResolverV18", evidence)
        if v18_result:
            ctx["consensus"] = v18_result
        return "*"

    async def _exec_verdict(self, ctx: Dict) -> str:
        """VERDICT (A43): Render final verdict.

        If consensus is unanimous, use deterministic result.
        Otherwise, use AI arbitration via VerdictEngineV18.
        """
        from src.core.agents_v2.schemas import (
            ConsensusResult, VerdictOutput, Verdict,
        )

        consensus = ctx.get("consensus")
        intent_result = ctx.get("intent_result") or ctx.get("intent_output")
        operation = getattr(intent_result, "operation", "SEARCH") if intent_result else "SEARCH"
        goal = getattr(intent_result, "goal", "FEATURE_ADD") if intent_result else "FEATURE_ADD"

        if consensus and isinstance(consensus, ConsensusResult) and consensus.needs_llm:
            v18_result = self._run_v18_agent("VerdictEngineV18", {
                "question": f"Should code for {operation}/{goal} be approved?",
                "consensus_result": consensus,
                "evidence_for": consensus.evidence_for,
                "evidence_against": consensus.evidence_against,
            })
            if v18_result and isinstance(v18_result, VerdictOutput):
                ctx["verdict_result"] = v18_result
                if v18_result.verdict == Verdict.YES:
                    return "approved"
                return "rejected"
        else:
            if consensus and isinstance(consensus, ConsensusResult):
                ctx["verdict_result"] = VerdictOutput(
                    verdict=consensus.verdict,
                    confidence=consensus.confidence,
                    source="deterministic_consensus",
                    llm_used=False,
                )
                if consensus.verdict == Verdict.YES:
                    return "approved"
                return "rejected"

        # Default: approve (optimistic)
        ctx["verdict_result"] = VerdictOutput(
            verdict=Verdict.YES,
            confidence=0.5,
            source="fallback",
            llm_used=False,
        )
        return "approved"

    # ══════════════════════════════════════════════════════════
    #  UNIFIED NODE EXECUTORS — ROUTE_DECISION
    # ══════════════════════════════════════════════════════════

    async def _exec_route_decision(self, ctx: Dict) -> str:
        """ROUTE_DECISION: Decide execution path based on intent + routing.

        This is the central routing hub that determines whether to follow
        the code, business, automation, or reasoning path.
        """
        return self._resolve_route(ctx)

    # ══════════════════════════════════════════════════════════
    #  BUSINESS TYPE INFERENCE
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _infer_business_type(message: str) -> str:
        """Infer business operation type from message keywords."""
        msg_lower = message.lower()
        type_keywords = {
            "invoice": ["invoice", "factura", "billing", "cobro", "pago", "receipt"],
            "inventory": ["inventory", "inventario", "stock", "almacen", "product", "producto"],
            "crm": ["crm", "cliente", "customer", "ventas", "sales", "lead", "pipeline"],
            "task": ["task", "tarea", "scheduling", "calendar", "agenda", "appointment"],
            "report": ["report", "reporte", "informe", "dashboard", "resumen", "summary"],
            "notification": ["notification", "notificacion", "alert", "alerta", "notify", "aviso"],
            "analytics": ["analytics", "analisis", "analysis", "statistics", "stats", "metric"],
        }
        for biz_type, keywords in type_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                return biz_type
        return "custom"

    # ══════════════════════════════════════════════════════════
    #  PERFORMANCE REPORTING
    # ══════════════════════════════════════════════════════════

    def get_performance_report(self) -> Dict[str, Any]:
        """Get detailed performance metrics for all nodes.

        Returns per-node latency statistics (p50, p95, p99, max),
        routing cache stats, shared memory bus stats, and
        execution summary.
        """
        report: Dict[str, Any] = {
            "version": self.VERSION,
            "unified_stats": dict(self._unified_stats),
            "node_count": len(self._unified_dag),
            "parallel_groups": {
                name: {
                    "nodes": pg.nodes,
                    "merge_node": pg.merge_node,
                    "timeout_ms": pg.timeout_ms,
                }
                for name, pg in PARALLEL_GROUPS.items()
            },
            "routing_cache": self._routing_cache.stats,
            "shared_memory_bus": self._bus.stats if hasattr(self._bus, "stats") else {},
            "node_latencies": {},
        }

        for node_name, latencies in self._node_latencies.items():
            if not latencies:
                continue
            sorted_lats = sorted(latencies)
            n = len(sorted_lats)
            report["node_latencies"][node_name] = {
                "count": n,
                "p50_ms": round(sorted_lats[n // 2], 2),
                "p95_ms": round(sorted_lats[int(n * 0.95)], 2) if n >= 20 else None,
                "p99_ms": round(sorted_lats[int(n * 0.99)], 2) if n >= 100 else None,
                "max_ms": round(sorted_lats[-1], 2),
                "avg_ms": round(sum(sorted_lats) / n, 2),
            }

        return report

    # ══════════════════════════════════════════════════════════
    #  SYSTEM STATUS (extends v16)
    # ══════════════════════════════════════════════════════════

    async def get_intelligence_status(self) -> Dict[str, Any]:
        """Get status of the unified intelligence system."""
        base_status = await DAGOrchestrator.get_intelligence_status(self)
        base_status["unified_dag_orchestrator"] = {
            "version": self.VERSION,
            "nodes": len(self._unified_dag),
            "parallel_groups": len(PARALLEL_GROUPS),
            "v18_agents_available": len(self._v18_agents),
            "routing_cache": self._routing_cache.stats,
            "shared_memory_bus": (
                self._bus.stats if hasattr(self._bus, "stats") else {}
            ),
        }
        return base_status

    async def get_system_status(self) -> Dict[str, Any]:
        """Get complete system status including unified DAG info."""
        base_status = await DAGOrchestrator.get_system_status(self)
        base_status["pipeline"] = f"Unified DAG ({self.VERSION})"
        base_status["unified_dag_nodes"] = len(self._unified_dag)
        base_status["parallel_groups"] = len(PARALLEL_GROUPS)
        base_status["v18_agents"] = len(self._v18_agents)
        base_status["routing_cache_hit_rate"] = self._routing_cache.stats.get(
            "hit_rate", 0.0
        )
        return base_status

    # ══════════════════════════════════════════════════════════
    #  BACKWARD COMPATIBILITY
    # ══════════════════════════════════════════════════════════

    @property
    def unified_dag(self) -> Dict[str, UnifiedDAGNode]:
        """Access the unified DAG definition."""
        return self._unified_dag

    @property
    def bus(self):
        """Access the SharedMemoryBus instance."""
        return self._bus

    @property
    def routing_cache(self) -> _RoutingCache:
        """Access the routing cache instance."""
        return self._routing_cache
