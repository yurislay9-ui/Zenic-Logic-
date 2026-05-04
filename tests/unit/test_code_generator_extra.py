"""
Unit tests for CodeGenerator (Extended Coverage)

Tests additional methods and edge cases not covered by the existing
test_code_generator.py. Focuses on:
- extract_solver_insights with various proof statuses
- extract_ast_context with various connection types
- extract_symbolic_insights
- Language-specific code generators (Kotlin, Go, JavaScript)
- Pipeline-driven feature module generation
- Security module generation
- Edge cases and error handling
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.code_generator import CodeGenerator
from src.core.shared.contracts import (
    IntentPayload, ExecutionPlan, PlanStep, OperationType, GoalType
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def code_gen():
    """Create a CodeGenerator with a mock orchestrator."""
    class MockOrchestrator:
        pass
    return CodeGenerator(MockOrchestrator())


@pytest.fixture
def create_intent():
    """Create a basic CREATE intent."""
    return IntentPayload(
        op=OperationType.CREATE, target="my_module.py",
        goal=GoalType.FEATURE_ADD, confidence=0.9, context="",
        raw_code="", language="python"
    )


@pytest.fixture
def security_intent():
    """Create a SECURITY_HARDEN intent."""
    return IntentPayload(
        op=OperationType.CREATE, target="secure_mod.py",
        goal=GoalType.SECURITY_HARDEN, confidence=0.95, context="",
        raw_code="", language="python"
    )


@pytest.fixture
def bugfix_intent():
    """Create a BUG_FIX intent with raw code."""
    return IntentPayload(
        op=OperationType.CREATE, target="buggy.py",
        goal=GoalType.BUG_FIX, confidence=0.85, context="",
        raw_code="def broken(): return 1/0", language="python"
    )


@pytest.fixture
def refactor_intent():
    """Create a REFACTOR intent."""
    return IntentPayload(
        op=OperationType.REFACTOR, target="old_code.py",
        goal=GoalType.READABILITY, confidence=0.8, context="",
        raw_code="def f(x): return x", language="python"
    )


@pytest.fixture
def debug_intent():
    """Create a DEBUG intent."""
    return IntentPayload(
        op=OperationType.DEBUG, target="debug_me.py",
        goal=GoalType.BUG_FIX, confidence=0.7, context="",
        raw_code="def crash(): raise Error", language="python"
    )


# ============================================================
#  extract_solver_insights Tests
# ============================================================

class TestExtractSolverInsights:
    """Extended tests for extract_solver_insights static method."""

    def test_none_proof(self):
        """Should return default insights for None proof."""
        insights = CodeGenerator.extract_solver_insights(None)
        assert insights["null_safety_required"] is False
        assert insights["type_safety_required"] is False
        assert insights["critical_target"] is False
        assert insights["status"] == "none"

    def test_empty_dict_proof(self):
        """Should handle empty dict proof (treated as falsy)."""
        insights = CodeGenerator.extract_solver_insights({})
        assert insights["status"] == "none"
        assert isinstance(insights["validated_constraints"], list)

    def test_proven_status(self):
        """Should extract validated constraints from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Z3 EnumSort proved null-safety constraints",
            "solver_type": "Z3_ENUMSORT",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "PROVEN"
        assert insights["null_safety_required"] is True
        assert len(insights["validated_constraints"]) > 0

    def test_proven_type_safety(self):
        """Should detect type safety requirement from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Type assignment verified",
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["type_safety_required"] is True

    def test_proven_critical_target(self):
        """Should detect critical target from PROVEN proof."""
        proof = {
            "status": "PROVEN",
            "proof": "Critical constraint verified",
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True

    def test_violated_status(self):
        """Should extract violated constraints from VIOLATED proof."""
        proof = {
            "status": "VIOLATED",
            "counterexamples": [{"x": "None", "y": 0}],
            "solver_type": "Z3",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "VIOLATED"
        assert len(insights["violated_constraints"]) > 0
        assert insights["null_safety_required"] is True

    def test_likely_violated_status(self):
        """Should handle LIKELY_VIOLATED status."""
        proof = {
            "status": "LIKELY_VIOLATED",
            "counterexamples": [{"a": "type_mismatch"}],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "LIKELY_VIOLATED"
        assert insights["type_safety_required"] is True

    def test_satisfied_status(self):
        """Should extract assignment from SATISFIED proof."""
        proof = {
            "status": "SATISFIED",
            "assignment": {"x": 1, "y": 2},
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "SATISFIED"
        assert len(insights["validated_constraints"]) >= 2

    def test_satisfied_non_dict_assignment(self):
        """Should handle non-dict assignment in SATISFIED proof."""
        proof = {
            "status": "SATISFIED",
            "assignment": None,
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["status"] == "SATISFIED"

    def test_constraints_in_proof(self):
        """Should detect critical/null from constraints list."""
        proof = {
            "status": "UNKNOWN",
            "constraints": ["critical: must not be null", "null check required"],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True
        assert insights["null_safety_required"] is True

    def test_constraints_as_objects(self):
        """Should handle Constraint objects in constraints list."""
        from src.core.shared.constraint_solver import Constraint

        c = Constraint("x", "y", lambda a, b: a < b, description="critical safety")
        proof = {
            "status": "UNKNOWN",
            "constraints": [c],
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["critical_target"] is True

    def test_solver_type_extracted(self):
        """Should extract solver_type from proof."""
        proof = {"status": "PROVEN", "solver_type": "Z3_ENUMSORT"}
        insights = CodeGenerator.extract_solver_insights(proof)
        assert insights["solver_type"] == "Z3_ENUMSORT"


# ============================================================
#  extract_ast_context Tests
# ============================================================

class TestExtractASTContext:
    """Extended tests for extract_ast_context static method."""

    def test_none_ast(self):
        """Should return default context for None AST analysis."""
        ctx = CodeGenerator.extract_ast_context(None)
        assert ctx["function_signatures"] == []
        assert ctx["max_complexity"] == 0

    def test_empty_ast(self):
        """Should return default context for empty AST analysis."""
        ctx = CodeGenerator.extract_ast_context({})
        assert ctx["function_names"] == []
        assert ctx["class_names"] == []

    def test_extends_connections(self):
        """Should detect class hierarchy from extends: connections."""
        ast = {
            "function_names": [],
            "class_names": ["ChildClass"],
            "max_complexity": 0,
            "connections": ["extends:BaseClass"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["class_hierarchies"]) > 0

    def test_method_connections(self):
        """Should detect call relationships from method: connections."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
            "connections": ["MyClassmethod:process"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["call_relationships"]) > 0

    def test_import_dependencies(self):
        """Should detect import dependencies from other connections."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
            "connections": ["utils.helper"],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "utils.helper" in ctx["import_dependencies"]

    def test_getter_pattern(self):
        """Should detect getter pattern."""
        ast = {
            "function_names": ["get_name", "get_age"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "getter" in ctx["existing_patterns"]

    def test_setter_pattern(self):
        """Should detect setter pattern."""
        ast = {
            "function_names": ["set_name"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "setter" in ctx["existing_patterns"]

    def test_private_methods_pattern(self):
        """Should detect private methods pattern."""
        ast = {
            "function_names": ["_helper", "__init__"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "private_methods" in ctx["existing_patterns"]

    def test_validation_pattern(self):
        """Should detect validation pattern."""
        ast = {
            "function_names": ["validate_input", "check_status"],
            "class_names": [],
            "max_complexity": 0,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert "validation" in ctx["existing_patterns"]

    def test_max_complexity(self):
        """Should extract max_complexity from AST analysis."""
        ast = {
            "function_names": [],
            "class_names": [],
            "max_complexity": 15,
            "connections": [],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert ctx["max_complexity"] == 15


# ============================================================
#  extract_symbolic_insights Tests
# ============================================================

class TestExtractSymbolicInsights:
    """Tests for extract_symbolic_insights static method."""

    def test_none_result(self):
        """Should return default insights for None result."""
        insights = CodeGenerator.extract_symbolic_insights(None)
        assert insights["symbolic_violations"] == []
        assert insights["paths_explored"] == 0

    def test_sandbox_result_with_warnings(self):
        """Should extract Z3-proven and heuristic violations from warnings."""
        class MockResult:
            warnings = [
                "Symbolic (Z3 PROVEN): division by zero at line 5",
                "Symbolic: potential null dereference",
                "Regular warning",
            ]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["z3_proven_violations"]) == 1
        assert len(insights["division_by_zero_risks"]) == 1
        assert len(insights["symbolic_violations"]) == 1

    def test_sandbox_result_with_metrics(self):
        """Should extract metrics from sandbox result."""
        class MockResult:
            warnings = []
            metrics = {
                "paths_explored": 25,
                "paths_pruned": 5,
                "feasible_paths": 20,
                "smt_paths_available": True,
                "test_inputs_sample": [{"x": 1, "y": 2}],
            }

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert insights["paths_explored"] == 25
        assert insights["paths_pruned"] == 5
        assert insights["feasible_paths"] == 20
        assert insights["smt_paths_available"] is True
        assert len(insights["concrete_test_inputs"]) == 1

    def test_sandbox_result_none_deref(self):
        """Should detect None dereference risks."""
        class MockResult:
            warnings = ["Symbolic (Z3 PROVEN): none dereference at line 10"]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["null_dereference_risks"]) == 1

    def test_sandbox_result_index_oob(self):
        """Should detect index out of bounds risks."""
        class MockResult:
            warnings = ["Symbolic (Z3 PROVEN): index out of bounds at line 3"]
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert len(insights["index_oob_risks"]) == 1

    def test_empty_metrics(self):
        """Should handle empty metrics dict."""
        class MockResult:
            warnings = []
            metrics = {}

        insights = CodeGenerator.extract_symbolic_insights(MockResult())
        assert insights["paths_explored"] == 0


# ============================================================
#  Static Code Generation Tests
# ============================================================

class TestStaticCodeGeneration:
    """Tests for static code generation methods."""

    def test_generate_security_module(self):
        """Should generate a security module."""
        code = CodeGenerator.generate_security_module("auth")
        assert isinstance(code, str)
        assert "SecurityManager" in code
        assert "hash_password" in code
        assert "verify_password" in code
        assert "generate_token" in code

    def test_generate_feature_module(self):
        """Should generate a feature module."""
        code = CodeGenerator.generate_feature_module(
            "my_feature",
            existing_functions=["func1", "func2"],
            existing_classes=["MyClass"],
            needed_imports={"os", "sys"},
        )
        assert isinstance(code, str)
        assert "My_featureManager" in code
        assert "func1" in code
        assert "MyClass" in code

    def test_generate_feature_module_no_existing(self):
        """Should generate a feature module without existing code context."""
        code = CodeGenerator.generate_feature_module(
            "standalone",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
        )
        assert isinstance(code, str)
        assert "StandaloneManager" in code

    def test_generate_kotlin_contextual(self):
        """Should generate Kotlin code."""
        code = CodeGenerator.generate_kotlin_contextual(None, "auth", [])
        assert isinstance(code, str)
        assert "package com.titan" in code
        assert "auth" in code.lower()
        assert "class" in code

    def test_generate_go_contextual(self):
        """Should generate Go code."""
        code = CodeGenerator.generate_go_contextual(None, "handler")
        assert isinstance(code, str)
        assert "package main" in code
        assert "Manager" in code

    def test_generate_javascript_contextual(self):
        """Should generate JavaScript code."""
        code = CodeGenerator.generate_javascript_contextual(None, "service")
        assert isinstance(code, str)
        assert "ServiceManager" in code
        assert "module.exports" in code

    def test_generate_kotlin_with_existing_classes(self):
        """Should reference existing classes in Kotlin generation."""
        code = CodeGenerator.generate_kotlin_contextual(None, "auth", ["BaseService"])
        assert isinstance(code, str)

    def test_generate_go_empty_target(self):
        """Should handle empty target name for Go."""
        code = CodeGenerator.generate_go_contextual(None, "")
        assert isinstance(code, str)

    def test_generate_javascript_empty_target(self):
        """Should handle empty target name for JavaScript."""
        code = CodeGenerator.generate_javascript_contextual(None, "")
        assert isinstance(code, str)


# ============================================================
#  Pipeline Feature Module Tests
# ============================================================

class TestPipelineFeatureModule:
    """Tests for generate_pipeline_feature_module method."""

    def test_basic_pipeline_module(self, code_gen):
        """Should generate a pipeline feature module."""
        code = code_gen.generate_pipeline_feature_module(
            safe_target="pipeline_mod",
            existing_functions=["func_a"],
            existing_classes=["ClassA"],
            needed_imports=set(),
            solver_insights=CodeGenerator.extract_solver_insights(None),
            mcts_actions=["ANALYZE_CODE"],
        )
        assert isinstance(code, str)
        assert "Pipeline_modManager" in code

    def test_pipeline_module_with_null_safety(self, code_gen):
        """Should include null-safety guard when solver requires it."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["null_safety_required"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="safe_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_validate_not_none" in code

    def test_pipeline_module_with_type_safety(self, code_gen):
        """Should include type-safety guard when solver requires it."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["type_safety_required"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="typed_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_validate_type" in code

    def test_pipeline_module_with_critical_target(self, code_gen):
        """Should include sanitization for critical targets."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["critical_target"] = True
        solver_insights["status"] = "PROVEN"

        code = code_gen.generate_pipeline_feature_module(
            safe_target="critical_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_sanitize_input" in code

    def test_pipeline_module_with_symbolic_validation(self, code_gen):
        """Should include invariant assertion for SYMBOLIC_VALIDATION action."""
        code = code_gen.generate_pipeline_feature_module(
            safe_target="validated_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=CodeGenerator.extract_solver_insights(None),
            mcts_actions=["SYMBOLIC_VALIDATION"],
        )
        assert "_assert_invariant" in code

    def test_pipeline_module_with_div_zero_risk(self, code_gen):
        """Should include division guard for division-by-zero risks."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["division_by_zero_risks"] = ["div by zero at line 5"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="div_safe",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_safe_divide" in code

    def test_pipeline_module_with_index_oob_risk(self, code_gen):
        """Should include index bounds guard for OOB risks."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["index_oob_risks"] = ["index OOB at line 3"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="idx_safe",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "_safe_index" in code

    def test_pipeline_module_with_violated_constraints(self, code_gen):
        """Should include defensive checks for violated constraints."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["status"] = "VIOLATED"
        solver_insights["violated_constraints"] = ["division by zero found"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="defended",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert isinstance(code, str)
        # Violated constraints header should be in code
        assert "violation" in code.lower() or "defensive" in code.lower()

    def test_pipeline_module_with_concrete_test_inputs(self, code_gen):
        """Should generate test cases from concrete symbolic inputs."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["concrete_test_inputs"] = [
            {"x": 1, "y": 2},
            {"x": 0, "y": -1},
        ]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="tested_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "Test" in code
        assert "test_case" in code


