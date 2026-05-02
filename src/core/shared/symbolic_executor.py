"""
TITAN OMNISCALE X - Symbolic Executor v13

Ejecutor Simbolico Acotado real.

Implementa la ejecucion simbolica del Nivel 6 como especifica el documento:
- Estados simbolicos (valores abstractos con constraints)
- Path conditions por cada rama (string + Z3 cuando disponible)
- Path Pruning de side effects (I/O -> Mock)
- K-Path limiting (radio de exploracion)
- Bounded execution (profundidad limitada)
- Assignment tracking (mutaciones de estado simbolico)
- Return value tracking (verificacion de retorno consistente)
- Bounded loop unrolling (hasta 2 iteraciones)
- Violation detection: div-by-zero, index OOB, type mismatch, uninitialized, None deref
"""

import ast
import logging
import time

logger = logging.getLogger(__name__)

from .z3_solver import Z3Solver, HAS_Z3
from .constraint_solver import Constraint

# Z3 module reference for convenience (only available when HAS_Z3 is True)
if HAS_Z3:
    import z3 as z3_module


# ============================================================
#  SYMBOLIC EXECUTOR - Ejecucion Simbolica Acotada Real
# ============================================================

class SymbolicValue:
    """Representa un valor simbolico con constraint asociada."""

    def __init__(self, name, var_type="any", constraint=None, concrete=None):
        self.name = name
        self.var_type = var_type
        self.constraint = constraint  # Funcion lambda que debe cumplir
        self.concrete = concrete  # Valor concreto conocido (int, str, None, etc.)

    def __repr__(self):
        if self.concrete is not None:
            return f"Sym({self.name}:{self.var_type}={self.concrete!r})"
        return f"Sym({self.name}:{self.var_type})"


class SymbolicPath:
    """
    Representa un camino de ejecucion simbolica con path condition.

    Mantiene condiciones tanto en formato string (para AC-3 fallback)
    como en formato Z3 (para verificacion formal cuando Z3 esta disponible).
    """

    MAX_Z3_CONDITIONS = 50  # Limite de condiciones Z3 por camino (memoria-safe)

    def __init__(self, condition=None, result=None, is_pruned=False, variables=None,
                 z3_conditions=None, assignments=None, return_values=None):
        self.condition = condition or []  # Lista de condiciones simbolicas (string)
        self.result = result  # Resultado al final del camino
        self.is_pruned = is_pruned  # Si fue podado por I/O
        self.variables = variables if variables is not None else {}  # Estado de variables simbolicas
        self.z3_conditions = z3_conditions if z3_conditions is not None else []  # Z3 constraints
        self.assignments = assignments if assignments is not None else []  # Historial de asignaciones
        self.return_values = return_values if return_values is not None else []  # Valores de return

    def add_condition(self, cond, z3_cond=None):
        """Agrega una condicion al path condition (string y opcionalmente Z3)."""
        self.condition.append(cond)
        if z3_cond is not None and len(self.z3_conditions) < self.MAX_Z3_CONDITIONS:
            self.z3_conditions.append(z3_cond)

    def add_assignment(self, var_name, value_desc):
        """Registra una asignacion de variable en este camino."""
        self.assignments.append((var_name, value_desc))

    def add_return(self, return_desc, return_type="any"):
        """Registra un valor de retorno en este camino."""
        self.return_values.append({"desc": return_desc, "type": return_type})

    def is_feasible(self):
        """
        Verifica si el path condition es satisfacible.

        Usa Z3 cuando esta disponible para verificacion formal real.
        Fallback a verificacion string-based cuando Z3 no esta instalado.
        """
        if not self.condition and not self.z3_conditions:
            return True

        if HAS_Z3 and self.z3_conditions:
            return self._is_feasible_z3()
        return self._is_feasible_string()

    def _is_feasible_z3(self):
        """Verificacion de factibilidad usando Z3 SMT Solver."""
        try:
            solver = z3_module.Solver()
            solver.set("timeout", 500)  # 500ms para feasibility check
            for cond in self.z3_conditions:
                solver.add(cond)
            result = solver.check()
            return result != z3_module.unsat
        except Exception:
            # Fallback a string-based si Z3 falla
            return self._is_feasible_string()

    def _is_feasible_string(self):
        """Verificacion de factibilidad basada en strings (AC-3 fallback)."""
        if not self.condition:
            return True
        # Verificar contradicciones obvias
        negations = set()
        affirmations = set()
        for cond in self.condition:
            cond_str = str(cond)
            if cond_str.startswith("NOT_"):
                negations.add(cond_str[4:])
            else:
                affirmations.add(cond_str)
        # Si afirmamos y negamos lo mismo, es infeasible
        return not (affirmations & negations)


