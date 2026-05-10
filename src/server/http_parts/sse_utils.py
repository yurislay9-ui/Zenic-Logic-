"""Shared SSE streaming utilities for OpenAI-compatible chunk format.

Both the stdlib HTTP handler (_post_mixin.py) and the FastAPI server
(fastapi_app.py) produce the same OpenAI streaming chunk format.
This module extracts the common logic to avoid duplication.

OpenAI Streaming Spec:
- Each chunk is a chat.completion.chunk object
- `role: "assistant"` appears ONLY in the first chunk's delta
- Final chunk has `finish_reason: "stop"` and empty content delta
- Stream terminates with `data: [DONE]`
"""

import json
import time
import uuid
from typing import Iterator, List, Dict, Any, Optional


def make_sse_request_id() -> str:
    """Generate a Titan-style request ID for SSE chunks."""
    return f"titan-{uuid.uuid4().hex[:8]}"


def make_sse_chunk(
    request_id: str,
    created: int,
    model: str,
    delta: Dict[str, Any],
    finish_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single OpenAI-format SSE chunk dict.

    Args:
        request_id: Unique request identifier.
        created: Unix timestamp of request creation.
        model: Model name string.
        delta: Delta dict (e.g. {"content": "...", "role": "assistant"}).
        finish_reason: None for content chunks, "stop" for final chunk.

    Returns:
        Dict conforming to OpenAI chat.completion.chunk schema.
    """
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }


def format_sse_data(chunk: Dict[str, Any]) -> str:
    """Format a chunk dict as an SSE `data:` line."""
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def make_final_chunk(
    request_id: str,
    created: int,
    model: str,
) -> Dict[str, Any]:
    """Build the final SSE chunk with finish_reason='stop'."""
    return make_sse_chunk(
        request_id=request_id,
        created=created,
        model=model,
        delta={"content": ""},
        finish_reason="stop",
    )


def make_error_chunk(
    request_id: str,
    created: int,
    model: str,
    error_message: str,
) -> Dict[str, Any]:
    """Build an error SSE chunk (truncated message, finish_reason='stop')."""
    return make_sse_chunk(
        request_id=request_id,
        created=created,
        model=model,
        delta={"content": f"\n[Stream Error: {error_message[:100]}]"},
        finish_reason="stop",
    )


def iter_sse_chunks(
    content: str,
    model: str = "titan-omniscale-x",
    chunk_size: int = 8,
    request_id: Optional[str] = None,
) -> Iterator[str]:
    """Iterate over SSE-formatted strings for the given content.

    This is the shared core that both stdlib and FastAPI servers use.
    Yields `data: {...}\\n\\n` strings ready to write to the output.

    Args:
        content: The full text content to stream.
        model: Model name for the chunks.
        chunk_size: Characters per content chunk.
        request_id: Optional request ID (auto-generated if None).

    Yields:
        SSE-formatted strings (`data: {...}\\n\\n`).
    """
    if request_id is None:
        request_id = make_sse_request_id()
    created = int(time.time())

    first_chunk = True
    for i in range(0, len(content), chunk_size):
        chunk_text = content[i:i + chunk_size]
        delta: Dict[str, Any] = {"content": chunk_text}
        # Per OpenAI spec: role appears in the FIRST chunk only
        if first_chunk:
            delta["role"] = "assistant"
            first_chunk = False
        yield format_sse_data(make_sse_chunk(request_id, created, model, delta))

    # Final chunk with finish_reason="stop" (no role per OpenAI spec)
    yield format_sse_data(make_final_chunk(request_id, created, model))

    # Stream terminator
    yield "data: [DONE]\n\n"
