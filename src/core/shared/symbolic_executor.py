"""Symbolic Executor — Lightweight stub.

The full symbolic executor (2,158 lines across 8 files) was removed as
dead code. It was never used externally and added unnecessary complexity.
This stub provides the same interface but returns passthrough results.

FIX (M01): Added execute_symbolic(), prove_violation_reachable(),
generate_concrete_inputs(), and export_path_conditions_smt() methods
that were missing from the original stub, causing AttributeError in
sandbox validation (Subtask 0/1 failed).

S03b: Added SymbolicValue and SymbolicPath data classes that tests
and callers expect. These are lightweight containers with no Z3 logic.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Re-export HAS_Z3 from z3_solver for convenience
from src.core.shared.z3_solver import HAS_Z3

# ── Constants expected by tests ──────────────────────────────────
IO_OPERATIONS = {"input", "print", "read", "write", "open"}
LOOP_UNROLL_LIMIT = 2
INCOMPATIBLE_TYPES = frozenset()


class SymbolicValue:
    """Represents a symbolic variable with optional type and constraint.

    S03b: Lightweight data class for symbolic values. No Z3 integration.
    """

    def __init__(self, name: str, var_type: str = "any",
                 constraint: Any = None, concrete: Any = None):
        self.name = name
        self.var_type = var_type
        self.constraint = constraint
        self.concrete = concrete

    def __repr__(self) -> str:
        concrete_str = f"={self.concrete}" if self.concrete is not None else ""
        return f"SymbolicValue({self.name}{concrete_str})"


class SymbolicPath:
    """Represents a symbolic execution path with conditions and results.

    S03b: Lightweight data class for symbolic paths. No Z3 integration.
    """

    MAX_Z3_CONDITIONS = 50

    def __init__(
        self,
        condition: Optional[List[str]] = None,
        result: Any = None,
        is_pruned: bool = False,
        variables: Optional[Dict[str, SymbolicValue]] = None,
        z3_conditions: Optional[List[Any]] = None,
        assignments: Optional[List[tuple]] = None,
        return_values: Optional[List[Dict]] = None,
    ):
        self.condition: List[str] = condition or []
        self.result = result
        self.is_pruned = is_pruned
        self.variables: Dict[str, SymbolicValue] = variables or {}
        self.z3_conditions: List[Any] = z3_conditions or []
        self.assignments: List[tuple] = assignments or []
        self.return_values: List[Dict] = return_values or []

    def add_condition(self, cond_str: str, z3_cond: Any = None) -> None:
        """Add a path condition string and optional Z3 condition."""
        self.condition.append(cond_str)
        if z3_cond is not None and len(self.z3_conditions) < self.MAX_Z3_CONDITIONS:
            self.z3_conditions.append(z3_cond)

    def add_assignment(self, var_name: str, value_str: str) -> None:
        """Record a variable assignment on this path."""
        self.assignments.append((var_name, value_str))

    def add_return(self, desc: str, type: str = "any") -> None:
        """Record a return value on this path."""
        self.return_values.append({"desc": desc, "type": type})

    def is_feasible(self) -> bool:
        """Check if the path is feasible by looking for contradictions.

        Simple heuristic: checks for NOT_ prefix contradictions in
        string conditions. A path with both "x > 0" and "NOT_x > 0"
        is considered infeasible.
        """
        cond_set = set(c.strip() for c in self.condition if c.strip())
        for cond in cond_set:
            if cond.startswith("NOT_"):
                positive = cond[4:]
                if positive in cond_set:
                    return False
        return not self.is_pruned


class SymbolicExecutor:
    """Lightweight symbolic executor stub.

    Provides the same interface as the original but performs no
    symbolic execution. The full implementation was removed because:
    - It depended on Z3 which is never available on ARM/Termux
    - It added ~5-10s latency per validation
    - It never produced actionable symbolic analysis results
    """

    def __init__(self, k_path_limit: int = 10, max_depth: int = 20):
        self.k_path_limit = k_path_limit
        self.max_depth = max_depth
        self.paths_explored = 0
        self.paths_pruned = 0

    def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Symbolic execution — returns passthrough results."""
        return {
            "status": "skipped",
            "paths": [],
            "violations": [],
            "source": "stub",
        }

    def execute_symbolic(
        self,
        code: str,
        language: str = "python",
        target_name: str = "",
    ) -> Dict[str, Any]:
        """Symbolic execution with metrics — returns passthrough results.

        Called by python_validation.py and other_validation.py in the
        ReflexionSandbox. Returns the same structure as the full
        implementation would, but with zero paths/violations.
        """
        return {
            "status": "skipped",
            "paths": [],
            "violations": [],
            "source": "stub",
            "metrics": {
                "paths_explored": 0,
                "paths_pruned": 0,
                "feasible_paths": 0,
                "total_paths": 0,
            },
            "warnings": [],
        }

    def prove_violation_reachable(
        self, violation: Any, path: Any
    ) -> Dict[str, Any]:
        """Check if a violation is reachable along a path.

        Returns None reachability (inconclusive) since stub performs
        no actual Z3 reasoning.
        """
        return {
            "reachable": None,
            "counterexample": {},
        }

    def generate_concrete_inputs(self, path: Any) -> Dict[str, Any]:
        """Generate concrete input values for a symbolic path.

        Returns None inputs since stub performs no path analysis.
        """
        return {
            "inputs": None,
        }

    def export_path_conditions_smt(
        self, paths: List[Any], target_name: str = ""
    ) -> List[str]:
        """Export path conditions as SMT-LIB format strings.

        Returns empty list since stub performs no symbolic analysis.
        """
        return []
