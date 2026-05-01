"""
TITAN OMNISCALE X v13 - Unified HTTP Handler

Handler HTTP compatible con la API de OpenAI. Unifica la logica
que antes estaba duplicada entre main.py (Kivy) y main_headless.py (Termux).

Soporta modo opcional con Resource Governor (headless/Termux).
"""

import json
import logging
import time
from http.server import BaseHTTPRequestHandler

from src.core.shared.contracts import HAS_Z3
from src.server.rate_limiter import RateLimiter
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)

logger = logging.getLogger("TITAN")


class TitanHTTPHandler(BaseHTTPRequestHandler):
    """
    Handler HTTP compatible con la API de OpenAI.

    Atributos de clase (configurar antes de iniciar el servidor):
        orchestrator: TitanOrchestrator instance
        governor: ResourceGovernor instance (opcional, solo headless)
        start_time: float - timestamp de inicio del servidor (opcional)
        platform_tag: str - "kivy" o "termux-proot"
    """

    orchestrator = None
    governor = None
    start_time = None
    platform_tag = ""
    rate_limiter = None  # RateLimiter instance (configured by server)

    def log_message(self, format, *args):
        logger.info("HTTP: %s", format % args)

    # ============================================================
    #  GET endpoints
    # ============================================================

    def do_GET(self):
        if self.path == '/v1/models':
            self._send_json({
                "object": "list",
                "data": [{
                    "id": "titan-omniscale-x",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "titan-local"
                }]
            })
        elif self.path == '/':
            self._handle_root()
        elif self.path == '/health':
            self._handle_health()
        else:
            self._send_json({"error": "Not found"}, status=404)

    def _handle_root(self):
        """Info general del servidor."""
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        gov = self.governor
        res_status = gov.get_status() if gov else {}

        version_suffix = f"-{self.platform_tag}" if self.platform_tag else ""
        features = [
            "MCTS", f"{solver_name}_Solver", "Timeout_Enforcement",
            "Theorem_Cache", "Skeleton_Hash", "K_Path_Limiting",
            "Symbolic_Execution", "Abortive_Protocol",
            "Partial_Reasoning", "Contextual_CodeGen",
        ]
        if gov:
            features.append("Resource_Governor")

        response = {
            "status": "active",
            "model": "titan-omniscale-x",
            "version": f"13.0{version_suffix}",
            "endpoints": ["/v1/chat/completions", "/v1/models", "/health"],
            "pipeline_levels": 8,
            "solver": solver_name,
            "features": features,
            "description": f"TITAN OMNISCALE X v13 - Local Surgical AI Engine ({solver_name})",
        }
        if self.platform_tag:
            response["platform"] = self.platform_tag
        if res_status:
            response["resources"] = res_status

        self._send_json(response)

    def _handle_health(self):
        """Health check con info de recursos si governor disponible."""
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        gov = self.governor

        health = {
            "status": "healthy",
            "solver": solver_name,
            "has_z3": HAS_Z3,
        }
        if self.start_time:
            health["uptime_s"] = int(time.time() - self.start_time)

        if gov:
            health["resources"] = gov.get_status()
            if gov.is_ram_critical():
                health["status"] = "degraded"
                health["reason"] = f"RAM critical: {gov._ram_usage_mb:.0f}MB"

        self._send_json(health)

    # ============================================================
    #  POST endpoints
    # ============================================================

    def do_POST(self):
        if self.path == '/v1/chat/completions':
            self._handle_chat_completions()
        else:
            self._send_json({"error": "Not found"}, status=404)

    def _handle_chat_completions(self):
        """Procesa peticion /v1/chat/completions con rate limiting y governor."""
        # Rate limiting check
        client_ip = self.client_address[0]
        if self.rate_limiter and not self.rate_limiter.acquire(client_ip):
            self._send_json({
                "error": {"message": "Rate limit exceeded. Slow down.",
                          "type": "rate_limit_exceeded"}
            }, status=429)
            return

        gov = self.governor

        # Pre-request: preparar recursos y verificar RAM
        if gov:
            gov.pre_request()
            if gov.is_ram_critical():
                self._send_json(build_overloaded_response(), status=503)
                if self.rate_limiter:
                    self.rate_limiter.release()
                return

        try:
            # Parsear JSON del body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({
                "error": {"message": f"Invalid JSON: {str(e)}",
                          "type": "invalid_request_error"}
            }, status=400)
            return

        # Extraer mensaje del usuario
        messages = data.get("messages", [])
        if not messages:
            self._send_json({
                "error": {"message": "No messages provided",
                          "type": "invalid_request_error"}
            }, status=400)
            return

        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        if not user_msg:
            self._send_json({
                "error": {"message": "No user message found",
                          "type": "invalid_request_error"}
            }, status=400)
            return

        try:
            # Ejecutar pipeline
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.orchestrator.execute(user_msg))
            loop.close()

            # Razonamiento Parcial
            if result.get("partial_reasoning"):
                response = build_partial_reasoning_response(data, result, user_msg)
                self._send_json(response)
                return

            # Respuesta Normal
            response = build_normal_response(data, result, user_msg, governor=gov)
            self._send_json(response)

        except Exception as e:
            logger.error("Error processing request: %s", e, exc_info=True)
            self._send_json(build_error_response(str(e)))

        finally:
            if gov:
                gov.post_request()
            if self.rate_limiter:
                self.rate_limiter.release()

    # ============================================================
    #  CORS + JSON helpers
    # ============================================================

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._set_cors_headers()
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
