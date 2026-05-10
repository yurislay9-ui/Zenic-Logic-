"""
Code Generator - Pipeline-driven and contextual code generation.

Genera codigo usando datos del AST, solver y MCTS.
Incluye generacion contextual para Python, Kotlin, Go, y JavaScript.

Thin facade: all implementation lives in code_gen_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - code_gen_parts._extractors_mixin:   ExtractorsMixin (AST/solver data extraction)
  - code_gen_parts._pipeline_mixin:     PipelineMixin (pipeline-driven code generation)
  - code_gen_parts._contextual_mixin:   ContextualMixin (contextual multi-language generation)
  - code_gen_parts.__init__:            CodeGenerator class (inherits all mixins)

Public API:
  Classes:    CodeGenerator
"""

from .code_gen_parts import *  # noqa: F401,F403
from .code_gen_parts import CodeGenerator  # explicit

__all__ = ["CodeGenerator"]
