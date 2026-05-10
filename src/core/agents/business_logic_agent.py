"""
TITAN OMNISCALE X - BusinessLogicAgent — Facade

Agente IA que reemplaza los 30+ LogicBlocks hardcoded con lógica de negocio
impulsada por IA.

Thin facade: all implementation lives in business_logic_agent_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - business_logic_agent_parts._imports:          VALID_OPERATION_TYPES, shared constants
  - business_logic_agent_parts._fallbacks_mixin:   FallbacksMixin (fallback logic when AI unavailable)
  - business_logic_agent_parts._agent:             BusinessLogicAgent class (inherits FallbacksMixin + BaseAgent)

Public API:
  Classes:    BusinessLogicAgent
  Constants:  VALID_OPERATION_TYPES
"""

from .business_logic_agent_parts import *  # noqa: F401,F403
from .business_logic_agent_parts import BusinessLogicAgent, VALID_OPERATION_TYPES

__all__ = [
    "BusinessLogicAgent",
    "VALID_OPERATION_TYPES",
]
