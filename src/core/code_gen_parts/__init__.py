"""
CodeGenerator — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.code_generator import CodeGenerator``
still works exactly as before.
"""

from ._extractors_mixin import ExtractorsMixin
from ._pipeline_mixin import PipelineMixin
from ._contextual_mixin import ContextualMixin


class CodeGenerator(ExtractorsMixin, PipelineMixin, ContextualMixin):
    """Generates code using pipeline intelligence (AST + Solver + MCTS)."""

    def __init__(self, orchestrator=None):
        self._orchestrator = orchestrator


__all__ = ["CodeGenerator"]
