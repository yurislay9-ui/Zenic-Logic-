"""
MiniAIEngine fallback methods (deterministic, no LLM needed).
"""

import re
import os
import json
import logging
from typing import Optional, Dict, Any

from ._imports import IntentResult


class FallbackMethodsMixin:
    """Fallback methods for MiniAIEngine (deterministic, no LLM needed)."""

    # ================================================================
    #  FALLBACK METHODS (deterministic, no LLM needed)
    # ================================================================

    def _fallback_classify(self, text: str) -> IntentResult:
        """Fallback: keyword-based intent classification."""
        text_lower = text.lower()

        op_keywords = {
            "CREATE": ["create", "new", "add", "implement", "crear", "nuevo", "agregar", "generar", "build", "make"],
            "REFACTOR": ["refactor", "restructure", "reorganize", "refactorizar", "reestructurar", "clean", "simplify"],
            "DELETE": ["delete", "remove", "eliminate", "eliminar", "borrar", "quitar", "drop"],
            "SEARCH": ["search", "find", "where", "locate", "buscar", "encontrar", "donde"],
            "ANALYZE": ["analyze", "review", "check", "analizar", "revisar", "verificar", "examine"],
            "EXPLAIN": ["explain", "describe", "what does", "explicar", "describir", "como funciona"],
            "DEBUG": ["debug", "fix", "correct", "bug", "error", "corregir", "arreglar", "depurar"],
            "OPTIMIZE": ["optimize", "improve", "faster", "optimizar", "mejorar", "acelerar", "performance"],
        }

        best_op, best_score = "SEARCH", 0
        for op, keywords in op_keywords.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_score:
                best_score, best_op = score, op

        return IntentResult(
            operation=best_op,
            goal=self._fallback_goal(text),
            confidence=min(best_score / 10.0, 0.5),  # Low confidence for fallback
            source="fallback",
        )

    def _fallback_goal(self, text: str) -> str:
        """Fallback: keyword-based goal classification."""
        text_lower = text.lower()
        goal_keywords = {
            "BUG_FIX": ["bug", "fix", "error", "corregir", "arreglar", "wrong", "broken", "falla"],
            "FEATURE_ADD": ["add", "new", "feature", "agregar", "nueva", "implement", "crear"],
            "SECURITY_HARDEN": ["security", "auth", "login", "token", "crypto", "vulnerability", "seguridad"],
            "PERFORMANCE": ["optimize", "fast", "slow", "performance", "optimizar", "rapido", "lento"],
            "MODERN_PATTERN": ["modern", "update", "upgrade", "moderno", "actualizar", "migrate"],
            "COMPLEXITY_REDUCTION": ["simplify", "reduce", "complex", "simplificar", "reducir", "complejo"],
            "READABILITY": ["readable", "clean", "comment", "legible", "limpio", "documentar"],
        }

        best_goal, best_score = "FEATURE_ADD", 0
        for goal, keywords in goal_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_goal = goal

        return best_goal

    def _fallback_extract(self, text: str) -> Dict[str, Any]:
        """Fallback: regex-based entity extraction."""
        # File extraction
        file_match = re.search(r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text)
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        lang_map = {
            ".py": "python", ".kt": "kotlin", ".go": "go",
            ".js": "javascript", ".ts": "typescript", ".java": "java",
            ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
        }
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = lang_map.get(ext, "unknown")

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

        return {
            "file": file_name,
            "lang": lang,
            "function": function,
            "source": "fallback",
        }

    def _fallback_pattern(self, pattern_desc: str, language: str) -> str:
        """Fallback: hardcoded pattern snippets."""
        patterns = {
            "python": {
                "async_await": "async def process(data):\n    result = await async_operation(data)\n    return result\n",
                "validator": "def validate(data: dict) -> bool:\n    required = ['id', 'name']\n    return all(k in data for k in required)\n",
                "repository": "class Repository:\n    def __init__(self, db):\n        self.db = db\n    def get_by_id(self, id):\n        return self.db.query(id)\n",
                "factory": "def create_handler(type_: str):\n    handlers = {'auth': AuthHandler, 'data': DataHandler}\n    return handlers.get(type_, DefaultHandler)\n",
                "middleware": "def middleware(func):\n    def wrapper(*args, **kwargs):\n        pre_process(*args)\n        result = func(*args, **kwargs)\n        post_process(result)\n        return result\n    return wrapper\n",
                "observer": "class Observable:\n    def __init__(self):\n        self._observers = []\n    def subscribe(self, observer):\n        self._observers.append(observer)\n    def notify(self, event):\n        for obs in self._observers:\n            obs.on_event(event)\n",
                "security": "import hashlib, secrets\n\ndef hash_password(password: str) -> str:\n    salt = secrets.token_hex(16)\n    return hashlib.sha256((salt + password).encode()).hexdigest()\n",
                "cache": "from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef get_data(key):\n    return expensive_lookup(key)\n",
                "default": "def generated_function(data):\n    \"\"\"Generated by TITAN OMNISCALE X\"\"\"\n    return data\n",
            },
            "kotlin": {
                "default": "fun generatedFunction(data: Any): Any {\n    return data\n}\n",
            },
            "go": {
                "default": "func generatedFunction(data interface{}) interface{} {\n\treturn data\n}\n",
            },
            "javascript": {
                "default": "function generatedFunction(data) {\n    return data;\n}\n",
            },
        }

        lang_patterns = patterns.get(language, patterns["python"])

        # Try to match pattern description
        desc_lower = pattern_desc.lower()
        for key, snippet in lang_patterns.items():
            if key in desc_lower or key.replace("_", " ") in desc_lower:
                return snippet

        return lang_patterns.get("default", patterns["python"]["default"])

    def _match_operation(self, text: str) -> Optional[str]:
        """Try to find a valid operation in a text response."""
        text_upper = text.upper()
        for op in self.VALID_OPERATIONS:
            if op in text_upper:
                return op
        return None

    def _match_goal(self, text: str) -> Optional[str]:
        """Try to find a valid goal in a text response."""
        if not text:
            return None
        text_upper = text.upper()
        for goal in self.VALID_GOALS:
            if goal in text_upper:
                return goal
        return None
