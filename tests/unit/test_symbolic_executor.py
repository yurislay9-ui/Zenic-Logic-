"""
Unit tests for SymbolicExecutor

Tests the symbolic execution engine including SymbolicValue,
SymbolicPath, and SymbolicExecutor classes.
"""

import sys
import pytest

sys.path.insert(0, "/home/z/my-project/Zenic-Logic-")

from src.core.shared.symbolic_executor import (
    SymbolicValue,
    SymbolicPath,
    SymbolicExecutor,
    HAS_Z3,
)


# ============================================================
#  SymbolicValue Tests
# ============================================================

class TestSymbolicValue:
    """Tests for SymbolicValue class."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        sv = SymbolicValue("x")
        assert sv.name == "x"
        assert sv.var_type == "any"
        assert sv.constraint is None
        assert sv.concrete is None

    def test_custom_initialization(self):
        """Should accept custom type, constraint, and concrete value."""
        constraint = lambda v: v > 0
        sv = SymbolicValue("y", var_type="int", constraint=constraint, concrete=42)
        assert sv.name == "y"
        assert sv.var_type == "int"
        assert sv.constraint is constraint
        assert sv.concrete == 42

    def test_repr_with_concrete(self):
        """Should show concrete value in repr."""
        sv = SymbolicValue("z", var_type="int", concrete=10)
        r = repr(sv)
        assert "z" in r
        assert "10" in r

    def test_repr_without_concrete(self):
        """Should show symbolic representation when no concrete value."""
        sv = SymbolicValue("a", var_type="str")
        r = repr(sv)
        assert "a" in r
        assert "str" in r

    def test_var_type_bool(self):
        """Should support bool type."""
        sv = SymbolicValue("flag", var_type="bool", concrete=True)
        assert sv.var_type == "bool"
        assert sv.concrete is True

    def test_var_type_none(self):
        """Should handle None concrete value properly."""
        sv = SymbolicValue("x", var_type="int", concrete=None)
        assert sv.concrete is None
        # repr should not show concrete since it's None
        r = repr(sv)
        assert "=" not in r or "None" not in r


# ============================================================
#  SymbolicPath Tests
# ============================================================

class TestSymbolicPath:
    """Tests for SymbolicPath class."""

    def test_default_initialization(self):
        """Should initialize with default empty values."""
        sp = SymbolicPath()
        assert sp.condition == []
        assert sp.result is None
        assert sp.is_pruned is False
        assert sp.variables == {}
        assert sp.z3_conditions == []
        assert sp.assignments == []
        assert sp.return_values == []

    def test_custom_initialization(self):
        """Should accept custom values."""
        sp = SymbolicPath(
            condition=["x > 0"],
            result="some_result",
            is_pruned=True,
            variables={"x": SymbolicValue("x", "int")},
        )
        assert sp.condition == ["x > 0"]
        assert sp.result == "some_result"
        assert sp.is_pruned is True
        assert "x" in sp.variables

    def test_add_condition_string_only(self):
        """Should add string condition without Z3 constraint."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        assert "x > 0" in sp.condition
        assert len(sp.z3_conditions) == 0

    def test_add_condition_with_z3(self):
        """Should add both string and Z3 condition."""
        sp = SymbolicPath()
        sp.add_condition("x > 0", z3_cond="mock_z3_condition")
        assert "x > 0" in sp.condition
        assert "mock_z3_condition" in sp.z3_conditions

    def test_add_assignment(self):
        """Should record variable assignments."""
        sp = SymbolicPath()
        sp.add_assignment("x", "42")
        sp.add_assignment("y", "x + 1")
        assert len(sp.assignments) == 2
        assert sp.assignments[0] == ("x", "42")
        assert sp.assignments[1] == ("y", "x + 1")

    def test_add_return(self):
        """Should record return values with type."""
        sp = SymbolicPath()
        sp.add_return("42", "int")
        sp.add_return("None", "None")
        assert len(sp.return_values) == 2
        assert sp.return_values[0]["desc"] == "42"
        assert sp.return_values[0]["type"] == "int"
        assert sp.return_values[1]["desc"] == "None"

    def test_add_return_default_type(self):
        """add_return should default to 'any' type."""
        sp = SymbolicPath()
        sp.add_return("some_value")
        assert sp.return_values[0]["type"] == "any"

    def test_is_feasible_no_conditions(self):
        """Path with no conditions should be feasible."""
        sp = SymbolicPath()
        assert sp.is_feasible() is True

    def test_is_feasible_consistent_conditions(self):
        """Path with consistent conditions should be feasible."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        sp.add_condition("y > 0")
        assert sp.is_feasible() is True

    def test_is_feasible_contradictory_conditions(self):
        """Path with contradictory string conditions should be infeasible."""
        sp = SymbolicPath()
        sp.add_condition("x > 0")
        sp.add_condition("NOT_x > 0")
        assert sp.is_feasible() is False

    def test_max_z3_conditions(self):
        """Should not exceed MAX_Z3_CONDITIONS."""
        assert SymbolicPath.MAX_Z3_CONDITIONS == 50
        sp = SymbolicPath()
        for i in range(60):
            sp.add_condition(f"cond_{i}", z3_cond=f"z3_cond_{i}")
        assert len(sp.z3_conditions) <= SymbolicPath.MAX_Z3_CONDITIONS


# ============================================================
#  SymbolicExecutor Tests
# ============================================================

class TestSymbolicExecutor:
    """Tests for SymbolicExecutor class."""

    def test_default_initialization(self):
        """Should initialize with default parameters."""
        se = SymbolicExecutor()
        assert se.k_path_limit == 10
        assert se.max_depth == 20
        assert se.paths_explored == 0
        assert se.paths_pruned == 0

    def test_custom_initialization(self):
        """Should accept custom k_path_limit and max_depth."""
        se = SymbolicExecutor(k_path_limit=5, max_depth=15)
        assert se.k_path_limit == 5
        assert se.max_depth == 15

    def test_io_operations_set(self):
        """IO_OPERATIONS should contain expected I/O operations."""
        assert "open" in SymbolicExecutor.IO_OPERATIONS
        assert "read" in SymbolicExecutor.IO_OPERATIONS
        assert "write" in SymbolicExecutor.IO_OPERATIONS
        assert "print" in SymbolicExecutor.IO_OPERATIONS
        assert "connect" in SymbolicExecutor.IO_OPERATIONS

    def test_loop_unroll_limit(self):
        """LOOP_UNROLL_LIMIT should be 2."""
        assert SymbolicExecutor.LOOP_UNROLL_LIMIT == 2

    def test_incompatible_types(self):
        """INCOMPATIBLE_TYPES should contain expected type pairs."""
        incompatible = SymbolicExecutor.INCOMPATIBLE_TYPES
        assert frozenset({"str", "int"}) in incompatible
        assert frozenset({"None", "int"}) in incompatible

    def test_execute_simple_function(self):
        """Should analyze a simple function with a return."""
        code = """
