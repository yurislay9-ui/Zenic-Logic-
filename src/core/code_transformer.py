"""
Code Transformer - Refactoring, bug fixing, and optimization.

Thin facade: all implementation lives in code_trans_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - code_trans_parts.refactor:     RefactorMixin (Python refactoring with type annotations)
  - code_trans_parts.fixer:        FixerMixin (Python bug fixing: resource leaks, missing returns)
  - code_trans_parts.optimizer:    OptimizerMixin (function optimization with guard clauses)
  - code_trans_parts.transformer:  CodeTransformer class (inherits all mixins)

Public API:
  Classes:    CodeTransformer
"""

from .code_trans_parts import *  # noqa: F401,F403
