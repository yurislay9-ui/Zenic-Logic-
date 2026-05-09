"""
DAG Definition - Nodos y transiciones del pipeline.

Contains the DAGNode dataclass, PIPELINE_DAG constant dict,
and extracted constants used across the DAG orchestrator.
"""

from typing import Dict, Any, List
from dataclasses import dataclass, field


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
        transitions={"hit": "DONE", "miss": "CHAT_DETECT"},
        default_next="CHAT_DETECT",
    ),
    # ── FAST PATH: Chat Mode ──────────────────────────────────
    # Detects simple conversational messages and responds directly
    # WITHOUT running the full 15-node DAG pipeline.
    # This reduces "Hola" from 15+ nodes / 3-4 LLM calls / 15-60s
    # → 2 nodes / 0 LLM calls / <100ms
    "CHAT_DETECT": DAGNode(
        name="CHAT_DETECT",
        exec_method="_exec_chat_detect",
        transitions={"chat": "CHAT_RESPOND", "pipeline": "INTENT"},
        default_next="INTENT",
    ),
    "CHAT_RESPOND": DAGNode(
        name="CHAT_RESPOND",
        exec_method="_exec_chat_respond",
        transitions={"*": "DONE"},
        default_next="DONE",
    ),
    # ── FULL PIPELINE ─────────────────────────────────────────
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
            "visual": "VISUAL_BYPASS",
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
        max_retries=3,  # Must match VALIDATE's F5 correction loop (3 cycles)
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
    "VISUAL_BYPASS": DAGNode(
        name="VISUAL_BYPASS",
        exec_method="_exec_visual_bypass",
        transitions={
            "success": "MEMORY_SAVE",
            "fallback": "EXECUTE_STEPS",
        },
        default_next="EXECUTE_STEPS",
        criticality_skip=[3],  # Always skip SURGICAL level for visual requests
        max_retries=1,
    ),
}
