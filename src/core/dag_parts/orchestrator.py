"""
DAGOrchestrator - Orquestador basado en DAG.

Orquestador del pipeline de 8 niveles basado en DAG con TitanAgent (F1).
Reemplaza el dispatch estático if/elif de TitanOrchestrator con
un grafo dirigido donde cada nodo es un paso del pipeline y las
transiciones son condicionales.
"""

import os
import time
import logging
from typing import Dict, Any, Optional

from src.config.loader import load_settings
from src.core.tenant._context import (
    TenantContext,
    set_current_tenant,
    get_current_tenant,
    clear_current_tenant,
)

# Base class with shared initialization, public API, backward-compat
from src.core.orchestrator_base import BaseOrchestrator

# Step dispatcher for unified step execution
from src.core.step_dispatcher import StepDispatcher

# 3-Layer AI Architecture - Now via ModelManager for hybrid lazy loading
from src.core.model_manager import init_model_manager
from src.core.smart_memory import SmartMemory

# Agent Framework (F1-F5) - DAG-specific agents
from src.core.agents.schemas import IntentOutput, CriticalityOutput
from src.core.agents.context_agent import ContextAgent
from src.core.agents.criticality_agent import CriticalityAgent
from src.core.agents.code_agent import CodeAgent
from src.core.fractal_generator import FractalGenerator

# DAG sub-modules
from src.core.dag_parts.definition import PIPELINE_DAG
from src.core.dag_parts.titan_agent import TitanAgent
from src.core.dag_parts.node_executors import NodeExecutorsMixin
from src.core.dag_parts.node_executors2 import NodeExecutors2Mixin
from src.core.dag_parts.corrections import CorrectionsMixin

logger = logging.getLogger(__name__)


