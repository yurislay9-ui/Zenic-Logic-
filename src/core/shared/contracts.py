"""
TITAN OMNISCALE X - Contratos de Datos v13 (Facade Module)

This module re-exports all contracts from their dedicated sub-modules
for backward compatibility. The original monolith has been decomposed into:

- types.py: Data types and payloads
- mcts.py: Monte Carlo Tree Search
- constraint_solver.py: AC-3 + Backtracking CSP solver
- z3_solver.py: Z3 SMT Solver wrapper
- timeout.py: Timeout enforcement
- code_constraints.py: Code constraint builder
- symbolic_executor.py: Symbolic execution engine
- kpath_analyzer.py: K-Path dependency analyzer

Any code that does `from src.core.shared.contracts import X` will continue to work.
"""

from .types import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
    IntentPayload, RoutingPayload, PlanStep, ExecutionPlan,
    SandboxResult, MerkleNode, ChatMessage, ChatRequest,
)
from .mcts import MCTSNode, MCTSPlanner
from .constraint_solver import Constraint, ConstraintSolver
from .z3_solver import Z3Solver, HAS_Z3
from .timeout import TimeoutEnforcer
from .code_constraints import CodeConstraintBuilder
from .symbolic_executor import SymbolicValue, SymbolicPath, SymbolicExecutor
from .kpath_analyzer import KPathAnalyzer

__all__ = [
    "OperationType", "GoalType", "CriticalityLevel", "RoutePath",
    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest",
    "MCTSNode", "MCTSPlanner",
    "Constraint", "ConstraintSolver",
    "Z3Solver", "HAS_Z3",
    "TimeoutEnforcer",
    "CodeConstraintBuilder",
    "SymbolicValue", "SymbolicPath", "SymbolicExecutor",
    "KPathAnalyzer",
]
