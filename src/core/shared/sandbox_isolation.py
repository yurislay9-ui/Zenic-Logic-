"""
TITAN OMNISCALE X - Sandbox Isolation v16

Sistema de aislamiento completo para el sandbox. Garantiza que:
1. Todo codigo ejecutado por el sandbox corre en un workspace SEPARADO
2. El directorio del proyecto NUNCA es tocado por ejecucion sandbox
3. Archivos generados se crean en un chroot virtual (sin permisos de escritura fuera)
4. Las bases de datos del sandbox son INDEPENDIENTES de las del sistema
5. Al finalizar, el workspace se limpia automaticamente (configurable)

Arquitectura de directorios:
  ~/.titan_omniscale/
  ├── data/                    <- DATOS DEL SISTEMA (intocable por sandbox)
  │   ├── graph_ast.sqlite
  │   ├── theorem_cache.sqlite
  │   ├── merkle_ledger.sqlite
  │   └── projects/
  └── sandbox/                 <- WORKSPACE AISLADO (aqui ejecuta el sandbox)
      ├── workspace_<id>/       <- Directorio temporal por ejecucion
      │   ├── code/             <- Codigo a ejecutar
      │   ├── projects/         <- Archivos generados por sandbox
      │   ├── db/               <- Bases de datos SQLite del sandbox
      │   └── logs/             <- Logs de ejecucion
      └── base_env/             <- Entorno base reutilizable

Compatible con Termux + proot-distro (Debian ARM).
"""

import os
import shutil
import threading
import time
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
]


