"""
Tenant management mixin for AuthService.

Provides multi-tenant support: tenant CRUD, user-tenant assignment,
per-tenant quotas, and tenant-aware configuration.

Phase 1 SaaS Fundamentals — adds tenants table, tenant-aware users,
and plan-based resource quotas.
"""

from ._imports import (
    logger, sqlite3, secrets, json, threading,
    datetime, timezone, ROLE_HIERARCHY,
)
from typing import Dict, List, Optional, Any


# ── Plan definitions with resource quotas ──────────────────
PLAN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "free": {
        "display_name": "Free",
        "max_requests_per_minute": 10,
        "max_requests_per_day": 500,
        "max_tokens_per_day": 50000,
        "max_concurrent": 2,
        "max_storage_mb": 50,
        "features": ["basic_pipeline", "chat_completions"],
    },
    "pro": {
        "display_name": "Professional",
        "max_requests_per_minute": 60,
        "max_requests_per_day": 5000,
        "max_tokens_per_day": 500000,
        "max_concurrent": 10,
        "max_storage_mb": 500,
        "features": [
            "basic_pipeline", "chat_completions", "app_generation",
            "automation_generation", "schema_design", "thinking_engine",
            "reasoning_engine", "logic_chains",
        ],
    },
    "enterprise": {
        "display_name": "Enterprise",
        "max_requests_per_minute": 200,
        "max_requests_per_day": 50000,
        "max_tokens_per_day": 5000000,
        "max_concurrent": 50,
        "max_storage_mb": 5000,
        "features": "all",
    },
}


