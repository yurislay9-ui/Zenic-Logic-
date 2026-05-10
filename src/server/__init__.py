"""
TITAN OMNISCALE X v16 - Server Package

Servidor HTTP OpenAI-compatible compartido entre TUI (Textual) y Termux.
Elimina la duplicacion de ~300 lineas entre main.py y main_headless.py.

SaaS Phase 1: FastAPI server with auth, tenants, rate limiting.
"""

from src.server.http_handler import TitanHTTPHandler
from src.server.server import ThreadedHTTPServer, get_local_ip, configure_handler
from src.server.rate_limiter import RateLimiter

__all__ = [
    "TitanHTTPHandler",
    "ThreadedHTTPServer",
    "get_local_ip",
    "configure_handler",
    "RateLimiter",
]