class DAGOrchestrator(
    CorrectionsMixin,
    NodeExecutors2Mixin,
    NodeExecutorsMixin,
    BaseOrchestrator,
):
    """
    Orquestador del pipeline de 8 niveles basado en DAG con TitanAgent (F1).

    Reemplaza el dispatch estático if/elif de TitanOrchestrator con
    un grafo dirigido donde cada nodo es un paso del pipeline y las
    transiciones son condicionales. TitanAgent decide las transiciones
    no triviales usando el LLM, con fallback a tablas estáticas.

    Inherits from BaseOrchestrator which provides:
    - All shared initialization methods
    - Public API methods (generate_app, build_logic, reason, etc.)
    - Backward-compat delegation methods
    - Shared properties

    DAG-specific additions:
    - DAGNode, TitanAgent, PIPELINE_DAG definitions
    - DAG execution engine (execute method)
    - Node executor methods (_exec_*)
    - F5 correction loop (_apply_f5_corrections)
    - Criticality routing
    - Fractal app generation
    """

    def __init__(self) -> None:
        self._pipeline_dag = dict(PIPELINE_DAG)

        # 1. Common state
        settings = load_settings()
        self._init_common_state()

        # 2. Pipeline components
        self._init_pipeline_components(settings)

        # 3. 3-Layer AI Architecture (Hybrid Lazy Loading via ModelManager)
        self._model_mgr = init_model_manager(
            lazy_load=os.environ.get("TITAN_LAZY_LOAD", "1") == "1",
            idle_timeout_s=int(os.environ.get("TITAN_MODEL_IDLE_TIMEOUT", "300")),
            ram_budget_mb=int(os.environ.get("TITAN_RAM_BUDGET_MB", "1536")),
        )
        self._semantic = self._model_mgr.semantic_engine
        self._ai = self._model_mgr.mini_ai_engine
        self._memory = SmartMemory(semantic_engine=self._semantic)
        self._init_ai_architecture(self._semantic, self._ai, self._memory)

        # 4. Extended architecture (with defaults)
        self._init_extended_with_defaults()

        # 5. Decomposed sub-modules
        self._init_decomposed_modules()

        # 6. DAG-specific agents
        context_agent = ContextAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        criticality_agent = CriticalityAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
            macro_router=self.router,
        )
        titan_agent = TitanAgent()
        fractal_gen = FractalGenerator(
            code_agent=CodeAgent(
                semantic_engine=self._semantic, smart_memory=self._memory,
                template_engine=self._template_engine,
            ),
            ast_surgeon=self.surgeon,
            agent_runner=None,  # Will be set after _init_agent_framework
            mini_ai=self._ai,
        )

        # 7. Agent framework (F1-F5) + DAG-specific agents
        self._init_agent_framework(
            context_agent=context_agent,
            criticality_agent=criticality_agent,
            titan_agent=titan_agent,
            fractal_gen=fractal_gen,
        )

        # Fix FractalGenerator agent_runner (now available)
        if self._fractal_gen:
            self._fractal_gen._agent_runner = self._agent_runner

        # 8. Step dispatcher
        self._step_dispatcher = StepDispatcher(self)

        # 9. God-level improvements
        self._init_god_level_improvements()

        # Log status
        sem_s = "LAZY" if not self._model_mgr.semantic_loaded else "ACTIVE"
        ai_s = "LAZY" if not self._model_mgr.ai_loaded else "ACTIVE"
        logger.info(
            f"DAGOrchestrator v16 [HYBRID MODE]: SemanticEngine={sem_s} | "
            f"MiniAI(Qwen)={ai_s} | SmartMemory=ready | "
            f"TitanAgent(F1)=ready | SurgicalAgent(F2)=ready | "
            f"ContextAgent(F3)=ready | CriticalityAgent(F4)=ready | "
            f"ValidationAgent(F5)=ready | "
            f"DAG={len(self._pipeline_dag)} nodes | "
            f"ModelManager=lazy(idle=300s, budget=768MB)"
        )

        # 10. Scan project
        self._scan_project()

    # ============================================================
    #  DAG EXECUTION ENGINE - Corazón del orquestador
    # ============================================================

    async def execute(
        self,
        msg: str,
        client_id: str = "default",
        tenant_ctx: Optional[TenantContext] = None,
    ) -> Dict[str, Any]:
        """Ejecuta el pipeline DAG con TitanAgent como meta-router.
        
        Args:
            msg: Mensaje del usuario.
            client_id: Brecha B: Client identifier for multi-client isolation.
            tenant_ctx: TenantContext for Phase 2 multitenancy. If None,
                        reads from thread-local storage or creates anonymous.
        """
        start_time = time.time()
        with self._request_count_lock:
            self._request_count += 1

        # Phase 2: Set TenantContext for this request
        if tenant_ctx is None:
            tenant_ctx = get_current_tenant()
        else:
            set_current_tenant(tenant_ctx)

        # Hybrid Lazy Loading: Asegurar que los modelos estén disponibles
        # para esta request. Si están unloaded, se cargan ahora (lazy).
        self._semantic = self._model_mgr.semantic_engine
        self._ai = self._model_mgr.mini_ai_engine

        # Phase 2: Propagate tenant_id to all subsystems
        self._memory.set_tenant_id(tenant_ctx.effective_tenant_id)
        self._memory.set_client_id(client_id)
        self._current_client_id = client_id
        self._current_tenant_ctx = tenant_ctx

        # Propagate tenant_id to MerkleLedger, TheoremCache, and GraphASTEngine
        if hasattr(self, 'ledger') and self.ledger:
            self.ledger.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'cache') and self.cache:
            self.cache.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'ast_engine') and self.ast_engine:
            self.ast_engine.set_tenant_id(tenant_ctx.effective_tenant_id)

        # Reset context tracking para deduplicación cross-agent
        if self._context_agent:
            self._context_agent.reset_agent_tracking()

        # Open Design: Detect visual/UI requests for bypass routing
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
                        "OpenDesign: visual request detected — bypassing Z3/AC-3 "
                        "(signals=%s)", _od_detection.get("detection_signals", []),
                    )
                    # Propagate Design System mode to ContextAgent
                    if self._context_agent and _od_detection.get("has_design_system"):
                        self._context_agent.set_design_system_mode(
                            enabled=True,
                            budget_multiplier=od_config.design_system_budget_multiplier,
                        )
        except ImportError:
            pass
        except Exception as e:
            logger.debug("OpenDesign: detection failed: %s", e)

        # Contexto que fluye a través del DAG (now includes tenant info + Open Design)
        ctx: Dict[str, Any] = {
            "msg": msg,
            "client_id": client_id,
            "start_time": start_time,
            # Phase 2: Tenant context in pipeline
            "tenant": tenant_ctx.to_pipeline_context()["tenant"],
            "tenant_ctx": tenant_ctx,
            # Open Design: Visual bypass flags
            "is_visual_request": _is_visual_request,
            "open_design_detection": _od_detection,
            "intent": None,
            "intent_output": None,
            "context_output": None,
            "compressed_context": "",
            "token_budget": {},
            "criticality_output": None,
            "criticality_adjustments": {},
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
        }

        # Ejecutar DAG desde CACHE_CHECK
        current_node = "CACHE_CHECK"
        max_total_steps = 20

        for step in range(max_total_steps):
            if current_node not in self._pipeline_dag:
                break

            dag_node = self._pipeline_dag[current_node]

            # Anti-ciclo: trackear iteraciones por nodo
            ctx["iteration_counts"][current_node] = ctx["iteration_counts"].get(current_node, 0) + 1
            if ctx["iteration_counts"][current_node] > dag_node.max_retries + 1:
                logger.warning(f"DAG: Max iterations reached for {current_node}, forcing DONE")
                break

            # Ejecutar nodo
            exec_method = getattr(self, dag_node.exec_method, None)
            if exec_method is None:
                logger.error(f"DAG: No method {dag_node.exec_method} for node {current_node}")
                current_node = "DONE"
                continue

            node_result = await exec_method(ctx)
            ctx["node_result"] = node_result

            # Si el resultado es un dict con "status" terminado (CACHED, ABORTIVE, etc.)
            if isinstance(node_result, dict) and node_result.get("_dag_done"):
                result = {k: v for k, v in node_result.items() if k != "_dag_done"}
                return result

            # Determinar siguiente nodo
            result_key = node_result if isinstance(node_result, str) else "*"
            next_node = self._resolve_transition(current_node, result_key, ctx)
            current_node = next_node

        # Si el pipeline llegó al nodo DONE, ejecutar la lógica final
        if current_node == "DONE":
            done_result = await self._exec_done(ctx)
            if isinstance(done_result, dict):
                return done_result
            # _exec_done returned a string; build response with status
            elapsed = int((time.time() - start_time) * 1000)
            return self._build_response(ctx, "COMPLETED", elapsed)

        # Si llegamos aquí sin DONE, devolver resultado del contexto
        elapsed = int((time.time() - start_time) * 1000)
        return self._build_response(ctx, "COMPLETED", elapsed)

    def set_client_id(self, client_id: str) -> None:
        """Brecha B: Set the client_id for multi-client isolation."""
        self._memory.set_client_id(client_id)
        self._current_client_id = client_id
        logger.info(f"DAGOrchestrator: client_id set to '{client_id}'")

    def set_tenant_context(self, tenant_ctx: TenantContext) -> None:
        """Phase 2: Set the TenantContext for multi-tenant isolation.

        Propagates tenant_id to SmartMemory, MerkleLedger, TheoremCache,
        and thread-local storage so all subsystems operate within the
        correct tenant scope.

        Args:
            tenant_ctx: TenantContext with tenant_id, plan, quotas.
        """
        set_current_tenant(tenant_ctx)
        self._current_tenant_ctx = tenant_ctx
        self._memory.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'ledger') and self.ledger:
            self.ledger.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'cache') and self.cache:
            self.cache.set_tenant_id(tenant_ctx.effective_tenant_id)
        if hasattr(self, 'ast_engine') and self.ast_engine:
            self.ast_engine.set_tenant_id(tenant_ctx.effective_tenant_id)
        logger.info(
            "DAGOrchestrator: tenant_context set to tenant='%s' plan='%s'",
            tenant_ctx.effective_tenant_id, tenant_ctx.plan,
        )

    def _resolve_transition(self, current_node: str, result_key: str,
                            ctx: Dict) -> str:
        """Resuelve la transición del DAG."""
        dag_node = self._pipeline_dag.get(current_node)
        if not dag_node:
            return "DONE"

        # 0. Open Design: Check for visual bypass BEFORE direct transition lookup
        # This must come first because _exec_plan returns "low_crit" for visual
        # requests (CriticalityAgent sets path="low_crit" with source="visual_bypass"),
        # and "low_crit" would match the direct transition table → EXECUTE_STEPS,
        # bypassing the VISUAL_BYPASS node entirely.
        if current_node == "PLAN" and ctx.get("is_visual_request"):
            logger.info("OpenDesign: routing to VISUAL_BYPASS (skipping Z3/AC-3)")
            return "VISUAL_BYPASS"

        # 1. Buscar en tabla de transiciones directa
        if result_key in dag_node.transitions:
            return dag_node.transitions[result_key]
        if "*" in dag_node.transitions:
            return dag_node.transitions["*"]

        # 2. Nodos con transición dinámica (INTENT, PLAN)
        if current_node in ("INTENT", "PLAN"):
            # Build context dict with visual bypass flag for TitanAgent
            _titan_ctx = {
                "operation": ctx.get("intent_output", IntentOutput()).operation if ctx.get("intent_output") else "SEARCH",
                "goal": ctx.get("intent_output", IntentOutput()).goal if ctx.get("intent_output") else "",
                "criticality": ctx.get("routing").criticality if ctx.get("routing") else "standard",
                "is_visual_request": ctx.get("is_visual_request", False),
            }

            if self._ai and self._ai.is_loaded:
                try:
                    titan_input = {
                        "current_node": current_node,
                        "result": result_key,
                        "context": _titan_ctx,
                    }
                    if hasattr(self, '_agent_runner') and self._agent_runner is not None:
                        llm_result = self._agent_runner.run(self._titan_agent, titan_input)
                    else:
                        llm_result = self._titan_agent.fallback(titan_input)
                    if llm_result and llm_result in self._pipeline_dag:
                        return llm_result
                except Exception as e:
                    logger.debug(f"TitanAgent LLM fallback: {e}")

            return self._titan_agent.fallback({
                "current_node": current_node,
                "result": result_key,
                "context": _titan_ctx,
            })

        # 3. Default
        return dag_node.default_next or "DONE"

    # ============================================================
    #  RESPONSE BUILDER
    # ============================================================

    def _build_response(self, ctx: Dict, status: str, elapsed: int) -> Dict:
        """Construye la respuesta final del pipeline."""
        trial = ctx.get("trial")
        merkle_node = ctx.get("merkle_node")
        routing = ctx.get("routing")
        plan = ctx.get("plan")
        crit_output = ctx.get("criticality_output")

        response = {
            "status": status,
            "code": ctx.get("final_code", ""),
            "hash": merkle_node.hash_sha256[:12] if merkle_node else "N/A",
            "error": trial.error_message if trial and status == "ROLLBACK" else "",
            "processing_time_ms": elapsed,
            "route": routing.route if routing else "",
            "criticality": routing.criticality if routing else "",
            "criticality_detail": {
                "level": crit_output.level if crit_output else None,
                "path": crit_output.path if crit_output else None,
                "reason": crit_output.reason if crit_output else None,
                "confidence": crit_output.confidence if crit_output else None,
                "source": crit_output.source if crit_output else None,
            } if crit_output else None,
            "solver_status": plan.solver_status if plan else "",
            "solver_proof": plan.solver_proof if plan else "",
            "mcts_simulations": plan.mcts_simulations if plan else 0,
            "mcts_depth_reached": plan.mcts_depth_reached if plan else 0,
            "ast_analysis": ctx.get("ast_analysis", {}),
            "explanations": ctx.get("explanations", []),
        }

        if trial:
            response["warnings"] = trial.warnings
            response["metrics"] = trial.metrics
            response["paths_explored"] = trial.paths_explored
            response["paths_pruned"] = trial.paths_pruned

        if status == "SUCCESS":
            response["mini_ai_stats"] = self._ai.stats
            response["semantic_stats"] = self._semantic.stats
            response["memory_stats"] = self._memory.stats
            # Open Design: Include visual bypass info in response
            od_detection = ctx.get("open_design_detection")
            if od_detection and od_detection.get("is_visual_request"):
                response["visual_bypass"] = {
                    "enabled": True,
                    "solver_skipped": od_detection.get("bypass_solver", False),
                    "design_system_preserved": od_detection.get("has_design_system", False),
                    "signals": od_detection.get("detection_signals", []),
                }
            context_output = ctx.get("context_output")
            if context_output:
                response["context_metrics"] = {
                    "entries_used": context_output.entries_used,
                    "entries_total": context_output.entries_total,
                    "compression_ratio": context_output.compression_ratio,
                    "token_budget": context_output.token_budget,
                    "source": context_output.source,
                }
            v_out = ctx.get("validation_output")
            if v_out:
                response["validation_metrics"] = {
                    "risk_score": ctx.get("validation_risk_score", 0.0),
                    "issues_count": len(ctx.get("validation_issues", [])),
                    "correction_loops": ctx.get("correction_count", 0),
                    "source": getattr(v_out, 'source', 'unknown'),
                }

        return response

    # ============================================================
    #  DAG-SPECIFIC INTELLIGENCE STATUS
    # ============================================================

    async def get_intelligence_status(self) -> Dict[str, Any]:
        """Obtiene estado del sistema de inteligencia (Phase 8)."""
        base_status = await BaseOrchestrator.get_intelligence_status(self)
        base_status["dag_orchestrator"] = {
            "nodes": len(self._pipeline_dag),
            "titan_agent": "F1_ACTIVE",
            "criticality_paths": ["FAST", "STANDARD", "DEEP"],
        }
        return base_status

    async def get_system_status(self) -> Dict[str, Any]:
        """Obtiene estado completo del sistema."""
        base_status = await BaseOrchestrator.get_system_status(self)
        base_status["pipeline"] = "DAG-based (v16)"
        base_status["dag_nodes"] = len(self._pipeline_dag)
        base_status["titan_agent"] = "F1_ACTIVE"
        if self._titan_agent:
            base_status["agent_framework"]["titan_agent"] = self._titan_agent.stats
        return base_status