class TenantMixin:
    """Tenant management for AuthService.

    Requires ``_conn()``, ``_lock``, and ``init_db()`` from other mixins.
    Call ``init_tenant_tables()`` from ``init_db()`` to create the schema.
    """

    # ── Schema initialization ──────────────────────────────

    def init_tenant_tables(self) -> None:
        """Create tenants and tenant_usage tables if not exists.

        Must be called from ``init_db()`` after the core tables exist.
        Also migrates the users table to add ``tenant_id`` column.
        """
        c = self._conn()
        try:
            c.execute("""CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                config TEXT DEFAULT '{}',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            c.execute("""CREATE TABLE IF NOT EXISTS tenant_usage (
                tenant_id TEXT NOT NULL,
                date TEXT NOT NULL,
                requests_count INTEGER DEFAULT 0,
                tokens_count INTEGER DEFAULT 0,
                compute_seconds REAL DEFAULT 0.0,
                storage_mb REAL DEFAULT 0.0,
                PRIMARY KEY (tenant_id, date),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id))""")
            # Add tenant_id column to users (migration-safe)
            cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
            if "tenant_id" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN tenant_id TEXT REFERENCES tenants(id)")
            # Indexes
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_tenants_name ON tenants(name)",
                "CREATE INDEX IF NOT EXISTS idx_tenants_plan ON tenants(plan)",
                "CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(active)",
                "CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)",
                "CREATE INDEX IF NOT EXISTS idx_usage_tenant_date ON tenant_usage(tenant_id, date)",
            ]:
                c.execute(idx_sql)
            c.commit()
            logger.info("AuthService: tenant tables initialized")
        except sqlite3.Error as e:
            logger.error("AuthService: init_tenant_tables error: %s", e)
        finally:
            c.close()

    # ── Tenant CRUD ────────────────────────────────────────

    def create_tenant(
        self,
        name: str,
        plan: str = "free",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new tenant with the given plan.

        Args:
            name: Human-readable tenant name (e.g. company name).
            plan: One of 'free', 'pro', 'enterprise'.
            config: Optional per-tenant config overrides.

        Returns:
            Dict with tenant info on success, or ``{'error': ...}`` on failure.
        """
        if plan not in PLAN_DEFINITIONS:
            return {"error": f"Invalid plan: {plan}. Must be one of: {list(PLAN_DEFINITIONS)}"}
        if not name or len(name) < 2:
            return {"error": "Tenant name must be at least 2 characters"}

        tenant_id = f"tn_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps(config or {})

        c = self._conn()
        try:
            with self._lock:
                c.execute(
                    "INSERT INTO tenants (id, name, plan, config, active, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (tenant_id, name, plan, config_json, now, now),
                )
                c.commit()
            logger.info("AuthService: tenant created %s (%s, plan=%s)", tenant_id, name, plan)
            return {
                "tenant_id": tenant_id,
                "name": name,
                "plan": plan,
                "quotas": PLAN_DEFINITIONS[plan],
                "message": "Tenant created successfully",
            }
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID. Returns dict or None."""
        c = self._conn()
        try:
            row = c.execute(
                "SELECT id, name, plan, config, active, created_at, updated_at "
                "FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            try:
                result["config"] = json.loads(result.get("config", "{}"))
            except (json.JSONDecodeError, TypeError):
                result["config"] = {}
            result["quotas"] = PLAN_DEFINITIONS.get(result["plan"], PLAN_DEFINITIONS["free"])
            return result
        finally:
            c.close()

    def update_tenant(self, tenant_id: str, **fields: Any) -> Dict[str, Any]:
        """Update tenant fields (name, plan, config, active)."""
        allowed = {"name", "plan", "config", "active"}
        updates: Dict[str, Any] = {}
        for k, v in fields.items():
            if k in allowed:
                if k == "plan" and v not in PLAN_DEFINITIONS:
                    return {"error": f"Invalid plan: {v}"}
                if k == "config":
                    updates[k] = json.dumps(v)
                else:
                    updates[k] = v
        if not updates:
            return {"error": "No valid fields to update"}

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [tenant_id]

        c = self._conn()
        try:
            with self._lock:
                if c.execute(f"UPDATE tenants SET {set_clause} WHERE id = ?", vals).rowcount == 0:
                    return {"error": "Tenant not found"}
                c.commit()
            return self.get_tenant(tenant_id) or {"error": "Tenant not found after update"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Soft-delete a tenant (sets active=0)."""
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "UPDATE tenants SET active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), tenant_id),
                )
                c.commit()
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.error("AuthService: deactivate_tenant error: %s", e)
            return False
        finally:
            c.close()

    def list_tenants(self, plan: str = "", active_only: bool = True) -> List[Dict[str, Any]]:
        """List tenants with optional plan filter."""
        c = self._conn()
        try:
            query = "SELECT id, name, plan, config, active, created_at, updated_at FROM tenants"
            conditions: List[str] = []
            params: List[Any] = []
            if active_only:
                conditions.append("active = 1")
            if plan:
                conditions.append("plan = ?")
                params.append(plan)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            rows = c.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()

    # ── User-Tenant assignment ──────────────────────────────

    def assign_user_to_tenant(self, user_id: int, tenant_id: str) -> Dict[str, Any]:
        """Assign a user to a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}
        if not tenant.get("active"):
            return {"error": "Tenant is deactivated"}
        c = self._conn()
        try:
            with self._lock:
                if c.execute("UPDATE users SET tenant_id = ?, updated_at = ? WHERE id = ?",
                             (tenant_id, datetime.now(timezone.utc).isoformat(), user_id)).rowcount == 0:
                    return {"error": "User not found"}
                c.commit()
            return {"user_id": user_id, "tenant_id": tenant_id, "message": "User assigned to tenant"}
        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}
        finally:
            c.close()

    def get_user_tenant(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the tenant a user belongs to."""
        c = self._conn()
        try:
            row = c.execute("SELECT tenant_id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row or not row["tenant_id"]:
                return None
            return self.get_tenant(row["tenant_id"])
        finally:
            c.close()

    def list_tenant_users(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all users in a tenant."""
        c = self._conn()
        try:
            rows = c.execute(
                "SELECT id, username, email, role, active, created_at, last_login "
                "FROM users WHERE tenant_id = ? ORDER BY id",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()

    # ── Usage tracking ──────────────────────────────────────

    def record_usage(
        self,
        tenant_id: str,
        requests: int = 1,
        tokens: int = 0,
        compute_seconds: float = 0.0,
    ) -> bool:
        """Record usage for a tenant on the current date (upsert)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        c = self._conn()
        try:
            with self._lock:
                c.execute(
                    "INSERT INTO tenant_usage (tenant_id, date, requests_count, tokens_count, compute_seconds) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, date) DO UPDATE SET "
                    "requests_count = requests_count + ?, "
                    "tokens_count = tokens_count + ?, "
                    "compute_seconds = compute_seconds + ?",
                    (tenant_id, today, requests, tokens, compute_seconds,
                     requests, tokens, compute_seconds),
                )
                c.commit()
            return True
        except sqlite3.Error as e:
            logger.error("AuthService: record_usage error: %s", e)
            return False
        finally:
            c.close()

    def get_tenant_usage(self, tenant_id: str, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get usage for a tenant on a specific date (default: today)."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        c = self._conn()
        try:
            row = c.execute(
                "SELECT tenant_id, date, requests_count, tokens_count, compute_seconds, storage_mb "
                "FROM tenant_usage WHERE tenant_id = ? AND date = ?",
                (tenant_id, date),
            ).fetchone()
            return dict(row) if row else None
        finally:
            c.close()

    def check_tenant_quota(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant has exceeded any quota. Returns quota status."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "error": "Tenant not found"}

        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        usage = self.get_tenant_usage(tenant_id) or {
            "requests_count": 0,
            "tokens_count": 0,
            "compute_seconds": 0.0,
        }

        max_rpm = quotas.get("max_requests_per_minute", 10)
        max_rpd = quotas.get("max_requests_per_day", 500)
        max_tpd = quotas.get("max_tokens_per_day", 50000)

        requests_today = usage.get("requests_count", 0)
        tokens_today = usage.get("tokens_count", 0)

        if requests_today >= max_rpd:
            return {
                "allowed": False,
                "reason": f"Daily request limit reached ({requests_today}/{max_rpd})",
                "plan": plan,
                "usage": usage,
                "quotas": quotas,
            }
        if tokens_today >= max_tpd:
            return {
                "allowed": False,
                "reason": f"Daily token limit reached ({tokens_today}/{max_tpd})",
                "plan": plan,
                "usage": usage,
                "quotas": quotas,
            }
        return {
            "allowed": True,
            "plan": plan,
            "usage": usage,
            "quotas": quotas,
            "remaining_requests": max_rpd - requests_today,
            "remaining_tokens": max_tpd - tokens_today,
        }

    def get_tenant_features(self, tenant_id: str) -> List[str]:
        """Get feature list for tenant's plan."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return []
        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        features = quotas.get("features", [])
        if features == "all":
            # Enterprise gets everything
            all_features = set()
            for pq in PLAN_DEFINITIONS.values():
                f = pq.get("features", [])
                if isinstance(f, list):
                    all_features.update(f)
            return sorted(all_features)
        return features if isinstance(features, list) else []

    def deprovision_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Hard-delete a tenant and ALL associated data across all databases.

        This is the GDPR 'right to be forgotten' / full deprovisioning flow.
        It purges data from: SmartMemory, MerkleLedger, TheoremCache,
        GraphAST, RequestLog, auth DB (users unassigned, tenant deactivated).

        Args:
            tenant_id: Tenant identifier to deprovision.

        Returns:
            Dict with purge summary on success, or {'error': ...} on failure.
        """
        from src.core.patterns.resilience.retry import RetryConfig, with_retry

        # Validate tenant exists
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}

        purge_summary: Dict[str, int] = {}
        total_purged = 0

        # 1. Deactivate tenant first (prevents new data while purging)
        self.deactivate_tenant(tenant_id)

        # 2. Unassign all users from this tenant
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "UPDATE users SET tenant_id = NULL, updated_at = ? WHERE tenant_id = ?",
                    (datetime.now(timezone.utc).isoformat(), tenant_id),
                )
                c.commit()
                purge_summary["users_unassigned"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: unassign users error: %s", e)
        finally:
            c.close()

        # 3. Delete tenant_usage rows
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute(
                    "DELETE FROM tenant_usage WHERE tenant_id = ?", (tenant_id,)
                )
                c.commit()
                purge_summary["tenant_usage_deleted"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: tenant_usage delete error: %s", e)
        finally:
            c.close()

        # 4. Purge data from all tenant-aware databases (with retry)
        _purge_retry = RetryConfig(
            max_attempts=3, base_delay=0.5, max_delay=5.0,
            backoff_strategy="exponential", jitter=True,
            retryable_exceptions=(Exception,),
        )

        # SmartMemory purge
        try:
            from src.core.smart_memory import SmartMemory
            sm = SmartMemory()
            count = with_retry(sm.purge_tenant_data, _purge_retry, tenant_id)
            purge_summary["smart_memory_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: SmartMemory purge failed: %s", e)
            purge_summary["smart_memory_purged"] = -1

        # MerkleLedger purge
        try:
            from src.core.level7_merkle_ledger.ledger import MerkleLedger
            ml = MerkleLedger()
            count = with_retry(ml.purge_tenant_ledger, _purge_retry, tenant_id)
            purge_summary["merkle_ledger_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: MerkleLedger purge failed: %s", e)
            purge_summary["merkle_ledger_purged"] = -1

        # TheoremCache purge
        try:
            from src.core.level8_theorem_cache.cache import TheoremCache
            tc = TheoremCache()
            count = with_retry(tc.purge_tenant_cache, _purge_retry, tenant_id)
            purge_summary["theorem_cache_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: TheoremCache purge failed: %s", e)
            purge_summary["theorem_cache_purged"] = -1

        # GraphAST purge
        try:
            from src.core.level3_graph_ast.engine import GraphASTEngine
            gae = GraphASTEngine()
            count = with_retry(gae.purge_tenant_data, _purge_retry, tenant_id)
            purge_summary["graph_ast_purged"] = count
            total_purged += count
        except Exception as e:
            logger.warning("Deprovision: GraphAST purge failed: %s", e)
            purge_summary["graph_ast_purged"] = -1

        # RequestLog purge
        try:
            from src.core.shared.db_initializer import get_connection
            conn = get_connection("request_log.sqlite")
            cursor = conn.execute("DELETE FROM requests WHERE tenant_id = ?", (tenant_id,))
            conn.commit()
            purge_summary["request_log_purged"] = cursor.rowcount
            total_purged += cursor.rowcount
        except Exception as e:
            logger.warning("Deprovision: RequestLog purge failed: %s", e)
            purge_summary["request_log_purged"] = -1

        # 5. Delete tenant row from auth DB
        c = self._conn()
        try:
            with self._lock:
                cur = c.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
                c.commit()
                purge_summary["tenant_deleted"] = cur.rowcount
        except sqlite3.Error as e:
            logger.error("Deprovision: tenant delete error: %s", e)
        finally:
            c.close()

        purge_summary["total_purged"] = total_purged
        purge_summary["tenant_id"] = tenant_id
        purge_summary["tenant_name"] = tenant.get("name", "")
        logger.info(
            "Deprovision complete for tenant '%s' (%s): %d total rows purged",
            tenant_id, tenant.get("name", ""), total_purged,
        )
        return purge_summary

    def check_storage_quota(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant has exceeded storage quota.

        Queries SmartMemory.get_tenant_usage_mb() and compares against
        the plan's max_storage_mb limit.

        Returns:
            Dict with 'allowed', 'used_mb', 'max_mb', 'remaining_mb'.
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "error": "Tenant not found"}

        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        max_mb = quotas.get("max_storage_mb", 50)

        used_mb = 0.0
        try:
            from src.core.smart_memory import SmartMemory
            sm = SmartMemory()
            used_mb = sm.get_tenant_usage_mb(tenant_id)
        except Exception as e:
            logger.debug("Storage quota check: SmartMemory unavailable: %s", e)

        remaining_mb = max(0, max_mb - used_mb)
        allowed = used_mb < max_mb

        return {
            "allowed": allowed,
            "used_mb": round(used_mb, 2),
            "max_mb": max_mb,
            "remaining_mb": round(remaining_mb, 2),
            "plan": plan,
        }
