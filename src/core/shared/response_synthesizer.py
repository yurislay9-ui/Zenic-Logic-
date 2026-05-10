"""
TITAN OMNISCALE X - ResponseSynthesizer

Consolida la construccion de resultados internos del pipeline (status dicts)
que antes estaba duplicado entre DAGOrchestrator._build_response() y
TitanOrchestrator.execute().

Principios:
  - Single source of truth para la estructura del resultado del pipeline
  - Ambos orquestadores usan el mismo formato interno
  - response_builder.py (HTTP layer) consume estos dicts y los envuelve
    en formato OpenAI-compatible
  - Cada status tiene su propio builder para claridad y type safety

Status posibles del pipeline:
  SUCCESS       — Codigo generado, verificado y aceptado
  CACHED        — Resultado encontrado en cache
  REJECTED      — VerdictEngine rechazo el codigo
  ROLLBACK      — Sandbox fallo, codigo revertido
  NO_OP         — No se genero codigo nuevo
  DAG_TIMEOUT   — Pipeline excedio maximo de iteraciones
  PARTIAL_REASONING — Codigo parcialmente generado (K-Path)
  ERROR         — Error interno del pipeline
"""

import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResponseSynthesizer:
    """Constructor centralizado de resultados del pipeline.

    Elimina la duplicacion de ~80% de campos repetidos en los returns
    inline de TitanOrchestrator y DAGOrchestrator._build_response().

    Usage:
        synth = ResponseSynthesizer()
        result = synth.success(
            code=final_code, hash=node_hash, elapsed_ms=elapsed,
            route=routing.route, criticality=routing.criticality,
            solver_status=plan.solver_status, ...
        )
    """

    # ── Campos comunes que TODO resultado debe tener ──
    _COMMON_FIELDS = frozenset({
        "status", "code", "hash", "error", "processing_time_ms",
        "route", "criticality", "solver_status", "ast_analysis",
        "explanations",
    })

    @staticmethod
    def _base(status: str, elapsed_ms: int, **overrides: Any) -> Dict[str, Any]:
        """Construye el dict base con campos comunes.

        Todos los resultados del pipeline comparten estos campos.
        Los overrides permiten anadir o sobreescribir campos.
        """
        result: Dict[str, Any] = {
            "status": status,
            "code": "",
            "hash": "N/A",
            "error": "",
            "processing_time_ms": elapsed_ms,
            "route": "",
            "criticality": "",
            "solver_status": "",
            "solver_proof": "",
            "mcts_simulations": 0,
            "mcts_depth_reached": 0,
            "ast_analysis": {},
            "explanations": [],
        }
        result.update(overrides)
        return result

    # ── SUCCESS: Codigo generado, verificado y aceptado ──

    @staticmethod
    def success(
        code: str,
        hash_val: str,
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "",
        solver_proof: str = "",
        mcts_simulations: int = 0,
        mcts_depth_reached: int = 0,
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        metrics: Optional[Dict] = None,
        paths_explored: int = 0,
        paths_pruned: int = 0,
        verdict: str = "",
        verdict_source: str = "",
        verdict_llm_used: bool = False,
        verdict_evidence: str = "",
        mini_ai_stats: Optional[Dict] = None,
        semantic_stats: Optional[Dict] = None,
        memory_stats: Optional[Dict] = None,
        verdict_engine_stats: Optional[Dict] = None,
        context_metrics: Optional[Dict] = None,
        validation_metrics: Optional[Dict] = None,
        visual_bypass: Optional[Dict] = None,
        cache_source: str = "",
        cache_hits: int = 0,
    ) -> Dict[str, Any]:
        """Construye resultado SUCCESS con todos los campos del pipeline.

        Este es el resultado mas rico en metadata del pipeline.
        Incluye stats de todos los subsistemas para observabilidad.
        """
        result = ResponseSynthesizer._base(
            "SUCCESS", elapsed_ms,
            code=code,
            hash=hash_val,
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            solver_proof=solver_proof,
            mcts_simulations=mcts_simulations,
            mcts_depth_reached=mcts_depth_reached,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
        )

        # Sandbox trial fields
        if warnings is not None:
            result["warnings"] = warnings
        if metrics is not None:
            result["metrics"] = metrics
        if paths_explored:
            result["paths_explored"] = paths_explored
        if paths_pruned:
            result["paths_pruned"] = paths_pruned

        # Verdict fields (v17 architecture)
        if verdict:
            result["verdict"] = verdict
        if verdict_source:
            result["verdict_source"] = verdict_source
        if verdict_llm_used:
            result["verdict_llm_used"] = verdict_llm_used
        if verdict_evidence:
            result["verdict_evidence"] = verdict_evidence

        # Subsystem stats
        if mini_ai_stats is not None:
            result["mini_ai_stats"] = mini_ai_stats
        if semantic_stats is not None:
            result["semantic_stats"] = semantic_stats
        if memory_stats is not None:
            result["memory_stats"] = memory_stats
        if verdict_engine_stats is not None:
            result["verdict_engine_stats"] = verdict_engine_stats

        # Context and validation metrics
        if context_metrics is not None:
            result["context_metrics"] = context_metrics
        if validation_metrics is not None:
            result["validation_metrics"] = validation_metrics

        # Open Design visual bypass
        if visual_bypass is not None:
            result["visual_bypass"] = visual_bypass

        # Cache info
        if cache_source:
            result["cache_source"] = cache_source
            result["cache_hits"] = cache_hits

        return result

    # ── CACHED: Resultado encontrado en cache ──

    @staticmethod
    def cached(
        code: str,
        cache_source: str,
        elapsed_ms: int,
        hash_val: str = "mem",
        cache_hits: int = 0,
        ast_analysis: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Construye resultado CACHED — sin necesidad de ejecutar el pipeline."""
        return ResponseSynthesizer._base(
            "CACHED", elapsed_ms,
            code=code,
            hash=hash_val,
            cache_source=cache_source,
            cache_hits=cache_hits,
            ast_analysis=ast_analysis or {},
        )

    # ── REJECTED: VerdictEngine rechazo el codigo ──

    @staticmethod
    def rejected(
        code: str,
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "",
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
        verdict: str = "NO",
        verdict_source: str = "",
        verdict_llm_used: bool = False,
        verdict_evidence: str = "",
    ) -> Dict[str, Any]:
        """Construye resultado REJECTED — VerdictEngine dijo NO."""
        return ResponseSynthesizer._base(
            "REJECTED", elapsed_ms,
            code=code,
            error=f"Verdict: NO (source={verdict_source})",
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
            verdict=verdict,
            verdict_source=verdict_source,
            verdict_llm_used=verdict_llm_used,
            verdict_evidence=verdict_evidence,
        )

    # ── ROLLBACK: Sandbox fallo, codigo revertido ──

    @staticmethod
    def rollback(
        code: str,
        error_msg: str,
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "",
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        paths_explored: int = 0,
        paths_pruned: int = 0,
        verdict: str = "",
        verdict_source: str = "",
        verdict_llm_used: bool = False,
    ) -> Dict[str, Any]:
        """Construye resultado ROLLBACK — sandbox validation fallo."""
        result = ResponseSynthesizer._base(
            "ROLLBACK", elapsed_ms,
            code=code,
            error=error_msg,
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
            verdict=verdict,
            verdict_source=verdict_source,
            verdict_llm_used=verdict_llm_used,
        )
        if warnings is not None:
            result["warnings"] = warnings
        if paths_explored:
            result["paths_explored"] = paths_explored
        if paths_pruned:
            result["paths_pruned"] = paths_pruned
        return result

    # ── NO_OP: No se genero codigo nuevo ──

    @staticmethod
    def no_op(
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "",
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
        verdict: str = "",
        verdict_source: str = "",
    ) -> Dict[str, Any]:
        """Construye resultado NO_OP — no se genero codigo nuevo."""
        return ResponseSynthesizer._base(
            "NO_OP", elapsed_ms,
            error="No new code generated",
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
            verdict=verdict,
            verdict_source=verdict_source,
        )

    # ── DAG_TIMEOUT: Pipeline excedio maximo de iteraciones ──

    @staticmethod
    def dag_timeout(
        elapsed_ms: int,
        explanations: Optional[List[str]] = None,
        code: str = "",
        route: str = "",
        criticality: str = "",
        ast_analysis: Optional[Dict] = None,
        iteration_counts: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Construye resultado DAG_TIMEOUT — pipeline interrumpido."""
        result = ResponseSynthesizer._base(
            "DAG_TIMEOUT", elapsed_ms,
            code=code,
            route=route,
            criticality=criticality,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
        )
        if iteration_counts:
            result["iteration_counts"] = iteration_counts
        return result

    # ── ERROR: Error interno del pipeline ──

    @staticmethod
    def error(
        error_msg: str,
        elapsed_ms: int = 0,
        code: str = "",
        route: str = "",
    ) -> Dict[str, Any]:
        """Construye resultado ERROR — error interno del pipeline."""
        return ResponseSynthesizer._base(
            "ERROR", elapsed_ms,
            code=code,
            error=error_msg,
            route=route,
        )

    # ── PARTIAL_REASONING: Codigo parcialmente generado (K-Path) ──

    @staticmethod
    def partial_reasoning(
        partial_payload: Dict[str, Any],
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "",
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
        paths_explored: int = 0,
        paths_pruned: int = 0,
    ) -> Dict[str, Any]:
        """Construye resultado PARTIAL_REASONING — operacion subdividida."""
        return ResponseSynthesizer._base(
            "PARTIAL_REASONING", elapsed_ms,
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
            partial_reasoning=True,
            partial_reasoning_payload=partial_payload,
            paths_explored=paths_explored,
            paths_pruned=paths_pruned,
        )

    # ── ABORTIVE: Protocolo abortivo (solver timeout) ──

    @staticmethod
    def abortive(
        subtask_results: List[Dict[str, Any]],
        elapsed_ms: int,
        route: str = "",
        criticality: str = "",
        solver_status: str = "TIMEOUT_SUBDIVIDE_REQUIRED",
        ast_analysis: Optional[Dict] = None,
        explanations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Construye resultado ABORTIVE — solver timeout con auto-subdivision."""
        return ResponseSynthesizer._base(
            "ABORTIVE", elapsed_ms,
            route=route,
            criticality=criticality,
            solver_status=solver_status,
            ast_analysis=ast_analysis or {},
            explanations=explanations or [],
            subtask_results=subtask_results,
        )

    # ── DAG CONTEXT BUILDING ──
    # Helper para construir resultado desde DAG context dict
    # (usado por DAGOrchestrator._build_response)

    @staticmethod
    def from_dag_context(ctx: Dict[str, Any], status: str, elapsed: int) -> Dict[str, Any]:
        """Construye resultado a partir del context dict del DAG pipeline.

        Este metodo reemplaza DAGOrchestrator._build_response() directamente,
        extrayendo los campos del context dict que fluye a traves del DAG.
        """
        trial = ctx.get("trial")
        merkle_node = ctx.get("merkle_node")
        routing = ctx.get("routing")
        plan = ctx.get("plan")
        crit_output = ctx.get("criticality_output")

        # Build criticality detail
        crit_detail = None
        if crit_output:
            crit_detail = {
                "level": getattr(crit_output, 'level', None),
                "path": getattr(crit_output, 'path', None),
                "reason": getattr(crit_output, 'reason', None),
                "confidence": getattr(crit_output, 'confidence', None),
                "source": getattr(crit_output, 'source', None),
            }

        result = ResponseSynthesizer._base(
            status, elapsed,
            code=ctx.get("final_code", ""),
            hash=merkle_node.hash_sha256[:12] if merkle_node else "N/A",
            error=trial.error_message if trial and status == "ROLLBACK" else "",
            route=routing.route if routing else "",
            criticality=routing.criticality if routing else "",
            criticality_detail=crit_detail,
            solver_status=plan.solver_status if plan else "",
            solver_proof=plan.solver_proof if plan else "",
            mcts_simulations=plan.mcts_simulations if plan else 0,
            mcts_depth_reached=plan.mcts_depth_reached if plan else 0,
            ast_analysis=ctx.get("ast_analysis", {}),
            explanations=ctx.get("explanations", []),
        )

        # Sandbox trial fields
        if trial:
            result["warnings"] = trial.warnings
            result["metrics"] = trial.metrics
            result["paths_explored"] = trial.paths_explored
            result["paths_pruned"] = trial.paths_pruned

        # SUCCESS-specific fields
        if status == "SUCCESS":
            # Subsystem stats (injected by orchestrator after calling this)
            pass  # Stats added by the orchestrator itself

            # Open Design: visual bypass
            od_detection = ctx.get("open_design_detection")
            if od_detection and od_detection.get("is_visual_request"):
                result["visual_bypass"] = {
                    "enabled": True,
                    "solver_skipped": od_detection.get("bypass_solver", False),
                    "design_system_preserved": od_detection.get("has_design_system", False),
                    "signals": od_detection.get("detection_signals", []),
                }

            # Context metrics
            context_output = ctx.get("context_output")
            if context_output:
                result["context_metrics"] = {
                    "entries_used": context_output.entries_used,
                    "entries_total": context_output.entries_total,
                    "compression_ratio": context_output.compression_ratio,
                    "token_budget": context_output.token_budget,
                    "source": context_output.source,
                }

            # Validation metrics
            v_out = ctx.get("validation_output")
            if v_out:
                result["validation_metrics"] = {
                    "risk_score": ctx.get("validation_risk_score", 0.0),
                    "issues_count": len(ctx.get("validation_issues", [])),
                    "correction_loops": ctx.get("correction_count", 0),
                    "source": getattr(v_out, 'source', 'unknown'),
                }

        return result
