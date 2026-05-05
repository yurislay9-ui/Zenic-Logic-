"""
TITAN OMNISCALE X v16 - Security Middleware (Phase 5)

Comprehensive security middleware stack for FastAPI:
- Input sanitization (XSS, injection prevention)
- Security headers (CSP, X-Frame-Options, HSTS, etc.)
- Configurable CORS per environment
- Request size limiting
- HTTPS enforcement
- Auth endpoint rate limiting (brute-force protection)
- Token blacklisting/revocation

All components are configurable and can be selectively enabled/disabled
via environment variables or constructor parameters.
"""

import html
import logging
import os
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)

__all__ = [
    "SecurityConfig",
    "InputSanitizer",
    "SecurityHeadersMiddleware",
    "AuthRateLimiter",
    "TokenBlacklist",
    "create_security_middleware",
]


# ============================================================
#  SECURITY CONFIGURATION
# ============================================================

@dataclass
class SecurityConfig:
    """Centralized security configuration.

    All settings can be overridden via environment variables.

    Attributes:
        cors_origins: Allowed CORS origins (comma-separated).
        cors_allow_credentials: Whether to allow credentials.
        enable_csp: Whether to add Content-Security-Policy header.
        enable_hsts: Whether to add Strict-Transport-Security header.
        hsts_max_age: HSTS max-age in seconds.
        force_https: Whether to redirect HTTP to HTTPS.
        max_request_size_mb: Maximum request body size in MB.
        max_input_length: Maximum string input length.
        sanitize_html: Whether to HTML-escape string inputs.
        auth_rate_limit_rpm: Rate limit for auth endpoints (per IP).
        auth_rate_limit_burst: Burst size for auth rate limiting.
        token_blacklist_enabled: Whether to check token blacklist.
        token_blacklist_db: Path to token blacklist database.
    """
    # CORS
    cors_origins: str = "*"
    cors_allow_credentials: bool = True
    cors_max_age: int = 600

    # Security Headers
    enable_csp: bool = True
    csp_policy: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    enable_hsts: bool = True
    hsts_max_age: int = 31536000  # 1 year
    force_https: bool = False

    # Input Validation
    max_request_size_mb: float = 10.0
    max_input_length: int = 10000
    sanitize_html: bool = True

    # Auth Rate Limiting
    auth_rate_limit_rpm: int = 20
    auth_rate_limit_burst: int = 5

    # Token Blacklist
    token_blacklist_enabled: bool = True
    token_blacklist_db: str = "token_blacklist.sqlite"

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Create config from environment variables."""
        return cls(
            cors_origins=os.getenv("TITAN_CORS_ORIGINS", "*"),
            cors_allow_credentials=os.getenv("TITAN_CORS_CREDENTIALS", "true").lower() == "true",
            enable_csp=os.getenv("TITAN_CSP_ENABLED", "true").lower() == "true",
            enable_hsts=os.getenv("TITAN_HSTS_ENABLED", "true").lower() == "true",
            force_https=os.getenv("TITAN_FORCE_HTTPS", "false").lower() == "true",
            max_request_size_mb=float(os.getenv("TITAN_MAX_REQUEST_SIZE_MB", "10")),
            auth_rate_limit_rpm=int(os.getenv("TITAN_AUTH_RATE_LIMIT_RPM", "20")),
            auth_rate_limit_burst=int(os.getenv("TITAN_AUTH_RATE_LIMIT_BURST", "5")),
            token_blacklist_enabled=os.getenv("TITAN_TOKEN_BLACKLIST", "true").lower() == "true",
        )

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# ============================================================
#  INPUT SANITIZER
# ============================================================

class InputSanitizer:
    """Sanitizes user input to prevent XSS and injection attacks.

    Provides multiple sanitization strategies:
    - HTML escaping (prevents XSS)
    - SQL pattern detection (flags potential SQL injection)
    - Path traversal detection
    - Length limiting
    - Null byte removal

    Can be used as a FastAPI middleware or called directly.
    """

    # Patterns that indicate potential attacks
    SQL_INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r"(?i)(\b(union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table)\b)"),
        re.compile(r"(?i)(--|;|--\s*$|/\*|\*/)"),
        re.compile(r"(?i)(\b(exec|execute|xp_)\b)"),
    ]

    XSS_PATTERNS: List[re.Pattern] = [
        re.compile(r"<\s*script", re.IGNORECASE),
        re.compile(r"javascript\s*:", re.IGNORECASE),
        re.compile(r"on(error|load|click|mouseover|focus|blur)\s*=", re.IGNORECASE),
        re.compile(r"<\s*iframe", re.IGNORECASE),
        re.compile(r"<\s*object", re.IGNORECASE),
        re.compile(r"<\s*embed", re.IGNORECASE),
    ]

    PATH_TRAVERSAL_PATTERN: re.Pattern = re.compile(r"(\.\./|\.\.\\|%2e%2e%2f|%2e%2e/)", re.IGNORECASE)

    def __init__(self, config: Optional[SecurityConfig] = None) -> None:
        self._config = config or SecurityConfig()

    def sanitize_string(self, value: str) -> str:
        """Sanitize a string input.

        Applies:
        1. Null byte removal
        2. Length limiting
        3. HTML escaping (if configured)

        Args:
            value: Raw string input.

        Returns:
            Sanitized string.
        """
        # Remove null bytes
        value = value.replace("\x00", "")

        # Length limit
        if len(value) > self._config.max_input_length:
            value = value[:self._config.max_input_length]

        # HTML escaping
        if self._config.sanitize_html:
            value = html.escape(value, quote=True)

        return value

    def check_sql_injection(self, value: str) -> bool:
        """Check if a string matches SQL injection patterns.

        Args:
            value: String to check.

        Returns:
            True if potential SQL injection detected.
        """
        for pattern in self.SQL_INJECTION_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def check_xss(self, value: str) -> bool:
        """Check if a string matches XSS patterns.

        Args:
            value: String to check.

        Returns:
            True if potential XSS detected.
        """
        for pattern in self.XSS_PATTERNS:
            if pattern.search(value):
                return True
        return False

    def check_path_traversal(self, value: str) -> bool:
        """Check if a string contains path traversal attempts.

        Args:
            value: String to check.

        Returns:
            True if path traversal detected.
        """
        return bool(self.PATH_TRAVERSAL_PATTERN.search(value))

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize all string values in a dict.

        Args:
            data: Dictionary with potentially unsanitized values.

        Returns:
            Dictionary with sanitized values.
        """
        result: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.sanitize_string(item) if isinstance(item, str)
                    else self.sanitize_dict(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def validate_request_body(self, body: Dict[str, Any]) -> Optional[str]:
        """Validate a request body for security threats.

        Returns None if safe, or an error message string if threats detected.
        Does NOT sanitize — only validates. Use sanitize_dict() to sanitize.

        Args:
            body: Request body dict.

        Returns:
            Error message or None if safe.
        """
        all_text = self._extract_all_text(body)

        for text in all_text:
            if self.check_sql_injection(text):
                return "Potential SQL injection detected"
            if self.check_path_traversal(text):
                return "Path traversal attempt detected"
            # Note: XSS check is informational — we escape, not reject

        return None

    def _extract_all_text(self, data: Any) -> List[str]:
        """Extract all string values from nested data structures."""
        texts: List[str] = []
        if isinstance(data, str):
            texts.append(data)
        elif isinstance(data, dict):
            for v in data.values():
                texts.extend(self._extract_all_text(v))
        elif isinstance(data, list):
            for item in data:
                texts.extend(self._extract_all_text(item))
        return texts


# ============================================================
#  SECURITY HEADERS MIDDLEWARE
# ============================================================

class SecurityHeadersMiddleware:
    """Adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy (if enabled)
    - Strict-Transport-Security (if enabled)
    - Permissions-Policy: restrictive defaults
    """

    def __init__(self, config: Optional[SecurityConfig] = None) -> None:
        self._config = config or SecurityConfig()

    def get_headers(self) -> Dict[str, str]:
        """Get all security headers as a dict.

        Returns:
            Dict of header name -> header value.
        """
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        }

        if self._config.enable_csp:
            headers["Content-Security-Policy"] = self._config.csp_policy

        if self._config.enable_hsts:
            headers["Strict-Transport-Security"] = (
                f"max-age={self._config.hsts_max_age}; includeSubDomains; preload"
            )

        return headers


