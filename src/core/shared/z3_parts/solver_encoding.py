"""
Z3 Solver Encoding Mixin.

Provides domain classification and constraint encoding helpers:
- _classify_domain: Domain type classification (ENUM, NUMERIC_INT, NUMERIC_REAL, BOOLEAN, MIXED)
- _add_enum_constraint: Enum/Mixed constraint encoding
- _add_numeric_constraint: Numeric constraint encoding (FIXED: proper fallback)
- _add_boolean_constraint: Boolean constraint encoding
- _encode_value: Bijective value encoding to integers
- _decode_value: Bijective value decoding from integers
- _reset_encoding: Clear encoding maps to prevent unbounded memory growth

FIX (Phase 2): _add_numeric_constraint fallback was trivially true
(Implies(v1 == v2, True)). Now uses domain-aware sampling with the
constraint's .satisfied() method to build proper Z3 constraints.

FIX (Phase 3): Added _reset_encoding() to prevent unbounded growth of
_encode_map/_decode_map across solver invocations. Added max size limit
with LRU-style eviction when maps exceed _MAX_ENCODE_ENTRIES.
"""

import logging

try:
    import z3 as z3_module
    _HAS_Z3 = True
except ImportError:
    _HAS_Z3 = False

logger = logging.getLogger(__name__)

# Maximum domain size for exhaustive pair enumeration in numeric fallback
_MAX_EXHAUSTIVE_PAIRS = 500
# Maximum entries in bijective encoding maps before eviction (Phase 3)
_MAX_ENCODE_ENTRIES = 10000
# Number of entries to evict when limit is reached
_EVICT_BATCH_SIZE = 2000
# Default max samples for numeric domain sampling
_DEFAULT_MAX_SAMPLES = 20
# Decimal precision for Z3 Real value conversion
_REAL_DECIMAL_PRECISION = 6


