"""
TITAN OMNISCALE X - Mediator Pattern

Centralized request/response dispatcher for agent coordination.
Replaces direct agent-to-agent coupling with a mediator that routes
requests to the appropriate handler.

Features:
- Type-based request routing
- Pipeline behaviors (middleware) for cross-cutting concerns
- Sync and async dispatch
- Thread-safe handler registration and dispatch
- Dispatch logging for observability

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

__all__ = [
    "Request",
    "Response",
    "Mediator",
]


# ============================================================
#  DATA CONTRACTS
# ============================================================

@dataclass
class Request:
    """
    Request payload dispatched through the Mediator.

    Attributes:
        request_type: Identifier used to route to the correct handler.
        payload: Arbitrary data carried by the request.
        metadata: Optional metadata for logging/tracing.
    """
    request_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_type:
            raise ValueError("request_type must not be empty")


@dataclass
class Response:
    """
    Response returned by a RequestHandler.

    Attributes:
        success: Whether the request was handled successfully.
        data: Result data from the handler.
        error: Error message if success is False.
        source: Identifier of the handler that produced this response.
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    source: str = ""


# ============================================================
#  HANDLER INTERFACE
# ============================================================

class RequestHandler(ABC):
    """
    Abstract base class for request handlers.

    Subclasses implement `handle` to process a Request and return a Response.
    Each handler is registered for a specific request_type.
    """

    @abstractmethod
    def handle(self, request: Request) -> Response:
        """
        Process the given request and return a response.

        Args:
            request: The Request to process.

        Returns:
            A Response indicating success or failure.
        """
        ...


# ============================================================
#  PIPELINE BEHAVIOR TYPE
# ============================================================

# A pipeline behavior is a callable that wraps handler execution.
# Signature: (request, next_handler) -> Response
# - request: The incoming Request
# - next_handler: A callable that invokes the next pipeline step
#   (or the actual handler if this is the last pipeline)
#
# Pipeline behaviors enable cross-cutting concerns like logging,
# validation, caching, and metrics without modifying handlers.
PipelineBehavior = Callable[[Request, Callable[[Request], Response]], Response]

# Async variant
AsyncPipelineBehavior = Callable[
    [Request, Callable[[Request], Awaitable[Response]]],
    Awaitable[Response],
]


# ============================================================
#  MEDIATOR
# ============================================================

