"""
ZENIC LOGIC - TemplateEngine (Jinja2-Powered Code Generation + Niche Templates)

Motor de templates externos que reemplaza los f-strings inline.
Carga templates .j2 desde src/templates/, los compone con bloques,
y genera codigo funcional, no stubs.

Thin facade: all implementation lives in template_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - template_parts._imports:         TemplateBlock, CompositionPlan dataclasses, constants, logger
  - template_parts._core_mixin:      CoreRenderMixin (core template rendering logic)
  - template_parts._block_mixin:     BlockNicheMixin (niche block composition)
  - template_parts._resolve_mixin:   ResolveMixin (template resolution and lookup)
  - template_parts._builtin_mixin:   BuiltinMixin (built-in template blocks)
  - template_parts._utils_mixin:     UtilsMixin (utility helpers, case converters)
  - template_parts.__init__:         TemplateEngine class (inherits all mixins)

Public API:
  Classes:    TemplateEngine, TemplateBlock, CompositionPlan
  Constants:  JINJA2_AVAILABLE, TEMPLATE_ROOT
"""

from .template_parts import *  # noqa: F401,F403
from .template_parts import TemplateEngine, TemplateBlock, CompositionPlan  # explicit

__all__ = ["TemplateEngine", "TemplateBlock", "CompositionPlan"]
