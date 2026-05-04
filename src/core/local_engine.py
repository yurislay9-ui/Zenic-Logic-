"""
DEPRECATED: This module contains legacy engine implementations that are not used
by the current orchestrator pipeline. Kept for backward compatibility only.

TITAN OMNISCALE X - Motor Completo (Pure Python)

Este modulo contiene todo el motor logico sin dependencias nativas.
Compatible con Android via Buildozer.
"""

import hashlib
import json
import logging
import re
import sqlite3
import shutil
from pathlib import Path
import os

from src.core.shared.contracts import OperationType, GoalType


# === Detectar plataforma ===
IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ

logger = logging.getLogger(__name__)


# === Constantes ===


INTENT_KEYWORDS = {
    OperationType.CREATE: ["create", "new file", "implement", "add feature", "crear", "nuevo"],
    OperationType.REFACTOR: ["optimize", "refactor", "improve", "optimizar", "mejorar"],
    OperationType.DELETE: ["delete", "remove", "eliminate", "eliminar", "borrar"],
    OperationType.SEARCH: ["search", "find", "where", "buscar", "encontrar"],
}

GOAL_KEYWORDS = {
    GoalType.MODERN_PATTERN: ["modern", "update", "moderno", "actualizar"],
    GoalType.COMPLEXITY_REDUCTION: ["reduce", "faster", "simplify", "reducir", "rapido"],
    GoalType.BUG_FIX: ["fix", "correct", "bug", "error", "corregir"],
    GoalType.FEATURE_ADD: ["add", "new", "functionality", "agregar", "nueva"],
}

CRITICAL_PATTERNS = ["auth", "login", "crypto", "db"]


# === Utilidades ===

def get_data_dir():
    """Obtiene el directorio de datos segun la plataforma."""
    if IS_ANDROID:
        try:
            from android.storage import app_storage_path
            data_dir = Path(app_storage_path()) / "db"
        except ImportError:
            data_dir = Path.home() / ".titan_omniscale" / "db"
    else:
        data_dir = Path.home() / ".titan_omniscale" / "db"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path(db_name):
    return str(get_data_dir() / db_name)


