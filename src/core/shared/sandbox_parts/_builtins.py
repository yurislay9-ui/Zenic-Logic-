"""
Restricted builtins and sandbox globals for safe execution.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ._workspace import SandboxWorkspace


def create_sandbox_builtins(workspace: SandboxWorkspace) -> dict:
    """
    Crea un diccionario de builtins restringidos para ejecucion en sandbox.

    Garantias de seguridad:
    - NO hay acceso a os.system, subprocess, eval, exec, __import__
    - open() solo puede escribir/leer DENTRO del workspace
    - NO hay acceso al filesystem fuera del workspace
    - Las operaciones de archivo se redirigen al workspace aislado
    """
    # open() restringido que solo opera dentro del workspace
    def _sandbox_open(filepath, mode='r', *args, **kwargs):
        """open() restringido: solo permite acceso dentro del workspace."""
        # Resolver la ruta absoluta
        path = Path(filepath)

        # Si es relativa, resolverla contra el workspace
        if not path.is_absolute():
            path = workspace.projects_dir / filepath

        # Verificar que la ruta resolve esta DENTRO del workspace
        try:
            resolved = path.resolve()
            workspace_resolved = workspace.workspace_dir.resolve()
            if not resolved.is_relative_to(workspace_resolved):
                raise PermissionError(
                    f"Sandbox: acceso denegado a '{filepath}'. "
                    f"Solo se permite acceso dentro del workspace aislado."
                )
        except (OSError, ValueError):
            raise PermissionError(
                f"Sandbox: ruta invalida '{filepath}'."
            )

        # Si es escritura, asegurar que el directorio existe
        if 'w' in mode or 'a' in mode:
            path.parent.mkdir(parents=True, exist_ok=True)

        return open(resolved, mode, *args, **kwargs)

    # __import__ restringido: solo permite modulos seguros
    _SAFE_MODULES = {
        'math', 'random', 'string', 'collections', 'itertools',
        'functools', 'operator', 'typing', 'enum', 'dataclasses',
        'abc', 'copy', 're', 'json', 'decimal', 'fractions',
        'statistics', 'datetime', 'time', 'hashlib', 'base64',
        'struct', 'pprint', 'textwrap',
        'collections.abc',
    }

    def _sandbox_import(name, *args, **kwargs):
        """__import__ restringido: solo modulos seguros permitidos."""
        base_name = name.split('.')[0]
        if base_name not in _SAFE_MODULES:
            raise ImportError(
                f"Sandbox: importacion de '{name}' bloqueada. "
                f"Solo se permiten modulos seguros: {sorted(_SAFE_MODULES)}"
            )
        return __import__(name, *args, **kwargs)

    # Construir diccionario de builtins
    safe_builtins = {
        # I/O restringido
        'open': _sandbox_open,
        'print': lambda *a, **kw: None,  # Mocked: no side effects

        # Tipos basicos
        'bool': bool, 'int': int, 'float': float, 'str': str,
        'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
        'bytes': bytes, 'bytearray': bytearray, 'frozenset': frozenset,
        'complex': complex, 'range': range, 'type': type,
        'slice': slice, 'object': object, 'memoryview': memoryview,

        # Funciones builtins seguras
        'len': len, 'abs': abs, 'min': min, 'max': max, 'sum': sum,
        'round': round, 'pow': pow, 'divmod': divmod,
        'sorted': sorted, 'reversed': reversed, 'enumerate': enumerate,
        'zip': zip, 'map': map, 'filter': filter, 'all': all, 'any': any,
        'chr': chr, 'ord': ord, 'hex': hex, 'oct': oct, 'bin': bin,
        'format': format, 'repr': repr, 'ascii': ascii,
        'isinstance': isinstance, 'issubclass': issubclass,
        'hasattr': hasattr, 'getattr': getattr, 'setattr': setattr,
        'delattr': delattr, 'dir': dir, 'vars': vars,
        'callable': callable, 'hash': hash, 'id': id,
        'iter': iter, 'next': next, 'super': super,
        'property': property, 'classmethod': classmethod,
        'staticmethod': staticmethod,

        # Excepciones permitidas
        'Exception': Exception, 'ValueError': ValueError,
        'TypeError': TypeError, 'KeyError': KeyError,
        'AttributeError': AttributeError, 'IndexError': IndexError,
        'RuntimeError': RuntimeError, 'StopIteration': StopIteration,
        'NotImplementedError': NotImplementedError,
        'ZeroDivisionError': ZeroDivisionError,
        'OverflowError': OverflowError,
        'AssertionError': AssertionError,
        'LookupError': LookupError, 'IOError': IOError,
        'OSError': OSError, 'FileNotFoundError': FileNotFoundError,
        'PermissionError': PermissionError,
        'ArithmeticError': ArithmeticError,
        'BufferError': BufferError,

        # Constantes
        'True': True, 'False': False, 'None': None,
        'NotImplemented': NotImplemented, 'Ellipsis': Ellipsis,

        # Importacion restringida
        '__import__': _sandbox_import,

        # SECURITY: Explicitly block dangerous builtins even if referenced
        'eval': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: eval() is blocked for security")),
        'exec': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: exec() is blocked for security")),
        'compile': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: compile() is blocked for security")),
        'breakpoint': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: breakpoint() is blocked for security")),
        'input': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: input() is blocked for security")),
        'exit': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: exit() is blocked for security")),
        'quit': lambda *a, **kw: (_ for _ in ()).throw(
            ImportError("Sandbox: quit() is blocked for security")),
        'globals': lambda *a, **kw: {},
        'locals': lambda *a, **kw: {},
    }

    return safe_builtins


def create_sandbox_globals(workspace: SandboxWorkspace,
                           extra_globals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Crea el diccionario de globals para ejecucion segura en sandbox.

    Args:
        workspace: Workspace aislado donde se ejecuta el codigo.
        extra_globals: Variables adicionales a inyectar.

    Returns:
        Dict listo para usar como segundo argumento de exec().
    """
    safe_builtins = create_sandbox_builtins(workspace)

    sandbox_globals = {
        "__builtins__": safe_builtins,
        "__name__": "__sandbox__",
        "__file__": str(workspace.code_dir / "sandbox_code.py"),
        "__doc__": None,
    }

    # Agregar globals extra si se proporcionan
    if extra_globals:
        # Filtrar globals peligrosas
        dangerous_keys = {
            'os', 'sys', 'subprocess', 'shutil', 'signal',
            'socket', 'http', 'urllib', 'requests',
            'ctypes', 'multiprocessing', 'threading',
            'pickle', 'shelve', 'marshal',
        }
        for key, value in extra_globals.items():
            if key not in dangerous_keys:
                sandbox_globals[key] = value

    return sandbox_globals
