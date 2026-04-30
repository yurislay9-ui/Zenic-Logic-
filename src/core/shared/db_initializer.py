import sqlite3
from pathlib import Path
import os

def get_data_dir() -> Path:
    if 'ANDROID_ARGUMENT' in os.environ:
        import android
        data_dir = Path(android.storage.app_storage_path()) / "db"
    else:
        data_dir = Path.home() / ".titan_omniscale" / "db"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_db_path(db_name: str) -> str:
    return str(get_data_dir() / db_name)

def initialize_databases():
    with sqlite3.connect(get_db_path("graph_ast.sqlite"), check_same_thread=False) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, node_type TEXT NOT NULL,
            name TEXT NOT NULL, start_byte INTEGER NOT NULL, end_byte INTEGER NOT NULL,
            content_hash TEXT NOT NULL, UNIQUE(file_path, name, node_type))""")
    with sqlite3.connect(get_db_path("theorem_cache.sqlite"), check_same_thread=False) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS theorems (
            structural_hash TEXT PRIMARY KEY, operation TEXT NOT NULL, proof_result TEXT NOT NULL,
            solution_payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
