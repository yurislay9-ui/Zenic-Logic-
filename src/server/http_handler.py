"""
TITAN OMNISCALE X v13 - Unified HTTP Handler

Handler HTTP compatible con la API de OpenAI. Unifica la logica
que antes estaba duplicada entre main.py (Kivy) y main_headless.py (Termux).

Nuevos endpoints para generacion de apps y automatizaciones:
  POST /v1/generate/app      - Generar app completa
  POST /v1/generate/automation - Generar automatizacion
  POST /v1/design/schema     - Disenar esquema de BD
  POST /v1/think             - Razonar con ThinkingEngine
  POST /v1/reason            - Razonamiento avanzado (Phase 8)
  POST /v1/chain/validate    - Validar cadena de logica
  POST /v1/chain/execute     - Ejecutar cadena con rollback
  GET  /v1/projects          - Listar proyectos generados
  GET  /v1/automations       - Listar automatizaciones
  GET  /v1/system/status     - Estado completo del sistema
  GET  /v1/intelligence/status - Estado de inteligencia (Phase 8)
  GET  /v1/templates         - Templates disponibles
"""

import json
import logging
import time
import asyncio
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


class TitanHTTPHandler(BaseHTTPRequestHandler):
    """
    Handler HTTP compatible con la API de OpenAI + App/Automation generation.

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
    rate_limiter = None

    def log_message(self, format, *args):
        logger.info("HTTP: %s", format % args)

    # ============================================================
    #  GET endpoints
    # ============================================================

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/v1/models':
            self._send_json({
                "object": "list",
                "data": [{
                    "id": "titan-omniscale-x",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "titan-local"
                }]
            })
        elif path == '/':
            self._handle_root()
        elif path == '/health':
            self._handle_health()
        elif path == '/v1/projects':
            self._handle_list_projects(params)
        elif path == '/v1/automations':
            self._handle_list_automations()
        elif path == '/v1/templates':
            self._handle_list_templates()
        elif path == '/v1/system/status':
            self._handle_system_status()
        elif path == '/v1/intelligence/status':
            self._handle_intelligence_status()
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
            "ThinkingEngine", "AppGenerator", "AutomationEngine",
            "SchemaDesigner", "SmartMemory_Enhanced",
            "ReasoningEngine", "ChainValidator", "ChainExecutor",
        ]
        if gov:
            features.append("Resource_Governor")

        response = {
            "status": "active",
            "model": "titan-omniscale-x",
            "version": f"13.0{version_suffix}",
            "endpoints": [
                "/v1/chat/completions", "/v1/models", "/health",
                "/v1/generate/app", "/v1/generate/automation",
                "/v1/design/schema", "/v1/think", "/v1/reason",
                "/v1/chain/validate", "/v1/chain/execute",
                "/v1/projects", "/v1/automations",
                "/v1/templates", "/v1/system/status",
                "/v1/intelligence/status",
            ],
            "pipeline_levels": 8,
            "solver": solver_name,
            "features": features,
            "description": f"TITAN OMNISCALE X v13 - Local Surgical AI Engine ({solver_name}) + App & Automation Generator",
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

    def _handle_list_projects(self, params):
        """GET /v1/projects - Lista proyectos generados."""
        try:
            status_filter = params.get("status", [""])[0]
            loop = asyncio.new_event_loop()
            projects = loop.run_until_complete(
                self.orchestrator.list_projects(status_filter)
            )
            loop.close()
            self._send_json({"projects": projects, "total": len(projects)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_automations(self):
        """GET /v1/automations - Lista automatizaciones."""
        try:
            loop = asyncio.new_event_loop()
            automations = loop.run_until_complete(
                self.orchestrator.list_automations()
            )
            loop.close()
            self._send_json({"automations": automations, "total": len(automations)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_templates(self):
        """GET /v1/templates - Lista templates disponibles."""
        try:
            from src.core.app_generator import AppGenerator
            templates = AppGenerator.list_templates()
            self._send_json(templates)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_system_status(self):
        """GET /v1/system/status - Estado completo del sistema."""
        try:
            loop = asyncio.new_event_loop()
            status = loop.run_until_complete(
                self.orchestrator.get_system_status()
            )
            loop.close()
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    # ============================================================
    #  POST endpoints
    # ============================================================

    def do_POST(self):
        if self.path == '/v1/chat/completions':
            self._handle_chat_completions()
        elif self.path == '/v1/generate/app':
            self._handle_generate_app()
        elif self.path == '/v1/generate/automation':
            self._handle_generate_automation()
        elif self.path == '/v1/design/schema':
            self._handle_design_schema()
        elif self.path == '/v1/think':
            self._handle_think()
        elif self.path == '/v1/reason':
            self._handle_reason()
        elif self.path == '/v1/chain/validate':
            self._handle_chain_validate()
        elif self.path == '/v1/chain/execute':
            self._handle_chain_execute()
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

    def _handle_generate_app(self):
        """POST /v1/generate/app - Generar app completa."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return

        project_name = data.get("project_name", "")
        output_dir = data.get("output_dir", "")

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.generate_app(description, project_name, output_dir)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"App generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_generate_automation(self):
        """POST /v1/generate/automation - Generar automatizacion."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return

        output_dir = data.get("output_dir", "")

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.generate_automation(description, output_dir)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Automation generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_design_schema(self):
        """POST /v1/design/schema - Disenar esquema de BD."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.design_schema(description)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Schema design error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_think(self):
        """POST /v1/think - Razonar con ThinkingEngine."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        query = data.get("query", "")
        if not query:
            self._send_json({"error": "Missing 'query' field"}, status=400)
            return

        context = data.get("context", "")

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.think(query, context)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Thinking error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_reason(self):
        """POST /v1/reason - Razonamiento avanzado (Phase 8)."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        query = data.get("query", "")
        if not query:
            self._send_json({"error": "Missing 'query' field"}, status=400)
            return

        mode = data.get("mode", "auto")
        context = data.get("context", "")

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.reason(query, mode, context)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Reasoning error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_chain_validate(self):
        """POST /v1/chain/validate - Validar cadena de logica."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.validate_logic_chain(description)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Chain validation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_chain_execute(self):
        """POST /v1/chain/execute - Ejecutar cadena con rollback y recovery."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return

        chain_data = data.get("data", {})
        recovery = data.get("recovery", "skip")

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.execute_logic_chain(description, chain_data, recovery)
            )
            loop.close()
            self._send_json(result)
        except Exception as e:
            logger.error(f"Chain execution error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_intelligence_status(self):
        """GET /v1/intelligence/status - Estado de inteligencia (Phase 8)."""
        try:
            loop = asyncio.new_event_loop()
            status = loop.run_until_complete(
                self.orchestrator.get_intelligence_status()
            )
            loop.close()
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

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
