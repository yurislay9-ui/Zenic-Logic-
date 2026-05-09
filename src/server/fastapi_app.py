"""
TITAN OMNISCALE X v16 - FastAPI Application

Full SaaS-ready FastAPI server with:
- OpenAI-compatible endpoints (chat/completions, models)
- Auth middleware (JWT + API key) via AuthService
- Tenant-aware rate limiting
- CORS support
- Health/readiness/metrics endpoints
- All generation endpoints (app, automation, niche, schema, think, reason)
- Retry patterns on all critical operations
- Circuit breaker protection on auth and orchestrator calls
- Phase 4: Distributed orchestration endpoints (cluster, tasks, saga)
- Phase 5: Observability (OpenTelemetry, Prometheus, audit) & Security (CSP, HSTS, auth rate limit, token blacklist)

Coexists with the legacy stdlib server for backward compatibility.
Start with: python main_headless.py --server fastapi
"""

import json
import time
import logging
import uuid
import threading
import asyncio
from typing import Any, Dict, List, Optional

from src.core.shared._version import TITAN_VERSION, TITAN_VERSION_STR, TITAN_FULL_NAME
from src.core.patterns.resilience.retry import RetryConfig, with_retry
from src.core.patterns.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from src.server.auth_middleware import AuthContext, resolve_auth, require_auth
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
    build_artifact_response,
)
from src.core.auth_parts._tenant_mixin import PLAN_DEFINITIONS
from src.core.tenant._context import (
    TenantContext, set_current_tenant, clear_current_tenant, get_current_tenant,
)
from src.core.tenant._feature_gate import require_feature, FeatureNotAvailableError
import os

# Phase 5: Observability & Security
try:
    from src.core.observability.tracing import (
        TracingConfig, init_tracing, trace_span, get_current_trace_id,
    )
    _TRACING_AVAILABLE = True
except ImportError:
    _TRACING_AVAILABLE = False

try:
    from src.core.observability.metrics import (
        MetricsCollector, MetricsConfig, get_metrics_collector, metrics_middleware,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False

try:
    from src.core.observability.audit import (
        AuditLogger, AuditEvent, AuditEventType, AuditSeverity, get_audit_logger,
    )
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from src.core.observability.health import (
        HealthAggregator, HealthStatus, HealthCheckResult, get_health_aggregator,
        check_orchestrator, check_auth_db, check_resources, check_disk_space,
        check_coordination_backend,
    )
    _HEALTH_AVAILABLE = True
except ImportError:
    _HEALTH_AVAILABLE = False

try:
    from src.server.security_middleware import (
        SecurityConfig, InputSanitizer, create_security_middleware, TokenBlacklist,
    )
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False

# Open Design Integration
try:
    from src.core.open_design import (
        OpenDesignDetector, OpenDesignConfig, get_open_design_config,
        SSEStreamer, create_sse_response,
    )
    _OPEN_DESIGN_AVAILABLE = True
except ImportError:
    _OPEN_DESIGN_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Retry/Circuit Breaker configs ─────────────────────────
_ORCH_RETRY = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    backoff_strategy="exponential",
    jitter=True,
    retryable_exceptions=(Exception,),
)

_orch_breaker = CircuitBreaker(
    name="orchestrator",
    failure_threshold=10,
    recovery_timeout=60.0,
)

# ── FastAPI app (lazy creation) ───────────────────────────
_app = None


async def _basic_sse_generator(body: Dict[str, Any], result: Dict[str, Any]):
    """Async generator for basic SSE streaming of orchestrator results.

    Follows OpenAI streaming spec: each chunk is a chat.completion.chunk object.
    Used when Cline sends stream=true but is NOT an Open Design request.
    """
    request_id = f"titan-{uuid.uuid4().hex[:8]}"
    created = int(time.time())
    model = body.get("model", "titan-omniscale-x")

    # Build full content using the same logic as build_normal_response
    user_msg = ""
    messages = body.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            raw = msg.get("content", "")
            if isinstance(raw, list):
                user_msg = " ".join(
                    p.get("text", "") if isinstance(p, dict) and p.get("type") == "text"
                    else (p if isinstance(p, str) else "")
                    for p in raw
                )
            else:
                user_msg = str(raw)
            break

    response = build_normal_response(body, result, user_msg)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    if not content:
        content = f"[No output generated - status: {result.get('status', 'UNKNOWN')}]"

    try:
        # Stream content in chunks
        chunk_size = 8
        for i in range(0, len(content), chunk_size):
            chunk_text = content[i:i + chunk_size]
            sse_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": chunk_text},
                    "finish_reason": None,
                }],
            }
            yield f"data: {json.dumps(sse_chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)  # Yield control to event loop

        # Final chunk with finish_reason="stop"
        final_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": "stop",
            }],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("SSE generator crashed: %s", e, exc_info=True)
        try:
            error_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n[Stream Error: {str(e)[:100]}]"},
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            yield "data: [DONE]\n\n"


