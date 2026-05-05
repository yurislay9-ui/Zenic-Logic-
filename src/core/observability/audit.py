"""
TITAN OMNISCALE X v16 - Audit Logging (Phase 5)

Comprehensive audit trail for security and compliance.
Records all security-relevant events with trace correlation
for end-to-end observability.

Features:
- Structured audit events with trace_id correlation
- Event categorization (auth, data_access, admin, security)
- Severity levels (info, warning, critical)
- Dual output: structured log + SQLite persistence
- GDPR-compliant retention with automatic pruning
- Searchable by tenant_id, user_id, event_type, time range

Audit event types:
- AUTH_LOGIN_SUCCESS, AUTH_LOGIN_FAILURE, AUTH_LOGOUT
- AUTH_TOKEN_REFRESH, AUTH_TOKEN_REVOKED
- AUTH_API_KEY_CREATED, AUTH_API_KEY_REVOKED
- TENANT_CREATED, TENANT_UPDATED, TENANT_DEPROVISIONED
- DATA_ACCESS, DATA_MODIFICATION, DATA_EXPORT, DATA_DELETE
- SECURITY_VIOLATION, RATE_LIMIT_EXCEEDED, CIRCUIT_BREAKER_OPEN
- SAGA_STARTED, SAGA_COMPLETED, SAGA_COMPENSATED, SAGA_FAILED
- ADMIN_ROLE_CHANGE, ADMIN_CONFIG_CHANGE
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .tracing import get_current_trace_id, get_current_span_id

logger = logging.getLogger(__name__)

__all__ = [
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "get_audit_logger",
]


class AuditEventType(str, Enum):
    """Categories of auditable events."""
    # Authentication
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token.refresh"
    AUTH_TOKEN_REVOKED = "auth.token.revoked"
    AUTH_API_KEY_CREATED = "auth.api_key.created"
    AUTH_API_KEY_REVOKED = "auth.api_key.revoked"

    # Tenant management
    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"
    TENANT_DEPROVISIONED = "tenant.deprovisioned"
    TENANT_USER_ASSIGNED = "tenant.user_assigned"

    # Data access
    DATA_ACCESS = "data.access"
    DATA_MODIFICATION = "data.modification"
    DATA_EXPORT = "data.export"
    DATA_DELETE = "data.delete"

    # Security
    SECURITY_VIOLATION = "security.violation"
    RATE_LIMIT_EXCEEDED = "security.rate_limit_exceeded"
    CIRCUIT_BREAKER_OPEN = "security.circuit_breaker_open"
    INPUT_REJECTED = "security.input_rejected"
    CORS_REJECTED = "security.cors_rejected"

    # Orchestration
    SAGA_STARTED = "saga.started"
    SAGA_COMPLETED = "saga.completed"
    SAGA_COMPENSATED = "saga.compensated"
    SAGA_FAILED = "saga.failed"

    # Admin
    ADMIN_ROLE_CHANGE = "admin.role_change"
    ADMIN_CONFIG_CHANGE = "admin.config_change"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """A single auditable event.

    Attributes:
        event_id: Unique event identifier.
        event_type: Type of auditable event.
        severity: Event severity level.
        timestamp: ISO 8601 UTC timestamp.
        trace_id: Distributed trace ID for correlation.
        span_id: Current span ID.
        tenant_id: Tenant ID (or '__anonymous__').
        user_id: User ID (None for anonymous).
        ip_address: Client IP address.
        description: Human-readable event description.
        metadata: Additional structured metadata.
    """
    event_id: str = ""
    event_type: AuditEventType = AuditEventType.DATA_ACCESS
    severity: AuditSeverity = AuditSeverity.INFO
    timestamp: str = ""
    trace_id: str = ""
    span_id: str = ""
    tenant_id: str = "__anonymous__"
    user_id: Optional[int] = None
    ip_address: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = f"aud-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.trace_id:
            self.trace_id = get_current_trace_id()
        if not self.span_id:
            self.span_id = get_current_span_id()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "description": self.description,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class AuditLogger:
    """Centralized audit logging with dual output.

    Writes audit events to:
    1. Structured logger (for log aggregation systems)
    2. SQLite database (for long-term retention and queries)

    The SQLite database is per-tenant capable, supporting
    GDPR right-to-erasure via tenant-scoped pruning.
    """

    def __init__(
        self,
        db_path: str = "audit_log.sqlite",
        retention_days: int = 90,
        max_events_per_query: int = 1000,
    ) -> None:
        self._db_path = db_path
        self._retention_days = retention_days
        self._max_events_per_query = max_events_per_query
        self._lock = threading.Lock()
        self._initialized = False
        self._audit_logger = logging.getLogger("titan.audit")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the audit log SQLite database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trace_id TEXT,
                    span_id TEXT,
                    tenant_id TEXT NOT NULL,
                    user_id INTEGER,
                    ip_address TEXT,
                    description TEXT,
                    metadata TEXT,
                    created_at REAL NOT NULL
                )
            """)
            # Indexes for common query patterns
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_tenant
                ON audit_events(tenant_id, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_type
                ON audit_events(event_type, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_trace
                ON audit_events(trace_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_events(created_at)
            """)
            conn.commit()
            conn.close()
            self._initialized = True
            logger.info("AuditLogger: Database initialized at %s", self._db_path)
        except Exception as exc:
            logger.error("AuditLogger: Database initialization failed: %s", exc)
            self._initialized = False

    def log(self, event: AuditEvent) -> None:
        """Record an audit event.

        Writes to both the structured logger and the SQLite database.

        Args:
            event: The audit event to record.
        """
        # Log to structured logger
        self._audit_logger.info(
            event.description or event.event_type.value,
            extra={
                "audit_event_id": event.event_id,
                "audit_event_type": event.event_type.value,
                "audit_severity": event.severity.value,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "ip_address": event.ip_address,
                "audit_metadata": event.metadata,
            },
        )

        # Persist to SQLite
        if self._initialized:
            self._persist_event(event)

    def log_event(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        tenant_id: str = "__anonymous__",
        user_id: Optional[int] = None,
        ip_address: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Convenience method: create and log an audit event.

        Args:
            event_type: Type of auditable event.
            description: Human-readable description.
            severity: Event severity.
            tenant_id: Tenant ID.
            user_id: User ID.
            ip_address: Client IP.
            metadata: Additional metadata.

        Returns:
            The event_id of the created event.
        """
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address=ip_address,
            description=description,
            metadata=metadata or {},
        )
        self.log(event)
        return event.event_id

    def _persist_event(self, event: AuditEvent) -> None:
        """Persist an event to the SQLite database."""
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    """INSERT INTO audit_events
                       (event_id, event_type, severity, timestamp,
                        trace_id, span_id, tenant_id, user_id,
                        ip_address, description, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.event_type.value,
                        event.severity.value,
                        event.timestamp,
                        event.trace_id,
                        event.span_id,
                        event.tenant_id,
                        event.user_id,
                        event.ip_address,
                        event.description,
                        json.dumps(event.metadata, ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                conn.commit()
                conn.close()
        except Exception as exc:
            logger.debug("AuditLogger: Persist failed: %s", exc)

    # ── Query Methods ──────────────────────────────────────

    def query_events(
        self,
        tenant_id: Optional[str] = None,
        event_type: Optional[str] = None,
        user_id: Optional[int] = None,
        severity: Optional[str] = None,
        trace_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit events with filters.

        Args:
            tenant_id: Filter by tenant.
            event_type: Filter by event type.
            user_id: Filter by user.
            severity: Filter by severity.
            trace_id: Filter by trace ID.
            since: Unix timestamp lower bound.
            until: Unix timestamp upper bound.
            limit: Maximum events to return.

        Returns:
            List of matching audit event dicts.
        """
        if not self._initialized:
            return []

        conditions: List[str] = []
        params: List[Any] = []

        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if severity is not None:
            conditions.append("severity = ?")
            params.append(severity)
        if trace_id is not None:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("created_at <= ?")
            params.append(until)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit = min(limit, self._max_events_per_query)

        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM audit_events WHERE {where_clause} "
                f"ORDER BY created_at DESC LIMIT {limit}",
                params,
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("AuditLogger: Query failed: %s", exc)
            return []

    def prune_old_events(self, days: Optional[int] = None) -> int:
        """Delete events older than the retention period.

        Args:
            days: Override retention period in days.

        Returns:
            Number of events deleted.
        """
        retention = days or self._retention_days
        cutoff = time.time() - (retention * 86400)

        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(
                    "DELETE FROM audit_events WHERE created_at < ?",
                    (cutoff,),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.info("AuditLogger: Pruned %d events older than %d days", count, retention)
            return count
        except Exception as exc:
            logger.error("AuditLogger: Prune failed: %s", exc)
            return 0

    def purge_tenant_events(self, tenant_id: str) -> int:
        """Delete ALL audit events for a tenant (GDPR right to erasure).

        Args:
            tenant_id: Tenant whose events to purge.

        Returns:
            Number of events deleted.
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(
                    "DELETE FROM audit_events WHERE tenant_id = ?",
                    (tenant_id,),
                )
                count = cursor.rowcount
                conn.commit()
                conn.close()
            if count > 0:
                logger.info(
                    "AuditLogger: Purged %d events for tenant %s (GDPR)",
                    count, tenant_id[:8],
                )
            return count
        except Exception as exc:
            logger.error("AuditLogger: Tenant purge failed: %s", exc)
            return 0

    def get_event_count(self, tenant_id: Optional[str] = None) -> int:
        """Get total event count, optionally filtered by tenant."""
        if not self._initialized:
            return 0
        try:
            conn = sqlite3.connect(self._db_path)
            if tenant_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0


# ── Singleton ─────────────────────────────────────────────
_audit_logger_instance: Optional[AuditLogger] = None
_audit_logger_lock = threading.Lock()


def get_audit_logger(
    db_path: str = "audit_log.sqlite",
    retention_days: int = 90,
) -> AuditLogger:
    """Get or create the singleton AuditLogger.

    Args:
        db_path: Path to the audit log SQLite database.
        retention_days: Event retention period in days.

    Returns:
        The global AuditLogger instance.
    """
    global _audit_logger_instance
    with _audit_logger_lock:
        if _audit_logger_instance is None:
            _audit_logger_instance = AuditLogger(
                db_path=db_path,
                retention_days=retention_days,
            )
        return _audit_logger_instance
