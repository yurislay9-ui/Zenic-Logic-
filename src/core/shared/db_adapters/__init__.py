"""
TITAN OMNISCALE X v16 - Database Adapter Layer

Phase 3: Provides a unified database interface that abstracts over
SQLite (development/Termux) and PostgreSQL (production/VPS).

Strategy:
  - TITAN_ENV=development → SQLite (default, backward compatible)
  - TITAN_ENV=production  → PostgreSQL (via asyncpg / psycopg2)

All modules should use `get_db()` to obtain the correct adapter,
which provides a consistent API regardless of the backend.

Usage:
    from src.core.shared.db_adapters import get_db, DatabaseBackend

    db = get_db()
    async with db.connection() as conn:
        rows = await db.fetch_all(conn, "SELECT * FROM users WHERE tenant_id = $1", [tenant_id])
"""

from typing import Any, Dict, List, Optional
import os
import logging

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseBackend",
    "SQLiteDatabase",
    "PostgreSQLDatabase",
    "get_db",
    "get_db_backend",
    "is_postgresql",
]


class DatabaseBackend:
    """Abstract base class for database operations.

    Provides a unified async API that both SQLite and PostgreSQL
    adapters implement. All methods use parameterized queries to
    prevent SQL injection.
    """

    backend_name: str = "abstract"

    async def initialize(self) -> None:
        """Initialize database tables and connections."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close all connections gracefully."""
        raise NotImplementedError

    async def connection(self) -> Any:
        """Get a database connection/context manager."""
        raise NotImplementedError

    async def execute(self, conn: Any, query: str, params: Optional[tuple] = None) -> None:
        """Execute a write query (INSERT, UPDATE, DELETE, DDL)."""
        raise NotImplementedError

    async def fetch_one(self, conn: Any, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row as a dict."""
        raise NotImplementedError

    async def fetch_all(self, conn: Any, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all rows as a list of dicts."""
        raise NotImplementedError

    async def fetch_val(self, conn: Any, query: str, params: Optional[tuple] = None) -> Any:
        """Fetch a single scalar value."""
        raise NotImplementedError

    def format_param(self, index: int) -> str:
        """Return the parameter placeholder for position index (0-based).

        SQLite uses '?' while PostgreSQL uses '$1', '$2', etc.
        """
        raise NotImplementedError

    def adapt_query(self, query: str) -> str:
        """Adapt a SQLite-style query (?) to the backend's placeholder style.

        Replaces '?' placeholders with the appropriate format for the backend.
        """
        if self.backend_name == "sqlite":
            return query
        # Replace ? with $1, $2, etc. for PostgreSQL
        result = []
        param_idx = 1
        for char in query:
            if char == '?':
                result.append(f"${param_idx}")
                param_idx += 1
            else:
                result.append(char)
        return "".join(result)


class SQLiteDatabase(DatabaseBackend):
    """SQLite adapter — default for development and Termux.

    Uses aiosqlite for async operations. Maintains backward compatibility
    with the existing db_initializer.py connection pool.
    """

    backend_name = "sqlite"

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path
        self._pool: Optional[Any] = None

    async def initialize(self) -> None:
        """Initialize using the existing db_initializer for backward compat."""
        from src.core.shared.db_initializer import initialize_databases
        initialize_databases()
        logger.info("SQLiteDatabase: initialized with WAL mode + PRAGMA optimizations")

    async def close(self) -> None:
        from src.core.shared.db_initializer import close_all_connections
        close_all_connections()
        logger.info("SQLiteDatabase: all connections closed")

    async def connection(self) -> Any:
        """Return a synchronous SQLite connection wrapped for async compat.

        For SQLite, we use the existing connection pool from db_initializer.
        The connection is NOT async — callers should use run_in_executor
        for blocking operations, or use the sync API directly.
        """
        from src.core.shared.db_initializer import get_connection
        return get_connection(self._db_path or "graph_ast.sqlite")

    async def execute(self, conn: Any, query: str, params: Optional[tuple] = None) -> None:
        if params:
            conn.execute(query, params)
        else:
            conn.execute(query)
        conn.commit()

    async def fetch_one(self, conn: Any, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        cursor = conn.execute(query, params) if params else conn.execute(query)
        row = cursor.fetchone()
        if row is None:
            return None
        if hasattr(row, 'keys'):
            return dict(zip(row.keys(), row))
        return dict(row) if row else None

    async def fetch_all(self, conn: Any, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        cursor = conn.execute(query, params) if params else conn.execute(query)
        rows = cursor.fetchall()
        if rows and hasattr(rows[0], 'keys'):
            return [dict(zip(r.keys(), r)) for r in rows]
        return [dict(r) for r in rows]

    async def fetch_val(self, conn: Any, query: str, params: Optional[tuple] = None) -> Any:
        cursor = conn.execute(query, params) if params else conn.execute(query)
        row = cursor.fetchone()
        return row[0] if row else None

    def format_param(self, index: int) -> str:
        return "?"


class PostgreSQLDatabase(DatabaseBackend):
    """PostgreSQL adapter — production VPS deployment.

    Uses asyncpg for async operations with connection pooling.
    Supports all tenant-aware queries with proper parameterization.
    """

    backend_name = "postgresql"

    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn or os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://titan:titan@localhost:5432/titan_db"
        )
        # Convert SQLAlchemy-style DSN to asyncpg format
        self._async_dsn = self._convert_dsn(self._dsn)
        self._pool: Optional[Any] = None

    @staticmethod
    def _convert_dsn(dsn: str) -> str:
        """Convert SQLAlchemy DSN to asyncpg format.

        postgresql+asyncpg://user:pass@host:5432/db → postgresql://user:pass@host:5432/db
        postgresql+psycopg2://user:pass@host:5432/db → postgresql://user:pass@host:5432/db
        """
        if dsn.startswith("postgresql+"):
            # Strip the driver name
            idx = dsn.index("://")
            return "postgresql" + dsn[idx:]
        return dsn

    async def initialize(self) -> None:
        """Create connection pool and initialize tables."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg is required for PostgreSQL. "
                "Install with: pip install asyncpg"
            )

        self._pool = await asyncpg.create_pool(
            self._async_dsn,
            min_size=2,
            max_size=20,
            max_inactive_connection_lifetime=300,
        )
        logger.info("PostgreSQLDatabase: connection pool created (2-20 connections)")

        # Initialize tables
        await self._create_tables()

    async def _create_tables(self) -> None:
        """Create all application tables in PostgreSQL with tenant_id."""
        async with self._pool.acquire() as conn:
            # Graph AST
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ast_nodes (
                    id SERIAL PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    start_byte INTEGER NOT NULL,
                    end_byte INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    docstring TEXT,
                    complexity INTEGER DEFAULT 1,
                    connections JSONB DEFAULT '[]',
                    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
                    UNIQUE(file_path, name, node_type, tenant_id)
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_name ON ast_nodes(name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_type ON ast_nodes(node_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant ON ast_nodes(tenant_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant_file ON ast_nodes(tenant_id, file_path)")

            # Theorem Cache
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS theorems (
                    structural_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    proof_result TEXT NOT NULL,
                    solution_payload TEXT,
                    skeleton_hash TEXT,
                    hit_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_used TIMESTAMPTZ DEFAULT NOW(),
                    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
                    PRIMARY KEY (structural_hash, tenant_id)
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_skeleton ON theorems(skeleton_hash)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_theorems_tenant ON theorems(tenant_id)")

            # Merkle Ledger
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ledger (
                    id SERIAL PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    hash_sha256 TEXT NOT NULL,
                    parent_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT '__anonymous__'
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_file ON ledger(file_path)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON ledger(tenant_id)")

            # Request Log
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id SERIAL PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    model TEXT,
                    operation TEXT,
                    goal TEXT,
                    route TEXT,
                    status TEXT,
                    processing_time_ms INTEGER,
                    solver_status TEXT,
                    mcts_simulations INTEGER DEFAULT 0,
                    cache_hit INTEGER DEFAULT 0,
                    tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_time ON requests(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_tenant ON requests(tenant_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_tenant_time ON requests(tenant_id, created_at)")

            # Auth tables (users, api_keys, revoked_tokens, tenants, tenant_usage)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    active BOOLEAN DEFAULT TRUE,
                    tenant_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    last_login TIMESTAMPTZ,
                    login_count INTEGER DEFAULT 0
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti TEXT PRIMARY KEY,
                    user_id INTEGER,
                    revoked_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    permissions JSONB DEFAULT '[]',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_used TIMESTAMPTZ,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_apikeys_user ON api_keys(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_apikeys_active ON api_keys(active)")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    plan TEXT DEFAULT 'free',
                    active BOOLEAN DEFAULT TRUE,
                    config JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tenant_usage (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    period_date DATE DEFAULT CURRENT_DATE,
                    requests INTEGER DEFAULT 0,
                    tokens INTEGER DEFAULT 0,
                    compute_seconds DOUBLE PRECISION DEFAULT 0.0,
                    storage_mb DOUBLE PRECISION DEFAULT 0.0,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(tenant_id, period_date)
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant ON tenant_usage(tenant_id)")

            # SmartMemory tables
            for table_name, extra_cols in [
                ("semantic_cache", "query_hash TEXT NOT NULL, query_text TEXT NOT NULL, response_summary TEXT NOT NULL, operation TEXT DEFAULT '', goal TEXT DEFAULT '', importance REAL DEFAULT 0.5, embedding BYTEA, created_at DOUBLE PRECISION DEFAULT 0, access_count INTEGER DEFAULT 0, session_id TEXT DEFAULT '', client_id TEXT DEFAULT 'default', UNIQUE(query_hash, tenant_id)"),
                ("long_term_memory", "query_text TEXT NOT NULL, solution_summary TEXT NOT NULL, operation TEXT DEFAULT '', goal TEXT DEFAULT '', importance REAL DEFAULT 0.5, success BOOLEAN DEFAULT TRUE, embedding BYTEA, created_at DOUBLE PRECISION DEFAULT 0, access_count INTEGER DEFAULT 0, tags JSONB DEFAULT '[]', client_id TEXT DEFAULT 'default'"),
                ("episodic_memory", "event_type TEXT NOT NULL, description TEXT NOT NULL, context TEXT DEFAULT '', outcome TEXT DEFAULT '', importance REAL DEFAULT 0.5, embedding BYTEA, created_at DOUBLE PRECISION DEFAULT 0, tags JSONB DEFAULT '[]', client_id TEXT DEFAULT 'default'"),
                ("procedural_memory", "pattern_name TEXT NOT NULL UNIQUE, pattern_type TEXT DEFAULT 'strategy', description TEXT NOT NULL, success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0, success_rate REAL DEFAULT 0.0, steps JSONB DEFAULT '[]', embedding BYTEA, created_at DOUBLE PRECISION DEFAULT 0, last_used DOUBLE PRECISION DEFAULT 0, client_id TEXT DEFAULT 'default'"),
                ("project_memory", "project_name TEXT NOT NULL UNIQUE, project_type TEXT DEFAULT '', description TEXT DEFAULT '', path TEXT DEFAULT '', status TEXT DEFAULT 'active', entities JSONB DEFAULT '[]', endpoints JSONB DEFAULT '[]', config JSONB DEFAULT '{}', created_at DOUBLE PRECISION DEFAULT 0, updated_at DOUBLE PRECISION DEFAULT 0, notes TEXT DEFAULT '', client_id TEXT DEFAULT 'default'"),
                ("conversation_sessions", "started_at DOUBLE PRECISION DEFAULT 0, ended_at DOUBLE PRECISION DEFAULT 0, summary TEXT DEFAULT '', importance REAL DEFAULT 0.5, exchange_count INTEGER DEFAULT 0, client_id TEXT DEFAULT 'default'"),
            ]:
                pk = "id TEXT PRIMARY KEY" if table_name == "conversation_sessions" else "id SERIAL PRIMARY KEY"
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        {pk},
                        {extra_cols},
                        tenant_id TEXT DEFAULT '__anonymous__'
                    )
                """)
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_tenant ON {table_name}(tenant_id)")
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_tenant_client ON {table_name}(tenant_id, client_id)")

        logger.info("PostgreSQLDatabase: all tables created with tenant_id indexes")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQLDatabase: connection pool closed")

    async def connection(self) -> Any:
        """Acquire a connection from the pool."""
        if self._pool is None:
            await self.initialize()
        return self._pool.acquire()

    async def execute(self, conn: Any, query: str, params: Optional[tuple] = None) -> None:
        query = self.adapt_query(query)
        if params:
            await conn.execute(query, *params)
        else:
            await conn.execute(query)

    async def fetch_one(self, conn: Any, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        query = self.adapt_query(query)
        if params:
            row = await conn.fetchrow(query, *params)
        else:
            row = await conn.fetchrow(query)
        return dict(row) if row else None

    async def fetch_all(self, conn: Any, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        query = self.adapt_query(query)
        if params:
            rows = await conn.fetch(query, *params)
        else:
            rows = await conn.fetch(query)
        return [dict(r) for r in rows]

    async def fetch_val(self, conn: Any, query: str, params: Optional[tuple] = None) -> Any:
        query = self.adapt_query(query)
        if params:
            return await conn.fetchval(query, *params)
        return await conn.fetchval(query)

    def format_param(self, index: int) -> str:
        return f"${index + 1}"


# ── Singleton instance ────────────────────────────────────
_db_instance: Optional[DatabaseBackend] = None


def is_postgresql() -> bool:
    """Check if the configured database backend is PostgreSQL."""
    return os.environ.get("TITAN_ENV") == "production" or bool(os.environ.get("DATABASE_URL", "").startswith("postgresql"))


def get_db_backend() -> str:
    """Return the active database backend name."""
    return "postgresql" if is_postgresql() else "sqlite"


def get_db() -> DatabaseBackend:
    """Get or create the singleton database adapter.

    Uses environment variables to determine the backend:
    - TITAN_ENV=production or DATABASE_URL starts with 'postgresql' → PostgreSQLDatabase
    - Otherwise → SQLiteDatabase (default, backward compatible)
    """
    global _db_instance
    if _db_instance is not None:
        return _db_instance

    if is_postgresql():
        dsn = os.environ.get("DATABASE_URL", "")
        _db_instance = PostgreSQLDatabase(dsn=dsn)
        logger.info("Database backend: PostgreSQL (production)")
    else:
        _db_instance = SQLiteDatabase()
        logger.info("Database backend: SQLite (development)")

    return _db_instance


def reset_db() -> None:
    """Reset the singleton — mainly for testing."""
    global _db_instance
    _db_instance = None
