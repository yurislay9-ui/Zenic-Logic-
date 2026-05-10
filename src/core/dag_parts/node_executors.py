"""
DAG Node Executors (Part 1) - First 12 executor methods as a mixin.

Contains: _exec_cache_check, _exec_chat_detect, _exec_chat_respond,
through _exec_steps.
"""

import re
import time
import logging
from typing import Dict, Any, Union

from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.schemas import CriticalityOutput
from src.core.agents.criticality_agent_parts._imports import CRITICALITY_ADJUSTMENTS
from src.core.dag_parts.definition import MAX_CODE_SNIPPET_LEN

logger = logging.getLogger(__name__)


# ── Chat Detection Patterns (zero LLM, pure deterministic) ────────

# Greetings and simple social messages
_CHAT_GREETINGS = re.compile(
    r"^(hi|hello|hey|hola|buenas|qué tal|good morning|good afternoon|good evening|"
    r"buenos días|buenas tardes|buenas noches|sup|yo|what'?s up|howdy|saludos)[\s!.,?]*$",
    re.IGNORECASE,
)

# Gratitude / acknowledgments
_CHAT_THANKS = re.compile(
    r"^(thanks|thank you|thx|ty|gracias|genial|perfecto|ok|okay|got it|entendido|"
    r"entiendo|vale|bien|nice|cool|great|awesome|excelente)[\s!.,]*$",
    re.IGNORECASE,
)

# Simple questions that don't need code analysis
_CHAT_SIMPLE_Q = re.compile(
    r"^(what is|what are|who is|who are|where is|when is|how (do|does|is|are|to)|"
    r"can you|could you|por qué|cómo|qué es|quién|dónde|cuándo|"
    r"tell me about|explain|describe|define|resume|resumen)\b",
    re.IGNORECASE,
)

# Code/technical indicators — if present, go to full pipeline
_CODE_INDICATORS = re.compile(
    r"(\.py|\.js|\.ts|\.java|\.cpp|\.c|\.go|\.rs|\.rb|\.php|\.html|\.css|\.sql|"
    r"```|def |class |import |function |const |var |let |return |if |for |while |"
    r"async |await |try|except|catch|throw|error|bug|fix|refactor|optimize|"
    r"endpoint|api|database|server|deploy|docker|git |commit|pull|push|merge)",
    re.IGNORECASE,
)


