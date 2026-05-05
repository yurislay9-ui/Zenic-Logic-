"""
TenantIsolation — Enforces row-level tenant isolation on all DB queries.

Provides utility functions that ensure every database query is scoped
to the current tenant, preventing cross-tenant data leakage.

Core principle: Every table that stores tenant data MUST have a
`tenant_id` column, and every query MUST include a WHERE tenant_id = ?
clause. This module provides helpers to enforce that automatically.

Design decisions:
- Uses the thread-local TenantContext from _context.py so that
  deeply-nested code (e.g. SmartMemory, MerkleLedger) can access
  the current tenant_id without explicit parameter passing.
- Provides SQL query builders that automatically inject tenant_id filters.
- Provides a validation function that can be called in tests/CI to
  ensure no unscoped queries exist.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ._context import get_current_tenant, TenantContext

logger = logging.getLogger(__name__)


class TenantIsolation:
    """Utilities for enforcing tenant isolation at the database level.

    All methods are static — this is a utility class, not stateful.
    """

    # Tables that MUST have tenant_id (validated at startup)
    REQUIRED_TENANT_TABLES: frozenset = frozenset({
        # SmartMemory tables
        "semantic_cache", "long_term_memory", "episodic_memory",
        "procedural_memory", "project_memory", "conversation_sessions",
        # MerkleLedger table
        "ledger",
        # TheoremCache table
        "theorems",
        # GraphAST table (Phase 2)
        "ast_nodes",
        # Request log table (Phase 2)
        "requests",
        # Auth tables (already have tenant_id via Phase 1)
        "users",
    })

    # Tables exempt from tenant_id requirement (system-level)
    EXEMPT_TABLES: frozenset = frozenset({
        "tenants", "tenant_usage",
        "revoked_tokens", "api_keys",
        "sqlite_master", "sqlite_sequence",
    })

    @staticmethod
    def current_tenant_id() -> str:
        """Get the effective tenant_id for the current request.

        Returns '__anonymous__' for unauthenticated requests so that
        anonymous data is isolated from all tenant data.
        """
        ctx = get_current_tenant()
        return ctx.effective_tenant_id

    @staticmethod
    def scoped_query(
        base_query: str,
        table: str,
        params: Optional[Sequence[Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[str, Sequence[Any]]:
        """Inject tenant_id filter into a SQL query.

        Takes a base query (e.g. "SELECT * FROM semantic_cache WHERE query_hash = ?")
        and injects "AND tenant_id = ?" (or "WHERE tenant_id = ?" if no WHERE clause).

        Args:
            base_query: SQL query without tenant filter.
            table: Table name (for validation).
            params: Existing query parameters.
            tenant_id: Override tenant_id (defaults to current context).

        Returns:
            Tuple of (modified_query, new_params).
        """
        if table in TenantIsolation.EXEMPT_TABLES:
            return base_query, params or ()

        tid = tenant_id or TenantIsolation.current_tenant_id()
        new_params = list(params or [])

        # Check if query already has WHERE clause
        upper = base_query.upper()
        if "WHERE" in upper:
            # Insert AND tenant_id = ? before ORDER BY, GROUP BY, LIMIT, etc.
            insert_pos = len(base_query)
            for keyword in ("ORDER BY", "GROUP BY", "LIMIT", "HAVING", "UNION"):
                idx = upper.find(keyword)
                if idx != -1 and idx < insert_pos:
                    insert_pos = idx
            modified = base_query[:insert_pos] + " AND tenant_id = ? " + base_query[insert_pos:]
        else:
            # No WHERE clause — add one
            modified = base_query + " WHERE tenant_id = ?"

        new_params.append(tid)
        return modified, tuple(new_params)

    @staticmethod
    def scoped_insert(
        table: str,
        columns: List[str],
        values: Sequence[Any],
        tenant_id: Optional[str] = None,
    ) -> Tuple[str, List[str], Sequence[Any]]:
        """Add tenant_id to an INSERT statement.

        Args:
            table: Target table name.
            columns: Column names for the INSERT.
            values: Values for the INSERT.
            tenant_id: Override tenant_id.

        Returns:
            Tuple of (modified_insert_sql, modified_columns, modified_values).
        """
        if table in TenantIsolation.EXEMPT_TABLES:
            return "", columns, values

        tid = tenant_id or TenantIsolation.current_tenant_id()
        new_columns = list(columns) + ["tenant_id"]
        new_values = list(values) + [tid]
        return "", new_columns, new_values

    @staticmethod
    def validate_schema(conn: Any) -> List[str]:
        """Validate that all required tables have a tenant_id column.

        Called at startup to catch missing columns before they cause
        data leakage.

        Args:
            conn: sqlite3.Connection with row_factory set.

        Returns:
            List of error messages (empty if all OK).
        """
        errors: List[str] = []

        for table in TenantIsolation.REQUIRED_TENANT_TABLES:
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                if "tenant_id" not in cols:
                    errors.append(f"Table '{table}' is missing 'tenant_id' column (has: {cols})")
            except Exception as e:
                errors.append(f"Cannot check table '{table}': {e}")

        return errors

    @staticmethod
    def migrate_add_tenant_id(conn: Any, table: str, default_value: str = "__anonymous__") -> bool:
        """Add tenant_id column to a table if it doesn't exist.

        Safe to call multiple times — checks first.

        Args:
            conn: sqlite3.Connection.
            table: Table name.
            default_value: Default value for existing rows.

        Returns:
            True if column was added, False if it already existed.
        """
        import sqlite3

        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "tenant_id" in cols:
                return False  # Already exists
            conn.execute(
                f'ALTER TABLE "{table}" ADD COLUMN tenant_id TEXT NOT NULL DEFAULT ?',
                (default_value,),
            )
            # Create index for fast tenant-scoped queries
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table}_tenant" ON "{table}"(tenant_id)'
            )
            conn.commit()
            logger.info("TenantIsolation: added tenant_id column to '%s' (default='%s')", table, default_value)
            return True
        except sqlite3.Error as e:
            logger.error("TenantIsolation: migration failed for '%s': %s", table, e)
            return False

    @staticmethod
    def purge_tenant_data(conn: Any, tenant_id: str, table: str) -> int:
        """Delete all data for a specific tenant from a table.

        Used for GDPR compliance (right to be forgotten) or
        tenant deprovisioning.

        Args:
            conn: sqlite3.Connection.
            tenant_id: Tenant to purge.
            table: Table to purge from.

        Returns:
            Number of rows deleted.
        """
        if table not in TenantIsolation.REQUIRED_TENANT_TABLES:
            logger.warning("Refusing to purge from non-tenant table '%s'", table)
            return 0

        try:
            cursor = conn.execute(f'DELETE FROM "{table}" WHERE tenant_id = ?', (tenant_id,))
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info("TenantIsolation: purged %d rows from '%s' for tenant '%s'", count, table, tenant_id)
            return count
        except Exception as e:
            logger.error("TenantIsolation: purge failed for '%s': %s", table, e)
            return 0