class SymbolicExecutor:
    """
    Ejecutor Simbolico Acotado real.

    Implementa la ejecucion simbolica del Nivel 6 como especifica el documento:
    - Estados simbolicos (valores abstractos con constraints)
    - Path conditions por cada rama (string + Z3 cuando disponible)
    - Path Pruning de side effects (I/O -> Mock)
    - K-Path limiting (radio de exploracion)
    - Bounded execution (profundidad limitada)
    - Assignment tracking (mutaciones de estado simbolico)
    - Return value tracking (verificacion de retorno consistente)
    - Bounded loop unrolling (hasta 2 iteraciones)
    - Violation detection: div-by-zero, index OOB, type mismatch, uninitialized, None deref
    """

    # Operaciones que son side effects y deben ser podadas
    IO_OPERATIONS = {
        "open", "read", "write", "input", "print",
        "fetch", "urlopen", "request",
        "execute", "cursor", "query",
        "connect", "send", "recv",
    }

    # Bounded loop unrolling: max iterations
    LOOP_UNROLL_LIMIT = 2

    # Incompatible type pairs for binary operations
    INCOMPATIBLE_TYPES = {
        frozenset({"str", "int"}), frozenset({"str", "float"}),
        frozenset({"list", "int"}), frozenset({"dict", "int"}),
        frozenset({"None", "int"}), frozenset({"None", "float"}),
        frozenset({"None", "str"}), frozenset({"None", "list"}),
    }

    def __init__(self, k_path_limit=10, max_depth=20):
        self.k_path_limit = k_path_limit
        self.max_depth = max_depth
        self.paths_explored = 0
        self.paths_pruned = 0
        self.results = []
        self._z3_vars = {}  # Cache of Z3 variable objects per function
        self._func_return_type = {}  # Inferred return types per function

    def execute_symbolic(self, code, language="python", target_name=""):
        """
        Ejecuta analisis simbolico acotado sobre codigo Python.

        Returns:
            dict con paths, violations, warnings, metrics
        """
        self.paths_explored = 0
        self.paths_pruned = 0
        self.results = []
        self._z3_vars = {}
        self._func_return_type = {}

        if language != "python":
            return self._symbolic_regex(code, language, target_name)

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "status": "FAIL_SYNTAX",
                "paths": [],
                "violations": [],
                "warnings": [f"Syntax error: {e.msg} at line {e.lineno}"],
                "metrics": {"paths_explored": 0, "paths_pruned": 0}
            }

        # Pre-scan: build a map of function names for call resolution
        func_map = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_map[node.name] = node
        self._func_map = func_map

        # Analizar cada funcion
        all_paths = []
        all_violations = []
        all_warnings = []
        total_pruned = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._z3_vars = {}  # Reset Z3 var cache per function
                func_paths = self._analyze_function_symbolic(node, code)
                all_paths.extend(func_paths)

                # Verificar violaciones en cada camino
                for path in func_paths:
                    if path.is_pruned:
                        total_pruned += 1
                    violations = self._check_path_violations(path, node.name)
                    all_violations.extend(violations)

                # Check return consistency across all paths of this function
                return_warnings = self._check_return_consistency(func_paths, node.name)
                all_warnings.extend(return_warnings)

        self.paths_explored = len(all_paths)
        self.paths_pruned = total_pruned

        # Verificar K-Path limit
        if self.paths_explored > self.k_path_limit:
            all_warnings.append(
                f"K-Paths ({self.paths_explored}) exceeds limit ({self.k_path_limit}). "
                f"Subdivide operation into smaller units."
            )

        return {
            "status": "PASS" if not all_violations else "VIOLATIONS_FOUND",
            "paths": all_paths,
            "violations": all_violations,
            "warnings": all_warnings,
            "metrics": {
                "paths_explored": self.paths_explored,
                "paths_pruned": self.paths_pruned,
                "total_paths": len(all_paths),
                "feasible_paths": sum(1 for p in all_paths if p.is_feasible()),
            }
        }

    # ----------------------------------------------------------------
    #  Z3 Variable Management
    # ----------------------------------------------------------------

    def _get_or_create_z3_var(self, name, var_type="int"):
        """Get or create a Z3 variable for the given symbolic variable name."""
        if name in self._z3_vars:
            return self._z3_vars[name]
        if HAS_Z3:
            if var_type in ("int", "any"):
                z3_var = z3_module.Int(name)
            elif var_type == "bool":
                z3_var = z3_module.Bool(name)
            else:
                z3_var = z3_module.Int(name)  # Default to Int
            self._z3_vars[name] = z3_var
            return z3_var
        return None

    def _encode_z3_condition(self, test_node, current_path, negate=False):
        """
        Encode an AST condition as a Z3 constraint.

        Returns (string_condition, z3_constraint_or_None).
        """
        string_cond = self._symbolize_condition(test_node, current_path)
        z3_cond = None

        if HAS_Z3:
            try:
                z3_cond = self._build_z3_constraint(test_node, current_path, negate=negate)
            except Exception:
                z3_cond = None

        return string_cond, z3_cond

    def _build_z3_constraint(self, node, current_path, negate=False):
        """Build a Z3 constraint from an AST test node."""
        if not HAS_Z3:
            return None

        constraint = self._z3_expr_from_node(node, current_path)

        if constraint is None:
            return None

        if negate:
            constraint = z3_module.Not(constraint)
        return constraint

    def _z3_expr_from_node(self, node, current_path):
        """Recursively build a Z3 boolean expression from an AST node."""
        if not HAS_Z3:
            return None

        if isinstance(node, ast.Compare):
            left = self._z3_value_from_node(node.left, current_path)
            if left is None:
                return None
            z3_conds = []
            for op, comp in zip(node.ops, node.comparators):
                right = self._z3_value_from_node(comp, current_path)
                if right is None:
                    return None
                if isinstance(op, ast.Eq):
                    z3_conds.append(left == right)
                elif isinstance(op, ast.NotEq):
                    z3_conds.append(left != right)
                elif isinstance(op, ast.Lt):
                    z3_conds.append(left < right)
                elif isinstance(op, ast.LtE):
                    z3_conds.append(left <= right)
                elif isinstance(op, ast.Gt):
                    z3_conds.append(left > right)
                elif isinstance(op, ast.GtE):
                    z3_conds.append(left >= right)
                elif isinstance(op, ast.Is):
                    z3_conds.append(left == right)
                elif isinstance(op, ast.IsNot):
                    z3_conds.append(left != right)
                else:
                    return None
                left = right  # Chain comparisons
            if len(z3_conds) == 1:
                return z3_conds[0]
            return z3_module.And(*z3_conds)

        elif isinstance(node, ast.BoolOp):
            parts = []
            for v in node.values:
                part = self._z3_expr_from_node(v, current_path)
                if part is None:
                    return None
                parts.append(part)
            if isinstance(node.op, ast.And):
                return z3_module.And(*parts)
            elif isinstance(node.op, ast.Or):
                return z3_module.Or(*parts)

        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self._z3_expr_from_node(node.operand, current_path)
            if inner is None:
                return None
            return z3_module.Not(inner)

        elif isinstance(node, ast.Name):
            # TRUTHY check
            z3_var = self._get_or_create_z3_var(node.id)
            if z3_var is not None:
                return z3_var != 0

        return None

    def _z3_value_from_node(self, node, current_path):
        """Extract a Z3 numeric value from an AST expression node."""
        if not HAS_Z3:
            return None

        if isinstance(node, ast.Constant):
            if isinstance(node.value, int):
                return z3_module.IntVal(node.value)
            elif isinstance(node.value, bool):
                return z3_module.IntVal(1 if node.value else 0)
            elif node.value is None:
                return z3_module.IntVal(0)  # 0 = None in our encoding
        elif isinstance(node, ast.Name):
            if node.id in current_path.variables:
                sym_val = current_path.variables[node.id]
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    if isinstance(sym_val.concrete, int):
                        return z3_module.IntVal(sym_val.concrete)
                    elif sym_val.concrete is None:
                        return z3_module.IntVal(0)
            z3_var = self._get_or_create_z3_var(node.id)
            if z3_var is not None:
                return z3_var
        elif isinstance(node, ast.BinOp):
            left = self._z3_value_from_node(node.left, current_path)
            right = self._z3_value_from_node(node.right, current_path)
            if left is not None and right is not None:
                if isinstance(node.op, ast.Add):
                    return left + right
                elif isinstance(node.op, ast.Sub):
                    return left - right
                elif isinstance(node.op, ast.Mult):
                    return left * right
                elif isinstance(node.op, (ast.Div, ast.FloorDiv)):
                    return left  # Simplified - don't encode division in Z3 value
                elif isinstance(node.op, ast.Mod):
                    return left  # Simplified
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._z3_value_from_node(node.operand, current_path)
            if inner is not None:
                return -inner

        return None

    # ----------------------------------------------------------------
    #  Function Analysis
    # ----------------------------------------------------------------

    def _analyze_function_symbolic(self, func_node, source_code):
        """
        Analiza simbolicamente una funcion, explorando todos los caminos.

        Ahora con:
        - Tracking de asignaciones (ast.Assign, ast.AugAssign)
        - Handling de returns (ast.Return)
        - Bounded loop unrolling (ast.For, ast.While)
        - Z3 condition encoding
        """
        # Inicializar estado simbolico con parametros
        initial_state = {}
        for arg in func_node.args.args:
            arg_type = "any"
            if arg.annotation:
                arg_type = self._annotation_to_type(arg.annotation)
            initial_state[arg.arg] = SymbolicValue(
                name=arg.arg,
                var_type=arg_type
            )
            # Pre-create Z3 vars for parameters
            self._get_or_create_z3_var(arg.arg, arg_type)

        # Process function body statement by statement
        initial_path = SymbolicPath(
            variables=dict(initial_state),
            z3_conditions=[],
            assignments=[],
            return_values=[]
        )
        paths = self._process_stmts(func_node.body, initial_path)

        return paths[:self.k_path_limit]

    def _process_stmts(self, stmts, current_path):
        """
        Process a list of statements, returning a list of resulting SymbolicPaths.

        This is the core of the symbolic execution engine, handling each
        statement type and forking paths at branches.
        """
        worklist = [(list(stmts), current_path)]
        completed_paths = []

        while worklist:
            remaining_stmts, path = worklist.pop(0)

            if len(completed_paths) >= self.k_path_limit:
                break

            if not remaining_stmts:
                completed_paths.append(path)
                continue

            stmt = remaining_stmts[0]
            rest = remaining_stmts[1:]

            # --- ast.Assign: x = expr ---
            if isinstance(stmt, ast.Assign):
                new_path = self._process_assign(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.AugAssign: x += expr ---
            elif isinstance(stmt, ast.AugAssign):
                new_path = self._process_aug_assign(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.Return ---
            elif isinstance(stmt, ast.Return):
                ret_path = self._process_return(stmt, path)
                completed_paths.append(ret_path)

            # --- ast.If ---
            elif isinstance(stmt, ast.If):
                branch_paths = self._process_if(stmt, path)
                for bp in branch_paths:
                    if bp.is_feasible():
                        # Process true body then rest / false body then rest
                        worklist.append((rest, bp))
                    else:
                        self.paths_pruned += 1

            # --- ast.For (bounded unrolling) ---
            elif isinstance(stmt, ast.For):
                loop_paths = self._process_for(stmt, path)
                for lp in loop_paths:
                    worklist.append((rest, lp))

            # --- ast.While (bounded unrolling) ---
            elif isinstance(stmt, ast.While):
                loop_paths = self._process_while(stmt, path)
                for lp in loop_paths:
                    worklist.append((rest, lp))

            # --- ast.Expr (expression statement, e.g. function calls) ---
            elif isinstance(stmt, ast.Expr):
                new_path = self._process_expr_stmt(stmt, path)
                worklist.append((rest, new_path))

            # --- ast.Pass ---
            elif isinstance(stmt, ast.Pass):
                worklist.append((rest, path))

            # --- ast.Break ---
            elif isinstance(stmt, ast.Break):
                # Exit current loop - just complete the path here
                completed_paths.append(path)

            # --- ast.Continue ---
            elif isinstance(stmt, ast.Continue):
                # Would need loop context; simplified: skip
                worklist.append((rest, path))

            # --- ast.Try ---
            elif isinstance(stmt, ast.Try):
                # Process try body, and create alternative paths for each handler
                try_paths = self._process_try(stmt, path)
                for tp in try_paths:
                    worklist.append((rest, tp))

            # --- ast.Raise ---
            elif isinstance(stmt, ast.Raise):
                # Path ends with exception
                exc_desc = "raised_exception"
                if stmt.exc:
                    exc_desc = self._symbolize_expr(stmt.exc, path)
                new_path = SymbolicPath(
                    condition=list(path.condition),
                    variables=dict(path.variables),
                    is_pruned=path.is_pruned,
                    z3_conditions=list(path.z3_conditions),
                    assignments=list(path.assignments),
                    return_values=list(path.return_values)
                )
                new_path.add_return(f"raise {exc_desc}", "exception")
                completed_paths.append(new_path)

            # --- Other statements: skip but continue ---
            else:
                worklist.append((rest, path))

        return completed_paths[:self.k_path_limit]

    # ----------------------------------------------------------------
    #  Statement Processors
    # ----------------------------------------------------------------

    def _process_assign(self, stmt, path):
        """Process ast.Assign: update symbolic state with new value."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        for target in stmt.targets:
            if isinstance(target, ast.Name):
                var_name = target.id
                sym_val = self._eval_assign_value(stmt.value, new_path, var_name)
                new_path.variables[var_name] = sym_val
                new_path.add_assignment(var_name, self._symbolize_expr(stmt.value, path))

                # Update Z3 var if we have a concrete value
                if HAS_Z3 and sym_val.concrete is not None:
                    z3_var = self._get_or_create_z3_var(var_name)
                    if z3_var is not None and len(new_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                        if isinstance(sym_val.concrete, int):
                            new_path.z3_conditions.append(z3_var == sym_val.concrete)

            elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
                # Tuple/list unpacking: simplified handling
                for i, elt in enumerate(target.elts):
                    if isinstance(elt, ast.Name):
                        var_name = elt.id
                        sym_val = SymbolicValue(
                            name=var_name,
                            var_type="any",
                            constraint=None
                        )
                        new_path.variables[var_name] = sym_val
                        new_path.add_assignment(var_name, f"unpack[{i}]")

            elif isinstance(target, ast.Subscript):
                # x[key] = value: simplified - mark x as modified
                if isinstance(target.value, ast.Name):
                    var_name = target.value.id
                    if var_name in new_path.variables:
                        # Mark as possibly modified
                        existing = new_path.variables[var_name]
                        new_path.variables[var_name] = SymbolicValue(
                            name=var_name,
                            var_type=existing.var_type,
                            constraint=existing.constraint,
                            concrete=None  # No longer concretely known
                        )
                        new_path.add_assignment(f"{var_name}[...]", self._symbolize_expr(stmt.value, path))

        return new_path

    def _process_aug_assign(self, stmt, path):
        """Process ast.AugAssign (x += 1, x -= 2, etc.)."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if isinstance(stmt.target, ast.Name):
            var_name = stmt.target.id
            old_val = new_path.variables.get(var_name)
            old_type = old_val.var_type if old_val else "any"

            # Compute new concrete value if possible
            new_concrete = None
            if old_val and old_val.concrete is not None:
                rhs_concrete = self._try_eval_concrete(stmt.value, new_path)
                if rhs_concrete is not None:
                    op_map = {
                        ast.Add: lambda a, b: a + b,
                        ast.Sub: lambda a, b: a - b,
                        ast.Mult: lambda a, b: a * b,
                        ast.Mod: lambda a, b: a % b if b != 0 else None,
                        ast.FloorDiv: lambda a, b: a // b if b != 0 else None,
                    }
                    op_fn = op_map.get(type(stmt.op))
                    if op_fn:
                        try:
                            new_concrete = op_fn(old_val.concrete, rhs_concrete)
                        except (TypeError, ZeroDivisionError):
                            new_concrete = None

            op_str_map = {
                ast.Add: "+=", ast.Sub: "-=", ast.Mult: "*=",
                ast.Div: "/=", ast.Mod: "%=", ast.FloorDiv: "//=",
            }
            op_str = op_str_map.get(type(stmt.op), "?=")
            rhs_str = self._symbolize_expr(stmt.value, path)

            new_path.variables[var_name] = SymbolicValue(
                name=var_name,
                var_type=old_type,
                concrete=new_concrete
            )
            new_path.add_assignment(var_name, f"{var_name}{op_str}{rhs_str}")

            # Z3: add constraint for the augmented assignment
            if HAS_Z3 and new_concrete is not None:
                z3_var = self._get_or_create_z3_var(var_name)
                if z3_var is not None and len(new_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                    new_path.z3_conditions.append(z3_var == new_concrete)

        return new_path

    def _process_return(self, stmt, path):
        """Process ast.Return: track return value and end the path."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if stmt.value is not None:
            ret_desc = self._symbolize_expr(stmt.value, path)
            ret_type = "any"
            ret_concrete = self._try_eval_concrete(stmt.value, path)

            # Infer return type from expression
            if isinstance(stmt.value, ast.Constant):
                if stmt.value.value is None:
                    ret_type = "None"
                elif isinstance(stmt.value.value, int):
                    ret_type = "int"
                elif isinstance(stmt.value.value, float):
                    ret_type = "float"
                elif isinstance(stmt.value.value, str):
                    ret_type = "str"
                elif isinstance(stmt.value.value, bool):
                    ret_type = "bool"
            elif isinstance(stmt.value, ast.Name):
                if stmt.value.id in path.variables:
                    ret_type = path.variables[stmt.value.id].var_type
            elif isinstance(stmt.value, (ast.List, ast.ListComp)):
                ret_type = "list"
            elif isinstance(stmt.value, (ast.Dict, ast.DictComp)):
                ret_type = "dict"
            elif isinstance(stmt.value, ast.Call):
                func_name = self._get_call_name(stmt.value)
                # Try to infer from known function return types
                if func_name == "len":
                    ret_type = "int"
                elif func_name == "str":
                    ret_type = "str"
                elif func_name == "int":
                    ret_type = "int"
                elif func_name == "float":
                    ret_type = "float"
                elif func_name == "list":
                    ret_type = "list"
                elif func_name == "dict":
                    ret_type = "dict"
                elif func_name == "bool":
                    ret_type = "bool"

            new_path.add_return(ret_desc, ret_type)
            new_path.result = ret_desc
        else:
            # bare return -> returns None
            new_path.add_return("None", "None")
            new_path.result = "None"

        return new_path

    def _process_if(self, stmt, path):
        """Process ast.If: fork path into true and false branches."""
        true_str, true_z3 = self._encode_z3_condition(stmt.test, path, negate=False)
        false_str = f"NOT_{true_str}"
        false_z3 = None
        if HAS_Z3 and true_z3 is not None:
            try:
                false_z3 = z3_module.Not(true_z3)
            except Exception:
                false_z3 = None

        # True branch
        true_path = SymbolicPath(
            condition=path.condition + [true_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if true_z3 is not None:
            true_path.add_condition(true_str, true_z3)
        else:
            true_path.add_condition(true_str)

        # Process true body statements
        true_paths = self._process_stmts(stmt.body, true_path)

        # False branch
        false_path = SymbolicPath(
            condition=path.condition + [false_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if false_z3 is not None:
            false_path.add_condition(false_str, false_z3)
        else:
            false_path.add_condition(false_str)

        if stmt.orelse:
            false_paths = self._process_stmts(stmt.orelse, false_path)
        else:
            false_paths = [false_path]

        # Check I/O in branches
        for tp in true_paths:
            tp = self._check_io_in_body(stmt.body, tp)
        for fp in false_paths:
            if stmt.orelse:
                fp = self._check_io_in_body(stmt.orelse, fp)

        return true_paths + false_paths

    def _process_for(self, stmt, path):
        """
        Process ast.For with bounded unrolling (up to LOOP_UNROLL_LIMIT iterations).

        Creates paths for:
        - Loop body iteration 1
        - Loop body iteration 2
        - Loop exit (0 iterations)
        Each with appropriate path conditions on the loop variable.
        """
        all_paths = []

        # Get loop variable name
        if not isinstance(stmt.target, ast.Name):
            # Complex target; simplified handling
            return [path]
        loop_var = stmt.target.id

        # Determine iteration range if possible
        iter_concrete = None
        if isinstance(stmt.iter, ast.Call):
            func_name = self._get_call_name(stmt.iter)
            if func_name == "range" and stmt.iter.args:
                # range(n) or range(start, stop) or range(start, stop, step)
                args_concrete = [self._try_eval_concrete(a, path) for a in stmt.iter.args]
                if all(a is not None for a in args_concrete):
                    try:
                        iter_concrete = list(range(*args_concrete))
                    except (TypeError, ValueError):
                        iter_concrete = None

        # Path for 0 iterations (loop exit immediately)
        exit_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        # Add condition: loop didn't execute (i.e., iterator was empty)
        if iter_concrete is not None and len(iter_concrete) == 0:
            # This path is the only possibility
            return [exit_path]
        exit_path.add_condition(f"LOOP_EMPTY_{loop_var}")
        all_paths.append(exit_path)

        # Bounded unrolling
        current_paths = [path]
        for iteration in range(self.LOOP_UNROLL_LIMIT):
            next_paths = []
            for cp in current_paths:
                # Create path for this iteration
                iter_path = SymbolicPath(
                    condition=list(cp.condition),
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )

                # Set loop variable value
                if iter_concrete is not None and iteration < len(iter_concrete):
                    loop_val = iter_concrete[iteration]
                    iter_path.variables[loop_var] = SymbolicValue(
                        name=loop_var, var_type="int", concrete=loop_val
                    )
                    # Z3: constrain loop variable
                    if HAS_Z3:
                        z3_var = self._get_or_create_z3_var(loop_var, "int")
                        if z3_var is not None and len(iter_path.z3_conditions) < SymbolicPath.MAX_Z3_CONDITIONS:
                            iter_path.z3_conditions.append(z3_var == loop_val)
                else:
                    iter_path.variables[loop_var] = SymbolicValue(
                        name=loop_var, var_type="int"
                    )

                iter_path.add_condition(f"LOOP_ITER_{loop_var}_{iteration}")
                iter_path.add_assignment(loop_var, f"iter_{iteration}")

                # Process loop body
                body_paths = self._process_stmts(stmt.body, iter_path)
                next_paths.extend(body_paths)

            current_paths = next_paths
            if not current_paths:
                break

            # After last unrolled iteration, add exit paths
            if iteration == self.LOOP_UNROLL_LIMIT - 1:
                for cp in current_paths:
                    exit_after = SymbolicPath(
                        condition=list(cp.condition),
                        variables=dict(cp.variables),
                        is_pruned=cp.is_pruned,
                        z3_conditions=list(cp.z3_conditions),
                        assignments=list(cp.assignments),
                        return_values=list(cp.return_values)
                    )
                    exit_after.add_condition(f"LOOP_EXIT_{loop_var}")
                    all_paths.append(exit_after)
            else:
                # For intermediate iterations, also create exit paths
                for cp in current_paths:
                    exit_after = SymbolicPath(
                        condition=list(cp.condition),
                        variables=dict(cp.variables),
                        is_pruned=cp.is_pruned,
                        z3_conditions=list(cp.z3_conditions),
                        assignments=list(cp.assignments),
                        return_values=list(cp.return_values)
                    )
                    exit_after.add_condition(f"LOOP_EXIT_{loop_var}_after_{iteration + 1}")
                    all_paths.append(exit_after)

        all_paths.extend(current_paths)
        return all_paths[:self.k_path_limit]

    def _process_while(self, stmt, path):
        """
        Process ast.While with bounded unrolling (up to LOOP_UNROLL_LIMIT iterations).

        Creates paths for:
        - Condition false (loop exit)
        - Condition true + body (iteration 1)
        - Condition true + body (iteration 2)
        """
        all_paths = []

        # Path for 0 iterations (condition false immediately)
        false_str, false_z3 = self._encode_z3_condition(stmt.test, path, negate=True)
        exit_path = SymbolicPath(
            condition=path.condition + [false_str],
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )
        if false_z3 is not None:
            exit_path.add_condition(false_str, false_z3)
        else:
            exit_path.add_condition(false_str)
        all_paths.append(exit_path)

        # Bounded unrolling
        current_paths = [path]
        for iteration in range(self.LOOP_UNROLL_LIMIT):
            next_paths = []
            for cp in current_paths:
                # Condition true path
                true_str, true_z3 = self._encode_z3_condition(stmt.test, cp, negate=False)
                iter_path = SymbolicPath(
                    condition=cp.condition + [true_str],
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )
                if true_z3 is not None:
                    iter_path.add_condition(true_str, true_z3)
                else:
                    iter_path.add_condition(true_str)

                iter_path.add_condition(f"WHILE_ITER_{iteration}")

                # Process loop body
                body_paths = self._process_stmts(stmt.body, iter_path)
                next_paths.extend(body_paths)

                # Also add exit path after this iteration
                exit_str, exit_z3 = self._encode_z3_condition(stmt.test, cp, negate=True)
                exit_iter_path = SymbolicPath(
                    condition=cp.condition + [exit_str],
                    variables=dict(cp.variables),
                    is_pruned=cp.is_pruned,
                    z3_conditions=list(cp.z3_conditions),
                    assignments=list(cp.assignments),
                    return_values=list(cp.return_values)
                )
                if exit_z3 is not None:
                    exit_iter_path.add_condition(exit_str, exit_z3)
                else:
                    exit_iter_path.add_condition(exit_str)
                all_paths.append(exit_iter_path)

            current_paths = next_paths
            if not current_paths:
                break

        # Add remaining paths (after all unrolled iterations)
        all_paths.extend(current_paths)
        return all_paths[:self.k_path_limit]

    def _process_try(self, stmt, path):
        """Process ast.Try: create paths for try body and each handler."""
        all_paths = []

        # Try body (normal execution)
        try_paths = self._process_stmts(stmt.body, path)
        all_paths.extend(try_paths)

        # Each except handler
        for handler in stmt.handlers:
            handler_path = SymbolicPath(
                condition=list(path.condition),
                variables=dict(path.variables),
                is_pruned=path.is_pruned,
                z3_conditions=list(path.z3_conditions),
                assignments=list(path.assignments),
                return_values=list(path.return_values)
            )
            exc_type = "Exception"
            if handler.type:
                exc_type = self._symbolize_expr(handler.type, path)
            handler_path.add_condition(f"EXCEPTION_{exc_type}")

            if handler.name:
                handler_path.variables[handler.name] = SymbolicValue(
                    name=handler.name, var_type="exception"
                )
                handler_path.add_assignment(handler.name, f"caught_{exc_type}")

            handler_body_paths = self._process_stmts(handler.body, handler_path)
            all_paths.extend(handler_body_paths)

        # Else clause (if no exception)
        if stmt.orelse:
            else_paths = self._process_stmts(stmt.orelse, try_paths[0] if try_paths else path)
            all_paths.extend(else_paths)

        # Finally clause
        if stmt.finalbody:
            final_paths = []
            for p in all_paths:
                fp = self._process_stmts(stmt.finalbody, p)
                final_paths.extend(fp)
            all_paths = final_paths

        return all_paths

    def _process_expr_stmt(self, stmt, path):
        """Process ast.Expr statement (e.g., standalone function calls)."""
        new_path = SymbolicPath(
            condition=list(path.condition),
            variables=dict(path.variables),
            is_pruned=path.is_pruned,
            z3_conditions=list(path.z3_conditions),
            assignments=list(path.assignments),
            return_values=list(path.return_values)
        )

        if isinstance(stmt.value, ast.Call):
            call_name = self._get_call_name(stmt.value)
            base_name = call_name.split('.')[-1] if '.' in call_name else call_name
            if base_name in self.IO_OPERATIONS:
                new_path.is_pruned = True
                new_path.variables[f"_mocked_{call_name}"] = SymbolicValue(
                    name=f"_mocked_{call_name}",
                    var_type="mocked_io",
                    constraint=lambda x: True
                )

        return new_path

    # ----------------------------------------------------------------
    #  Value Evaluation Helpers
    # ----------------------------------------------------------------

    def _eval_assign_value(self, value_node, path, var_name):
        """Evaluate the RHS of an assignment to create a SymbolicValue."""
        # Try to get a concrete value first
        concrete = self._try_eval_concrete(value_node, path)
        var_type = "any"

        if isinstance(value_node, ast.Constant):
            if value_node.value is None:
                var_type = "None"
            elif isinstance(value_node.value, int):
                var_type = "int"
            elif isinstance(value_node.value, float):
                var_type = "float"
            elif isinstance(value_node.value, str):
                var_type = "str"
            elif isinstance(value_node.value, bool):
                var_type = "bool"
        elif isinstance(value_node, (ast.List, ast.ListComp)):
            var_type = "list"
        elif isinstance(value_node, (ast.Dict, ast.DictComp)):
            var_type = "dict"
        elif isinstance(value_node, ast.Name):
            if value_node.id in path.variables:
                src = path.variables[value_node.id]
                var_type = src.var_type
                if concrete is None and src.concrete is not None:
                    concrete = src.concrete
        elif isinstance(value_node, ast.BinOp):
            # Infer type from operands
            left_type = "any"
            right_type = "any"
            if isinstance(value_node.left, ast.Name) and value_node.left.id in path.variables:
                left_type = path.variables[value_node.left.id].var_type
            if isinstance(value_node.right, ast.Name) and value_node.right.id in path.variables:
                right_type = path.variables[value_node.right.id].var_type
            if left_type in ("int", "float") and right_type in ("int", "float"):
                var_type = "float" if "float" in (left_type, right_type) else "int"
            elif left_type == "str" and right_type == "str" and isinstance(value_node.op, ast.Add):
                var_type = "str"
        elif isinstance(value_node, ast.Call):
            func_name = self._get_call_name(value_node)
            type_inference = {
                "int": "int", "float": "float", "str": "str",
                "bool": "bool", "list": "list", "dict": "dict",
                "len": "int", "range": "list", "type": "type",
            }
            var_type = type_inference.get(func_name, "any")
            # Check if calling a known function in our func_map
            if func_name in getattr(self, '_func_map', {}):
                var_type = "return_type_of_func"

        return SymbolicValue(
            name=var_name,
            var_type=var_type,
            concrete=concrete
        )

    def _try_eval_concrete(self, node, path):
        """Try to evaluate an AST node to a concrete Python value."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in path.variables:
                sym_val = path.variables[node.id]
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    return sym_val.concrete
        elif isinstance(node, ast.BinOp):
            left = self._try_eval_concrete(node.left, path)
            right = self._try_eval_concrete(node.right, path)
            if left is not None and right is not None:
                try:
                    if isinstance(node.op, ast.Add):
                        return left + right
                    elif isinstance(node.op, ast.Sub):
                        return left - right
                    elif isinstance(node.op, ast.Mult):
                        return left * right
                    elif isinstance(node.op, ast.Div):
                        return left / right if right != 0 else None
                    elif isinstance(node.op, ast.FloorDiv):
                        return left // right if right != 0 else None
                    elif isinstance(node.op, ast.Mod):
                        return left % right if right != 0 else None
                except (TypeError, ZeroDivisionError):
                    return None
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._try_eval_concrete(node.operand, path)
            if inner is not None:
                try:
                    return -inner
                except TypeError:
                    return None
        elif isinstance(node, ast.Call):
            func_name = self._get_call_name(node)
            if func_name == "len" and node.args:
                inner = self._try_eval_concrete(node.args[0], path)
                if inner is not None and hasattr(inner, '__len__'):
                    try:
                        return len(inner)
                    except TypeError:
                        return None
        return None

    def _annotation_to_type(self, annotation):
        """Convert a type annotation AST node to a type string."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Attribute):
            return annotation.attr
        return "any"

    # ----------------------------------------------------------------
    #  Return Consistency Check
    # ----------------------------------------------------------------

    def _check_return_consistency(self, paths, func_name):
        """Check if all paths return a value and return types are consistent."""
        warnings = []

        # Check for paths that don't return (fall off the end)
        paths_without_return = []
        for path in paths:
            if not path.return_values:
                paths_without_return.append(path)

        if paths_without_return:
            warnings.append(
                f"Function '{func_name}' may not return a value on all paths "
                f"({len(paths_without_return)} path(s) fall off the end without returning)"
            )

        # Check return type consistency
        return_types = set()
        for path in paths:
            for rv in path.return_values:
                rt = rv.get("type", "any")
                if rt != "exception":  # Don't count raises as return types
                    return_types.add(rt)

        # If we have incompatible return types, warn
        non_any_types = return_types - {"any"}
        if len(non_any_types) > 1:
            # None is sometimes acceptable alongside other types (Optional)
            non_none_types = non_any_types - {"None"}
            if len(non_none_types) > 1:
                warnings.append(
                    f"Function '{func_name}' may return inconsistent types: {non_any_types}"
                )

        return warnings

    # ----------------------------------------------------------------
    #  Violation Detection
    # ----------------------------------------------------------------

    def _check_path_violations(self, path, func_name):
        """
        Verifica violaciones de invariantes en un camino simbolico.

        Detecta:
        - None dereference
        - Division by zero
        - Index out of bounds
        - Type mismatches
        - Uninitialized variable usage
        """
        violations = []

        # 1. Verificar None dereference
        self._check_none_dereference(path, func_name, violations)

        # 2. Verificar division by zero
        self._check_division_by_zero(path, func_name, violations)

        # 3. Verificar index out of bounds
        self._check_index_out_of_bounds(path, func_name, violations)

        # 4. Verificar type mismatches
        self._check_type_mismatches(path, func_name, violations)

        # 5. Verificar uninitialized variable usage
        self._check_uninitialized_variables(path, func_name, violations)

        return violations

    def _check_none_dereference(self, path, func_name, violations):
        """Check for potential None dereference on a path."""
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue):
                if sym_val.var_type == "None":
                    # Variable may be None - check if path condition excludes it
                    for cond in path.condition:
                        cond_str = str(cond)
                        if (f"SYM({var_name})!=" in cond_str or
                                f"SYM({var_name}) is_not None" in cond_str or
                                f"SYM({var_name}) is_not None" in cond_str):
                            break
                    else:
                        violations.append(
                            f"Potential None dereference: '{var_name}' may be None "
                            f"in function '{func_name}'"
                        )

    def _check_division_by_zero(self, path, func_name, violations):
        """Check for potential division by zero on a path."""
        # Collect all expression descriptions (from assignments and return values)
        all_exprs = [str(desc) for _, desc in path.assignments]
        for rv in path.return_values:
            all_exprs.append(str(rv.get("desc", "")))

        # Check 1: variables with known concrete value of 0 used as denominator
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and sym_val.concrete == 0:
                # Check if this variable is used as a denominator in any expression
                for expr_str in all_exprs:
                    if f"/SYM({var_name})" in expr_str or f"%SYM({var_name})" in expr_str:
                        violations.append(
                            f"Potential division by zero: '{var_name}' may be 0 "
                            f"in function '{func_name}'"
                        )
                        break  # One violation per variable is enough

        # Check 2: scan all expression descriptions for division patterns
        # and check if denominator variable can be 0 using Z3 or heuristic
        import re as _re
        for expr_str in all_exprs:
            # Find all denominator variables in division/modulo operations
            # Match patterns like /SYM(var) or %SYM(var)
            denom_refs = _re.findall(r'[/%]SYM\((\w+)\)', expr_str)
            for denom_var in denom_refs:
                sym_val = path.variables.get(denom_var)
                if not isinstance(sym_val, SymbolicValue):
                    continue
                # If the variable is known to be None, skip (that's a None deref)
                if sym_val.var_type == "None":
                    continue
                # If we already detected this variable, skip
                already_found = any(
                    f"'{denom_var}'" in v for v in violations
                )
                if already_found:
                    continue
                # If concrete value is known and non-zero, it's safe
                if sym_val.concrete is not None and sym_val.concrete != 0:
                    continue
                # Use Z3 to check if the variable can be 0 on this path
                if HAS_Z3:
                    try:
                        z3_var = self._get_or_create_z3_var(denom_var, "int")
                        if z3_var is not None:
                            test_solver = z3_module.Solver()
                            test_solver.set("timeout", 300)
                            # Add all existing path conditions
                            for cond in path.z3_conditions:
                                test_solver.add(cond)
                            # Check: can the denominator be 0?
                            test_solver.add(z3_var == 0)
                            if test_solver.check() == z3_module.sat:
                                violations.append(
                                    f"Potential division by zero: '{denom_var}' can be 0 "
                                    f"in function '{func_name}' (Z3 verified)"
                                )
                            # else: Z3 proved it can't be zero - safe
                    except Exception:
                        # Z3 failed - use heuristic: if variable is not constrained
                        # away from zero, flag it as potential issue
                        is_constrained_nonzero = any(
                            f"SYM({denom_var})!=0" in str(c) or
                            f"SYM({denom_var})>0" in str(c) or
                            f"SYM({denom_var})<" in str(c)
                            for c in path.condition
                        )
                        if not is_constrained_nonzero:
                            violations.append(
                                f"Potential division by zero: '{denom_var}' may be 0 "
                                f"in function '{func_name}'"
                            )
                else:
                    # No Z3: heuristic check - is the variable constrained away from zero?
                    is_constrained_nonzero = any(
                        f"SYM({denom_var})!=0" in str(c) or
                        f"SYM({denom_var})>0" in str(c) or
                        f"SYM({denom_var})<" in str(c)
                        for c in path.condition
                    )
                    if not is_constrained_nonzero and sym_val.concrete is None:
                        violations.append(
                            f"Potential division by zero: '{denom_var}' may be 0 "
                            f"in function '{func_name}'"
                        )

    def _check_index_out_of_bounds(self, path, func_name, violations):
        """Check for potential index out of bounds access."""
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and sym_val.var_type == "int":
                # Check if this int variable is used as an index
                for _, desc in path.assignments:
                    desc_str = str(desc)
                    # Pattern: something[var_name] - using var as index
                    if f"[{var_name}]" in desc_str or f"[SYM({var_name})]" in desc_str:
                        # Check if the index can be negative or too large
                        if sym_val.concrete is not None:
                            if sym_val.concrete < 0:
                                violations.append(
                                    f"Potential index out of bounds: '{var_name}' = {sym_val.concrete} "
                                    f"(negative index) in function '{func_name}'"
                                )
                        else:
                            # Variable is symbolic - check with Z3 if it can be negative
                            if HAS_Z3 and path.z3_conditions:
                                try:
                                    z3_var = self._get_or_create_z3_var(var_name, "int")
                                    if z3_var is not None:
                                        test_solver = z3_module.Solver()
                                        test_solver.set("timeout", 300)
                                        for cond in path.z3_conditions:
                                            test_solver.add(cond)
                                        test_solver.add(z3_var < 0)
                                        if test_solver.check() == z3_module.sat:
                                            violations.append(
                                                f"Potential index out of bounds: '{var_name}' may be "
                                                f"negative in function '{func_name}' (Z3 verified)"
                                            )
                                except Exception as z3_err:
                                    logger.debug(f"SymbolicExecutor: Z3 bounds check failed: {z3_err}")

    def _check_type_mismatches(self, path, func_name, violations):
        """Check for type mismatches in binary operations."""
        # Collect all expression descriptions (from assignments and return values)
        import re as _re
        all_exprs = [str(desc) for _, desc in path.assignments]
        for rv in path.return_values:
            all_exprs.append(str(rv.get("desc", "")))

        # Check all expressions for pairs of variables with incompatible types
        checked_pairs = set()
        for expr_str in all_exprs:
            # Find all SYM(var) references in this expression
            sym_refs = _re.findall(r'SYM\((\w+)\)', expr_str)
            if len(sym_refs) < 2:
                continue
            # Check all pairs of referenced variables for type incompatibility
            for i in range(len(sym_refs)):
                for j in range(i + 1, len(sym_refs)):
                    v1_name = sym_refs[i]
                    v2_name = sym_refs[j]
                    pair_key = (v1_name, v2_name) if v1_name < v2_name else (v2_name, v1_name)
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)
                    v1 = path.variables.get(v1_name)
                    v2 = path.variables.get(v2_name)
                    if not isinstance(v1, SymbolicValue) or not isinstance(v2, SymbolicValue):
                        continue
                    t1 = v1.var_type
                    t2 = v2.var_type
                    if t1 != "any" and t2 != "any" and t1 != t2:
                        pair = frozenset({t1, t2})
                        if pair in self.INCOMPATIBLE_TYPES:
                            violations.append(
                                f"Potential type mismatch: '{v1_name}' ({t1}) and "
                                f"'{v2_name}' ({t2}) used together "
                                f"in function '{func_name}'"
                            )

    def _check_uninitialized_variables(self, path, func_name, violations):
        """Check for use of uninitialized variables on a path."""
        import re as _re

        # Build set of variables that are assigned on this path
        assigned_vars = set()
        for var_name, _ in path.assignments:
            assigned_vars.add(var_name)

        # Build set of function parameters (always initialized)
        param_vars = set()
        for var_name, sym_val in path.variables.items():
            if isinstance(sym_val, SymbolicValue) and var_name not in assigned_vars:
                param_vars.add(var_name)

        initialized = assigned_vars | param_vars

        # Check return value descriptions for bare variable names
        # A bare name (not inside SYM()) in a return expression means the variable
        # was NOT in the symbolic state when referenced = potentially uninitialized
        for rv in path.return_values:
            desc = str(rv.get("desc", ""))
            # If the description is just a bare name (not SYM(...), not a literal)
            # then the variable was not in the symbolic state when used
            if not desc.startswith("SYM(") and not desc.startswith(("'", '"', '-', '(')):
                # It's a bare name - check if it was initialized
                if (desc not in {'None', 'True', 'False', 'UNKNOWN', 'SYM_EXPR'}
                        and not desc[0].isdigit()
                        and desc not in path.variables
                        and desc not in initialized
                        and not desc.startswith('_')
                        and '(' not in desc):
                    violations.append(
                        f"Potential uninitialized variable: '{desc}' used "
                        f"in function '{func_name}'"
                    )

    # ----------------------------------------------------------------
    #  Symbolic Expression Helpers (preserved from original)
    # ----------------------------------------------------------------

    def _symbolize_condition(self, test_node, current_path):
        """Convierte una condicion AST en una representacion simbolica."""
        if isinstance(test_node, ast.Compare):
            left = self._symbolize_expr(test_node.left, current_path)
            ops = {
                ast.Eq: "==", ast.NotEq: "!=",
                ast.Lt: "<", ast.LtE: "<=",
                ast.Gt: ">", ast.GtE: ">=",
                ast.Is: "is", ast.IsNot: "is_not",
            }
            right_parts = []
            for op, comp in zip(test_node.ops, test_node.comparators):
                op_str = ops.get(type(op), "?")
                right = self._symbolize_expr(comp, current_path)
                right_parts.append(f"{left}{op_str}{right}")
            return "_AND_".join(right_parts)

        elif isinstance(test_node, ast.BoolOp):
            if isinstance(test_node.op, ast.And):
                parts = [self._symbolize_expr(v, current_path) for v in test_node.values]
                return "_AND_".join(parts)
            elif isinstance(test_node.op, ast.Or):
                parts = [self._symbolize_expr(v, current_path) for v in test_node.values]
                return "_OR_".join(parts)

        elif isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
            inner = self._symbolize_expr(test_node.operand, current_path)
            return f"NOT_{inner}"

        elif isinstance(test_node, ast.Name):
            return f"TRUTHY_{test_node.id}"

        return "UNKNOWN_COND"

    def _symbolize_expr(self, node, current_path):
        """Convierte una expresion AST en representacion simbolica."""
        if isinstance(node, ast.Name):
            if node.id in current_path.variables:
                return f"SYM({node.id})"
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            value = self._symbolize_expr(node.value, current_path)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.Call):
            func_name = self._get_call_name(node)
            # Path Pruning: si es I/O, podar
            if func_name in self.IO_OPERATIONS:
                return f"MOCKED_IO({func_name})"
            args = [self._symbolize_expr(a, current_path) for a in node.args]
            return f"{func_name}({', '.join(args)})"
        elif isinstance(node, ast.BinOp):
            left = self._symbolize_expr(node.left, current_path)
            right = self._symbolize_expr(node.right, current_path)
            op_map = {
                ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
                ast.Mod: "%", ast.FloorDiv: "//",
            }
            op_str = op_map.get(type(node.op), "?")
            return f"({left}{op_str}{right})"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            inner = self._symbolize_expr(node.operand, current_path)
            return f"-{inner}"
        elif isinstance(node, ast.Subscript):
            value = self._symbolize_expr(node.value, current_path)
            if isinstance(node.slice, ast.Index):  # Python 3.8 compat
                slice_expr = self._symbolize_expr(node.slice.value, current_path)
            else:
                slice_expr = self._symbolize_expr(node.slice, current_path)
            return f"{value}[{slice_expr}]"
        elif isinstance(node, (ast.List, ast.Tuple)):
            elts = [self._symbolize_expr(e, current_path) for e in node.elts]
            brackets = "[]" if isinstance(node, ast.List) else "()"
            return f"{brackets[0]}{', '.join(elts)}{brackets[1]}"
        return "SYM_EXPR"

    def _get_call_name(self, call_node):
        """Obtiene el nombre de una llamada a funcion."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            if isinstance(call_node.func.value, ast.Name):
                return f"{call_node.func.value.id}.{call_node.func.attr}"
            return call_node.func.attr
        return "unknown_call"

    def _check_io_in_body(self, body, path):
        """Verifica si un bloque contiene I/O y marca el camino como podado."""
        for node in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                base_name = call_name.split('.')[-1] if '.' in call_name else call_name
                if base_name in self.IO_OPERATIONS:
                    path.is_pruned = True
                    # Mockear I/O: agregar variable simbolica
                    path.variables[f"_mocked_{call_name}"] = SymbolicValue(
                        name=f"_mocked_{call_name}",
                        var_type="mocked_io",
                        constraint=lambda x: True  # Asumimos resultado valido
                    )
                    break
        return path

    def _symbolic_regex(self, code, language, target_name):
        """Analisis simbolico simplificado para lenguajes no-Python."""
        # Contar ramas condicionales
        branch_patterns = {
            "kotlin": r'\bif\b|\bwhen\b|\belse\b',
            "go": r'\bif\b|\bswitch\b|\belse\b',
            "javascript": r'\bif\b|\bswitch\b|\belse\b|\?.*:',
            "typescript": r'\bif\b|\bswitch\b|\belse\b|\?.*:',
            "java": r'\bif\b|\bswitch\b|\belse\b',
            "rust": r'\bif\b|\bmatch\b|\belse\b',
        }
        pattern = branch_patterns.get(language, r'\bif\b|\belse\b')
        import re
        branches = len(re.findall(pattern, code))
        estimated_paths = min(2 ** branches, 1000) if branches > 0 else 1

        return {
            "status": "PASS",
            "paths": [],
            "violations": [],
            "warnings": [f"Symbolic execution for {language} uses estimation ({estimated_paths} estimated paths)"],
            "metrics": {
                "paths_explored": estimated_paths,
                "paths_pruned": 0,
                "total_paths": estimated_paths,
                "feasible_paths": estimated_paths,
            }
        }

    # ================================================================
    #  Deep Symbolic Analysis: Counterexample & Test Generation
    # ================================================================

    def generate_concrete_inputs(self, path):
        """
        Generate concrete input values from a Z3 model for a feasible path.

        Given a SymbolicPath with Z3 conditions, uses the Z3 solver to find
        a concrete model (assignment of values to variables) that satisfies
        all path conditions. This produces actual test inputs that would
        exercise this specific execution path.

        Returns:
            dict with:
                - 'inputs': dict of {var_name: concrete_value}
                - 'model_str': human-readable model string
                - 'smt_lib': SMT-LIB2 representation of path conditions
                - 'feasible': bool
                - 'proven_with': 'Z3' or 'STRING_HEURISTIC'
        """
        if not path.z3_conditions and not path.condition:
            return {
                "inputs": {},
                "model_str": "empty_path",
                "smt_lib": "",
                "feasible": True,
                "proven_with": "TRIVIAL",
            }

        if HAS_Z3 and path.z3_conditions:
            return self._generate_z3_concrete_inputs(path)
        return self._generate_heuristic_inputs(path)

    def _generate_z3_concrete_inputs(self, path):
        """
        Use Z3 to find a concrete model satisfying all path conditions.

        Produces actual test inputs and an SMT-LIB2 formula for the path.
        """
        try:
            solver = z3_module.Solver()
            solver.set("timeout", 1000)  # 1s for model generation

            for cond in path.z3_conditions:
                solver.add(cond)

            result = solver.check()

            if result == z3_module.sat:
                model = solver.model()
                inputs = {}
                for var_name, z3_var in self._z3_vars.items():
                    val = model.eval(z3_var, model_completion=True)
                    try:
                        if z3_var.sort() == z3_module.IntSort():
                            inputs[var_name] = val.as_long()
                        elif z3_var.sort() == z3_module.BoolSort():
                            inputs[var_name] = bool(val)
                        elif z3_var.sort() == z3_module.RealSort():
                            dec_str = val.as_decimal(6)
                            inputs[var_name] = float(dec_str.rstrip('0').rstrip('.') if '.' in dec_str else dec_str)
                        else:
                            inputs[var_name] = str(val)
                    except Exception:
                        inputs[var_name] = str(val)

                # Generate SMT-LIB2 representation
                smt_lib = solver.to_smt2()

                return {
                    "inputs": inputs,
                    "model_str": str(model),
                    "smt_lib": smt_lib,
                    "feasible": True,
                    "proven_with": "Z3_SMT",
                }
            elif result == z3_module.unsat:
                return {
                    "inputs": {},
                    "model_str": "UNSAT",
                    "smt_lib": "",
                    "feasible": False,
                    "proven_with": "Z3_SMT",
                }
            else:
                # Timeout or unknown
                return {
                    "inputs": {},
                    "model_str": "UNKNOWN/TIMEOUT",
                    "smt_lib": "",
                    "feasible": None,  # Unknown
                    "proven_with": "Z3_SMT",
                }

        except Exception as e:
            logger.debug("Z3 concrete input generation error: %s", e)
            return {
                "inputs": {},
                "model_str": f"ERROR: {e}",
                "smt_lib": "",
                "feasible": None,
                "proven_with": "Z3_SMT_ERROR",
            }

    def _generate_heuristic_inputs(self, path):
        """
        Fallback: generate approximate inputs from string-based path conditions.

        When Z3 is not available, attempts to extract constraints from the
        string representation of path conditions and produce heuristic inputs.
        """
        inputs = {}
        import re as _re

        for cond in path.condition:
            cond_str = str(cond)
            # Try to extract variable assignments from conditions
            # Pattern: SYM(var) == value
            eq_match = _re.match(r'SYM\((\w+)\)\s*==\s*(\d+)', cond_str)
            if eq_match:
                var_name, value = eq_match.group(1), int(eq_match.group(2))
                inputs[var_name] = value
                continue

            # Pattern: SYM(var) > value
            gt_match = _re.match(r'SYM\((\w+)\)\s*>\s*(\d+)', cond_str)
            if gt_match:
                var_name, value = gt_match.group(1), int(gt_match.group(2))
                inputs[var_name] = value + 1
                continue

            # Pattern: SYM(var) < value
            lt_match = _re.match(r'SYM\((\w+)\)\s*<\s*(\d+)', cond_str)
            if lt_match:
                var_name, value = lt_match.group(1), int(lt_match.group(2))
                inputs[var_name] = value - 1
                continue

            # Pattern: SYM(var) != value
            neq_match = _re.match(r'SYM\((\w+)\)\s*!=\s*(\d+)', cond_str)
            if neq_match:
                var_name, value = neq_match.group(1), int(neq_match.group(2))
                inputs[var_name] = value + 1

        # For variables referenced but not constrained, use default values
        for var_name in path.variables:
            if var_name not in inputs:
                sym_val = path.variables.get(var_name)
                if isinstance(sym_val, SymbolicValue) and sym_val.concrete is not None:
                    inputs[var_name] = sym_val.concrete
                else:
                    inputs[var_name] = 0  # Default concrete value

        return {
            "inputs": inputs,
            "model_str": str(inputs),
            "smt_lib": "",
            "feasible": True,  # Assumed feasible
            "proven_with": "STRING_HEURISTIC",
        }

    def prove_violation_reachable(self, violation, path):
        """
        Use Z3 to formally prove that a detected violation is reachable.

        Given a violation (e.g., "division by zero on var x") and the
        SymbolicPath where it was detected, constructs a Z3 query that
        checks: can the program reach a state where the violation occurs?

        Returns:
            dict with:
                - 'reachable': bool (True if Z3 proves the violation is reachable)
                - 'counterexample': dict of concrete values that trigger the violation
                - 'proof_method': 'Z3_FORMAL' or 'HEURISTIC'
        """
        if not HAS_Z3 or not path.z3_conditions:
            return {
                "reachable": True,  # Assume reachable without Z3
                "counterexample": {},
                "proof_method": "HEURISTIC",
                "note": "Z3 not available - assuming violation is reachable",
            }

        try:
            solver = z3_module.Solver()
            solver.set("timeout", 1000)

            # Add all path conditions (the path to the violation point)
            for cond in path.z3_conditions:
                solver.add(cond)

            # Add the violation condition
            violation_cond = self._violation_to_z3_condition(violation, path)
            if violation_cond is not None:
                solver.add(violation_cond)
            else:
                # Can't encode the violation in Z3 - assume reachable
                return {
                    "reachable": True,
                    "counterexample": {},
                    "proof_method": "HEURISTIC",
                    "note": "Violation could not be encoded in Z3",
                }

            result = solver.check()

            if result == z3_module.sat:
                # Z3 found a concrete input that reaches the violation!
                model = solver.model()
                counterexample = {}
                for var_name, z3_var in self._z3_vars.items():
                    val = model.eval(z3_var, model_completion=True)
                    try:
                        if z3_var.sort() == z3_module.IntSort():
                            counterexample[var_name] = val.as_long()
                        elif z3_var.sort() == z3_module.BoolSort():
                            counterexample[var_name] = bool(val)
                        else:
                            counterexample[var_name] = str(val)
                    except Exception:
                        counterexample[var_name] = str(val)

                return {
                    "reachable": True,
                    "counterexample": counterexample,
                    "proof_method": "Z3_FORMAL",
                    "note": f"Z3 proved violation is reachable with inputs: {counterexample}",
                }
            elif result == z3_module.unsat:
                # Z3 proved the violation is NOT reachable under these path conditions
                return {
                    "reachable": False,
                    "counterexample": {},
                    "proof_method": "Z3_FORMAL",
                    "note": "Z3 proved violation is unreachable (path conditions prevent it)",
                }
            else:
                return {
                    "reachable": None,  # Unknown
                    "counterexample": {},
                    "proof_method": "Z3_FORMAL",
                    "note": "Z3 returned unknown/timeout - reachability undetermined",
                }

        except Exception as e:
            logger.debug("Z3 violation reachability proof error: %s", e)
            return {
                "reachable": True,
                "counterexample": {},
                "proof_method": "HEURISTIC",
                "note": f"Z3 error: {e}",
            }

    def _violation_to_z3_condition(self, violation, path):
        """
        Convert a violation string to a Z3 constraint that encodes
        the violation condition.

        Supported violation types:
        - "division by zero" on var X -> z3_var == 0
        - "None dereference" on var X -> z3_var == 0 (0 encodes None)
        - "index out of bounds" on var X -> z3_var < 0
        """
        import re as _re

        # Extract variable name from violation string
        var_match = _re.search(r"'(\w+)'", violation)
        if not var_match:
            return None

        var_name = var_match.group(1)
        z3_var = self._get_or_create_z3_var(var_name, "int")
        if z3_var is None:
            return None

        if "division by zero" in violation.lower():
            return z3_var == 0
        elif "none dereference" in violation.lower():
            return z3_var == 0
        elif "index out of bounds" in violation.lower() or "negative" in violation.lower():
            return z3_var < 0
        elif "type mismatch" in violation.lower():
            # Can't easily encode type violations as Z3 constraints
            return None

        return None

    def export_path_conditions_smt(self, paths, func_name=""):
        """
        Export all path conditions as SMT-LIB2 formulas for external analysis.

        This enables:
        - Offline verification with other SMT solvers
        - Integration with verification pipelines
        - Human-readable proof artifacts

        Returns:
            list of dicts, each with:
                - 'path_index': int
                - 'conditions': list of string conditions
                - 'smt_lib': SMT-LIB2 formula string (if Z3 available)
                - 'feasible': bool
                - 'concrete_inputs': dict of test inputs (if Z3 available)
        """
        exported = []

        for i, path in enumerate(paths):
            entry = {
                "path_index": i,
                "function": func_name,
                "conditions": [str(c) for c in path.condition],
                "feasible": path.is_feasible(),
                "is_pruned": path.is_pruned,
                "assignments": [(name, str(desc)) for name, desc in path.assignments],
                "return_values": path.return_values,
                "smt_lib": "",
                "concrete_inputs": {},
            }

            if HAS_Z3 and path.z3_conditions:
                try:
                    solver = z3_module.Solver()
                    solver.set("timeout", 500)
                    for cond in path.z3_conditions:
                        solver.add(cond)
                    entry["smt_lib"] = solver.to_smt2()

                    # Try to generate concrete test inputs
                    if solver.check() == z3_module.sat:
                        model = solver.model()
                        for var_name, z3_var in self._z3_vars.items():
                            val = model.eval(z3_var, model_completion=True)
                            try:
                                if z3_var.sort() == z3_module.IntSort():
                                    entry["concrete_inputs"][var_name] = val.as_long()
                                else:
                                    entry["concrete_inputs"][var_name] = str(val)
                            except Exception:
                                entry["concrete_inputs"][var_name] = str(val)
                except Exception as export_err:
                    logger.debug(f"SymbolicExecutor: Path export failed: {export_err}")

            exported.append(entry)

        return exported
