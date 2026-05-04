"""
Z3 Solver Core Mixin.

Provides the core Z3 solving functionality:
- _z3_solve: Main CSP solving using Z3 with native symbolic variables
- _unique_sort_name: Unique Z3 sort name generator
- _decode_native_z3_value: Native Z3 value decoding
- _model_to_dict: Model conversion helper

Domain classification and constraint encoding helpers are in solver_encoding.py.
Bijective value encoding/decoding helpers are in solver_encoding.py.
"""

import time
import gc
import logging

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

from ..constraint_solver import ConstraintSolver

logger = logging.getLogger(__name__)


class Z3SolverCoreMixin:
    """Mixin for core Z3 solving methods and native value decoding."""

    def _unique_sort_name(self, base):
        """Generate a unique Z3 sort name to avoid 'already declared' errors."""
        self._sort_counter += 1
        # Include timestamp + counter for global uniqueness across solver instances
        return f"{base}_{self._sort_counter}_{int(time.time() * 1000) % 1000000}"

    def _z3_solve(self, domains, constraints):
        """
        Solve a CSP using Z3 with NATIVE symbolic variables (Deep Encoding).

        Instead of the old bijective int-encoding that hashed all values to
        integers (losing semantic information), this implementation:

        1. DETECTS the domain type for each variable:
           - ENUM domains (finite sets of strings) -> z3.EnumSort
           - NUMERIC domains (all int/float)       -> z3.Int or z3.Real
           - BOOLEAN domains (bool values)          -> z3.Bool
           - MIXED domains                          -> z3.EnumSort (safe fallback)

        2. ENCODES constraints as NATIVE Z3 expressions:
           - For EnumSort vars: direct equality comparisons
           - For Int/Real vars: arithmetic + relational constraints
           - For Bool vars: logical implication/conjunction
           - Uses z3.Implies, z3.If for conditional constraints

        3. GENERATES counterexamples from solver.model() with
           human-readable values (not encoded integers).

        4. Falls back to EnumSort for any domain that cannot be
           purely typed, ensuring correctness always.
        """
        try:
            solver = z3_module.Solver()
            solver.set("timeout", self.timeout_ms)

            # --- Phase 1: Classify domains and create Z3 variables ---
            z3_vars = {}          # var_name -> z3 variable
            var_meta = {}         # var_name -> {type, sort, const_map, domain_vals}
            enum_sorts = []       # Track EnumSort objects for memory cleanup

            for var_name, values in domains.items():
                if not values:
                    continue

                domain_type = self._classify_domain(values)
                meta = {"type": domain_type, "values": values}

                if domain_type == "ENUM":
                    # Finite string/symbol domain -> EnumSort (native Z3)
                    enum_name = self._unique_sort_name(var_name)
                    # Z3 EnumSort requires >= 1 constructor; if single value, add placeholder
                    enum_vals = list(values)
                    if len(enum_vals) == 1:
                        enum_vals.append(f"__{var_name}_placeholder__")
                    sort, consts = z3_module.EnumSort(enum_name, [str(v) for v in enum_vals])
                    const_map = {}  # value_str -> z3 constant
                    for i, val in enumerate(enum_vals):
                        const_map[str(val)] = consts[i]
                        const_map[val] = consts[i]  # Also map by original value
                    meta["sort"] = sort
                    meta["const_map"] = const_map
                    meta["enum_vals"] = enum_vals
                    z3_vars[var_name] = z3_module.Const(f"enum_{var_name}", sort)
                    enum_sorts.append(sort)

                    # Domain constraint: variable must be one of the domain values
                    valid_consts = [const_map[str(v)] for v in values if str(v) in const_map]
                    if valid_consts:
                        solver.add(z3_module.Or(*[z3_vars[var_name] == c for c in valid_consts]))

                elif domain_type == "NUMERIC_INT":
                    # All-integer domain -> z3.Int
                    z3_vars[var_name] = z3_module.Int(f"int_{var_name}")
                    meta["sort"] = "Int"
                    # Add range constraints
                    int_vals = [v for v in values if isinstance(v, int)]
                    if int_vals:
                        solver.add(z3_module.Or(*[z3_vars[var_name] == v for v in int_vals]))

                elif domain_type == "NUMERIC_REAL":
                    # Float domain -> z3.Real
                    z3_vars[var_name] = z3_module.Real(f"real_{var_name}")
                    meta["sort"] = "Real"
                    float_vals = [v for v in values if isinstance(v, (int, float))]
                    if float_vals:
                        solver.add(z3_module.Or(*[z3_vars[var_name] == v for v in float_vals]))

                elif domain_type == "BOOLEAN":
                    # Boolean domain -> z3.Bool
                    z3_vars[var_name] = z3_module.Bool(f"bool_{var_name}")
                    meta["sort"] = "Bool"
                    # If domain has both True/False, no constraint needed
                    # If only one, constrain to that value
                    has_true = any(v is True or v == True for v in values)
                    has_false = any(v is False or v == False for v in values)
                    if has_true and not has_false:
                        solver.add(z3_vars[var_name] == True)
                    elif has_false and not has_true:
                        solver.add(z3_vars[var_name] == False)

                else:
                    # MIXED domain -> EnumSort (safe fallback)
                    enum_name = self._unique_sort_name(var_name)
                    str_vals = [str(v) for v in values]
                    if len(str_vals) == 1:
                        str_vals.append(f"__{var_name}_placeholder__")
                    sort, consts = z3_module.EnumSort(enum_name, str_vals)
                    const_map = {sv: consts[i] for i, sv in enumerate(str_vals)}
                    # Also map original values
                    for i, v in enumerate(values):
                        const_map[v] = consts[i]
                    meta["sort"] = sort
                    meta["const_map"] = const_map
                    meta["enum_vals"] = str_vals
                    z3_vars[var_name] = z3_module.Const(f"mix_{var_name}", sort)
                    enum_sorts.append(sort)

                    valid_consts = [const_map[str(v)] for v in values if str(v) in const_map]
                    if valid_consts:
                        solver.add(z3_module.Or(*[z3_vars[var_name] == c for c in valid_consts]))

                var_meta[var_name] = meta

            # --- Phase 2: Encode constraints as native Z3 expressions ---
            for c in constraints:
                if c.var1 not in z3_vars or c.var2 not in z3_vars:
                    continue

                meta1 = var_meta.get(c.var1, {})
                meta2 = var_meta.get(c.var2, {})
                type1 = meta1.get("type", "ENUM")
                type2 = meta2.get("type", "ENUM")

                if type1 == "ENUM" or type2 == "ENUM" or type1 == "MIXED" or type2 == "MIXED":
                    # Enum/Mixed domains: build constraint from valid pairs
                    # but express them as native Z3 equality, not int comparisons
                    self._add_enum_constraint(
                        solver, z3_vars, var_meta, c
                    )
                elif type1 == "NUMERIC_INT" and type2 == "NUMERIC_INT":
                    # Both Int: try to build native arithmetic constraint
                    self._add_numeric_constraint(
                        solver, z3_vars, c, "int"
                    )
                elif type1 == "BOOLEAN" and type2 == "BOOLEAN":
                    # Both Bool: build logical constraint
                    self._add_boolean_constraint(
                        solver, z3_vars, c
                    )
                else:
                    # Cross-type: use EnumSort valid-pair encoding
                    self._add_enum_constraint(
                        solver, z3_vars, var_meta, c
                    )

            # --- Phase 3: Solve and extract model ---
            result = solver.check()

            if result == z3_module.sat:
                model = solver.model()
                assignment = {}
                counterexample = {}
                for var_name, z3_var in z3_vars.items():
                    val = model.eval(z3_var, model_completion=True)
                    meta = var_meta.get(var_name, {})
                    assignment[var_name] = self._decode_native_z3_value(
                        val, meta
                    )
                    counterexample[var_name] = str(val)

                return {
                    "status": "SATISFIED",
                    "solver_type": "Z3_DEEP_NATIVE",
                    "assignment": assignment,
                    "counterexample": counterexample,
                    "variable_types": {k: v.get("type", "UNKNOWN") for k, v in var_meta.items()},
                }
            elif result == z3_module.unsat:
                return {
                    "status": "UNSATISFIABLE",
                    "solver_type": "Z3_DEEP_NATIVE",
                    "assignment": None,
                    "variable_types": {k: v.get("type", "UNKNOWN") for k, v in var_meta.items()},
                }
            else:
                return {
                    "status": "TIMEOUT",
                    "solver_type": "Z3_DEEP_NATIVE",
                    "assignment": None,
                    "variable_types": {k: v.get("type", "UNKNOWN") for k, v in var_meta.items()},
                }

        except Exception as e:
            logger.error("Z3 deep solve error: %s", e)
            # Fallback a AC-3
            ac3 = ConstraintSolver(timeout_ms=self.timeout_ms)
            result = ac3.solve(domains, constraints)
            result["solver_type"] = "AC3_FALLBACK"
            return result
        finally:
            gc.collect()

    # ================================================================
    #  Z3 value decoding (native types, not bijective)
    # ================================================================

    def _decode_native_z3_value(self, z3_val, meta):
        """
        Decode a Z3 model value back to a Python value using the
        native type information (not bijective integer mapping).
        """
        domain_type = meta.get("type", "ENUM")

        try:
            if domain_type == "ENUM" or domain_type == "MIXED":
                const_map = meta.get("const_map", {})
                val_str = str(z3_val)
                # Direct lookup in const_map
                if val_str in const_map:
                    return val_str
                # Try reverse lookup from original values
                for orig_val, z3_const in const_map.items():
                    if str(z3_const) == val_str:
                        return orig_val
                return val_str

            elif domain_type == "NUMERIC_INT":
                return z3_val.as_long()

            elif domain_type == "NUMERIC_REAL":
                # Z3 Real values: try as_decimal or as_fraction
                try:
                    dec_str = z3_val.as_decimal(6)
                    return float(dec_str)
                except Exception as e:
                    logger.debug("Z3Solver: Numeric value conversion failed: %s", e)
                    return str(z3_val)

            elif domain_type == "BOOLEAN":
                return bool(z3_val)

        except Exception as decode_err:
            logger.debug(f"Z3Solver: Value decoding failed: {decode_err}")

        return str(z3_val)

    # ================================================================
    #  Model conversion
    # ================================================================

    def _model_to_dict(self, model, z3_vars):
        """Convert a Z3 model to a plain dict of string values."""
        result = {}
        for name, var in z3_vars.items():
            val = model.eval(var)
            result[name] = str(val)
        return result
