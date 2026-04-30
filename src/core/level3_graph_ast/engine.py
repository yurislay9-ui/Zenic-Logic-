import sqlite3
import hashlib
import logging
from pathlib import Path
from tree_sitter_languages import get_language, get_parser
from src.core.shared.db_initializer import get_db_path

logger = logging.getLogger(__name__)

# Queries tree-sitter específicas por lenguaje
LANGUAGE_QUERIES = {
    "python": "(function_definition name: (identifier) @name) (class_definition name: (identifier) @name)",
    "kotlin": "(function_declaration name: (simple_identifier) @name) (class_declaration name: (identifier) @name)",
    "go": "(function_declaration name: (identifier) @name) (method_declaration name: (field_identifier) @name) (type_declaration name: (type_identifier) @name)",
    "javascript": "(function_declaration name: (identifier) @name) (class_declaration name: (identifier) @name)",
}


class GraphASTEngine:
    def scan_project(self, project_dir: str):
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

    def _parse_and_store(self, f: Path, p_dir: str, conn: sqlite3.Connection):
        lang_map = {".py": "python", ".kt": "kotlin", ".go": "go", ".js": "javascript"}
        lang = lang_map.get(f.suffix)
        if not lang:
            return
        parser = get_parser(lang)
        tree = parser.parse(f.read_text(encoding="utf-8").encode())
        query_str = LANGUAGE_QUERIES.get(lang, LANGUAGE_QUERIES["python"])
        try:
            lang_obj = get_language(lang)
            q = lang_obj.query(query_str)
            for node, _ in q.captures(tree.root_node):
                if node.parent:
                    conn.execute(
                        "INSERT OR REPLACE INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, content_hash) VALUES (?,?,?,?,?,?)",
                        (str(f.relative_to(p_dir)), "function", node.text.decode(), node.parent.start_byte, node.parent.end_byte, hashlib.sha256(f.read_bytes()).hexdigest())
                    )
        except Exception as e:
            logger.debug("Query tree-sitter no soportada para %s: %s", lang, e)

    def get_node_info(self, target_name: str) -> list[dict]:
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM ast_nodes WHERE name = ?", (target_name,)).fetchall()]
