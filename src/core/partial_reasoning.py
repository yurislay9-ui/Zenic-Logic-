"""
Partial Reasoning Manager - Response Contract for OpenAI-compatible partial responses.

Thin facade: all implementation lives in partial_reason_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - partial_reason_parts._imports:  Shared imports and constants
  - partial_reason_parts.partial:    PartialMixin (build partial reasoning response)
  - partial_reason_parts.resume:     ResumeMixin (resume from partial reasoning state)
  - partial_reason_parts.manager:    PartialReasoningManager class (inherits all mixins)

Public API:
  Classes:    PartialReasoningManager
"""

from .partial_reason_parts import *  # noqa: F401,F403
