"""
TITAN OMNISCALE X - Sandbox Isolation v16 — Facade

Sistema de aislamiento completo para el sandbox.

This module is a thin facade; all logic lives in sandbox_parts/.
"""

from .sandbox_parts import *  # noqa: F401,F403
from .sandbox_parts import (
    SandboxWorkspace, SandboxIsolationManager,
    get_isolation_manager, shutdown_isolation,
    create_sandbox_builtins, create_sandbox_globals,
)

__all__ = [
    "SandboxWorkspace", "SandboxIsolationManager",
    "get_isolation_manager", "shutdown_isolation",
    "create_sandbox_builtins", "create_sandbox_globals",
]
