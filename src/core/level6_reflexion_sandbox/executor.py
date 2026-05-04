"""
TITAN OMNISCALE X - Reflexion Sandbox v16 (Isolated + Symbolic Execution)

Sandbox con ejecucion simbolica acotada real, timeout real, K-Path limiting
basado en grafo de dependencias, y path pruning para I/O.

MEJORAS v16 - AISLAMIENTO COMPLETO:
- Workspace aislado: el sandbox NUNCA toca archivos del proyecto
- Builtins restringidos con open() que solo escribe dentro del workspace
- __import__ restringido: solo modulos seguros permitidos
- DBs del sandbox son INDEPENDIENTES de las del sistema
- Cleanup automatico de workspaces expirados
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
from src.core.shared.sandbox_isolation import (
    get_isolation_manager, create_sandbox_globals, SandboxWorkspace
)
from src.config.loader import load_settings, get_sandbox_timeout_s, get_k_path_limit

logger = logging.getLogger(__name__)


class ReflexionSandbox:
    """
    Sandbox con ejecucion simbolica real, timeout real y K-Path limiting.
    TODO el codigo se ejecuta en un workspace AISLADO separado del proyecto.

    Implementa el Nivel 6 del documento de arquitectura:
    - AISLAMIENTO: Workspace separado, sin acceso al filesystem del proyecto
    - Ejecucion Simbolica Acotada (estados simbolicos + path conditions)
    - K-Paths de radio configurable (default 10) desde el grafo AST
    - Path Pruning de side effects (I/O -> Mock)
    - Timeout enforcement real via threading
    - Ejecucion segura con builtins restringidos y open() sandboxed
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

        # Sistema de aislamiento
        self._isolation_manager = get_isolation_manager()

        logger.info("ReflexionSandbox: timeout=%ds, k_path_limit=%d, ISOLATED=True",
                     self.timeout_seconds, self.k_path_limit)

    async def validate_code(self, code, language, target_name):
        """Valida codigo con ejecucion simbolica real y analisis de caminos."""
        if language == "python":
            return self._validate_python(code, target_name)
        return self._validate_other(code, language, target_name)

    def _validate_python(self, code, target_name):
        """Validacion completa de codigo Python con ejecucion simbolica AISLADA."""
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
        # NUEVA MEJORA: Probar formalmente con Z3 si las violaciones son alcanzables
        for violation in symbolic_result.get("violations", []):
            # Try to prove the violation is reachable using Z3
            proven_reachable = False
            for path in symbolic_result.get("paths", []):
                reachability = self._symbolic_executor.prove_violation_reachable(
                    violation, path
                )
                if reachability.get("reachable") is True:
                    counterexample = reachability.get("counterexample", {})
                    if counterexample:
                        warnings.append(
                            f"Symbolic (Z3 PROVEN): {violation} "
                            f"[counterexample: {counterexample}]"
                        )
                    else:
                        warnings.append(f"Symbolic (Z3 PROVEN): {violation}")
                    proven_reachable = True
                    break
                elif reachability.get("reachable") is False:
                    # Z3 proved the violation is NOT reachable - skip it
                    continue
            if not proven_reachable:
                warnings.append(f"Symbolic: {violation}")

        # NUEVA MEJORA: Generar test inputs concretos para cada path factible
        concrete_test_inputs = []
        for path in symbolic_result.get("paths", []):
            if path.is_feasible() and not path.is_pruned:
                inputs_result = self._symbolic_executor.generate_concrete_inputs(path)
                if inputs_result.get("inputs"):
                    concrete_test_inputs.append(inputs_result["inputs"])

        if concrete_test_inputs:
            metrics["concrete_test_inputs"] = len(concrete_test_inputs)
            metrics["test_inputs_sample"] = concrete_test_inputs[:3]  # First 3 samples

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

        # Fase 7: Ejecucion segura AISLADA con timeout real
        if dangerous_calls:
            # Dangerous code detected — do NOT execute, return FAIL status
            warnings.append(f"Dangerous calls detected: {', '.join(dangerous_calls)}. Execution blocked.")
            return SandboxResult(
                status="FAIL_DANGEROUS",
                error_message=(
                    f"Dangerous code patterns detected: {', '.join(dangerous_calls)}. "
                    f"Execution blocked for safety. Remove or refactor these calls."
                ),
                warnings=warnings,
                metrics=metrics,
                paths_explored=paths_explored,
                paths_pruned=paths_pruned
            )

        exec_result, timed_out = self._enforcer.execute_with_timeout(
            self._isolated_exec, code, target_name
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
        metrics["sandbox_isolated"] = True

        # NUEVA MEJORA: Exportar path conditions como SMT-LIB2 para analisis externo
        if symbolic_result.get("paths"):
            smt_export = self._symbolic_executor.export_path_conditions_smt(
                symbolic_result["paths"], target_name
            )
            metrics["smt_path_count"] = len(smt_export)
            # Store SMT formulas (truncated for metrics, full export available via API)
            metrics["smt_paths_available"] = True

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
            metrics={"k_paths": paths_explored, "sandbox_isolated": True},
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

    def _isolated_exec(self, code, target_name):
        """
        Ejecuta codigo en un workspace AISLADO con builtins restringidos.

        El codigo se ejecuta en un directorio separado donde:
        - open() solo puede escribir/leer DENTRO del workspace
        - __import__ solo permite modulos seguros (math, json, etc.)
        - NO hay acceso al filesystem del proyecto
        - NO hay acceso a os, subprocess, shutil, etc.
        - El workspace se limpia automaticamente al terminar

        SECURITY: Pre-validates AST to block dangerous constructs before exec.
        """
        # SECURITY: Pre-validate AST — block dangerous constructs before execution
        try:
            tree = ast.parse(code, filename=target_name)
            dangerous_attrs = {
                '__class__', '__bases__', '__subclasses__', '__mro__',
                '__globals__', '__code__', '__closure__', '__func__',
                '__self__', '__dict__', '__weakref__',
                '__builtins__', '__import__',
            }
            for node in ast.walk(tree):
                # Block attribute access to dunder attributes (sandbox escape vectors)
                if isinstance(node, ast.Attribute):
                    if node.attr.startswith('__') and node.attr.endswith('__'):
                        if node.attr in dangerous_attrs:
                            raise ImportError(
                                f"Sandbox: access to '{node.attr}' is blocked "
                                f"for security (line {node.lineno})"
                            )
                # Block getattr/hasattr with dunder string literals
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ('getattr', 'hasattr'):
                        if node.args and len(node.args) >= 2:
                            arg = node.args[1]
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                if arg.value.startswith('__') and arg.value.endswith('__'):
                                    if arg.value in dangerous_attrs:
                                        raise ImportError(
                                            f"Sandbox: getattr/hasattr access to "
                                            f"'{arg.value}' is blocked for security"
                                        )
        except SyntaxError as e:
            return {"error": f"Sandbox: syntax error in code: {e}"}
        except ImportError as e:
            return {"error": str(e)}

        workspace = None
        try:
            # Crear workspace aislado para esta ejecucion
            workspace = self._isolation_manager.create_workspace(
                ttl_seconds=self.timeout_seconds * 2 + 60  # TTL > timeout
            )

            # Escribir codigo en el workspace aislado
            workspace.write_code(code, filename=f"{target_name}")

            # Crear globals con builtins restringidos que operan dentro del workspace
            sandbox_globals = create_sandbox_globals(workspace)

            # Log de ejecucion
            workspace.write_log(
                f"Exec started: target={target_name}, "
                f"code_size={len(code)} bytes, "
                f"workspace={workspace.sandbox_id}"
            )

            # Ejecutar codigo compilado en el workspace aislado
            compiled = compile(code, str(workspace.code_dir / target_name), 'exec')
            exec(compiled, sandbox_globals)

            # Log de exito
            workspace.write_log(f"Exec completed successfully: target={target_name}")

            return {}

        except PermissionError as e:
            # El codigo intento acceder fuera del workspace
            logger.warning("Sandbox bloqueo acceso ilegal: %s", e)
            return {"error": f"Sandbox security: {str(e)}"}

        except ImportError as e:
            # El codigo intento importar un modulo bloqueado
            logger.warning("Sandbox bloqueo import ilegal: %s", e)
            return {"error": f"Sandbox import blocked: {str(e)}"}

        except Exception as e:
            return {"error": f"Runtime error: {type(e).__name__}: {str(e)}"}

        finally:
            # Liberar workspace (se limpia del disco)
            if workspace:
                try:
                    self._isolation_manager.release_workspace(workspace.sandbox_id)
                except Exception as e:
                    logger.warning("Error liberando workspace %s: %s",
                                   workspace.sandbox_id, e)
