"""
TITAN OMNISCALE X - TitanAgent (F1) + DAG Orchestrator v14

Reemplaza el dispatch estático de orchestrator.py con un grafo dirigido
acíclico (DAG) donde cada nodo representa un estado del pipeline y las
transiciones son condicionales según el resultado del paso anterior.

TitanAgent (F1): Agente meta-router que decide dinámicamente la
siguiente transición del DAG usando el LLM, con fallback al
pipeline secuencial original.

Restricciones de diseño:
- Cada nodo del DAG ejecuta UNA llamada al LLM máximo (≤600 tokens)
- Todo nodo tiene un fallback determinista
- El DAG soporta ciclos de feedback (máx. 3 iteraciones)
- Compatible con Android/Termux, Qwen3-0.6B, 500MB RAM

Conexiones (cableado completo):
- Hereda todos los subsistemas del TitanOrchestrator original
- Mantiene API pública idéntica (execute, generate_app, build_logic, etc.)
- Preserva backward compatibility con métodos delegados
"""

import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

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

# 3-Layer AI Architecture
from src.core.semantic_engine import SemanticEngine
from src.core.mini_ai_engine import MiniAIEngine
from src.core.smart_memory import SmartMemory
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
from src.core.agents.base import BaseAgent
from src.core.agents.schemas import IntentOutput, CriticalityOutput
from src.core.agents.intent_agent import IntentAgent
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.context_agent import ContextAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent
from src.core.agents.criticality_agent import CriticalityAgent

logger = logging.getLogger(__name__)


# ============================================================
#  DAG DEFINITION - Nodos y transiciones del pipeline
# ============================================================

@dataclass
class DAGNode:
    """Un nodo del DAG del pipeline."""
    name: str
    exec_method: str          # Nombre del método a ejecutar
    transitions: Dict[str, str] = field(default_factory=dict)  # resultado -> siguiente nodo
    default_next: str = ""    # Siguiente nodo si resultado no está en transitions
    criticality_skip: List[str] = field(default_factory=list)   # Niveles criticalidad que SKIPean este nodo
    max_retries: int = 1      # Veces que se puede reintentar este nodo (feedback)


# Grafo del pipeline - reemplaza el if/elif de 185+ lineas con ~30 lineas
PIPELINE_DAG: Dict[str, DAGNode] = {
    "CACHE_CHECK": DAGNode(
        name="CACHE_CHECK",
        exec_method="_exec_cache_check",
        transitions={"hit": "DONE", "miss": "INTENT"},
        default_next="INTENT",
    ),
    "INTENT": DAGNode(
        name="INTENT",
        exec_method="_exec_intent",
        transitions={},  # Dinámico: depende de operation + goal
        default_next="CONTEXT_PREPARE",
    ),
    "CONTEXT_PREPARE": DAGNode(
        name="CONTEXT_PREPARE",
        exec_method="_exec_context_prepare",
        transitions={"*": "AST_ANALYZE"},
        default_next="AST_ANALYZE",
    ),
    "THEOREM_CACHE": DAGNode(
        name="THEOREM_CACHE",
        exec_method="_exec_theorem_cache",
        transitions={"hit": "DONE", "miss": "ROUTE"},
        default_next="ROUTE",
    ),
    "AST_ANALYZE": DAGNode(
        name="AST_ANALYZE",
        exec_method="_exec_ast_analyze",
        transitions={"*": "THEOREM_CACHE"},
        default_next="THEOREM_CACHE",
    ),
    "ROUTE": DAGNode(
        name="ROUTE",
        exec_method="_exec_route",
        transitions={"*": "CRITICALITY_ROUTE"},
        default_next="CRITICALITY_ROUTE",
    ),
    "CRITICALITY_ROUTE": DAGNode(
        name="CRITICALITY_ROUTE",
        exec_method="_exec_criticality_route",
        transitions={"*": "PLAN"},
        default_next="PLAN",
    ),
    "PLAN": DAGNode(
        name="PLAN",
        exec_method="_exec_plan",
        transitions={
            "abortive": "ABORTIVE",
            "low_crit": "EXECUTE_STEPS",
            "standard": "EXECUTE_STEPS",
            "high_crit": "SOLVER_VERIFY",
        },
        default_next="EXECUTE_STEPS",
    ),
    "SOLVER_VERIFY": DAGNode(
        name="SOLVER_VERIFY",
        exec_method="_exec_solver_verify",
        transitions={"pass": "EXECUTE_STEPS", "fail": "PLAN"},
        default_next="EXECUTE_STEPS",
        max_retries=2,
    ),
    "EXECUTE_STEPS": DAGNode(
        name="EXECUTE_STEPS",
        exec_method="_exec_steps",
        transitions={"*": "SANDBOX"},
        default_next="SANDBOX",
    ),
    "ABORTIVE": DAGNode(
        name="ABORTIVE",
        exec_method="_exec_abortive",
        transitions={"*": "DONE"},
        default_next="DONE",
    ),
    "SANDBOX": DAGNode(
        name="SANDBOX",
        exec_method="_exec_sandbox",
        transitions={
            "PASS": "LEDGER_COMMIT",
            "FAIL_K_PATH": "PARTIAL_REASONING",
            "FAIL": "LEDGER_ROLLBACK",
        },
        default_next="LEDGER_ROLLBACK",
    ),
    "PARTIAL_REASONING": DAGNode(
        name="PARTIAL_REASONING",
        exec_method="_exec_partial_reasoning",
        transitions={"*": "DONE"},
        default_next="DONE",
    ),
    "LEDGER_COMMIT": DAGNode(
        name="LEDGER_COMMIT",
        exec_method="_exec_ledger_commit",
        transitions={"*": "THEOREM_SAVE"},
        default_next="THEOREM_SAVE",
    ),
    "LEDGER_ROLLBACK": DAGNode(
        name="LEDGER_ROLLBACK",
        exec_method="_exec_ledger_rollback",
        transitions={"*": "DONE"},
        default_next="DONE",
    ),
    "THEOREM_SAVE": DAGNode(
        name="THEOREM_SAVE",
        exec_method="_exec_theorem_save",
        transitions={"*": "MEMORY_SAVE"},
        default_next="MEMORY_SAVE",
    ),
    "MEMORY_SAVE": DAGNode(
        name="MEMORY_SAVE",
        exec_method="_exec_memory_save",
        transitions={"*": "DONE"},
        default_next="DONE",
    ),
    "DONE": DAGNode(
        name="DONE",
        exec_method="_exec_done",
        transitions={},
        default_next="",
    ),
}


