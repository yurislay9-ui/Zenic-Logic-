"""
DAG Node Executors (Part 1) - First 10 executor methods as a mixin.

Contains: _exec_cache_check through _exec_steps.
"""

import time
import logging
from typing import Dict, Any, Union

from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.schemas import CriticalityOutput
from src.core.agents.criticality_agent_parts._imports import CRITICALITY_ADJUSTMENTS
from src.core.dag_parts.definition import MAX_CODE_SNIPPET_LEN

logger = logging.getLogger(__name__)


class NodeExecutorsMixin:
    """Mixin providing the first 10 DAG node executor methods."""

    async def _exec_cache_check(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo CACHE_CHECK: Check SmartMemory cache."""
        cached = self._memory.check_cache(ctx["msg"])
        if cached:
            elapsed = int((time.time() - ctx["start_time"]) * 1000)
            logger.info(f"SmartMemory: Cache hit ({cached['source']})")
            ctx["final_code"] = cached.get("response", "")
            return {
                "status": "CACHED",
                "code": cached.get("response", ""),
                "hash": "mem",
                "error": "",
                "cache_source": cached["source"],
                "processing_time_ms": elapsed,
                "_dag_done": True,
            }
        return "miss"

    async def _exec_intent(self, ctx: Dict) -> str:
        """Nodo INTENT: Clasificación unificada via SurgicalAgent (F2)."""
        intent_output = self._surgical_agent.classify_with_runner(
            self._agent_runner, ctx["msg"], context=""
        )
        intent = self._surgical_agent.to_intent_payload(
            intent_output, context=ctx["msg"]
        )

        code_lang, raw_code = SurgicalAgent._extract_code_block(ctx["msg"])
        if raw_code:
            intent.raw_code = raw_code
            if code_lang:
                intent.language = code_lang

        ctx["intent"] = intent
        ctx["intent_output"] = intent_output
        ctx["lang"] = intent.language
        ctx["code"] = intent.raw_code or ""

        logger.info(
            f"SurgicalAgent(F2): {intent_output.operation}/{intent_output.goal} "
            f"(source={intent_output.source}, conf={intent_output.confidence:.2f})"
        )
        return intent_output.operation

    async def _exec_context_prepare(self, ctx: Dict) -> str:
        """Nodo CONTEXT_PREPARE (F3): Prepara contexto óptimo para downstream agents."""
        if not self._context_agent:
            return "*"

        intent_output = ctx.get("intent_output")
        msg = ctx["msg"]

        context_result = self._context_agent.prepare_context(
            message=msg,
            intent_output=intent_output,
        )

        ctx["context_output"] = context_result
        ctx["compressed_context"] = context_result.compressed_context
        ctx["token_budget"] = context_result.token_budget

        logger.info(
            f"ContextAgent(F3): {context_result.entries_used}/{context_result.entries_total} entries "
            f"ratio={context_result.compression_ratio:.2f} "
            f"budget={context_result.token_budget} "
            f"(source={context_result.source})"
        )
        return "*"

    async def _exec_ast_analyze(self, ctx: Dict) -> str:
        """Nodo AST_ANALYZE: Análisis AST del código."""
        intent = ctx.get("intent")
        if intent and intent.raw_code:
            ctx["ast_analysis"] = self.ast_engine.analyze_structure(
                intent.raw_code, intent.language
            )
        return "*"

    async def _exec_theorem_cache(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo THEOREM_CACHE: Búsqueda en caché de teoremas."""
        intent = ctx.get("intent")
        if not intent:
            return "miss"
        cache_hit = self.cache.lookup(intent, intent.raw_code, intent.language)
        if cache_hit:
            elapsed = int((time.time() - ctx["start_time"]) * 1000)
            ctx["final_code"] = cache_hit["data"].get("code", "")
            return {
                "status": "CACHED",
                "code": cache_hit["data"].get("code", ""),
                "hash": cache_hit["data"].get("h", "N/A"),
                "error": "",
                "cache_source": cache_hit["source"],
                "cache_hits": cache_hit["hits"],
                "processing_time_ms": elapsed,
                "ast_analysis": ctx["ast_analysis"],
                "_dag_done": True,
            }
        return "miss"

    async def _exec_route(self, ctx: Dict) -> str:
        """Nodo ROUTE: Macro Router (MoE)."""
        intent = ctx.get("intent")
        ctx["routing"] = self.router.route(intent)
        return "*"

    async def _exec_criticality_route(self, ctx: Dict) -> str:
        """Nodo CRITICALITY_ROUTE (F4): Ruteo Dinámico de Criticalidad."""
        if not self._criticality_agent:
            return "*"

        intent_output = ctx.get("intent_output")
        routing = ctx.get("routing")
        router_crit = routing.criticality if routing else 2

        crit_output = self._criticality_agent.assess_with_runner(
            runner=self._agent_runner,
            intent_output=intent_output,
            message=ctx["msg"],
            existing_criticality=router_crit,
        )

        ctx["criticality_output"] = crit_output
        ctx["criticality_adjustments"] = crit_output.adjustments

        # Propagar ajustes a agentes downstream
        if crit_output.adjustments:
            if hasattr(self._code_agent, 'set_criticality_adjustments'):
                self._code_agent.set_criticality_adjustments(crit_output.adjustments)
            if hasattr(self._business_logic_agent, 'set_criticality_adjustments'):
                self._business_logic_agent.set_criticality_adjustments(crit_output.adjustments)

        # Override del routing.criticality
        if routing and crit_output.level != router_crit:
            if crit_output.level > router_crit:
                routing.criticality = crit_output.level
                logger.info(
                    f"CriticalityAgent(F4): Elevated criticality "
                    f"{router_crit} → {crit_output.level} "
                    f"(path={crit_output.path}, reason={crit_output.reason[:80]})"
                )

        # F4: Ajustar presupuesto de contexto de F3
        context_output = ctx.get("context_output")
        if context_output and crit_output.adjustments:
            budget_modifier = crit_output.adjustments.get(
                "context_budget_modifier", 1.0
            )
            if budget_modifier != 1.0 and hasattr(context_output, 'token_budget'):
                adjusted_budget = {
                    k: int(v * budget_modifier)
                    for k, v in context_output.token_budget.items()
                }
                context_output.token_budget = adjusted_budget

        logger.info(
            f"CriticalityAgent(F4): level={crit_output.level} "
            f"path={crit_output.path} conf={crit_output.confidence:.2f} "
            f"(source={crit_output.source}, router={router_crit})"
        )
        return "*"

    async def _exec_plan(self, ctx: Dict) -> str:
        """Nodo PLAN: APA Planner con Router de Criticalidad (F4 enhanced)."""
        routing = ctx.get("routing")
        crit_output = ctx.get("criticality_output")

        ctx["plan"] = self.planner.generate_plan(routing)

        if ctx["plan"].solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            return "abortive"

        if crit_output and isinstance(crit_output, CriticalityOutput):
            return crit_output.path

        crit = routing.criticality if routing else 2
        return self._titan_agent.CRITICALITY_PATHS.get(crit, "standard")

    async def _exec_solver_verify(self, ctx: Dict) -> str:
        """Nodo SOLVER_VERIFY: Verificación Z3 para alta criticalidad."""
        plan = ctx.get("plan")
        if plan and plan.solver_status in ("PROVEN", "SAT", "PARTIAL"):
            return "pass"
        if plan and plan.solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            return "fail_timeout"
        if plan and plan.solver_status in ("UNSAT", "UNKNOWN", "TIMEOUT"):
            logger.warning(
                f"SOLVER_VERIFY: Solver status={plan.solver_status}. "
                f"Formal verification FAILED for high-criticality path."
            )
            return "fail"
        logger.warning("SOLVER_VERIFY: No plan or unknown solver status. Failing conservatively.")
        return "fail"

    async def _exec_steps(self, ctx: Dict) -> str:
        """Nodo EXECUTE_STEPS: Ejecutar pasos del plan via StepDispatcher."""
        plan = ctx.get("plan")
        intent = ctx.get("intent")
        if not plan or not intent:
            return "*"

        code = ctx["code"]
        result_code = ""
        explanations = ctx["explanations"]
        lang = ctx["lang"]

        # F3: Inyectar contexto comprimido en explanations
        compressed_ctx = ctx.get("compressed_context", "")
        if compressed_ctx:
            explanations.append(f"[F3 Context] {compressed_ctx[:MAX_CODE_SNIPPET_LEN]}")

        # F5: Si estamos en bucle de corrección, aplicar auto-fix
        if ctx.get("correction_loop") and ctx.get("validation_issues"):
            final_code = ctx.get("final_code", code)
            if final_code:
                corrected_code = self._apply_f5_corrections(
                    final_code, ctx["validation_issues"], lang
                )
                if corrected_code != final_code:
                    result_code = corrected_code
                    ctx["final_code"] = corrected_code
                    explanations.append(
                        f"[F5 AUTO-FIX] Applied {len(ctx['validation_issues'])} corrections"
                    )

        # Use StepDispatcher for unified step execution
        result_code, code, explanations = await self._step_dispatcher.execute_plan_steps(
            plan, intent, code, explanations, lang, ctx["ast_analysis"],
        )

        ctx["code"] = code
        ctx["result_code"] = result_code
        ctx["explanations"] = explanations
        ctx["final_code"] = result_code if result_code else code
        return "*"

    async def _exec_visual_bypass(self, ctx: Dict) -> str:
        """VISUAL_BYPASS node: Execute visual/UI code generation without Z3/AC-3 solver.

        Open Design requests for UI/visual generation skip the expensive SMT
        verification step. Code is generated via CodeAgent with FAST criticality
        adjustments and sent directly to validation (no solver).
        """
        msg = ctx.get("msg", "")

        # Force FAST criticality for visual bypass
        ctx["criticality_output"] = CriticalityOutput(
            level=1,  # FAST_STANDARD
            path="low_crit",
            reason="Visual bypass: UI/Design request from Open Design (skipping Z3/AC-3)",
            confidence=0.95,
            source="visual_bypass",
            adjustments=CRITICALITY_ADJUSTMENTS.get(1, CRITICALITY_ADJUSTMENTS[2]),
        )

        # Apply FAST adjustments to CodeAgent
        if self._code_agent:
            self._code_agent.set_criticality_adjustments(
                CRITICALITY_ADJUSTMENTS.get(1, CRITICALITY_ADJUSTMENTS[2])
            )

        # Generate code directly via CodeAgent
        if self._code_agent and self._agent_runner:
            try:
                code_result = self._code_agent.generate_with_runner(
                    self._agent_runner, msg, language="html",
                )
                if code_result and code_result.code:
                    ctx["final_code"] = code_result.code
                    ctx["code"] = code_result.code
                    ctx["explanations"] = [
                        "Visual bypass: Generated UI code (FAST path, no solver verification)",
                    ]
                    return "success"
            except Exception as e:
                logger.warning("Visual bypass CodeAgent failed, falling back to standard: %s", e)

        # Fallback to standard execution path
        return "fallback"
