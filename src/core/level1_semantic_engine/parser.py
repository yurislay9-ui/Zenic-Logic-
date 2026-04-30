from fastembed import TextEmbedding
import numpy as np
import re
from src.core.shared.contracts import IntentPayload, OperationType, GoalType

class SemanticParser:
    def __init__(self):
        self.model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self.intent_map = {
            OperationType.CREATE: ["create new file", "implement function", "add feature"],
            OperationType.REFACTOR: ["optimize this", "refactor", "improve performance"],
            OperationType.DELETE: ["delete function", "remove file", "eliminate dependency"],
            OperationType.SEARCH: ["search where used", "find file", "where is defined"]
        }
        self.goal_map = {
            GoalType.MODERN_PATTERN: ["use modern pattern", "update library"],
            GoalType.COMPLEXITY_REDUCTION: ["reduce complexity", "faster", "simplify"],
            GoalType.BUG_FIX: ["fix error", "correct bug"],
            GoalType.FEATURE_ADD: ["add functionality", "new capability"]
        }
        self.intent_vectors = {op: list(self.model.embed(examples)) for op, examples in self.intent_map.items()}
        self.goal_vectors = {g: list(self.model.embed(examples)) for g, examples in self.goal_map.items()}

    def _cosine_sim(self, v1, v2):
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    def parse(self, text: str) -> IntentPayload:
        query_v = list(self.model.embed([text]))[0]
        best_op, best_g = OperationType.SEARCH, GoalType.FEATURE_ADD
        best_s_op, best_s_g = -2.0, -2.0

        for op, vecs in self.intent_vectors.items():
            s = max(self._cosine_sim(query_v, v) for v in vecs)
            if s > best_s_op: best_s_op, best_op = s, op
        for g, vecs in self.goal_vectors.items():
            s = max(self._cosine_sim(query_v, v) for v in vecs)
            if s > best_s_g: best_s_g, best_g = s, g

        tgt = re.search(r'([\w\.-]+(?:\.kt|\.py|\.go|\.js|\.ts))', text)
        return IntentPayload(
            op=best_op, target=tgt.group(1) if tgt else "unknown", goal=best_g,
            scrap_query=f"modern {best_g.value} {best_op.value}" if best_op == OperationType.CREATE else "",
            confidence=round((best_s_op + best_s_g) / 2, 3)
        )
