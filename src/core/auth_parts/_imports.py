"""
Shared imports and constants for auth_parts sub-modules.
"""

import os
import re
import json
import time
import hashlib
import hmac
import secrets
import sqlite3
import threading
import logging
import base64
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Set, Callable, Any

logger = logging.getLogger(__name__)

# --- Optional deps ---
try:
    from jose import JWTError, jwt as jose_jwt
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False; jose_jwt = None; JWTError = Exception

try:
    from passlib.context import CryptContext
    PASSLIB_AVAILABLE = True
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    PASSLIB_AVAILABLE = False; _pwd_context = None

try:
    from fastapi import Depends, HTTPException, status
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    HAS_FASTAPI = True
    _security = HTTPBearer()
except ImportError:
    HAS_FASTAPI = False; Depends = None; HTTPException = None
    status = None; _security = None

# --- Constants ---
ROLE_HIERARCHY = {"viewer": 0, "user": 1, "manager": 2, "admin": 3}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin":   {"read", "write", "delete", "manage_users", "manage_system", "view_analytics"},
    "manager": {"read", "write", "delete", "view_analytics"},
    "user":    {"read", "write"},
    "viewer":  {"read"},
}

ACCESS_EXPIRE_MIN = 60
REFRESH_EXPIRE_DAYS = 7
PBKDF2_ITERATIONS = 100_000
API_KEY_PREFIX = "titan_"
PAGE_SIZE = 50
