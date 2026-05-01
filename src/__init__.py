"""
TITAN OMNISCALE X - Motor de IA Quirurgico Local v13

Pipeline de 8 niveles con Z3 SMT Solver, MCTS real,
Ejecucion Simbolica, Timeout enforcement, Cache de Teoremas,
Protocolo Abortivo y Razonamiento Parcial.

Compatible con Android (Termux + proot-distro).
"""

from src.core.orchestrator import TitanOrchestrator

__all__ = ["TitanOrchestrator"]
