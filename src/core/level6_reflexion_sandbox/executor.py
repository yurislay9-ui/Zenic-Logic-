"""
TITAN OMNISCALE X - Reflexion Sandbox v13 (Symbolic Execution Real)

Sandbox con ejecucion simbolica acotada real, timeout real, K-Path limiting
basado en grafo de dependencias, y path pruning para I/O.

MEJORAS v13:
- Ejecucion Simbolica Acotada real (SymbolicExecutor)
- K-Paths medidos desde el grafo AST (KPathAnalyzer)
- Path Pruning de side effects con Mocks
- Timeout enforcement real via threading
- Configuracion desde YAML

Sin dependencias externas obligatorias. Compatible con Android.
"""

import ast
import re
import time
import logging
from src.core.shared.contracts import (
    SandboxResult, TimeoutEnforcer, SymbolicExecutor, KPathAnalyzer
)
from src.config.loader import load_settings, get_sandbox_timeout_s, get_k_path_limit

logger = logging.getLogger(__name__)


class ReflexionSandbox:
    """
    Sandbox con ejecucion simbolica real, timeout real y K-Path limiting.

    Implementa el Nivel 6 del documento de arquitectura:
    - Ejecucion Simbolica Acotada (estados simbolicos + path conditions)
    - K-Paths de radio configurable (default 10) desde el grafo AST
    - Path Pruning de side effects (I/O -> Mock)
    - Timeout enforcement real via threading
    - Ejecucion segura con builtins restringidos
    """

    def __init__(self, timeout_seconds=None, k_path_limit=None):
        self.settings = load_settings()
        self.timeout_seconds = timeout_seconds or get_sandbox_timeout_s(self.settings)
        self.k_path_limit = k_path_limit or get_k_path_limit(self.settings)
        self._enforcer = TimeoutEnforcer(timeout_ms=self.timeout_seconds * 1000)
        self._symbolic_executor = SymbolicExecutor(
            k_path_limit=self.k_path_limit,
            max_depth=20
        )
        self._kpath_analyzer = KPathAnalyzer(k_limit=self.k_path_limit)

        logger.info("ReflexionSandbox: timeout=%ds, k_path_limit=%d",
                     self.timeout_seconds, self.k_path_limit)

    async def validate_code(self, code, language, target_name):
        """Valida codigo con ejecucion simbolica real y analisis de caminos."""
        if language == "python":
            return self._validate_python(code, target_name)
        return self._validate_other(code, language, target_name)

    def _validate_python(self, code, target_name):
        """Validacion completa de codigo Python con ejecucion simbolica."""
        # Fase 1: Parseo AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return SandboxResult(
                status="FAIL_SYNTAX",
                error_message=f"Syntax error line {e.lineno}: {e.msg}",
                error_node={"line": e.lineno, "offset": e.offset}
            )

        warnings = []
        metrics = {"functions": 0, "classes": 0, "max_complexity": 0,
                   "imports": 0, "calls": 0}
        paths_explored = 0
        paths_pruned = 0

        # Fase 2: Analisis estructural
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                metrics["functions"] += 1
                complexity = self._cyclomatic(node)
                metrics["max_complexity"] = max(metrics["max_complexity"], complexity)
                if complexity > 10:
                    warnings.append(
                        f"Function '{node.name}' has complexity {complexity} (>10). "
                        f"Consider refactoring."
                    )
            elif isinstance(node, ast.ClassDef):
                metrics["classes"] += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                metrics["imports"] += 1
            elif isinstance(node, ast.Call):
                metrics["calls"] += 1

        # Fase 3: Ejecucion Simbolica Acotada Real
        symbolic_result = self._symbolic_executor.execute_symbolic(
            code, "python", target_name
        )

        paths_explored = symbolic_result["metrics"]["paths_explored"]
        paths_pruned = symbolic_result["metrics"]["paths_pruned"]
        metrics["k_paths"] = paths_explored
        metrics["feasible_paths"] = symbolic_result["metrics"].get("feasible_paths", 0)
        metrics["io_calls"] = paths_pruned

        # Agregar violaciones simbolicas como warnings
        for violation in symbolic_result.get("violations", []):
            warnings.append(f"Symbolic: {violation}")

        # Fase 4: Deteccion de side effects (I/O) - Path Pruning
        io_calls = self._detect_io_calls(tree)
        for call in io_calls:
            if not any(f"I/O side-effect" in w for w in warnings):
                warnings.append(f"I/O side-effect detected: {call} (mocked in execution)")
            paths_pruned += len(io_calls)

        # Fase 5: Deteccion de llamadas peligrosas
        dangerous_calls = self._detect_dangerous(tree)
        for call in dangerous_calls:
            warnings.append(f"Potentially dangerous operation: {call}")

        # Fase 6: K-Path check usando grafo de dependencias real
        kpath_result = self._kpath_analyzer.measure_dependency_depth(target_name)
        if kpath_result["exceeds_limit"]:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({kpath_result['nodes_affected']} nodes affected, "
                    f"depth {kpath_result['depth']}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Si no hay grafo en SQLite, usar la estimacion del codigo
        if kpath_result["nodes_affected"] == 0 and paths_explored > self.k_path_limit:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({paths_explored}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Fase 7: Ejecucion segura con timeout real
        if not dangerous_calls:
            exec_result, timed_out = self._enforcer.execute_with_timeout(
                self._safe_exec, code, target_name
            )
            if timed_out:
                return SandboxResult(
                    status="FAIL_TIMEOUT",
                    error_message=(
                        f"Execution exceeded timeout ({self.timeout_seconds}s). "
                        f"Code may contain infinite loops or excessive computation."
                    ),
                    warnings=warnings,
                    metrics=metrics,
                    paths_explored=paths_explored,
                    paths_pruned=paths_pruned
                )
            if exec_result and exec_result.get("error"):
                return SandboxResult(
                    status="FAIL_RUNTIME",
                    error_message=exec_result["error"],
                    warnings=warnings,
                    metrics=metrics,
                    paths_explored=paths_explored,
                    paths_pruned=paths_pruned
                )

        # Agregar info de la ejecucion simbolica al resultado
        metrics["symbolic_paths"] = len(symbolic_result.get("paths", []))
        metrics["symbolic_violations"] = len(symbolic_result.get("violations", []))

        return SandboxResult(
            status="PASS",
            warnings=warnings,
            metrics=metrics,
            paths_explored=paths_explored,
            paths_pruned=paths_pruned
        )

    def _validate_other(self, code, language, target_name):
        """Validacion basica para lenguajes no-Python."""
        if not code.strip():
            return SandboxResult(status="FAIL_SYNTAX", error_message="Empty code")

        warnings = []
        # Verificar balance de delimitadores
        for open_ch, close_ch in [('{', '}'), ('(', ')'), ('[', ']')]:
            opens = code.count(open_ch)
            closes = code.count(close_ch)
            if opens != closes:
                return SandboxResult(
                    status="FAIL_SYNTAX",
                    error_message=f"Unbalanced '{open_ch}'={opens}, '{close_ch}'={closes}"
                )

        # Ejecucion simbolica simplificada para otros lenguajes
        symbolic_result = self._symbolic_executor.execute_symbolic(
            code, language, target_name
        )

        paths_explored = symbolic_result["metrics"]["paths_explored"]
        paths_pruned = symbolic_result["metrics"]["paths_pruned"]

        if paths_explored > self.k_path_limit:
            return SandboxResult(
                status="FAIL_K_PATH",
                error_message=(
                    f"K-Paths ({paths_explored}) exceeds limit ({self.k_path_limit}). "
                    f"Subdivide operation into smaller units."
                ),
                warnings=warnings + symbolic_result.get("warnings", []),
                metrics={"k_paths": paths_explored},
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        # Verificar que hay al menos una definicion
        patterns = {
            "kotlin": r'(?:fun|class)\s+\w+',
            "go": r'func\s+\w+',
            "javascript": r'(?:function|class|const|let)\s+\w+',
            "typescript": r'(?:function|class|const|let)\s+\w+',
            "java": r'(?:public|private|protected)\s+(?:static\s+)?(?:class|void)\s+\w+',
            "rust": r'(?:pub\s+)?fn\s+\w+',
        }
        pattern = patterns.get(language, r'(?:def|function|fun|func)\s+\w+')
        if not re.search(pattern, code):
            warnings.append("No function/class definitions found in code")

        return SandboxResult(
            status="PASS",
            warnings=warnings + symbolic_result.get("warnings", []),
            metrics={"k_paths": paths_explored},
            paths_explored=paths_explored,
            paths_pruned=paths_pruned
        )

    def _cyclomatic(self, func_node):
        """Calcula la complejidad ciclomatica de una funcion."""
        complexity = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        return complexity

    def _detect_io_calls(self, tree):
        """Detecta llamadas I/O que deben ser mockeadas (Path Pruning)."""
        io_call_names = {
            "open", "read", "write", "input", "print",
            "fetch", "requests.get", "requests.post", "urlopen",
            "socket.connect", "http", "urllib", "aiohttp",
            "db.execute", "cursor.execute", "session.query",
            "redis.get", "redis.set", "cache.get", "cache.set"
        }
        io_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in io_call_names:
                    io_calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    full = f"{node.func.value.id}.{node.func.attr}" if isinstance(node.func.value, ast.Name) else node.func.attr
                    if full in io_call_names or node.func.attr in io_call_names:
                        io_calls.append(full)
        return list(set(io_calls))

    def _detect_dangerous(self, tree):
        """Detecta llamadas potencialmente peligrosas."""
        dangerous_names = {
            "eval", "exec", "compile", "__import__",
            "os.system", "os.popen", "subprocess.call", "subprocess.run",
            "shutil.rmtree", "os.remove", "os.unlink"
        }
        dangerous = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_names:
                    dangerous.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    full = f"{node.func.value.id}.{node.func.attr}" if isinstance(node.func.value, ast.Name) else node.func.attr
                    if full in dangerous_names or node.func.attr in dangerous_names:
                        dangerous.append(full)
        return list(set(dangerous))

    def _safe_exec(self, code, target_name):
        """Ejecuta codigo en un entorno sandbox con builtins restringidos."""
        safe_builtins = {
            'print': lambda *a, **kw: None,  # Mocked I/O (Path Pruning)
            'len': len, 'range': range, 'enumerate': enumerate,
            'str': str, 'int': int, 'float': float, 'bool': bool, 'list': list,
            'dict': dict, 'set': set, 'tuple': tuple, 'type': type,
            'isinstance': isinstance, 'hasattr': hasattr, 'getattr': getattr,
            'setattr': setattr, 'sorted': sorted, 'reversed': reversed,
            'zip': zip, 'map': map, 'filter': filter, 'sum': sum,
            'min': min, 'max': max, 'abs': abs, 'round': round,
            'any': any, 'all': all,
            'open': lambda *a, **kw: None,  # Mocked I/O (Path Pruning)
            'True': True, 'False': False, 'None': None,
            'Exception': Exception, 'ValueError': ValueError,
            'TypeError': TypeError, 'KeyError': KeyError,
            'AttributeError': AttributeError, 'IndexError': IndexError,
        }
        sandbox_globals = {"__builtins__": safe_builtins, "__name__": "__sandbox__"}
        try:
            exec(compile(code, target_name, 'exec'), sandbox_globals)
            return {}
        except Exception as e:
            return {"error": f"Runtime error: {type(e).__name__}: {str(e)}"}
