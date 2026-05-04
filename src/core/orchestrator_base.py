"""
BaseOrchestrator - Shared base class for TitanOrchestrator and DAGOrchestrator.

Extracts all duplicated initialization, public API, backward-compat delegation,
and shared properties from both orchestrator implementations.

Both TitanOrchestrator (sequential) and DAGOrchestrator (graph-based) share:
- 8-level pipeline component initialization
- 3-layer AI architecture wiring
- Extended architecture (thinking, template, app, automation, schema)
- Phase 7 engines (executor_registry, logic_builder, auth)
- Phase 8 intelligence (reasoning, chain_validator, chain_executor)
- Decomposed sub-modules (abortive, partial, code_gen, code_transform, analysis)
- Agent framework (F1-F5 agents)
- Common state (request_count, locks, pending_resumptions)
- Public API methods (resume_from_partial, generate_app, etc.)
- Backward-compat delegation methods
- Shared properties (model_manager, low_power_mode, etc.)
"""

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
from src.core.shared.sandbox_isolation import (
    get_isolation_manager, SandboxWorkspace, shutdown_isolation
)

# Decomposed modules
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.abortive_protocol import AbortiveProtocol
from src.core.partial_reasoning import PartialReasoningManager
from src.core.code_generator import CodeGenerator
from src.core.code_transformer import CodeTransformer
from src.core.analysis_utils import AnalysisUtils

# Extended AI Architecture
from src.core.thinking_engine import ThinkingEngine, GenerationPlan
from src.core.app_generator import AppGenerator
from src.core.automation_engine import AutomationEngine
from src.core.schema_designer import SchemaDesigner

# Phase 7: Real Engines
from src.core.action_executor import ExecutorRegistry, get_default_registry
from src.core.logic_builder import LogicBuilder
from src.core.auth_service import AuthService

# Phase 8: Intelligence
from src.core.reasoning_engine import ReasoningEngine, ReasoningMode, ReasoningResult
from src.core.chain_validator import ChainValidator, ChainExecutor, execute_chain_safe, validate_chain, RecoveryAction

# Agent Framework (F1-F5)
from src.core.agents import AgentRunner, AgentCache
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent

logger = logging.getLogger(__name__)