class Z3SolverEncodingMixin:
    """Mixin for domain classification and Z3 constraint encoding helpers."""

    # ================================================================
    #  Domain classification
    # ================================================================

    def _classify_domain(self, values):
        """
        Classify a domain into its Z3-native type.

        Returns one of: 'ENUM', 'NUMERIC_INT', 'NUMERIC_REAL', 'BOOLEAN', 'MIXED'
        """
        if not values:
            return "ENUM"

        has_int = False
        has_float = False
        has_bool = False
        has_str = False
        has_other = False

        for v in values:
            if isinstance(v, bool):
                has_bool = True
            elif isinstance(v, int):
                has_int = True
            elif isinstance(v, float):
                has_float = True
            elif isinstance(v, str):
                has_str = True
            else:
                has_other = True

        # Pure boolean
        if has_bool and not has_int and not has_float and not has_str and not has_other:
            return "BOOLEAN"

        # Pure numeric
        if (has_int or has_float) and not has_str and not has_bool and not has_other:
            if has_float:
                return "NUMERIC_REAL"
            return "NUMERIC_INT"

        # Pure string / enum
        if has_str and not has_int and not has_float and not has_bool and not has_other:
            return "ENUM"

        # Anything else -> mixed
        return "MIXED"

    # ================================================================
    #  Constraint encoding helpers
    # ================================================================

    def _add_enum_constraint(self, solver, z3_vars, var_meta, constraint):
        """
        Add a constraint between Enum/Mixed variables as native Z3
        equality expressions.

        Instead of the old approach (enumerate all valid pairs and
        encode each as an And of Int equalities), this builds the
        constraint using Z3's Or/And/Implies on EnumSort constants.

        For each valid pair (v1, v2), creates:
            And(var1 == const_v1, var2 == const_v2)
        Then wraps all valid pairs in Or().
        This is semantically equivalent but uses Z3's native sort
        system for better pruning and theory combination.
        """
        meta1 = var_meta.get(constraint.var1, {})
        meta2 = var_meta.get(constraint.var2, {})
        const_map1 = meta1.get("const_map", {})
        const_map2 = meta2.get("const_map", {})

        valid_pairs = []
        for v1 in meta1.get("values", []):
            for v2 in meta2.get("values", []):
                try:
                    if constraint.satisfied(v1, v2):
                        key1 = str(v1)
                        key2 = str(v2)
                        z3_const1 = const_map1.get(key1) if key1 in const_map1 else const_map1.get(v1)
                        z3_const2 = const_map2.get(key2) if key2 in const_map2 else const_map2.get(v2)
                        if z3_const1 is not None and z3_const2 is not None:
                            valid_pairs.append(
                                z3_module.And(
                                    z3_vars[constraint.var1] == z3_const1,
                                    z3_vars[constraint.var2] == z3_const2,
                                )
                            )
                except Exception as e:
                    logger.debug("Z3Solver: Enum constraint pair failed: %s", e)
                    continue

        if valid_pairs:
            solver.add(z3_module.Or(*valid_pairs))
        else:
            solver.add(z3_module.BoolVal(False))

    def _add_numeric_constraint(self, solver, z3_vars, constraint, num_type="int",
                                 var_meta=None):
        """
        Add a constraint between numeric variables using native
        Z3 arithmetic/comparison expressions.

        Attempts to detect common constraint patterns:
        - Inequality: v1 != v2, v1 < v2, v1 > v2
        - Ordering: v1 <= v2
        - Equality: v1 == v2
        - Functional: v1 == v2 + k, v1 == v2 * k

        FIX (Phase 2): The fallback previously added a trivially true
        constraint (Implies(v1 == v2, True)). Now it uses domain-aware
        sampling with the constraint's .satisfied() method to build
        proper Z3 constraints from the actual predicate behavior.
        """
        v1 = z3_vars[constraint.var1]
        v2 = z3_vars[constraint.var2]

        # Try to detect the constraint pattern from the description
        desc = constraint.description.lower()

        # Pattern: "not equal" / "!="
        if "not_equal" in desc or "!=" in desc or "not equal" in desc:
            solver.add(v1 != v2)
            return

        # Pattern: "less than" / "<"
        if "less_than" in desc or " < " in desc:
            solver.add(v1 < v2)
            return

        # Pattern: "greater than" / ">"
        if "greater_than" in desc or " > " in desc:
            solver.add(v1 > v2)
            return

        # Pattern: "less or equal" / "<="
        if "less_or_equal" in desc or "<=" in desc:
            solver.add(v1 <= v2)
            return

        # Pattern: "greater or equal" / ">="
        if "greater_or_equal" in desc or ">=" in desc:
            solver.add(v1 >= v2)
            return

        # Pattern: "equal" / "=="
        if "equal" in desc and "not_equal" not in desc:
            solver.add(v1 == v2)
            return

        # ============================================================
        #  FIXED FALLBACK: Domain-aware constraint encoding
        #  Instead of trivially true Implies(v1==v2, True), we now
        #  enumerate domain values and test constraint.satisfied()
        #  to build proper Z3 constraints.
        # ============================================================
        if var_meta is not None:
            meta1 = var_meta.get(constraint.var1, {})
            meta2 = var_meta.get(constraint.var2, {})
            vals1 = meta1.get("values", [])
            vals2 = meta2.get("values", [])

            if vals1 and vals2:
                total_pairs = len(vals1) * len(vals2)

                if total_pairs <= _MAX_EXHAUSTIVE_PAIRS:
                    # Exhaustive enumeration: test every (v1, v2) pair
                    valid_conditions = []
                    for val1 in vals1:
                        for val2 in vals2:
                            try:
                                if constraint.satisfied(val1, val2):
                                    # Build Z3 condition for this valid pair
                                    cond1 = (v1 == val1) if num_type == "int" else (v1 == z3_module.RealVal(str(val1)))
                                    cond2 = (v2 == val2) if num_type == "int" else (v2 == z3_module.RealVal(str(val2)))
                                    valid_conditions.append(z3_module.And(cond1, cond2))
                            except Exception:
                                continue

                    if valid_conditions:
                        solver.add(z3_module.Or(*valid_conditions))
                    else:
                        # No valid pairs → constraint is unsatisfiable
                        solver.add(z3_module.BoolVal(False))
                        logger.debug(
                            "Numeric constraint '%s': no valid pairs found — adding False",
                            constraint.description
                        )
                    return
                else:
                    # Large domain: sample representative values
                    # Group vals1 into bins and test boundary + midpoint values
                    sample1 = self._sample_numeric_domain(vals1, max_samples=_DEFAULT_MAX_SAMPLES)
                    sample2 = self._sample_numeric_domain(vals2, max_samples=_DEFAULT_MAX_SAMPLES)

                    valid_conditions = []
                    for val1 in sample1:
                        for val2 in sample2:
                            try:
                                if constraint.satisfied(val1, val2):
                                    cond1 = (v1 == val1) if num_type == "int" else (v1 == z3_module.RealVal(str(val1)))
                                    cond2 = (v2 == val2) if num_type == "int" else (v2 == z3_module.RealVal(str(val2)))
                                    valid_conditions.append(z3_module.And(cond1, cond2))
                            except Exception:
                                continue

                    if valid_conditions:
                        # Use Implies for sampled valid pairs (approximate)
                        # This is less precise than exhaustive but handles large domains
                        solver.add(z3_module.Or(*valid_conditions))
                        logger.debug(
                            "Numeric constraint '%s': sampled %d/%d pairs, found %d valid",
                            constraint.description,
                            len(sample1) * len(sample2),
                            total_pairs,
                            len(valid_conditions),
                        )
                    else:
                        solver.add(z3_module.BoolVal(False))
                    return

        # Last resort: if no domain info available at all, log a warning
        # and add a minimal constraint (v1 and v2 are related)
        logger.warning(
            "Numeric constraint '%s' has no domain info — adding equality fallback. "
            "Consider providing var_meta for proper constraint encoding.",
            constraint.description
        )
        solver.add(v1 == v2)

    def _sample_numeric_domain(self, values, max_samples=_DEFAULT_MAX_SAMPLES):
        """Sample representative values from a numeric domain for constraint testing.

        Strategy: take min, max, midpoint, and evenly spaced interior values.
        """
        if len(values) <= max_samples:
            return list(values)

        sorted_vals = sorted(set(v for v in values if isinstance(v, (int, float))))
        if not sorted_vals:
            return values[:max_samples]

        if len(sorted_vals) <= max_samples:
            return sorted_vals

        # Uniform sampling across the range
        step = (len(sorted_vals) - 1) / (max_samples - 1)
        indices = [int(round(i * step)) for i in range(max_samples)]
        indices = sorted(set(max(0, min(i, len(sorted_vals) - 1)) for i in indices))

        return [sorted_vals[i] for i in indices]

    def _add_boolean_constraint(self, solver, z3_vars, constraint):
        """
        Add a constraint between boolean variables using Z3 logical
        operators (Implies, And, Or, Not).

        Common patterns:
        - Implication: v1 implies v2
        - Equivalence: v1 == v2
        - Exclusion: Not(And(v1, v2))
        - Dependency: v1 requires v2 (Implies(v1, v2))
        """
        v1 = z3_vars[constraint.var1]
        v2 = z3_vars[constraint.var2]
        desc = constraint.description.lower()

        # Pattern: "implies" / "requires"
        if "implies" in desc or "requires" in desc:
            solver.add(z3_module.Implies(v1, v2))
            return

        # Pattern: "excludes" / "mutually exclusive"
        if "exclu" in desc or "mutual" in desc:
            solver.add(z3_module.Not(z3_module.And(v1, v2)))
            return

        # Pattern: "equivalent" / "iff" / "same"
        if "equivalent" in desc or "iff" in desc or "same" in desc:
            solver.add(v1 == v2)
            return

        # Default: test the predicate and encode with Implies
        # If predicate(True, True) -> no constraint needed for (T,T)
        # Build: For each boolean combo, if NOT satisfied -> exclude
        for v1_val in [True, False]:
            for v2_val in [True, False]:
                if not constraint.satisfied(v1_val, v2_val):
                    # Exclude this combination
                    if v1_val and v2_val:
                        solver.add(z3_module.Not(z3_module.And(v1, v2)))
                    elif v1_val and not v2_val:
                        solver.add(z3_module.Not(z3_module.And(v1, z3_module.Not(v2))))
                    elif not v1_val and v2_val:
                        solver.add(z3_module.Not(z3_module.And(z3_module.Not(v1), v2)))
                    else:
                        solver.add(z3_module.Not(z3_module.And(z3_module.Not(v1), z3_module.Not(v2))))

    # ================================================================
    #  Encoding helpers - Bijective mapping (no hash collisions)
    # ================================================================

    def _reset_encoding(self):
        """
        Clear bijective encoding maps to prevent unbounded memory growth.

        FIX (Phase 3): The _encode_map and _decode_map grew without bound
        across solver invocations because only _z3_prove_invariant() reset
        them. Now every top-level solve/proof method calls this before starting.

        The deep encoding (_z3_solve_attempt) doesn't use bijective mapping
        at all, so these maps are legacy baggage that just accumulates.
        """
        self._encode_map = {}
        self._decode_map = {}
        self._next_encode_id = 0

    def _encode_value(self, value):
        """
        Bijective encoding of domain values to unique sequential integers.
        No collisions possible - each value gets a unique ID.

        FIX (Phase 3): Added max size limit with LRU-style eviction.
        When _encode_map exceeds _MAX_ENCODE_ENTRIES, the oldest entries
        are evicted to prevent unbounded memory growth on long-running
        solver instances.
        """
        # Evict oldest entries if limit reached
        if len(self._encode_map) >= _MAX_ENCODE_ENTRIES:
            keys_to_evict = list(self._encode_map.keys())[:_EVICT_BATCH_SIZE]
            for k in keys_to_evict:
                eid = self._encode_map.pop(k, None)
                if eid is not None:
                    self._decode_map.pop(eid, None)
            logger.debug(
                "Z3Solver: Encoding map evicted %d entries (limit: %d)",
                len(keys_to_evict), _MAX_ENCODE_ENTRIES
            )

        # Use a stable key that handles unhashable types
        try:
            key = (type(value).__name__, value)
            hash(key)
        except TypeError:
            key = (type(value).__name__, repr(value))

        if key not in self._encode_map:
            self._encode_map[key] = self._next_encode_id
            self._decode_map[self._next_encode_id] = value
            self._next_encode_id += 1

        return self._encode_map[key]

    def _decode_value(self, z3_value, domain):
        """
        Decode a Z3 integer value back to the original domain value
        using the bidirectional mapping.
        """
        try:
            int_val = z3_value.as_long()
            if int_val in self._decode_map:
                return self._decode_map[int_val]
            # Fallback: search domain with bijective encoding
            for v in domain:
                if self._encode_value(v) == int_val:
                    return v
        except Exception as decode_err:
            logger.debug(f"Z3Solver: Domain lookup failed: {decode_err}")
        return str(z3_value)
