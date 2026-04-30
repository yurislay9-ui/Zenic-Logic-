import sqlite3, json, hashlib
from src.core.shared.contracts import IntentPayload
from src.core.shared.db_initializer import get_db_path

class TheoremCache:
    def _hash(self, i: IntentPayload) -> str:
        # Incluir target, op y goal para evitar colisiones de hash
        composite = f"{i.op.value}|{i.goal.value}|{i.target}|{i.scrap_query}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent: IntentPayload) -> dict | None:
        with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
            r = c.execute("SELECT solution_payload FROM theorems WHERE structural_hash=?", (self._hash(intent),)).fetchone()
            return json.loads(r[0]) if r else None

    def save(self, intent: IntentPayload, proof: str, sol: dict):
        with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
            c.execute(
                "INSERT OR REPLACE INTO theorems (structural_hash, operation, proof_result, solution_payload) VALUES (?,?,?,?)",
                (self._hash(intent), intent.op.value, proof, json.dumps(sol))
            )
