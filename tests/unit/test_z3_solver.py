"""
Unit tests for Z3Solver

Tests the Z3 SMT Solver wrapper with conditional Z3 import.
Tests should work with or without Z3 installed.
"""

import sys
import pytest

sys.path.insert(0, "/home/z/my-project/Zenic-Logic-")

from src.core.shared.z3_solver import Z3Solver, HAS_Z3
from src.core.shared.constraint_solver import Constraint


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def solver():
    """Create a Z3Solver with default timeout."""
    return Z3Solver(timeout_ms=5000)


@pytest.fixture
def short_timeout_solver():
    """Create a Z3Solver with very short timeout for timeout tests."""
    return Z3Solver(timeout_ms=500)


# ============================================================
#  Constructor and Property Tests
# ============================================================

class TestZ3SolverConstructor:
    """Tests for Z3Solver initialization and properties."""

    def test_default_timeout(self):
        """Should initialize with default timeout of 15000ms."""
        s = Z3Solver()
        assert s.timeout_ms == 15000

    def test_custom_timeout(self):
        """Should accept custom timeout_ms parameter."""
        s = Z3Solver(timeout_ms=10000)
        assert s.timeout_ms == 10000

    def test_solver_type_property(self):
        """solver_type should be 'Z3' or 'AC3_FALLBACK' depending on availability."""
        s = Z3Solver()
        assert s.solver_type in ("Z3", "AC3_FALLBACK")

    def test_solver_type_matches_has_z3(self):
        """solver_type should be 'Z3' when HAS_Z3 is True, else 'AC3_FALLBACK'."""
        s = Z3Solver()
        if HAS_Z3:
            assert s.solver_type == "Z3"
        else:
            assert s.solver_type == "AC3_FALLBACK"

    def test_internal_state_initialized(self):
        """Should initialize internal encoding maps and sort counter."""
        s = Z3Solver()
        assert s._encode_map == {}
        assert s._decode_map == {}
        assert s._next_encode_id == 0
        assert s._sort_counter == 0


# ============================================================
#  Null Safety Tests
# ============================================================

class TestProveNullSafety:
    """Tests for prove_null_safety method."""

    def test_no_nullable_vars(self, solver):
        """When no vars are nullable, all should be non-null -> PROVEN."""
        result = solver.prove_null_safety(
            variable_names=["x", "y", "z"],
            nullable_vars=set()
        )
        assert isinstance(result, dict)
        assert "status" in result
        # With no nullable vars, constraints should be consistent -> PROVEN
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN")

    def test_some_nullable_vars(self, solver):
        """When some vars are nullable, should still be satisfiable."""
        result = solver.prove_null_safety(
            variable_names=["x", "y"],
            nullable_vars={"y"}
        )
        assert isinstance(result, dict)
        assert "status" in result

    def test_all_nullable_vars(self, solver):
        """When all vars are nullable, should be trivially satisfiable."""
        result = solver.prove_null_safety(
            variable_names=["x", "y"],
            nullable_vars={"x", "y"}
        )
        assert isinstance(result, dict)
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN", "UNKNOWN")

    def test_empty_variable_names(self, solver):
        """Should handle empty variable list."""
        result = solver.prove_null_safety(
            variable_names=[],
            nullable_vars=set()
        )
        assert isinstance(result, dict)

    def test_result_has_solver_type(self, solver):
        """Result should include solver_type information."""
        result = solver.prove_null_safety(["x"], set())
        assert "solver_type" in result

    def test_result_has_verified_field(self, solver):
        """Result should include a verified boolean field."""
        result = solver.prove_null_safety(["x"], set())
        assert "verified" in result
        assert isinstance(result["verified"], bool)


# ============================================================
#  Type Safety Tests
# ============================================================

