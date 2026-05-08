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
_loop_thread = None
_loop_lock = threading.Lock()


def _shutdown_loop():
    """Close the shared event loop on shutdown."""
    global _shared_loop, _loop_thread
    with _loop_lock:
        if _shared_loop is not None and not _shared_loop.is_closed():
            try:
                _shared_loop.call_soon_threadsafe(_shared_loop.stop)
                _shared_loop.close()
                logger.info("HTTP: Shared event loop closed")
            except Exception as e:
                logger.debug("HTTP: Error closing event loop: %s", e)
            _shared_loop = None
            _loop_thread = None


def _is_loop_alive():
    """Check if the shared event loop AND its daemon thread are alive.

    The daemon thread can die silently (e.g. from a C extension crash in
    llama-cpp-python during GC).  If only the loop is checked but not the
    thread, ``run_coroutine_threadsafe`` enqueues work that is never
    executed, and every subsequent request hangs until
    TITAN_REQUEST_TIMEOUT — which is what the user sees as
    "se apaga el motor" (the motor shuts down).
    """
    if _shared_loop is None or _shared_loop.is_closed():
        return False
    if _loop_thread is None or not _loop_thread.is_alive():
        return False
    return True


def _get_shared_loop():
    """Get or create the shared asyncio event loop (thread-safe).

    The loop runs in a daemon thread so that async coroutines submitted
    via ``run_coroutine_threadsafe`` are actually executed.  Without a
    running loop the orchestrator's ``execute()`` coroutine would never
    be processed and every request would time out.

    CRITICAL FIX: Also detects when the daemon thread has died (even
    if the loop object is still open).  This happens when a C extension
    like llama-cpp-python crashes during garbage collection.  In that
    case we create a fresh loop + thread so the server recovers instead
    of hanging forever.
    """
    global _shared_loop, _loop_thread
    if not _is_loop_alive():
        with _loop_lock:
            # Double-check under lock (another thread may have recreated)
            if not _is_loop_alive():
                # Clean up old loop if it exists but thread is dead
                if _shared_loop is not None and not _shared_loop.is_closed():
                    try:
                        _shared_loop.close()
                    except Exception:
                        pass
                    logger.warning(
                        "HTTP: Daemon event loop thread died — recreating "
                        "(this is normal after a C extension crash)"
                    )
                _shared_loop = asyncio.new_event_loop()
                _loop_thread = threading.Thread(
                    target=_shared_loop.run_forever,
                    daemon=True,
                    name="titan-async-loop",
                )
                _loop_thread.start()
    return _shared_loop


_REQUEST_TIMEOUT = int(os.environ.get("TITAN_REQUEST_TIMEOUT", "120"))


def _run_async(coro):
    """Run an async coroutine on the shared event loop (thread-safe)."""
    loop = _get_shared_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=_REQUEST_TIMEOUT)


# Register atexit handler
atexit.register(_shutdown_loop)
