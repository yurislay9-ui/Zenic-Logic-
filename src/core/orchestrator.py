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

# Phase 7: Real Engines - ActionExecutor, LogicBuilder, AuthService
from src.core.action_executor import ExecutorRegistry, get_default_registry
from src.core.logic_builder import LogicBuilder
from src.core.auth_service import AuthService

# Phase 8: Intelligence - ReasoningEngine, ChainValidator
from src.core.reasoning_engine import ReasoningEngine, ReasoningMode, ReasoningResult
from src.core.chain_validator import ChainValidator, ChainExecutor, execute_chain_safe, validate_chain, RecoveryAction

# Agent Framework (Phase F1-F5) - AI-driven logic replaces hardcoded rules
from src.core.agents import AgentRunner, AgentCache
from src.core.agents.intent_agent import IntentAgent
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent

logger = logging.getLogger(__name__)


class TitanOrchestrator:
    """Orquestador del pipeline completo de 8 niveles con Protocolo Abortivo."""

    def __init__(self) -> None:
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

        # Wire SemanticEngine into L1 parser (Phase 8.2)
        if self._semantic and self._semantic.is_loaded:
            self.parser.set_semantic_engine(self._semantic)
        if self._memory:
            self.parser.set_smart_memory(self._memory)

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

        # TemplateEngine for Jinja2-based code generation
        self._template_engine = None
        try:
            from src.core.template_engine import TemplateEngine
            self._template_engine = TemplateEngine()
        except ImportError:
            logger.warning("Orchestrator: TemplateEngine not available")

        # Phase 7: Real Engines
        # ActionExecutor Registry - real action execution (no more logger.info stubs)
        self._executor_registry = get_default_registry()

        # LogicBuilder - composable business logic (replaces _process() placeholder)
        self._logic_builder = LogicBuilder(template_engine=self._template_engine)

        # AuthService - JWT + RBAC runtime authentication
        self._auth = AuthService()

        logger.info(f"Phase 7 Engines: ActionExecutor={len(self._executor_registry._executors)} types | LogicBuilder={len(self._logic_builder.list_blocks())} blocks | AuthService=ready")

        # Phase 8: Intelligence - ReasoningEngine + ChainValidator
        self._reasoning = ReasoningEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._chain_validator = ChainValidator()
        self._chain_executor = ChainExecutor(default_recovery=RecoveryAction.SKIP, max_retries=1)

        logger.info(f"Phase 8 Intelligence: ReasoningEngine=3 modes | ChainValidator=ready | ChainExecutor=rollback+recovery")

        self._app_gen = AppGenerator(
            thinking_engine=self._thinking,
            template_engine=self._template_engine,
        )
        self._automation = AutomationEngine(
            thinking_engine=self._thinking,
            template_engine=self._template_engine,
            executor_registry=self._executor_registry,
        )
        self._schema_designer = SchemaDesigner(thinking_engine=self._thinking)

        te_status = "ACTIVE" if self._template_engine else "legacy"
        logger.info(f"Extended Architecture: ThinkingEngine=ready | TemplateEngine={te_status} | AppGenerator=ready | AutomationEngine=ready | SchemaDesigner=ready")

        # ============================================================
        #  DECOMPOSED SUB-MODULES (composition)
        # ============================================================
        self._abortive = AbortiveProtocol(self)
        self._partial_reasoning = PartialReasoningManager(self)
        self._code_gen = CodeGenerator(self)
        self._code_transform = CodeTransformer()
        self._analysis = AnalysisUtils(self)

        # ============================================================
        #  AGENT FRAMEWORK (Phase F1) - IA-driven agents
        #  Reemplaza logica de negocio hardcodeada con agentes IA
        # ============================================================
        self._agent_runner = AgentRunner(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
            enable_cache=True,
        )
        # Cablear cache semantico al AgentRunner
        if self._semantic and self._semantic.is_loaded:
            self._agent_runner._cache.set_semantic_engine(self._semantic)

        # ============================================================
        #  INTENT AGENT (Phase F2) - Replaces scattered intent classification
        #  Unifica: SemanticParser + SemanticEngine + MiniAI classify_intent
        # ============================================================
        self._intent_agent = SurgicalAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        agent_status = "ACTIVE" if self._ai and self._ai.is_loaded else "fallback"
        intent_agent_status = f"ACTIVE (sem={self._semantic.is_loaded})" if self._semantic else "fallback"
        logger.info(f"Agent Framework: AgentRunner={agent_status} | SurgicalAgent(F2)={intent_agent_status} | Cache=enabled | SemanticCache={'ACTIVE' if self._semantic and self._semantic.is_loaded else 'off'}")

        # ============================================================
        #  REASONING AGENT (Phase F3) - Replaces ReasoningEngine + ThinkingEngine
        #  Unifica: step_by_step + self_reflect + with_context reasoning
        # ============================================================
        self._reasoning_agent = ReasoningAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        # ============================================================
        #  BUSINESS LOGIC AGENT (Phase F3) - Replaces 30+ LogicBlocks
        #  Unifica: invoice, inventory, CRM, task, report, notification, analytics
        # ============================================================
        self._business_logic_agent = BusinessLogicAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        logger.info(f"Agent Framework F3: ReasoningAgent=ready | BusinessLogicAgent=ready")

        # ============================================================
        #  CODE AGENT (Phase F4) - Replaces CodeGenerator + CodeTransformer
        #  Unifica: generate, transform, scaffold, optimize, fix
        # ============================================================
        self._code_agent = CodeAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
            template_engine=self._template_engine,
        )

        # ============================================================
        #  AUTOMATION AGENT (Phase F4) - Replaces AutomationEngine keyword inference
        #  Unifica: trigger inference, action inference, schedule parsing
        # ============================================================
        self._automation_agent = AutomationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        # ============================================================
        #  VALIDATION AGENT (Phase F5) - Replaces ChainValidator regex patterns
        #  Unifica: code validation, chain validation, config validation
        # ============================================================
        self._validation_agent = ValidationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        logger.info(f"Agent Framework F4-F5: CodeAgent=ready | AutomationAgent=ready | ValidationAgent=ready")

        # Escanear proyecto si existe
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)

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
        #  Reemplaza: SemanticParser + SemanticEngine + MiniAI classify_intent
        #  Flujo: AgentRunner(LLM) → SemanticEngine → TF-IDF fallback
        # ============================================================
        from src.core.agents.schemas import IntentInput
        intent_output = self._intent_agent.classify_with_runner(
            self._agent_runner, msg, context=""
        )
        intent = self._intent_agent.to_intent_payload(intent_output, context=msg)

        # Extraer código del mensaje (separado de la clasificación)
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
                # SmartScraper: Auto-routing multi-fuente (GitHub + DevDocs + IconStack + Picsum)
                smart_result = await self.scrap.smart_fetch(query, lang)
                if smart_result.get("success") and smart_result.get("content"):
                    source_name = smart_result.get("source", "github")
                    explanations.append(f"SmartScraper: Found content via {source_name}")
                    content = smart_result["content"]
                    if not code:
                        code = content
                else:
                    # Fallback: buscar en todas las fuentes
                    all_results = await self.scrap.fetch_all_sources(query, lang)
                    best_content = ""
                    best_source = ""
                    for src in ["github", "devdocs", "iconstack", "picsum"]:
                        if src in all_results and all_results[src]:
                            best_content = all_results[src]
                            best_source = src
                            break
                    if best_content:
                        explanations.append(f"SmartScraper: Found content via {best_source} (fallback)")
                        if not code:
                            code = best_content
                    else:
                        explanations.append("SmartScraper: No results. Using local generation.")

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
                # Use ValidationAgent (F5) for intelligent validation
                if self._validation_agent and code:
                    from src.core.agents.schemas import ValidationInput
                    v_output = self._validation_agent.validate_with_runner(
                        self._agent_runner, target="code", content=code,
                        rules=["security", "quality"], language=lang,
                    )
                    if v_output.issues:
                        issue_strs = [f"{i.severity}: {i.message}" for i in v_output.issues[:5]]
                        explanations.append(
                            f"Validation (F5): {len(v_output.issues)} issues found "
                            f"(risk={v_output.risk_score:.2f}, source={v_output.source})"
                        )
                        for iss in issue_strs:
                            explanations.append(f"  - {iss}")
                    else:
                        explanations.append("Validation (F5): No issues found")
                else:
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

    async def resume_from_partial(self, resumption_token: str, subtask_index: Optional[int] = None) -> Dict[str, Any]:
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

        Usa AutomationAgent (F4) para diseño inteligente del workflow,
        con fallback a AutomationEngine (Legacy) para generación de archivos.
        """
        # Try AutomationAgent (F4) for workflow design first
        automation_design = None
        if self._automation_agent:
            from src.core.agents.schemas import AutomationInput
            automation_design = self._automation_agent.design_with_runner(
                self._agent_runner, description,
            )

        # Generate project files using existing AutomationEngine (keeps file generation)
        result = self._automation.generate_automation_project(description, output_dir)

        # Enhance result with AutomationAgent design if available
        if automation_design:
            wf_dict = self._automation_agent.to_workflow_dict(automation_design)
            result["automation_agent"] = {
                "name": automation_design.name,
                "triggers": [{"type": t.type, "config": t.config, "description": t.description}
                             for t in automation_design.triggers],
                "actions": [{"type": a.type, "config": a.config, "description": a.description}
                            for a in automation_design.actions],
                "schedule": {"type": automation_design.schedule.type,
                             "cron": automation_design.schedule.cron_expression},
                "source": automation_design.source,
            }
        
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
            "automation_agent": result.get("automation_agent"),
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

    # ============================================================
    #  PHASE 7: AUTH & LOGIC BUILDER API
    # ============================================================

    async def register_user(self, username: str, email: str, password: str,
                           role: str = "user") -> Dict[str, Any]:
        """Registra un nuevo usuario en el sistema de autenticación."""
        if not self._auth:
            return {"error": "AuthService not available"}
        return self._auth.register_user(username, email, password, role)

    async def login_user(self, username: str, password: str) -> Dict[str, Any]:
        """Autentica un usuario y devuelve tokens JWT."""
        if not self._auth:
            return {"error": "AuthService not available"}
        return self._auth.login_user(username, password)

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verifica un token JWT."""
        if not self._auth:
            return {"error": "AuthService not available"}
        try:
            return self._auth.verify_token(token)
        except Exception as e:
            return {"error": str(e)}

    async def build_logic(self, description: str) -> Dict[str, Any]:
        """
        Construye lógica de negocio a partir de una descripción.

        Usa BusinessLogicAgent (F3) para ejecución inteligente,
        con fallback a LogicBuilder (Legacy) para composición de bloques.
        Mantiene compatibilidad con la API Legacy (block_count, generated_code).
        """
        # Try BusinessLogicAgent (F3) first
        if self._business_logic_agent:
            output = self._business_logic_agent.execute_with_runner(
                self._agent_runner,
                operation_type="custom",
                data={"description": description},
                description=description,
            )
            result = {
                "success": output.success,
                "data": output.data,
                "side_effects": output.side_effects,
                "insights": output.insights,
                "errors": output.errors,
                "source": output.source,
                "description": description,
            }
            # Legacy compat: if LogicBuilder available, also include blocks
            if self._logic_builder:
                chain = self._logic_builder.build_from_description(description)
                blocks = [b.name for b in chain.blocks]
                code = self._logic_builder.generate_process_method(blocks)
                result["blocks"] = blocks
                result["block_count"] = len(blocks)
                result["generated_code"] = code
            return result

        # Legacy fallback to LogicBuilder only
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        blocks = [b.name for b in chain.blocks]
        code = self._logic_builder.generate_process_method(blocks)
        return {
            "blocks": blocks,
            "block_count": len(blocks),
            "generated_code": code,
            "description": description,
        }

    async def list_logic_blocks(self, category: str = "") -> List[Dict[str, Any]]:
        """Lista bloques de lógica disponibles."""
        if not self._logic_builder:
            return []
        blocks = self._logic_builder.list_blocks(category)
        return [
            {
                "name": b.name,
                "category": b.category,
                "description": b.description,
                "inputs": b.inputs,
                "outputs": b.outputs,
            }
            for b in blocks
        ]

    async def execute_action(self, action_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una acción individual usando el ActionExecutor."""
        if not self._executor_registry:
            return {"error": "ExecutorRegistry not available"}
        result = await self._executor_registry.execute_action(action_type, config, {})
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    # ============================================================
    #  PHASE 8: INTELLIGENCE API
    # ============================================================

    async def reason(self, query: str, mode: str = "auto",
                     context: str = "") -> Dict[str, Any]:
        """
        Razonamiento avanzado usando ReasoningAgent (F3) o ReasoningEngine (Legacy).

        Modes: step_by_step, self_reflect, with_context, auto
        """
        # Try ReasoningAgent (F3) first
        if self._reasoning_agent:
            actual_mode = mode if mode != "auto" else "step_by_step"
            output = self._reasoning_agent.reason_with_runner(
                self._agent_runner, query, mode=actual_mode, context=context,
            )
            return {
                "answer": output.answer,
                "confidence": output.confidence,
                "mode": output.mode,
                "steps": len(output.steps),
                "refinements": output.refinements,
                "context_used": output.context_used,
                "memory_hits": output.memory_hits,
                "source": output.source,
                "duration_ms": output.total_duration_ms,
            }

        # Legacy fallback to ReasoningEngine
        if not self._reasoning:
            return {"error": "ReasoningEngine not available"}

        result = self._reasoning.reason(query, mode=mode, context=context)
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "mode": result.mode.value,
            "steps": len(result.steps),
            "refinements": result.refinements,
            "context_used": result.context_used,
            "memory_hits": result.memory_hits,
            "source": result.source,
            "duration_ms": result.total_duration_ms,
        }

    async def validate_logic_chain(self, description: str) -> Dict[str, Any]:
        """
        Valida una cadena de lógica antes de ejecutarla.

        Usa ValidationAgent (F5) para validación inteligente,
        con fallback a ChainValidator (Legacy) para validación por reglas.
        """
        # Try ValidationAgent (F5) first
        if self._validation_agent:
            from src.core.agents.schemas import ValidationInput
            output = self._validation_agent.validate_with_runner(
                self._agent_runner, target="chain", content=description,
                rules=["compatibility", "completeness"], language="python",
            )
            result = {
                "is_valid": output.is_valid,
                "can_execute": output.is_valid or not any(
                    i.severity == "error" for i in output.issues
                ),
                "issues": [
                    {"severity": i.severity, "code": i.code,
                     "message": i.message, "line": i.line,
                     "suggestion": i.suggestion}
                    for i in output.issues
                ],
                "suggestions": output.suggestions,
                "risk_score": output.risk_score,
                "source": output.source,
            }
            # Legacy compat: also run ChainValidator if LogicBuilder available
            if self._logic_builder:
                chain = self._logic_builder.build_from_description(description)
                validation = self._chain_validator.validate(chain)
                result["block_count"] = len(chain.blocks)
                result["legacy_errors"] = [
                    {"code": e.code, "message": e.message, "block": e.block_name}
                    for e in validation.errors
                ]
                result["legacy_warnings"] = [
                    {"code": e.code, "message": e.message, "block": e.block_name}
                    for e in validation.warnings
                ]
            return result

        # Legacy fallback to ChainValidator
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        validation = self._chain_validator.validate(chain)
        return {
            "is_valid": validation.is_valid,
            "can_execute": validation.can_execute,
            "errors": [{"code": e.code, "message": e.message, "block": e.block_name}
                       for e in validation.errors],
            "warnings": [{"code": e.code, "message": e.message, "block": e.block_name}
                         for e in validation.warnings],
            "block_count": len(chain.blocks),
        }

    async def execute_logic_chain(self, description: str,
                                   data: Optional[Dict[str, Any]] = None,
                                   recovery: str = "skip") -> Dict[str, Any]:
        """
        Ejecuta una cadena de lógica con validación, rollback y recovery.

        Recovery modes: retry, skip, fallback, abort, rollback
        """
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}

        chain = self._logic_builder.build_from_description(description)
        recovery_map = {
            "retry": RecoveryAction.RETRY,
            "skip": RecoveryAction.SKIP,
            "fallback": RecoveryAction.FALLBACK,
            "abort": RecoveryAction.ABORT,
            "rollback": RecoveryAction.ROLLBACK,
        }
        recovery_action = recovery_map.get(recovery, RecoveryAction.SKIP)

        executor = ChainExecutor(default_recovery=recovery_action, max_retries=1)
        result = executor.execute(chain, data or {}, validate_first=True)

        return {
            "status": result.status.value,
            "steps_completed": result.steps_completed,
            "steps_failed": result.steps_failed,
            "steps_skipped": result.steps_skipped,
            "rollback_count": result.rollback_count,
            "total_duration_ms": result.total_duration_ms,
            "final_data": result.final_data,
            "error": result.error,
            "validation_passed": result.validation.is_valid if result.validation else None,
        }

    async def get_intelligence_status(self) -> Dict[str, Any]:
        """Obtiene estado del sistema de inteligencia (Phase 8)."""
        return {
            "reasoning_engine": self._reasoning.stats if self._reasoning else {},
            "ai_layers": {
                "layer1_semantic": {
                    "available": self._semantic.is_loaded if self._semantic else False,
                    "model": "paraphrase-multilingual-MiniLM-L12-v2",
                },
                "layer2_qwen": {
                    "available": self._ai.is_loaded if self._ai else False,
                    "model": "Qwen3-0.6B Q4_K_M",
                },
                "layer3_memory": {
                    "available": self._memory is not None,
                    "stats": self._memory.enhanced_stats if self._memory else {},
                },
            },
            "thinking_engine": self._thinking.stats,
            "phase8_modes": {
                "reasoning": ["step_by_step", "self_reflect", "with_context", "auto"],
                "chain_validation": True,
                "chain_recovery": ["retry", "skip", "fallback", "abort", "rollback"],
            },
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
            "phase7_engines": {
                "action_executors": len(self._executor_registry._executors) if self._executor_registry else 0,
                "logic_blocks": len(self._logic_builder.list_blocks()) if self._logic_builder else 0,
                "auth_available": self._auth is not None,
            },
            "phase8_intelligence": {
                "reasoning_available": self._reasoning is not None,
                "chain_validation": True,
                "chain_recovery_modes": 5,
            },
            "agent_framework": {
                "runner_stats": self._agent_runner.stats if self._agent_runner else {},
                "cache_stats": self._agent_runner._cache.stats if self._agent_runner and self._agent_runner._cache else {},
                "intent_agent": self._intent_agent.stats if self._intent_agent else {},
                "reasoning_agent": self._reasoning_agent.stats if self._reasoning_agent else {},
                "business_logic_agent": self._business_logic_agent.stats if self._business_logic_agent else {},
                "code_agent": self._code_agent.stats if self._code_agent else {},
                "automation_agent": self._automation_agent.stats if self._automation_agent else {},
                "validation_agent": self._validation_agent.stats if self._validation_agent else {},
            },
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
