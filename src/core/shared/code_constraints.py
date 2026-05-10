"""
ZENIC LOGIC — Code Constraint Builder

Builds constraints from AST analysis for Z3/AC-3 constraint solving.
Used by the APA Planner's solver to generate constraint domains for
code verification and step planning.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CodeConstraintBuilder:
    """Builds constraint specifications from code analysis.

    Transforms AST analysis results and code context into constraint
    domains that can be fed to Z3Solver or AC-3 ConstraintSolver.

    This is a lightweight implementation — the full Z3 integration
    lives in z3_parts/solver_encoding.py.
    """

    def __init__(self) -> None:
        self._domains: Dict[str, List[Any]] = {}
        self._constraints: List[Dict[str, Any]] = []

    def add_domain(self, name: str, values: List[Any]) -> None:
        """Add a variable domain."""
        self._domains[name] = values

    def add_constraint(self, constraint: Dict[str, Any]) -> None:
        """Add a constraint specification."""
        self._constraints.append(constraint)

    def build_from_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Build constraint specification from AST analysis results.

        Args:
            analysis: Dict with AST analysis results (imports, functions,
                      classes, complexity metrics, etc.)

        Returns:
            Dict with 'domains' and 'constraints' for the solver.
        """
        # Extract domains from analysis
        if "imports" in analysis:
            self.add_domain("imports", analysis["imports"])
        if "functions" in analysis:
            self.add_domain("functions", analysis["functions"])
        if "classes" in analysis:
            self.add_domain("classes", analysis["classes"])

        return {
            "domains": dict(self._domains),
            "constraints": list(self._constraints),
        }

    def reset(self) -> None:
        """Clear all domains and constraints."""
        self._domains.clear()
        self._constraints.clear()
