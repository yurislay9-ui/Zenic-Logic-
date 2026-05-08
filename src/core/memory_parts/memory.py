"""
TITAN OMNISCALE X - SmartMemory Main Class

SmartMemory class combining all mixins + session/consolidation/client isolation methods.
Now fully tenant-aware via TenantContext (Phase 2: Real Multitenancy).
"""

import os
import time
import json
import sqlite3
import hashlib
import threading
import logging
from typing import Optional, Dict, Any, List

from .types import DB_DIR, DB_PATH, MemoryEntry, logger, IMPORTANCE_THRESHOLD
from .database import DatabaseMixin
from .cache import CacheMixin
from .longterm import LongTermMixin
from .episodes import EpisodesMixin

# Phase 2: Tenant context for multitenancy
from src.core.tenant._context import get_current_tenant, set_current_tenant, TenantContext


class SmartMemory(DatabaseMixin, CacheMixin, LongTermMixin, EpisodesMixin):
    """
    Memoria inteligente para compensar las limitaciones de Qwen3-0.6B.
    
    3 tipos de memoria:
    1. Semantic Cache: "Ya respondí esto antes" → bypass total
    2. Working Memory: "Estamos hablando de X" → contexto para Qwen
    3. Long-term Memory: "La última vez que hicimos X, funcionó Y" → aprendizaje

    Phase 2: Fully tenant-aware. All data is scoped by tenant_id from
    TenantContext. Backward compatible — defaults to '__anonymous__'.
    """

    def __init__(self, semantic_engine=None):
        self._semantic = semantic_engine  # Reference to SemanticEngine for embeddings
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._working_memory: List[MemoryEntry] = []
        self._working_lock = threading.Lock()
        self._client_id = 'default'  # Brecha B: Multi-client isolation
        self._last_vacuum_time = 0.0  # Instance variable (was class var)

        # Phase 2: Tenant-aware initialization
        ctx = get_current_tenant()
        self._tenant_id: str = ctx.effective_tenant_id
        logger.info(
            f"SmartMemory: Initialized with tenant_id='{self._tenant_id}', "
            f"client_id='{self._client_id}'"
        )

        # Initialize DB with WAL mode for better mobile performance
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()
        self._enable_wal_mode()
        self._maybe_vacuum()

    def set_tenant_id(self, tenant_id: str) -> None:
        """Phase 2: Set the tenant_id for all subsequent operations.

        Updates both the instance variable and the thread-local
        TenantContext so that deeply-nested code also sees the
        correct tenant.

        Args:
            tenant_id: The tenant identifier to scope operations to.
                       Must be a non-empty string.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        self._tenant_id = tenant_id.strip()

        # Also update the thread-local context so nested code sees the change
        current_ctx = get_current_tenant()
        if current_ctx.tenant_id != self._tenant_id:
            new_ctx = TenantContext(
                tenant_id=self._tenant_id,
                user_id=current_ctx.user_id,
                username=current_ctx.username,
                role=current_ctx.role,
                plan=current_ctx.plan,
                quotas=current_ctx.quotas,
                features=current_ctx.features,
                permissions=current_ctx.permissions,
                auth_method=current_ctx.auth_method,
                is_authenticated=current_ctx.is_authenticated,
                extra=current_ctx.extra,
            )
            set_current_tenant(new_ctx)

        logger.info(f"SmartMemory: tenant_id set to '{self._tenant_id}'")

    def set_client_id(self, client_id: str):
        """Brecha B: Set the client_id for multi-client isolation.
        
        All subsequent DB operations will be scoped to this client.
        Validates that client_id is a non-empty string.
        """
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        self._client_id = client_id.strip()
        logger.info(f"SmartMemory: client_id set to '{self._client_id}'")

    def clear_session(self) -> None:
        """Limpia la memoria de trabajo para una nueva sesión."""
        with self._working_lock:
            self._working_memory.clear()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]

    # ================================================================
    #  Brecha B: MULTI-CLIENT MANAGEMENT (enhanced with tenant_id)
    # ================================================================

    def list_clients(self, tenant_id: Optional[str] = None) -> List[str]:
        """Returns distinct client_ids, optionally scoped by tenant_id.

        Args:
            tenant_id: If provided, list clients only for this tenant.
                       Defaults to the current instance tenant_id.
        """
        tid = tenant_id or self._tenant_id
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT client_id FROM semantic_cache WHERE tenant_id=?",
                (tid,)
            ).fetchall()
        return [r[0] for r in rows]

    def clear_client_data(self, client_id: str, tenant_id: Optional[str] = None):
        """Deletes all data for a specific client, scoped by tenant_id.

        Args:
            client_id: The client identifier to clear data for.
            tenant_id: If provided, scope to this tenant. Defaults to
                       the current instance tenant_id.
        """
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        tid = tenant_id or self._tenant_id
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        with sqlite3.connect(DB_PATH) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                conn.execute(
                    f'DELETE FROM "{table}" WHERE client_id=? AND tenant_id=?',
                    (client_id, tid)
                )
        # Also remove from working memory (thread-safe)
        with self._working_lock:
            self._working_memory = [
                e for e in self._working_memory
                if not (e.client_id == client_id and e.tenant_id == tid)
            ]
        logger.info(
            f"SmartMemory: Cleared all data for client_id='{client_id}', "
            f"tenant_id='{tid}'"
        )

    # ================================================================
    #  Phase 2: TENANT MANAGEMENT
    # ================================================================

    def purge_tenant_data(self, tenant_id: str) -> int:
        """Delete ALL data for a tenant across all tables.

        Used for GDPR compliance (right to be forgotten) or tenant
        deprovisioning. This is a destructive operation.

        Args:
            tenant_id: The tenant identifier to purge all data for.

        Returns:
            Total number of rows deleted across all tables.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        tid = tenant_id.strip()
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        total_deleted = 0
        with sqlite3.connect(DB_PATH) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                cursor = conn.execute(
                    f'DELETE FROM "{table}" WHERE tenant_id=?',
                    (tid,)
                )
                total_deleted += cursor.rowcount
        # Also remove from working memory (thread-safe)
        with self._working_lock:
            self._working_memory = [
                e for e in self._working_memory if e.tenant_id != tid
            ]
        logger.info(
            f"SmartMemory: Purged all data for tenant_id='{tid}' "
            f"({total_deleted} rows deleted)"
        )
        return total_deleted

    def get_tenant_usage_mb(self, tenant_id: str) -> float:
        """Calculate approximate storage usage in MB for a tenant.

        Estimates the storage consumed by all rows belonging to the
        given tenant across all tables. Uses row count and average
        row size estimation.

        Args:
            tenant_id: The tenant identifier to measure usage for.

        Returns:
            Estimated storage usage in megabytes.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        tid = tenant_id.strip()

        # Try to get actual DB page usage for tenant rows
        total_bytes = 0
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]

        with sqlite3.connect(DB_PATH) as conn:
            # Get total DB size and total row count for proportional estimate
            db_size_bytes = 0
            try:
                db_size_bytes = os.path.getsize(DB_PATH)
            except OSError:
                pass

            total_tenant_rows = 0
            total_all_rows = 0
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                try:
                    tenant_count = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE tenant_id=?',
                        (tid,)
                    ).fetchone()[0]
                    total_tenant_rows += tenant_count

                    all_count = conn.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                    total_all_rows += all_count
                except sqlite3.OperationalError:
                    pass

            if total_all_rows > 0 and db_size_bytes > 0:
                # Proportional estimate: tenant rows / total rows * db size
                total_bytes = (total_tenant_rows / total_all_rows) * db_size_bytes

        usage_mb = total_bytes / (1024 * 1024)
        logger.debug(
            f"SmartMemory: Tenant '{tid}' usage: {usage_mb:.2f}MB "
            f"({total_tenant_rows} rows)"
        )
        return usage_mb

    # ================================================================
    #  7. SESSION MANAGEMENT (tenant-aware)
    # ================================================================

    def start_session(self) -> str:
        """Inicia una nueva sesión de conversación (tenant-aware)."""
        # End current session if any
        with self._working_lock:
            if self._working_memory:
                # end_session will acquire _working_lock, so release first
                pass
            else:
                self._working_memory.clear()
        if self._working_memory:
            self.end_session()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        with self._working_lock:
            self._working_memory.clear()
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO conversation_sessions 
                   (id, started_at, exchange_count, importance, client_id, tenant_id)
                   VALUES (?, ?, 0, 0.5, ?, ?)""",
                (self._session_id, time.time(), self._client_id, self._tenant_id)
            )
        
        logger.info(
            f"SmartMemory: Session {self._session_id} started "
            f"(tenant='{self._tenant_id}', client='{self._client_id}')"
        )
        return self._session_id

    def end_session(self) -> Dict[str, Any]:
        """Termina la sesión actual y consolida memorias (tenant-aware)."""
        with self._working_lock:
            summary = self.get_conversation_summary()
            exchange_count = len(self._working_memory)  # Capture BEFORE consolidation
            
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """UPDATE conversation_sessions 
                       SET ended_at=?, summary=?, exchange_count=?, importance=?
                       WHERE id=? AND tenant_id=?""",
                    (time.time(), summary[:1000], exchange_count,
                     max((e.importance for e in self._working_memory), default=0.5),
                     self._session_id, self._tenant_id)
                )
            
            # Snapshot working memory for consolidation (within lock)
            working_snapshot = list(self._working_memory)
        
        # Trigger consolidation (uses snapshot, no lock needed for DB ops)
        self._consolidate_from_snapshot(working_snapshot)
        
        with self._working_lock:
            self._working_memory.clear()
        logger.info(
            f"SmartMemory: Session {self._session_id} ended "
            f"({exchange_count} exchanges, tenant='{self._tenant_id}')"
        )
        return {"session_id": self._session_id, "summary": summary, "exchanges": exchange_count}

    def get_conversation_summary(self, session_id: str = "") -> str:
        """Obtiene un resumen de la conversación de la sesión."""
        sid = session_id or self._session_id
        if not sid:
            return ""
        
        # From working memory if current session
        if sid == self._session_id and self._working_memory:
            ops = [f"{e.operation}/{e.goal}: {e.query[:50]}" for e in self._working_memory[-10:]]
            return f"Session {sid}: {' | '.join(ops)}"
        
        # From database for past sessions (tenant-scoped)
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT summary, exchange_count FROM conversation_sessions WHERE id=? AND tenant_id=?",
                (sid, self._tenant_id)
            ).fetchone()
            if row and row[0]:
                return row[0]
        
        return ""

    # ================================================================
    #  8. MEMORY CONSOLIDATION
    # ================================================================

    def consolidate_memories(self) -> Dict[str, int]:
        """
        Consolida memorias: promueve working → long-term, agrupa similares.
        
        Returns dict with counts of items consolidated.
        """
        # Snapshot working memory under lock
        with self._working_lock:
            working_snapshot = list(self._working_memory)
        
        return self._consolidate_from_snapshot(working_snapshot)

    def _consolidate_from_snapshot(self, working_snapshot: List[MemoryEntry]) -> Dict[str, int]:
        """Consolidate from a snapshot of working memory (thread-safe, tenant-aware)."""
        promoted = 0
        consolidated_episodes = 0
        
        # 1. Promote important working memory to long-term
        for entry in working_snapshot:
            if entry.importance >= IMPORTANCE_THRESHOLD:
                # Check if already exists in long-term (avoid duplicates)
                existing = self.find_similar_solutions(entry.query, top_k=1)
                is_duplicate = any(s.get("similarity", 0) > 0.9 for s in existing)
                
                if not is_duplicate:
                    self.save_to_long_term(
                        query=entry.query,
                        solution=entry.response[:500],
                        operation=entry.operation,
                        goal=entry.goal,
                        importance=entry.importance,
                        success=True,
                        tags=[entry.operation, entry.goal, self._session_id],
                    )
                    promoted += 1
        
        # 2. Consolidate episodic memories with same event_type (tenant-scoped)
        with sqlite3.connect(DB_PATH) as conn:
            event_types = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM episodic_memory WHERE tenant_id=? GROUP BY event_type HAVING cnt > 3",
                (self._tenant_id,)
            ).fetchall()
            
            for event_type, count in event_types:
                # Get all episodes of this type for current tenant
                rows = conn.execute(
                    "SELECT id, description, importance FROM episodic_memory WHERE event_type=? AND tenant_id=? ORDER BY importance DESC",
                    (event_type, self._tenant_id)
                ).fetchall()
                
                # Keep top 3, consolidate the rest into a summary
                if len(rows) > 3:
                    ids_to_remove = [r[0] for r in rows[3:]]
                    descriptions = [r[1][:100] for r in rows[3:]]
                    avg_importance = sum(r[2] for r in rows[3:]) / len(rows[3:])
                    
                    # Create consolidated episode (tenant-scoped)
                    consolidated_desc = f"Consolidated {len(ids_to_remove)} {event_type} events: {'; '.join(descriptions[:3])}"
                    
                    conn.execute(
                        """INSERT INTO episodic_memory 
                           (event_type, description, importance, created_at, client_id, tenant_id)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (event_type, consolidated_desc[:1000], avg_importance, time.time(),
                         self._client_id, self._tenant_id)
                    )
                    
                    # Remove individual entries
                    conn.execute(
                        f"DELETE FROM episodic_memory WHERE id IN ({','.join('?' * len(ids_to_remove))})",
                        ids_to_remove
                    )
                    consolidated_episodes += len(ids_to_remove)
        
        if promoted > 0 or consolidated_episodes > 0:
            logger.info(f"SmartMemory: Consolidated - promoted={promoted}, episodes_merged={consolidated_episodes}")
        
        return {"promoted_to_long_term": promoted, "episodes_consolidated": consolidated_episodes}

    def get_recent_entries(self, limit: int = 30):
        """Public accessor for recent working memory entries."""
        return self._working_memory[:limit]
