"""
TITAN OMNISCALE X - Semantic Parser (Pure Python)

Parser de intenciones basado en palabras clave.
Sin dependencias externas (fastembed, numpy, etc.)
"""
import re
from src.core.shared.contracts import IntentPayload, OperationType, GoalType


class SemanticParser:
    def __init__(self):
        self.intent_map = {
            OperationType.CREATE: ["create new file", "implement function", "add feature", "crear", "nuevo"],
            OperationType.REFACTOR: ["optimize this", "refactor", "improve performance", "optimizar", "mejorar"],
            OperationType.DELETE: ["delete function", "remove file", "eliminate dependency", "eliminar", "borrar"],
            OperationType.SEARCH: ["search where used", "find file", "where is defined", "buscar", "encontrar"],
        }
        self.goal_map = {
            GoalType.MODERN_PATTERN: ["use modern pattern", "update library", "moderno", "actualizar"],
            GoalType.COMPLEXITY_REDUCTION: ["reduce complexity", "faster", "simplify", "reducir", "rapido"],
            GoalType.BUG_FIX: ["fix error", "correct bug", "error", "corregir"],
            GoalType.FEATURE_ADD: ["add functionality", "new capability", "agregar", "nueva"],
        }

    def _keyword_match(self, text, keywords):
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return matches / len(keywords) if keywords else 0.0

    def parse(self, text):
        best_op, best_g = OperationType.SEARCH, GoalType.FEATURE_ADD
        best_s_op, best_s_g = 0.0, 0.0

        for op, keywords in self.intent_map.items():
            s = self._keyword_match(text, keywords)
            if s > best_s_op:
                best_s_op, best_op = s, op
        for g, keywords in self.goal_map.items():
            s = self._keyword_match(text, keywords)
            if s > best_s_g:
                best_s_g, best_g = s, g

        tgt = re.search(r'([\w\.-]+(?:\.kt|\.py|\.go|\.js|\.ts))', text)
        return IntentPayload(
            op=best_op, target=tgt.group(1) if tgt else "unknown", goal=best_g,
            scrap_query=f"modern {best_g} {best_op}" if best_op == OperationType.CREATE else "",
            confidence=round((best_s_op + best_s_g) / 2, 3)
        )
