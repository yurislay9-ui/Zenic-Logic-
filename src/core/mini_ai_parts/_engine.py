"""
MiniAIEngine main class — inherits from all mixins.
"""

from ._imports import IntentResult
from ._lifecycle import ModelLifecycleMixin
from ._tasks import BoundedTasksMixin
from ._fallbacks import FallbackMethodsMixin
from typing import Optional


class MiniAIEngine(ModelLifecycleMixin, BoundedTasksMixin, FallbackMethodsMixin):
    """
    Motor de IA semántico COPILOTO para el pipeline TITAN OMNISCALE X.

    Filosofía: Pipeline da superpoderes al LLM, LLM da intuición al pipeline.
    El LLM solo hace tareas cortas y bounded. Todo tiene fallback determinístico.
    """

    def __init__(self, model_path: Optional[str] = None, auto_load: bool = True):
        self._init_lifecycle(model_path=model_path, auto_load=auto_load)