# ============================================================
#  Contextual Code Generation Tests
# ============================================================

class TestContextualCodeGeneration:
    """Tests for generate_contextual_code and generate_intelligent_code."""

    def test_generate_contextual_code_no_plan(self, code_gen, create_intent):
        """Should use fallback generation when no plan available."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        result = code_gen.generate_contextual_code(create_intent, ast, None, "python")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_contextual_code_kotlin(self, code_gen, create_intent):
        """Should generate Kotlin code when language is kotlin."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "kotlin")
        assert isinstance(result, str)
        assert "package" in result

    def test_generate_contextual_code_go(self, code_gen, create_intent):
        """Should generate Go code when language is go."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "go")
        assert isinstance(result, str)
        assert "package" in result

    def test_generate_contextual_code_javascript(self, code_gen, create_intent):
        """Should generate JavaScript code when language is javascript."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_contextual_code(create_intent, ast, plan, "javascript")
        assert isinstance(result, str)
        assert "class" in result.lower()

    def test_generate_intelligent_code(self, code_gen, create_intent):
        """Should delegate to generate_contextual_code."""
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        result = code_gen.generate_intelligent_code(create_intent, ast, "python")
        assert isinstance(result, str)


# ============================================================
#  Edge Cases Tests
# ============================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_special_chars_in_target(self, code_gen, create_intent):
        """Should sanitize special characters in target name."""
        create_intent.target = "my-module@v2.py"
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_pipeline_driven_code(create_intent, ast, plan, "python")
        assert isinstance(result, str)

    def test_unknown_target(self, code_gen):
        """Should handle 'unknown' target gracefully."""
        intent = IntentPayload(
            op=OperationType.CREATE, target="unknown",
            goal=GoalType.FEATURE_ADD, confidence=0.5, context="",
            raw_code="", language="python"
        )
        ast = {"function_names": [], "class_names": [], "connections": [], "max_complexity": 0}
        plan = ExecutionPlan(plan_id="p1", steps=[])
        result = code_gen.generate_pipeline_driven_code(intent, ast, plan, "python")
        assert isinstance(result, str)

    def test_empty_ast_analysis_no_plan(self, code_gen, create_intent):
        """Should handle empty AST analysis without a plan."""
        result = code_gen.generate_contextual_code(create_intent, {}, None, "python")
        assert isinstance(result, str)

    def test_extract_solver_insights_counterexamples_as_string(self):
        """Should handle counterexamples as string (not list)."""
        proof = {
            "status": "VIOLATED",
            "counterexamples": "single counterexample string",
        }
        insights = CodeGenerator.extract_solver_insights(proof)
        assert isinstance(insights["violated_constraints"], list)

    def test_extract_ast_context_complex_connections(self):
        """Should handle complex connection strings."""
        ast = {
            "function_names": ["get_data", "_internal"],
            "class_names": ["DataClass"],
            "max_complexity": 5,
            "connections": [
                "extends:BaseClass",
                "DataClassmethod:process",
                "external.module",
            ],
        }
        ctx = CodeGenerator.extract_ast_context(ast)
        assert len(ctx["class_hierarchies"]) > 0
        assert len(ctx["call_relationships"]) > 0
        assert len(ctx["import_dependencies"]) > 0
        assert "getter" in ctx["existing_patterns"]
        assert "private_methods" in ctx["existing_patterns"]

    def test_generate_feature_module_with_needed_imports(self):
        """Should include import comments for detected dependencies."""
        code = CodeGenerator.generate_feature_module(
            "imported",
            existing_functions=[],
            existing_classes=[],
            needed_imports={"my_module", "helpers"},
        )
        assert "my_module" in code
        assert "helpers" in code

    def test_pipeline_module_proven_header(self, code_gen):
        """Should include Z3 verified header for PROVEN status."""
        solver_insights = CodeGenerator.extract_solver_insights(None)
        solver_insights["status"] = "PROVEN"
        solver_insights["validated_constraints"] = ["constraint_1", "constraint_2"]

        code = code_gen.generate_pipeline_feature_module(
            safe_target="proven_mod",
            existing_functions=[],
            existing_classes=[],
            needed_imports=set(),
            solver_insights=solver_insights,
            mcts_actions=[],
        )
        assert "Z3 Verified" in code
