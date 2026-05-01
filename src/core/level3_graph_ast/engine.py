"""
TITAN OMNISCALE X - Graph AST Engine v13 (ast nativo + regex)

Motor de AST usando el modulo nativo ast de Python para codigo Python,
y regex para otros lenguajes. Almacena nodos en SQLite con conexiones.
Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import hashlib
import sqlite3
import json
import logging
from pathlib import Path
from src.core.shared.db_initializer import get_db_path

logger = logging.getLogger(__name__)


class GraphASTEngine:
    """Motor de AST usando ast nativo para Python, regex para otros."""

    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL, node_type TEXT NOT NULL,
                name TEXT NOT NULL, start_byte INTEGER NOT NULL,
                end_byte INTEGER NOT NULL, content_hash TEXT NOT NULL,
                docstring TEXT, complexity INTEGER DEFAULT 1,
                connections TEXT DEFAULT '[]',
                UNIQUE(file_path, name, node_type))""")

    def scan_code(self, code, file_path="input.py", language="python"):
        if language == "python":
            return self._parse_python(code, file_path)
        return self._parse_regex(code, file_path, language)

    def scan_project(self, project_dir):
        base_path = Path(project_dir)
        if not base_path.exists():
            return
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            for f in base_path.rglob("*"):
                if f.suffix in [".py", ".kt", ".go", ".js", ".ts", ".java", ".rs"]:
                    try:
                        lang = self._detect_language(f.suffix)
                        source = f.read_text(encoding="utf-8", errors="ignore")
                        self.scan_code(source, str(f.relative_to(base_path)), lang)
                    except Exception as e:
                        logger.warning("Error parsing %s: %s", f, e)

    def _detect_language(self, suffix):
        mapping = {".py": "python", ".kt": "kotlin", ".go": "go",
                   ".js": "javascript", ".ts": "typescript",
                   ".java": "java", ".rs": "rust"}
        return mapping.get(suffix, "python")

    def _parse_python(self, code, file_path):
        nodes = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._cyclomatic_complexity(node)
                    docstring = ast.get_docstring(node) or ""
                    connections = self._extract_calls(node)
                    start = node.lineno
                    end = node.end_lineno or start
                    content = ast.get_source_segment(code, node) or ""
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    nodes.append({
                        "file_path": file_path, "node_type": "function",
                        "name": node.name, "start_byte": start, "end_byte": end,
                        "content_hash": content_hash, "docstring": docstring,
                        "complexity": complexity, "connections": json.dumps(connections),
                    })
                    self._store_node(nodes[-1])
                elif isinstance(node, ast.ClassDef):
                    connections = self._extract_class_connections(node)
                    content_hash = hashlib.sha256(node.name.encode()).hexdigest()[:16]
                    docstring = ast.get_docstring(node) or ""
                    nodes.append({
                        "file_path": file_path, "node_type": "class",
                        "name": node.name, "start_byte": node.lineno,
                        "end_byte": node.end_lineno or node.lineno,
                        "content_hash": content_hash, "docstring": docstring,
                        "complexity": 1, "connections": json.dumps(connections),
                    })
                    self._store_node(nodes[-1])
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = []
                    for alias in node.names:
                        names.append(alias.asname or alias.name)
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names.insert(0, node.module)
                    content_hash = hashlib.sha256(",".join(names).encode()).hexdigest()[:16]
                    nodes.append({
                        "file_path": file_path, "node_type": "import",
                        "name": ",".join(names), "start_byte": node.lineno,
                        "end_byte": node.end_lineno or node.lineno,
                        "content_hash": content_hash, "docstring": "",
                        "complexity": 0, "connections": "[]",
                    })
                    self._store_node(nodes[-1])
        except SyntaxError as e:
            logger.warning("Syntax error in %s: %s", file_path, e)
        return nodes

    def _parse_regex(self, code, file_path, language):
        nodes = []
        patterns = {
            "kotlin": r'(?:fun|companion object)\s+(\w+)\s*[\(<]',
            "go": r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(',
            "javascript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))',
            "typescript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))',
            "java": r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+(\w+)\s*\(',
            "rust": r'(?:pub\s+)?fn\s+(\w+)\s*[\(<]',
        }
        pattern = patterns.get(language, r'(?:def|function|fun|func)\s+(\w+)\s*[\(\{]')
        for match in re.finditer(pattern, code):
            name = match.group(1) or (match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1))
            content_hash = hashlib.sha256(match.group(0).encode()).hexdigest()[:16]
            nodes.append({
                "file_path": file_path, "node_type": "function",
                "name": name, "start_byte": match.start(),
                "end_byte": match.end(), "content_hash": content_hash,
                "docstring": "", "complexity": 1, "connections": "[]",
            })
            self._store_node(nodes[-1])
        return nodes

    def _store_node(self, node_data):
        try:
            with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO ast_nodes
                    (file_path, node_type, name, start_byte, end_byte,
                     content_hash, docstring, complexity, connections)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (node_data["file_path"], node_data["node_type"],
                     node_data["name"], node_data["start_byte"],
                     node_data["end_byte"], node_data["content_hash"],
                     node_data["docstring"], node_data["complexity"],
                     node_data["connections"])
                )
        except Exception as e:
            logger.debug("Error storing node: %s", e)

    def _cyclomatic_complexity(self, func_node):
        complexity = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        return complexity

    def _extract_calls(self, func_node):
        calls = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        return list(set(calls))

    def _extract_class_connections(self, class_node):
        connections = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                connections.append(f"extends:{base.id}")
            elif isinstance(base, ast.Attribute):
                connections.append(f"extends:{base.attr}")
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                connections.append(f"method:{node.name}")
        return connections

    def get_node_info(self, target_name):
        with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM ast_nodes WHERE name LIKE ?",
                (f"%{target_name}%",)).fetchall()]

    def analyze_structure(self, code, language="python"):
        nodes = self.scan_code(code, "analysis_target", language)
        if not nodes:
            return {"functions": 0, "classes": 0, "imports": 0,
                    "max_complexity": 0, "total_complexity": 0,
                    "avg_complexity": 0, "connections": [],
                    "function_names": [], "class_names": []}
        functions = [n for n in nodes if n["node_type"] == "function"]
        classes = [n for n in nodes if n["node_type"] == "class"]
        imports = [n for n in nodes if n["node_type"] == "import"]
        all_connections = []
        for n in nodes:
            try:
                conns = json.loads(n.get("connections", "[]"))
                all_connections.extend(conns)
            except Exception:
                pass
        return {
            "functions": len(functions), "classes": len(classes),
            "imports": len(imports),
            "max_complexity": max((n["complexity"] for n in functions), default=0),
            "total_complexity": sum(n["complexity"] for n in functions),
            "avg_complexity": round(sum(n["complexity"] for n in functions) / max(len(functions), 1), 1),
            "connections": list(set(all_connections)),
            "function_names": [n["name"] for n in functions],
            "class_names": [n["name"] for n in classes],
        }
