"""
TITAN OMNISCALE X - Theorem Cache (Pure Python)

Cache de teoremas en SQLite. Sin dependencias externas.
Compatible con Android.
"""
import sqlite3
import json
import hashlib
from src.core.shared.contracts import IntentPayload
from src.core.shared.db_initializer import get_db_path


class TheoremCache:
    def _hash(self, intent):
        composite = f"{intent.op}|{intent.goal}|{intent.target}|{intent.scrap_query}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent):
        try:
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                r = c.execute(
                    "SELECT solution_payload FROM theorems WHERE structural_hash=?",
                    (self._hash(intent),)
                ).fetchone()
                return json.loads(r[0]) if r else None
        except Exception:
            return None

    def save(self, intent, proof, sol):
        try:
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                c.execute(
                    "INSERT OR REPLACE INTO theorems (structural_hash, operation, proof_result, solution_payload) VALUES (?,?,?,?)",
                    (self._hash(intent), intent.op, proof, json.dumps(sol))
                )
        except Exception:
            pass
