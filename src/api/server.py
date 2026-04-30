"""
TITAN OMNISCALE X - API Server (Pure Python conditional)

Servidor API con import condicional de fastapi.
Compatible con Android (no carga fastapi si no esta disponible).
"""
import time
import uuid
from src.core.shared.contracts import ChatRequest

try:
    from fastapi import FastAPI, HTTPException
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    HTTPException = None

from src.core.orchestrator import TitanOrchestrator

if HAS_FASTAPI:
    app = FastAPI()
    orch = TitanOrchestrator()

    @app.post("/v1/chat/completions")
    async def openai_mock(req):
        msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        if not msg:
            raise HTTPException(status_code=400, detail="No message provided in request")

        res = await orch.execute(msg)
        content = (
            f"TITAN OMNISCALE X\n"
            f"Estado: {res['status']}\n"
            f"Hash: {res.get('hash', 'N/A')}\n"
            f"Error: {res.get('error', 'Ninguno')}\n\n"
            f"```{res.get('code', '')}```"
        )

        return {
            "id": f"titan-{uuid.uuid4().hex[:6]}", "object": "chat.completion",
            "created": int(time.time()), "model": "titan-v12",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": "titan-omniscale-x", "object": "model", "owned_by": "local"}]}
