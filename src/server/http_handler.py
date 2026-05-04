"""
TITAN OMNISCALE X v16 - Unified HTTP Handler

Handler HTTP compatible con la API de OpenAI. Unifica la logica
que antes estaba duplicada entre main.py (Kivy) y main_headless.py (Termux).

Nuevos endpoints para generacion de apps y automatizaciones:
  POST /v1/generate/app      - Generar app completa
  POST /v1/generate/automation - Generar automatizacion
  POST /v1/generate/niche     - Generar app desde nicho predefinido
  POST /v1/design/schema     - Disenar esquema de BD
  POST /v1/think             - Razonar con ThinkingEngine
  POST /v1/reason            - Razonamiento avanzado (Phase 8)
  POST /v1/chain/validate    - Validar cadena de logica
  POST /v1/chain/execute     - Ejecutar cadena con rollback
  GET  /v1/projects          - Listar proyectos generados
  GET  /v1/automations       - Listar automatizaciones
  GET  /v1/niches            - Listar nichos disponibles
  GET  /v1/niches/domains    - Listar dominios de nichos
  GET  /v1/niches/search     - Buscar nichos por descripcion
  GET  /v1/system/status     - Estado completo del sistema
  GET  /v1/intelligence/status - Estado de inteligencia (Phase 8)
  GET  /v1/templates         - Templates disponibles
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

# Configurable CORS origin (SEC-6: avoid hardcoded wildcard)
_cors_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# ============================================================
#  PERSISTENT ASYNCIO EVENT LOOP (performance optimization)
#  Replaces creating a new event loop per request, which is
#  expensive and can cause issues with asyncio-based resources.
# ============================================================

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
    """Run an async coroutine on the shared event loop (thread-safe).
    
    Uses asyncio.run_coroutine_threadsafe() to safely submit coroutines
    from handler threads to the shared event loop. This avoids
    RuntimeError when multiple threads call run_until_complete concurrently.
    """
    loop = _get_shared_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=120)


# Register atexit handler for shared loop cleanup (CQ-7/CQ-8)
atexit.register(_shutdown_loop)


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
        elif path == '/v1/niches':
            self._handle_list_niches(params)
        elif path == '/v1/niches/domains':
            self._handle_list_domains()
        elif path == '/v1/niches/search':
            self._handle_search_niches(params)
        elif path == '/v1/system/status':
            self._handle_system_status()
        elif path == '/v1/intelligence/status':
            self._handle_intelligence_status()
        elif path == '/v1/system/power-mode':
            self._handle_power_mode()
        elif path == '/v1/system/context-index':
            self._handle_context_index()
        elif path == '/v1/system/auto-evolve':
            self._handle_auto_evolve(params)
        elif path == '/v1/dna/modules':
            self._handle_dna_modules(params)
        elif path == '/v1/dna/domain-rules':
            self._handle_dna_domain_rules(params)
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
            "version": f"16.0{version_suffix}",
            "endpoints": [
                "/v1/chat/completions", "/v1/models", "/health",
                "/v1/generate/app", "/v1/generate/automation", "/v1/generate/niche",
                "/v1/design/schema", "/v1/think", "/v1/reason",
                "/v1/chain/validate", "/v1/chain/execute",
                "/v1/projects", "/v1/automations",
                "/v1/niches", "/v1/niches/domains", "/v1/niches/search",
                "/v1/templates", "/v1/system/status",
                "/v1/intelligence/status",
            ],
            "pipeline_levels": 8,
            "solver": solver_name,
            "features": features,
            "description": f"TITAN OMNISCALE X v16 - Local Surgical AI Engine ({solver_name}) + App & Automation Generator",
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
            "mode": "hybrid_lazy",  # New: indicates hybrid lazy loading mode
        }
        if self.start_time:
            health["uptime_s"] = int(time.time() - self.start_time)

        if gov:
            health["resources"] = gov.get_status()
            if gov.is_ram_critical():
                health["status"] = "degraded"
                health["reason"] = f"RAM critical: {gov.ram_usage_mb:.0f}MB"

        # Model Manager status
        if hasattr(self.orchestrator, '_model_mgr'):
            health["models"] = self.orchestrator._model_mgr.get_status()

        self._send_json(health)

    def _handle_list_projects(self, params):
        """GET /v1/projects - Lista proyectos generados."""
        try:
            status_filter = params.get("status", [""])[0]
            projects = _run_async(self.orchestrator.list_projects(status_filter))
            self._send_json({"projects": projects, "total": len(projects)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_automations(self):
        """GET /v1/automations - Lista automatizaciones."""
        try:
            automations = _run_async(self.orchestrator.list_automations())
            self._send_json({"automations": automations, "total": len(automations)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_templates(self):
        """GET /v1/templates - Lista templates disponibles."""
        try:
            from src.core.app_generator import AppGenerator
            templates = AppGenerator.list_templates()
            # Add niche templates info
            try:
                from src.core.template_engine import TemplateEngine
                engine = TemplateEngine()
                templates["niche_templates"] = engine.list_niches()
                templates["niche_domains"] = engine.list_domains()
            except Exception as e:
                logger.debug("HTTP: TemplateEngine niche listing failed: %s", e)
            self._send_json(templates)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_niches(self, params):
        """GET /v1/niches - Lista nichos disponibles."""
        try:
            domain = params.get("domain", [""])[0]
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            niches = engine.list_niches(domain)
            result = []
            for name in niches:
                plan = engine.get_niche_plan(name)
                if plan:
                    result.append({
                        "name": name,
                        "entities": len(plan.entities),
                        "blocks": plan.blocks,
                    })
            self._send_json({"niches": result, "total": len(result), "domain": domain or "all"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_list_domains(self):
        """GET /v1/niches/domains - Lista dominios de nichos."""
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            domains = engine.list_domains()
            result = []
            for d in domains:
                niches = engine.list_niches(d)
                result.append({"domain": d, "niche_count": len(niches), "niches": niches})
            self._send_json({"domains": result, "total": len(result)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_search_niches(self, params):
        """GET /v1/niches/search - Buscar nichos por descripcion."""
        try:
            query = params.get("q", [""])[0]
            if not query:
                self._send_json({"error": "Missing 'q' parameter"}, status=400)
                return
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            results = engine.search_niches(query)
            self._send_json({"results": results, "total": len(results), "query": query})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_system_status(self):
        """GET /v1/system/status - Estado completo del sistema."""
        try:
            status = _run_async(self.orchestrator.get_system_status())
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
        elif self.path == '/v1/generate/niche':
            self._handle_generate_niche()
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
        elif self.path == '/v1/system/context-index':
            self._handle_context_index_post()
        elif self.path == '/v1/system/auto-evolve/trigger':
            self._handle_auto_evolve_trigger()
        elif self.path == '/v1/dna/validate':
            self._handle_dna_validate()
        elif self.path == '/v1/dna/polish':
            self._handle_dna_polish()
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
            result = _run_async(self.orchestrator.execute(user_msg))

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
            result = _run_async(self.orchestrator.generate_app(description, project_name, output_dir))
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
            result = _run_async(self.orchestrator.generate_automation(description, output_dir))
            self._send_json(result)
        except Exception as e:
            logger.error(f"Automation generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_generate_niche(self):
        """POST /v1/generate/niche - Generar app desde nicho predefinido."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        niche_name = data.get("niche", "")
        if not niche_name:
            # Try to auto-detect niche from description
            description = data.get("description", "")
            if not description:
                self._send_json({"error": "Missing 'niche' or 'description' field"}, status=400)
                return
            try:
                from src.core.template_engine import TemplateEngine
                engine = TemplateEngine()
                results = engine.search_niches(description, limit=1)
                if results:
                    niche_name = results[0].get("name", "")
                else:
                    self._send_json({"error": f"No niche found matching: {description}"}, status=404)
                    return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return

        output_dir = data.get("output_dir", "")

        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            plan = engine.get_niche_plan(niche_name)
            if not plan:
                self._send_json({"error": f"Niche '{niche_name}' not found"}, status=404)
                return

            files = engine.render_niche(niche_name)
            self._send_json({
                "niche": niche_name,
                "files_generated": len(files),
                "files": list(files.keys()),
                "entities": len(plan.entities),
                "blocks": plan.blocks,
            })
        except Exception as e:
            logger.error(f"Niche generation error: {e}", exc_info=True)
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
            result = _run_async(self.orchestrator.design_schema(description))
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
            result = _run_async(self.orchestrator.think(query, context))
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
            result = _run_async(self.orchestrator.reason(query, mode, context))
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
            result = _run_async(self.orchestrator.validate_logic_chain(description))
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
            result = _run_async(self.orchestrator.execute_logic_chain(description, chain_data, recovery))
            self._send_json(result)
        except Exception as e:
            logger.error(f"Chain execution error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_intelligence_status(self):
        """GET /v1/intelligence/status - Estado de inteligencia (Phase 8)."""
        try:
            status = _run_async(self.orchestrator.get_intelligence_status())
            self._send_json(status)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_power_mode(self):
        """GET /v1/system/power-mode - Estado del modo Low-Power Sequential."""
        try:
            lpm = getattr(self.orchestrator, '_low_power_mode', None)
            if lpm:
                self._send_json(lpm.stats)
            else:
                self._send_json({"mode": "unavailable", "reason": "LowPowerSequentialMode not initialized"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_context_index(self, params=None):
        """GET /v1/system/context-index - Estado del índice de Context Pointers."""
        try:
            cpe = getattr(self.orchestrator, '_context_pointer_engine', None)
            if cpe:
                query = (params or {}).get("q", [""])[0] if params else ""
                if query:
                    pointers = cpe.search(query, top_k=10)
                    result = {
                        "stats": cpe.stats,
                        "query": query,
                        "results": [p.to_model_context() for p in pointers],
                    }
                else:
                    result = cpe.stats
                self._send_json(result)
            else:
                self._send_json({"status": "unavailable", "reason": "ContextPointerEngine not initialized"})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_context_index_post(self):
        """POST /v1/system/context-index - Indexar código para Context Pointers."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        code = data.get("code", "")
        file_path = data.get("file_path", "input.py")
        if not code:
            self._send_json({"error": "Missing 'code' field"}, status=400)
            return

        try:
            cpe = getattr(self.orchestrator, '_context_pointer_engine', None)
            if cpe:
                count = cpe.index_code(code, file_path)
                compact_ctx, pointers = cpe.build_compact_context(data.get("query", ""), max_tokens=2000)
                self._send_json({
                    "indexed_signatures": count,
                    "compact_context": compact_ctx,
                    "pointers_count": len(pointers),
                    "stats": cpe.stats,
                })
            else:
                self._send_json({"error": "ContextPointerEngine not available"}, status=503)
        except Exception as e:
            logger.error(f"Context index error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_auto_evolve(self, params):
        """GET /v1/system/auto-evolve - Estado del Auto-Scraping YAML."""
        try:
            cron = getattr(self.orchestrator, '_niche_cron', None)
            updater = getattr(self.orchestrator, '_niche_auto_scraper', None)
            result = {
                "auto_scraper": updater.stats if updater else {"status": "unavailable"},
                "cron_scheduler": cron.stats if cron else {"status": "unavailable"},
            }
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_auto_evolve_trigger(self):
        """POST /v1/system/auto-evolve/trigger - Forzar ciclo de auto-evolución."""
        try:
            cron = getattr(self.orchestrator, '_niche_cron', None)
            if cron:
                result = cron.trigger_now()
                self._send_json(result)
            else:
                self._send_json({"error": "AutoEvolve cron not available"}, status=503)
        except Exception as e:
            logger.error(f"Auto-evolve trigger error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_modules(self, params):
        """GET /v1/dna/modules - Listar módulos de lógica atómica."""
        try:
            from src.core.dna_loader import get_dna_loader
            dna = get_dna_loader()
            domain = params.get("domain", [""])[0]
            query = params.get("q", [""])[0]
            if query:
                modules = dna.search_modules(query, limit=20)
            elif domain:
                modules = dna.get_modules_by_domain(domain)
            else:
                modules = list(dna._logic_modules.values())
            result = [
                {"id": m.id, "domain": m.domain, "description": m.description,
                 "dependencies": m.dependencies, "verification_rule": m.verification_rule}
                for m in modules
            ]
            self._send_json({"modules": result, "total": len(result)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_domain_rules(self, params):
        """GET /v1/dna/domain-rules - Obtener reglas de negocio por industria."""
        try:
            from src.core.dna_loader import get_dna_loader
            dna = get_dna_loader()
            industry = params.get("industry", [""])[0]
            if industry:
                rules = dna.get_domain_rules(industry)
                if rules:
                    self._send_json({
                        "industry": rules.name,
                        "display_name": rules.display_name,
                        "mandatory_logic": rules.mandatory_logic,
                        "compliance": rules.compliance_requirements,
                        "invariants": rules.business_invariants,
                    })
                else:
                    self._send_json({"error": f"Industry '{industry}' not found"}, status=404)
            else:
                industries = [{"name": r.name, "display_name": r.display_name,
                               "mandatory_count": len(r.mandatory_logic)}
                              for r in dna._domain_rules.values()]
                self._send_json({"industries": industries, "total": len(industries)})
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_validate(self):
        """POST /v1/dna/validate - Validar código contra gates de calidad."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        code = data.get("code", "")
        niche_name = data.get("niche", "")
        if not code:
            self._send_json({"error": "Missing 'code' field"}, status=400)
            return

        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            result = engine.validate_niche_code(code, niche_name)
            self._send_json(result)
        except Exception as e:
            logger.error(f"DNA validate error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    def _handle_dna_polish(self):
        """POST /v1/dna/polish - Pulir texto técnico a corporativo."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return

        text = data.get("text", "")
        if not text:
            self._send_json({"error": "Missing 'text' field"}, status=400)
            return

        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            polished = engine.polish_output(text)
            self._send_json({"original": text, "polished": polished})
        except Exception as e:
            logger.error(f"DNA polish error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)

    # ============================================================
    #  CORS + JSON helpers
    # ============================================================

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', _cors_origin)
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