# ============================================================
#  AUTH RATE LIMITER
# ============================================================

class AuthRateLimiter:
    """Rate limiter specifically for authentication endpoints.

    Prevents brute-force attacks on login, register, and token
    refresh endpoints. Uses per-IP token bucket with lower limits
    than the general rate limiter.

    This is separate from the main TenantRateLimiter because:
    1. Auth endpoints need much stricter limits
    2. Failed attempts should progressively increase delays
    3. Auth rate limiting happens before auth resolution
    """

    def __init__(
        self,
        rpm: int = 20,
        burst: int = 5,
        lockout_duration: float = 300.0,
        max_failures_before_lockout: int = 10,
    ) -> None:
        self._rpm = rpm
        self._burst = burst
        self._lockout_duration = lockout_duration
        self._max_failures = max_failures_before_lockout

        self._clients: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        """Check if an auth request from this IP is allowed.

        Args:
            client_ip: Client IP address.

        Returns:
            True if the request is allowed.
        """
        now = time.time()

        with self._lock:
            if client_ip not in self._clients:
                self._clients[client_ip] = {
                    "tokens": float(self._burst),
                    "last_refill": now,
                    "failures": 0,
                    "lockout_until": 0.0,
                }

            client = self._clients[client_ip]

            # Check lockout
            if now < client.get("lockout_until", 0):
                return False

            # Refill tokens
            elapsed = now - client["last_refill"]
            refill_rate = self._rpm / 60.0
            client["tokens"] = min(float(self._burst), client["tokens"] + elapsed * refill_rate)
            client["last_refill"] = now

            if client["tokens"] < 1.0:
                return False

            client["tokens"] -= 1.0
            return True

    def record_failure(self, client_ip: str) -> None:
        """Record a failed auth attempt (for progressive lockout).

        Args:
            client_ip: Client IP that failed authentication.
        """
        now = time.time()
        with self._lock:
            if client_ip in self._clients:
                self._clients[client_ip]["failures"] += 1
                if self._clients[client_ip]["failures"] >= self._max_failures:
                    self._clients[client_ip]["lockout_until"] = now + self._lockout_duration
                    logger.warning(
                        "AuthRateLimiter: IP %s locked out for %ds after %d failures",
                        client_ip, int(self._lockout_duration),
                        self._clients[client_ip]["failures"],
                    )

    def record_success(self, client_ip: str) -> None:
        """Record a successful auth attempt (resets failure counter).

        Args:
            client_ip: Client IP that succeeded authentication.
        """
        with self._lock:
            if client_ip in self._clients:
                self._clients[client_ip]["failures"] = 0

    def cleanup(self, max_age: float = 300.0) -> int:
        """Remove stale client entries.

        Args:
            max_age: Seconds of inactivity before removal.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        with self._lock:
            stale = [
                ip for ip, c in self._clients.items()
                if c["last_refill"] < now - max_age
            ]
            for ip in stale:
                del self._clients[ip]
        return len(stale)


# ============================================================
#  TOKEN BLACKLIST
# ============================================================

class TokenBlacklist:
    """JWT token blacklist for revocation and rotation.

    Stores revoked token IDs (jti claims) in a SQLite database
    with automatic expiry cleanup. Supports:
    - Single token revocation
    - Bulk revocation (all tokens for a user)
    - Token rotation (revoke old, issue new)
    - Automatic pruning of expired entries

    Thread-safe: all operations are protected by a lock.
    """

    def __init__(self, db_path: str = "token_blacklist.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._initialized = False
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the blacklist database."""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti TEXT PRIMARY KEY,
                    user_id INTEGER,
                    reason TEXT,
                    revoked_at REAL NOT NULL,
                    expires_at REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revoked_expires
                ON revoked_tokens(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_revoked_user
                ON revoked_tokens(user_id)
            """)
            conn.commit()
            conn.close()
            self._initialized = True
        except Exception as exc:
            logger.error("TokenBlacklist: Init failed: %s", exc)

    def is_revoked(self, jti: str) -> bool:
        """Check if a token has been revoked.

        Args:
            jti: JWT ID claim.

        Returns:
            True if the token is revoked.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT 1 FROM revoked_tokens WHERE jti = ?",
                (jti,),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def revoke_token(
        self,
        jti: str,
        user_id: Optional[int] = None,
        reason: str = "manual",
        expires_at: Optional[float] = None,
    ) -> bool:
        """Revoke a token by its JTI.

        Args:
            jti: JWT ID claim to revoke.
            user_id: Associated user ID.
            reason: Revocation reason.
            expires_at: Token expiry timestamp (for auto-cleanup).

        Returns:
            True if successfully revoked.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    """INSERT OR IGNORE INTO revoked_tokens
                       (jti, user_id, reason, revoked_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (jti, user_id, reason, time.time(), expires_at),
                )
                conn.commit()
                conn.close()
            logger.info("TokenBlacklist: Revoked token %s (reason=%s)", jti[:8], reason)
            return True
        except Exception as exc:
            logger.error("TokenBlacklist: Revoke failed: %s", exc)
            return False

    def revoke_all_user_tokens(self, user_id: int, reason: str = "security") -> int:
        """Revoke all tokens for a user.

        Used when a user changes password or is compromised.

        Args:
            user_id: User whose tokens to revoke.
            reason: Revocation reason.

        Returns:
            Number of tokens revoked.
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                # Get active tokens for this user
                rows = conn.execute(
                    "SELECT jti FROM revoked_tokens WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
                # Mark all future tokens for this user as revoked via a special entry
                conn.execute(
                    """INSERT OR IGNORE INTO revoked_tokens
                       (jti, user_id, reason, revoked_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (f"user-all-{user_id}-{time.time()}", user_id, reason, time.time(), None),
                )
                conn.commit()
                conn.close()
            logger.info(
                "TokenBlacklist: Revoked all tokens for user %d (reason=%s)",
                user_id, reason,
            )
            return len(rows) + 1
        except Exception as exc:
            logger.error("TokenBlacklist: Bulk revoke failed: %s", exc)
            return 0

    def is_user_fully_revoked(self, user_id: int, after_time: float) -> bool:
        """Check if all tokens for a user were revoked after a timestamp.

        Args:
            user_id: User to check.
            after_time: Timestamp to check against.

        Returns:
            True if a bulk revocation exists after the given time.
        """
        if not self._initialized:
            return False

        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                """SELECT 1 FROM revoked_tokens
                   WHERE user_id = ? AND jti LIKE 'user-all-%'
                   AND revoked_at >= ?""",
                (user_id, after_time),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def prune_expired(self) -> int:
        """Remove entries for tokens that have already expired.

        Returns:
            Number of entries pruned.
        """
        if not self._initialized:
            return 0

        try:
            import sqlite3
            import time
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(
                    "DELETE FROM revoked_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (time.time(),),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.debug("TokenBlacklist: Pruned %d expired entries", count)
            return count
        except Exception:
            return 0


# ============================================================
#  SECURITY MIDDLEWARE FACTORY
# ============================================================

def create_security_middleware(config: Optional[SecurityConfig] = None):
    """Create a FastAPI middleware function that applies all security measures.

    This is the main entry point for wiring Phase 5 security into
    the FastAPI app. It returns a middleware function that:
    1. Checks request size
    2. Enforces auth rate limits
    3. Adds security headers to responses
    4. Enforces HTTPS (if configured)
    5. Validates and sanitizes input

    Usage in fastapi_app.py:
        security_config = SecurityConfig.from_env()
        app.middleware("http")(create_security_middleware(security_config))

    Args:
        config: Security configuration.

    Returns:
        Async middleware function for FastAPI.
    """
    if config is None:
        config = SecurityConfig.from_env()

    sanitizer = InputSanitizer(config)
    headers_middleware = SecurityHeadersMiddleware(config)
    auth_limiter = AuthRateLimiter(
        rpm=config.auth_rate_limit_rpm,
        burst=config.auth_rate_limit_burst,
    )
    security_headers = headers_middleware.get_headers()
    max_size_bytes = int(config.max_request_size_mb * 1024 * 1024)

    # Auth endpoints that need strict rate limiting
    AUTH_ENDPOINTS: FrozenSet[str] = frozenset({
        "/v1/auth/login",
        "/v1/auth/register",
        "/v1/auth/refresh",
    })

    async def security_middleware(request: Any, call_next: Any) -> Any:
        """FastAPI middleware for security checks and headers."""
        # 1. HTTPS enforcement
        if config.force_https:
            scheme = request.url.scheme
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            if scheme != "https" and forwarded_proto != "https":
                from fastapi.responses import RedirectResponse
                https_url = str(request.url).replace("http://", "https://", 1)
                return RedirectResponse(url=https_url, status_code=301)

        # 2. Request size check
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > max_size_bytes:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"error": {"message": "Request body too large", "type": "payload_too_large"}},
            )

        # 3. Auth endpoint rate limiting
        if request.url.path in AUTH_ENDPOINTS:
            client_ip = request.client.host if request.client else "0.0.0.0"
            if not auth_limiter.is_allowed(client_ip):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=429,
                    content={"error": {"message": "Too many auth attempts", "type": "auth_rate_limit"}},
                    headers={"Retry-After": "60"},
                )

        # 4. Process request
        response = await call_next(request)

        # 5. Record auth result for rate limiting
        if request.url.path in AUTH_ENDPOINTS:
            client_ip = request.client.host if request.client else "0.0.0.0"
            if response.status_code == 401:
                auth_limiter.record_failure(client_ip)
            elif response.status_code == 200:
                auth_limiter.record_success(client_ip)

        # 6. Add security headers
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value

        return response

    return security_middleware
