"""
TITAN OMNISCALE X - Orchestrator v16 (Real Pipeline + Abortive Protocol)

Orquestador del pipeline completo de 8 niveles.
Incluye:
- MiniAIEngine: Qwen3-0.6B como copiloto semantico (7 tareas bounded)
- Protocolo Abortivo: auto-subdivision cuando el solver hace timeout
- Razonamiento Parcial: response contract OpenAI-compatible
- Generacion contextual: usa datos del AST, solver y MCTS
- Configuracion desde YAML

Sin dependencias externas obligatorias. Compatible con Android.

Decomposed into focused modules:
- orchestrator_base: BaseOrchestrator (shared init, public API, backward-compat)
- step_dispatcher: StepDispatcher (unified step dispatch logic)
- mini_ai_engine: MiniAIEngine (Qwen3-0.6B semantic copilot)
- subtask_descriptor: SubtaskDescriptor class
- abortive_protocol: AbortiveProtocol (auto-subdivision)
- partial_reasoning: PartialReasoningManager (response contract)
- code_generator: CodeGenerator (pipeline-driven code generation)
- code_transformer: CodeTransformer (refactoring, fixing, optimization)
- analysis_utils: AnalysisUtils (quality reports, explanations, logging)
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config.loader import load_settings
from src.core.shared.db_initializer import get_projects_dir
from src.core.shared.contracts import OperationType, GoalType, RoutePath

# Base class with shared initialization, public API, backward-compat
from src.core.orchestrator_base import BaseOrchestrator

# Step dispatcher for unified step execution
from src.core.step_dispatcher import StepDispatcher

# Decomposed modules - 3-Layer AI Architecture
from src.core.semantic_engine import SemanticEngine   # Capa 1: ENTIENDE
from src.core.mini_ai_engine import MiniAIEngine      # Capa 2: PIENSA
from src.core.smart_memory import SmartMemory          # Capa 3: RECUERDA
from src.core.agents.surgical_agent import SurgicalAgent

logger = logging.getLogger(__name__)

# === Extracted Constants (previously hardcoded inline) ===
MAX_MEMORY_SNIPPET_LEN = 500      # Max chars for memory save snippets
SANDBOX_TTL_MULTIPLIER = 3        # Sandbox TTL = timeout * multiplier
SANDBOX_TTL_MIN = 120             # Minimum sandbox TTL in seconds
MAX_CODE_SNIPPET_LEN = 200        # Max chars for code context snippets


class TitanOrchestrator(BaseOrchestrator):
    """
    Orquestador del pipeline completo de 8 niveles con Protocolo Abortivo.

    Inherits from BaseOrchestrator which provides:
    - All shared initialization methods
    - Public API methods (generate_app, build_logic, reason, etc.)
    - Backward-compat delegation methods
    - Shared properties

    This class only contains the sequential `execute()` method and
    TitanOrchestrator-specific code.
    """

    def __init__(self) -> None:
        # 1. Common state
        settings = load_settings()
        self._init_common_state()

        # 2. Pipeline components
        self._init_pipeline_components(settings)

        # 3. 3-Layer AI Architecture (eager loading for TitanOrchestrator)
        semantic = SemanticEngine(auto_load=True)
        ai = MiniAIEngine(auto_load=True)
        memory = SmartMemory(semantic_engine=semantic)
        self._init_ai_architecture(semantic, ai, memory)

        # Log AI status
        sem_status = "ACTIVE" if self._semantic.is_loaded else "fallback"
        ai_status = "ACTIVE" if self._ai.is_loaded else "fallback"
        logger.info(f"AI Architecture: SemanticEngine={sem_status} | MiniAI(Qwen)={ai_status} | SmartMemory=ready")

        # 4. Extended architecture (with defaults)
        self._init_extended_with_defaults()

        # 5. Decomposed sub-modules
        self._init_decomposed_modules()

        # 6. Agent framework (F1-F5)
        self._init_agent_framework()

        # 7. Step dispatcher
        self._step_dispatcher = StepDispatcher(self)

        # 8. God-level improvements
        self._init_god_level_improvements()

        # 9. Scan project
        self._scan_project()

    async def execute(self, msg: str) -> Dict[str, Any]:
        """Ejecuta el pipeline completo de 8 niveles con Protocolo Abortivo."""
        start_time = time.time()
        self.request_count += 1

        # ============================================================
        #  CAPA 3: SmartMemory - Check semantic cache first
        # ============================================================
        cached = self._memory.check_cache(msg)
        if cached:
            elapsed = int((time.time() - start_time) * 1000)
            logger.info(f"SmartMemory: Cache hit ({cached['source']}) for: {msg[:50]}")
            self._analysis.log_request(None, "CACHED", elapsed, cache_hit=True)
            return {
                "status": "CACHED",
                "code": cached.get("response", ""),
                "hash": "mem",
                "error": "",
                "cache_source": cached["source"],
                "processing_time_ms": elapsed,
            }

        # ============================================================
        #  INTENT AGENT (Phase F2) - Unified intent classification
        # ============================================================
        intent_output = self._surgical_agent.classify_with_runner(
            self._agent_runner, msg, context=""
        )
        intent = self._surgical_agent.to_intent_payload(intent_output, context=msg)

        # Extraer codigo del mensaje (separado de la clasificacion)
        code_lang, raw_code = SurgicalAgent._extract_code_block(msg)
        if raw_code:
            intent.raw_code = raw_code
            if code_lang:
                intent.language = code_lang

        logger.info(f"SurgicalAgent: {intent_output.operation}/{intent_output.goal} "
                    f"(source={intent_output.source}, conf={intent_output.confidence:.2f}, "
                    f"target={intent.target})")

        # Nivel 3: Analisis AST del codigo proporcionado
        ast_analysis = {}
        if intent.raw_code:
            ast_analysis = self.ast_engine.analyze_structure(intent.raw_code, intent.language)

        # Nivel 8: Cache lookup (bypass O(1))
        cache_hit = self.cache.lookup(intent, intent.raw_code, intent.language)
        if cache_hit:
            elapsed = int((time.time() - start_time) * 1000)
            self._analysis.log_request(intent, "CACHED", elapsed, cache_hit=True)
            return {
                "status": "CACHED",
                "code": cache_hit["data"].get("code", ""),
                "hash": cache_hit["data"].get("h", "N/A"),
                "error": "",
                "cache_source": cache_hit["source"],
                "cache_hits": cache_hit["hits"],
                "processing_time_ms": elapsed,
                "ast_analysis": ast_analysis,
            }

        # Nivel 2: Macro Router (MoE Clasificador con firmas topologicas)
        routing = self.router.route(intent)

        # Nivel 4: APA Planner (Z3 + MCTS REALES)
        plan = self.planner.generate_plan(routing)

        # ============================================================
        #  PROTOCOLO ABORTIVO: Auto-subdivision cuando solver timeout
        # ============================================================
        if plan.solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            return await self._abortive.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time
            )

        # Nivel 5: Ejecutar pasos del plan via StepDispatcher
        code = intent.raw_code or ""
        explanations = []
        lang = intent.language

        result_code, code, explanations = await self._step_dispatcher.execute_plan_steps(
            plan, intent, code, explanations, lang, ast_analysis,
        )

        final_code = result_code if result_code else code

        # Nivel 7 (Snapshot) -> Nivel 6 (Sandbox Trial) -> Nivel 7 (Commit/Rollback)
        # Crear workspace AISLADO para sandbox y ledger
        sandbox_workspace = self._isolation_manager.create_workspace(
            ttl_seconds=max(self.sandbox.timeout_seconds * SANDBOX_TTL_MULTIPLIER, SANDBOX_TTL_MIN)
        )
        p_dir = str(get_projects_dir())
        self.ledger.snapshot(intent.target, p_dir, workspace=sandbox_workspace)

        trial = await self.sandbox.validate_code(final_code, lang, intent.target)

        if trial.status == "PASS" and final_code:
            node = self.ledger.commit(intent.target, final_code, p_dir,
                                       workspace=sandbox_workspace)
            # Release sandbox workspace after successful commit
            try:
                self._isolation_manager.release_workspace(sandbox_workspace.sandbox_id)
            except Exception as e:
                logger.debug("Orchestrator: Failed to release workspace: %s", e)
            self.cache.save(intent, "PROVEN",
                          {"h": node.hash_sha256[:8], "code": final_code},
                          final_code, lang)
            elapsed = int((time.time() - start_time) * 1000)
            self._analysis.log_request(intent, "SUCCESS", elapsed,
                            solver_status=plan.solver_status,
                            mcts_sims=plan.mcts_simulations)

            # SmartMemory: Save successful interaction (learning)
            importance = SmartMemory.compute_importance(
                msg, intent.op, intent.goal, success=True, response_length=len(final_code))
            self._memory.add_working(msg, final_code[:MAX_MEMORY_SNIPPET_LEN], intent.op, intent.goal, importance)
            self._memory.save_to_cache(msg, final_code[:MAX_MEMORY_SNIPPET_LEN], intent.op, intent.goal, importance)
            return {
                "status": "SUCCESS", "code": final_code,
                "hash": node.hash_sha256[:12], "error": "",
                "processing_time_ms": elapsed, "route": routing.route,
                "criticality": routing.criticality,
                "solver_status": plan.solver_status,
                "solver_proof": plan.solver_proof,
                "mcts_simulations": plan.mcts_simulations,
                "mcts_depth_reached": plan.mcts_depth_reached,
                "ast_analysis": ast_analysis,
                "explanations": explanations,
                "warnings": trial.warnings, "metrics": trial.metrics,
                "paths_explored": trial.paths_explored,
                "paths_pruned": trial.paths_pruned,
                "mini_ai_stats": self._ai.stats,
                "semantic_stats": self._semantic.stats,
                "memory_stats": self._memory.stats,
            }
        elif trial.status.startswith("FAIL") and final_code:
            self.ledger.rollback(intent.target, p_dir, workspace=sandbox_workspace)
            # Liberar workspace tras rollback
            self._isolation_manager.release_workspace(sandbox_workspace.sandbox_id)
            elapsed = int((time.time() - start_time) * 1000)
            self._analysis.log_request(intent, "ROLLBACK", elapsed,
                            solver_status=plan.solver_status)

            # Si fallo por K-Path, devolver Razonamiento Parcial
            if trial.status == "FAIL_K_PATH":
                return self._partial_reasoning.build_partial_reasoning_response(
                    intent, routing, plan, ast_analysis, trial, start_time
                )

            return {
                "status": "ROLLBACK", "code": final_code, "hash": "N/A",
                "error": trial.error_message,
                "processing_time_ms": elapsed, "route": routing.route,
                "criticality": routing.criticality,
                "solver_status": plan.solver_status,
                "ast_analysis": ast_analysis,
                "explanations": explanations,
                "warnings": trial.warnings,
                "paths_explored": trial.paths_explored,
                "paths_pruned": trial.paths_pruned,
            }
        else:
            # Release sandbox workspace on NO_OP path (resource leak fix)
            try:
                self._isolation_manager.release_workspace(sandbox_workspace.sandbox_id)
            except Exception as e:
                logger.debug("Orchestrator: Failed to release workspace on NO_OP: %s", e)

            elapsed = int((time.time() - start_time) * 1000)
            self._analysis.log_request(intent, "NO_OP", elapsed)

            # Save to SmartMemory even on NO_OP (learning what doesn't work)
            self._memory.add_working(msg, "NO_OP", intent.op, intent.goal, importance=0.2)

            return {
                "status": "NO_OP", "code": "", "hash": "N/A",
                "error": "No new code generated",
                "processing_time_ms": elapsed, "route": routing.route,
                "criticality": routing.criticality,
                "solver_status": plan.solver_status,
                "ast_analysis": ast_analysis,
                "explanations": explanations,
            }