class BaseOrchestrator:
    """
    Shared base for TitanOrchestrator and DAGOrchestrator.

    Contains all initialization, public API, backward-compat delegation,
    and shared properties that were previously duplicated between the two
    orchestrator implementations.
    """

    # ============================================================
    #  INITIALIZATION METHODS (called by subclass __init__)
    # ============================================================

    def _init_pipeline_components(self, settings: Dict[str, Any]) -> None:
        """Initialize the 8-level pipeline components."""
        initialize_databases()
        self.settings = settings
        self.p_dir = settings.get("project_dir", ".")  # Deprecated: use project_dir property

        self.parser = SemanticParser()
        self.router = MacroRouter()
        self.ast_engine = GraphASTEngine()
        self.planner = APAPlanner()
        self.scrap = GitHubScrapAgent()
        self.surgeon = ASTSurgeon()
        self.sandbox = ReflexionSandbox()
        self.ledger = MerkleLedger()
        self.cache = TheoremCache()

    def _init_ai_architecture(self, semantic, ai, memory) -> None:
        """Wire the 3-layer AI architecture and connect to parser."""
        self._semantic = semantic
        self._ai = ai
        self._memory = memory

        # Wire SemanticEngine into L1 parser
        if self._semantic and self._semantic.is_loaded:
            self.parser.set_semantic_engine(self._semantic)
        if self._memory is not None:
            self.parser.set_smart_memory(self._memory)

    def _init_extended_architecture(self, thinking_engine=None,
                                     template_engine=None,
                                     executor_registry=None,
                                     logic_builder=None,
                                     auth=None,
                                     reasoning=None,
                                     chain_validator=None,
                                     chain_executor=None,
                                     app_gen=None,
                                     automation=None,
                                     schema_designer=None) -> None:
        """Initialize thinking, template, app, automation, schema engines."""
        self._thinking = thinking_engine
        self._template_engine = template_engine
        self._executor_registry = executor_registry
        self._logic_builder = logic_builder
        self._auth = auth
        self._reasoning = reasoning
        self._chain_validator = chain_validator
        self._chain_executor = chain_executor
        self._app_gen = app_gen
        self._automation = automation
        self._schema_designer = schema_designer

    def _init_phase7_engines(self, template_engine=None) -> None:
        """Initialize executor_registry, logic_builder, auth."""
        self._executor_registry = get_default_registry()
        self._logic_builder = LogicBuilder(template_engine=template_engine)
        self._auth = AuthService()

        logger.info(
            f"Phase 7 Engines: ActionExecutor="
            f"{len(getattr(self._executor_registry, 'list_types', lambda: [])())} types | "
            f"LogicBuilder={len(self._logic_builder.list_blocks())} blocks | "
            f"AuthService=ready"
        )

    def _init_phase8_intelligence(self) -> None:
        """Initialize reasoning, chain_validator, chain_executor."""
        self._reasoning = ReasoningEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._chain_validator = ChainValidator()
        self._chain_executor = ChainExecutor(
            default_recovery=RecoveryAction.SKIP, max_retries=1
        )

        logger.info(
            "Phase 8 Intelligence: ReasoningEngine=3 modes | "
            "ChainValidator=ready | ChainExecutor=rollback+recovery"
        )

    def _init_extended_with_defaults(self) -> None:
        """
        Initialize extended architecture using already-set _ai, _semantic, _memory.

        This is the convenience method used by TitanOrchestrator which creates
        all components inline (vs DAGOrchestrator which may customize).
        """
        # ThinkingEngine
        self._thinking = ThinkingEngine(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        # TemplateEngine
        self._template_engine = None
        try:
            from src.core.template_engine import TemplateEngine
            self._template_engine = TemplateEngine()
        except ImportError:
            logger.warning("Orchestrator: TemplateEngine not available")

        # Phase 7
        self._init_phase7_engines(template_engine=self._template_engine)

        # Phase 8
        self._init_phase8_intelligence()

        # App & Automation
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
        logger.info(
            f"Extended Architecture: ThinkingEngine=ready | "
            f"TemplateEngine={te_status} | AppGenerator=ready | "
            f"AutomationEngine=ready | SchemaDesigner=ready"
        )

    def _init_decomposed_modules(self) -> None:
        """Initialize abortive, partial, code_gen, code_transform, analysis."""
        self._abortive = AbortiveProtocol(self)
        self._partial_reasoning = PartialReasoningManager(self)
        self._code_gen = CodeGenerator(self)
        self._code_transform = CodeTransformer()
        self._analysis = AnalysisUtils(self)

    def _init_agent_framework(self, context_agent=None, criticality_agent=None,
                               titan_agent=None, fractal_gen=None) -> None:
        """
        Initialize all F1-F5 agents.

        Args:
            context_agent: Optional ContextAgent (only DAGOrchestrator uses this)
            criticality_agent: Optional CriticalityAgent (only DAGOrchestrator)
            titan_agent: Optional TitanAgent (only DAGOrchestrator)
            fractal_gen: Optional FractalGenerator (only DAGOrchestrator)
        """
        # AgentRunner (F1 core)
        self._agent_runner = AgentRunner(
            mini_ai=self._ai,
            semantic_engine=self._semantic,
            smart_memory=self._memory,
            enable_cache=True,
        )
        # Wire semantic cache
        if self._semantic and self._semantic.is_loaded:
            self._agent_runner._cache.set_semantic_engine(self._semantic)

        # SurgicalAgent (F2)
        self._intent_agent = SurgicalAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        agent_status = "ACTIVE" if self._ai and self._ai.is_loaded else "fallback"
        intent_agent_status = (
            f"ACTIVE (sem={self._semantic.is_loaded})"
            if self._semantic else "fallback"
        )
        logger.info(
            f"Agent Framework: AgentRunner={agent_status} | "
            f"SurgicalAgent(F2)={intent_agent_status} | "
            f"Cache=enabled | "
            f"SemanticCache={'ACTIVE' if self._semantic and self._semantic.is_loaded else 'off'}"
        )

        # ReasoningAgent (F3)
        self._reasoning_agent = ReasoningAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        # BusinessLogicAgent (F3)
        self._business_logic_agent = BusinessLogicAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        logger.info("Agent Framework F3: ReasoningAgent=ready | BusinessLogicAgent=ready")

        # CodeAgent (F4)
        self._code_agent = CodeAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
            template_engine=self._template_engine,
        )

        # AutomationAgent (F4)
        self._automation_agent = AutomationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        # ValidationAgent (F5)
        self._validation_agent = ValidationAgent(
            semantic_engine=self._semantic,
            smart_memory=self._memory,
        )

        logger.info(
            "Agent Framework F4-F5: CodeAgent=ready | "
            "AutomationAgent=ready | ValidationAgent=ready"
        )

        # Optional DAG-only agents
        self._context_agent = context_agent
        self._criticality_agent = criticality_agent
        self._titan_agent = titan_agent
        self._fractal_gen = fractal_gen

    def _init_common_state(self) -> None:
        """Initialize common state: request_count, locks, pending resumptions."""
        self.request_count = 0
        self._pending_resumptions = {}
        self._isolation_manager = get_isolation_manager()
        self._current_client_id = "default"

    def _init_god_level_improvements(self) -> None:
        """Initialize niche auto-scraper, context pointer engine, low-power mode."""
        # A) Auto-Scraping YAML
        self._niche_auto_scraper = None
        self._niche_cron = None
        try:
            from src.core.niche_auto_scraper import NicheAutoUpdater, NicheCronScheduler
            if self._template_engine:
                niche_loader = self._template_engine._get_niche_loader()
                if niche_loader:
                    self._niche_auto_scraper = NicheAutoUpdater(
                        niche_loader=niche_loader,
                        scrap_agent=self.scrap,
                    )
                    self._niche_cron = NicheCronScheduler(
                        auto_updater=self._niche_auto_scraper,
                        interval_hours=24,
                    )
                    logger.info("Orchestrator: NicheAutoScraper + Cron initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: NicheAutoScraper not available: {e}")

        # B) Context Pointer Engine
        self._context_pointer_engine = None
        try:
            from src.core.context_pointer_engine import SignatureIndex
            self._context_pointer_engine = SignatureIndex(project_root=self.p_dir)
            logger.info("Orchestrator: ContextPointerEngine initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: ContextPointerEngine not available: {e}")

        # C) Low-Power Sequential Mode
        self._low_power_mode = None
        try:
            from src.core.low_power_sequential import LowPowerSequentialMode
            self._low_power_mode = LowPowerSequentialMode(governor=None)
            logger.info("Orchestrator: LowPowerSequentialMode initialized")
        except ImportError as e:
            logger.debug(f"Orchestrator: LowPowerSequentialMode not available: {e}")

    def _scan_project(self) -> None:
        """Scan project directory if it exists."""
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)

    # ============================================================
    #  PROPERTIES
    # ============================================================

    @property
    def project_dir(self) -> str:
        """Project directory (preferred over deprecated p_dir)."""
        return self.p_dir

    # ============================================================
    #  SHARED PUBLIC API METHODS
    # ============================================================

    async def resume_from_partial(self, resumption_token: str,
                                   subtask_index: Optional[int] = None) -> Dict[str, Any]:
        """Resume execution from a partial reasoning state."""
        return await self._partial_reasoning.resume_from_partial(
            resumption_token, subtask_index
        )

    async def generate_app(self, request: str, project_name: str = "",
                           output_dir: str = "") -> Dict[str, Any]:
        """Genera una aplicacion completa a partir de una descripcion."""
        result = self._app_gen.generate_app(request, project_name, output_dir)

        if result.status == "generated" and self._memory is not None:
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
            self._memory.learn_pattern(
                pattern_name=f"gen_{result.template_type}",
                pattern_type="app_generation",
                description=f"Generated {result.template_type} app from request",
                steps=[f"Used template: {result.template_type}",
                       f"Generated {len(result.files)} files"],
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
        """Genera un proyecto de automatizacion a partir de una descripcion."""
        automation_design = None
        if self._automation_agent:
            from src.core.agents.schemas import AutomationInput
            automation_design = self._automation_agent.design_with_runner(
                self._agent_runner, description,
            )

        result = self._automation.generate_automation_project(description, output_dir)

        if automation_design:
            wf_dict = self._automation_agent.to_workflow_dict(automation_design)
            result["automation_agent"] = {
                "name": automation_design.name,
                "triggers": [
                    {"type": t.type, "config": t.config, "description": t.description}
                    for t in automation_design.triggers
                ],
                "actions": [
                    {"type": a.type, "config": a.config, "description": a.description}
                    for a in automation_design.actions
                ],
                "schedule": {
                    "type": automation_design.schedule.type,
                    "cron": automation_design.schedule.cron_expression,
                },
                "source": automation_design.source,
            }

        if self._memory is not None:
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
        """Disena un esquema de base de datos a partir de una descripcion."""
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
        if self._memory is not None:
            return self._memory.list_projects(status)
        return []

    async def list_automations(self) -> List[Dict[str, Any]]:
        """Lista automatizaciones."""
        return self._automation.list_workflows()

    async def think(self, query: str, context: str = "") -> Dict[str, Any]:
        """Usa ThinkingEngine para razonar sobre una pregunta."""
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
        """Registra un nuevo usuario en el sistema de autenticacion."""
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
        """Construye logica de negocio a partir de una descripcion."""
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
        """Lista bloques de logica disponibles."""
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

    async def execute_action(self, action_type: str,
                             config: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una accion individual usando el ActionExecutor."""
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
        """Razonamiento avanzado usando ReasoningAgent (F3) o ReasoningEngine (Legacy)."""
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
        """Valida una cadena de logica antes de ejecutarla."""
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
        """Ejecuta una cadena de logica con validacion, rollback y recovery."""
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
    #  BACKWARD COMPATIBILITY - Delegate old method names to sub-objects
    # ============================================================

    # Abortive Protocol backward compat
    async def _handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        return await self._abortive.handle_abortive_protocol(
            intent, routing, plan, ast_analysis, start_time
        )

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
        return self._abortive.merge_block_code(
            code_parts, comment_prefix, skip_prefix
        )

    # Partial Reasoning backward compat
    def _build_partial_reasoning_response(self, intent, routing, plan,
                                           ast_analysis, trial, start_time,
                                           subtask_results=None,
                                           combined_code=""):
        return self._partial_reasoning.build_partial_reasoning_response(
            intent, routing, plan, ast_analysis, trial, start_time,
            subtask_results=subtask_results, combined_code=combined_code,
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
        return self._code_gen.generate_pipeline_driven_code(
            intent, ast_analysis, plan, lang
        )

    def _generate_python_pipeline_driven(self, intent, ast_analysis, ast_context,
                                          solver_insights, mcts_actions, safe_target,
                                          has_security_action, has_replace_node,
                                          has_patch_fix):
        return self._code_gen.generate_python_pipeline_driven(
            intent, ast_analysis, ast_context, solver_insights,
            mcts_actions, safe_target, has_security_action,
            has_replace_node, has_patch_fix,
        )

    def _generate_pipeline_feature_module(self, safe_target, existing_functions,
                                           existing_classes, needed_imports,
                                           solver_insights, mcts_actions):
        return self._code_gen.generate_pipeline_feature_module(
            safe_target, existing_functions, existing_classes,
            needed_imports, solver_insights, mcts_actions,
        )

    def _generate_contextual_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_contextual_code(
            intent, ast_analysis, plan, lang
        )

    def _generate_python_contextual(self, intent, ast_analysis, safe_target,
                                     existing_functions, existing_classes,
                                     existing_connections, needed_imports,
                                     max_complexity):
        return self._code_gen.generate_python_contextual(
            intent, ast_analysis, safe_target, existing_functions,
            existing_classes, existing_connections, needed_imports,
            max_complexity,
        )

    def _generate_security_module(self, safe_target):
        return self._code_gen.generate_security_module(safe_target)

    def _generate_feature_module(self, safe_target, existing_functions,
                                  existing_classes, needed_imports):
        return self._code_gen.generate_feature_module(
            safe_target, existing_functions, existing_classes, needed_imports,
        )

    def _generate_kotlin_contextual(self, intent, safe_target, existing_classes):
        return self._code_gen.generate_kotlin_contextual(
            intent, safe_target, existing_classes,
        )

    def _generate_go_contextual(self, intent, safe_target):
        return self._code_gen.generate_go_contextual(intent, safe_target)

    def _generate_javascript_contextual(self, intent, safe_target):
        return self._code_gen.generate_javascript_contextual(intent, safe_target)

    # Code Transformer backward compat
    def _refactor_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.refactor_python(code, ast_analysis, solver_insights)

    def _fix_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.fix_python(code, ast_analysis, solver_insights)

    def _optimize_function(self, target_name, lang="python",
                            ast_analysis=None, solver_insights=None):
        return self._code_transform.optimize_function(
            target_name, lang, ast_analysis, solver_insights,
        )

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
        return self._analysis.log_request(
            intent, status, elapsed_ms, cache_hit, solver_status, mcts_sims,
        )

    # ============================================================
    #  SHARED PROPERTIES
    # ============================================================

    @property
    def model_manager(self):
        """Public accessor for model manager."""
        return getattr(self, '_model_mgr', None)

    @property
    def low_power_mode(self):
        """Public accessor for low power mode."""
        return getattr(self, '_low_power_mode', None)

    @property
    def context_pointer_engine(self):
        """Public accessor for context pointer engine."""
        return getattr(self, '_context_pointer_engine', None)

    def get_niche_cron(self):
        """Public accessor for niche cron scheduler."""
        return getattr(self, '_niche_cron', None)

    def get_niche_auto_scraper(self):
        """Public accessor for niche auto scraper."""
        return getattr(self, '_niche_auto_scraper', None)

    @property
    def abortive(self):
        """Public accessor for abortive protocol."""
        return getattr(self, '_abortive', None)

    @property
    def pending_resumptions(self):
        """Public accessor for pending resumptions dict."""
        return getattr(self, '_pending_resumptions', {})

    @property
    def isolation_manager(self):
        """Public accessor for isolation manager."""
        return getattr(self, '_isolation_manager', None)
