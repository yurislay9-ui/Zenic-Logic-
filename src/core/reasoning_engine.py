"""
TITAN OMNISCALE X - ReasoningEngine (Phase 8.1) — Facade

Motor de RAZONAMIENTO AVANZADO que va más allá de las tareas bounded de MiniAI.

Thin facade: all implementation lives in reasoning_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - reasoning_parts._imports:        ReasoningMode enum, ReasoningStep/ReasoningResult dataclasses, constants
  - reasoning_parts._helpers_mixin:  HelpersMixin (utility methods for reasoning)
  - reasoning_parts._context_mixin:  ContextMixin (context-aware reasoning)
  - reasoning_parts._reflect_mixin:  SelfReflectMixin (self-reflection and critique)
  - reasoning_parts._step_mixin:     StepByStepMixin (step-by-step chain reasoning)
  - reasoning_parts._engine:         ReasoningEngine class (inherits all mixins)

Public API:
  Classes:    ReasoningEngine, ReasoningMode, ReasoningStep, ReasoningResult
  Constants:  MAX_REASONING_STEPS, MAX_TOKENS_PER_STEP, MAX_REFLECT_ITERATIONS,
              REASONING_TIMEOUT_S, MIN_CONFIDENCE_ACCEPT
"""

from .reasoning_parts import *  # noqa: F401,F403
from .reasoning_parts import ReasoningEngine, ReasoningMode, ReasoningResult

__all__ = [
    "ReasoningEngine",
    "ReasoningMode",
    "ReasoningStep",
    "ReasoningResult",
    "MAX_REASONING_STEPS",
    "MAX_TOKENS_PER_STEP",
    "MAX_REFLECT_ITERATIONS",
    "REASONING_TIMEOUT_S",
    "MIN_CONFIDENCE_ACCEPT",
]
