"""
TITAN OMNISCALE X - API Server (Pure Python conditional)

Servidor API con import condicional de fastapi.
Compatible con Android (no carga fastapi si no esta disponible).
"""
import json
import time
import uuid

try:
    from fastapi import FastAPI, HTTPException
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    HTTPException = None

# Use DAGOrchestrator (v16) as primary, with TitanOrchestrator (v16) as fallback
try:
    from src.core.dag_orchestrator import DAGOrchestrator as _Orchestrator
except ImportError:
    from src.core.orchestrator import TitanOrchestrator as _Orchestrator

if HAS_FASTAPI:
    _app = None
    _orch = None

    def get_app():
        """Lazy factory for FastAPI app + Orchestrator (avoids module-level instantiation)."""
        global _app, _orch
        if _app is None:
            _app = FastAPI()
            _orch = _Orchestrator()
            _register_routes(_app, _orch)
        return _app

    def _register_routes(app, orch):

        @app.post("/v1/chat/completions")
        async def openai_mock(req):
            msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
            if not msg:
                raise HTTPException(status_code=400, detail="No message provided in request")

            # Gap 5: Detect tool_calls responses (resumption from partial reasoning)
            # If the last assistant message contains tool_calls with zenith_mcts_plan,
            # and a tool response follows, resume from partial reasoning
            resumption_token = None
            for m in req.messages:
                if m.role == "assistant" and hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        if hasattr(tc, 'function') and tc.function.name == "zenith_mcts_plan":
                            try:
                                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                                resumption_token = args.get("resumption_token")
                            except (json.JSONDecodeError, AttributeError):
                                pass
                # Also check for explicit resumption in tool response
                if m.role == "tool" and hasattr(m, 'content'):
                    try:
                        tool_data = json.loads(m.content) if isinstance(m.content, str) else {}
                        if tool_data.get("resumption_token"):
                            resumption_token = tool_data["resumption_token"]
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        pass

            if resumption_token:
                # Resume from partial reasoning
                res = await orch.resume_from_partial(resumption_token)
            else:
                # Normal execution path
                res = await orch.execute(msg)

            content = (
                f"TITAN OMNISCALE X\n"
                f"Estado: {res['status']}\n"
                f"Hash: {res.get('hash', 'N/A')}\n"
                f"Error: {res.get('error', 'Ninguno')}\n\n"
                f"```{res.get('code', '')}```"
            )

            # If partial reasoning, include the tool_calls payload in OpenAI format
            finish_reason = "stop"
            tool_calls_data = None
            if res.get("partial_reasoning") and res.get("partial_reasoning_payload"):
                payload = res["partial_reasoning_payload"]
                tool_calls_data = payload.get("tool_calls")
                finish_reason = payload.get("finish_reason", "tool_calls")
                content = payload.get("content", content)

            message_obj = {"role": "assistant", "content": content}
            if tool_calls_data:
                message_obj["tool_calls"] = tool_calls_data

            response = {
                "id": f"titan-{uuid.uuid4().hex[:6]}", "object": "chat.completion",
                "created": int(time.time()), "model": "titan-omniscale-x",
                "choices": [{"index": 0, "message": message_obj, "finish_reason": finish_reason}],
                "usage": res.get("usage_metadata", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            }

            # Include resumption data if available (for client to resume later)
            if res.get("resumption"):
                response["resumption"] = res["resumption"]

            return response

        @app.post("/v1/resume")
        async def resume_partial(req):
            """Resume a partial reasoning session using a resumption token."""
            body = req if isinstance(req, dict) else {}
            if hasattr(req, 'model_dump'):
                body = req.model_dump()
            elif hasattr(req, 'dict'):
                body = req.dict()

            token = body.get("resumption_token", "")
            subtask_index = body.get("subtask_index")

            if not token:
                raise HTTPException(status_code=400, detail="resumption_token is required")

            res = await orch.resume_from_partial(token, subtask_index=subtask_index)
            return res

        @app.get("/v1/models")
        async def models():
            return {"object": "list", "data": [{"id": "titan-omniscale-x", "object": "model", "owned_by": "local"}]}
