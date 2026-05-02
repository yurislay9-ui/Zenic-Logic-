"""
TITAN OMNISCALE X - SmartMemory (Intelligent Memory for Qwen)

Memoria inteligente que APOYA a Qwen3-0.6B compensando sus limitaciones:
- Contexto limitado → SmartMemory almacena y recupera contexto relevante
- Sin aprendizaje → SmartMemory aprende de interacciones previas
- Sin estado → SmartMemory mantiene estado entre sesiones

Arquitectura de 3 capas:
  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud)
  Capa 2: MiniAIEngine (Qwen) → PIENSA (razonamiento)
  Capa 3: SmartMemory → RECUERDA (cache semántico, contexto, aprendizaje)

Características:
  1. Semantic Cache: Si ya respondimos algo similar → devolver cacheado
  2. Working Memory: Contexto de la tarea actual (últimos N intercambios)
  3. Long-term Memory: Soluciones previas exitosas indexadas por semántica
  4. Importance Scoring: No todo es igual de importante → priorizar
  5. Auto-compress: Resumir contexto largo para que Qwen no se sature
  6. SQLite persistente: Sobrevive reinicios

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB)
  - Qwen3-0.6B con contexto de 2048 tokens
  - ~100KB por sesión de trabajo
"""

import os
import re
import time
import json
import sqlite3
import hashlib
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.expanduser("~"), ".titan_omniscale", "db")
DB_PATH = os.path.join(DB_DIR, "smart_memory.sqlite")

# Limits for Qwen3-0.6B context window
MAX_WORKING_ENTRIES = 20       # Max entries in working memory
MAX_COMPRESSED_TOKENS = 500    # Max tokens for compressed context
IMPORTANCE_THRESHOLD = 0.6     # Min importance to promote to long-term
SEMANTIC_CACHE_THRESHOLD = 0.85 # Min similarity for cache hit
MAX_LONG_TERM_ENTRIES = 500    # Max entries in long-term memory


@dataclass
class MemoryEntry:
    """Una entrada en la memoria."""
    id: Optional[int] = None
    query: str = ""
    response: str = ""
    operation: str = ""
    goal: str = ""
    importance: float = 0.5     # 0.0-1.0, higher = more important
    timestamp: float = 0.0
    embedding: Optional[np.ndarray] = None  # Lazy-loaded
    access_count: int = 0
    session_id: str = ""


