"""
ZENIC LOGIC - DNALoader — Facade

Cargador de Plantillas Maestras de ADN Técnico.

This module is a thin facade; all logic lives in dna_loader_parts/.
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
