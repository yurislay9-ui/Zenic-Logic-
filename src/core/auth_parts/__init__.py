"""
AuthService — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.auth_service import AuthService``
still works exactly as before.
"""

import os
import threading
from pathlib import Path

from ._imports import (
    logger, secrets, JOSE_AVAILABLE, PASSLIB_AVAILABLE,
)
from ._db_mixin import DbPasswordMixin
from ._token_mixin import TokenMixin
from ._user_mixin import UserMixin
from ._rbac_mixin import RbacMixin
from ._api_key_mixin import ApiKeyMixin
from ._validation_mixin import ValidationMixin


class AuthService(DbPasswordMixin, TokenMixin, UserMixin, RbacMixin,
                  ApiKeyMixin, ValidationMixin):
    """
    Runtime authentication service for TITAN OMNISCALE X.

    Provides JWT authentication, user management, and RBAC.
    Uses SQLite for user storage. Works with or without
    python-jose and passlib (has fallbacks).
    """

    def __init__(self, db_path: str = "", secret_key: str = ""):
        if db_path:
            self._db_path = db_path
        else:
            d = Path.home() / ".titan_omniscale" / "db"
            d.mkdir(parents=True, exist_ok=True)
            self._db_path = str(d / "auth.sqlite")

        self._secret_key = secret_key or os.environ.get("TITAN_AUTH_SECRET", "")
        if not self._secret_key:
            kf = Path(self._db_path).parent / ".auth_secret"
            if kf.exists():
                self._secret_key = kf.read_text().strip()
            else:
                self._secret_key = secrets.token_hex(32)
                kf.write_text(self._secret_key); kf.chmod(0o600)

        self._lock = threading.RLock()
        self.init_db()
        logger.info(f"AuthService: init (jose={JOSE_AVAILABLE}, passlib={PASSLIB_AVAILABLE})")


__all__ = ["AuthService"]
