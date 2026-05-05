"""
TITAN OMNISCALE X v16 - Prometheus Metrics (Phase 5)

Standard Prometheus client library integration for production metrics.
Replaces the custom text-format metrics with proper Prometheus
counters, gauges, histograms, and summaries.

Features:
- Standard prometheus_client library integration
- HTTP request duration histogram (latency distribution)
- Request counter by method/path/status
- Active requests gauge
- Rate limiter metrics (accepted/rejected)
- Circuit breaker state gauge
- Task queue depth gauge
- Tenant usage counters
- Resource governor metrics (RAM/CPU)
- Graceful fallback to custom metrics when prometheus_client unavailable

Environment variables:
    TITAN_METRICS_ENABLED: 'true' to enable (default: true)
    TITAN_METRICS_PORT: Port for metrics HTTP server (default: 9090)
    TITAN_METRICS_PATH: Metrics endpoint path (default: /metrics)
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "metrics_middleware",
]

# ── Singleton ─────────────────────────────────────────────
_instance: Optional["MetricsCollector"] = None
_instance_lock = threading.Lock()


@dataclass
class MetricsConfig:
    """Configuration for Prometheus metrics collection.

    Attributes:
        enabled: Whether Prometheus metrics are active.
        port: Port for standalone metrics server (0 = shared with app).
        path: Metrics endpoint path.
        namespace: Metric namespace prefix.
        histograms: Whether to enable histogram metrics.
        default_buckets: Default histogram buckets in seconds.
    """
    enabled: bool = True
    port: int = 0
    path: str = "/metrics"
    namespace: str = "titan"
    histograms: bool = True
    default_buckets: Tuple[float, ...] = (
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    )

    @classmethod
    def from_env(cls) -> "MetricsConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("TITAN_METRICS_ENABLED", "true").lower() == "true",
            port=int(os.getenv("TITAN_METRICS_PORT", "0")),
            path=os.getenv("TITAN_METRICS_PATH", "/metrics"),
        )


class MetricsCollector:
    """Centralized Prometheus metrics collection for TITAN OMNISCALE X.

    All metrics are lazily created on first use. The collector works
    with or without prometheus_client installed — when unavailable,
    it tracks counts internally and exports custom text format.

    Thread-safe: all operations are protected by locks.
    """

    def __init__(self, config: Optional[MetricsConfig] = None) -> None:
        self._config = config or MetricsConfig()
        self._lock = threading.Lock()
        self._prom_available = False

        # Internal counters for fallback mode
        self._request_count: int = 0
        self._request_count_by_path: Dict[str, int] = {}
        self._request_count_by_status: Dict[int, int] = {}
        self._active_requests: int = 0
        self._rate_limit_accepted: int = 0
        self._rate_limit_rejected: int = 0
        self._auth_success: int = 0
        self._auth_failure: int = 0
        self._circuit_breaker_open: Dict[str, bool] = {}
        self._task_queue_depth: Dict[str, int] = {}
        self._start_time: float = time.time()

        # Try to import prometheus_client
        self._init_prometheus()

    def _init_prometheus(self) -> None:
        """Initialize Prometheus client metrics if available."""
        try:
            import prometheus_client

            self._prom_available = True

            # ── Counters ──────────────────────────────────
            self._http_requests_total = prometheus_client.Counter(
                f"{self._config.namespace}_http_requests_total",
                "Total HTTP requests",
                ["method", "path", "status"],
            )
            self._rate_limit_accepted_total = prometheus_client.Counter(
                f"{self._config.namespace}_rate_limit_accepted_total",
                "Total accepted requests",
            )
            self._rate_limit_rejected_total = prometheus_client.Counter(
                f"{self._config.namespace}_rate_limit_rejected_total",
                "Total rejected requests",
            )
            self._auth_success_total = prometheus_client.Counter(
                f"{self._config.namespace}_auth_success_total",
                "Total successful authentications",
                ["auth_method"],
            )
            self._auth_failure_total = prometheus_client.Counter(
                f"{self._config.namespace}_auth_failure_total",
                "Total failed authentications",
                ["auth_method"],
            )
            self._tasks_completed_total = prometheus_client.Counter(
                f"{self._config.namespace}_tasks_completed_total",
                "Total completed tasks",
                ["task_type", "worker_id"],
            )
            self._tasks_failed_total = prometheus_client.Counter(
                f"{self._config.namespace}_tasks_failed_total",
                "Total failed tasks",
                ["task_type", "worker_id"],
            )

            # ── Gauges ────────────────────────────────────
            self._active_requests_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_active_requests",
                "Currently active requests",
            )
            self._ram_usage_mb_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_ram_usage_mb",
                "Current RAM usage in MB",
            )
            self._cpu_usage_pct_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_cpu_usage_pct",
                "Current CPU usage percentage",
            )
            self._uptime_seconds_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_uptime_seconds",
                "Server uptime in seconds",
            )
            self._circuit_breaker_state_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_circuit_breaker_state",
                "Circuit breaker state (0=closed, 1=open, 2=half_open)",
                ["name"],
            )
            self._task_queue_depth_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_task_queue_depth",
                "Task queue depth",
                ["queue_name"],
            )
            self._tenant_active_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_tenants_active",
                "Number of active tenants",
            )

            # ── Histograms ────────────────────────────────
            if self._config.histograms:
                self._http_request_duration_seconds = prometheus_client.Histogram(
                    f"{self._config.namespace}_http_request_duration_seconds",
                    "HTTP request duration in seconds",
                    ["method", "path"],
                    buckets=self._config.default_buckets,
                )
                self._task_duration_seconds = prometheus_client.Histogram(
                    f"{self._config.namespace}_task_duration_seconds",
                    "Task execution duration in seconds",
                    ["task_type"],
                    buckets=self._config.default_buckets,
                )

            logger.info(
                "MetricsCollector: Prometheus client initialized (namespace=%s)",
                self._config.namespace,
            )

        except ImportError:
            self._prom_available = False
            logger.info(
                "MetricsCollector: prometheus_client not installed — "
                "using internal counters with text format export"
            )

    # ── HTTP Request Tracking ──────────────────────────────

    def record_request(
        self,
        method: str,
        path: str,
        status: int,
        duration: float,
    ) -> None:
        """Record an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Request path.
            status: Response status code.
            duration: Request duration in seconds.
        """
        with self._lock:
            self._request_count += 1
            self._request_count_by_path[path] = self._request_count_by_path.get(path, 0) + 1
            self._request_count_by_status[status] = self._request_count_by_status.get(status, 0) + 1

        if self._prom_available:
            try:
                self._http_requests_total.labels(
                    method=method, path=path, status=str(status),
                ).inc()
                if self._config.histograms:
                    self._http_request_duration_seconds.labels(
                        method=method, path=path,
                    ).observe(duration)
            except Exception as exc:
                logger.debug("Metrics: Failed to record request: %s", exc)

    def inc_active_requests(self) -> None:
        """Increment the active requests counter."""
        with self._lock:
            self._active_requests += 1
        if self._prom_available:
            try:
                self._active_requests_gauge.inc()
            except Exception:
                pass

    def dec_active_requests(self) -> None:
        """Decrement the active requests counter."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
        if self._prom_available:
            try:
                self._active_requests_gauge.dec()
            except Exception:
                pass

    # ── Rate Limit Tracking ────────────────────────────────

    def record_rate_limit_accepted(self) -> None:
        """Record an accepted request (rate limiter allowed)."""
        with self._lock:
            self._rate_limit_accepted += 1
        if self._prom_available:
            try:
                self._rate_limit_accepted_total.inc()
            except Exception:
                pass

    def record_rate_limit_rejected(self) -> None:
        """Record a rejected request (rate limiter denied)."""
        with self._lock:
            self._rate_limit_rejected += 1
        if self._prom_available:
            try:
                self._rate_limit_rejected_total.inc()
            except Exception:
                pass

    # ── Auth Tracking ──────────────────────────────────────

    def record_auth_success(self, method: str = "jwt") -> None:
        """Record a successful authentication."""
        with self._lock:
            self._auth_success += 1
        if self._prom_available:
            try:
                self._auth_success_total.labels(auth_method=method).inc()
            except Exception:
                pass

    def record_auth_failure(self, method: str = "jwt") -> None:
        """Record a failed authentication."""
        with self._lock:
            self._auth_failure += 1
        if self._prom_available:
            try:
                self._auth_failure_total.labels(auth_method=method).inc()
            except Exception:
                pass

    # ── Circuit Breaker Tracking ───────────────────────────

    def update_circuit_breaker(self, name: str, state: str) -> None:
        """Update circuit breaker state metric.

        Args:
            name: Circuit breaker name.
            state: Current state ('closed', 'open', 'half_open').
        """
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        value = state_map.get(state, 0)
        with self._lock:
            self._circuit_breaker_open[name] = state != "closed"
        if self._prom_available:
            try:
                self._circuit_breaker_state_gauge.labels(name=name).set(value)
            except Exception:
                pass

    # ── Task Queue Tracking ────────────────────────────────

    def update_task_queue_depth(self, queue_name: str, depth: int) -> None:
        """Update task queue depth metric."""
        with self._lock:
            self._task_queue_depth[queue_name] = depth
        if self._prom_available:
            try:
                self._task_queue_depth_gauge.labels(queue_name=queue_name).set(depth)
            except Exception:
                pass

    def record_task_completed(self, task_type: str, worker_id: str, duration: float = 0.0) -> None:
        """Record a completed task."""
        if self._prom_available:
            try:
                self._tasks_completed_total.labels(
                    task_type=task_type, worker_id=worker_id,
                ).inc()
                if self._config.histograms and duration > 0:
                    self._task_duration_seconds.labels(task_type=task_type).observe(duration)
            except Exception:
                pass

    def record_task_failed(self, task_type: str, worker_id: str) -> None:
        """Record a failed task."""
        if self._prom_available:
            try:
                self._tasks_failed_total.labels(
                    task_type=task_type, worker_id=worker_id,
                ).inc()
            except Exception:
                pass

    # ── Resource Tracking ──────────────────────────────────

    def update_resources(self, ram_mb: float, cpu_pct: float) -> None:
        """Update resource usage metrics."""
        if self._prom_available:
            try:
                self._ram_usage_mb_gauge.set(ram_mb)
                self._cpu_usage_pct_gauge.set(cpu_pct)
            except Exception:
                pass

    def update_uptime(self, seconds: float) -> None:
        """Update uptime metric."""
        if self._prom_available:
            try:
                self._uptime_seconds_gauge.set(seconds)
            except Exception:
                pass

    def update_tenant_count(self, count: int) -> None:
        """Update active tenant count."""
        if self._prom_available:
            try:
                self._tenant_active_gauge.set(count)
            except Exception:
                pass

    # ── Export ─────────────────────────────────────────────

    def generate_text_metrics(self) -> str:
        """Generate Prometheus text-format metrics.

        Used when prometheus_client is not available, or for
        the /metrics endpoint in the FastAPI app.

        Returns:
            Prometheus text format string.
        """
        if self._prom_available:
            try:
                import prometheus_client
                return prometheus_client.generate_latest().decode("utf-8")
            except Exception:
                pass

        # Fallback: custom text format
        with self._lock:
            uptime = int(time.time() - self._start_time)
            lines = [
                f"# HELP {self._config.namespace}_uptime_seconds Server uptime in seconds",
                f"# TYPE {self._config.namespace}_uptime_seconds gauge",
                f"{self._config.namespace}_uptime_seconds {uptime}",
                f"# HELP {self._config.namespace}_requests_total Total HTTP requests",
                f"# TYPE {self._config.namespace}_requests_total counter",
                f"{self._config.namespace}_requests_total {self._request_count}",
                f"# HELP {self._config.namespace}_active_requests Currently active requests",
                f"# TYPE {self._config.namespace}_active_requests gauge",
                f"{self._config.namespace}_active_requests {self._active_requests}",
                f"# HELP {self._config.namespace}_rate_limit_accepted_total Total accepted requests",
                f"# TYPE {self._config.namespace}_rate_limit_accepted_total counter",
                f"{self._config.namespace}_rate_limit_accepted_total {self._rate_limit_accepted}",
                f"# HELP {self._config.namespace}_rate_limit_rejected_total Total rejected requests",
                f"# TYPE {self._config.namespace}_rate_limit_rejected_total counter",
                f"{self._config.namespace}_rate_limit_rejected_total {self._rate_limit_rejected}",
                f"# HELP {self._config.namespace}_auth_success_total Total successful authentications",
                f"# TYPE {self._config.namespace}_auth_success_total counter",
                f"{self._config.namespace}_auth_success_total {self._auth_success}",
                f"# HELP {self._config.namespace}_auth_failure_total Total failed authentications",
                f"# TYPE {self._config.namespace}_auth_failure_total counter",
                f"{self._config.namespace}_auth_failure_total {self._auth_failure}",
            ]

            # Per-status counters
            for status, count in sorted(self._request_count_by_status.items()):
                lines.append(
                    f'{self._config.namespace}_requests_total{{status="{status}"}} {count}'
                )

            # Circuit breaker states
            for name, is_open in self._circuit_breaker_open.items():
                value = 1 if is_open else 0
                lines.append(
                    f'{self._config.namespace}_circuit_breaker_state{{name="{name}"}} {value}'
                )

            # Queue depths
            for queue, depth in self._task_queue_depth.items():
                lines.append(
                    f'{self._config.namespace}_task_queue_depth{{queue_name="{queue}"}} {depth}'
                )

        return "\n".join(lines) + "\n"

    @property
    def is_prometheus_available(self) -> bool:
        """Whether prometheus_client is installed and initialized."""
        return self._prom_available


def get_metrics_collector(config: Optional[MetricsConfig] = None) -> MetricsCollector:
    """Get or create the singleton MetricsCollector.

    Args:
        config: Configuration (only used on first call).

    Returns:
        The global MetricsCollector instance.
    """
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = MetricsCollector(config)
        return _instance


async def metrics_middleware(request: Any, call_next: Any) -> Any:
    """FastAPI middleware that collects HTTP metrics.

    Records request duration, status codes, and active request count.

    Usage:
        app.middleware("http")(metrics_middleware)

    Args:
        request: FastAPI Request object.
        call_next: Next middleware/endpoint callable.

    Returns:
        Response from downstream.
    """
    collector = get_metrics_collector()
    collector.inc_active_requests()

    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time

        collector.record_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration=duration,
        )
        return response
    except Exception:
        duration = time.time() - start_time
        collector.record_request(
            method=request.method,
            path=request.url.path,
            status=500,
            duration=duration,
        )
        raise
    finally:
        collector.dec_active_requests()