def initialize_databases():
    """Crea las tablas SQLite si no existen."""
    with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, node_type TEXT NOT NULL,
            name TEXT NOT NULL, start_byte INTEGER NOT NULL, end_byte INTEGER NOT NULL,
            content_hash TEXT NOT NULL, UNIQUE(file_path, name, node_type))""")
    with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS theorems (
            structural_hash TEXT PRIMARY KEY, operation TEXT NOT NULL, proof_result TEXT NOT NULL,
            solution_payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")


# === Componentes del Motor ===

class SimpleParser:
    """Parser basado en palabras clave (sin fastembed)."""

    def parse(self, text):
        text_lower = text.lower()
        best_op, best_op_score = OperationType.SEARCH, 0
        best_goal, best_goal_score = GoalType.FEATURE_ADD, 0

        for op, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_op_score:
                best_op_score, best_op = score, op

        for goal, keywords in GOAL_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_goal_score:
                best_goal_score, best_goal = score, goal

        tgt = re.search(r'([\w\.-]+(?:\.kt|\.py|\.go|\.js|\.ts))', text)
        target = tgt.group(1) if tgt else "unknown"

        return {
            "op": best_op, "target": target, "goal": best_goal,
            "scrap_query": f"modern {best_goal} {best_op}" if best_op == OperationType.CREATE else "",
            "confidence": round((best_op_score + best_goal_score) / max(len(text_lower.split()), 1), 3)
        }


class SimpleRouter:
    """Router basado en patrones de criticidad."""

    def route(self, intent):
        is_critical = any(p in intent["target"].lower() for p in CRITICAL_PATTERNS)
        if is_critical or intent["op"] in [OperationType.DELETE, OperationType.REFACTOR]:
            return {"criticality": "SURGICAL_CRITICAL", "route": "DEEP_PATH",
                    "reason": "Nodo critico u operacion de riesgo."}
        if intent["op"] == OperationType.CREATE:
            return {"criticality": "DEEP_MODERATE", "route": "DEEP_PATH",
                    "reason": "Creacion requiere planificacion."}
        return {"criticality": "FAST_STANDARD", "route": "FAST_PATH",
                "reason": "Operacion estandar."}


class SimplePlanner:
    """Planificador de ejecucion."""

    def generate_plan(self, routing, intent):
        steps = []
        if intent["op"] == OperationType.CREATE:
            steps.append({"action": "SCRAPE_GITHUB", "target": intent["target"],
                          "query": intent["scrap_query"]})
            steps.append({"action": "INSERT_AST_NODE", "target": intent["target"]})
        elif intent["op"] == OperationType.REFACTOR:
            steps.append({"action": "REPLACE_AST_NODE", "target": intent["target"]})
        elif intent["op"] == OperationType.DELETE:
            steps.append({"action": "DELETE_AST_NODE", "target": intent["target"]})
        return steps


class SimpleCache:
    """Cache de teoremas en SQLite."""

    def _hash(self, intent):
        composite = f"{intent['op']}|{intent['goal']}|{intent['target']}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent):
        try:
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                r = c.execute("SELECT solution_payload FROM theorems WHERE structural_hash=?",
                              (self._hash(intent),)).fetchone()
                return json.loads(r[0]) if r else None
        except Exception:
            return None

    def save(self, intent, proof, sol):
        try:
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                c.execute("INSERT OR REPLACE INTO theorems (structural_hash, operation, proof_result, solution_payload) VALUES (?,?,?,?)",
                          (self._hash(intent), intent["op"], proof, json.dumps(sol)))
        except Exception as e:
            logger.debug(f"SimpleCache: Failed to save theorem to cache: {e}")


class SimpleLedger:
    """Ledger Merkle para snapshots y rollback."""

    def __init__(self):
        bk_dir = get_data_dir().parent / "backups"
        bk_dir.mkdir(exist_ok=True)
        self.bk_dir = bk_dir

    def snapshot(self, rel_path, project_dir):
        p = Path(project_dir) / rel_path
        if p.exists():
            import base64
            safe_name = base64.urlsafe_b64encode(rel_path.encode()).decode()
            shutil.copy2(p, self.bk_dir / safe_name)

    def commit(self, rel_path, content, project_dir):
        p = Path(project_dir) / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256(content.encode("utf-8")).hexdigest()
        p.write_text(content, encoding="utf-8")
        return {"file_path": rel_path, "hash_sha256": h}

    def rollback(self, rel_path, project_dir):
        import base64
        safe_name = base64.urlsafe_b64encode(rel_path.encode()).decode()
        bk = self.bk_dir / safe_name
        p = Path(project_dir) / rel_path
        if bk.exists():
            shutil.copy2(bk, p)


class SimpleSandbox:
    """Sandbox de validacion via compilacion Python."""

    def validate_code(self, code, language, target_name):
        if language == "python":
            try:
                compile(code, target_name, 'exec')
                return {"status": "PASS", "error_message": ""}
            except SyntaxError as e:
                return {"status": "FAIL_SYNTAX", "error_message": f"Error de sintaxis linea {e.lineno}: {e.msg}"}
        if code.strip():
            return {"status": "PASS", "error_message": ""}
        return {"status": "FAIL_SYNTAX", "error_message": "Codigo vacio"}


# === Motor Principal ===

class TitanEngine:
    """Motor TITAN OMNISCALE X - Version Android (Pure Python)."""

    def __init__(self):
        initialize_databases()
        self.parser = SimpleParser()
        self.router = SimpleRouter()
        self.planner = SimplePlanner()
        self.cache = SimpleCache()
        self.ledger = SimpleLedger()
        self.sandbox = SimpleSandbox()

    def execute(self, msg):
        """Ejecuta el pipeline completo del motor."""
        # N1 - Parse
        intent = self.parser.parse(msg)

        # N8 - Cache lookup
        cached = self.cache.lookup(intent)
        if cached:
            return {"status": "CACHED", "code": "// Servido desde Cache O(1)",
                    "hash": cached.get("h", "N/A"), "error": ""}

        # N2 - Route
        routing = self.router.route(intent)

        # N4 - Plan
        steps = self.planner.generate_plan(routing, intent)

        # N5 - Execute steps
        code = ""
        lang = "python"
        if ".kt" in intent["target"]:
            lang = "kotlin"
        elif ".go" in intent["target"]:
            lang = "go"

        for step in steps:
            if step["action"] == "SCRAPE_GITHUB":
                code = self._generate_template(intent["target"], lang)
            elif step["action"] == "REPLACE_AST_NODE":
                comment = "#" if lang == "python" else "//"
                code = f"{comment} Optimized version of {step['target']}\n"

        if not code:
            return {"status": "NO_OP", "code": "", "error": "No new code generated",
                    "hash": "N/A"}

        # N7 (Snapshot)
        p_dir = str(Path.home() / ".titan_omniscale" / "projects")
        Path(p_dir).mkdir(parents=True, exist_ok=True)
        self.ledger.snapshot(intent["target"], p_dir)

        # N6 (Trial)
        trial = self.sandbox.validate_code(code, lang, intent["target"])

        if trial["status"] == "PASS":
            node = self.ledger.commit(intent["target"], code, p_dir)
            self.cache.save(intent, "PROVEN", {"h": node["hash_sha256"][:8]})
            return {"status": "SUCCESS", "code": code, "hash": node["hash_sha256"][:12], "error": ""}
        else:
            self.ledger.rollback(intent["target"], p_dir)
            return {"status": "ROLLBACK", "code": code, "error": trial["error_message"],
                    "hash": "N/A"}

    def _generate_template(self, target, lang):
        """Genera codigo de plantilla cuando no hay scraping disponible."""
        templates = {
            "python": f'# Auto-generated for {target}\ndef main():\n    """Generated by TITAN OMNISCALE X"""\n    print("Hello from {target}")\n\nif __name__ == "__main__":\n    main()\n',
            "kotlin": f'// Auto-generated for {target}\nfun main() {{\n    println("Hello from {target}")\n}}\n',
            "go": f'// Auto-generated for {target}\npackage main\n\nimport "fmt"\n\nfunc main() {{\n    fmt.Println("Hello from {target}")\n}}\n',
        }
        return templates.get(lang, templates["python"])
