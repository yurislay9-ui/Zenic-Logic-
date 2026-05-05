"""
TITAN OMNISCALE X — Single source of truth for version information.

All version references should import from this module:
    from src.core.shared._version import TITAN_VERSION, TITAN_VERSION_STR

This avoids inconsistencies between main.py, main_headless.py,
install_termux.sh, and README.md.
"""

TITAN_VERSION: str = "18"
"""Numeric version string (e.g. '18')."""

TITAN_VERSION_STR: str = f"v{TITAN_VERSION}"
"""Prefixed version string (e.g. 'v18')."""

TITAN_FULL_NAME: str = f"TITAN OMNISCALE X {TITAN_VERSION_STR}"
"""Full product name with version (e.g. 'TITAN OMNISCALE X v18')."""