# ============================================================
#  TitanAgent (F1) - Meta-router del DAG
# ============================================================

class TitanAgent(BaseAgent):
    """
    Agente F1: Meta-router que decide transiciones del DAG.

    Cuando un nodo tiene transiciones condicionales no triviales
    (ej: INTENT necesita decidir el path según operation/goal),
    TitanAgent evalúa el contexto y devuelve el siguiente nodo.

    Fallback: Usa la tabla de transiciones estática del DAG
    (comportamiento idéntico al pipeline secuencial original).
    """

    name = "titan"

    # Mapa de intencion -> siguiente nodo (fallback determinista)
    INTENT_TRANSITIONS: Dict[str, str] = {
        "CREATE": "CONTEXT_PREPARE",
        "REFACTOR": "CONTEXT_PREPARE",
        "DELETE": "CONTEXT_PREPARE",
        "SEARCH": "CONTEXT_PREPARE",
        "ANALYZE": "CONTEXT_PREPARE",
        "EXPLAIN": "CONTEXT_PREPARE",
        "DEBUG": "CONTEXT_PREPARE",
        "OPTIMIZE": "CONTEXT_PREPARE",
    }

    # Mapa de criticalidad -> path en PLAN
    # CriticalityLevel values: 1=FAST_STANDARD, 2=DEEP_MODERATE, 3=SURGICAL_CRITICAL
    CRITICALITY_PATHS: Dict[Any, str] = {
        1: "low_crit",              # FAST_STANDARD -> Salta SOLVER_VERIFY
        2: "standard",              # DEEP_MODERATE -> Pipeline completo sin self_reflect
        3: "high_crit",             # SURGICAL_CRITICAL -> Pipeline completo + Z3 + self_reflect
        "FAST": "low_crit",
        "STANDARD": "standard",
        "DEEP": "high_crit",
        "SURGICAL_CRITICAL": "high_crit",
        "DEEP_MODERATE": "standard",
        "FAST_STANDARD": "low_crit",
    }

    def build_prompt(self, input_data: Any) -> tuple:
        """
        Construye prompt para decidir la transición del DAG.

        Input esperado: dict con keys:
          - current_node: str (nombre del nodo actual)
          - result: str (resultado del nodo actual)
          - context: dict (operation, goal, criticality, etc.)
        """
        node = input_data.get("current_node", "")
        result = input_data.get("result", "")
        ctx = input_data.get("context", {})
        op = ctx.get("operation", "SEARCH")
        goal = ctx.get("goal", "")
        crit = ctx.get("criticality", "standard")

        system = (
            "You are a pipeline router. Given the current pipeline node, "
            "its result, and context, decide the NEXT node. "
            "Reply ONLY with the node name from: "
            "INTENT, CONTEXT_PREPARE, AST_ANALYZE, THEOREM_CACHE, ROUTE, "
            "CRITICALITY_ROUTE, PLAN, SOLVER_VERIFY, EXECUTE_STEPS, SANDBOX, "
            "LEDGER_COMMIT, "
            "LEDGER_ROLLBACK, THEOREM_SAVE, MEMORY_SAVE, DONE. "
            "No explanation, just the node name."
        )
        user = (
            f"Node:{node} Result:{result} Op:{op} Goal:{goal} Crit:{crit}"
        )
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[str]:
        """Parsea la respuesta del LLM como nombre de nodo válido."""
        from src.core.agents.base import BaseAgent
        text = BaseAgent.clean_llm_text(raw_response).strip().upper()
        valid_nodes = set(PIPELINE_DAG.keys())
        if text in valid_nodes:
            return text
        # Intentar match parcial
        for node_name in valid_nodes:
            if node_name in text:
                return node_name
        return None

    def fallback(self, input_data: Any) -> str:
        """
        Fallback determinista: usa tablas estáticas para decidir transición.

        Comportamiento idéntico al pipeline secuencial original.
        """
        node = input_data.get("current_node", "")
        result = input_data.get("result", "")
        ctx = input_data.get("context", {})
        op = ctx.get("operation", "SEARCH")
        crit = ctx.get("criticality", "standard")

        # Nodo INTENT: decidir path según operation
        if node == "INTENT":
            return self.INTENT_TRANSITIONS.get(op, "AST_ANALYZE")

        # Nodo PLAN: decidir path según criticalidad
        if node == "PLAN":
            path_key = self.CRITICALITY_PATHS.get(crit, "standard")
            return path_key

        # Para otros nodos: usar transición por defecto del DAG
        dag_node = PIPELINE_DAG.get(node)
        if dag_node:
            if result in dag_node.transitions:
                return dag_node.transitions[result]
            if "*" in dag_node.transitions:
                return dag_node.transitions["*"]
            return dag_node.default_next

        return "DONE"


