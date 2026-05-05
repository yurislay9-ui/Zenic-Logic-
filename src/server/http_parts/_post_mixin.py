"""
POST endpoint mixin for TitanHTTPHandler.
"""

from ._imports import (
    logger, json, _run_async,
    build_normal_response, build_partial_reasoning_response,
    build_error_response, build_overloaded_response,
)


class PostMixin:
    """POST endpoint handlers for TitanHTTPHandler."""

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
        client_ip = self.client_address[0]
        if self.rate_limiter and not self.rate_limiter.acquire(client_ip):
            self._send_json({
                "error": {"message": "Rate limit exceeded. Slow down.",
                          "type": "rate_limit_exceeded"}
            }, status=429)
            return

        gov = self.governor
        if gov:
            gov.pre_request()
            if gov.is_ram_critical():
                self._send_json(build_overloaded_response(), status=503)
                if self.rate_limiter:
                    self.rate_limiter.release()
                return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({
                "error": {"message": f"Invalid JSON: {str(e)}",
                          "type": "invalid_request_error"}
            }, status=400)
            return

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
            result = _run_async(self.orchestrator.execute(user_msg))
            if result.get("partial_reasoning"):
                response = build_partial_reasoning_response(data, result, user_msg)
                self._send_json(response)
                return
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
                "niche": niche_name, "files_generated": len(files),
                "files": list(files.keys()), "entities": len(plan.entities),
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
