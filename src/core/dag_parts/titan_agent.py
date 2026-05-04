"""
TitanAgent (F1) - Meta-router del DAG.

Agente meta-router que decide dinámicamente la siguiente transición
del DAG usando el LLM, con fallback al pipeline secuencial original.
"""

from typing import Dict, Any, Optional

from src.core.agents.base import BaseAgent
from src.core.dag_parts.definition import PIPELINE_DAG


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
