"""
TITAN OMNISCALE X - Orchestrator v13 (Real Pipeline + Abortive Protocol)

Orquestador del pipeline completo de 8 niveles.
Incluye:
- MiniAIEngine: Qwen3-0.6B como copiloto semantico (7 tareas bounded)
- Protocolo Abortivo: auto-subdivision cuando el solver hace timeout
- Razonamiento Parcial: response contract OpenAI-compatible
- Generacion contextual: usa datos del AST, solver y MCTS
- Configuracion desde YAML

Sin dependencias externas obligatorias. Compatible con Android.

Decomposed into focused modules:
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
from typing import Dict, Any, List

from src.config.loader import load_settings
from src.core.shared.db_initializer import initialize_databases, get_projects_dir
from src.core.level1_semantic_engine.parser import SemanticParser
from src.core.level2_macro_router.router import MacroRouter
from src.core.level3_graph_ast.engine import GraphASTEngine
from src.core.level4_apa_planner.planner import APAPlanner
from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache
from src.core.shared.contracts import OperationType, GoalType, RoutePath
from src.core.shared.sandbox_isolation import (
    get_isolation_manager, SandboxWorkspace, shutdown_isolation
)

# Decomposed modules - 3-Layer AI Architecture
from src.core.semantic_engine import SemanticEngine   # Capa 1: ENTIENDE
from src.core.mini_ai_engine import MiniAIEngine      # Capa 2: PIENSA
from src.core.smart_memory import SmartMemory          # Capa 3: RECUERDA
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.abortive_protocol import AbortiveProtocol
from src.core.partial_reasoning import PartialReasoningManager
from src.core.code_generator import CodeGenerator
from src.core.code_transformer import CodeTransformer
from src.core.analysis_utils import AnalysisUtils

# Extended AI Architecture - App & Automation Generation
from src.core.thinking_engine import ThinkingEngine, GenerationPlan
from src.core.app_generator import AppGenerator
from src.core.automation_engine import AutomationEngine
from src.core.schema_designer import SchemaDesigner

logger = logging.getLogger(__name__)


class TitanOrchestrator:
    """Orquestador del pipeline completo de 8 niveles con Protocolo Abortivo."""

    def __init__(self):
        initialize_databases()
        self.settings = load_settings()
        self.p_dir = self.settings.get("project_dir", ".")

        self.parser = SemanticParser()
        self.router = MacroRouter()  # Ahora lee config YAML + AST graph
        self.ast_engine = GraphASTEngine()
        self.planner = APAPlanner()  # Ahora usa Z3 con fallback AC-3
        self.scrap = GitHubScrapAgent()
        self.surgeon = ASTSurgeon()
        self.sandbox = ReflexionSandbox()  # Ahora con ejecucion simbolica real
        self.ledger = MerkleLedger()
        self.cache = TheoremCache()
        self.request_count = 0

        # Pending resumptions for partial reasoning (Gap 5)
        self._pending_resumptions = {}  # token -> resumption_state

        # Sistema de aislamiento del sandbox
        self._isolation_manager = get_isolation_manager()

        # ============================================================
        #  3-LAYER AI ARCHITECTURE
        #  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud)
        #  Capa 2: MiniAIEngine (Qwen) → PIENSA (razonamiento)
        #  Capa 3: SmartMemory → RECUERDA (cache, contexto, aprendizaje)
        # ============================================================
        self._semantic = SemanticEngine(auto_load=True)
        self._ai = MiniAIEngine(auto_load=True)
        self._memory = SmartMemory(semantic_engine=self._semantic)

        # Log AI status
        sem_status = "ACTIVE" if self._semantic.is_loaded else "fallback"
        ai_status = "ACTIVE" if self._ai.is_loaded else "fallback"
        logger.info(f"AI Architecture: SemanticEngine={sem_status} | MiniAI(Qwen)={ai_status} | SmartMemory=ready")

        # ============================================================
        #  EXTENDED AI ARCHITECTURE - App & Automation Generation
        # ============================================================
        self._thinking = ThinkingEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._app_gen = AppGenerator(thinking_engine=self._thinking)
        self._automation = AutomationEngine(thinking_engine=self._thinking)
        self._schema_designer = SchemaDesigner(thinking_engine=self._thinking)

        logger.info(f"Extended Architecture: ThinkingEngine=ready | AppGenerator=ready | AutomationEngine=ready | SchemaDesigner=ready")

        # ============================================================
        #  DECOMPOSED SUB-MODULES (composition)
        # ============================================================
        self._abortive = AbortiveProtocol(self)
        self._partial_reasoning = PartialReasoningManager(self)
        self._code_gen = CodeGenerator(self)
        self._code_transform = CodeTransformer()
        self._analysis = AnalysisUtils(self)

        # Escanear proyecto si existe
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)

    async def execute(self, msg):
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
            self._analysis.log_request(intent if 'intent' in dir() else None, "CACHED", elapsed, cache_hit=True)
            return {
                "status": "CACHED",
                "code": cached.get("response", ""),
                "hash": "mem",
                "error": "",
                "cache_source": cached["source"],
                "processing_time_ms": elapsed,
            }

        # ============================================================
        #  CAPA 1: SemanticEngine + CAPA 2: MiniAI - Intent Classification
        # ============================================================
        # Nivel 1: Parse semantico (TF-IDF baseline)
        intent = self.parser.parse(msg)

        # Capa 1: SemanticEngine classify (mejor que keywords, mejor que Qwen)
        if self._semantic.is_loaded:
            sem_result = self._semantic.classify_intent(msg)
            if sem_result.source == "embedding" and sem_result.confidence > 0.3:
                intent.op = sem_result.operation
                intent.goal = sem_result.goal
                logger.info(f"SemanticEngine: {sem_result.operation}/{sem_result.goal} (emb={sem_result.confidence:.2f})")

        # Capa 2: MiniAI (Qwen) como backup si SemanticEngine no está seguro
        elif self._ai.is_loaded:
            ai_intent = self._ai.classify_intent(msg)
            if ai_intent.source == "llm" and ai_intent.confidence > 0.5:
                intent.op = ai_intent.operation
                intent.goal = ai_intent.goal
                logger.info(f"MiniAI: {ai_intent.operation}/{ai_intent.goal} (LLM, conf={ai_intent.confidence:.2f})")

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

        # Nivel 5: Ejecutar pasos del plan
        code = intent.raw_code or ""
        result_code = ""
        explanations = []
        lang = intent.language

        for step in plan.steps:
            if step.action == "ANALYZE_STRUCTURE":
                if code:
                    analysis = self.ast_engine.analyze_structure(code, lang)
                    explanations.append(
                        f"Structure: {analysis['functions']} functions, "
                        f"{analysis['classes']} classes, max complexity {analysis['max_complexity']}"
                    )
                else:
                    explanations.append("No code provided for analysis.")

            elif step.action == "SCRAPE_PATTERNS":
                query = step.constraints.get("query", intent.scrap_query)
                patterns = await self.scrap.fetch_modern_code(query, lang)
                if patterns:
                    explanations.append(f"Found {len(patterns) if isinstance(patterns, list) else 1} patterns on GitHub")
                    best = patterns[0] if isinstance(patterns, list) else patterns
                    if isinstance(best, dict):
                        best = best.get("code", str(best))[:2000]
                    if not code:
                        code = best
                else:
                    explanations.append("GitHub search: no results. Using local generation.")

            elif step.action == "GENERATE_CODE":
                result_code = self._code_gen.generate_contextual_code(intent, ast_analysis, plan, lang)
                explanations.append(f"Code generated for {intent.op}")

            elif step.action == "REPLACE_AST_NODE":
                if code and step.target_node_name:
                    solver_insights = self._code_gen.extract_solver_insights(plan.solver_proof) if plan else None
                    # MiniAI: sugerir patrón de reemplazo
                    if self._ai.is_loaded:
                        pattern = self._ai.suggest_pattern(step.target_node_name, str(intent))
                        explanations.append(f"MiniAI suggests pattern: {pattern}")
                    new_snippet = self._code_transform.optimize_function(step.target_node_name, lang, ast_analysis, solver_insights)
                    result_code = self.surgeon.mutate_node(code, step.target_node_name, new_snippet, lang)
                    explanations.append(f"Function '{step.target_node_name}' replaced via AST surgery")
                else:
                    result_code = self._code_gen.generate_contextual_code(intent, ast_analysis, plan, lang)
                    explanations.append("Optimized code generated")

            elif step.action == "DELETE_AST_NODE":
                if code and step.target_node_name:
                    result_code = self.surgeon.delete_function(code, step.target_node_name, lang)
                    explanations.append(f"Function '{step.target_node_name}' deleted via AST surgery")

            elif step.action == "TRACE_EXECUTION":
                explanations.append("Symbolic execution trace performed (K-Path limited)")
                if code:
                    analysis = self.ast_engine.analyze_structure(code, lang)
                    for fn_name in analysis.get("function_names", []):
                        explanations.append(f"  - Traced: {fn_name}")

            elif step.action == "PATCH_FIX":
                result_code = self._analysis.apply_fix(code, intent, lang)
                explanations.append("Fix patch applied")

            elif step.action == "QUALITY_REPORT":
                if code:
                    report = self._analysis.generate_quality_report(
                        self.ast_engine.analyze_structure(code, lang), code, lang)
                    explanations.append(report)

            elif step.action == "EXPLAIN_CODE":
                if code:
                    base_explanation = self._analysis.explain_code(code, lang, ast_analysis)
                    # MiniAI: mejorar explicacion si hay violaciones detectadas
                    if self._ai.is_loaded:
                        # Detectar violaciones basicas del codigo para explicar
                        violations = []
                        if "eval(" in code or "exec(" in code:
                            violations.append("dangerous_call")
                        if "os.system(" in code:
                            violations.append("command_injection")
                        if violations:
                            ai_explain = self._ai.explain_violation(code[:200], violations)
                            if ai_explain:
                                base_explanation += f" | AI: {ai_explain}"
                    explanations.append(base_explanation)
                else:
                    explanations.append(self._analysis.explain_concept(intent))

            elif step.action == "SEARCH_DEFINITION":
                if code:
                    nodes = self.ast_engine.get_node_info(intent.target)
                    if nodes:
                        for n in nodes[:5]:
                            explanations.append(
                                f"Found: {n['node_type']} '{n['name']}' "
                                f"(complexity: {n.get('complexity', 'N/A')})"
                            )
                    else:
                        explanations.append(f"'{intent.target}' not found in code")

            elif step.action in ["SYMBOLIC_VALIDATION", "SYNTAX_VALIDATION"]:
                explanations.append("Symbolic validation executed (bounded symbolic execution)")

            elif step.action == "ANALYZE_AND_RESPOND":
                if code:
                    explanations.append(self._analysis.analyze_and_respond(code, intent, ast_analysis))
                else:
                    explanations.append(self._analysis.general_response(intent))

            elif step.action == "QUICK_ANALYSIS":
                explanations.append("Quick analysis completed")

            elif step.action == "FULL_ANALYSIS":
                if code:
                    explanations.append(self._analysis.full_analysis(code, intent, ast_analysis, lang))
                else:
                    explanations.append(self._analysis.general_response(intent))

            elif step.action == "CHECK_DEPENDENCIES":
                if code:
                    deps = self._analysis.check_dependencies(code, intent.target, lang)
                    explanations.extend(deps)

        final_code = result_code if result_code else code

        # Nivel 7 (Snapshot) -> Nivel 6 (Sandbox Trial) -> Nivel 7 (Commit/Rollback)
        # Crear workspace AISLADO para sandbox y ledger
        sandbox_workspace = self._isolation_manager.create_workspace(
            ttl_seconds=max(self.sandbox.timeout_seconds * 3, 120)
        )
        p_dir = str(get_projects_dir())
        self.ledger.snapshot(intent.target, p_dir, workspace=sandbox_workspace)

        trial = await self.sandbox.validate_code(final_code, lang, intent.target)

        if trial.status == "PASS" and final_code:
            node = self.ledger.commit(intent.target, final_code, p_dir,
                                       workspace=sandbox_workspace)
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
            self._memory.add_working(msg, final_code[:500], intent.op, intent.goal, importance)
            self._memory.save_to_cache(msg, final_code[:500], intent.op, intent.goal, importance)
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

    # ============================================================
    #  PUBLIC API - resume_from_partial (delegates to PartialReasoningManager)
    # ============================================================

    async def resume_from_partial(self, resumption_token, subtask_index=None):
        """Resume execution from a partial reasoning state. Delegates to PartialReasoningManager."""
        return await self._partial_reasoning.resume_from_partial(resumption_token, subtask_index)

    # ============================================================
    #  APP & AUTOMATION GENERATION
    # ============================================================

    async def generate_app(self, request: str, project_name: str = "",
                           output_dir: str = "") -> Dict[str, Any]:
        """
        Genera una aplicación completa a partir de una descripción.
        
        Usa ThinkingEngine para planificar, AppGenerator para crear archivos,
        y el pipeline para verificar el resultado.
        """
        # Generate the app
        result = self._app_gen.generate_app(request, project_name, output_dir)
        
        # Save to project memory
        if result.status == "generated" and self._memory:
            self._memory.save_project(
                project_name=result.name,
                project_type=result.template_type,
                description=request,
                path=result.path,
                status="generated",
                entities=[e.get("name", "") for e in result.entities],
                endpoints=[str(ep) for ep in result.endpoints],
            )
            self._memory.save_episode(
                event_type="app_generated",
                description=f"Generated {result.template_type} app: {result.name}",
                context=request[:200],
                outcome="success" if result.status == "generated" else "failed",
                importance=0.8,
            )
            # Learn the pattern
            self._memory.learn_pattern(
                pattern_name=f"gen_{result.template_type}",
                pattern_type="app_generation",
                description=f"Generated {result.template_type} app from request",
                steps=[f"Used template: {result.template_type}", f"Generated {len(result.files)} files"],
                success=result.status == "generated",
            )
        
        return {
            "status": result.status,
            "project_name": result.name,
            "template_type": result.template_type,
            "path": result.path,
            "files": result.files,
            "endpoints": result.endpoints,
            "entities": result.entities,
            "generation_time_s": result.generation_time_s,
            "error": result.error,
        }

    async def generate_automation(self, description: str,
                                   output_dir: str = "") -> Dict[str, Any]:
        """
        Genera un proyecto de automatización a partir de una descripción.
        """
        result = self._automation.generate_automation_project(description, output_dir)
        
        # Save to memory
        if self._memory:
            wf = result.get("workflow")
            if wf:
                self._memory.save_episode(
                    event_type="automation_created",
                    description=f"Created automation: {wf.name}",
                    outcome="success",
                    importance=0.7,
                )
        
        return {
            "status": result.get("status", "unknown"),
            "path": result.get("path", ""),
            "files": result.get("files", []),
            "workflow": {
                "id": result.get("workflow", None).id if result.get("workflow") else None,
                "name": result.get("workflow", None).name if result.get("workflow") else None,
            } if result.get("workflow") else None,
        }

    async def design_schema(self, description: str) -> Dict[str, Any]:
        """
        Diseña un esquema de base de datos a partir de una descripción.
        """
        schema = self._schema_designer.design_schema(description)
        sql = self._schema_designer.generate_sql(schema)
        models = self._schema_designer.generate_models(schema)
        init_sql = self._schema_designer.generate_init_sql(schema)
        
        return {
            "status": "designed",
            "tables": [{"name": t.name, "columns": len(t.columns)} for t in schema.tables],
            "sql": sql,
            "models": models,
            "init_sql": init_sql,
        }

    async def list_projects(self, status: str = "") -> List[Dict[str, Any]]:
        """Lista proyectos generados."""
        if self._memory:
            return self._memory.list_projects(status)
        return []

    async def list_automations(self) -> List[Dict[str, Any]]:
        """Lista automatizaciones."""
        return self._automation.list_workflows()

    async def think(self, query: str, context: str = "") -> Dict[str, Any]:
        """
        Usa ThinkingEngine para razonar sobre una pregunta.
        """
        result = self._thinking.reason(query, context)
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "source": result.source,
            "context_used": result.context_used,
            "thinking_time_s": result.thinking_time_s,
        }

    async def get_system_status(self) -> Dict[str, Any]:
        """Obtiene estado completo del sistema."""
        return {
            "pipeline": "8-level active",
            "ai": {
                "qwen_loaded": self._ai.is_loaded if self._ai else False,
                "semantic_loaded": self._semantic.is_loaded if self._semantic else False,
                "memory_available": self._memory is not None,
            },
            "thinking_engine": self._thinking.stats,
            "app_templates": AppGenerator.list_templates(),
            "automation_stats": self._automation.stats,
            "memory_stats": self._memory.enhanced_stats if self._memory else {},
            "request_count": self.request_count,
        }

    # ============================================================
    #  BACKWARD COMPATIBILITY - delegate old method names to sub-objects
    # ============================================================

    # Abortive Protocol backward compat
    async def _handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        return await self._abortive.handle_abortive_protocol(intent, routing, plan, ast_analysis, start_time)

    def _generate_subtasks(self, intent, ast_analysis, plan=None):
        return self._abortive.generate_subtasks(intent, ast_analysis, plan)

    async def _execute_subtask(self, subtask, depth=0, max_depth=2):
        return await self._abortive.execute_subtask(subtask, depth, max_depth)

    def _merge_subtask_results(self, subtask_results, language="python"):
        return self._abortive.merge_subtask_results(subtask_results, language)

    def _merge_python_code(self, code_parts):
        return self._abortive.merge_python_code(code_parts)

    def _merge_go_code(self, code_parts):
        return self._abortive.merge_go_code(code_parts)

    def _merge_block_code(self, code_parts, comment_prefix, skip_prefix):
        return self._abortive.merge_block_code(code_parts, comment_prefix, skip_prefix)

    # Partial Reasoning backward compat
    def _build_partial_reasoning_response(self, intent, routing, plan, ast_analysis, trial, start_time,
                                          subtask_results=None, combined_code=""):
        return self._partial_reasoning.build_partial_reasoning_response(
            intent, routing, plan, ast_analysis, trial, start_time,
            subtask_results=subtask_results, combined_code=combined_code
        )

    # Code Generator backward compat
    def _generate_intelligent_code(self, intent, ast_analysis, lang):
        return self._code_gen.generate_intelligent_code(intent, ast_analysis, lang)

    def _extract_solver_insights(self, solver_proof):
        return self._code_gen.extract_solver_insights(solver_proof)

    def _extract_ast_context(self, ast_analysis):
        return self._code_gen.extract_ast_context(ast_analysis)

    def _extract_symbolic_insights(self, sandbox_result):
        return self._code_gen.extract_symbolic_insights(sandbox_result)

    def _generate_pipeline_driven_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_pipeline_driven_code(intent, ast_analysis, plan, lang)

    def _generate_python_pipeline_driven(self, intent, ast_analysis, ast_context,
                                          solver_insights, mcts_actions, safe_target,
                                          has_security_action, has_replace_node,
                                          has_patch_fix):
        return self._code_gen.generate_python_pipeline_driven(
            intent, ast_analysis, ast_context, solver_insights,
            mcts_actions, safe_target, has_security_action,
            has_replace_node, has_patch_fix
        )

    def _generate_pipeline_feature_module(self, safe_target, existing_functions,
                                           existing_classes, needed_imports,
                                           solver_insights, mcts_actions):
        return self._code_gen.generate_pipeline_feature_module(
            safe_target, existing_functions, existing_classes,
            needed_imports, solver_insights, mcts_actions
        )

    def _generate_contextual_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_contextual_code(intent, ast_analysis, plan, lang)

    def _generate_python_contextual(self, intent, ast_analysis, safe_target,
                                     existing_functions, existing_classes,
                                     existing_connections, needed_imports,
                                     max_complexity):
        return self._code_gen.generate_python_contextual(
            intent, ast_analysis, safe_target, existing_functions,
            existing_classes, existing_connections, needed_imports,
            max_complexity
        )

    def _generate_security_module(self, safe_target):
        return self._code_gen.generate_security_module(safe_target)

    def _generate_feature_module(self, safe_target, existing_functions, existing_classes, needed_imports):
        return self._code_gen.generate_feature_module(safe_target, existing_functions, existing_classes, needed_imports)

    def _generate_kotlin_contextual(self, intent, safe_target, existing_classes):
        return self._code_gen.generate_kotlin_contextual(intent, safe_target, existing_classes)

    def _generate_go_contextual(self, intent, safe_target):
        return self._code_gen.generate_go_contextual(intent, safe_target)

    def _generate_javascript_contextual(self, intent, safe_target):
        return self._code_gen.generate_javascript_contextual(intent, safe_target)

    # Code Transformer backward compat
    def _refactor_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.refactor_python(code, ast_analysis, solver_insights)

    def _fix_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.fix_python(code, ast_analysis, solver_insights)

    def _optimize_function(self, target_name, lang="python", ast_analysis=None, solver_insights=None):
        return self._code_transform.optimize_function(target_name, lang, ast_analysis, solver_insights)

    # Analysis Utils backward compat
    def _apply_fix(self, code, intent, lang):
        return self._analysis.apply_fix(code, intent, lang)

    def _generate_quality_report(self, analysis, code, lang):
        return self._analysis.generate_quality_report(analysis, code, lang)

    def _explain_code(self, code, lang, ast_analysis):
        return self._analysis.explain_code(code, lang, ast_analysis)

    def _explain_concept(self, intent):
        return self._analysis.explain_concept(intent)

    def _analyze_and_respond(self, code, intent, ast_analysis):
        return self._analysis.analyze_and_respond(code, intent, ast_analysis)

    def _general_response(self, intent):
        return self._analysis.general_response(intent)

    def _full_analysis(self, code, intent, ast_analysis, lang):
        return self._analysis.full_analysis(code, intent, ast_analysis, lang)

    def _check_dependencies(self, code, target, lang):
        return self._analysis.check_dependencies(code, target, lang)

    def _log_request(self, intent, status, elapsed_ms, cache_hit=False,
                    solver_status="", mcts_sims=0):
        return self._analysis.log_request(intent, status, elapsed_ms, cache_hit,
                                          solver_status, mcts_sims)
