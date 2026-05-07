"""
TitanHTTPHandler — facade re-exporting all sub-modules.

Backward-compatible: ``from src.server.http_handler import TitanHTTPHandler``
still works exactly as before.
"""

from http.server import BaseHTTPRequestHandler
from ._imports import (
    logger, HAS_Z3, RateLimiter, _run_async, _get_shared_loop,
    _shutdown_loop, _cors_origin,
)
from ._get_mixin import GetMixin
from ._post_mixin import PostMixin
from ._helpers_mixin import HelpersMixin


class TitanHTTPHandler(GetMixin, PostMixin, HelpersMixin, BaseHTTPRequestHandler):
    """
    Handler HTTP compatible con la API de OpenAI + App/Automation generation.

    Atributos de clase (configurar antes de iniciar el servidor):
        orchestrator: TitanOrchestrator instance
        governor: ResourceGovernor instance (opcional, solo headless)
        start_time: float - timestamp de inicio del servidor (opcional)
        platform_tag: str - "tui" o "termux-proot"
    """

    orchestrator = None
    governor = None
    start_time = None
    platform_tag = ""
    rate_limiter = None


__all__ = [
    "TitanHTTPHandler",
    "_run_async",
    "_get_shared_loop",
    "_shutdown_loop",
]