def create_app(
    orchestrator: Any,
    auth_service: Any = None,
    rate_limiter: Any = None,
    governor: Any = None,
    platform_tag: str = "",
) -> Any:
    """Create and configure the FastAPI application.

    Args:
        orchestrator: DAGOrchestrator or TitanOrchestrator instance.
        auth_service: AuthService instance (optional, auth disabled if None).
        rate_limiter: TenantRateLimiter or RateLimiter instance.
        governor: ResourceGovernor instance (optional).
        platform_tag: Platform identifier (e.g. 'termux-proot').

    Returns:
        FastAPI application instance.
    """
    try:
        from fastapi import FastAPI, Request, Response, HTTPException, Depends
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for the SaaS server. "
            "Install with: pip install fastapi uvicorn"
        )

    start_time = time.time()

    app = FastAPI(
        title=f"{TITAN_FULL_NAME}",
        description="Local Surgical AI Engine — OpenAI-Compatible API",
        version=TITAN_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Phase 5: Configurable CORS per environment ───────
    cors_origins = os.getenv("TITAN_CORS_ORIGINS", "*")
    cors_origins_list = [o.strip() for o in cors_origins.split(",") if o.strip()] if cors_origins != "*" else ["*"]
    cors_credentials_env = os.getenv("TITAN_CORS_CREDENTIALS", "true").lower() == "true"

    # Merge Open Design origins BEFORE adding middleware (FastAPI captures values at registration time)
    if _OPEN_DESIGN_AVAILABLE:
        od_config = get_open_design_config()
        if od_config.open_design_origins and cors_origins_list != ["*"]:
            for origin in od_config.open_design_origins:
                if origin not in cors_origins_list:
                    cors_origins_list.append(origin)

    # CORS spec: credentials=true with origin=* is invalid — force false for wildcard
    cors_credentials = cors_credentials_env if cors_origins_list != ["*"] else False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_list,
        allow_credentials=cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS: origins=%s, credentials=%s", cors_origins_list, cors_credentials)

    # ── Phase 5: Security middleware (headers, auth rate limit, input sanitization) ─
    if _SECURITY_AVAILABLE:
        security_config = SecurityConfig.from_env()
        app.middleware("http")(create_security_middleware(security_config))
        app.state.security_config = security_config
        app.state.token_blacklist = TokenBlacklist(security_config.token_blacklist_db)
        logger.info("Security: middleware enabled (CSP=%s, HSTS=%s, auth_rate_limit=%dRPM)",
                    security_config.enable_csp, security_config.enable_hsts,
                    security_config.auth_rate_limit_rpm)
    else:
        app.state.security_config = None
        app.state.token_blacklist = None

    # ── Phase 5: Metrics middleware ────────────────────────
    if _METRICS_AVAILABLE:
        _metrics = get_metrics_collector(MetricsConfig.from_env())
        app.middleware("http")(metrics_middleware)
        app.state.metrics_collector = _metrics
        logger.info("Metrics: Prometheus collector initialized (prometheus_client=%s)",
                    _metrics.is_prometheus_available)
    else:
        app.state.metrics_collector = None

    # ── Phase 5: Initialize tracing ────────────────────────
    if _TRACING_AVAILABLE:
        tracing_initialized = init_tracing(TracingConfig.from_env())
        logger.info("Tracing: OpenTelemetry=%s", tracing_initialized)

    # ── Phase 5: Initialize audit logger ───────────────────
    if _AUDIT_AVAILABLE:
        _audit = get_audit_logger()
        app.state.audit_logger = _audit
        logger.info("Audit: logger initialized (DB=%s)", _audit._initialized)
    else:
        app.state.audit_logger = None

    # ── Phase 5: Initialize health aggregator ──────────────
    if _HEALTH_AVAILABLE:
        _health_agg = get_health_aggregator()
        _health_agg.register_liveness_check(
            "orchestrator", lambda: check_orchestrator(orchestrator),
        )
        _health_agg.register_liveness_check(
            "resources", lambda: check_resources(governor),
        )
        _health_agg.register_readiness_check(
            "orchestrator", lambda: check_orchestrator(orchestrator),
        )
        _health_agg.register_readiness_check(
            "auth_db", lambda: check_auth_db(auth_service),
        )
        _health_agg.register_readiness_check(
            "resources", lambda: check_resources(governor),
        )
        _health_agg.register_readiness_check(
            "disk", lambda: check_disk_space("."),
        )
        app.state.health_aggregator = _health_agg
        logger.info("Health: aggregator initialized (liveness=%d, readiness=%d)",
                    len(_health_agg._liveness_checks), len(_health_agg._readiness_checks))
    else:
        app.state.health_aggregator = None

    # ── Open Design Integration ──────────────────────────
    if _OPEN_DESIGN_AVAILABLE:
        _od_config = get_open_design_config()
        app.state.open_design_config = _od_config
        logger.info(
            "OpenDesign: integration enabled (SSE=%s, visual_bypass=%s, origins=%s)",
            _od_config.sse_enabled, _od_config.visual_bypass_enabled,
            _od_config.open_design_origins,
        )
    else:
        app.state.open_design_config = None

    # ── Phase 4: Initialize distributed coordination backend ──
    try:
        from src.core.distributed import CoordinationBackend, BackendConfig, DistributedTaskQueue
        _backend_config = BackendConfig()
        # Use PostgreSQL in production if configured
        # NOTE: Do NOT re-import 'os' here — it shadows the module-level
        # import (line 44) and causes UnboundLocalError for earlier os.getenv() calls.
        db_url = os.getenv("DATABASE_URL", "")
        if db_url and ("postgresql" in db_url or "postgres" in db_url):
            from src.core.distributed.backend import BackendType
            _backend_config = BackendConfig(backend_type=BackendType.POSTGRESQL, connection_string=db_url)
        _coord_backend = CoordinationBackend.create(_backend_config)
        app.state.coordination_backend = _coord_backend
        app.state.task_queue = DistributedTaskQueue(backend=_coord_backend)
        logger.info("Distributed: coordination backend initialized (type=%s)", type(_coord_backend).__name__)
    except Exception as e:
        logger.warning("Distributed: backend initialization failed (%s) — Phase 4 endpoints disabled", e)
        app.state.coordination_backend = None
        app.state.task_queue = None

    # ── Store references in app state ──────────────────────
    app.state.orchestrator = orchestrator
    app.state.auth_service = auth_service
    app.state.rate_limiter = rate_limiter
    app.state.governor = governor
    app.state.platform_tag = platform_tag
    app.state.start_time = start_time
    app.state.request_count = 0
    app.state._request_count_lock = threading.Lock()

    # ── Auth dependency ────────────────────────────────────
    async def get_auth_context(request: Request) -> Optional[AuthContext]:
        """FastAPI dependency that resolves auth from request headers.

        Returns None if no auth service configured (auth disabled).
        Raises HTTPException(401/403) if auth fails.
        """
        if auth_service is None:
            return None  # Auth not configured — all requests anonymous

        authorization = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")

        ctx = resolve_auth(auth_service, authorization or None, api_key or None)
        if ctx is None and auth_service is not None:
            # Auth service exists but credentials invalid → 401
            # However, some endpoints are public (health, models), so
            # we return None and let each endpoint decide
            pass
        return ctx

    async def require_auth_dep(request: Request) -> AuthContext:
        """FastAPI dependency that requires valid authentication."""
        if auth_service is None:
            raise HTTPException(status_code=401, detail="Authentication not configured")
        authorization = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")
        result = require_auth(auth_service, authorization or None, api_key or None)
        if "error" in result:
            raise HTTPException(status_code=result.get("status", 401), detail=result["error"])
        return result["auth"]

    # ── Helper: build TenantContext from AuthContext ─────
    def _build_tenant_context(auth_ctx: Optional[AuthContext]) -> TenantContext:
        """Build a TenantContext from an AuthContext, resolving plan/quotas/features."""
        if auth_ctx is None or not auth_ctx.tenant_id:
            return TenantContext.anonymous()

        # Resolve tenant plan and quotas
        tenant = auth_service.get_tenant(auth_ctx.tenant_id) if auth_service else None
        plan = tenant.get("plan", "free") if tenant else "free"
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        features = quotas.get("features", [])

        return TenantContext.from_auth_context(
            auth_ctx=auth_ctx,
            plan=plan,
            quotas=quotas,
            features=features if isinstance(features, list) else [],
        )

    # ── Middleware: rate limiting + tenant context + governor + usage tracking ─
    @app.middleware("http")
    async def rate_limit_and_governor(request: Request, call_next):
        """Per-request middleware: tenant context injection, rate limiting, governor check, usage tracking.

        Phase 2: This middleware is the CRITICAL bridge between HTTP auth and
        the tenant-aware pipeline. It:
        1. Resolves auth context (JWT/API key)
        2. Builds TenantContext from AuthContext + plan/quotas/features
        3. Sets TenantContext in thread-local storage (accessible by SmartMemory, Ledger, Cache)
        4. Checks daily quota and storage quota
        5. Applies plan-based rate limits
        6. Clears TenantContext in finally block to prevent leaks
        """
        # Skip for docs/health/openapi
        skip_paths = {"/docs", "/redoc", "/openapi.json", "/health", "/ready", "/metrics"}
        if request.url.path in skip_paths:
            return await call_next(request)

        # Resolve auth for rate limiting
        auth_ctx: Optional[AuthContext] = None
        if auth_service is not None:
            authorization = request.headers.get("Authorization", "")
            api_key = request.headers.get("X-API-Key", "")
            auth_ctx = resolve_auth(auth_service, authorization or None, api_key or None)

        # ── Phase 2: Set TenantContext in thread-local ───────
        tenant_ctx = _build_tenant_context(auth_ctx)
        set_current_tenant(tenant_ctx)

        # Also store in request state for endpoint access
        request.state.tenant_ctx = tenant_ctx
        request.state.auth_ctx = auth_ctx

        try:
            # Rate limiting
            if rate_limiter is not None:
                client_ip = request.client.host if request.client else "0.0.0.0"
                user_id = auth_ctx.user_id if auth_ctx else None
                tenant_id = auth_ctx.tenant_id if auth_ctx else None

                # Apply plan-based user limits
                if auth_ctx and tenant_id:
                    tenant = auth_service.get_tenant(tenant_id) if auth_service else None
                    if tenant:
                        plan = tenant.get("plan", "free")
                        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
                        # Update rate limiter with plan limits
                        if hasattr(rate_limiter, "set_user_limits"):
                            rate_limiter.set_user_limits(
                                user_id,
                                rpm=quotas.get("max_requests_per_minute", 10),
                                burst=min(quotas.get("max_requests_per_minute", 10), 20),
                            )
                        if hasattr(rate_limiter, "set_tenant_limits"):
                            rate_limiter.set_tenant_limits(
                                tenant_id,
                                rpm=quotas.get("max_requests_per_minute", 10),
                            )

                        # Check daily quota
                        if auth_service and hasattr(auth_service, "check_tenant_quota"):
                            quota_check = auth_service.check_tenant_quota(tenant_id)
                            if not quota_check.get("allowed", True):
                                return JSONResponse(
                                    status_code=429,
                                    content={
                                        "error": {
                                            "message": quota_check.get("reason", "Quota exceeded"),
                                            "type": "quota_exceeded",
                                            "plan": plan,
                                        }
                                    },
                                )

                        # Check storage quota (Phase 2)
                        if auth_service and hasattr(auth_service, "check_storage_quota"):
                            storage_check = auth_service.check_storage_quota(tenant_id)
                            if not storage_check.get("allowed", True):
                                return JSONResponse(
                                    status_code=429,
                                    content={
                                        "error": {
                                            "message": f"Storage quota exceeded ({storage_check.get('used_mb', 0):.1f}MB / {storage_check.get('max_mb', 0)}MB)",
                                            "type": "storage_quota_exceeded",
                                            "plan": plan,
                                        }
                                    },
                                )

                if hasattr(rate_limiter, "acquire"):
                    allowed = rate_limiter.acquire(
                        client_ip,
                        user_id=user_id,
                        tenant_id=tenant_id,
                    )
                    if not allowed:
                        return JSONResponse(
                            status_code=429,
                            content={"error": {"message": "Rate limit exceeded", "type": "rate_limit_exceeded"}},
                        )

            # Governor check (headless mode)
            if governor is not None:
                governor.pre_request()
                if governor.is_ram_critical():
                    if rate_limiter and hasattr(rate_limiter, "release"):
                        rate_limiter.release()
                    return JSONResponse(
                        status_code=503,
                        content=build_overloaded_response(),
                    )

            # Process request and measure time
            request_start = time.time()
            try:
                with app.state._request_count_lock:
                    app.state.request_count += 1
                response = await call_next(request)
            finally:
                # Record usage with compute_seconds and tokens
                processing_time_ms = int((time.time() - request_start) * 1000)
                if auth_ctx and auth_ctx.tenant_id and auth_service and hasattr(auth_service, "record_usage"):
                    try:
                        compute_seconds = processing_time_ms / 1000.0
                        # Estimate tokens from response (if available)
                        tokens = 0
                        auth_service.record_usage(
                            auth_ctx.tenant_id,
                            requests=1,
                            tokens=tokens,
                            compute_seconds=compute_seconds,
                        )
                    except Exception as e:
                        logger.debug("Usage recording failed: %s", e)

                # Log request with tenant_id
                try:
                    from src.core.shared.db_initializer import get_connection
                    log_conn = get_connection("request_log.sqlite")
                    log_conn.execute(
                        "INSERT INTO requests (request_id, model, operation, route, status, processing_time_ms, tenant_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            "titan-omniscale-x",
                            request.method,
                            request.url.path,
                            "completed",
                            processing_time_ms,
                            tenant_ctx.effective_tenant_id,
                        ),
                    )
                    log_conn.commit()
                except Exception as e:
                    logger.debug("Request logging failed: %s", e)

                if governor is not None:
                    governor.post_request()
                if rate_limiter is not None and hasattr(rate_limiter, "release"):
                    rate_limiter.release()

            return response
        finally:
            # ── Phase 2: ALWAYS clear tenant context ───────
            clear_current_tenant()

    # ════════════════════════════════════════════════════════
    #  PUBLIC ENDPOINTS (no auth required)
    # ════════════════════════════════════════════════════════

    @app.get("/")
    async def root():
        """Server info and available endpoints."""
        from src.core.shared.contracts import HAS_Z3
        solver = "Z3" if HAS_Z3 else "AC-3"
        version_suffix = f"-{platform_tag}" if platform_tag else ""
        return {
            "status": "active",
            "model": "titan-omniscale-x",
            "version": f"{TITAN_VERSION}{version_suffix}",
            "server": "FastAPI",
            "auth_enabled": auth_service is not None,
            "endpoints": [
                "/v1/chat/completions", "/v1/models", "/health", "/ready", "/metrics",
                "/v1/generate/app", "/v1/generate/automation", "/v1/generate/niche",
                "/v1/design/schema", "/v1/think", "/v1/reason",
                "/v1/chain/validate", "/v1/chain/execute",
                "/v1/auth/register", "/v1/auth/login", "/v1/auth/refresh",
                "/v1/auth/me", "/v1/auth/api-keys",
                "/v1/tenants", "/v1/tenants/{tenant_id}",
                "/v1/cluster/nodes", "/v1/cluster/status",
                "/v1/tasks/enqueue", "/v1/tasks/{task_id}/status",
                "/v1/saga/start", "/v1/saga/{saga_id}",
                "/docs",
            ],
            "solver": solver,
            "pipeline_levels": 8,
        }

    @app.get("/health")
    async def health():
        """Liveness health check (Phase 5: enhanced with HealthAggregator)."""
        health_agg = getattr(app.state, "health_aggregator", None)
        if health_agg is not None and _HEALTH_AVAILABLE:
            result = await health_agg.check_liveness()
            status_code = 200 if result.get("status") != "unhealthy" else 503
            return JSONResponse(content=result, status_code=status_code)

        # Fallback: basic health check
        from src.core.shared.contracts import HAS_Z3
        health_data: Dict[str, Any] = {
            "status": "healthy",
            "solver": "Z3" if HAS_Z3 else "AC-3",
            "has_z3": HAS_Z3,
            "mode": "fastapi",
            "uptime_s": int(time.time() - start_time),
        }
        if governor:
            health_data["resources"] = governor.get_status()
            if governor.is_ram_critical():
                health_data["status"] = "degraded"
        return health_data

    @app.get("/ready")
    async def readiness():
        """Readiness probe (Phase 5: enhanced with HealthAggregator)."""
        health_agg = getattr(app.state, "health_aggregator", None)
        if health_agg is not None and _HEALTH_AVAILABLE:
            result = await health_agg.check_readiness()
            status_code = 200 if result.get("ready") else 503
            return JSONResponse(content=result, status_code=status_code)

        # Fallback: basic readiness check
        checks: Dict[str, bool] = {}
        try:
            checks["orchestrator"] = orchestrator is not None
        except Exception:
            checks["orchestrator"] = False
        if auth_service:
            try:
                stats = auth_service.get_stats()
                checks["auth_db"] = True
            except Exception:
                checks["auth_db"] = False
        else:
            checks["auth_db"] = None
        ready = all(v is not False for v in checks.values())
        return {"ready": ready, "checks": checks}

    @app.get("/metrics")
    async def metrics():
        """Prometheus-compatible metrics (Phase 5: enhanced with MetricsCollector)."""
        mc = getattr(app.state, "metrics_collector", None)
        if mc is not None and _METRICS_AVAILABLE:
            if governor:
                try:
                    res = governor.get_status()
                    mc.update_resources(res.get("ram_usage_mb", 0), res.get("cpu_usage_pct", 0))
                except Exception:
                    pass
            mc.update_uptime(time.time() - start_time)
            content = mc.generate_text_metrics()
            return Response(content=content, media_type="text/plain")

        # Fallback: basic custom metrics
        uptime = int(time.time() - start_time)
        lines = [
            "# HELP titan_uptime_seconds Server uptime in seconds",
            "# TYPE titan_uptime_seconds gauge",
            f"titan_uptime_seconds {uptime}",
            "# HELP titan_requests_total Total requests served",
            "# TYPE titan_requests_total counter",
            f"titan_requests_total {app.state.request_count}",
        ]
        if rate_limiter:
            stats = rate_limiter.get_stats()
            lines.extend([
                "# HELP titan_rate_limit_accepted Total accepted requests",
                "# TYPE titan_rate_limit_accepted counter",
                f"titan_rate_limit_accepted {stats.get('total_accepted', 0)}",
                "# HELP titan_rate_limit_rejected Total rejected requests",
                "# TYPE titan_rate_limit_rejected counter",
                f"titan_rate_limit_rejected {stats.get('total_rejected', 0)}",
            ])
        if governor:
            res = governor.get_status()
            lines.extend([
                "# HELP titan_ram_usage_mb Current RAM usage in MB",
                "# TYPE titan_ram_usage_mb gauge",
                f"titan_ram_usage_mb {res.get('ram_usage_mb', 0):.1f}",
                "# HELP titan_cpu_usage_pct Current CPU usage percentage",
                "# TYPE titan_cpu_usage_pct gauge",
                f"titan_cpu_usage_pct {res.get('cpu_usage_pct', 0):.1f}",
            ])
        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    @app.get("/v1/models")
    async def list_models():
        """OpenAI-compatible models endpoint."""
        return {
            "object": "list",
            "data": [{
                "id": "titan-omniscale-x",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "titan-local",
            }],
        }

    # ════════════════════════════════════════════════════════
    #  AUTH ENDPOINTS (public registration/login)
    # ════════════════════════════════════════════════════════

    if auth_service is not None:
        @app.post("/v1/auth/register")
        async def auth_register(request: Request):
            """Register a new user."""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            # Force role='user' on public registration — admins change roles via admin API
            result = auth_service.register_user(
                username=body.get("username", ""),
                email=body.get("email", ""),
                password=body.get("password", ""),
                role="user",
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        @app.post("/v1/auth/login")
        async def auth_login(request: Request):
            """Authenticate user and return tokens."""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            result = auth_service.login_user(
                username=body.get("username", ""),
                password=body.get("password", ""),
            )
            if "error" in result:
                raise HTTPException(status_code=401, detail=result["error"])
            return result

        @app.post("/v1/auth/refresh")
        async def auth_refresh(request: Request):
            """Refresh access token."""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            result = auth_service.refresh_access_token(body.get("refresh_token", ""))
            if "error" in result:
                raise HTTPException(status_code=401, detail=result["error"])
            return result

        @app.get("/v1/auth/me")
        async def auth_me(auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Get current user info."""
            user = auth_service.get_user(auth_ctx.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return user

        @app.post("/v1/auth/api-keys")
        async def create_api_key(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Create an API key for the current user."""
            try:
                body = await request.json()
            except Exception:
                body = {}
            result = auth_service.create_api_key(
                user_id=auth_ctx.user_id,
                name=body.get("name", "default"),
                permissions=body.get("permissions"),
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        @app.get("/v1/auth/api-keys")
        async def list_api_keys(auth_ctx: AuthContext = Depends(require_auth_dep)):
            """List API keys for the current user."""
            return auth_service.list_api_keys(auth_ctx.user_id)

        # ── Tenant endpoints (admin/manager only) ──────────
        @app.get("/v1/tenants")
        async def list_tenants(auth_ctx: AuthContext = Depends(require_auth_dep)):
            """List all tenants (admin/manager)."""
            if not auth_ctx.has_role("manager"):
                raise HTTPException(status_code=403, detail="Manager or admin required")
            return auth_service.list_tenants()

        @app.post("/v1/tenants")
        async def create_tenant(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Create a new tenant (admin only)."""
            if not auth_ctx.has_role("admin"):
                raise HTTPException(status_code=403, detail="Admin required")
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            result = auth_service.create_tenant(
                name=body.get("name", ""),
                plan=body.get("plan", "free"),
                config=body.get("config"),
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        @app.get("/v1/tenants/{tenant_id}")
        async def get_tenant(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Get tenant details."""
            if not auth_ctx.has_role("manager"):
                raise HTTPException(status_code=403, detail="Manager or admin required")
            tenant = auth_service.get_tenant(tenant_id)
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            return tenant

        @app.post("/v1/tenants/{tenant_id}/assign/{user_id}")
        async def assign_user(tenant_id: str, user_id: int, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Assign user to tenant (admin only)."""
            if not auth_ctx.has_role("admin"):
                raise HTTPException(status_code=403, detail="Admin required")
            result = auth_service.assign_user_to_tenant(user_id, tenant_id)
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        @app.patch("/v1/tenants/{tenant_id}")
        async def update_tenant(tenant_id: str, request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Update tenant (plan, name, config). Admin only."""
            if not auth_ctx.has_role("admin"):
                raise HTTPException(status_code=403, detail="Admin required")
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON")
            result = auth_service.update_tenant(
                tenant_id,
                name=body.get("name"),
                plan=body.get("plan"),
                config=body.get("config"),
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        @app.delete("/v1/tenants/{tenant_id}")
        async def delete_tenant(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Deprovision tenant: hard-delete tenant and ALL associated data (GDPR). Admin only."""
            if not auth_ctx.has_role("admin"):
                raise HTTPException(status_code=403, detail="Admin required")
            if not hasattr(auth_service, "deprovision_tenant"):
                raise HTTPException(status_code=501, detail="Deprovision not available")
            result = auth_service.deprovision_tenant(tenant_id)
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            return result

        @app.get("/v1/tenants/{tenant_id}/usage")
        async def get_tenant_usage(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Get tenant usage stats (manager/admin or member of the tenant)."""
            if not auth_ctx.has_role("manager"):
                raise HTTPException(status_code=403, detail="Manager or admin required")
            usage = auth_service.get_tenant_usage(tenant_id)
            quota = auth_service.check_tenant_quota(tenant_id) if hasattr(auth_service, "check_tenant_quota") else None
            storage = auth_service.check_storage_quota(tenant_id) if hasattr(auth_service, "check_storage_quota") else None
            return {
                "tenant_id": tenant_id,
                "usage": usage,
                "quota": quota,
                "storage": storage,
            }

        @app.get("/v1/tenants/{tenant_id}/features")
        async def get_tenant_features_api(tenant_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
            """Get available features for a tenant's plan."""
            if not auth_ctx.has_role("manager"):
                raise HTTPException(status_code=403, detail="Manager or admin required")
            features = auth_service.get_tenant_features(tenant_id) if hasattr(auth_service, "get_tenant_features") else []
            return {"tenant_id": tenant_id, "features": features}

    # ════════════════════════════════════════════════════════
    #  AI ENDPOINTS (auth optional, rate-limited)
    # ════════════════════════════════════════════════════════

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint with SSE streaming for Open Design."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                raw_content = msg.get("content", "")
                # Handle OpenAI multimodal content (list of parts or string)
                if isinstance(raw_content, list):
                    parts = []
                    for part in raw_content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and part.get("type") == "text":
                            parts.append(part.get("text", ""))
                    user_msg = " ".join(parts)
                elif isinstance(raw_content, str):
                    user_msg = raw_content
                else:
                    user_msg = str(raw_content) if raw_content else ""
                break

        if not user_msg:
            raise HTTPException(status_code=400, detail="No user message found")

        # ── Open Design Detection ──
        detection_result = None
        if _OPEN_DESIGN_AVAILABLE:
            try:
                headers_dict = {k.lower(): v for k, v in request.headers.items()}
                detection_result = OpenDesignDetector.detect(
                    messages=messages, headers=headers_dict, body=body,
                )
                if detection_result.get("is_open_design") or detection_result.get("is_visual_request"):
                    logger.info(
                        "OpenDesign: detected request (bypass=%s, DS=%s, signals=%s)",
                        detection_result.get("bypass_solver"),
                        detection_result.get("has_design_system"),
                        detection_result.get("detection_signals"),
                    )
            except Exception as e:
                logger.warning("OpenDesign detection failed (skipping): %s", e)
                detection_result = None

        # Execute with retry + circuit breaker (non-blocking via run_in_executor)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,  # default ThreadPoolExecutor
                _orch_breaker.call,
                with_retry,
                _run_orchestrator,
                _ORCH_RETRY,
                orchestrator,
                user_msg,
            )
        except CircuitOpenError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {e}",
            )
        except Exception as e:
            logger.error("Orchestrator error: %s", e, exc_info=True)
            return JSONResponse(
                status_code=500,
                content=build_error_response(str(e)),
            )

        # ── Defensive: ensure result is never None/empty ──
        # If the orchestrator returns None, Cline would receive
        # an empty HTTP body → parse error → crash
        if result is None:
            logger.error("chat_completions: orchestrator returned None — building error response")
            result = {"status": "ERROR", "code": "", "error": "Orchestrator returned empty result"}

        # ── SSE Streaming ──
        # OpenAI spec: when stream=true, client expects SSE format.
        # For Open Design requests, use full SSEStreamer with fractal phases.
        # For general Cline requests with stream=true, use basic SSE streaming.
        if body.get("stream", False):
            if (_OPEN_DESIGN_AVAILABLE
                    and detection_result
                    and (detection_result.get("is_open_design")
                         or detection_result.get("is_visual_request"))):
                # Open Design: full SSE with fractal phases and artifact events
                try:
                    streamer = SSEStreamer()
                    return create_sse_response(streamer, result, body, detection_result)
                except Exception as e:
                    logger.warning("OpenDesign: SSE streaming failed, falling back to basic SSE: %s", e)
            # General Cline or Open Design fallback: basic SSE streaming
            try:
                from fastapi.responses import StreamingResponse
                return StreamingResponse(
                    _basic_sse_generator(body, result),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            except Exception as e:
                logger.warning("SSE streaming failed, falling back to JSON: %s", e)

        # Standard JSON response
        if result.get("partial_reasoning"):
            return build_partial_reasoning_response(body, result, user_msg)

        # Open Design: Use artifact-wrapped response for visual requests (non-streaming)
        if (detection_result
                and (detection_result.get("is_open_design")
                     or detection_result.get("is_visual_request"))):
            return build_artifact_response(body, result, user_msg, governor=governor)

        # Detect fallback-only responses (all LLM calls timed out or failed).
        # This happens when the model is too slow on ARM or hasn't warmed up yet.
        # Return a clear error instead of garbage fallback code.
        mini_ai_stats = result.get("mini_ai_stats", {})
        fallback_rate = mini_ai_stats.get("fallback_rate", 0.0)
        total_calls = mini_ai_stats.get("total_calls", 0)
        if total_calls > 0 and fallback_rate >= 1.0:
            # 100% of LLM calls used fallback — model is not responding
            logger.warning(
                "chat_completions: 100%% fallback rate (%d calls) — model not responding",
                total_calls,
            )
            return JSONResponse(
                status_code=503,
                content=build_error_response(
                    "Model inference timed out — the AI model is not responding in time. "
                    "This is common on first request after startup (warm-up). "
                    "Please try again — subsequent requests will be faster."
                ),
            )

        return build_normal_response(body, result, user_msg, governor=governor)

    @app.post("/v1/generate/app")
    async def generate_app(request: Request):
        """Generate a complete application from description. Requires 'app_generation' feature."""
        # Feature gate: app_generation requires Pro plan
        try:
            require_feature("app_generation")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.generate_app(
                description, body.get("project_name", ""), body.get("output_dir", "")
            )
            return result
        except Exception as e:
            logger.error("App generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/generate/automation")
    async def generate_automation(request: Request):
        """Generate an automation from description. Requires 'automation_generation' feature."""
        # Feature gate: automation_generation requires Pro plan
        try:
            require_feature("automation_generation")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.generate_automation(
                description, body.get("output_dir", "")
            )
            return result
        except Exception as e:
            logger.error("Automation generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/generate/niche")
    async def generate_niche(request: Request):
        """Generate an app from a predefined niche template."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        niche_name = body.get("niche", "")
        if not niche_name:
            raise HTTPException(status_code=400, detail="Missing 'niche' field")
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            plan = engine.get_niche_plan(niche_name)
            if not plan:
                raise HTTPException(status_code=404, detail=f"Niche '{niche_name}' not found")
            files = engine.render_niche(niche_name)
            return {
                "niche": niche_name, "files_generated": len(files),
                "files": list(files.keys()), "entities": len(plan.entities),
                "blocks": plan.blocks,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Niche generation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/design/schema")
    async def design_schema(request: Request):
        """Design a database schema from description. Requires 'schema_design' feature."""
        # Feature gate: schema_design requires Pro plan
        try:
            require_feature("schema_design")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.design_schema(description)
            return result
        except Exception as e:
            logger.error("Schema design error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/think")
    async def think(request: Request):
        """Thinking engine endpoint. Requires 'thinking_engine' feature."""
        # Feature gate: thinking_engine requires Pro plan
        try:
            require_feature("thinking_engine")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        query = body.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' field")
        try:
            result = await orchestrator.think(query, body.get("context", ""))
            return result
        except Exception as e:
            logger.error("Thinking error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/reason")
    async def reason(request: Request):
        """Advanced reasoning endpoint (Phase 8). Requires 'reasoning_engine' feature."""
        # Feature gate: reasoning_engine requires Pro plan
        try:
            require_feature("reasoning_engine")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        query = body.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="Missing 'query' field")
        try:
            result = await orchestrator.reason(query, body.get("mode", "auto"), body.get("context", ""))
            return result
        except Exception as e:
            logger.error("Reasoning error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/chain/validate")
    async def chain_validate(request: Request):
        """Validate a logic chain. Requires 'logic_chains' feature."""
        # Feature gate: logic_chains requires Pro plan
        try:
            require_feature("logic_chains")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.validate_logic_chain(description)
            return result
        except Exception as e:
            logger.error("Chain validation error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/chain/execute")
    async def chain_execute(request: Request):
        """Execute a logic chain with rollback and recovery. Requires 'logic_chains' feature."""
        # Feature gate: logic_chains requires Pro plan
        try:
            require_feature("logic_chains")
        except FeatureNotAvailableError as e:
            raise HTTPException(status_code=403, detail=str(e))

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        description = body.get("description", "")
        if not description:
            raise HTTPException(status_code=400, detail="Missing 'description' field")
        try:
            result = await orchestrator.execute_logic_chain(
                description, body.get("data", {}), body.get("recovery", "skip")
            )
            return result
        except Exception as e:
            logger.error("Chain execution error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── Legacy GET endpoints ───────────────────────────────
    @app.get("/v1/projects")
    async def list_projects(status: str = ""):
        try:
            projects = await orchestrator.list_projects(status)
            return {"projects": projects, "total": len(projects)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/automations")
    async def list_automations():
        try:
            automations = await orchestrator.list_automations()
            return {"automations": automations, "total": len(automations)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/niches")
    async def list_niches(domain: str = ""):
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            niches = engine.list_niches(domain)
            result = []
            for name in niches:
                plan = engine.get_niche_plan(name)
                if plan:
                    result.append({"name": name, "entities": len(plan.entities), "blocks": plan.blocks})
            return {"niches": result, "total": len(result), "domain": domain or "all"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/niches/domains")
    async def list_domains():
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            domains = engine.list_domains()
            result = [{"domain": d, "niche_count": len(engine.list_niches(d)), "niches": engine.list_niches(d)} for d in domains]
            return {"domains": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/templates")
    async def list_templates():
        try:
            from src.core.app_generator import AppGenerator
            templates = AppGenerator.list_templates()
            try:
                from src.core.template_engine import TemplateEngine
                templates["niche_templates"] = TemplateEngine().list_niches()
                templates["niche_domains"] = TemplateEngine().list_domains()
            except Exception:
                pass
            return templates
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/system/status")
    async def system_status():
        try:
            return await orchestrator.get_system_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  PHASE 4: DISTRIBUTED ORCHESTRATION ENDPOINTS
    # ════════════════════════════════════════════════════════

    @app.get("/v1/cluster/nodes")
    async def cluster_nodes(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """List active nodes in the distributed cluster."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            from src.core.distributed import ClusterTopology, NodeInfo
            # Use a lightweight backend query for topology
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                return {"nodes": [], "total": 0, "distributed": False}
            topology = ClusterTopology(backend=backend)
            nodes = await topology.list_active_nodes()
            return {
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "hostname": n.hostname,
                        "ip_address": n.ip_address,
                        "capabilities": n.capabilities,
                        "state": n.state.value,
                        "last_heartbeat": n.last_heartbeat,
                    }
                    for n in nodes
                ],
                "total": len(nodes),
                "distributed": True,
            }
        except Exception as e:
            logger.error("Cluster nodes error: %s", e)
            return {"nodes": [], "total": 0, "error": str(e)}

    @app.get("/v1/cluster/status")
    async def cluster_status(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get cluster-wide distributed orchestration status."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                return {
                    "distributed": False,
                    "backend_type": "none",
                    "message": "Coordination backend not configured",
                }
            health = await backend.health_check()
            return {
                "distributed": True,
                "backend_type": type(backend).__name__,
                "health": health,
                "node_id": backend.node_id,
            }
        except Exception as e:
            logger.error("Cluster status error: %s", e)
            return {"distributed": False, "error": str(e)}

    @app.post("/v1/tasks/enqueue")
    async def enqueue_task(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Enqueue a task to the distributed task queue."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        queue_name = body.get("queue_name", "default")
        task_type = body.get("task_type", "generic")
        payload = body.get("payload", {})
        priority = body.get("priority", 5)
        tenant_id = body.get("tenant_id")
        delay_seconds = body.get("delay_seconds")

        try:
            from src.core.distributed import (
                DistributedTaskQueue, TaskMessage, TaskPriority,
            )
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(
                    status_code=503,
                    detail="Distributed task queue not available",
                )
            task_queue = getattr(app.state, "task_queue", None)
            if task_queue is None:
                raise HTTPException(
                    status_code=503,
                    detail="Task queue not initialized",
                )

            delay_until = None
            if delay_seconds and delay_seconds > 0:
                delay_until = time.time() + delay_seconds

            msg = TaskMessage(
                queue_name=queue_name,
                task_type=task_type,
                payload=payload,
                priority=priority,
                delay_until=delay_until,
                tenant_id=tenant_id,
            )
            task_id = await task_queue.enqueue(msg)
            return {"task_id": task_id, "status": "enqueued", "queue": queue_name}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Task enqueue error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/tasks/{task_id}/status")
    async def task_status(task_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get the status of a distributed task."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(status_code=503, detail="Backend not available")
            saga = await backend.get_saga(task_id)
            if saga:
                return {
                    "task_id": task_id,
                    "type": "saga",
                    "status": saga.get("status"),
                    "name": saga.get("name"),
                    "steps": len(saga.get("steps", [])),
                }
            return {"task_id": task_id, "status": "unknown"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Task status error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/saga/start")
    async def start_saga(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Start a new distributed SAGA."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        name = body.get("name", "")
        steps = body.get("steps", [])
        initial_context = body.get("context", {})

        if not name:
            raise HTTPException(status_code=400, detail="Missing 'name' field")
        if not steps:
            raise HTTPException(status_code=400, detail="Missing 'steps' field")

        try:
            from src.core.distributed import (
                DistributedSagaCoordinator, DistributedSagaStep,
            )
            backend = getattr(app.state, "coordination_backend", None)
            task_queue = getattr(app.state, "task_queue", None)
            if backend is None or task_queue is None:
                raise HTTPException(
                    status_code=503,
                    detail="Distributed orchestration not available",
                )

            saga_coordinator = DistributedSagaCoordinator(
                backend=backend,
                task_queue=task_queue,
            )

            saga_steps = [
                DistributedSagaStep(
                    name=step.get("name", f"step-{i}"),
                    action_task_type=step.get("action_task_type", f"saga_step_{step.get('name', i)}"),
                    compensation_task_type=step.get("compensation_task_type"),
                    timeout=step.get("timeout"),
                    priority=step.get("priority", 5),
                )
                for i, step in enumerate(steps)
            ]

            tenant_id = getattr(
                getattr(request.state, "tenant_ctx", None),
                "effective_tenant_id", None,
            )

            saga_id = await saga_coordinator.start_saga(
                name=name,
                steps=saga_steps,
                initial_context=initial_context,
                tenant_id=tenant_id,
            )

            return {
                "saga_id": saga_id,
                "name": name,
                "steps": len(saga_steps),
                "status": "RUNNING",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Saga start error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/saga/{saga_id}")
    async def get_saga_status(saga_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get the status of a distributed SAGA."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(status_code=503, detail="Backend not available")
            saga = await backend.get_saga(saga_id)
            if saga is None:
                raise HTTPException(status_code=404, detail="Saga not found")
            return saga
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Saga status error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # ════════════════════════════════════════════════════════
    #  PHASE 5: OBSERVABILITY & SECURITY ENDPOINTS
    # ════════════════════════════════════════════════════════

    @app.post("/v1/auth/logout")
    async def auth_logout(request: Request):
        """Logout: revoke the current access token (Phase 5)."""
        token_blacklist = getattr(app.state, "token_blacklist", None)
        if token_blacklist is None:
            return {"message": "Logout processed (blacklist not available)"}

        authorization = request.headers.get("Authorization", "")
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            try:
                # Decode without full verification to get JTI
                import base64, json
                parts = token.split(".")
                if len(parts) >= 2:
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    jti = payload.get("jti", payload.get("sub", ""))
                    exp = payload.get("exp")
                    user_id = payload.get("sub")
                    token_blacklist.revoke_token(
                        jti=str(jti),
                        user_id=int(user_id) if user_id and user_id.isdigit() else None,
                        reason="logout",
                        expires_at=exp,
                    )
                    # Audit event
                    audit = getattr(app.state, "audit_logger", None)
                    if audit and _AUDIT_AVAILABLE:
                        audit.log_event(
                            event_type=AuditEventType.AUTH_TOKEN_REVOKED,
                            description=f"Token revoked on logout (jti={str(jti)[:8]})",
                            tenant_id=payload.get("tenant_id", "__anonymous__"),
                            user_id=int(user_id) if user_id and user_id.isdigit() else None,
                            ip_address=request.client.host if request.client else "",
                        )
            except Exception as e:
                logger.debug("Token revocation parsing failed: %s", e)

        return {"message": "Logged out successfully"}

    @app.get("/v1/audit/events")
    async def query_audit_events(
        request: Request,
        tenant_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        auth_ctx: AuthContext = Depends(require_auth_dep),
    ):
        """Query audit events (Phase 5). Requires manager role."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager or admin required")

        audit = getattr(app.state, "audit_logger", None)
        if audit is None or not _AUDIT_AVAILABLE:
            raise HTTPException(status_code=501, detail="Audit logging not available")

        # Non-admin users can only see their own tenant's events
        effective_tenant = tenant_id
        if not auth_ctx.has_role("admin"):
            effective_tenant = auth_ctx.tenant_id

        events = audit.query_events(
            tenant_id=effective_tenant,
            event_type=event_type,
            limit=min(limit, 1000),
        )
        return {"events": events, "total": len(events)}

    return app


def _run_orchestrator(orchestrator: Any, user_msg: str) -> Dict[str, Any]:
    """Synchronous orchestrator execution (for retry/circuit breaker).

    Handles both sync and async execute() methods.
    Called from run_in_executor so it runs in a worker thread, NOT the event loop.
    """
    import asyncio
    result = orchestrator.execute(user_msg)
    # Handle coroutine — since we're in a worker thread, asyncio.run() is safe
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


def get_app() -> Any:
    """Get or lazily create the FastAPI app (for uvicorn)."""
    return _app


def create_app_from_env() -> Any:
    """Phase 3: Factory function for Gunicorn + Docker deployment.

    Reads environment variables to configure and create the FastAPI app
    without requiring explicit constructor arguments. This is the entry
    point used by Docker/Gunicorn:

        gunicorn src.server.fastapi_app:create_app_from_env --factory

    Environment variables:
        TITAN_ENV: 'production' or 'development' (default: development)
        TITAN_AUTH_ENABLED: 'true' to enable auth (default: false in dev)
        TITAN_AUTH_SECRET: JWT secret (required if auth enabled)
        TITAN_RAM_LIMIT_MB: RAM limit in MB (default: 4096)
        DATABASE_URL: PostgreSQL or SQLite connection string
    """
    import os

    # Load .env if present
    try:
        from src.core.env_loader import load_env
        load_env()
    except Exception:
        pass

    # Initialize ResourceGovernor
    ram_limit = int(os.environ.get("TITAN_RAM_LIMIT_MB", "4096"))
    try:
        from src.core.shared.resource_governor import (
            tune_gc_for_arm, set_process_priority_low, limit_open_files, init_governor,
        )
        tune_gc_for_arm()
        set_process_priority_low()
        limit_open_files()
        governor = init_governor(ram_limit_mb=ram_limit)
    except Exception as e:
        logger.warning("ResourceGovernor init failed: %s", e)
        governor = None

    # Initialize database
    from src.core.shared.db_adapters import get_db, is_postgresql
    if is_postgresql():
        # PostgreSQL: async initialization happens on first request
        logger.info("Production mode: PostgreSQL backend selected")
    else:
        # SQLite: synchronous initialization
        try:
            from src.core.shared.db_initializer import initialize_databases
            initialize_databases()
        except Exception as e:
            logger.warning("Database init failed: %s", e)

    # Create orchestrator
    try:
        from src.core.dag_orchestrator import DAGOrchestrator
        orchestrator: Any = DAGOrchestrator()
    except ImportError:
        try:
            from src.core.orchestrator import TitanOrchestrator
            orchestrator = TitanOrchestrator()
        except ImportError:
            logger.warning("No orchestrator available — AI endpoints will fail")
            orchestrator = None

    # Connect governor to model manager
    if governor and hasattr(orchestrator, '_model_mgr'):
        governor.set_model_manager(orchestrator._model_mgr)

    # Auth service
    auth_service = None
    auth_enabled = os.environ.get("TITAN_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
    if auth_enabled or os.environ.get("TITAN_ENV") == "production":
        try:
            from src.core.auth_service import AuthService
            auth_service = AuthService()
            auth_service.ensure_admin()
            logger.info("AuthService: initialized with tenant support")
        except Exception as e:
            logger.warning("AuthService init failed: %s", e)

    # Rate limiter (configurable via env vars for Cline and other tools)
    _rl_rpm = int(os.environ.get("TITAN_RATE_LIMIT_RPM", str(max(1, ram_limit // 64))))
    _rl_burst = int(os.environ.get("TITAN_RATE_LIMIT_BURST", "20"))
    _rl_concurrent = int(os.environ.get("TITAN_RATE_LIMIT_CONCURRENT", "60"))
    if auth_service is not None:
        try:
            from src.server.tenant_rate_limiter import TenantRateLimiter
            rate_limiter: Any = TenantRateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
                default_user_rpm=_rl_rpm,
                default_user_burst=_rl_burst,
            )
        except ImportError:
            from src.server.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
    else:
        try:
            from src.server.rate_limiter import RateLimiter
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
        except ImportError:
            rate_limiter = None

    # Determine platform tag
    platform_tag = "production" if os.environ.get("TITAN_ENV") == "production" else "development"

    # Create and return the FastAPI app
    global _app
    _app = create_app(
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        platform_tag=platform_tag,
    )
    return _app


def run_fastapi_server(
    orchestrator: Any,
    host: str = "0.0.0.0",
    port: int = 5000,
    auth_service: Any = None,
    rate_limiter: Any = None,
    governor: Any = None,
    platform_tag: str = "",
) -> None:
    """Start the FastAPI server using uvicorn.

    Args:
        orchestrator: Orchestrator instance.
        host: Bind host.
        port: Bind port.
        auth_service: Optional AuthService instance.
        rate_limiter: Optional RateLimiter instance.
        governor: Optional ResourceGovernor instance.
        platform_tag: Platform identifier.
    """
    import uvicorn

    global _app
    _app = create_app(
        orchestrator=orchestrator,
        auth_service=auth_service,
        rate_limiter=rate_limiter,
        governor=governor,
        platform_tag=platform_tag,
    )
    uvicorn.run(_app, host=host, port=port, log_level="info")
