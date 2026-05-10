"""
TITAN OMNISCALE X - Motor de IA Quirurgico Local v16.1

Pipeline DAG de 22 nodos con Z3 SMT Solver (opcional), MCTS real,
Timeout enforcement, Cache de Teoremas, Protocolo Abortivo
y Razonamiento Parcial.

Compatible con Android (Termux + proot-distro).
"""

__all__ = ["DAGOrchestrator"]


def __getattr__(name):
    if name == "DAGOrchestrator":
        from src.core.dag_orchestrator import DAGOrchestrator
        return DAGOrchestrator
    if name == "patterns":
        from src.core import patterns
        return patterns
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
