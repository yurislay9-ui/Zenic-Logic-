"""
TITAN OMNISCALE X - ThinkingEngine (Qwen3-0.6B as Main Brain)

El CEREBRO del sistema. Qwen3-0.6B es el motor principal de razonamiento,
NO solo un copiloto. ThinkingEngine coordina:

  Qwen (PIENSA)  →  SemanticEngine (ENTIENDE)  →  SmartMemory (RECUERDA)

Thin facade: all implementation lives in thinking_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - thinking_parts._imports:          GenerationPlan, ThinkingResult dataclasses, constants, logger
  - thinking_parts._context_mixin:    ContextMixin (context window management)
  - thinking_parts._planning_mixin:   PlanningMixin (generation plan creation)
  - thinking_parts._reasoning_mixin:  ReasoningMixin (reasoning chain execution)
  - thinking_parts.__init__:          ThinkingEngine class (inherits all mixins)

Public API:
  Classes:    ThinkingEngine, GenerationPlan, ThinkingResult
  Constants:  APP_TEMPLATES, AUTOMATION_TEMPLATES
"""

from .thinking_parts import *  # noqa: F401,F403
from .thinking_parts import ThinkingEngine, GenerationPlan, ThinkingResult  # explicit

__all__ = ["ThinkingEngine", "GenerationPlan", "ThinkingResult"]
