"""
SSE Streamer — Server-Sent Events streaming for Open Design.

Provides real-time streaming of LLM output chunks to Open Design's
iframe, enabling live preview of generated UI as it's being created.

Supports both FastAPI (StreamingResponse) and the legacy stdlib HTTP server.
"""

import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, AsyncIterator, Iterator, Callable, List

from .config import get_open_design_config

logger = logging.getLogger(__name__)


class SSEStreamer:
    """
    Streams LLM output as Server-Sent Events (SSE) for Open Design.

    The SSE format follows the OpenAI streaming spec:
        data: {"id":"titan-xxx","object":"chat.completion.chunk",
               "choices":[{"delta":{"content":"chunk text"},"index":0}]}

    With additional Open Design event types:
        event: fractal_structure
        data: {...}

        event: fractal_skeleton
        data: {...}

        event: fractal_fill
        data: {...}

        event: artifact
        data: {"identifier":"...","language":"html","code":"..."}
    """

    def __init__(self, request_id: Optional[str] = None):
        self._request_id = request_id or f"titan-{uuid.uuid4().hex[:8]}"
        self._created = int(time.time())
        self._model = "titan-omniscale-x"
        self._config = get_open_design_config()
        self._chunk_index = 0

    def format_chunk(self, content: str, finish_reason: Optional[str] = None) -> str:
        """
        Format a single SSE chunk following OpenAI streaming spec.

        Args:
            content: Text content for this chunk.
            finish_reason: None for intermediate chunks, "stop" for final.

        Returns:
            Formatted SSE data line: "data: {json}\\n\\n"
        """
        delta: Dict[str, Any] = {"content": content}
        if finish_reason:
            delta["role"] = "assistant"

        chunk = {
            "id": self._request_id,
            "object": "chat.completion.chunk",
            "created": self._created,
            "model": self._model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }

        self._chunk_index += 1
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def format_done(self) -> str:
        """Format the SSE [DONE] signal."""
        return "data: [DONE]\n\n"

    def format_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        Format a custom SSE event (for fractal phases, artifacts, etc.).

        Args:
            event_type: Event name (e.g., 'fractal_structure', 'artifact').
            data: Event payload as dict.

        Returns:
            Formatted SSE event: "event: type\\ndata: json\\n\\n"
        """
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def format_artifact_event(self, identifier: str, language: str,
                               code: str, title: str = "") -> str:
        """Format an SSE event with an <artifact> tag payload."""
        return self.format_event("artifact", {
            "identifier": identifier,
            "language": language,
            "title": title or f"Generated {language.upper()}",
            "code": code,
        })

    def format_fractal_phase(self, phase: str, data: Dict[str, Any]) -> str:
        """
        Format an SSE event for a FractalGenerator phase.

        Args:
            phase: One of 'structure', 'skeletons', 'fill'.
            data: Phase-specific data (spec, files, progress).

        Returns:
            Formatted SSE event.
        """
        event_name = self._config.fractal_phase_events.get(
            phase, f"fractal_{phase}"
        )
        return self.format_event(event_name, data)

    async def stream_orchestrator_result(
        self,
        result: Dict[str, Any],
        body: Dict[str, Any],
        detection_result: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a complete orchestrator result as SSE chunks.

        Breaks the result into logical chunks for progressive rendering
        in Open Design's iframe. Code content is streamed character-by-character
        for the typing effect; metadata is sent as a single chunk.

        Args:
            result: Orchestrator result dict.
            body: Original request body.
            detection_result: Open Design detection result.

        Yields:
            SSE-formatted strings.
        """
        # Extract content from the result (same as build_normal_response)
        content_parts = self._build_content_parts(result)
        full_content = "\n".join(content_parts)

        # If artifact wrapping is needed, wrap the content
        if detection_result and (detection_result.get("is_open_design")
                                  or detection_result.get("is_visual_request")):
            from .artifact_builder import ArtifactBuilder
            full_content = ArtifactBuilder.wrap_response_content(
                full_content, detection_result,
                language=result.get("ast_analysis", {}).get("language", "html"),
            )

        # Stream content in chunks for progressive rendering
        chunk_size = 4  # Characters per chunk (typing effect)
        for i in range(0, len(full_content), chunk_size):
            chunk_text = full_content[i:i + chunk_size]
            yield self.format_chunk(chunk_text)
            # Small delay for natural typing feel
            if self._config.sse_chunk_delay_s > 0:
                import asyncio
                await asyncio.sleep(self._config.sse_chunk_delay_s)

        # Final chunk with finish_reason
        yield self.format_chunk("", finish_reason="stop")
        yield self.format_done()

    def stream_orchestrator_result_sync(
        self,
        result: Dict[str, Any],
        body: Dict[str, Any],
        detection_result: Optional[Dict[str, Any]] = None,
    ) -> Iterator[str]:
        """
        Synchronous version of stream_orchestrator_result.

        Used by the stdlib HTTP server which doesn't support async.
        """
        content_parts = self._build_content_parts(result)
        full_content = "\n".join(content_parts)

        # Artifact wrapping
        if detection_result and (detection_result.get("is_open_design")
                                  or detection_result.get("is_visual_request")):
            from .artifact_builder import ArtifactBuilder
            full_content = ArtifactBuilder.wrap_response_content(
                full_content, detection_result,
                language=result.get("ast_analysis", {}).get("language", "html"),
            )

        # Stream in chunks
        chunk_size = 8  # Larger chunks for sync (no async delay)
        for i in range(0, len(full_content), chunk_size):
            chunk_text = full_content[i:i + chunk_size]
            yield self.format_chunk(chunk_text)

        # Final chunk
        yield self.format_chunk("", finish_reason="stop")
        yield self.format_done()

    def _build_content_parts(self, result: Dict[str, Any]) -> List[str]:
        """Build content parts from orchestrator result (mirrors response_builder)."""
        parts = [f"TITAN OMNISCALE X v16 - {result.get('status', 'UNKNOWN')}"]

        if result.get("explanations"):
            for exp in result["explanations"]:
                parts.append(f"  {exp}")

        if result.get("code"):
            lang = result.get("ast_analysis", {}).get("language", "python")
            parts.append(f"\n```{lang}\n{result['code']}\n```")

        if result.get("warnings"):
            parts.append("\nWarnings:")
            for w in result["warnings"]:
                parts.append(f"  - {w}")

        return parts


def create_sse_response(streamer: SSEStreamer,
                         result: Dict[str, Any],
                         body: Dict[str, Any],
                         detection_result: Optional[Dict[str, Any]] = None):
    """
    Create a FastAPI StreamingResponse for SSE.

    Args:
        streamer: SSEStreamer instance.
        result: Orchestrator result.
        body: Request body.
        detection_result: Open Design detection result.

    Returns:
        FastAPI StreamingResponse with SSE content type.
    """
    try:
        from fastapi.responses import StreamingResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for SSE streaming. "
            "Install with: pip install fastapi uvicorn"
        )

    return StreamingResponse(
        streamer.stream_orchestrator_result(result, body, detection_result),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
