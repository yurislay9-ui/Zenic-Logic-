"""
TITAN OMNISCALE X v16 - Response Builder

Construye respuestas OpenAI-compatible para el servidor HTTP.
Centraliza el formateo de respuestas normales, partial reasoning y errores,
eliminando la duplicacion entre main.py (Kivy) y main_headless.py (Termux).
"""

import time
import uuid

from src.core.shared.contracts import HAS_Z3


def _solver_name():
    """Retorna el nombre del solver activo."""
    return "Z3" if HAS_Z3 else "AC-3"


def build_normal_response(data, result, user_msg, governor=None):
    """
    Construye la respuesta OpenAI-compatible para un resultado normal del pipeline.

    Args:
        data: JSON original de la peticion del cliente
        result: Dict resultado del TitanOrchestrator.execute()
        user_msg: Mensaje del usuario (str)
        governor: ResourceGovernor opcional (headless mode)

    Returns:
        Dict con la respuesta OpenAI-compatible
    """
    content_parts = [f"TITAN OMNISCALE X v16 - {result['status']}"]

    if result.get("explanations"):
        for exp in result["explanations"]:
            content_parts.append(f"  {exp}")

    if result.get("code"):
        lang = result.get("ast_analysis", {}).get("language", "python")
        content_parts.append(f"\n```{lang}\n{result['code']}\n```")

    if result.get("warnings"):
        content_parts.append("\nWarnings:")
        for w in result["warnings"]:
            content_parts.append(f"  - {w}")

    if result.get("cache_source"):
        content_parts.append(
            f"\nCache hit: {result['cache_source']} (hits: {result.get('cache_hits', 0)})"
        )

    # Metadata del solver y MCTS
    solver_status = result.get('solver_status', 'N/A')
    mcts_sims = result.get('mcts_simulations', 0)
    mcts_depth = result.get('mcts_depth_reached', 0)
    paths_explored = result.get('paths_explored', 0)
    paths_pruned = result.get('paths_pruned', 0)

    sname = _solver_name()
    meta_parts = [
        f"\nTime: {result.get('processing_time_ms', 0)}ms",
        f"Route: {result.get('route', 'N/A')}",
        f"Hash: {result.get('hash', 'N/A')}",
        f"Solver({sname}): {solver_status}",
        f"MCTS: {mcts_sims} sims, depth {mcts_depth}",
    ]
    if paths_explored:
        meta_parts.append(f"Paths: {paths_explored} explored, {paths_pruned} pruned")

    # Info de recursos si governor disponible (headless mode)
    if governor:
        res = governor.get_status()
        meta_parts.append(f"RAM: {res['ram_usage_mb']}MB/{res['ram_limit_mb']}MB")
        meta_parts.append(f"CPU: {res['cpu_usage_pct']}%")

    content_parts.append(" | ".join(meta_parts))
    response_content = "\n".join(content_parts)

    titan_metadata = {
        "status": result["status"],
        "hash": result.get("hash", "N/A"),
        "processing_time_ms": result.get("processing_time_ms", 0),
        "route": result.get("route", ""),
        "criticality": result.get("criticality", 0),
        "solver_type": sname,
        "solver_status": solver_status,
        "solver_proof": result.get("solver_proof"),
        "mcts_simulations": mcts_sims,
        "mcts_depth_reached": mcts_depth,
        "cache_hit": bool(result.get("cache_source")),
        "paths_explored": paths_explored,
        "paths_pruned": paths_pruned,
        "symbolic_execution": True,
    }
    if governor:
        titan_metadata["platform"] = "termux-proot"

    return {
        "id": f"titan-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "titan-omniscale-x"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_content
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": len(response_content.split()),
            "total_tokens": len(user_msg.split()) + len(response_content.split()),
        },
        "titan_metadata": titan_metadata,
    }


def build_partial_reasoning_response(data, result, user_msg):
    """
    Construye la respuesta de Razonamiento Parcial con tool_calls.

    El payload JSON incluye tool_calls para que el cliente (Cline/Aide)
    pueda continuar la operacion subdividida.

    Args:
        data: JSON original de la peticion del cliente
        result: Dict resultado del TitanOrchestrator con partial_reasoning
        user_msg: Mensaje del usuario (str)

    Returns:
        Dict con la respuesta OpenAI-compatible con tool_calls
    """
    partial = result.get("partial_reasoning_payload", {})

    return {
        "id": f"titan-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "titan-omniscale-x"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": partial.get(
                    "content",
                    result.get("explanations", [""])[0] if result.get("explanations") else ""
                ),
                "tool_calls": partial.get("tool_calls", []),
            },
            "finish_reason": partial.get("finish_reason", "tool_calls"),
        }],
        "usage": result.get("usage_metadata", {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": 0,
            "total_tokens": len(user_msg.split()),
        }),
        "titan_metadata": {
            "status": "PARTIAL_REASONING",
            "processing_time_ms": result.get("processing_time_ms", 0),
            "route": result.get("route", ""),
            "criticality": result.get("criticality", 0),
            "solver_status": result.get("solver_status", ""),
            "paths_explored": result.get("paths_explored", 0),
            "paths_pruned": result.get("paths_pruned", 0),
            "partial_reasoning": True,
        }
    }


def build_error_response(error_msg):
    """
    Construye la respuesta de error interno compatible con OpenAI.

    Args:
        error_msg: Mensaje de error (str)

    Returns:
        Dict con la respuesta OpenAI-compatible de error
    """
    error_content = (
        f"TITAN OMNISCALE X v16 - Internal Error\n"
        f"{error_msg}\n\nTry reformulating your request."
    )
    return {
        "id": f"titan-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "titan-omniscale-x",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": error_content
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_overloaded_response():
    """
    Construye la respuesta de servidor sobrecargado (503).

    Returns:
        Dict con la respuesta de error 503
    """
    return {
        "error": {
            "message": "Server overloaded - RAM critical. Retry later.",
            "type": "server_overloaded"
        }
    }
