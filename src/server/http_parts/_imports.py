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
    build_artifact_response,
)

# Open Design CORS origins
try:
    from src.core.open_design.config import get_open_design_config
    _open_design_available = True
except ImportError:
    _open_design_available = False

logger = logging.getLogger("TITAN")

# Configurable CORS origin
_cors_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# Build Open Design allowed origins set for dynamic CORS
_od_allowed_origins = set()
if _open_design_available:
    try:
        _od_config = get_open_design_config()
        _od_allowed_origins = set(_od_config.open_design_origins)
    except Exception:
        pass

def _get_cors_origin(request_origin: str = "") -> str:
    """Resolve the Access-Control-Allow-Origin header value.
    
    If the request Origin matches an Open Design origin, return it specifically
    (required for credentials=true). Otherwise fall back to the configured default.
    """
    if request_origin and request_origin in _od_allowed_origins:
        return request_origin
    return _cors_origin

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


_REQUEST_TIMEOUT = int(os.environ.get("TITAN_REQUEST_TIMEOUT", "300"))


def _run_async(coro):
    """Run an async coroutine on the shared event loop (thread-safe)."""
    loop = _get_shared_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=_REQUEST_TIMEOUT)


# Register atexit handler
atexit.register(_shutdown_loop)