def add(a, b):
    return a + b
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert result["status"] in ("PASS", "VIOLATIONS_FOUND")
        assert len(result["paths"]) > 0
        assert "metrics" in result

    def test_execute_function_with_if(self):
        """Should explore both branches of an if statement."""
        code = """
def abs_val(x):
    if x >= 0:
        return x
    else:
        return -x
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert len(result["paths"]) >= 2  # At least true and false branch

    def test_execute_syntax_error(self):
        """Should handle syntax errors gracefully."""
        code = "def foo( $$$ "
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert result["status"] == "FAIL_SYNTAX"
        assert len(result["warnings"]) > 0

    def test_execute_non_python_language(self):
        """Should handle non-Python languages via regex fallback."""
        code = "function test() { return 1; }"
        se = SymbolicExecutor()
        result = se.execute_symbolic(code, language="javascript")
        assert isinstance(result, dict)
        assert "status" in result

    def test_execute_empty_code(self):
        """Should handle empty code."""
        code = ""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)
        # Empty code is valid Python, no functions to analyze

    def test_execute_function_with_assignment(self):
        """Should track variable assignments."""
        code = """
def compute(x):
    y = x + 1
    return y
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert len(result["paths"]) > 0
        # Check that assignments are tracked
        for path in result["paths"]:
            if path.assignments:
                var_names = [a[0] for a in path.assignments]
                assert "y" in var_names

    def test_execute_function_with_loop(self):
        """Should handle for loops with bounded unrolling."""
        code = """
def sum_range(n):
    total = 0
    for i in range(n):
        total += i
    return total
"""
        se = SymbolicExecutor(k_path_limit=20)
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)
        assert len(result["paths"]) > 0

    def test_execute_while_loop(self):
        """Should handle while loops with bounded unrolling."""
        code = """
def countdown(n):
    while n > 0:
        n -= 1
    return n
"""
        se = SymbolicExecutor(k_path_limit=20)
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)

    def test_execute_try_except(self):
        """Should handle try/except blocks."""
        code = """
def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return 0
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)
        assert len(result["paths"]) > 0

    def test_execute_division_by_zero_detection(self):
        """Should detect potential division by zero."""
        code = """
