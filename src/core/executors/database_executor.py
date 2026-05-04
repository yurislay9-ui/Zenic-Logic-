"""
TITAN OMNISCALE X - DatabaseExecutor (Phase 7.1)

Ejecutor de operaciones reales en SQLite.
"""

import os, time, sqlite3, logging, asyncio
from typing import Any, Dict

from .base import ActionExecutor, ActionResult, _validate_sql

logger = logging.getLogger(__name__)


class DatabaseExecutor(ActionExecutor):
    """Ejecutor de operaciones reales en SQLite. TODAS las queries usan placeholders (?).

    Config: {db_path, operation, query, params, script, destination}
    Operations: query, insert, update, delete, backup, script
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        db_path = config.get("db_path", ":memory:")
        operation = config.get("operation", "query").lower()
        query = config.get("query", "")
        params = config.get("params", [])
        script = config.get("script", "")

        if not isinstance(params, (list, tuple)): params = [params]

        valid_ops = {"query", "insert", "update", "delete", "backup", "script"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid DB operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))

        if operation == "backup":
            return await self._backup(db_path, config.get("destination", ""), start)
        if operation == "script":
            return await self._execute_script(db_path, script, start)
        if not query:
            return ActionResult(False, {}, "No SQL query provided", self._elapsed_ms(start))

        if not _validate_sql(query):
            return ActionResult(False, {"query": query}, "SQL validation failed: dangerous pattern detected", self._elapsed_ms(start))
        try:
            result_data = await asyncio.to_thread(self._execute_db, db_path, operation, query, params)
            elapsed = self._elapsed_ms(start)
            logger.info(f"DatabaseExecutor: {operation} on {db_path} completed")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"DatabaseExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "query": query}, str(e), elapsed)

    def _execute_db(self, db_path, operation, query, params):
        """Ejecuta la operación en SQLite (síncrono, desde thread)."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(query, params)
            if operation == "query":
                rows = [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return {"rows": rows, "row_count": len(rows)}
            conn.commit()
            return {"affected_rows": cursor.rowcount, "lastrowid": cursor.lastrowid}
        finally: conn.close()

    async def _backup(self, db_path, destination, start):
        """Realiza backup de la base de datos SQLite."""
        if db_path == ":memory:":
            return ActionResult(False, {}, "Cannot backup in-memory database", self._elapsed_ms(start))
        if not os.path.exists(db_path):
            return ActionResult(False, {"db_path": db_path}, f"Database file not found: {db_path}", self._elapsed_ms(start))
        try:
            if not destination: destination = db_path + f".backup_{int(time.time())}"
            def _do_backup():
                src = sqlite3.connect(db_path); dst = sqlite3.connect(destination)
                src.backup(dst); dst.close(); src.close()
            await asyncio.to_thread(_do_backup)
            size = os.path.getsize(destination)
            logger.info(f"DatabaseExecutor: Backup created at {destination} ({size} bytes)")
            return ActionResult(True, {"source": db_path, "destination": destination, "size_bytes": size},
                                duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {"db_path": db_path}, f"Backup failed: {e}", self._elapsed_ms(start))

    async def _execute_script(self, db_path, script, start):
        """Ejecuta un script SQL con múltiples statements."""
        if not script:
            return ActionResult(False, {}, "No SQL script provided", self._elapsed_ms(start))
        try:
            def _run():
                conn = sqlite3.connect(db_path)
                try: conn.executescript(script); conn.commit()
                finally: conn.close()
            await asyncio.to_thread(_run)
            return ActionResult(True, {"script_lines": len(script.split(";"))}, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {}, f"Script execution failed: {e}", self._elapsed_ms(start))
