"""
TITAN OMNISCALE X - AuthService Runtime (Phase 7.3)

Runtime authentication service for the orchestrator and generated apps.
JWT + HMAC fallback tokens, RBAC, user management, token revocation,
API key auth. Uses SQLite. Zero hard deps beyond stdlib.

Compatible con Termux + Android.
"""

import os, re, json, time, hashlib, hmac, secrets, sqlite3, threading, logging, base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Set, Callable, Any

logger = logging.getLogger(__name__)

# --- Optional deps (graceful fallback) ---
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


class AuthService:
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

        self._lock = threading.Lock()
        self.init_db()
        logger.info(f"AuthService: init (jose={JOSE_AVAILABLE}, passlib={PASSLIB_AVAILABLE})")

    # ================================================================
    #  DATABASE
    # ================================================================

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def init_db(self):
        """Create users, revoked_tokens, and api_keys tables if not exists."""
        c = self._conn()
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT,
                login_count INTEGER DEFAULT 0)""")
            c.execute("""CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                user_id INTEGER,
                revoked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                permissions TEXT DEFAULT '[]',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used TEXT,
                usage_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id))""")
            for idx in [
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
                "CREATE INDEX IF NOT EXISTS idx_revoked_jti ON revoked_tokens(jti)",
                "CREATE INDEX IF NOT EXISTS idx_revoked_expires ON revoked_tokens(expires_at)",
                "CREATE INDEX IF NOT EXISTS idx_apikeys_user ON api_keys(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_apikeys_active ON api_keys(active)",
            ]:
                c.execute(idx)
            c.commit()
        finally:
            c.close()

    # ================================================================
    #  PASSWORD MANAGEMENT
    # ================================================================

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt (preferred) or PBKDF2-SHA256 (fallback).
        Format: pbkdf2$iterations$salt$hash  (100k iterations)."""
        if _pwd_context:
            return _pwd_context.hash(password)
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
        return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash. Supports bcrypt, pbkdf2$, sha256$ formats."""
        if not password or not hashed:
            return False
        if _pwd_context:
            try:
                return _pwd_context.verify(password, hashed)
            except Exception:
                pass  # Fall through to pbkdf2/sha256
        if hashed.startswith("pbkdf2$"):
            try:
                _, iters_s, salt, stored = hashed.split("$", 3)
                dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters_s))
                return secrets.compare_digest(dk.hex(), stored)
            except (ValueError, IndexError):
                return False
        if hashed.startswith("sha256$"):
            try:
                _, salt, stored = hashed.split("$", 2)
                computed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
                return secrets.compare_digest(computed, stored)
            except (ValueError, IndexError):
                return False
        return False

    # ================================================================
    #  TOKEN MANAGEMENT
    # ================================================================

    def create_access_token(self, user_id: int, role: str, extra: Dict = None) -> str:
        """Create access token. JWT if jose available, HMAC-based otherwise."""
        jti = secrets.token_hex(16)
        now = datetime.utcnow()
        payload = {
            "sub": str(user_id), "role": role, "type": "access", "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=ACCESS_EXPIRE_MIN)).timestamp()),
        }
        if extra:
            payload.update(extra)
        if JOSE_AVAILABLE:
            return jose_jwt.encode(payload, self._secret_key, algorithm="HS256")
        return self._encode_hmac(payload)

    def create_refresh_token(self, user_id: int) -> str:
        """Create refresh token with longer expiry."""
        jti = secrets.token_hex(16)
        now = datetime.utcnow()
        payload = {
            "sub": str(user_id), "type": "refresh", "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=REFRESH_EXPIRE_DAYS)).timestamp()),
        }
        if JOSE_AVAILABLE:
            return jose_jwt.encode(payload, self._secret_key, algorithm="HS256")
        return self._encode_hmac(payload)

    def verify_token(self, token: str, token_type: str = "access") -> Dict:
        """Verify and decode token. Returns payload dict or error dict."""
        payload = None
        if JOSE_AVAILABLE:
            try:
                payload = jose_jwt.decode(token, self._secret_key, algorithms=["HS256"])
            except JWTError:
                payload = None
        if payload is None:
            payload = self._decode_hmac(token)
        if payload is None:
            return {"error": "Invalid or expired token"}
        if payload.get("type") != token_type:
            return {"error": f"Invalid token type: expected {token_type}"}
        if payload.get("exp") and time.time() > payload["exp"]:
            return {"error": "Token has expired"}
        jti = payload.get("jti", "")
        if jti and self.is_token_revoked(jti):
            return {"error": "Token has been revoked"}
        return payload

    def refresh_access_token(self, refresh_token: str) -> Dict:
        """Use refresh token to get new access + refresh tokens."""
        payload = self.verify_token(refresh_token, token_type="refresh")
        if "error" in payload:
            return payload
        user_id = int(payload["sub"])
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return {"error": "User account is deactivated"}
        old_jti = payload.get("jti", "")
        if old_jti:
            self.revoke_token(refresh_token)
        return {
            "access_token": self.create_access_token(user_id, user["role"]),
            "refresh_token": self.create_refresh_token(user_id),
            "token_type": "bearer",
        }

    def revoke_token(self, token: str) -> bool:
        """Add token to revocation blacklist."""
        payload = None
        if JOSE_AVAILABLE:
            try:
                payload = jose_jwt.decode(token, self._secret_key, algorithms=["HS256"],
                                          options={"verify_exp": False})
            except JWTError:
                pass
        if payload is None:
            payload = self._decode_hmac(token, verify_exp=False)
        if payload is None:
            return False
        jti = payload.get("jti", "")
        if not jti:
            return False
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp).isoformat() if exp else None
        now = datetime.utcnow().isoformat()
        c = self._conn()
        try:
            c.execute("INSERT OR IGNORE INTO revoked_tokens (jti, user_id, revoked_at, expires_at) "
                      "VALUES (?, ?, ?, ?)", (jti, int(payload.get("sub", 0)), now, expires_at))
            c.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"AuthService: revoke_token error: {e}")
            return False
        finally:
            c.close()

    # --- HMAC token fallback (sin python-jose) ---

    def _encode_hmac(self, payload: Dict) -> str:
        """Encode payload using HMAC-SHA256. Format: header.payload.signature"""
        hdr = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "HMAC-JWT"}, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        sig = hmac.new(self._secret_key.encode(), f"{hdr}.{body}".encode(), hashlib.sha256).hexdigest()
        return f"{hdr}.{body}.{sig}"

    def _decode_hmac(self, token: str, verify_exp: bool = True) -> Optional[Dict]:
        """Decode HMAC-SHA256 token. Returns payload or None."""
        if not token or token.count(".") != 2:
            return None
        try:
            hdr_b64, body_b64, sig = token.split(".")
            expected = hmac.new(self._secret_key.encode(), f"{hdr_b64}.{body_b64}".encode(),
                               hashlib.sha256).hexdigest()
            if not secrets.compare_digest(sig, expected):
                return None
            pad = 4 - len(body_b64) % 4
            if pad != 4:
                body_b64 += "=" * pad
            payload = json.loads(base64.urlsafe_b64decode(body_b64))
            if verify_exp and payload.get("exp") and time.time() > payload["exp"]:
                return None
            return payload
        except Exception:
            return None

    # --- Token revocation ---

    def _init_revocation_table(self):
        """Ensure revocation table exists (handled by init_db)."""
        pass

    def is_token_revoked(self, token_jti: str) -> bool:
        """Check if a token JTI is in the revocation blacklist."""
        if not token_jti:
            return False
        c = self._conn()
        try:
            return c.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (token_jti,)).fetchone() is not None
        finally:
            c.close()

    def cleanup_revoked_tokens(self) -> int:
        """Remove expired tokens from blacklist. Returns count removed."""
        now = datetime.utcnow().isoformat()
        c = self._conn()
        try:
            n = c.execute("DELETE FROM revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
                          (now,)).rowcount
            c.commit()
            if n:
                logger.info(f"AuthService: cleaned {n} expired revoked tokens")
            return n
        finally:
            c.close()

    # ================================================================
    #  USER MANAGEMENT
    # ================================================================

    def register_user(self, username: str, email: str, password: str, role: str = "user") -> Dict:
        """Register new user with validation. Returns user info or error dict."""
        errors = self._validate_registration(username, email, password)
        if errors:
            return {"error": "; ".join(errors)}
        if role not in ROLE_HIERARCHY:
            return {"error": f"Invalid role: {role}"}
        pw_hash = self.hash_password(password)
        now = datetime.utcnow().isoformat()
        c = self._conn()
        try:
            with self._lock:
                if c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                    return {"error": "Username already exists"}
                if c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
                    return {"error": "Email already registered"}
                cur = c.execute("INSERT INTO users (username, email, password_hash, role, active, "
                                "created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
                                (username, email, pw_hash, role, now, now))
                uid = cur.lastrowid
                c.commit()
            logger.info(f"AuthService: registered {username} (id={uid}, role={role})")
            return {"user_id": uid, "username": username, "email": email, "role": role,
                    "message": "User registered successfully"}
        except sqlite3.IntegrityError:
            return {"error": "Username or email already exists"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def login_user(self, username: str, password: str) -> Dict:
        """Authenticate user and return tokens, or error dict."""
        c = self._conn()
        try:
            row = c.execute("SELECT id, username, email, password_hash, role, active "
                            "FROM users WHERE username = ? OR email = ?",
                            (username, username)).fetchone()
            if not row:
                return {"error": "Invalid credentials"}
            if not row["active"]:
                return {"error": "Account is deactivated"}
            if not self.verify_password(password, row["password_hash"]):
                return {"error": "Invalid credentials"}
            uid, role = row["id"], row["role"]
            now = datetime.utcnow().isoformat()
            c.execute("UPDATE users SET last_login = ?, login_count = login_count + 1, "
                      "updated_at = ? WHERE id = ?", (now, now, uid))
            c.commit()
            logger.info(f"AuthService: login {row['username']}")
            return {
                "access_token": self.create_access_token(uid, role),
                "refresh_token": self.create_refresh_token(uid),
                "token_type": "bearer",
                "user": {"id": uid, "username": row["username"], "email": row["email"], "role": role},
            }
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID (without password hash). Returns dict or None."""
        c = self._conn()
        try:
            row = c.execute("SELECT id, username, email, role, active, created_at, "
                            "updated_at, last_login, login_count FROM users WHERE id = ?",
                            (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            c.close()

    def update_user(self, user_id: int, **fields) -> Dict:
        """Update user fields. Returns updated user dict or error dict."""
        allowed = {"username", "email", "role", "active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return {"error": "No valid fields to update"}
        if "role" in updates and updates["role"] not in ROLE_HIERARCHY:
            return {"error": f"Invalid role: {updates['role']}"}
        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [user_id]
        c = self._conn()
        try:
            with self._lock:
                if c.execute(f"UPDATE users SET {set_clause} WHERE id = ?", vals).rowcount == 0:
                    return {"error": "User not found"}
                c.commit()
            return self.get_user(user_id) or {"error": "User not found after update"}
        except sqlite3.IntegrityError:
            return {"error": "Username or email already exists"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def deactivate_user(self, user_id: int) -> bool:
        """Soft-delete user. Returns True if deactivated."""
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute("UPDATE users SET active = 0, updated_at = ? WHERE id = ?",
                                (datetime.utcnow().isoformat(), user_id))
                c.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"AuthService: deactivate error: {e}")
            return False
        finally:
            c.close()

    def list_users(self, role: str = "", page: int = 1) -> List[Dict]:
        """List users with optional role filter and pagination."""
        offset = (page - 1) * PAGE_SIZE
        c = self._conn()
        try:
            if role:
                rows = c.execute("SELECT id, username, email, role, active, created_at, "
                                 "last_login, login_count FROM users WHERE role = ? "
                                 "ORDER BY id LIMIT ? OFFSET ?", (role, PAGE_SIZE, offset)).fetchall()
            else:
                rows = c.execute("SELECT id, username, email, role, active, created_at, "
                                 "last_login, login_count FROM users ORDER BY id LIMIT ? OFFSET ?",
                                 (PAGE_SIZE, offset)).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """Change password (requires current password). Returns True if changed."""
        c = self._conn()
        try:
            row = c.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row or not self.verify_password(old_password, row["password_hash"]):
                return False
            with self._lock:
                c.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                          (self.hash_password(new_password), datetime.utcnow().isoformat(), user_id))
                c.commit()
            logger.info(f"AuthService: password changed for user {user_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"AuthService: change_password error: {e}")
            return False
        finally:
            c.close()

    def reset_password(self, user_id: int, new_password: str) -> bool:
        """Reset password (admin op, no old password needed). Returns True if reset."""
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                                (self.hash_password(new_password), datetime.utcnow().isoformat(), user_id))
                c.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"AuthService: reset_password error: {e}")
            return False
        finally:
            c.close()

    # ================================================================
    #  RBAC
    # ================================================================

    def check_permission(self, user_id: int, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.get_user_permissions(user_id)

    def check_role(self, user_id: int, minimum_role: str) -> bool:
        """Check if user meets minimum role level."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return False
        return ROLE_HIERARCHY.get(user.get("role", ""), -1) >= ROLE_HIERARCHY.get(minimum_role, -1)

    def get_user_permissions(self, user_id: int) -> Set[str]:
        """Get all permissions for user based on their role."""
        user = self.get_user(user_id)
        if not user or not user.get("active"):
            return set()
        return ROLE_PERMISSIONS.get(user.get("role", "viewer"), set())

    def require_permission(self, permission: str) -> Callable:
        """FastAPI dependency factory requiring a specific permission."""
        auth = self
        async def _check(credentials=Depends(_security)) -> Dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_permission(uid, permission):
                raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
            return {"user_id": uid, "role": payload.get("role", "user"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    def require_role(self, minimum_role: str) -> Callable:
        """FastAPI dependency factory requiring minimum role."""
        auth = self
        async def _check(credentials=Depends(_security)) -> Dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            if not auth.check_role(uid, minimum_role):
                raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
            return {"user_id": uid, "role": payload.get("role", "user"),
                    "permissions": list(auth.get_user_permissions(uid))}
        return _check

    # ================================================================
    #  FASTAPI INTEGRATION
    # ================================================================

    def get_auth_dependencies(self) -> Dict:
        """Returns FastAPI dependency functions for auth."""
        if not HAS_FASTAPI:
            return {"error": "FastAPI not available"}
        auth = self

        async def get_current_user(credentials=Depends(_security)) -> Dict:
            payload = auth.verify_token(credentials.credentials, "access")
            if "error" in payload:
                raise HTTPException(status_code=401, detail=payload["error"],
                                    headers={"WWW-Authenticate": "Bearer"})
            uid = int(payload["sub"])
            user = auth.get_user(uid)
            if not user or not user.get("active"):
                raise HTTPException(status_code=401, detail="User not found or deactivated")
            return {"user_id": uid, "username": user.get("username", ""),
                    "role": user.get("role", "viewer"), "permissions": list(auth.get_user_permissions(uid))}

        async def require_admin(user=Depends(get_current_user)) -> Dict:
            if user.get("role") != "admin":
                raise HTTPException(status_code=403, detail="Admin access required")
            return user

        async def require_manager(user=Depends(get_current_user)) -> Dict:
            if ROLE_HIERARCHY.get(user.get("role", ""), -1) < ROLE_HIERARCHY["manager"]:
                raise HTTPException(status_code=403, detail="Manager or admin access required")
            return user

        return {
            "get_current_user": get_current_user,
            "require_admin": require_admin,
            "require_manager": require_manager,
            "require_permission": lambda perm: auth.require_permission(perm),
        }

    def protect_endpoint(self, minimum_role: str = "user") -> Callable:
        """Decorator to protect a FastAPI endpoint by role."""
        if not HAS_FASTAPI:
            return lambda f: f  # no-op si FastAPI no disponible
        auth = self

        def decorator(func: Callable) -> Callable:
            async def wrapper(*args, **kwargs):
                request = kwargs.get("request")
                if not request:
                    raise HTTPException(status_code=401, detail="No request object found")
                auth_hdr = request.headers.get("Authorization", "")
                if not auth_hdr.startswith("Bearer "):
                    raise HTTPException(status_code=401, detail="Bearer token required",
                                        headers={"WWW-Authenticate": "Bearer"})
                payload = auth.verify_token(auth_hdr[7:], "access")
                if "error" in payload:
                    raise HTTPException(status_code=401, detail=payload["error"])
                uid = int(payload["sub"])
                if not auth.check_role(uid, minimum_role):
                    raise HTTPException(status_code=403, detail=f"Role '{minimum_role}' or higher required")
                kwargs["auth_user_id"] = uid
                kwargs["auth_role"] = payload.get("role", "viewer")
                return await func(*args, **kwargs)
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator

    # ================================================================
    #  API KEY AUTHENTICATION
    # ================================================================

    def create_api_key(self, user_id: int, name: str, permissions: List[str] = None) -> Dict:
        """Create API key. Plaintext shown only once. Returns key info or error."""
        user = self.get_user(user_id)
        if not user:
            return {"error": "User not found"}
        if not user.get("active"):
            return {"error": "User account is deactivated"}
        raw = secrets.token_hex(32)
        api_key = f"{API_KEY_PREFIX}{raw}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_id = secrets.token_hex(8)
        now = datetime.utcnow().isoformat()
        perms_json = json.dumps(permissions or [])
        c = self._conn()
        try:
            with self._lock:
                c.execute("INSERT INTO api_keys (id, user_id, name, key_hash, permissions, "
                          "active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                          (key_id, user_id, name, key_hash, perms_json, now))
                c.commit()
            logger.info(f"AuthService: API key created for user {user_id}: {name}")
            return {"key_id": key_id, "api_key": api_key, "name": name,
                    "permissions": permissions or [],
                    "message": "Save this key securely - it cannot be retrieved later"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def verify_api_key(self, api_key: str) -> Optional[Dict]:
        """Verify API key. Returns identity dict or None."""
        if not api_key or not api_key.startswith(API_KEY_PREFIX):
            return None
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        c = self._conn()
        try:
            rows = c.execute("SELECT id, user_id, name, key_hash, permissions, active "
                             "FROM api_keys WHERE active = 1").fetchall()
            for row in rows:
                if secrets.compare_digest(row["key_hash"], key_hash):
                    user = self.get_user(row["user_id"])
                    if not user or not user.get("active"):
                        return None
                    now = datetime.utcnow().isoformat()
                    c.execute("UPDATE api_keys SET last_used = ?, usage_count = usage_count + 1 "
                              "WHERE id = ?", (now, row["id"]))
                    c.commit()
                    try:
                        perms = json.loads(row["permissions"])
                    except (json.JSONDecodeError, TypeError):
                        perms = []
                    all_perms = self.get_user_permissions(row["user_id"]) | set(perms)
                    return {"key_id": row["id"], "user_id": row["user_id"], "name": row["name"],
                            "role": user.get("role", "viewer"), "permissions": list(all_perms)}
            return None
        finally:
            c.close()

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke API key by ID. Returns True if revoked."""
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute("UPDATE api_keys SET active = 0 WHERE id = ?", (key_id,))
                c.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"AuthService: revoke_api_key error: {e}")
            return False
        finally:
            c.close()

    def list_api_keys(self, user_id: int) -> List[Dict]:
        """List API keys for user (without key values)."""
        c = self._conn()
        try:
            rows = c.execute("SELECT id, name, permissions, active, created_at, last_used, "
                             "usage_count FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                             (user_id,)).fetchall()
            result = []
            for r in rows:
                try:
                    perms = json.loads(r["permissions"])
                except (json.JSONDecodeError, TypeError):
                    perms = []
                result.append({"key_id": r["id"], "name": r["name"], "permissions": perms,
                               "active": bool(r["active"]), "created_at": r["created_at"],
                               "last_used": r["last_used"], "usage_count": r["usage_count"]})
            return result
        finally:
            c.close()

    # ================================================================
    #  VALIDATION
    # ================================================================

    @staticmethod
    def _validate_registration(username: str, email: str, password: str) -> List[str]:
        """Validate registration inputs. Returns error list (empty = valid)."""
        errors = []
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters")
        if len(username) > 50:
            errors.append("Username must be at most 50 characters")
        if username and not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append("Username: only letters, numbers, underscores")
        if not email:
            errors.append("Email is required")
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append("Invalid email format")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters")
        if password and len(password) >= 8:
            if not (any(c.isupper() for c in password) and
                    any(c.islower() for c in password) and
                    any(c.isdigit() for c in password)):
                errors.append("Password must contain uppercase, lowercase, and a digit")
        return errors

    # ================================================================
    #  UTILITY
    # ================================================================

    def get_stats(self) -> Dict:
        """Get auth service statistics."""
        c = self._conn()
        try:
            return {
                "total_users": c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "active_users": c.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0],
                "revoked_tokens": c.execute("SELECT COUNT(*) FROM revoked_tokens").fetchone()[0],
                "active_api_keys": c.execute("SELECT COUNT(*) FROM api_keys WHERE active = 1").fetchone()[0],
                "jose_available": JOSE_AVAILABLE,
                "passlib_available": PASSLIB_AVAILABLE,
                "token_mode": "JWT" if JOSE_AVAILABLE else "HMAC-SHA256",
                "hash_mode": "bcrypt" if PASSLIB_AVAILABLE else "PBKDF2-SHA256",
            }
        finally:
            c.close()

    def ensure_admin(self, username: str = "admin", password: str = "") -> Dict:
        """Ensure an admin user exists. Creates one if no admin found."""
        c = self._conn()
        try:
            admin = c.execute("SELECT id FROM users WHERE role = 'admin' AND active = 1").fetchone()
            if admin:
                return {"message": "Admin user already exists", "user_id": admin["id"]}
            if not password:
                password = secrets.token_urlsafe(16)
            result = self.register_user(username, f"{username}@titan.local", password, "admin")
            if "error" not in result:
                result["initial_password"] = password
                result["message"] = "Admin created. SAVE the password - it won't be shown again."
            return result
        finally:
            c.close()
