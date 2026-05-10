"""
TITAN OMNISCALE X v16 - Distributed Tracing (Phase 5)

OpenTelemetry-compatible tracing with Jaeger/OTLP export.
Provides request-level and operation-level tracing with
correlation IDs that flow through the entire pipeline.

Features:
- OpenTelemetry SDK integration (when available)
- Automatic span creation for HTTP requests
- Correlation ID propagation to SAGA, EventBus, TaskQueue
- Graceful fallback to correlation-ID-only tracing when
  OpenTelemetry is not installed (e.g. Termux/ARM)
- Trace context injection into log records

Environment variables:
    TITAN_TRACING_ENABLED: 'true' to enable (default: false in dev)
    TITAN_TRACING_EXPORTER: 'jaeger', 'otlp', 'console' (default: console)
    TITAN_TRACING_ENDPOINT: Exporter endpoint URL
    TITAN_TRACING_SAMPLE_RATE: Sample rate 0.0-1.0 (default: 1.0)
"""

import contextlib
import functools
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar

from src.core.shared._version import TITAN_VERSION

logger = logging.getLogger(__name__)

__all__ = [
    "TracingConfig",
    "init_tracing",
    "get_tracer",
    "trace_span",
    "get_current_trace_id",
    "get_current_span_id",
    "inject_trace_context",
    "extract_trace_context",
]

# ── Global state ──────────────────────────────────────────
_tracer: Optional[Any] = None
_tracing_enabled: bool = False
_provider: Optional[Any] = None

# Thread-local for correlation IDs when OTel is unavailable
import threading
_trace_context: threading.local = threading.local()


@dataclass
class TracingConfig:
    """Configuration for distributed tracing.

    Attributes:
        enabled: Whether tracing is active.
        exporter: Export destination ('jaeger', 'otlp', 'console', 'none').
        endpoint: Exporter endpoint URL (e.g. 'http://jaeger:4317').
        service_name: Service name for trace attribution.
        sample_rate: Trace sample rate (0.0 to 1.0).
        max_span_attributes: Maximum attributes per span.
    """
    enabled: bool = False
    exporter: str = "console"
    endpoint: str = ""
    service_name: str = "titan-omniscale-x"
    sample_rate: float = 1.0
    max_span_attributes: int = 128

    @classmethod
    def from_env(cls) -> "TracingConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("TITAN_TRACING_ENABLED", "false").lower() == "true",
            exporter=os.getenv("TITAN_TRACING_EXPORTER", "console"),
            endpoint=os.getenv("TITAN_TRACING_ENDPOINT", ""),
            service_name=os.getenv("TITAN_SERVICE_NAME", "titan-omniscale-x"),
            sample_rate=float(os.getenv("TITAN_TRACING_SAMPLE_RATE", "1.0")),
        )


def init_tracing(config: Optional[TracingConfig] = None) -> bool:
    """Initialize the distributed tracing subsystem.

    Attempts to set up OpenTelemetry SDK. Falls back to
    correlation-ID-only mode if OTel dependencies are missing.

    Args:
        config: Tracing configuration. If None, reads from env.

    Returns:
        True if full OTel tracing was initialized,
        False if using correlation-ID fallback.
    """
    global _tracer, _tracing_enabled, _provider

    if config is None:
        config = TracingConfig.from_env()

    if not config.enabled:
        _tracing_enabled = False
        logger.info("Tracing: DISABLED (set TITAN_TRACING_ENABLED=true to enable)")
        return False

    # Try OpenTelemetry SDK
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": config.service_name,
            "service.version": TITAN_VERSION,
        })

        sampler = TraceIdRatioBased(rate=config.sample_rate)
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Configure exporter
        _setup_exporter(provider, config)

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(config.service_name, TITAN_VERSION)
        _provider = provider
        _tracing_enabled = True

        logger.info(
            "Tracing: ENABLED (exporter=%s, sample_rate=%.2f, service=%s)",
            config.exporter, config.sample_rate, config.service_name,
        )
        return True

    except ImportError:
        logger.info(
            "Tracing: OpenTelemetry not installed — using correlation-ID fallback"
        )
        _tracing_enabled = False
        return False
    except Exception as exc:
        logger.warning("Tracing: Initialization failed (%s) — using fallback", exc)
        _tracing_enabled = False
        return False


def _setup_exporter(provider: Any, config: TracingConfig) -> None:
    """Configure the trace exporter on the provider."""
    if config.exporter == "none":
        return

    if config.exporter == "console":
        try:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        except ImportError:
            pass
        return

    if config.exporter in ("jaeger", "otlp"):
        try:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            if config.exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                endpoint = config.endpoint or "http://localhost:4317"
                exporter = OTLPSpanExporter(endpoint=endpoint)
            else:
                # Jaeger OTLP (modern Jaeger supports OTLP natively)
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    endpoint = config.endpoint or "http://localhost:4317"
                    exporter = OTLPSpanExporter(endpoint=endpoint)
                except ImportError:
                    # Legacy Jaeger exporter
                    from opentelemetry.exporter.jaeger.thrift import (
                        JaegerExporter,
                    )
                    endpoint = config.endpoint or "http://localhost:14268/api/traces"
                    exporter = JaegerExporter(
                        agent_host_name=config.endpoint.split("://")[-1].split(":")[0] if config.endpoint else "localhost",
                        agent_port=int(os.getenv("TITAN_JAEGER_PORT", "6831")),
                    )

            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError as exc:
            logger.warning("Tracing: Exporter '%s' not available (%s)", config.exporter, exc)


