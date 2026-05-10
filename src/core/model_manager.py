"""
TITAN OMNISCALE X - Model Manager v16 (Hybrid Lazy Loading + Auto-Unload)

Thin facade: all implementation lives in model_mgr_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - model_mgr_parts._imports:       Shared constants (IDLE_TIMEOUT_S, RAM_BUDGET_MB, etc.)
  - model_mgr_parts.manager:        ModelManager class (inherits all mixins)
  - model_mgr_parts.unload:         UnloadMixin (model unloading methods)
  - model_mgr_parts.status:         StatusMixin (eager/lazy init, status and stats)
  - model_mgr_parts.semantic_access: SemanticAccessMixin (SemanticEngine access methods)
  - model_mgr_parts.ai_access:      AIAccessMixin (MiniAIEngine access methods)
  - model_mgr_parts.ram_mgmt:       RAMMixin (RAM budget management)
  - model_mgr_parts.monitor:        AutoUnloadMixin (auto-unload monitor methods)
  - model_mgr_parts.singleton:      get_model_manager(), init_model_manager() helpers

Public API:
  Classes:    ModelManager
  Functions:  get_model_manager, init_model_manager
  Constants:  IDLE_TIMEOUT_S, RAM_BUDGET_MB, ENABLE_AUTO_UNLOAD, ENABLE_LAZY_LOAD
"""

from .model_mgr_parts import *  # noqa: F401,F403
