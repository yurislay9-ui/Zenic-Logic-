"""Mixin: Isolated execution for ReflexionSandbox."""

import ast

from ._imports import logger, create_sandbox_globals


class IsolatedExecMixin:
    """Mixin providing isolated code execution within a sandbox workspace."""

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