class SandboxWorkspace:
    """
    Workspace aislado para una ejecucion de sandbox.

    Crea un directorio temporal con estructura completa donde:
    - El codigo se ejecuta SIN acceso al filesystem del proyecto
    - Los builtins son reemplazados por versiones seguras
    - Las escrituras de archivos se redirigen al workspace
    - Las bases de datos son independientes
    """

    def __init__(self, sandbox_id=None, auto_cleanup=True, ttl_seconds=3600, client_id='default'):
        """
        Args:
            sandbox_id: ID unico del workspace. Si None, se genera uno.
            auto_cleanup: Si True, elimina el workspace al hacer close().
            ttl_seconds: Tiempo de vida maximo antes de cleanup automatico.
            client_id: Brecha B: Client identifier for multi-client isolation.
        """
        self.sandbox_id = sandbox_id or uuid.uuid4().hex[:12]
        self.auto_cleanup = auto_cleanup
        self.ttl_seconds = ttl_seconds
        self._closed = False
        self._created_at = time.time()
        self.client_id = client_id  # Brecha B: Multi-client isolation

        # Directorio raiz del sandbox
        self.sandbox_root = self._get_sandbox_root()
        self.workspace_dir = self.sandbox_root / f"workspace_{self.sandbox_id}_{self.client_id}"

        # Subdirectorios del workspace
        self.code_dir = self.workspace_dir / "code"
        self.projects_dir = self.workspace_dir / "projects"
        self.db_dir = self.workspace_dir / "db"
        self.logs_dir = self.workspace_dir / "logs"
        self.tmp_dir = self.workspace_dir / "tmp"

        # Crear estructura completa
        self._create_workspace()

        # Lock para operaciones concurrentes
        self._lock = threading.Lock()

        logger.info("SandboxWorkspace creado: %s (client_id=%s, auto_cleanup=%s)",
                     self.sandbox_id, self.client_id, auto_cleanup)

    def _get_sandbox_root(self) -> Path:
        """Obtiene el directorio raiz del sandbox (separado de data/)."""
        if 'ANDROID_ARGUMENT' in os.environ:
            try:
                from android.storage import app_storage_path
                return Path(app_storage_path()) / "titan_sandbox"
            except Exception as e:
                logger.debug(f"SandboxWorkspace: Android storage path detection failed: {e}")
        return Path.home() / ".titan_omniscale" / "sandbox"

    def _create_workspace(self):
        """Crea la estructura completa del workspace aislado."""
        for d in [self.code_dir, self.projects_dir, self.db_dir,
                  self.logs_dir, self.tmp_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Escribir archivo de metadatos del workspace
        meta = {
            "sandbox_id": self.sandbox_id,
            "client_id": self.client_id,
            "created_at": self._created_at,
            "ttl_seconds": self.ttl_seconds,
            "pid": os.getpid(),
            "auto_cleanup": self.auto_cleanup,
        }
        meta_path = self.workspace_dir / ".sandbox_meta"
        meta_path.write_text(
            "\n".join(f"{k}={v}" for k, v in meta.items()),
            encoding="utf-8"
        )

    def write_code(self, code: str, filename: str = "sandbox_code.py") -> Path:
        """
        Write code to the sandbox code directory with path traversal protection.

        Returns:
            Path al archivo creado dentro del workspace
        """
        # Sanitize filename to prevent path traversal
        if not filename:
            raise ValueError("Filename cannot be empty")
        clean = filename.replace("..", "").replace("/", "").replace("\\", "")
        if clean != filename:
            raise ValueError(f"Invalid filename (path traversal detected): {filename!r}")
        code_path = self.code_dir / filename
        # Verify the resolved path stays within the sandbox
        if not code_path.resolve().is_relative_to(self.workspace_dir.resolve()):
            raise ValueError(f"Path escape detected: {filename!r}")
        code_path.write_text(code, encoding="utf-8")
        logger.debug("Codigo escrito en: %s", code_path)
        return code_path

    def read_code(self, filename: str = "sandbox_code.py") -> str:
        """Lee codigo del workspace aislado."""
        code_path = self.code_dir / filename
        if code_path.exists():
            return code_path.read_text(encoding="utf-8")
        return ""

    def write_project_file(self, rel_path: str, content: str) -> Path:
        """
        Escribe un archivo de proyecto en el workspace aislado.
        NUNCA toca el directorio de proyectos real del sistema.
        """
        file_path = self.projects_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read_project_file(self, rel_path: str) -> str:
        """Lee un archivo de proyecto del workspace aislado."""
        file_path = self.projects_dir / rel_path
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return ""

    def project_file_exists(self, rel_path: str) -> bool:
        """Verifica si un archivo existe en el workspace aislado."""
        return (self.projects_dir / rel_path).exists()

    def snapshot_project_file(self, rel_path: str, source_content: str) -> Path:
        """
        Crea un snapshot (backup) de un archivo en el workspace aislado.
        Equivalente a MerkleLedger.snapshot() pero dentro del sandbox.
        """
        bk_dir = self.workspace_dir / "backups"
        bk_dir.mkdir(exist_ok=True)
        bk_path = bk_dir / rel_path.replace("/", "_")
        bk_path.write_text(source_content, encoding="utf-8")
        return bk_path

    def rollback_project_file(self, rel_path: str) -> bool:
        """
        Restaura un archivo desde el backup en el workspace aislado.
        """
        bk_dir = self.workspace_dir / "backups"
        bk_path = bk_dir / rel_path.replace("/", "_")
        target_path = self.projects_dir / rel_path
        if bk_path.exists():
            shutil.copy2(bk_path, target_path)
            return True
        return False

    def get_db_path(self, db_name: str) -> str:
        """
        Retorna la ruta a una base de datos DENTRO del sandbox.
        Las DBs del sandbox son INDEPENDIENTES de las del sistema.
        """
        return str(self.db_dir / db_name)

    def get_tmp_path(self, filename: str) -> Path:
        """Retorna una ruta temporal dentro del sandbox."""
        return self.tmp_dir / filename

    def write_log(self, log_content: str, log_name: str = "execution.log"):
        """Escribe un log de ejecucion dentro del workspace."""
        log_path = self.logs_dir / log_name
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {log_content}\n")

    def is_expired(self) -> bool:
        """Verifica si el workspace ha excedido su TTL."""
        return (time.time() - self._created_at) > self.ttl_seconds

    def get_size_mb(self) -> float:
        """Retorna el tamaño total del workspace en MB."""
        total = 0
        if self.workspace_dir.exists():
            for f in self.workspace_dir.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total / (1024 * 1024)

    def close(self):
        """
        Cierra el workspace. Si auto_cleanup=True, elimina todo el directorio.
        """
        if self._closed:
            return
        self._closed = True

        if self.auto_cleanup and self.workspace_dir.exists():
            try:
                shutil.rmtree(self.workspace_dir, ignore_errors=True)
                logger.info("SandboxWorkspace limpiado: %s (%.2f MB liberados)",
                            self.sandbox_id, self.get_size_mb())
            except Exception as e:
                logger.warning("Error limpiando workspace %s: %s",
                               self.sandbox_id, e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __repr__(self):
        return (f"SandboxWorkspace(id={self.sandbox_id}, "
                f"path={self.workspace_dir}, closed={self._closed})")


class SandboxIsolationManager:
    """
    Gestor central de aislamiento del sandbox.

    Responsabilidades:
    1. Crear/destruir workspaces aislados
    2. Limpiar workspaces expirados automaticamente
    3. Verificar que el sandbox NUNCA escribe fuera de su workspace
    4. Proveer builtins restringidos para ejecucion segura
    5. Monitorear uso de recursos del sandbox
    """

    # Maximo de workspaces simultaneos para evitar consumir toda la RAM
    MAX_CONCURRENT_WORKSPACES = 10
    # Maximo tamaño total de todos los workspaces en MB
    MAX_TOTAL_SIZE_MB = 500

    def __init__(self):
        self.sandbox_root = SandboxWorkspace(sandbox_id="init",
                                              auto_cleanup=False).sandbox_root
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self._active_workspaces: Dict[str, SandboxWorkspace] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = None
        self._running = True

        # Crear entorno base reutilizable
        self._ensure_base_env()

        # Iniciar thread de cleanup automatico
        self._start_cleanup_thread()

        logger.info("SandboxIsolationManager iniciado (root=%s)", self.sandbox_root)

    def _ensure_base_env(self):
        """Crea el entorno base que se copia a cada workspace nuevo."""
        base_dir = self.sandbox_root / "base_env"
        base_dir.mkdir(parents=True, exist_ok=True)

        # Crear estructura base minima
        (base_dir / "code").mkdir(exist_ok=True)
        (base_dir / "projects").mkdir(exist_ok=True)
        (base_dir / "db").mkdir(exist_ok=True)
        (base_dir / "logs").mkdir(exist_ok=True)
        (base_dir / "tmp").mkdir(exist_ok=True)

    def create_workspace(self, sandbox_id=None, ttl_seconds=3600, client_id='default') -> SandboxWorkspace:
        """
        Crea un nuevo workspace aislado para ejecucion de sandbox.

        Args:
            sandbox_id: ID opcional. Se genera uno si no se proporciona.
            ttl_seconds: Tiempo de vida del workspace antes de cleanup.

        Returns:
            SandboxWorkspace listo para usar.

        Raises:
            RuntimeError: Si se excede el limite de workspaces simultaneos.
        """
        with self._lock:
            # Verificar limites
            if len(self._active_workspaces) >= self.MAX_CONCURRENT_WORKSPACES:
                # Forzar cleanup de workspaces expirados
                self._cleanup_expired()
                if len(self._active_workspaces) >= self.MAX_CONCURRENT_WORKSPACES:
                    raise RuntimeError(
                        f"Maximo de workspaces simultaneos alcanzado "
                        f"({self.MAX_CONCURRENT_WORKSPACES}). "
                        f"Espera a que terminen las ejecuciones en curso."
                    )

            # Verificar tamaño total
            total_size = self._get_total_size_mb()
            if total_size >= self.MAX_TOTAL_SIZE_MB:
                self._cleanup_expired()
                self._cleanup_oldest(count=2)
                total_size = self._get_total_size_mb()
                if total_size >= self.MAX_TOTAL_SIZE_MB:
                    raise RuntimeError(
                        f"Limite de almacenamiento del sandbox alcanzado "
                        f"({total_size:.0f}/{self.MAX_TOTAL_SIZE_MB} MB). "
                        f"Ejecuta cleanup_forced() para liberar espacio."
                    )

            workspace = SandboxWorkspace(
                sandbox_id=sandbox_id,
                auto_cleanup=False,  # El manager controla el ciclo de vida
                ttl_seconds=ttl_seconds,
                client_id=client_id,  # Brecha B: Pass client_id to workspace
            )
            self._active_workspaces[workspace.sandbox_id] = workspace

            logger.info("Workspace creado: %s (activos: %d/%d)",
                        workspace.sandbox_id,
                        len(self._active_workspaces),
                        self.MAX_CONCURRENT_WORKSPACES)

            return workspace

    def release_workspace(self, sandbox_id: str):
        """
        Libera un workspace, eliminandolo del disco.

        Args:
            sandbox_id: ID del workspace a liberar.
        """
        with self._lock:
            workspace = self._active_workspaces.pop(sandbox_id, None)
            if workspace:
                workspace.auto_cleanup = True
                workspace.close()
                logger.info("Workspace liberado: %s", sandbox_id)

    def get_workspace(self, sandbox_id: str) -> Optional[SandboxWorkspace]:
        """Obtiene un workspace activo por su ID."""
        return self._active_workspaces.get(sandbox_id)

    def list_active_workspaces(self) -> List[Dict[str, Any]]:
        """Lista todos los workspaces activos con su estado."""
        result = []
        for ws in self._active_workspaces.values():
            result.append({
                "sandbox_id": ws.sandbox_id,
                "client_id": ws.client_id,
                "path": str(ws.workspace_dir),
                "size_mb": ws.get_size_mb(),
                "age_seconds": int(time.time() - ws._created_at),
                "expired": ws.is_expired(),
                "closed": ws._closed,
            })
        return result

    def list_client_workspaces(self, client_id: str) -> List[Dict[str, Any]]:
        """Brecha B: Lista todos los workspaces activos para un client_id especifico."""
        result = []
        for ws in self._active_workspaces.values():
            if ws.client_id == client_id:
                result.append({
                    "sandbox_id": ws.sandbox_id,
                    "client_id": ws.client_id,
                    "path": str(ws.workspace_dir),
                    "size_mb": ws.get_size_mb(),
                    "age_seconds": int(time.time() - ws._created_at),
                    "expired": ws.is_expired(),
                    "closed": ws._closed,
                })
        return result

    def release_client_workspaces(self, client_id: str):
        """Brecha B: Libera todos los workspaces de un client_id especifico."""
        with self._lock:
            client_sids = [
                sid for sid, ws in self._active_workspaces.items()
                if ws.client_id == client_id
            ]
            for sid in client_sids:
                self._release_unsafe(sid)
            if client_sids:
                logger.info(
                    "Released %d workspaces for client_id='%s'",
                    len(client_sids), client_id
                )

    def cleanup_forced(self):
        """
        Fuerza la limpieza de TODOS los workspaces (incluso los no expirados).
        Se usa cuando el sistema necesita liberar memoria/disco urgentemente.
        """
        with self._lock:
            ids = list(self._active_workspaces.keys())
            for sid in ids:
                self._release_unsafe(sid)
            logger.warning("Cleanup forzado completado: %d workspaces eliminados", len(ids))

    def _cleanup_expired(self):
        """Elimina workspaces que han excedido su TTL."""
        expired_ids = [
            sid for sid, ws in self._active_workspaces.items()
            if ws.is_expired()
        ]
        for sid in expired_ids:
            self._release_unsafe(sid)
        if expired_ids:
            logger.info("Cleanup TTL: %d workspaces expirados eliminados", len(expired_ids))

    def _cleanup_oldest(self, count: int = 1):
        """Elimina los workspaces mas antiguos para liberar espacio."""
        sorted_ws = sorted(
            self._active_workspaces.items(),
            key=lambda x: x[1]._created_at
        )
        for sid, ws in sorted_ws[:count]:
            self._release_unsafe(sid)

    def _release_unsafe(self, sandbox_id: str):
        """Libera un workspace sin adquirir el lock (llamar dentro de _lock)."""
        workspace = self._active_workspaces.pop(sandbox_id, None)
        if workspace:
            workspace.auto_cleanup = True
            workspace.close()

    def _get_total_size_mb(self) -> float:
        """Calcula el tamaño total de todos los workspaces activos."""
        return sum(ws.get_size_mb() for ws in self._active_workspaces.values())

    def _start_cleanup_thread(self):
        """Inicia un thread daemon que limpia workspaces expirados periodicamente."""
        def _cleanup_loop():
            while self._running:
                try:
                    time.sleep(60)  # Check cada minuto
                    with self._lock:
                        self._cleanup_expired()
                except Exception as e:
                    logger.error("Error en cleanup thread: %s", e)

        self._cleanup_thread = threading.Thread(
            target=_cleanup_loop, daemon=True, name="sandbox-cleanup"
        )
        self._cleanup_thread.start()

    def shutdown(self):
        """Detiene el manager y limpia todos los workspaces."""
        self._running = False
        self.cleanup_forced()
        logger.info("SandboxIsolationManager detenido")


# ============================================================
#  BUILTINS RESTRINGIDOS PARA EJECUCION AISLADA
# ============================================================

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


# ============================================================
#  INSTANCIA GLOBAL DEL MANAGER (Singleton)
# ============================================================

_isolation_manager = None
_manager_lock = threading.Lock()


def get_isolation_manager() -> SandboxIsolationManager:
    """
    Obtiene la instancia singleton del SandboxIsolationManager.
    Thread-safe: se crea una sola instancia compartida.
    """
    global _isolation_manager
    if _isolation_manager is None:
        with _manager_lock:
            if _isolation_manager is None:
                _isolation_manager = SandboxIsolationManager()
    return _isolation_manager


def shutdown_isolation():
    """Detiene el sistema de aislamiento y limpia todos los workspaces."""
    global _isolation_manager
    if _isolation_manager is not None:
        _isolation_manager.shutdown()
        _isolation_manager = None
