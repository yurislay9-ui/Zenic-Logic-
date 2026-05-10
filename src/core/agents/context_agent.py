"""
TITAN OMNISCALE X - ContextAgent (F3) — Facade

Agente gestor de ventana de contexto que UNIFICA y OPTIMIZA la gestión
de contexto dispersa en múltiples subsistemas.

Thin facade: all implementation lives in context_agent_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - context_agent_parts._imports:        Constants (TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET, etc.), ContextEntry/ContextOutput/IntentOutput dataclasses
  - context_agent_parts._cables_mixin:   CablesMixin (cable-based context scoring and selection)
  - context_agent_parts._core_mixin:     CoreMixin (core context window management)
  - context_agent_parts._agent:          ContextAgent class (inherits all mixins + BaseAgent)

Public API:
  Classes:    ContextAgent, ContextEntry, ContextOutput, IntentOutput
  Constants:  TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET, RECENCY_DECAY_FACTOR,
              OP_RELEVANCE_WEIGHTS, GOAL_RELEVANCE_WEIGHTS,
              MAX_ENTRIES_FOR_SCORING, MAX_PREFETCH_RESULTS
"""

from .context_agent_parts import *  # noqa: F401,F403
from .context_agent_parts import (
    ContextAgent, TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET,
    ContextEntry, ContextOutput, IntentOutput,
)

__all__ = [
    "ContextAgent",
    "TOTAL_CONTEXT_BUDGET",
    "DEFAULT_TOKEN_BUDGET",
    "RECENCY_DECAY_FACTOR",
    "OP_RELEVANCE_WEIGHTS",
    "GOAL_RELEVANCE_WEIGHTS",
    "MAX_ENTRIES_FOR_SCORING",
    "MAX_PREFETCH_RESULTS",
    "ContextEntry",
    "ContextOutput",
    "IntentOutput",
]
