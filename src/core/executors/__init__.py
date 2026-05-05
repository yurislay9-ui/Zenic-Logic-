"""
TITAN OMNISCALE X - ActionExecutor System (Phase 7.1)

Sistema de ejecutores de acciones reales para el AutomationEngine.
Reemplaza los stubs logger.info() con operaciones funcionales.

Ocho ejecutores:
  1. EmailExecutor      - Envío real de emails vía SMTP
  2. HttpExecutor       - Peticiones HTTP reales (aiohttp/urllib)
  3. DatabaseExecutor   - Operaciones SQLite con queries parametrizadas
  4. FileExecutor       - Operaciones de archivos con protección path-traversal
  5. NotificationExecutor - Despacho multi-canal de notificaciones
  6. WebhookExecutor    - Envío y verificación de webhooks (HMAC-SHA256)
  7. TransformExecutor  - Transformación y mapeo de datos
  8. ScheduleExecutor   - Programación de jobs (APScheduler/fallback)

Todos los ejecutores:
  - Manejan errores gracefulmente (nunca raise, siempre devuelven ActionResult)
  - Tienen modo dry-run/fallback cuando faltan dependencias
  - Son testeable sin servicios externos
  - Usan logging extensivo
"""

from .base import (
    ActionResult,
    ActionExecutor,
    ExecutorRegistry,
    _validate_email,
    _validate_url,
    _safe_path,
    _validate_sql,
    _HAS_AIOSMTPLIB,
    _HAS_AIOHTTP,
    _HAS_APSCHEDULER,
    get_default_registry,
    reset_default_registry,
)

from .email_executor import EmailExecutor
from .http_executor import HttpExecutor
from .database_executor import DatabaseExecutor
from .file_executor import FileExecutor
from .notification_executor import NotificationExecutor
from .webhook_executor import WebhookExecutor
from .transform_executor import TransformExecutor
from .schedule_executor import ScheduleExecutor

__all__ = [
    "ActionResult",
    "ActionExecutor",
    "ExecutorRegistry",
    "_validate_email",
    "_validate_url",
    "_safe_path",
    "_validate_sql",
    "_HAS_AIOSMTPLIB",
    "_HAS_AIOHTTP",
    "_HAS_APSCHEDULER",
    "get_default_registry",
    "reset_default_registry",
    "EmailExecutor",
    "HttpExecutor",
    "DatabaseExecutor",
    "FileExecutor",
    "NotificationExecutor",
    "WebhookExecutor",
    "TransformExecutor",
    "ScheduleExecutor",
]