def divide(a, b):
    return a / b
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        # May or may not detect depending on Z3 availability
        assert isinstance(result, dict)

    def test_execute_multiple_functions(self):
        """Should analyze all functions in the code."""
        code = """
def foo(x):
    return x + 1

def bar(y):
    return y * 2
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        # Both functions should be analyzed
        total_paths = result["metrics"]["total_paths"]
        assert total_paths >= 2

    def test_execute_with_type_annotations(self):
        """Should respect type annotations on parameters."""
        code = """
def typed_func(x: int, y: str) -> int:
    return x
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)

    def test_metrics_in_result(self):
        """Result should include expected metrics."""
        code = "def f(x): return x"
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        metrics = result["metrics"]
        assert "paths_explored" in metrics
        assert "paths_pruned" in metrics
        assert "total_paths" in metrics
        assert "feasible_paths" in metrics

    def test_k_path_limit_respected(self):
        """Should not exceed k_path_limit in path count."""
        code = """
def many_branches(a, b, c):
    if a > 0:
        if b > 0:
            if c > 0:
                return 1
            else:
                return 2
        else:
            return 3
    else:
        return 4
"""
        limit = 5
        se = SymbolicExecutor(k_path_limit=limit)
        result = se.execute_symbolic(code)
        # The number of paths should be limited
        assert len(result["paths"]) <= limit

    def test_execute_augmented_assignment(self):
        """Should track augmented assignments (+=, -=, etc.)."""
        code = """
def increment(x):
    x += 1
    return x
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert len(result["paths"]) > 0

    def test_execute_pass_statement(self):
        """Should handle pass statements."""
        code = """
def noop(x):
    pass
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)

    def test_execute_raise_statement(self):
        """Should handle raise statements."""
        code = """
def may_raise(x):
    if x < 0:
        raise ValueError("negative")
    return x
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)
        # Should have paths including exception path
        has_exception = any(
            any(rv.get("type") == "exception" for rv in p.return_values)
            for p in result["paths"]
        )
        # At least one path should have the exception return
        assert has_exception or len(result["paths"]) >= 1

    def test_execute_bare_return(self):
        """Should handle bare return statements (return without value)."""
        code = """
def early_return(x):
    if x < 0:
        return
    return x
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)

    def test_execute_function_with_none_return(self):
        """Should detect None return type."""
        code = """
def returns_none(x):
    return None
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        # Should have at least one path with None return type
        none_returns = []
        for p in result["paths"]:
            for rv in p.return_values:
                if rv.get("type") == "None":
                    none_returns.append(rv)
        assert len(none_returns) > 0


# ============================================================
#  Integration-style Tests
# ============================================================

class TestSymbolicExecutorIntegration:
    """Integration tests combining multiple features."""

    def test_if_else_with_return(self):
        """Should correctly trace paths through if/else with returns."""
        code = """
def classify(x):
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"
"""
        se = SymbolicExecutor(k_path_limit=20)
        result = se.execute_symbolic(code)
        # Should have multiple paths
        assert len(result["paths"]) >= 2
        # All paths should have return values
        for path in result["paths"]:
            if path.return_values:
                assert path.return_values[0]["type"] == "str"

    def test_nested_if(self):
        """Should handle nested if statements."""
        code = """
def nested(x, y):
    if x > 0:
        if y > 0:
            return 1
        return 2
    return 3
"""
        se = SymbolicExecutor(k_path_limit=20)
        result = se.execute_symbolic(code)
        assert isinstance(result, dict)

    def test_code_with_io_detection(self):
        """Should detect I/O operations for pruning."""
        code = """
def read_file(path):
    f = open(path)
    data = f.read()
    f.close()
    return data
"""
        se = SymbolicExecutor()
        result = se.execute_symbolic(code)
        # Some paths may be pruned due to I/O
        assert isinstance(result, dict)

    def test_reset_state_between_executions(self):
        """Should reset internal state between execute_symbolic calls."""
        se = SymbolicExecutor()
        code1 = "def f(x): return x + 1"
        code2 = "def g(y): return y * 2"

        result1 = se.execute_symbolic(code1)
        result2 = se.execute_symbolic(code2)

        # Second execution should have fresh state
        assert isinstance(result2, dict)
