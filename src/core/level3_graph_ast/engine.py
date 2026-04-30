"""
TITAN OMNISCALE X - Graph AST Engine (Pure Python)

Motor de AST basado en regex. Sin tree-sitter.
Compatible con Android.
"""
import sqlite3
import hashlib
import re
import logging
from pathlib import Path
from src.core.shared.db_initializer import get_db_path

logger = logging.getLogger(__name__)


class GraphASTEngine:
    def scan_project(self, project_dir):
        base_path = Path(project_dir)
        if not base_path.exists():
            return
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            conn.execute("DELETE FROM ast_nodes")
            for f in base_path.rglob("*"):
                if f.suffix in [".py", ".kt", ".go", ".js"]:
                    try:
                        self._parse_and_store(f, project_dir, conn)
                    except Exception as e:
                        logger.warning("Error parseando %s: %s", f, e)

    def _parse_and_store(self, f, p_dir, conn):
        source = f.read_text(encoding="utf-8", errors="ignore")
        # Detectar funciones por regex
        func_pattern = r'(?:def|function|fun|func)\s+(\w+)\s*[\(\{]'
        for match in re.finditer(func_pattern, source):
            name = match.group(1)
            start = match.start()
            content_hash = hashlib.sha256(source.encode()).hexdigest()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash) VALUES (?,?,?,?,?,?)",
                    (str(f.relative_to(p_dir)), "function", name, start, start + len(match.group(0)), content_hash)
                )
            except Exception:
                pass

    def get_node_info(self, target_name):
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM ast_nodes WHERE name = ?", (target_name,)).fetchall()]
