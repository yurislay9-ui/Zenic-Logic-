"""
TITAN OMNISCALE X v16 - Server Utilities

ThreadedHTTPServer, utilidades de red, rate limiter y funciones auxiliares
compartidas entre main.py (TUI/Textual) y main_headless.py (Termux).
"""

import socket
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from src.server.rate_limiter import RateLimiter


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Servidor HTTP multithread para manejar peticiones concurrentes."""
    daemon_threads = True
    allow_reuse_address = True


def get_local_ip():
    """
    Obtiene la IP local del dispositivo.

    Hace una conexion UDP temporal a 8.8.8.8 para determinar
    la IP de la interfaz de red activa.

    Returns:
        str: IP local o "127.0.0.1" si falla
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def configure_handler(
    orchestrator,
    governor=None,
    start_time=None,
    platform_tag="",
    rate_limiter=None,
):
    """
    Configura TitanHTTPHandler con las instancias necesarias.

    Debe llamarse antes de crear el servidor HTTP.

    Args:
        orchestrator: TitanOrchestrator instance
        governor: ResourceGovernor instance (opcional, solo headless)
        start_time: float - timestamp de inicio (opcional)
        platform_tag: str - identificador de plataforma (e.g. "termux-proot")
        rate_limiter: RateLimiter instance (opcional, proteccion contra flood)
    """
    from src.server.http_handler import TitanHTTPHandler
    TitanHTTPHandler.orchestrator = orchestrator
    TitanHTTPHandler.governor = governor
    TitanHTTPHandler.start_time = start_time
    TitanHTTPHandler.platform_tag = platform_tag
    TitanHTTPHandler.rate_limiter = rate_limiter
