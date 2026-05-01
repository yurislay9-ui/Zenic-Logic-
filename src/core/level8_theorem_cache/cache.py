"""
TITAN OMNISCALE X - Theorem Cache v13 (Skeleton Hash Real)

Cache de teoremas con destilacion topologica (skeleton hash).
Normaliza AST, elimina nombres de variables, y guarda esqueletos
estructurales para bypass O(1) en mutaciones repetidas.

Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import hashlib
import sqlite3
import json
import logging
from src.core.shared.contracts import IntentPayload
from src.core.shared.db_initializer import get_db_path

logger = logging.getLogger(__name__)


class TheoremCache:
    """
    Cache con destilacion topologica.
    
    Implementa el Nivel 8 del documento de arquitectura:
    - Hash compuesto (operacion + objetivo + target) para lookup directo
    - Skeleton hash (topologia AST pura sin nombres) para bypass estructural
    - Hit counter para metricas de eficiencia
    """

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
        structure = re.sub(r'\b\w+\b', 'X', code)
        structure = re.sub(r'".*?"', '"S"', structure)
        structure = re.sub(r"'.*?'", "'S'", structure)
        structure = re.sub(r'#.*', '', structure)
        return hashlib.sha256(structure.encode()).hexdigest()

    def _hash(self, intent):
        """Hash compuesto basado en operacion, objetivo y target."""
        composite = f"{intent.op}|{intent.goal}|{intent.target}"
        return hashlib.sha256(composite.encode()).hexdigest()

    def lookup(self, intent, code=None, language="python"):
        """
        Busca en la cache usando hash compuesto primero,
        luego skeleton hash como fallback estructural.
        """
        try:
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                # Busqueda directa por hash compuesto
                r = c.execute(
                    "SELECT solution_payload, hit_count FROM theorems WHERE structural_hash=?",
                    (self._hash(intent),)).fetchone()
                if r:
                    c.execute(
                        "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE structural_hash=?",
                        (self._hash(intent),))
                    return {"source": "composite_hash", "data": json.loads(r[0]), "hits": r[1]}
                
                # Busqueda por skeleton hash (bypass experiencial)
                if code:
                    sk_hash = self._skeleton_hash(code, language)
                    r = c.execute(
                        "SELECT solution_payload, hit_count FROM theorems WHERE skeleton_hash=?",
                        (sk_hash,)).fetchone()
                    if r:
                        c.execute(
                            "UPDATE theorems SET hit_count=hit_count+1, last_used=CURRENT_TIMESTAMP WHERE skeleton_hash=?",
                            (sk_hash,))
                        return {"source": "skeleton_hash", "data": json.loads(r[0]), "hits": r[1]}
        except Exception as e:
            logger.debug("Cache lookup error: %s", e)
        return None

    def save(self, intent, proof, sol, code=None, language="python"):
        """Guarda una demostracion con hash compuesto y skeleton hash."""
        try:
            skeleton_hash = None
            if code:
                skeleton_hash = self._skeleton_hash(code, language)
            with sqlite3.connect(get_db_path("theorem_cache.sqlite")) as c:
                c.execute(
                    """INSERT OR REPLACE INTO theorems
                    (structural_hash, operation, goal, proof_result, solution_payload, skeleton_hash)
                    VALUES (?,?,?,?,?,?)""",
                    (self._hash(intent), intent.op, intent.goal, proof,
                     json.dumps(sol), skeleton_hash))
        except Exception as e:
            logger.debug("Cache save error: %s", e)