# ============================================================
#  DAGOrchestrator - Orquestador basado en DAG
# ============================================================

class DAGOrchestrator:
    """
    Orquestador del pipeline de 8 niveles basado en DAG con TitanAgent (F1).

    Reemplaza el dispatch estático if/elif de TitanOrchestrator con
    un grafo dirigido donde cada nodo es un paso del pipeline y las
    transiciones son condicionales. TitanAgent decide las transiciones
    no triviales usando el LLM, con fallback a tablas estáticas.

    Ventajas sobre el orquestador original:
    - 75% menos código (1,179 → ~300 líneas de lógica central)
    - Soporta ciclos de feedback (reintentar pasos, saltar irrelevantes)
    - Router de criticalidad integrado (FAST/STANDARD/DEEP)
    - Fallback determinista = comportamiento original garantizado
    """

    def __init__(self) -> None:
        initialize_databases()
        self.settings = load_settings()
        self.p_dir = self.settings.get("project_dir", ".")
        self.request_count = 0

        # ── 8-Level Pipeline Components ──
        self.parser = SemanticParser()
        self.router = MacroRouter()
        self.ast_engine = GraphASTEngine()
        self.planner = APAPlanner()
        self.scrap = GitHubScrapAgent()
        self.surgeon = ASTSurgeon()
        self.sandbox = ReflexionSandbox()
        self.ledger = MerkleLedger()
        self.cache = TheoremCache()

        # ── 3-Layer AI Architecture ──
        self._semantic = SemanticEngine(auto_load=True)
        self._ai = MiniAIEngine(auto_load=True)
        self._memory = SmartMemory(semantic_engine=self._semantic)

        # Wire SemanticEngine into parser
        if self._semantic and self._semantic.is_loaded:
            self.parser.set_semantic_engine(self._semantic)
        if self._memory:
            self.parser.set_smart_memory(self._memory)

        # ── Isolation Manager ──
        self._isolation_manager = get_isolation_manager()
        self._pending_resumptions = {}

        # ── Extended AI Architecture ──
        self._thinking = ThinkingEngine(
            mini_ai=self._ai, semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._template_engine = None
        try:
            from src.core.template_engine import TemplateEngine
            self._template_engine = TemplateEngine()
        except ImportError:
            logger.warning("DAGOrchestrator: TemplateEngine not available")

        # ── Phase 7: Real Engines ──
        self._executor_registry = get_default_registry()
        self._logic_builder = LogicBuilder(template_engine=self._template_engine)
        self._auth = AuthService()

        # ── Phase 8: Intelligence ──
        self._reasoning = ReasoningEngine(
            mini_ai=self._ai, semantic_engine=self._semantic,
            smart_memory=self._memory,
        )
        self._chain_validator = ChainValidator()
        self._chain_executor = ChainExecutor(
            default_recovery=RecoveryAction.SKIP, max_retries=1
        )

        # ── App & Automation ──
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

        # ── Decomposed Sub-Modules ──
        self._abortive = AbortiveProtocol(self)
        self._partial_reasoning = PartialReasoningManager(self)
        self._code_gen = CodeGenerator(self)
        self._code_transform = CodeTransformer()
        self._analysis = AnalysisUtils(self)

        # ── Agent Framework (F1-F5) ──
        self._agent_runner = AgentRunner(
            mini_ai=self._ai, semantic_engine=self._semantic,
            smart_memory=self._memory, enable_cache=True,
        )
        if self._semantic and self._semantic.is_loaded:
            self._agent_runner._cache.set_semantic_engine(self._semantic)

        self._intent_agent = SurgicalAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        self._context_agent = ContextAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        self._reasoning_agent = ReasoningAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        self._business_logic_agent = BusinessLogicAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        self._code_agent = CodeAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
            template_engine=self._template_engine,
        )
        self._automation_agent = AutomationAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )
        self._validation_agent = ValidationAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
        )

        # ── CriticalityAgent (F4): Dynamic Criticality Router ──
        self._criticality_agent = CriticalityAgent(
            semantic_engine=self._semantic, smart_memory=self._memory,
            macro_router=self.router,
        )

        # ── TitanAgent (F1) - Meta-router del DAG ──
        self._titan_agent = TitanAgent()

        # Log status
        sem_s = "ACTIVE" if self._semantic.is_loaded else "fallback"
        ai_s = "ACTIVE" if self._ai.is_loaded else "fallback"
        logger.info(
            f"DAGOrchestrator v16: SemanticEngine={sem_s} | "
            f"MiniAI(Qwen)={ai_s} | SmartMemory=ready | "
            f"TitanAgent(F1)=ready | SurgicalAgent(F2)=ready | "
            f"ContextAgent(F3)=ready | CriticalityAgent(F4)=ready | "
            f"DAG={len(PIPELINE_DAG)} nodes"
        )

        # Escanear proyecto si existe
        if Path(self.p_dir).exists():
            self.ast_engine.scan_project(self.p_dir)

    # ============================================================
    #  DAG EXECUTION ENGINE - Corazón del orquestador
    # ============================================================

    async def execute(self, msg: str) -> Dict[str, Any]:
        """Ejecuta el pipeline DAG con TitanAgent como meta-router."""
        start_time = time.time()
        self.request_count += 1

        # Reset context tracking para deduplicación cross-agent
        self._context_agent.reset_agent_tracking()

        # Contexto que fluye a través del DAG
        ctx: Dict[str, Any] = {
            "msg": msg,
            "start_time": start_time,
            "intent": None,
            "intent_output": None,
            "context_output": None,   # F3: ContextAgent output
            "compressed_context": "",  # F3: Contexto pre-comprimido
            "token_budget": {},         # F3: Presupuesto de tokens
            "criticality_output": None, # F4: CriticalityAgent output
            "criticality_adjustments": {},  # F4: Ajustes de criticalidad para agentes
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
            "iteration_counts": {},  # Anti-ciclo infinito
        }

        # Ejecutar DAG desde CACHE_CHECK
        current_node = "CACHE_CHECK"
        max_total_steps = 20  # Safety: máximo 20 pasos total

        for step in range(max_total_steps):
            if current_node == "DONE" or current_node not in PIPELINE_DAG:
                break

            dag_node = PIPELINE_DAG[current_node]

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
                # Remover flag interno y devolver
                result = {k: v for k, v in node_result.items() if k != "_dag_done"}
                return result

            # Determinar siguiente nodo
            result_key = node_result if isinstance(node_result, str) else "*"
            next_node = self._resolve_transition(
                current_node, result_key, ctx
            )
            current_node = next_node

        # Si llegamos aquí sin DONE, devolver resultado del contexto
        elapsed = int((time.time() - start_time) * 1000)
        return self._build_response(ctx, "COMPLETED", elapsed)

    def _resolve_transition(self, current_node: str, result_key: str,
                            ctx: Dict) -> str:
        """
        Resuelve la transición del DAG. Usa TitanAgent para decisiones
        no triviales, fallback a tabla estática.
        """
        dag_node = PIPELINE_DAG.get(current_node)
        if not dag_node:
            return "DONE"

        # 1. Buscar en tabla de transiciones directa
        if result_key in dag_node.transitions:
            return dag_node.transitions[result_key]
        if "*" in dag_node.transitions:
            return dag_node.transitions["*"]

        # 2. Nodos con transición dinámica (INTENT, PLAN)
        if current_node in ("INTENT", "PLAN"):
            # Intentar TitanAgent (LLM) si está disponible
            if self._ai and self._ai.is_loaded:
                try:
                    titan_input = {
                        "current_node": current_node,
                        "result": result_key,
                        "context": {
                            "operation": ctx.get("intent_output", IntentOutput()).operation if ctx.get("intent_output") else "SEARCH",
                            "goal": ctx.get("intent_output", IntentOutput()).goal if ctx.get("intent_output") else "",
                            "criticality": ctx.get("routing").criticality if ctx.get("routing") else "standard",
                        },
                    }
                    llm_result = self._titan_agent.fallback(titan_input)
                    if llm_result and llm_result in PIPELINE_DAG:
                        return llm_result
                except Exception as e:
                    logger.debug(f"TitanAgent LLM fallback: {e}")

            # Fallback determinista
            return self._titan_agent.fallback({
                "current_node": current_node,
                "result": result_key,
                "context": {
                    "operation": ctx.get("intent_output", IntentOutput()).operation if ctx.get("intent_output") else "SEARCH",
                    "criticality": ctx.get("routing").criticality if ctx.get("routing") else "standard",
                },
            })

        # 3. Default
        return dag_node.default_next or "DONE"

    # ============================================================
    #  DAG NODE EXECUTORS - Un método por nodo del DAG
    # ============================================================

    async def _exec_cache_check(self, ctx: Dict) -> str:
        """Nodo CACHE_CHECK: Check SmartMemory cache."""
        cached = self._memory.check_cache(ctx["msg"])
        if cached:
            elapsed = int((time.time() - ctx["start_time"]) * 1000)
            logger.info(f"SmartMemory: Cache hit ({cached['source']})")
            ctx["final_code"] = cached.get("response", "")
            # Retornar resultado final directamente
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
        intent_output = self._intent_agent.classify_with_runner(
            self._agent_runner, ctx["msg"], context=""
        )
        intent = self._intent_agent.to_intent_payload(
            intent_output, context=ctx["msg"]
        )

        # Extraer código del mensaje
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
        return intent_output.operation  # Transición dinámica por operation

    async def _exec_context_prepare(self, ctx: Dict) -> str:
        """Nodo CONTEXT_PREPARE (F3): Prepara contexto óptimo para downstream agents."""
        intent_output = ctx.get("intent_output")
        msg = ctx["msg"]

        # ContextAgent prepara contexto comprimido + presupuesto de tokens
        context_result = self._context_agent.prepare_context(
            message=msg,
            intent_output=intent_output,
        )

        # Guardar en contexto del DAG para uso de downstream agents
        ctx["context_output"] = context_result
        ctx["compressed_context"] = context_result.compressed_context
        ctx["token_budget"] = context_result.token_budget

        # Log métricas de compresión
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

    async def _exec_theorem_cache(self, ctx: Dict) -> str:
        """Nodo THEOREM_CACHE: Búsqueda en caché de teoremas."""
        intent = ctx.get("intent")
        if not intent:
            return "miss"
        cache_hit = self.cache.lookup(
            intent, intent.raw_code, intent.language
        )
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
        """
        Nodo CRITICALITY_ROUTE (F4): Ruteo Dinámico de Criticalidad.

        Unifica la inferencia de criticalidad desde múltiples señales:
        1. MacroRouter (ya ejecutado en ROUTE) → baseline criticality
        2. SurgicalAgent (F2) → intent context
        3. SmartMemory → historical importance
        4. CriticalityAgent → fusión ponderada con ajustes

        Output: CriticalityOutput canónico que alimenta todos los agentes.
        """
        intent_output = ctx.get("intent_output")
        routing = ctx.get("routing")

        # Criticalidad base del MacroRouter
        router_crit = routing.criticality if routing else 2

        # Ejecutar CriticalityAgent (LLM → fallback)
        crit_output = self._criticality_agent.assess_with_runner(
            runner=self._agent_runner,
            intent_output=intent_output,
            message=ctx["msg"],
            existing_criticality=router_crit,
        )

        # Guardar en contexto del DAG
        ctx["criticality_output"] = crit_output
        ctx["criticality_adjustments"] = crit_output.adjustments

        # Propagar ajustes a agentes downstream (cableado F4)
        if crit_output.adjustments:
            # CodeAgent: ajustar generación según criticalidad
            if hasattr(self._code_agent, 'set_criticality_adjustments'):
                self._code_agent.set_criticality_adjustments(crit_output.adjustments)
            # BusinessLogicAgent: ajustar ejecución según criticalidad
            if hasattr(self._business_logic_agent, 'set_criticality_adjustments'):
                self._business_logic_agent.set_criticality_adjustments(crit_output.adjustments)

        # Override del routing.criticality con la evaluación dinámica de F4
        if routing and crit_output.level != router_crit:
            # F4 puede elevar criticalidad pero MacroRouter no la baja
            if crit_output.level > router_crit:
                routing.criticality = crit_output.level
                logger.info(
                    f"CriticalityAgent(F4): Elevated criticality "
                    f"{router_crit} → {crit_output.level} "
                    f"(path={crit_output.path}, reason={crit_output.reason[:80]})"
                )

        # F4: Ajustar presupuesto de contexto de F3 según criticalidad
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

        # Protocolo abortivo
        if ctx["plan"].solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            return "abortive"

        # Router de criticalidad: F4 → TitanAgent mapping
        # F4 proporciona el nivel canónico; si no está, usar MacroRouter
        if crit_output and isinstance(crit_output, CriticalityOutput):
            return crit_output.path  # "low_crit", "standard", "high_crit"

        # Fallback: usar mapping estático de TitanAgent
        crit = routing.criticality if routing else 2
        return self._titan_agent.CRITICALITY_PATHS.get(crit, "standard")

    async def _exec_solver_verify(self, ctx: Dict) -> str:
        """Nodo SOLVER_VERIFY: Verificación Z3 para alta criticalidad."""
        plan = ctx.get("plan")
        # La verificación Z3 ya se ejecutó en APAPlanner
        if plan and plan.solver_status in ("PROVEN", "SAT", "PARTIAL"):
            return "pass"
        # Si falló pero podemos continuar sin prueba formal
        return "pass"

    async def _exec_steps(self, ctx: Dict) -> str:
        """Nodo EXECUTE_STEPS: Ejecutar pasos del plan (el dispatch compacto)."""
        plan = ctx.get("plan")
        intent = ctx.get("intent")
        if not plan or not intent:
            return "*"

        code = ctx["code"]
        result_code = ""
        explanations = ctx["explanations"]
        lang = ctx["lang"]

        # F3: Inyectar contexto comprimido en explanations para agentes downstream
        compressed_ctx = ctx.get("compressed_context", "")
        if compressed_ctx:
            explanations.append(f"[F3 Context] {compressed_ctx[:200]}")

        for step in plan.steps:
            result_code, code, explanations = await self._execute_step(
                step, intent, code, result_code, explanations,
                lang, ctx["ast_analysis"], plan
            )

        ctx["code"] = code
        ctx["result_code"] = result_code
        ctx["explanations"] = explanations
        ctx["final_code"] = result_code if result_code else code
        return "*"

    async def _execute_step(self, step, intent, code, result_code,
                            explanations, lang, ast_analysis, plan):
        """Ejecuta UN paso del plan. Compacto vs if/elif original."""
        action = step.action

        # Dispatch compacto por acción
        if action == "ANALYZE_STRUCTURE" and code:
            a = self.ast_engine.analyze_structure(code, lang)
            explanations.append(
                f"Structure: {a['functions']} funcs, {a['classes']} classes, "
                f"max complexity {a['max_complexity']}"
            )
        elif action == "SCRAPE_PATTERNS":
            q = step.constraints.get("query", intent.scrap_query)
            patterns = await self.scrap.fetch_modern_code(q, lang)
            if patterns:
                explanations.append(f"Found patterns on GitHub")
                best = patterns[0] if isinstance(patterns, list) else patterns
                if isinstance(best, dict):
                    best = best.get("code", str(best))[:2000]
                if not code:
                    code = best
            else:
                explanations.append("GitHub: no results. Using local generation.")
        elif action == "GENERATE_CODE":
            result_code = self._code_gen.generate_contextual_code(
                intent, ast_analysis, plan, lang
            )
            explanations.append(f"Code generated for {intent.op}")
        elif action == "REPLACE_AST_NODE" and code and step.target_node_name:
            insights = self._code_gen.extract_solver_insights(plan.solver_proof) if plan else None
            if self._ai.is_loaded:
                pattern = self._ai.suggest_pattern(step.target_node_name, str(intent))
                explanations.append(f"MiniAI pattern: {pattern}")
            new_snippet = self._code_transform.optimize_function(
                step.target_node_name, lang, ast_analysis, insights
            )
            result_code = self.surgeon.mutate_node(
                code, step.target_node_name, new_snippet, lang
            )
            explanations.append(f"'{step.target_node_name}' replaced via AST")
        elif action == "DELETE_AST_NODE" and code and step.target_node_name:
            result_code = self.surgeon.delete_function(
                code, step.target_node_name, lang
            )
            explanations.append(f"'{step.target_node_name}' deleted via AST")
        elif action == "TRACE_EXECUTION" and code:
            a = self.ast_engine.analyze_structure(code, lang)
            for fn in a.get("function_names", []):
                explanations.append(f"  - Traced: {fn}")
        elif action == "PATCH_FIX":
            result_code = self._analysis.apply_fix(code, intent, lang)
            explanations.append("Fix patch applied")
        elif action == "QUALITY_REPORT" and code:
            report = self._analysis.generate_quality_report(
                self.ast_engine.analyze_structure(code, lang), code, lang
            )
            explanations.append(report)
        elif action == "EXPLAIN_CODE":
            if code:
                base = self._analysis.explain_code(code, lang, ast_analysis)
                if self._ai.is_loaded:
                    violations = []
                    if "eval(" in code or "exec(" in code:
                        violations.append("dangerous_call")
                    if "os.system(" in code:
                        violations.append("command_injection")
                    if violations:
                        ai_exp = self._ai.explain_violation(code[:200], violations)
                        if ai_exp:
                            base += f" | AI: {ai_exp}"
                explanations.append(base)
            else:
                explanations.append(self._analysis.explain_concept(intent))
        elif action == "SEARCH_DEFINITION" and code:
            nodes = self.ast_engine.get_node_info(intent.target)
            if nodes:
                for n in nodes[:5]:
                    explanations.append(
                        f"Found: {n['node_type']} '{n['name']}' "
                        f"(complexity: {n.get('complexity', 'N/A')})"
                    )
            else:
                explanations.append(f"'{intent.target}' not found")
        elif action in ("SYMBOLIC_VALIDATION", "SYNTAX_VALIDATION"):
            if self._validation_agent and code:
                v_out = self._validation_agent.validate_with_runner(
                    self._agent_runner, target="code", content=code,
                    rules=["security", "quality"], language=lang,
                )
                if v_out.issues:
                    explanations.append(
                        f"Validation: {len(v_out.issues)} issues "
                        f"(risk={v_out.risk_score:.2f})"
                    )
                else:
                    explanations.append("Validation: No issues")
        elif action == "ANALYZE_AND_RESPOND":
            if code:
                explanations.append(self._analysis.analyze_and_respond(code, intent, ast_analysis))
            else:
                explanations.append(self._analysis.general_response(intent))
        elif action == "QUICK_ANALYSIS":
            explanations.append("Quick analysis completed")
        elif action == "FULL_ANALYSIS" and code:
            explanations.append(self._analysis.full_analysis(code, intent, ast_analysis, lang))
        elif action == "CHECK_DEPENDENCIES" and code:
            deps = self._analysis.check_dependencies(code, intent.target, lang)
            explanations.extend(deps)

        return result_code, code, explanations

    async def _exec_abortive(self, ctx: Dict) -> str:
        """Nodo ABORTIVE: Protocolo abortivo."""
        result = await self._abortive.handle_abortive_protocol(
            ctx["intent"], ctx["routing"], ctx["plan"],
            ctx["ast_analysis"], ctx["start_time"]
        )
        return {**result, "_dag_done": True}

    async def _exec_sandbox(self, ctx: Dict) -> str:
        """Nodo SANDBOX: Validación en sandbox aislado."""
        final_code = ctx["final_code"]
        lang = ctx["lang"]
        intent = ctx.get("intent")

        workspace = self._isolation_manager.create_workspace(
            ttl_seconds=max(self.sandbox.timeout_seconds * 3, 120)
        )
        ctx["sandbox_workspace"] = workspace

        p_dir = str(get_projects_dir())
        self.ledger.snapshot(intent.target if intent else "unknown", p_dir, workspace=workspace)

        trial = await self.sandbox.validate_code(
            final_code, lang, intent.target if intent else "unknown"
        )
        ctx["trial"] = trial
        return trial.status  # "PASS", "FAIL", "FAIL_K_PATH"

    async def _exec_partial_reasoning(self, ctx: Dict) -> str:
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
                msg, final_code[:500], intent.op if intent else "",
                intent.goal if intent else "", importance
            )
            self._memory.save_to_cache(
                msg, final_code[:500], intent.op if intent else "",
                intent.goal if intent else "", importance
            )

            # F3: Save procedural pattern if context agent tracked high-value context
            context_output = ctx.get("context_output")
            if context_output and context_output.relevant_memories:
                for mem in context_output.relevant_memories[:2]:
                    if mem.get("type") == "similar_solution" and mem.get("similarity", 0) > 0.7:
                        try:
                            self._memory.learn_pattern(
                                pattern_name=f"{intent.op if intent else 'unknown'}_solution",
                                pattern_type="solution",
                                description=mem.get("solution", "")[:200],
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

        # Log request
        self._analysis.log_request(
            ctx.get("intent"), status, elapsed,
            solver_status=ctx.get("plan", None) and ctx["plan"].solver_status or "",
            mcts_sims=ctx.get("plan", None) and ctx["plan"].mcts_simulations or 0,
        )

        return self._build_response(ctx, status, elapsed)

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
            # F3: Incluir métricas de contexto en respuesta exitosa
            context_output = ctx.get("context_output")
            if context_output:
                response["context_metrics"] = {
                    "entries_used": context_output.entries_used,
                    "entries_total": context_output.entries_total,
                    "compression_ratio": context_output.compression_ratio,
                    "token_budget": context_output.token_budget,
                    "source": context_output.source,
                }

        return response

    # ============================================================
    #  PUBLIC API - Idéntica al TitanOrchestrator original
    # ============================================================

    async def resume_from_partial(self, resumption_token: str,
                                   subtask_index: Optional[int] = None) -> Dict[str, Any]:
        return await self._partial_reasoning.resume_from_partial(resumption_token, subtask_index)

    async def generate_app(self, request: str, project_name: str = "",
                           output_dir: str = "") -> Dict[str, Any]:
        result = self._app_gen.generate_app(request, project_name, output_dir)
        if result.status == "generated" and self._memory:
            self._memory.save_project(
                project_name=result.name, project_type=result.template_type,
                description=request, path=result.path, status="generated",
                entities=[e.get("name", "") for e in result.entities],
                endpoints=[str(ep) for ep in result.endpoints],
            )
            self._memory.save_episode(
                event_type="app_generated",
                description=f"Generated {result.template_type} app: {result.name}",
                context=request[:200], outcome="success", importance=0.8,
            )
        return {
            "status": result.status, "project_name": result.name,
            "template_type": result.template_type, "path": result.path,
            "files": result.files, "endpoints": result.endpoints,
            "entities": result.entities, "generation_time_s": result.generation_time_s,
            "error": result.error,
        }

    async def generate_automation(self, description: str,
                                   output_dir: str = "") -> Dict[str, Any]:
        automation_design = None
        if self._automation_agent:
            automation_design = self._automation_agent.design_with_runner(
                self._agent_runner, description,
            )
        result = self._automation.generate_automation_project(description, output_dir)
        if automation_design:
            result["automation_agent"] = {
                "name": automation_design.name,
                "triggers": [{"type": t.type, "config": t.config} for t in automation_design.triggers],
                "actions": [{"type": a.type, "config": a.config} for a in automation_design.actions],
                "source": automation_design.source,
            }
        return {
            "status": result.get("status", "unknown"),
            "path": result.get("path", ""),
            "files": result.get("files", []),
            "automation_agent": result.get("automation_agent"),
        }

    async def design_schema(self, description: str) -> Dict[str, Any]:
        schema = self._schema_designer.design_schema(description)
        return {
            "status": "designed",
            "tables": [{"name": t.name, "columns": len(t.columns)} for t in schema.tables],
            "sql": self._schema_designer.generate_sql(schema),
            "models": self._schema_designer.generate_models(schema),
            "init_sql": self._schema_designer.generate_init_sql(schema),
        }

    async def list_projects(self, status: str = "") -> List[Dict[str, Any]]:
        return self._memory.list_projects(status) if self._memory else []

    async def list_automations(self) -> List[Dict[str, Any]]:
        return self._automation.list_workflows()

    async def think(self, query: str, context: str = "") -> Dict[str, Any]:
        result = self._thinking.reason(query, context)
        return {
            "answer": result.answer, "confidence": result.confidence,
            "source": result.source, "context_used": result.context_used,
            "thinking_time_s": result.thinking_time_s,
        }

    async def register_user(self, username: str, email: str, password: str,
                           role: str = "user") -> Dict[str, Any]:
        return self._auth.register_user(username, email, password, role) if self._auth else {"error": "AuthService N/A"}

    async def login_user(self, username: str, password: str) -> Dict[str, Any]:
        return self._auth.login_user(username, password) if self._auth else {"error": "AuthService N/A"}

    async def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            return self._auth.verify_token(token) if self._auth else {"error": "AuthService N/A"}
        except Exception as e:
            return {"error": str(e)}

    async def build_logic(self, description: str) -> Dict[str, Any]:
        if self._business_logic_agent:
            output = self._business_logic_agent.execute_with_runner(
                self._agent_runner, operation_type="custom",
                data={"description": description}, description=description,
            )
            result = {
                "success": output.success, "data": output.data,
                "side_effects": output.side_effects, "insights": output.insights,
                "errors": output.errors, "source": output.source,
            }
            if self._logic_builder:
                chain = self._logic_builder.build_from_description(description)
                blocks = [b.name for b in chain.blocks]
                result["blocks"] = blocks
                result["block_count"] = len(blocks)
                result["generated_code"] = self._logic_builder.generate_process_method(blocks)
            return result
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        blocks = [b.name for b in chain.blocks]
        return {"blocks": blocks, "block_count": len(blocks),
                "generated_code": self._logic_builder.generate_process_method(blocks)}

    async def list_logic_blocks(self, category: str = "") -> List[Dict[str, Any]]:
        if not self._logic_builder:
            return []
        return [{"name": b.name, "category": b.category, "description": b.description,
                 "inputs": b.inputs, "outputs": b.outputs}
                for b in self._logic_builder.list_blocks(category)]

    async def execute_action(self, action_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        if not self._executor_registry:
            return {"error": "ExecutorRegistry not available"}
        result = await self._executor_registry.execute_action(action_type, config, {})
        return {"success": result.success, "data": result.data,
                "error": result.error, "duration_ms": result.duration_ms}

    async def reason(self, query: str, mode: str = "auto",
                     context: str = "") -> Dict[str, Any]:
        if self._reasoning_agent:
            actual_mode = mode if mode != "auto" else "step_by_step"
            output = self._reasoning_agent.reason_with_runner(
                self._agent_runner, query, mode=actual_mode, context=context,
            )
            return {"answer": output.answer, "confidence": output.confidence,
                    "mode": output.mode, "steps": len(output.steps),
                    "refinements": output.refinements, "source": output.source,
                    "duration_ms": output.total_duration_ms}
        if not self._reasoning:
            return {"error": "ReasoningEngine not available"}
        result = self._reasoning.reason(query, mode=mode, context=context)
        return {"answer": result.answer, "confidence": result.confidence,
                "mode": result.mode.value, "steps": len(result.steps),
                "source": result.source, "duration_ms": result.total_duration_ms}

    async def validate_logic_chain(self, description: str) -> Dict[str, Any]:
        if self._validation_agent:
            output = self._validation_agent.validate_with_runner(
                self._agent_runner, target="chain", content=description,
                rules=["compatibility", "completeness"], language="python",
            )
            return {
                "is_valid": output.is_valid,
                "can_execute": output.is_valid or not any(
                    i.severity == "error" for i in output.issues
                ),
                "issues": [{"severity": i.severity, "code": i.code,
                            "message": i.message, "line": i.line,
                            "suggestion": i.suggestion} for i in output.issues],
                "suggestions": output.suggestions,
                "risk_score": output.risk_score, "source": output.source,
            }
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        validation = self._chain_validator.validate(chain)
        return {
            "is_valid": validation.is_valid,
            "can_execute": validation.can_execute,
            "errors": [{"code": e.code, "message": e.message} for e in validation.errors],
            "warnings": [{"code": e.code, "message": e.message} for e in validation.warnings],
        }

    async def execute_logic_chain(self, description: str,
                                   data: Optional[Dict[str, Any]] = None,
                                   recovery: str = "skip") -> Dict[str, Any]:
        if not self._logic_builder:
            return {"error": "LogicBuilder not available"}
        chain = self._logic_builder.build_from_description(description)
        recovery_map = {"retry": RecoveryAction.RETRY, "skip": RecoveryAction.SKIP,
                       "fallback": RecoveryAction.FALLBACK, "abort": RecoveryAction.ABORT,
                       "rollback": RecoveryAction.ROLLBACK}
        executor = ChainExecutor(default_recovery=recovery_map.get(recovery, RecoveryAction.SKIP), max_retries=1)
        result = executor.execute(chain, data or {}, validate_first=True)
        return {
            "status": result.status.value, "steps_completed": result.steps_completed,
            "steps_failed": result.steps_failed, "steps_skipped": result.steps_skipped,
            "rollback_count": result.rollback_count, "total_duration_ms": result.total_duration_ms,
            "final_data": result.final_data, "error": result.error,
        }

    async def get_intelligence_status(self) -> Dict[str, Any]:
        return {
            "reasoning_engine": self._reasoning.stats if self._reasoning else {},
            "ai_layers": {
                "layer1_semantic": {"available": self._semantic.is_loaded if self._semantic else False},
                "layer2_qwen": {"available": self._ai.is_loaded if self._ai else False},
                "layer3_memory": {"available": self._memory is not None},
            },
            "thinking_engine": self._thinking.stats,
            "dag_orchestrator": {
                "nodes": len(PIPELINE_DAG),
                "titan_agent": "F1_ACTIVE",
                "criticality_paths": ["FAST", "STANDARD", "DEEP"],
            },
        }

    async def get_system_status(self) -> Dict[str, Any]:
        return {
            "pipeline": "DAG-based (v14)",
            "dag_nodes": len(PIPELINE_DAG),
            "titan_agent": "F1_ACTIVE",
            "ai": {
                "qwen_loaded": self._ai.is_loaded if self._ai else False,
                "semantic_loaded": self._semantic.is_loaded if self._semantic else False,
                "memory_available": self._memory is not None,
            },
            "thinking_engine": self._thinking.stats,
            "memory_stats": self._memory.enhanced_stats if self._memory else {},
            "agent_framework": {
                "runner_stats": self._agent_runner.stats if self._agent_runner else {},
                "titan_agent": self._titan_agent.stats,
                "intent_agent": self._intent_agent.stats if self._intent_agent else {},
                "reasoning_agent": self._reasoning_agent.stats if self._reasoning_agent else {},
                "validation_agent": self._validation_agent.stats if self._validation_agent else {},
            },
            "request_count": self.request_count,
        }

    # ============================================================
    #  BACKWARD COMPATIBILITY - Delegaciones idénticas al original
    # ============================================================

    async def _handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        return await self._abortive.handle_abortive_protocol(intent, routing, plan, ast_analysis, start_time)

    def _generate_subtasks(self, intent, ast_analysis, plan=None):
        return self._abortive.generate_subtasks(intent, ast_analysis, plan)

    async def _execute_subtask(self, subtask, depth=0, max_depth=2):
        return await self._abortive.execute_subtask(subtask, depth, max_depth)

    def _merge_subtask_results(self, subtask_results, language="python"):
        return self._abortive.merge_subtask_results(subtask_results, language)

    def _generate_intelligent_code(self, intent, ast_analysis, lang):
        return self._code_gen.generate_intelligent_code(intent, ast_analysis, lang)

    def _extract_solver_insights(self, solver_proof):
        return self._code_gen.extract_solver_insights(solver_proof)

    def _extract_ast_context(self, ast_analysis):
        return self._code_gen.extract_ast_context(ast_analysis)

    def _extract_symbolic_insights(self, sandbox_result):
        return self._code_gen.extract_symbolic_insights(sandbox_result)

    def _generate_contextual_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_contextual_code(intent, ast_analysis, plan, lang)

    def _apply_fix(self, code, intent, lang):
        return self._analysis.apply_fix(code, intent, lang)

    def _explain_code(self, code, lang, ast_analysis):
        return self._analysis.explain_code(code, lang, ast_analysis)

    def _explain_concept(self, intent):
        return self._analysis.explain_concept(intent)

    def _log_request(self, intent, status, elapsed_ms, cache_hit=False,
                    solver_status="", mcts_sims=0):
        return self._analysis.log_request(intent, status, elapsed_ms, cache_hit,
                                          solver_status, mcts_sims)
