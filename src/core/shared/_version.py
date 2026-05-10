"""
TITAN OMNISCALE X — Single source of truth for version information.

All version references should import from this module:
    from src.core.shared._version import TITAN_VERSION, TITAN_VERSION_STR

This avoids inconsistencies between main.py, main_headless.py,
install_termux.sh, and README.md.

v18.0: Unified architecture — DAGOrchestrator is the primary orchestrator
       with optional VerdictEngine integration. TitanOrchestrator delegates
       to DAGOrchestrator. ConversationState + ReferenceResolver for
       multi-turn context. ResponseSynthesizer as single source of truth.
"""

TITAN_VERSION: str = "18.0"
"""Numeric version string (e.g. '18.0'). v18 unified DAG + Verdict architecture."""

TITAN_VERSION_STR: str = f"v{TITAN_VERSION}"
"""Prefixed version string (e.g. 'v18.0')."""

TITAN_FULL_NAME: str = f"TITAN OMNISCALE X {TITAN_VERSION_STR}"
"""Full product name with version (e.g. 'TITAN OMNISCALE X v18.0')."""
