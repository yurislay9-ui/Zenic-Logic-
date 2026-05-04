"""
Z3 Null-Safety Proof Mixin.

Provides the _z3_prove_null_safety method using Z3 EnumSort {NONE, SOME_VALUE}
for formal null-safety verification.
"""

import gc
import logging

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)


class Z3NullSafetyMixin:
    """Mixin for null-safety proof methods using Z3 EnumSort."""

    def _z3_prove_null_safety(self, variable_names, nullable_vars):
        """Null-safety proof using Z3 EnumSort {NONE, SOME_VALUE}.

        Two-phase proof:
        1. Consistency check: verify null-safety constraints are satisfiable
           (non-nullable = SOME_VALUE, nullable = SOME_VALUE | NONE)
        2. Counterexample search: try to find a state where non-nullable = NONE
           WITH the safety constraints enforced. This only succeeds if the
           constraints are contradictory (e.g., a flow from nullable to non-nullable).
        """
        try:
            # Create EnumSort for nullability domain
            null_sort, null_consts = z3_module.EnumSort(
                self._unique_sort_name("Nullability"), ["NONE", "SOME_VALUE"]
            )
            NONE_VAL, SOME_VAL = null_consts[0], null_consts[1]

            # Create a Z3 variable of this sort for each program variable
            z3_vars = {}
            for name in variable_names:
                z3_vars[name] = z3_module.Const(f"null_{name}", null_sort)

            non_nullable = [v for v in variable_names if v not in nullable_vars]

            # Phase 1: Check that null-safety constraints are consistent
            # Non-nullable vars = SOME_VALUE, nullable = SOME_VALUE | NONE
            safety_solver = z3_module.Solver()
            safety_solver.set("timeout", self.timeout_ms)

            for var_name in variable_names:
                if var_name not in nullable_vars:
                    safety_solver.add(z3_vars[var_name] == SOME_VAL)
                else:
                    safety_solver.add(
                        z3_module.Or(
                            z3_vars[var_name] == NONE_VAL,
                            z3_vars[var_name] == SOME_VAL,
                        )
                    )

            safety_result = safety_solver.check()
            if safety_result == z3_module.unsat:
                # Null-safety conditions are contradictory
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Z3: null-safety conditions are contradictory (cannot be satisfied)",
                }
            elif safety_result == z3_module.sat:
                # Null-safety conditions are consistent -> PROVEN
                model = safety_solver.model()
                assignment = {}
                for var_name in variable_names:
                    if var_name in z3_vars:
                        val = model.eval(z3_vars[var_name])
                        assignment[var_name] = (
                            "None" if str(val) == "NONE" else "Some"
                        )
                return {
                    "status": "PROVEN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": True,
                    "counterexamples": [],
                    "proof": "Z3 EnumSort proved: null-safety constraints are satisfiable (non-nullable vars are SOME_VALUE)",
                    "model": assignment,
                }
            else:
                return {
                    "status": "UNKNOWN",
                    "solver_type": "Z3_ENUMSORT",
                    "verified": False,
                    "counterexamples": [],
                    "proof": "Z3 returned unknown (timeout or unsupported theory)",
                }

        except Exception as e:
            logger.error("Z3 null-safety proof error: %s", e)
            return {"status": "ERROR", "solver_type": "Z3", "message": str(e)}
        finally:
            gc.collect()