def get_tracer() -> Optional[Any]:
    """Get the OpenTelemetry tracer (or None if not initialized)."""
    return _tracer


def get_current_trace_id() -> str:
    """Get the current trace ID from the active span or thread-local.

    Returns a 32-character hex string, or a new UUID if no trace is active.
    This is the key correlation ID that flows through all subsystems.
    """
    # Try OpenTelemetry first
    if _tracing_enabled:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.trace_id != 0:
                return format(ctx.trace_id, "032x")
        except Exception:
            pass

    # Fallback to thread-local
    trace_id = getattr(_trace_context, "trace_id", None)
    if trace_id:
        return trace_id

    # Generate new trace ID
    new_id = uuid.uuid4().hex
    _trace_context.trace_id = new_id
    return new_id


def get_current_span_id() -> str:
    """Get the current span ID from the active span or thread-local.

    Returns a 16-character hex string, or a new UUID if no span is active.
    """
    if _tracing_enabled:
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.span_id != 0:
                return format(ctx.span_id, "016x")
        except Exception:
            pass

    span_id = getattr(_trace_context, "span_id", None)
    if span_id:
        return span_id

    new_id = uuid.uuid4().hex[:16]
    _trace_context.span_id = new_id
    return new_id


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: Optional[Any] = None,
):
    """Context manager for creating a traced span.

    Works with or without OpenTelemetry. When OTel is not available,
    it manages correlation IDs in thread-local storage.

    Args:
        name: Span name (e.g. 'chat_completions', 'saga_step_execute').
        attributes: Optional dict of span attributes.
        kind: Span kind (SERVER, CLIENT, INTERNAL, etc.).

    Yields:
        The span object (OTel Span or a simple dict for fallback).
    """
    attrs = attributes or {}

    if _tracing_enabled and _tracer is not None:
        try:
            from opentelemetry import trace
            from opentelemetry.trace import SpanKind

            span_kind = kind
            if isinstance(kind, str):
                kind_map = {
                    "SERVER": SpanKind.SERVER,
                    "CLIENT": SpanKind.CLIENT,
                    "PRODUCER": SpanKind.PRODUCER,
                    "CONSUMER": SpanKind.CONSUMER,
                    "INTERNAL": SpanKind.INTERNAL,
                }
                span_kind = kind_map.get(kind.upper(), SpanKind.INTERNAL)

            with _tracer.start_as_current_span(name, kind=span_kind) as span:
                for k, v in attrs.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception:
                        pass
                # Also set thread-local for logging correlation
                ctx = span.get_span_context()
                _trace_context.trace_id = format(ctx.trace_id, "032x")
                _trace_context.span_id = format(ctx.span_id, "016x")
                yield span
                return
        except Exception as exc:
            logger.debug("trace_span: OTel error, falling back: %s", exc)

    # Fallback: correlation-ID-only tracing
    parent_trace_id = getattr(_trace_context, "trace_id", None)
    parent_span_id = getattr(_trace_context, "span_id", None)

    _trace_context.trace_id = parent_trace_id or uuid.uuid4().hex
    _trace_context.span_id = uuid.uuid4().hex[:16]

    fallback_span = {
        "name": name,
        "trace_id": _trace_context.trace_id,
        "span_id": _trace_context.span_id,
        "parent_span_id": parent_span_id,
        "attributes": attrs,
    }

    try:
        yield fallback_span
    finally:
        # Restore parent context
        _trace_context.trace_id = parent_trace_id or _trace_context.trace_id
        _trace_context.span_id = parent_span_id or _trace_context.span_id


def inject_trace_context(carrier: Dict[str, str]) -> Dict[str, str]:
    """Inject trace context into a carrier dict (for propagation).

    Used to propagate trace context to:
    - Task messages (DistributedTaskQueue)
    - SAGA steps (DistributedSagaCoordinator)
    - Event bus messages
    - HTTP headers for downstream calls

    Args:
        carrier: Dict to inject trace headers into.

    Returns:
        The carrier with trace headers added.
    """
    if _tracing_enabled:
        try:
            from opentelemetry import trace, propagate
            propagate.inject(carrier)
            return carrier
        except Exception:
            pass

    # Fallback: manual injection
    carrier["x-trace-id"] = get_current_trace_id()
    carrier["x-span-id"] = get_current_span_id()
    return carrier


def extract_trace_context(carrier: Dict[str, str]) -> Optional[Any]:
    """Extract trace context from a carrier dict.

    Args:
        carrier: Dict containing trace headers.

    Returns:
        OTel Context object, or None for fallback.
    """
    if _tracing_enabled:
        try:
            from opentelemetry import propagate
            return propagate.extract(carrier)
        except Exception:
            pass

    # Fallback: set thread-local from carrier
    trace_id = carrier.get("x-trace-id")
    span_id = carrier.get("x-span-id")
    if trace_id:
        _trace_context.trace_id = trace_id
    if span_id:
        _trace_context.span_id = span_id
    return None


# ── Decorator for tracing functions ──────────────────────

F = TypeVar("F", bound=Callable)


def traced(name: Optional[str] = None, **span_attrs: Any) -> Callable[[F], F]:
    """Decorator that wraps a function in a trace span.

    Usage:
        @traced("process_pipeline", pipeline_level=5)
        def process_request(query: str) -> dict:
            ...

    Args:
        name: Span name (defaults to function.__qualname__).
        **span_attrs: Static span attributes.
    """
    def decorator(func: F) -> F:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, attributes=span_attrs):
                return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name, attributes=span_attrs):
                return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator
