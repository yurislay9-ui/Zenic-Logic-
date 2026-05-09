"""
DAG Node Executors (Part 2) - Remaining 9 executor methods as a mixin.

Contains: _exec_validate through _exec_done.
"""

import time
import logging
from typing import Dict, Any, Union

from src.core.agents.schemas import CriticalityOutput, ValidationInput
from src.core.smart_memory import SmartMemory
from src.core.shared.db_initializer import get_projects_dir
from src.core.dag_parts.definition import (
    MAX_MEMORY_SNIPPET_LEN,
    MAX_CODE_SNIPPET_LEN,
    SANDBOX_TTL_MULTIPLIER,
    SANDBOX_TTL_MIN,
)

logger = logging.getLogger(__name__)


class NodeExecutors2Mixin:
    """Mixin providing the remaining 9 DAG node executor methods."""

    async def _exec_validate(self, ctx: Dict) -> str:
        """Nodo VALIDATE (F5): Enjambre de Revisión Secuencial.

        OPTIMIZATION: For low_crit path, use deterministic regex-only validation
        (skip LLM call). Saves 4-8s per low-criticality request.
        """
        final_code = ctx.get("final_code", "")
        lang = ctx.get("lang", "python")

        if not final_code or not final_code.strip():
            logger.info("VALIDATE(F5): No code to validate, proceeding to SANDBOX")
            return "clean"

        # ── FAST PATH: low_crit → deterministic validation only (no LLM) ──
        crit_output = ctx.get("criticality_output")
        is_low_crit = (
            crit_output
            and isinstance(crit_output, CriticalityOutput)
            and crit_output.level == 1
        )

        if is_low_crit:
            # Use fallback (regex-based) validation — no LLM call
            intent = ctx.get("intent")
            v_out = self._validation_agent.fallback(
                ValidationInput(
                    target="code",
                    content=final_code,
                    rules=["security", "quality"],
                    language=lang,
                )
            )
            logger.info(
                "VALIDATE(F5): FAST-PATH low_crit → regex-only (skipped LLM)"
            )
        else:
            # Full LLM-based validation for standard/high_crit
            v_out = self._validation_agent.validate_with_runner(
                self._agent_runner,
                target="code",
                content=final_code,
                rules=["security", "quality"],
                language=lang,
            )

        risk_score = v_out.risk_score
        issues = v_out.issues

        ctx["validation_output"] = v_out
        ctx["validation_risk_score"] = risk_score
        ctx["validation_issues"] = issues

        # Low-crit path: tolerate low risk scores without correction loop
        # (e.g. risk=0.22 with 3 warnings is normal for generated code)
        risk_threshold = 0.3 if is_low_crit else 0.0

        if risk_score <= risk_threshold or not issues:
            if risk_score > 0.0 and issues:
                logger.info(
                    f"VALIDATE(F5): Low-risk issues (risk={risk_score:.2f}, "
                    f"issues={len(issues)}) below threshold ({risk_threshold}). "
                    f"Proceeding to SANDBOX."
                )
            else:
                logger.info(
                    f"VALIDATE(F5): Code CLEAN (risk={risk_score:.2f}, issues=0). "
                    f"Proceeding to SANDBOX."
                )
            return "clean"

        logger.warning(
            f"VALIDATE(F5): ISSUES DETECTED (risk={risk_score:.2f}, "
            f"issues={len(issues)}). Forcing correction loop."
        )

        correction_instructions = []
        for issue in issues:
            sev = getattr(issue, 'severity', 'warning')
            code_id = getattr(issue, 'code', 'unknown')
            msg = getattr(issue, 'message', str(issue))
            correction_instructions.append(
                f"[F5 CORRECTION] {sev.upper()}: {code_id} - {msg}"
            )

        ctx["explanations"].extend(correction_instructions)
        ctx["correction_loop"] = True
        ctx["correction_count"] = ctx.get("correction_count", 0) + 1

        if ctx["correction_count"] > 3:
            logger.warning(
                f"VALIDATE(F5): Max correction loops reached ({ctx['correction_count']}). "
                f"Proceeding with remaining issues."
            )
            ctx["explanations"].append(
                f"[F5 WARNING] Code delivered with {len(issues)} unresolved issues "
                f"(risk={risk_score:.2f})"
            )
            return "clean"

        return "issues_found"

    async def _exec_abortive(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo ABORTIVE: Protocolo abortivo."""
        result = await self._abortive.handle_abortive_protocol(
            ctx["intent"], ctx["routing"], ctx["plan"],
            ctx["ast_analysis"], ctx["start_time"]
        )
        return {**result, "_dag_done": True}

    async def _exec_sandbox(self, ctx: Dict) -> str:
        """Nodo SANDBOX: Validación en sandbox aislado.

        OPTIMIZATION: Skip sandbox for EXPLAIN/ANALYZE/SEARCH operations
        that don't produce executable code. Saves 1-30s per non-code request.
        """
        final_code = ctx["final_code"]
        lang = ctx.get("lang", "python")
        intent = ctx.get("intent")

        # ── FAST PATH: Skip sandbox for non-code operations ──
        if intent and intent.op and intent.op.upper() in ("EXPLAIN", "ANALYZE", "SEARCH"):
            logger.info(
                "SANDBOX: FAST-PATH skipped for %s operation (no executable code)",
                intent.op.upper(),
            )
            # Treat as PASS — no code to sandbox-test
            from src.core.shared.types import SandboxResult
            ctx["trial"] = SandboxResult(
                status="PASS",
                error_message="",
            )
            return "PASS"

        workspace = self._isolation_manager.create_workspace(
            ttl_seconds=max(self.sandbox.timeout_seconds * SANDBOX_TTL_MULTIPLIER, SANDBOX_TTL_MIN),
            client_id=ctx.get("client_id", "default")
        )
        ctx["sandbox_workspace"] = workspace

        try:
            p_dir = str(get_projects_dir())
            self.ledger.snapshot(intent.target if intent else "unknown", p_dir, workspace=workspace)

            trial = await self.sandbox.validate_code(
                final_code, lang, intent.target if intent else "unknown"
            )
            ctx["trial"] = trial
            return trial.status
        except Exception as e:
            logger.error("SANDBOX: Validation failed with exception: %s", e)
            # Release workspace on error
            if workspace:
                try:
                    self._isolation_manager.release_workspace(workspace.sandbox_id)
                except Exception:
                    pass
            ctx["trial"] = None
            return "FAIL"

    async def _exec_partial_reasoning(self, ctx: Dict) -> Union[str, Dict]:
        """Nodo PARTIAL_REASONING: Razonamiento parcial para K-Path."""
        result = self._partial_reasoning.build_partial_reasoning_response(
            ctx["intent"], ctx["routing"], ctx["plan"],
            ctx["ast_analysis"], ctx["trial"], ctx["start_time"]
        )
        return {**result, "_dag_done": True}

    async def _exec_ledger_commit(self, ctx: Dict) -> str:
        """Nodo LEDGER_COMMIT: Commit del código validado."""
        intent = ctx.get("intent")
        final_code = ctx["final_code"]
        workspace = ctx.get("sandbox_workspace")

        p_dir = str(get_projects_dir())
        node = self.ledger.commit(
            intent.target if intent else "unknown", final_code, p_dir,
            workspace=workspace
        )
        ctx["merkle_node"] = node

        # Release sandbox workspace after successful commit
        if workspace:
            try:
                self._isolation_manager.release_workspace(workspace.sandbox_id)
            except Exception as e:
                logger.debug("Failed to release workspace after commit: %s", e)

        return "*"

    async def _exec_ledger_rollback(self, ctx: Dict) -> str:
        """Nodo LEDGER_ROLLBACK: Rollback del código fallido."""
        intent = ctx.get("intent")
        workspace = ctx.get("sandbox_workspace")

        p_dir = str(get_projects_dir())
        self.ledger.rollback(
            intent.target if intent else "unknown", p_dir, workspace=workspace
        )
        if workspace:
            self._isolation_manager.release_workspace(workspace.sandbox_id)
        return "*"

    async def _exec_theorem_save(self, ctx: Dict) -> str:
        """Nodo THEOREM_SAVE: Guardar en caché de teoremas."""
        intent = ctx.get("intent")
        merkle_node = ctx.get("merkle_node")
        final_code = ctx["final_code"]

        if intent and merkle_node:
            self.cache.save(
                intent, "PROVEN",
                {"h": merkle_node.hash_sha256[:8], "code": final_code},
                final_code, ctx["lang"]
            )
        return "*"

    async def _exec_memory_save(self, ctx: Dict) -> str:
        """Nodo MEMORY_SAVE: Guardar en SmartMemory (aprendizaje) + F3 context save."""
        intent = ctx.get("intent")
        final_code = ctx["final_code"]
        msg = ctx["msg"]

        if ctx.get("trial") and ctx["trial"].status == "PASS" and final_code:
            importance = SmartMemory.compute_importance(
                msg, intent.op if intent else "", intent.goal if intent else "",
                success=True, response_length=len(final_code)
            )
            self._memory.add_working(
                msg, final_code[:MAX_MEMORY_SNIPPET_LEN], intent.op if intent else "",
                intent.goal if intent else "", importance
            )
            self._memory.save_to_cache(
                msg, final_code[:MAX_MEMORY_SNIPPET_LEN], intent.op if intent else "",
                intent.goal if intent else "", importance
            )

            # F3: Save procedural pattern
            context_output = ctx.get("context_output")
            if context_output and context_output.relevant_memories:
                for mem in context_output.relevant_memories[:2]:
                    if mem.get("type") == "similar_solution" and mem.get("similarity", 0) > 0.7:
                        try:
                            self._memory.learn_pattern(
                                pattern_name=f"{intent.op if intent else 'unknown'}_solution",
                                pattern_type="solution",
                                description=mem.get("solution", "")[:MAX_CODE_SNIPPET_LEN],
                                success=True,
                            )
                        except Exception:
                            pass
        else:
            self._memory.add_working(
                msg, "NO_OP", intent.op if intent else "",
                intent.goal if intent else "", importance=0.2
            )
        return "*"

    async def _exec_done(self, ctx: Dict) -> str:
        """Nodo DONE: Construir respuesta final."""
        elapsed = int((time.time() - ctx["start_time"]) * 1000)
        trial = ctx.get("trial")
        final_code = ctx.get("final_code", "")

        if trial and trial.status == "PASS" and final_code:
            status = "SUCCESS"
        elif trial and trial.status.startswith("FAIL"):
            status = "ROLLBACK"
        elif final_code:
            status = "SUCCESS"
        else:
            status = "NO_OP"

        self._analysis.log_request(
            ctx.get("intent"), status, elapsed,
            solver_status=ctx.get("plan", None) and ctx["plan"].solver_status or "",
            mcts_sims=ctx.get("plan", None) and ctx["plan"].mcts_simulations or 0,
        )

        return self._build_response(ctx, status, elapsed)
