"""
ZENIC LOGIC - DNALoader — Facade

Cargador de Plantillas Maestras de ADN Técnico.

Thin facade: all implementation lives in dna_loader_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - dna_loader_parts._imports:                LogicModule, DomainRule, ValidationGate, GlossaryEntry dataclasses, constants
  - dna_loader_parts._glossary_mixin:         GlossaryMixin (glossary entry management)
  - dna_loader_parts._logic_modules_mixin:    LogicModulesMixin (logic module loading)
  - dna_loader_parts._loaders_mixin:          LoadersMixin (DNA YAML loading)
  - dna_loader_parts._domain_validation_mixin: DomainValidationMixin (domain rule validation)
  - dna_loader_parts._loader:                 DNALoader class (inherits all mixins) + get_dna_loader() singleton

Public API:
  Classes:    DNALoader, LogicModule, DomainRule, ValidationGate, GlossaryEntry
  Functions:  get_dna_loader
  Constants:  DNA_ROOT, YAML_AVAILABLE
"""

from .dna_loader_parts import *  # noqa: F401,F403
from .dna_loader_parts import (
    DNALoader, LogicModule, DomainRule, ValidationGate,
    GlossaryEntry, DNA_ROOT, YAML_AVAILABLE, get_dna_loader,
)

__all__ = [
    "DNALoader",
    "LogicModule",
    "DomainRule",
    "ValidationGate",
    "GlossaryEntry",
    "DNA_ROOT",
    "YAML_AVAILABLE",
    "get_dna_loader",
]
