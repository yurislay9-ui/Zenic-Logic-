"""
TITAN OMNISCALE X - AuthService Runtime (Phase 7.3)

Runtime authentication service for the orchestrator and generated apps.
JWT + HMAC fallback tokens, RBAC, user management, token revocation,
API key auth. Uses SQLite. Zero hard deps beyond stdlib.

Compatible con Termux + Android.
"""

from .auth_parts import *  # noqa: F401,F403
from .auth_parts import AuthService  # explicit
from .auth_parts._imports import (
    ROLE_HIERARCHY, ROLE_PERMISSIONS, ACCESS_EXPIRE_MIN,
    REFRESH_EXPIRE_DAYS, PBKDF2_ITERATIONS, API_KEY_PREFIX, PAGE_SIZE,
    JOSE_AVAILABLE, PASSLIB_AVAILABLE, HAS_FASTAPI,
)

__all__ = [
    "AuthService",
    "ROLE_HIERARCHY",
    "ROLE_PERMISSIONS",
    "ACCESS_EXPIRE_MIN",
    "REFRESH_EXPIRE_DAYS",
    "PBKDF2_ITERATIONS",
    "API_KEY_PREFIX",
    "PAGE_SIZE",
    "JOSE_AVAILABLE",
    "PASSLIB_AVAILABLE",
    "HAS_FASTAPI",
]
