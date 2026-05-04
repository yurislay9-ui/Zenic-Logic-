"""
TITAN OMNISCALE X - SmartMemory Main Class

SmartMemory class combining all mixins + session/consolidation/client isolation methods.
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


class SmartMemory(DatabaseMixin, CacheMixin, LongTermMixin, EpisodesMixin):
    """
    Memoria inteligente para compensar las limitaciones de Qwen3-0.6B.
    
    3 tipos de memoria:
    1. Semantic Cache: "Ya respondí esto antes" → bypass total
    2. Working Memory: "Estamos hablando de X" → contexto para Qwen
    3. Long-term Memory: "La última vez que hicimos X, funcionó Y" → aprendizaje
    """

    def __init__(self, semantic_engine=None):
        self._semantic = semantic_engine  # Reference to SemanticEngine for embeddings
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._working_memory: List[MemoryEntry] = []
        self._working_lock = threading.Lock()
        self._client_id = 'default'  # Brecha B: Multi-client isolation
        self._last_vacuum_time = 0.0  # Instance variable (was class var)

        # Initialize DB with WAL mode for better mobile performance
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()
        self._enable_wal_mode()
        self._maybe_vacuum()

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
    #  Brecha B: MULTI-CLIENT MANAGEMENT
    # ================================================================

    def list_clients(self) -> List[str]:
        """Brecha B: Returns distinct client_ids from semantic_cache."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT client_id FROM semantic_cache"
            ).fetchall()
        return [r[0] for r in rows]

    def clear_client_data(self, client_id: str):
        """Brecha B: Deletes all data for a specific client across all tables."""
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id must be a non-empty string")
        tables = [
            "semantic_cache", "long_term_memory", "episodic_memory",
            "procedural_memory", "project_memory", "conversation_sessions",
        ]
        with sqlite3.connect(DB_PATH) as conn:
            for table in tables:
                assert table in self._VALID_TABLES, f"Invalid table: {table}"
                conn.execute(
                    f'DELETE FROM "{table}" WHERE client_id=?', (client_id,)
                )
        # Also remove from working memory
        self._working_memory = [
            e for e in self._working_memory if e.client_id != client_id
        ]
        logger.info(f"SmartMemory: Cleared all data for client_id='{client_id}'")

    # ================================================================
    #  7. SESSION MANAGEMENT
    # ================================================================

    def start_session(self) -> str:
        """Inicia una nueva sesión de conversación."""
        # End current session if any
        if self._working_memory:
            self.end_session()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self._working_memory.clear()
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO conversation_sessions (id, started_at, exchange_count, importance) VALUES (?, ?, 0, 0.5)",
                (self._session_id, time.time())
            )
        
        logger.info(f"SmartMemory: Session {self._session_id} started")
        return self._session_id

    def end_session(self) -> Dict[str, Any]:
        """Termina la sesión actual y consolida memorias."""
        summary = self.get_conversation_summary()
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE conversation_sessions SET ended_at=?, summary=?, exchange_count=?, importance=? WHERE id=?",
                (time.time(), summary[:1000], len(self._working_memory),
                 max((e.importance for e in self._working_memory), default=0.5),
                 self._session_id)
            )
        
        # Trigger consolidation
        self.consolidate_memories()
        
        logger.info(f"SmartMemory: Session {self._session_id} ended ({len(self._working_memory)} exchanges)")
        self._working_memory.clear()
        return {"session_id": self._session_id, "summary": summary, "exchanges": len(self._working_memory)}

    def get_conversation_summary(self, session_id: str = "") -> str:
        """Obtiene un resumen de la conversación de la sesión."""
        sid = session_id or self._session_id
        if not sid:
            return ""
        
        # From working memory if current session
        if sid == self._session_id and self._working_memory:
            ops = [f"{e.operation}/{e.goal}: {e.query[:50]}" for e in self._working_memory[-10:]]
            return f"Session {sid}: {' | '.join(ops)}"
        
        # From database for past sessions
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT summary, exchange_count FROM conversation_sessions WHERE id=?",
                (sid,)
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
        promoted = 0
        consolidated_episodes = 0
        
        # 1. Promote important working memory to long-term
        for entry in self._working_memory:
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
        
        # 2. Consolidate episodic memories with same event_type
        with sqlite3.connect(DB_PATH) as conn:
            event_types = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM episodic_memory GROUP BY event_type HAVING cnt > 3"
            ).fetchall()
            
            for event_type, count in event_types:
                # Get all episodes of this type
                rows = conn.execute(
                    "SELECT id, description, importance FROM episodic_memory WHERE event_type=? ORDER BY importance DESC",
                    (event_type,)
                ).fetchall()
                
                # Keep top 3, consolidate the rest into a summary
                if len(rows) > 3:
                    ids_to_remove = [r[0] for r in rows[3:]]
                    descriptions = [r[1][:100] for r in rows[3:]]
                    avg_importance = sum(r[2] for r in rows[3:]) / len(rows[3:])
                    
                    # Create consolidated episode
                    consolidated_desc = f"Consolidated {len(ids_to_remove)} {event_type} events: {'; '.join(descriptions[:3])}"
                    
                    conn.execute(
                        "INSERT INTO episodic_memory (event_type, description, importance, created_at) VALUES (?, ?, ?, ?)",
                        (event_type, consolidated_desc[:1000], avg_importance, time.time())
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
