"""
TITAN OMNISCALE X - Motor de IA Quirurgico Local v16

Pipeline de 8 niveles con Z3 SMT Solver, MCTS real,
Ejecucion Simbolica, Timeout enforcement, Cache de Teoremas,
Protocolo Abortivo y Razonamiento Parcial.

Compatible con Android (Termux + proot-distro).
"""

__all__ = ["TitanOrchestrator", "DAGOrchestrator"]


def __getattr__(name):
    if name == "TitanOrchestrator":
        from src.core.orchestrator import TitanOrchestrator
        return TitanOrchestrator
    if name == "DAGOrchestrator":
        from src.core.dag_orchestrator import DAGOrchestrator
        return DAGOrchestrator
    if name == "patterns":
        from src.core import patterns
        return patterns
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
