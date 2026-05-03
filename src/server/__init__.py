"""
TITAN OMNISCALE X v16 - Server Package

Servidor HTTP OpenAI-compatible compartido entre Kivy y Termux.
Elimina la duplicacion de ~300 lineas entre main.py y main_headless.py.
"""

from src.server.http_handler import TitanHTTPHandler
from src.server.server import ThreadedHTTPServer, get_local_ip, configure_handler
from src.server.rate_limiter import RateLimiter
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)

__all__ = [
    "TitanHTTPHandler",
    "ThreadedHTTPServer",
    "get_local_ip",
    "configure_handler",
    "RateLimiter",
    "build_normal_response",
    "build_partial_reasoning_response",
    "build_error_response",
    "build_overloaded_response",
]
