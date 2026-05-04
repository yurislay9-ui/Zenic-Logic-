"""
TITAN OMNISCALE X - TitanAgent (F1) + DAG Orchestrator v16

Reemplaza el dispatch estático de orchestrator.py con un grafo dirigido
acíclico (DAG) donde cada nodo representa un estado del pipeline y las
transiciones son condicionales según el resultado del paso anterior.

TitanAgent (F1): Agente meta-router que decide dinámicamente la
siguiente transición del DAG usando el LLM, con fallback al
pipeline secuencial original.

CAMBIO TECNOLÓGICO v16 - Model Manager (Hybrid Lazy Loading):
- SemanticEngine y MiniAIEngine ahora se cargan via ModelManager
- Lazy loading: modelos solo se cargan al primer uso (no en __init__)
- Auto-unload: modelos se descargan tras 5 min sin uso
- RAM budget: control estricto de memoria para proteger el teléfono
- Resultado: arranque en <5s (vs ~60s) y ~50MB idle (vs ~730MB)

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
from src.core.shared.db_initializer import get_projects_dir

# Base class with shared initialization, public API, backward-compat
from src.core.orchestrator_base import BaseOrchestrator

# Step dispatcher for unified step execution
from src.core.step_dispatcher import StepDispatcher

# 3-Layer AI Architecture - Now via ModelManager for hybrid lazy loading
from src.core.model_manager import ModelManager, get_model_manager, init_model_manager
from src.core.smart_memory import SmartMemory

# Agent Framework (F1-F5) - DAG-specific agents
from src.core.agents.base import BaseAgent
from src.core.agents.schemas import IntentOutput, CriticalityOutput
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.context_agent import ContextAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.code_agent import CodeAgent
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent
from src.core.agents.criticality_agent import CriticalityAgent
from src.core.fractal_generator import FractalGenerator

logger = logging.getLogger(__name__)

# === Extracted Constants (previously hardcoded inline) ===
MAX_MEMORY_SNIPPET_LEN = 500      # Max chars for memory save snippets
SANDBOX_TTL_MULTIPLIER = 3        # Sandbox TTL = timeout * multiplier
SANDBOX_TTL_MIN = 120             # Minimum sandbox TTL in seconds
MAX_CODE_SNIPPET_LEN = 200        # Max chars for code context snippets


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
# Note: PIPELINE_DAG is mutable; consider copying in __init__ for isolation
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
        transitions={"pass": "EXECUTE_STEPS", "fail": "ABORTIVE", "fail_timeout": "ABORTIVE"},
        default_next="ABORTIVE",
        max_retries=2,
    ),
    "EXECUTE_STEPS": DAGNode(
        name="EXECUTE_STEPS",
        exec_method="_exec_steps",
        transitions={"*": "VALIDATE"},
        default_next="VALIDATE",
    ),
    "VALIDATE": DAGNode(
        name="VALIDATE",
        exec_method="_exec_validate",
        transitions={"clean": "SANDBOX", "issues_found": "EXECUTE_STEPS"},
        default_next="SANDBOX",
        max_retries=3,  # F5: Bucle de corrección secuencial (máx 3 ciclos)
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
            "CRITICALITY_ROUTE, PLAN, SOLVER_VERIFY, EXECUTE_STEPS, VALIDATE, SANDBOX, "
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

class DAGOrchestrator(BaseOrchestrator):
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
            lazy_load=True,
            idle_timeout_s=300,
            ram_budget_mb=768,
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

    async def execute(self, msg: str, client_id: str = "default") -> Dict[str, Any]:
        """Ejecuta el pipeline DAG con TitanAgent como meta-router.
        
        Args:
            msg: Mensaje del usuario.
            client_id: Brecha B: Client identifier for multi-client isolation.
        """
        start_time = time.time()
        self.request_count += 1

        # Hybrid Lazy Loading: Asegurar que los modelos estén disponibles
        # para esta request. Si están unloaded, se cargan ahora (lazy).
        self._semantic = self._model_mgr.semantic_engine
        self._ai = self._model_mgr.mini_ai_engine

        # Brecha B: Set client_id for memory and workspace isolation
        self._memory.set_client_id(client_id)
        self._current_client_id = client_id

        # Reset context tracking para deduplicación cross-agent
        if self._context_agent:
            self._context_agent.reset_agent_tracking()

        # Contexto que fluye a través del DAG
        ctx: Dict[str, Any] = {
            "msg": msg,
            "client_id": client_id,
            "start_time": start_time,
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
            if current_node == "DONE" or current_node not in self._pipeline_dag:
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

        # Si llegamos aquí sin DONE, devolver resultado del contexto
        elapsed = int((time.time() - start_time) * 1000)
        return self._build_response(ctx, "COMPLETED", elapsed)

    def set_client_id(self, client_id: str):
        """Brecha B: Set the client_id for multi-client isolation."""
        self._memory.set_client_id(client_id)
        self._current_client_id = client_id
        logger.info(f"DAGOrchestrator: client_id set to '{client_id}'")

    def _resolve_transition(self, current_node: str, result_key: str,
                            ctx: Dict) -> str:
        """Resuelve la transición del DAG."""
        dag_node = self._pipeline_dag.get(current_node)
        if not dag_node:
            return "DONE"

        # 1. Buscar en tabla de transiciones directa
        if result_key in dag_node.transitions:
            return dag_node.transitions[result_key]
        if "*" in dag_node.transitions:
            return dag_node.transitions["*"]

        # 2. Nodos con transición dinámica (INTENT, PLAN)
        if current_node in ("INTENT", "PLAN"):
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

    async def _exec_theorem_cache(self, ctx: Dict) -> str:
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

    async def _exec_validate(self, ctx: Dict) -> str:
        """Nodo VALIDATE (F5): Enjambre de Revisión Secuencial."""
        final_code = ctx.get("final_code", "")
        lang = ctx.get("lang", "python")

        if not final_code or not final_code.strip():
            logger.info("VALIDATE(F5): No code to validate, proceeding to SANDBOX")
            return "clean"

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

        if risk_score <= 0.0 or not issues:
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
            ttl_seconds=max(self.sandbox.timeout_seconds * SANDBOX_TTL_MULTIPLIER, SANDBOX_TTL_MIN),
            client_id=ctx.get("client_id", "default")
        )
        ctx["sandbox_workspace"] = workspace

        p_dir = str(get_projects_dir())
        self.ledger.snapshot(intent.target if intent else "unknown", p_dir, workspace=workspace)

        trial = await self.sandbox.validate_code(
            final_code, lang, intent.target if intent else "unknown"
        )
        ctx["trial"] = trial
        return trial.status

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

    # ============================================================
    #  F5 CORRECTION LOGIC
    # ============================================================

    def _apply_f5_corrections(self, code: str, issues: list, lang: str) -> str:
        """
        F5: Aplica correcciones automáticas basadas en los issues detectados
        por ValidationAgent.
        """
        import re as _re
        corrected = code

        for issue in issues:
            issue_code = getattr(issue, 'code', '')
            severity = getattr(issue, 'severity', 'warning')

            if severity != 'error':
                continue

            if issue_code == 'dangerous_eval':
                corrected = _re.sub(
                    r'\beval\s*\(', 'ast.literal_eval(', corrected
                )
                if 'ast.literal_eval' in corrected and 'import ast' not in corrected:
                    corrected = 'import ast\n' + corrected

            elif issue_code == 'command_injection':
                corrected = _re.sub(
                    r'os\.system\s*\(\s*([^)]+)\s*\)',
                    r'subprocess.run(\1, shell=False, capture_output=True)',
                    corrected
                )
                if 'subprocess.run' in corrected and 'import subprocess' not in corrected:
                    corrected = 'import subprocess\n' + corrected

            elif issue_code == 'shell_injection':
                corrected = _re.sub(
                    r'subprocess\.\w+\s*\(([^)]*?)shell\s*=\s*True',
                    r'subprocess.run(\1shell=False',
                    corrected
                )

            elif issue_code == 'pickle_deserialization':
                corrected = _re.sub(
                    r'pickle\.loads?\s*\(',
                    'json.loads(  # F5: Replaced unsafe pickle\n        ',
                    corrected
                )

            elif issue_code == 'bare_except':
                corrected = _re.sub(
                    r'except\s*:', 'except Exception:', corrected
                )

            elif issue_code in ('weak_hash_md5', 'weak_hash_sha1'):
                if 'md5' in issue_code:
                    corrected = _re.sub(
                        r'hashlib\.md5\b', 'hashlib.sha256', corrected
                    )
                elif 'sha1' in issue_code:
                    corrected = _re.sub(
                        r'hashlib\.sha1\b', 'hashlib.sha256', corrected
                    )

        return corrected

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
    #  DAG-SPECIFIC PUBLIC API
    # ============================================================

    async def generate_fractal_app(self, description: str,
                                    project_name: str = "generated_project",
                                    project_type: str = "",
                                    language: str = "python",
                                    output_dir: str = "") -> Dict[str, Any]:
        """Brecha C: Genera una app completa usando Generación Fractal (Top-Down)."""
        fractal_result = self._fractal_gen.generate_project(
            description=description,
            project_type=project_type,
            project_name=project_name,
            language=language,
            output_dir=output_dir,
        )

        if self._memory and fractal_result.status == "complete":
            self._memory.save_project(
                project_name=project_name,
                project_type=project_type,
                description=description,
                path=output_dir,
                status="generated_fractal",
                entities=[],
                endpoints=[],
            )
            self._memory.save_episode(
                event_type="fractal_app_generated",
                description=f"Fractal generated {project_type} app: {project_name}",
                context=description[:200],
                outcome="success",
                importance=0.9,
            )

        return {
            "status": fractal_result.status,
            "project_name": fractal_result.project_name,
            "project_type": project_type,
            "files_generated": fractal_result.files_generated,
            "total_files": fractal_result.total_files,
            "items_completed": fractal_result.items_completed,
            "items_total": fractal_result.items_total,
            "current_phase": fractal_result.current_phase,
            "error": fractal_result.error,
        }

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