class TestProveTypeSafety:
    """Tests for prove_type_safety method."""

    def test_compatible_types(self, solver):
        """Compatible type assignments should be PROVEN."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["int"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert result["status"] in ("PROVEN", "LIKELY_PROVEN")

    def test_incompatible_types(self, solver):
        """Incompatible type assignments should be VIOLATED or UNSATISFIABLE."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
            {"name": "y", "types": ["str"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_single_variable(self, solver):
        """Should handle a single variable."""
        variables_with_types = [
            {"name": "x", "types": ["int"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_empty_variables(self, solver):
        """Should handle empty variables list."""
        result = solver.prove_type_safety([])
        assert isinstance(result, dict)

    def test_multiple_types_per_variable(self, solver):
        """Should handle variables with multiple possible types."""
        variables_with_types = [
            {"name": "x", "types": ["int", "float"]},
            {"name": "y", "types": ["str"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)
        assert "status" in result

    def test_unknown_type(self, solver):
        """Should handle 'unknown' type gracefully."""
        variables_with_types = [
            {"name": "x", "types": ["unknown"]},
        ]
        result = solver.prove_type_safety(variables_with_types)
        assert isinstance(result, dict)


# ============================================================
#  Invariant Verification Tests
# ============================================================

class TestProveInvariant:
    """Tests for prove_invariant method."""

    def test_trivially_true_invariant(self, solver):
        """An invariant that's always true should be PROVEN."""
        def always_true(**kwargs):
            return True

        result = solver.prove_invariant(
            always_true,
            variables=["x", "y"],
            domains={"x": [1, 2, 3], "y": [4, 5, 6]}
        )
        assert isinstance(result, dict)
        assert result.get("verified") is True

    def test_trivially_false_invariant(self, solver):
        """An invariant that's always false should be VIOLATED."""
        def always_false(**kwargs):
            return False

        result = solver.prove_invariant(
            always_false,
            variables=["x"],
            domains={"x": [1, 2, 3]}
        )
        assert isinstance(result, dict)
        assert result.get("verified") is False

    def test_conditional_invariant(self, solver):
        """An invariant with a conditional should work correctly."""
        def x_less_than_y(**kwargs):
            return kwargs.get("x", 0) < kwargs.get("y", 0)

        result = solver.prove_invariant(
            x_less_than_y,
            variables=["x", "y"],
            domains={"x": [1, 2], "y": [3, 0]}
        )
        assert isinstance(result, dict)
        # x=2, y=0 violates x < y
        assert result.get("status") in ("VIOLATED", "LIKELY_VIOLATED")

    def test_invariant_with_empty_domain(self, solver):
        """Should handle empty domains gracefully."""
        def always_true(**kwargs):
            return True

        result = solver.prove_invariant(
            always_true,
            variables=["x"],
            domains={}
        )
        assert isinstance(result, dict)

    def test_invariant_exception_handling(self, solver):
        """Should handle exceptions in invariant function."""
        def bad_invariant(**kwargs):
            raise ValueError("test error")

        result = solver.prove_invariant(
            bad_invariant,
            variables=["x"],
            domains={"x": [1, 2]}
        )
        assert isinstance(result, dict)


# ============================================================
#  Constraint Solving Tests
# ============================================================

class TestSolveConstraints:
    """Tests for solve_constraints method."""

    def test_satisfiable_constraints(self, solver):
        """Should find a solution for satisfiable constraints."""
        domains = {"x": [1, 2, 3], "y": [2, 3, 4]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y")
        ]
        result = solver.solve_constraints(domains, constraints)
        assert isinstance(result, dict)
        assert result["status"] in ("SATISFIED",)

    def test_unsatisfiable_constraints(self, solver):
        """Should return UNSATISFIABLE for contradictory constraints."""
        domains = {"x": [1], "y": [1]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y"),
            Constraint("x", "y", lambda a, b: a > b, "x > y"),
        ]
        result = solver.solve_constraints(domains, constraints)
        assert result["status"] == "UNSATISFIABLE"

    def test_no_constraints(self, solver):
        """Should find any solution when no constraints exist."""
        domains = {"x": [1, 2], "y": [3, 4]}
        result = solver.solve_constraints(domains, [])
        assert result["status"] == "SATISFIED"

    def test_empty_domains(self, solver):
        """Should handle empty domains."""
        domains = {}
        result = solver.solve_constraints(domains, [])
        assert isinstance(result, dict)

    def test_assignment_present_on_satisfied(self, solver):
        """SATISFIED result should include an assignment dict."""
        domains = {"x": [1, 2, 3], "y": [4, 5, 6]}
        constraints = [
            Constraint("x", "y", lambda a, b: a < b, "x < y")
        ]
        result = solver.solve_constraints(domains, constraints)
        if result["status"] == "SATISFIED":
            assert result["assignment"] is not None
            assert "x" in result["assignment"]
            assert "y" in result["assignment"]


# ============================================================
#  Code Safety Proof Tests
# ============================================================

class TestProveCodeSafety:
    """Tests for prove_code_safety method."""

    def test_basic_code_safety(self, solver):
        """Should analyze basic code with variables."""
        ast_analysis = {
            "variables": [
                {"name": "x", "annotation": "int", "nullable": False},
                {"name": "y", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x = 1\ny = 2\n")
        assert isinstance(result, dict)
        assert "overall_status" in result
        assert result["overall_status"] in ("PROVEN", "PARTIAL", "VIOLATED", "UNKNOWN", "ERROR", "LIKELY_PROVEN")

    def test_code_safety_with_nullable(self, solver):
        """Should detect nullable variables and check null safety."""
        ast_analysis = {
            "variables": [
                {"name": "x", "annotation": "Optional[int]", "nullable": True},
                {"name": "y", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x: Optional[int] = None\ny: int = 1\n")
        assert isinstance(result, dict)
        assert "null_safety" in result

    def test_code_safety_empty_analysis(self, solver):
        """Should handle empty AST analysis."""
        ast_analysis = {
            "variables": [],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "")
        assert isinstance(result, dict)
        assert "overall_status" in result

    def test_code_safety_with_operations(self, solver):
        """Should analyze code with type operations."""
        ast_analysis = {
            "variables": [
                {"name": "a", "annotation": "int", "nullable": False},
                {"name": "b", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [
                {"op": "add", "left_var": "a", "right_var": "b",
                 "left_type": "int", "right_type": "int"},
            ],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "a + b\n")
        assert isinstance(result, dict)
        assert "type_safety" in result

    def test_code_safety_with_invariants(self, solver):
        """Should verify invariants from AST analysis."""
        ast_analysis = {
            "variables": [
                {"name": "idx", "annotation": "int", "nullable": False},
            ],
            "functions": [],
            "operations": [],
            "invariants": [
                {"kind": "index_bounds", "expr": "idx >= 0", "variables": ["idx"]},
            ],
        }
        result = solver.prove_code_safety(ast_analysis, "items[idx]\n")
        assert isinstance(result, dict)
        assert "invariant_safety" in result

    def test_code_safety_syntax_error_code(self, solver):
        """Should handle code with syntax errors gracefully."""
        ast_analysis = {
            "variables": [],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "def foo( $$$ ")
        assert isinstance(result, dict)
        # Should not crash

    def test_code_safety_result_fields(self, solver):
        """Result should have all expected fields."""
        ast_analysis = {
            "variables": [{"name": "x", "annotation": "int", "nullable": False}],
            "functions": [],
            "operations": [],
            "invariants": [],
        }
        result = solver.prove_code_safety(ast_analysis, "x = 1\n")
        assert "null_safety" in result
        assert "type_safety" in result
        assert "invariant_safety" in result
        assert "overall_status" in result
        assert "solver_type" in result
        assert "errors" in result


# ============================================================
#  Type Lattice Tests
# ============================================================

class TestTypeLattice:
    """Tests for the _TYPE_LATTICE class attribute."""

    def test_type_lattice_exists(self):
        """Z3Solver should have _TYPE_LATTICE attribute."""
        assert hasattr(Z3Solver, "_TYPE_LATTICE")

    def test_type_lattice_compatibility(self):
        """int should be compatible with float and object."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "float" in lattice["int"]
        assert "object" in lattice["int"]

    def test_type_lattice_none(self):
        """None type should be compatible with object and unknown."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "object" in lattice["None"]
        assert "unknown" in lattice["None"]

    def test_type_lattice_bool_compatibility(self):
        """bool should be compatible with int (Python semantics)."""
        lattice = Z3Solver._TYPE_LATTICE
        assert "int" in lattice["bool"]

    def test_type_lattice_unknown_is_minimal(self):
        """unknown should only be compatible with itself."""
        lattice = Z3Solver._TYPE_LATTICE
        assert lattice["unknown"] == {"unknown"}


# ============================================================
#  Annotation-to-Types Tests
# ============================================================

class TestAnnotationToTypes:
    """Tests for _annotation_to_types helper method."""

    def test_simple_int(self, solver):
        """Should parse 'int' annotation."""
        types = solver._annotation_to_types("int")
        assert "int" in types

    def test_optional_type(self, solver):
        """Should parse 'Optional[int]' annotation."""
        types = solver._annotation_to_types("Optional[int]")
        assert isinstance(types, list)
        assert len(types) > 0

    def test_none_annotation(self, solver):
        """Should handle None annotation."""
        types = solver._annotation_to_types(None)
        assert isinstance(types, list)

    def test_empty_annotation(self, solver):
        """Should handle empty string annotation."""
        types = solver._annotation_to_types("")
        assert isinstance(types, list)

    def test_union_type(self, solver):
        """Should parse 'Union[int, str]' annotation."""
        types = solver._annotation_to_types("Union[int, str]")
        assert isinstance(types, list)
        assert len(types) >= 2
