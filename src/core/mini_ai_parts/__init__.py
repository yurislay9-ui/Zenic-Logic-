"""
MiniAIEngine sub-package — Qwen3-0.6B verdict + generative engine (v16.1).

Motor de VEREDICTO y GENERACIÓN:
  - VerdictMixin: La IA solo dice SÍ o NO (árbitro)
  - GenerativeMixin: La IA genera código, texto y completa código
  - Validación: Veredicto como gate de seguridad para código generado

v16.1: Añadido GenerativeMixin para generación de código real.
v17.1: Las 7 tareas bounded son 100% determinísticas.
       Solo verdict() y generate_*() usan el LLM.
"""

from ._imports import (
    MODEL_DIR, MODEL_FILENAME, MODEL_PATH,
    MAX_TOKENS_CLASSIFY, MAX_TOKENS_EXTRACT, MAX_TOKENS_PATTERN,
    MAX_TOKENS_TEMPLATE, MAX_TOKENS_GENERATE, MAX_TOKENS_EXPLAIN,
    MAX_TOKENS_SUBTASK, MAX_TOKENS_CODE_GENERATE, LLM_TIMEOUT_S, N_CTX, N_THREADS, TEMPERATURE,
    IntentResult,
)
from ._lifecycle import ModelLifecycleMixin
from ._tasks import BoundedTasksMixin
from ._fallbacks import FallbackMethodsMixin
from ._verdict_mixin import VerdictMixin
from ._generative_mixin import GenerativeMixin
from ._engine import MiniAIEngine

__all__ = [
    "MODEL_DIR", "MODEL_FILENAME", "MODEL_PATH",
    "MAX_TOKENS_CLASSIFY", "MAX_TOKENS_EXTRACT", "MAX_TOKENS_PATTERN",
    "MAX_TOKENS_TEMPLATE", "MAX_TOKENS_GENERATE", "MAX_TOKENS_EXPLAIN",
    "MAX_TOKENS_SUBTASK", "MAX_TOKENS_CODE_GENERATE",
    "LLM_TIMEOUT_S", "N_CTX", "N_THREADS", "TEMPERATURE",
    "IntentResult",
    "ModelLifecycleMixin",
    "BoundedTasksMixin",
    "FallbackMethodsMixin",
    "VerdictMixin",
    "GenerativeMixin",
    "MiniAIEngine",
]