class Mediator:
    """
    Centralized request/response dispatcher with pipeline behaviors.

    Routes requests to registered handlers based on request_type.
    Supports pipeline behaviors (middleware) for cross-cutting concerns
    such as logging, validation, caching, and metrics.

    Usage::

        mediator = Mediator()

        class AnalyzeHandler(RequestHandler):
            def handle(self, request):
                return Response(success=True, data={"result": 42}, source="analyze")

        mediator.register("analyze", AnalyzeHandler())
        response = mediator.send(Request(request_type="analyze"))

    Pipeline Behaviors::

        def logging_pipeline(request, next_handler):
            logger.info("Handling %s", request.request_type)
            response = next_handler(request)
            logger.info("Result: %s", response.success)
            return response

        mediator.add_pipeline(logging_pipeline)

    Thread Safety:
        All operations are protected by threading.Lock.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, RequestHandler] = {}
        self._pipelines: List[PipelineBehavior] = []
        self._async_pipelines: List[AsyncPipelineBehavior] = []
        self._lock = threading.Lock()
        self._dispatch_count: int = 0
        self._error_count: int = 0

    # ----------------------------------------------------------
    #  HANDLER REGISTRATION
    # ----------------------------------------------------------

    def register(self, request_type: str, handler: RequestHandler) -> None:
        """
        Register a handler for a specific request type.

        Args:
            request_type: The request type this handler handles.
            handler: A RequestHandler instance.

        Raises:
            ValueError: If request_type is empty or handler is None.
        """
        if not request_type:
            raise ValueError("request_type must not be empty")
        if handler is None:
            raise ValueError("handler must not be None")

        with self._lock:
            self._handlers[request_type] = handler
            logger.info(
                "Mediator: Registered handler %s for request_type '%s'",
                type(handler).__name__, request_type,
            )

    # ----------------------------------------------------------
    #  PIPELINE BEHAVIORS
    # ----------------------------------------------------------

    def add_pipeline(self, behavior_fn: PipelineBehavior) -> None:
        """
        Add a pipeline behavior (middleware) that wraps handler execution.

        Pipeline behaviors are executed in the order they are added.
        Each behavior receives the request and a `next` callable that
        invokes the next behavior (or the actual handler).

        Use pipeline behaviors for:
        - Logging
        - Input validation
        - Caching
        - Metrics collection
        - Authorization checks

        Args:
            behavior_fn: A callable with signature
                         (request, next_handler) -> Response
        """
        if behavior_fn is None:
            raise ValueError("behavior_fn must not be None")

        with self._lock:
            self._pipelines.append(behavior_fn)
            logger.debug(
                "Mediator: Added pipeline behavior '%s'",
                getattr(behavior_fn, '__name__', repr(behavior_fn)),
            )

    # ----------------------------------------------------------
    #  SYNC DISPATCH
    # ----------------------------------------------------------

    def send(self, request: Request) -> Response:
        """
        Synchronously dispatch a request to its registered handler.

        Pipeline behaviors are applied in order, wrapping the actual
        handler execution. If no handler is registered for the
        request_type, returns an error Response.

        Args:
            request: The Request to dispatch.

        Returns:
            A Response from the handler (or an error Response).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(request.request_type)
            pipelines = list(self._pipelines)

        # Log dispatch
        logger.info(
            "Mediator: Dispatching request_type='%s' (pipelines=%d)",
            request.request_type, len(pipelines),
        )

        if handler is None:
            error_msg = (
                f"No handler registered for request_type '{request.request_type}'"
            )
            logger.warning("Mediator: %s", error_msg)
            self._error_count_inc()
            return Response(
                success=False,
                error=error_msg,
                source="Mediator",
            )

        # Build the handler chain: outermost pipeline wraps the next,
        # innermost wraps the actual handler
        def _build_chain(
            handler_fn: Callable[[Request], Response],
            pipelines: List[PipelineBehavior],
        ) -> Callable[[Request], Response]:
            chain = handler_fn
            for pipeline in reversed(pipelines):
                chain = _wrap_pipeline(chain, pipeline)
            return chain

        try:
            chain = _build_chain(handler.handle, pipelines)
            response = chain(request)
            return response
        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "Mediator: Handler failed for request_type '%s': %s",
                request.request_type, exc,
                exc_info=True,
            )
            return Response(
                success=False,
                error=str(exc),
                source=type(handler).__name__,
            )

    # ----------------------------------------------------------
    #  ASYNC DISPATCH
    # ----------------------------------------------------------

    async def send_async(self, request: Request) -> Response:
        """
        Asynchronously dispatch a request to its registered handler.

        Supports async handlers and async pipeline behaviors.
        Sync handlers are automatically wrapped to run in the
        default executor.

        Args:
            request: The Request to dispatch.

        Returns:
            A Response from the handler (or an error Response).
        """
        with self._lock:
            self._dispatch_count += 1
            handler = self._handlers.get(request.request_type)
            pipelines = list(self._pipelines)
            async_pipelines = list(self._async_pipelines)

        logger.info(
            "Mediator[async]: Dispatching request_type='%s' "
            "(sync_pipelines=%d, async_pipelines=%d)",
            request.request_type, len(pipelines), len(async_pipelines),
        )

        if handler is None:
            error_msg = (
                f"No handler registered for request_type '{request.request_type}'"
            )
            logger.warning("Mediator[async]: %s", error_msg)
            self._error_count_inc()
            return Response(
                success=False,
                error=error_msg,
                source="Mediator",
            )

        try:
            # Wrap sync handler as async
            async def _async_handle(req: Request) -> Response:
                result = handler.handle(req)
                if asyncio.iscoroutine(result):
                    result = await result
                return result

            # Build async chain with async pipelines
            chain: Callable[[Request], Awaitable[Response]] = _async_handle

            # Apply async pipelines (reverse order for nesting)
            for pipeline in reversed(async_pipelines):
                prev_chain = chain

                async def _make_async_step(
                    req: Request,
                    _pipeline: AsyncPipelineBehavior = pipeline,
                    _next: Callable[[Request], Awaitable[Response]] = prev_chain,
                ) -> Response:
                    return await _pipeline(req, _next)

                chain = _make_async_step  # type: ignore[assignment]

            # Apply sync pipelines as async wrappers (reverse order)
            for pipeline in reversed(pipelines):
                prev_chain = chain

                async def _make_sync_step(
                    req: Request,
                    _pipeline: PipelineBehavior = pipeline,
                    _next: Callable[[Request], Awaitable[Response]] = prev_chain,
                ) -> Response:
                    # Wrap the async next in a sync-compatible way
                    def _sync_next(r: Request) -> Response:
                        # Run the async chain in a new event loop
                        # inside a dedicated thread to avoid
                        # "cannot run the event loop while another
                        # loop is running" errors on Xiaomi.
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            future = pool.submit(asyncio.run, _next(r))
                            return future.result()

                    return _pipeline(req, _sync_next)

                chain = _make_sync_step  # type: ignore[assignment]

            response = await chain(request)
            return response

        except Exception as exc:
            self._error_count_inc()
            logger.error(
                "Mediator[async]: Handler failed for request_type '%s': %s",
                request.request_type, exc,
                exc_info=True,
            )
            return Response(
                success=False,
                error=str(exc),
                source=type(handler).__name__,
            )

    # ----------------------------------------------------------
    #  UTILITIES
    # ----------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        """
        Runtime statistics for monitoring and debugging.

        Returns:
            Dict with:
            - dispatch_count: Total requests dispatched
            - errors_count: Total dispatch errors
            - registered_handlers: Number of registered handlers
            - registered_types: List of registered request types
            - pipeline_count: Number of registered pipeline behaviors
        """
        with self._lock:
            return {
                "dispatch_count": self._dispatch_count,
                "errors_count": self._error_count,
                "registered_handlers": len(self._handlers),
                "registered_types": list(self._handlers.keys()),
                "pipeline_count": len(self._pipelines),
            }

    def _error_count_inc(self) -> None:
        """Increment error counter in a thread-safe manner."""
        with self._lock:
            self._error_count += 1


# ============================================================
#  HELPER: Pipeline wrapper
# ============================================================

def _wrap_pipeline(
    next_fn: Callable[[Request], Response],
    pipeline: PipelineBehavior,
) -> Callable[[Request], Response]:
    """
    Wrap a handler callable with a pipeline behavior.

    Creates a closure that invokes the pipeline with the request
    and the next callable.

    Args:
        next_fn: The next handler or pipeline in the chain.
        pipeline: The pipeline behavior to wrap around next_fn.

    Returns:
        A new callable that applies the pipeline.
    """
    def _wrapped(request: Request) -> Response:
        return pipeline(request, next_fn)
    return _wrapped
