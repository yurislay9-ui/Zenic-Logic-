"""
TITAN OMNISCALE X - ActionExecutor Base Module (Phase 7.1)

Base classes, validation helpers, and registry for the ActionExecutor system.
"""

import os, re, time, hashlib, hmac, logging, sqlite3
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Dependencias opcionales
try:
    import aiosmtplib; _HAS_AIOSMTPLIB = True
except ImportError: _HAS_AIOSMTPLIB = False

try:
    import aiohttp; _HAS_AIOHTTP = True
except ImportError: _HAS_AIOHTTP = False

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    _HAS_APSCHEDULER = True
except ImportError: _HAS_APSCHEDULER = False


# ============================================================
#  RESULTADO DE ACCIÓN
# ============================================================

@dataclass
class ActionResult:
    """Resultado estandarizado de cualquier acción ejecutada."""
    success: bool
    data: Dict[str, Any]
    error: str = ""
    duration_ms: float = 0.0


# ============================================================
#  CLASE BASE ABSTRACTA
# ============================================================

class ActionExecutor(ABC):
    """Clase base abstracta para todos los ejecutores de acciones."""

    @abstractmethod
    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        """Ejecuta la acción con la configuración y contexto dados."""
        ...

    def _measure(self) -> float:
        return time.monotonic()

    def _elapsed_ms(self, start: float) -> float:
        return round((time.monotonic() - start) * 1000, 2)


# ============================================================
#  VALIDADORES UTILITARIOS
# ============================================================

def _validate_email(email: str) -> bool:
    """Valida formato básico de email."""
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))

def _validate_url(url: str) -> bool:
    """Valida formato básico de URL."""
    try:
        r = urllib.parse.urlparse(url)
        return all([r.scheme in ("http", "https"), r.netloc])
    except Exception: return False

def _safe_path(path: str, base_dir: str = "") -> str:
    """Resuelve path y verifica que no escape del base_dir (path traversal).

    SECURITY (H-05 fix): Removed /tmp and home directory from allowed prefixes.
    Only the explicitly configured base_dir is allowed. This prevents reading
    sensitive files like ~/.ssh/, ~/.env, ~/.bashrc via FileExecutor.

    If base_dir is "", uses os.getcwd(). Absolute paths are only allowed
    if they resolve within the base_dir. Relative paths are resolved
    against base_dir and must not escape it via ../ traversal.
    """
    if not base_dir: base_dir = os.getcwd()
    base_dir = os.path.realpath(base_dir)

    # Si el path es absoluto, verificar que está dentro del base_dir
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
        # SECURITY: Only allow paths within the configured base_dir
        if resolved.startswith(base_dir + os.sep) or resolved == base_dir:
            return resolved
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")

    # Path relativo: verificar que no escapa del base_dir
    resolved = os.path.realpath(os.path.join(base_dir, path))
    if not resolved.startswith(base_dir + os.sep) and resolved != base_dir:
        raise ValueError(f"Path traversal detected: '{path}' escapes base directory")
    return resolved

def _validate_sql(query: str) -> bool:
    """Valida que un query SQL no contenga patrones de inyección peligrosos."""
    dangerous = [r";\s*DROP\s", r";\s*DELETE\s+FROM\s", r";\s*UPDATE\s+.+\s+SET\s",
                 r";\s*INSERT\s+INTO\s", r"UNION\s+SELECT\s", r"--\s*$", r"/\*.*\*/"]
    for pattern in dangerous:
        if re.search(pattern, query, re.MULTILINE | re.IGNORECASE):
            logger.warning(f"SQL validation: potentially dangerous pattern: {pattern}")
            return False
    return True


# ============================================================
#  REGISTRY DE EJECUTORES
# ============================================================

class ExecutorRegistry:
    """Registry centralizado que gestiona todos los action executors.

    Provee un punto único de acceso para registrar y ejecutar
    cualquier tipo de acción a través de su executor correspondiente.
    """

    def __init__(self) -> None:
        self._executors: Dict[str, ActionExecutor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra los ejecutores por defecto."""
        # Lazy imports to avoid circular dependencies
        from .email_executor import EmailExecutor
        from .http_executor import HttpExecutor
        from .database_executor import DatabaseExecutor
        from .file_executor import FileExecutor
        from .webhook_executor import WebhookExecutor
        from .transform_executor import TransformExecutor
        from .notification_executor import NotificationExecutor
        from .schedule_executor import ScheduleExecutor

        email_exec = EmailExecutor()
        http_exec = HttpExecutor()
        db_exec = DatabaseExecutor()
        file_exec = FileExecutor()
        webhook_exec = WebhookExecutor()
        transform_exec = TransformExecutor()
        notification_exec = NotificationExecutor(email_executor=email_exec, webhook_executor=webhook_exec)
        schedule_exec = ScheduleExecutor()

        # Mapeo de tipos de acción a ejecutores (alias incluidos)
        for key, executor in [
            ("send_email", email_exec), ("email", email_exec),
            ("http_request", http_exec), ("http", http_exec),
            ("database_operation", db_exec), ("database", db_exec), ("db", db_exec),
            ("file_operation", file_exec), ("file", file_exec),
            ("send_notification", notification_exec), ("notification", notification_exec),
            ("webhook", webhook_exec),
            ("data_transform", transform_exec), ("transform", transform_exec),
            ("schedule", schedule_exec),
        ]:
            self.register_executor(key, executor)

    def get_executor(self, action_type: str) -> Optional[ActionExecutor]:
        """Obtiene el executor registrado para un tipo de acción."""
        return self._executors.get(action_type)

    def register_executor(self, action_type: str, executor: ActionExecutor) -> None:
        """Registra un executor para un tipo de acción."""
        self._executors[action_type] = executor
        logger.debug(f"ExecutorRegistry: Registered '{action_type}' -> {executor.__class__.__name__}")

    async def execute_action(self, action_type: str, config: Dict[str, Any],
                             context: Optional[Dict[str, Any]] = None) -> ActionResult:
        """Ejecuta una acción a través del executor correspondiente."""
        if context is None: context = {}
        executor = self.get_executor(action_type)
        if not executor:
            return ActionResult(False, {"action_type": action_type},
                                f"No executor for '{action_type}'. Available: {list(self._executors.keys())}")
        try:
            return await executor.execute(config, context)
        except Exception as e:
            logger.error(f"ExecutorRegistry: Unhandled exception in {action_type}: {e}")
            return ActionResult(False, {"action_type": action_type}, f"Executor error: {e}")

    @property
    def registered_types(self) -> List[str]:
        """Lista de tipos de acción registrados."""
        return list(self._executors.keys())

    @property
    def executor_classes(self) -> Dict[str, str]:
        """Mapeo de tipo de acción a clase de executor."""
        return {k: v.__class__.__name__ for k, v in self._executors.items()}


# ============================================================
#  INSTANCIA GLOBAL DEL REGISTRY
# ============================================================

_default_registry: Optional[ExecutorRegistry] = None

def get_default_registry() -> ExecutorRegistry:
    """Obtiene la instancia global del ExecutorRegistry."""
    global _default_registry
    if _default_registry is None: _default_registry = ExecutorRegistry()
    return _default_registry

def reset_default_registry() -> None:
    """Resetea la instancia global del registry (para tests)."""
    global _default_registry
    _default_registry = None
