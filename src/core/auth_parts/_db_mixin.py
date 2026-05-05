"""
Database and password management mixin for AuthService.
"""

from ._imports import (
    logger, sqlite3, secrets, hashlib, threading,
    Path, datetime, timezone, _pwd_context,
    PBKDF2_ITERATIONS, PASSLIB_AVAILABLE,
)


class DbPasswordMixin:
    """Database initialization and password management for AuthService."""

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
                "CREATE INDEX IF NOT EXISTS idx_apikeys_hash ON api_keys(key_hash, active)",
            ]:
                c.execute(idx)
            c.commit()
        finally:
            c.close()

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt (preferred) or PBKDF2-SHA256 (fallback)."""
        if _pwd_context:
            return _pwd_context.hash(password)
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
        return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${dk.hex()}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password against hash."""
        if not password or not hashed:
            return False
        if _pwd_context:
            try:
                return _pwd_context.verify(password, hashed)
            except Exception:
                logger.debug("passlib verify failed, falling back to pbkdf2")
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