class SmartMemory:
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
        
        # Initialize DB
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Crea tablas SQLite si no existen."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS semantic_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT NOT NULL,
                query_text TEXT NOT NULL,
                response_summary TEXT NOT NULL,
                operation TEXT DEFAULT '',
                goal TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                embedding BLOB,
                created_at REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                session_id TEXT DEFAULT '',
                UNIQUE(query_hash)
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                solution_summary TEXT NOT NULL,
                operation TEXT DEFAULT '',
                goal TEXT DEFAULT '',
                importance REAL DEFAULT 0.5,
                success BOOLEAN DEFAULT 1,
                embedding BLOB,
                created_at REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_cache_hash 
                ON semantic_cache(query_hash)""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_ltm_importance 
                ON long_term_memory(importance DESC)""")

    # ================================================================
    #  1. SEMANTIC CACHE
    # ================================================================

    def check_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Busca en el cache semántico: "Ya respondí algo similar antes?"
        
        Usa embeddings si SemanticEngine está disponible, si no usa hash exacto.
        Returns cached response or None.
        """
        # First: exact hash match (fastest)
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT response_summary, operation, goal, importance, access_count, id FROM semantic_cache WHERE query_hash=?",
                (query_hash,)
            ).fetchone()
            if row:
                # Update access count
                conn.execute("UPDATE semantic_cache SET access_count=access_count+1 WHERE id=?", (row[5],))
                return {
                    "response": row[0],
                    "operation": row[1],
                    "goal": row[2],
                    "importance": row[3],
                    "source": "cache_exact",
                }

        # Second: semantic similarity match (if SemanticEngine available)
        if self._semantic and self._semantic.is_loaded:
            query_emb = self._semantic.embed(query)
            if query_emb is not None:
                # Load recent cache entries and compare
                with sqlite3.connect(DB_PATH) as conn:
                    rows = conn.execute(
                        "SELECT id, query_text, response_summary, operation, goal, importance, embedding FROM semantic_cache ORDER BY id DESC LIMIT 100"
                    ).fetchall()

                for row in rows:
                    cache_emb = self._deserialize_embedding(row[6])
                    if cache_emb is not None:
                        sim = self._semantic.similarity(query_emb, cache_emb)
                        if sim >= SEMANTIC_CACHE_THRESHOLD:
                            # Update access count
                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("UPDATE semantic_cache SET access_count=access_count+1 WHERE id=?", (row[0],))
                            return {
                                "response": row[2],
                                "operation": row[3],
                                "goal": row[4],
                                "importance": row[5],
                                "similarity": sim,
                                "source": "cache_semantic",
                            }

        return None

    def save_to_cache(self, query: str, response: str, operation: str = "",
                       goal: str = "", importance: float = 0.5):
        """Guarda una entrada en el cache semántico."""
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        
        # Compute embedding if possible
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(query)
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)

        # Truncate response for storage
        response_summary = response[:2000] if response else ""

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO semantic_cache 
                   (query_hash, query_text, response_summary, operation, goal, importance, embedding, created_at, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query_hash, query[:500], response_summary, operation, goal,
                 importance, emb_blob, time.time(), self._session_id)
            )

        # If high importance, also save to long-term
        if importance >= IMPORTANCE_THRESHOLD:
            self.save_to_long_term(query, response_summary, operation, goal, importance)

    # ================================================================
    #  2. WORKING MEMORY (context for Qwen)
    # ================================================================

    def add_working(self, query: str, response: str, operation: str = "", 
                     goal: str = "", importance: float = 0.5):
        """Añade entrada a la memoria de trabajo (contexto actual)."""
        entry = MemoryEntry(
            query=query[:500],
            response=response[:1000],
            operation=operation,
            goal=goal,
            importance=importance,
            timestamp=time.time(),
            session_id=self._session_id,
        )
        self._working_memory.append(entry)

        # Evict oldest if over limit
        if len(self._working_memory) > MAX_WORKING_ENTRIES:
            # Remove lowest importance entry
            self._working_memory.sort(key=lambda e: e.importance)
            self._working_memory.pop(0)

    def get_working_context(self, max_tokens: int = MAX_COMPRESSED_TOKENS) -> str:
        """
        Obtiene contexto comprimido de la memoria de trabajo para Qwen.
        
        Formato: "Previous context: [summarized interactions]"
        Esto le da a Qwen el contexto que no tendría de otra forma.
        """
        if not self._working_memory:
            return ""

        # Build context from working memory, prioritizing important entries
        sorted_entries = sorted(self._working_memory, key=lambda e: (-e.importance, -e.timestamp))
        
        context_parts = []
        token_estimate = 0
        
        for entry in sorted_entries:
            part = f"[{entry.operation}/{entry.goal}] Q: {entry.query[:80]}"
            if entry.response:
                part += f" → A: {entry.response[:100]}"
            
            part_tokens = len(part.split())  # Rough estimate
            if token_estimate + part_tokens > max_tokens:
                break
            
            context_parts.append(part)
            token_estimate += part_tokens

        if not context_parts:
            return ""

        return "Previous context: " + " | ".join(context_parts)

    def get_recent_operations(self, n: int = 5) -> List[str]:
        """Obtiene las últimas N operaciones realizadas."""
        return [e.operation for e in self._working_memory[-n:] if e.operation]

    # ================================================================
    #  3. LONG-TERM MEMORY (learning)
    # ================================================================

    def save_to_long_term(self, query: str, solution: str, operation: str = "",
                           goal: str = "", importance: float = 0.5, 
                           success: bool = True, tags: List[str] = None):
        """Guarda una solución exitosa en la memoria a largo plazo."""
        emb_blob = None
        if self._semantic and self._semantic.is_loaded:
            emb = self._semantic.embed(query)
            if emb is not None:
                emb_blob = self._serialize_embedding(emb)

        tags_json = json.dumps(tags or [])

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """INSERT INTO long_term_memory 
                   (query_text, solution_summary, operation, goal, importance, success, embedding, created_at, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query[:500], solution[:2000], operation, goal, importance,
                 success, emb_blob, time.time(), tags_json)
            )

        # Evict if over limit
        self._evict_long_term()

    def find_similar_solutions(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Busca soluciones previas semánticamente similares.
        "La última vez que hicimos algo parecido, funcionó esto."
        """
        if not self._semantic or not self._semantic.is_loaded:
            return []

        query_emb = self._semantic.embed(query)
        if query_emb is None:
            return []

        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT id, query_text, solution_summary, operation, goal, importance, success, embedding, tags FROM long_term_memory WHERE success=1 ORDER BY importance DESC LIMIT 100"
            ).fetchall()

        results = []
        for row in rows:
            cache_emb = self._deserialize_embedding(row[7])
            if cache_emb is not None:
                sim = self._semantic.similarity(query_emb, cache_emb)
                if sim >= 0.5:
                    results.append({
                        "query": row[1],
                        "solution": row[2],
                        "operation": row[3],
                        "goal": row[4],
                        "importance": row[5],
                        "similarity": sim,
                        "tags": json.loads(row[8] or "[]"),
                    })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def _evict_long_term(self):
        """Evict least important entries if over limit."""
        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]
            if count > MAX_LONG_TERM_ENTRIES:
                # Delete lowest importance entries
                conn.execute(
                    "DELETE FROM long_term_memory WHERE id IN (SELECT id FROM long_term_memory ORDER BY importance ASC, access_count ASC LIMIT ?)",
                    (count - MAX_LONG_TERM_ENTRIES + 50,)  # Delete extra 50 to avoid frequent eviction
                )

    # ================================================================
    #  UTILITY: Importance Scoring
    # ================================================================

    @staticmethod
    def compute_importance(query: str, operation: str, goal: str, 
                            success: bool, response_length: int) -> float:
        """
        Calcula la importancia de una interacción.
        
        Factores:
        - Operaciones críticas (DELETE, DEBUG) → más importantes
        - Goals de seguridad → más importantes
        - Interacciones exitosas → más importantes
        - Respuestas largas → posiblemente más complejas → más importantes
        """
        score = 0.5  # Base

        # Operation importance
        op_weights = {
            "DELETE": 0.2, "DEBUG": 0.15, "REFACTOR": 0.1,
            "CREATE": 0.05, "OPTIMIZE": 0.1, "ANALYZE": 0.05,
            "SEARCH": -0.1, "EXPLAIN": 0.0,
        }
        score += op_weights.get(operation, 0.0)

        # Goal importance
        goal_weights = {
            "SECURITY_HARDEN": 0.2, "BUG_FIX": 0.15,
            "PERFORMANCE": 0.1, "FEATURE_ADD": 0.05,
            "COMPLEXITY_REDUCTION": 0.05, "MODERN_PATTERN": 0.0,
            "READABILITY": 0.0,
        }
        score += goal_weights.get(goal, 0.0)

        # Success bonus
        if success:
            score += 0.1

        # Response length (longer = more complex, probably more important)
        if response_length > 500:
            score += 0.05
        if response_length > 1000:
            score += 0.05

        return max(0.0, min(1.0, score))

    # ================================================================
    #  UTILITY: Embedding Serialization
    # ================================================================

    @staticmethod
    def _serialize_embedding(emb: np.ndarray) -> bytes:
        """Serialize embedding to bytes for SQLite storage."""
        return emb.astype(np.float32).tobytes()

    @staticmethod
    def _deserialize_embedding(data: bytes) -> Optional[np.ndarray]:
        """Deserialize embedding from SQLite bytes."""
        if data is None or len(data) == 0:
            return None
        try:
            emb = np.frombuffer(data, dtype=np.float32)
            # Normalize
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb
        except Exception:
            return None

    # ================================================================
    #  STATS & DEBUG
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas de uso de la memoria."""
        with sqlite3.connect(DB_PATH) as conn:
            cache_count = conn.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
            ltm_count = conn.execute("SELECT COUNT(*) FROM long_term_memory").fetchone()[0]

        return {
            "session_id": self._session_id,
            "working_memory_size": len(self._working_memory),
            "semantic_cache_size": cache_count,
            "long_term_memory_size": ltm_count,
            "semantic_engine_available": self._semantic is not None and self._semantic.is_loaded,
        }

    def clear_session(self):
        """Limpia la memoria de trabajo para una nueva sesión."""
        self._working_memory.clear()
        self._session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
