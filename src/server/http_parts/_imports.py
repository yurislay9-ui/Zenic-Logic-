"""
Shared imports and async event loop for http_parts sub-modules.
"""

import json
import logging
import time
import asyncio
import threading
import atexit
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from src.core.shared.contracts import HAS_Z3
from src.server.rate_limiter import RateLimiter
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)

logger = logging.getLogger("TITAN")

# Configurable CORS origin
_cors_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# Shared asyncio event loop
_shared_loop = None
_loop_lock = threading.Lock()


def _shutdown_loop():
    """Close the shared event loop on shutdown."""
    global _shared_loop
    with _loop_lock:
        if _shared_loop is not None and not _shared_loop.is_closed():
            try:
                _shared_loop.call_soon_threadsafe(_shared_loop.stop)
                _shared_loop.close()
                logger.info("HTTP: Shared event loop closed")
            except Exception as e:
                logger.debug("HTTP: Error closing event loop: %s", e)
            _shared_loop = None


def _get_shared_loop():
    """Get or create the shared asyncio event loop (thread-safe)."""
    global _shared_loop
    if _shared_loop is None or _shared_loop.is_closed():
        with _loop_lock:
            if _shared_loop is None or _shared_loop.is_closed():
                _shared_loop = asyncio.new_event_loop()
    return _shared_loop


def _run_async(coro):
    """Run an async coroutine on the shared event loop (thread-safe)."""
    loop = _get_shared_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


# Register atexit handler
atexit.register(_shutdown_loop)
