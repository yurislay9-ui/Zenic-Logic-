"""
TITAN OMNISCALE X - ActionExecutor System (Phase 7.1)

Facade module that re-exports all public symbols from the executors sub-package.
All implementation has been modularized into src/core/executors/.
"""

from .executors import (
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
    EmailExecutor,
    HttpExecutor,
    DatabaseExecutor,
    FileExecutor,
    NotificationExecutor,
    WebhookExecutor,
    TransformExecutor,
    ScheduleExecutor,
)

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
