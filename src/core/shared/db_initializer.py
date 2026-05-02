"""
TITAN OMNISCALE X - Database Initializer v13 (Optimized for ARM)

Inicializa todas las bases de datos SQLite con:
- WAL mode para concurrencia sin locks
- Connection pooling para no abrir/cerrar constantemente
- PRAGMA optimizados para ARM (menos memoria, mas eficiencia)
- Indice en theorem_cache para skeleton_hash lookups rapidos

Compatible con Termux + proot-distro (Debian ARM).
"""

import sqlite3
import threading
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

# ============================================================
#  CONNECTION POOL - Reutiliza conexiones SQLite
# ============================================================

_db_connections = {}
_db_lock = threading.Lock()


def _optimize_pragma(conn):
    """
    Aplica PRAGMA optimizados para rendimiento en ARM.

    WAL mode: Permite lecturas concurrentes sin bloquear escrituras.
    cache_size: -4000 = 4MB cache (buen balance para telefono)
    synchronous NORMAL: Mas rapido que FULL, seguro con WAL
    temp_store MEMORY: Tablas temporales en RAM
    mmap_size: Memory-mapped I/O para lecturas grandes
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-4000")      # 4MB cache
    conn.execute("PRAGMA synchronous=NORMAL")     # Mas rapido con WAL
    conn.execute("PRAGMA temp_store=MEMORY")      # Temp en RAM
    conn.execute("PRAGMA mmap_size=67108864")     # 64MB mmap
    conn.execute("PRAGMA wal_autocheckpoint=1000") # Auto-checkpoint cada 1000 frames
    conn.execute("PRAGMA busy_timeout=5000")       # 5s timeout para locks


def get_data_dir() -> Path:
    if 'ANDROID_ARGUMENT' in os.environ:
        try:
            from android.storage import app_storage_path
            data_dir = Path(app_storage_path()) / "titan_data"
        except Exception:
            data_dir = Path.home() / ".titan_omniscale" / "data"
    else:
        data_dir = Path.home() / ".titan_omniscale" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path(db_name: str) -> str:
    return str(get_data_dir() / db_name)


def get_projects_dir() -> Path:
    p = get_data_dir() / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_connection(db_name: str) -> sqlite3.Connection:
    """
    Obtiene una conexion del pool. Reutiliza conexiones existentes.

    El pool mantiene una conexion por DB, thread-safe con lock.
    Si la conexion esta rota, crea una nueva.
    """
    key = db_name
    with _db_lock:
        if key in _db_connections:
            conn = _db_connections[key]
            # Verificar que la conexion sigue viva
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                # Conexion rota, crear nueva
                del _db_connections[key]

        path = get_db_path(db_name)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _optimize_pragma(conn)
        _db_connections[key] = conn
        return conn


def close_all_connections():
    """Cierra todas las conexiones del pool (para shutdown limpio)."""
    with _db_lock:
        for key, conn in list(_db_connections.items()):
            try:
                conn.close()
            except Exception as e:
                logger.debug(f"close_all_connections: Failed to close connection: {e}")
        _db_connections.clear()


def initialize_databases():
    """Crea todas las tablas SQLite con esquemas completos v13 + indices + PRAGMA."""

    # Graph AST
    conn = get_connection("graph_ast.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        node_type TEXT NOT NULL,
        name TEXT NOT NULL,
        start_byte INTEGER NOT NULL,
        end_byte INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        docstring TEXT,
        complexity INTEGER DEFAULT 1,
        connections TEXT DEFAULT '[]',
        UNIQUE(file_path, name, node_type))""")
    # Indice para busquedas rapidas por nombre (usado por MacroRouter)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_name ON ast_nodes(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_type ON ast_nodes(node_type)")
    conn.commit()

    # Theorem Cache
    conn = get_connection("theorem_cache.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS theorems (
        structural_hash TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        goal TEXT NOT NULL,
        proof_result TEXT NOT NULL,
        solution_payload TEXT,
        skeleton_hash TEXT,
        hit_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    # Indice para skeleton hash lookups (O(1) bypass experiencial)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skeleton ON theorems(skeleton_hash)")
    conn.commit()

    # Merkle Ledger
    conn = get_connection("merkle_ledger.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        hash_sha256 TEXT NOT NULL,
        parent_hash TEXT NOT NULL,
        operation TEXT NOT NULL,
        timestamp REAL NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_file ON ledger(file_path)")
    conn.commit()

    # Request Log
    conn = get_connection("request_log.sqlite")
    conn.execute("""CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_time ON requests(created_at)")
    conn.commit()

    logger.info("Databases initialized with WAL mode + PRAGMA optimizations")
