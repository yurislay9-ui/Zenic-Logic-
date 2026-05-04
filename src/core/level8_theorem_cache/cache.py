"""
TITAN OMNISCALE X - Theorem Cache v16 (Skeleton Hash + LRU Eviction)

Cache de teoremas con destilacion topologica (skeleton hash).
Normaliza AST, elimina nombres de variables, y guarda esqueletos
estructurales para bypass O(1) en mutaciones repetidas.

v16 EVICTION: Politica LRU con limite de entradas y limpieza automatica.
Previene que la cache crezca sin control en dispositivos ARM con RAM limitada.

Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import hashlib
import json
import time
import logging
from src.core.shared.contracts import IntentPayload
from src.core.shared.db_initializer import get_connection

logger = logging.getLogger(__name__)

__all__ = ["TheoremCache"]


class TheoremCache:
    """
    Cache con destilacion topologica + politica de eviction LRU.

    Implementa el Nivel 8 del documento de arquitectura:
    - Hash compuesto (operacion + objetivo + target) para lookup directo
    - Skeleton hash (topologia AST pura sin nombres) para bypass estructural
    - Hit counter para metricas de eficiencia
    - LRU eviction: elimina entradas menos usadas cuando se alcanza el limite
    - Max entries configurable para ARM (default: 500)
    - Auto-eviction en cada save si el limite se supera
    """

    def __init__(self, max_entries: int = 500):
        """
        Inicializa el cache con politica de eviction.

        Args:
            max_entries: Maximo numero de entradas en cache (default 500).
                        En ARM con 12GB RAM, 500 entries ~ 5MB es seguro.
        """
        self.max_entries = max_entries

    def _skeleton_hash(self, code, language="python"):
        """
        Genera un hash de la topologia sintactica pura del codigo.

        Elimina todos los rasgos humanos (nombres de variables, strings)
        y guarda solo el "esqueleto" estructural.

        Ejemplo: Una funcion con 3 args, 2 ifs y 1 return
        genera: "FN(3,2,1)" -> hash SHA256
        """
        if language == "python":
            try:
                tree = ast.parse(code)
                skeleton_parts = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        num_args = len(node.args.args)
                        complexity = sum(1 for n in ast.walk(node)
                                       if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)))
                        num_returns = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))
                        skeleton_parts.append(f"FN({num_args},{complexity},{num_returns})")
                    elif isinstance(node, ast.ClassDef):
                        num_methods = sum(1 for n in node.body
                                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
                        skeleton_parts.append(f"CLS({num_methods})")
                    elif isinstance(node, ast.Import):
                        skeleton_parts.append("IMP")
                    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
                        skeleton_parts.append("COMP")
                skeleton = "|".join(skeleton_parts)
                return hashlib.sha256(skeleton.encode()).hexdigest()
            except SyntaxError:
                pass

        # Fallback para otros lenguajes: normalizar por regex
        structure = re.sub(r'\b(?!def|class|return|if|for|while|try|with|import|from|else|elif|pass|raise|except|async|await|yield|break|continue|lambda|not|and|or|is|in|True|False|None)\w+\b', 'X', code)
        structure = re.sub(r'".*?"', '"S"', structure)
        structure = re.sub(r"'.*?'", "'S'", structure)
        structure = re.sub(r'#.*', '', structure)
        return hashlib.sha256(structure.encode()).hexdigest()

    def _hash(self, intent, code=None):
        """Hash compuesto basado en operacion, objetivo, target y codigo."""
        composite = f"{intent.op}|{intent.goal}|{intent.target}"
        if code:
            code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
            composite = f"{composite}|{code_hash}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent, code=None, language="python"):
        """
        Busca en la cache usando hash compuesto primero,
        luego skeleton hash como fallback estructural.
        """
        try:
            conn = get_connection("theorem_cache.sqlite")
            # Busqueda directa por hash compuesto
            intent_hash = self._hash(intent, code)
            r = conn.execute(
                "SELECT solution_payload, hit_count FROM theorems WHERE structural_hash=?",
                (intent_hash,)).fetchone()
            if r:
                conn.execute(
                    "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE structural_hash=?",
                    (intent_hash,))
                conn.commit()
                return {"source": "composite_hash", "data": json.loads(r[0]), "hits": r[1]}

            # Busqueda por skeleton hash (bypass experiencial)
            if code:
                sk_hash = self._skeleton_hash(code, language)
                r = conn.execute(
                    "SELECT solution_payload, hit_count FROM theorems WHERE skeleton_hash=?",
                    (sk_hash,)).fetchone()
                if r:
                    conn.execute(
                        "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE skeleton_hash=?",
                        (sk_hash,))
                    conn.commit()
                    return {"source": "skeleton_hash", "data": json.loads(r[0]), "hits": r[1]}
        except Exception as e:
            logger.debug("Cache lookup error: %s", e)
        return None

    def save(self, intent, proof, sol, code=None, language="python"):
        """
        Guarda una demostracion con hash compuesto y skeleton hash.
        Ejecuta eviction LRU si se supera el limite de entradas.
        """
        try:
            skeleton_hash = None
            if code:
                skeleton_hash = self._skeleton_hash(code, language)
            conn = get_connection("theorem_cache.sqlite")
            conn.execute(
                """INSERT INTO theorems
                (structural_hash, operation, goal, proof_result, solution_payload, skeleton_hash)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(structural_hash) DO UPDATE SET
                    proof_result=excluded.proof_result,
                    solution_payload=excluded.solution_payload,
                    skeleton_hash=excluded.skeleton_hash""",
                (self._hash(intent, code), intent.op, intent.goal, proof,
                 json.dumps(sol), skeleton_hash))
            conn.commit()

            # Eviction: eliminar entradas LRU si se supera el limite
            self._evict_if_needed(conn)
        except Exception as e:
            logger.debug("Cache save error: %s", e)

    def _evict_if_needed(self, conn):
        """
        Eviction LRU: elimina las entradas menos recientemente usadas
        cuando el cache supera el limite de entradas.

        Estrategia:
        1. Contar entradas actuales
        2. Si count > max_entries, eliminar las (count - max_entries) mas viejas
        3. Priorizar eliminacion de entradas con bajo hit_count
        4. Nunca eliminar entradas con hit_count > 50 (altamente valiosas)
        """
        try:
            count = conn.execute("SELECT COUNT(*) FROM theorems").fetchone()[0]

            if count <= self.max_entries:
                return

            # Calcular cuantas entradas eliminar (10% extra para evitar eviction frecuente)
            to_evict = count - int(self.max_entries * 0.9)

            if to_evict <= 0:
                return

            # LRU eviction: eliminar las mas viejas con menor hit_count
            # Proteger entradas altamente usadas (hit_count > 50)
            conn.execute(
                """DELETE FROM theorems
                WHERE rowid IN (
                    SELECT rowid FROM theorems
                    WHERE hit_count <= 50
                    ORDER BY last_used ASC, hit_count ASC
                    LIMIT ?
                )""",
                (to_evict,)
            )
            conn.commit()

            # Actualizar stats
            remaining = conn.execute("SELECT COUNT(*) FROM theorems").fetchone()[0]
            logger.info(
                "Cache eviction: removed %d entries, %d remaining (max: %d)",
                to_evict, remaining, self.max_entries
            )
        except Exception as e:
            logger.debug("Cache eviction error: %s", e)

    def get_stats(self) -> dict:
        """Retorna estadisticas del cache."""
        try:
            conn = get_connection("theorem_cache.sqlite")
            count = conn.execute("SELECT COUNT(*) FROM theorems").fetchone()[0]
            total_hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM theorems").fetchone()[0]
            avg_hits = conn.execute("SELECT COALESCE(AVG(hit_count), 0) FROM theorems").fetchone()[0]
            max_hits_row = conn.execute(
                "SELECT hit_count FROM theorems ORDER BY hit_count DESC LIMIT 1"
            ).fetchone()
            max_hits = max_hits_row[0] if max_hits_row else 0
            return {
                "entries": count,
                "max_entries": self.max_entries,
                "usage_pct": round(count / self.max_entries * 100, 1) if self.max_entries > 0 else 0,
                "total_hits": total_hits,
                "avg_hits": round(avg_hits, 1),
                "max_hits": max_hits,
            }
        except Exception:
            return {"entries": 0, "max_entries": self.max_entries, "usage_pct": 0}

    def clear(self):
        """Limpia todo el cache."""
        try:
            conn = get_connection("theorem_cache.sqlite")
            conn.execute("DELETE FROM theorems")
            conn.commit()
            logger.info("Cache cleared")
        except Exception as e:
            logger.warning("Cache clear error: %s", e)