class NodeExecutorsMixin:
    """Mixin providing the first 12 DAG node executor methods."""

    # ── FAST PATH: Chat Mode ──────────────────────────────────

    async def _exec_chat_detect(self, ctx: Dict) -> str:
        """Nodo CHAT_DETECT: Detectar mensajes de chat simple vs. solicitud técnica.

        Zero LLM calls — pure deterministic pattern matching.
        Returns 'chat' for simple conversational messages,
        'pipeline' for anything that needs the full DAG.

        IMPORTANT: Cline and other AI coding assistants send messages that
        look like "simple questions" but are actually complex requests.
        The TITAN_NO_CHAT_DETECT env var disables this shortcut entirely
        for environments where all requests should go through the full pipeline.
        """
        import os

        # ── KILL SWITCH: Disable chat detect for Cline-only environments ──
        # When TITAN_NO_CHAT_DETECT=1, ALL messages go to the full pipeline.
        # This prevents Cline requests from being misclassified as "chat".
        if os.environ.get("TITAN_NO_CHAT_DETECT", "0") == "1":
            logger.debug("CHAT_DETECT: bypassed (TITAN_NO_CHAT_DETECT=1)")
            return "pipeline"

        msg = ctx["msg"].strip()

        # Always go to pipeline if code indicators present
        if _CODE_INDICATORS.search(msg):
            return "pipeline"

        # ── GUARD: Messages >15 words are NEVER chat ──
        # Cline sends multi-sentence requests that match _CHAT_SIMPLE_Q
        # (e.g. "how do I fix the authentication bug in my Flask app?")
        # but are clearly NOT simple chat. Only VERY short messages qualify.
        word_count = len(msg.split())

        # Very short messages that match greetings/thanks → chat mode
        if word_count <= 5:
            if _CHAT_GREETINGS.match(msg):
                logger.info("CHAT_DETECT: greeting detected → chat mode")
                return "chat"
            if _CHAT_THANKS.match(msg):
                logger.info("CHAT_DETECT: thanks/ack detected → chat mode")
                return "chat"

        # DISABLED: The _CHAT_SIMPLE_Q pattern is too aggressive for Cline.
        # Messages like "how do I fix..." or "what is the error..." get
        # misclassified as chat and receive template responses instead of
        # going through the pipeline. Only pure greetings/thanks qualify now.

        # Everything else → full pipeline
        return "pipeline"

    async def _exec_chat_respond(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo CHAT_RESPOND: Generate response for simple chat messages.

        Uses the LLM (Qwen) directly for a fast response, bypassing
        the entire 15-node DAG pipeline. No agents, no validation,
        no sandbox — just direct inference.
        """
        msg = ctx["msg"].strip()
        start = ctx["start_time"]

        # Try direct LLM inference for a conversational response
        if self._agent_runner and hasattr(self._agent_runner, 'runner'):
            try:
                llm_engine = getattr(self._agent_runner, '_llm_engine', None)
                if llm_engine is None:
                    # Try to get it from the orchestrator's model manager
                    if hasattr(self, '_model_mgr'):
                        llm_engine = self._model_mgr.mini_ai_engine

                if llm_engine and hasattr(llm_engine, 'chat'):
                    response_text = llm_engine.chat(msg, max_tokens=256)
                    elapsed = int((time.time() - start) * 1000)
                    logger.info(
                        "CHAT_RESPOND: Direct LLM response in %dms", elapsed
                    )
                    ctx["final_code"] = response_text
                    return {
                        "status": "SUCCESS",
                        "code": response_text,
                        "hash": "chat",
                        "error": "",
                        "processing_time_ms": elapsed,
                        "pipeline_path": "chat_mode",
                        "_dag_done": True,
                    }
            except Exception as e:
                logger.warning("CHAT_RESPOND: Direct LLM failed: %s, using template", e)

        # Fallback: Template-based responses (zero LLM, instant)
        elapsed = int((time.time() - start) * 1000)
        response_text = self._chat_template_response(msg)
        logger.info("CHAT_RESPOND: Template response in %dms", elapsed)

        ctx["final_code"] = response_text
        return {
            "status": "SUCCESS",
            "code": response_text,
            "hash": "chat",
            "error": "",
            "processing_time_ms": elapsed,
            "pipeline_path": "chat_mode_template",
            "_dag_done": True,
        }

    def _chat_template_response(self, msg: str) -> str:
        """Generate template-based response for simple chat (zero LLM)."""
        msg_lower = msg.lower().strip()

        # Greetings
        if _CHAT_GREETINGS.match(msg):
            return (
                "¡Hola! Soy TITAN OMNISCALE X, tu motor de IA local. "
                "Estoy listo para ayudarte. ¿En qué puedo asistirte?"
            )

        # Thanks
        if _CHAT_THANKS.match(msg):
            return "¡De nada! Estoy aquí cuando me necesites."

        # Simple questions - give a helpful redirect
        if _CHAT_SIMPLE_Q.match(msg):
            return (
                f"Buena pregunta. Puedo ayudarte con eso. "
                f"Para darte una respuesta más precisa, ¿puedes dar más contexto "
                f"o detalles sobre lo que necesitas?"
            )

        # Default
        return (
            "Entendido. Estoy procesando tu mensaje. "
            "¿Necesitas que genere código, analice algo, o tienes alguna pregunta específica?"
        )

    async def _exec_cache_check(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo CACHE_CHECK: Check SmartMemory cache.

        Can be disabled via TITAN_NO_CACHE=1 env var to force all requests
        through the full pipeline. Useful for Cline environments where cached
        (potentially stale/truncated) responses cause more harm than good.
        """
        import os

        # ── KILL SWITCH: Disable cache for Cline environments ──
        if os.environ.get("TITAN_NO_CACHE", "0") == "1":
            logger.debug("CACHE_CHECK: bypassed (TITAN_NO_CACHE=1)")
            return "miss"

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
            # E06-note: Mutating intent object post-construction to inject
            # extracted code. This is safe because ctx["intent"] is not read
            # by any node between _exec_intent and this point. However, if
            # a new DAG node is added between INTENT and PLAN that reads
            # intent.raw_code, it would see an empty string. Consider moving
            # code extraction into IntentPayload.__init__ or _exec_intent.
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
        """Nodo AST_ANALYZE: Análisis AST del código.

        CRITICAL: Always initialize ctx["ast_analysis"], even for CREATE
        operations where raw_code is empty. Without this, ast_analysis is
        None, which causes code generation to produce generic code without
        structural awareness, and downstream "Structure: 0 functions, 0 classes".
        """
        intent = ctx.get("intent")
        if intent and intent.raw_code:
            ctx["ast_analysis"] = self.ast_engine.analyze_structure(
                intent.raw_code, intent.language
            )
        else:
            # CREATE operations have no raw_code — initialize with empty defaults
            # so downstream nodes don't crash on None
            ctx["ast_analysis"] = {
                "functions": 0, "classes": 0, "imports": 0,
                "max_complexity": 0, "total_complexity": 0,
                "avg_complexity": 0, "connections": [],
                "function_names": [], "class_names": [],
            }
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
        """Nodo CRITICALITY_ROUTE (F4): Ruteo Dinámico de Criticalidad.

        OPTIMIZATION: Skip LLM call for EXPLAIN/SEARCH/ANALYZE operations
        with high confidence — they are always low_crit. Saves 1-2s per request.
        """
        if not self._criticality_agent:
            return "*"

        intent_output = ctx.get("intent_output")
        routing = ctx.get("routing")
        router_crit = routing.criticality if routing else 2

        # ── FAST PATH: Skip LLM for low-criticality operations ──
        if intent_output and intent_output.confidence > 0.6:
            op = intent_output.operation.upper() if intent_output.operation else ""
            if op in ("EXPLAIN", "SEARCH", "ANALYZE"):
                # These are always low_crit — skip the LLM call entirely
                crit_output = CriticalityOutput(
                    level=1,
                    path="low_crit",
                    reason=f"Fast-path: {op} operation (skipped F4 LLM)",
                    confidence=0.9,
                    source="operation_fast_path",
                    adjustments=CRITICALITY_ADJUSTMENTS.get(1, CRITICALITY_ADJUSTMENTS[2]),
                )
                ctx["criticality_output"] = crit_output
                if routing:
                    routing.criticality = 1
                logger.info(
                    "CriticalityAgent(F4): FAST-PATH %s → low_crit (skipped LLM)",
                    op,
                )
                return "*"

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

        code = ctx.get("code", "")
        result_code = ""
        explanations = ctx.get("explanations", [])
        lang = ctx.get("lang", "python")

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

        # Re-analyze generated code with AST (was empty for CREATE operations)
        # This gives VALIDATE and downstream nodes structural awareness
        generated = ctx["final_code"]
        if generated and isinstance(ctx.get("ast_analysis"), dict):
            current_funcs = ctx["ast_analysis"].get("functions", 0)
            if current_funcs == 0:
                try:
                    ctx["ast_analysis"] = self.ast_engine.analyze_structure(
                        generated, lang
                    )
                except Exception as e:
                    logger.debug("AST re-analysis of generated code failed: %s", e)

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
