from fastapi import FastAPI, HTTPException
from src.core.shared.contracts import ChatRequest
from src.core.orchestrator import TitanOrchestrator
import time, uuid

app = FastAPI()
orch = TitanOrchestrator()

@app.post("/v1/chat/completions")
async def openai_mock(req: ChatRequest):
    msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
    if not msg:
        raise HTTPException(status_code=400, detail="No message provided in request")

    res = await orch.execute(msg)
    content = f"TITAN OMNISCALE X\nEstado: {res['status']}\nHash: {res.get('hash','N/A')}\nError: {res.get('error','Ninguno')}\n\n```{res.get('code','')}```"

    return {
        "id": f"titan-{uuid.uuid4().hex[:6]}", "object": "chat.completion", "created": int(time.time()), "model": "titan-v12",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "titan-omniscale-x", "object": "model", "owned_by": "local"}]}
