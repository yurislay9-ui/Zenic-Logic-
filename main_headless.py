#!/usr/bin/env python3
"""
TITAN OMNISCALE X v13 - Headless Server for Termux/proot-distro

Servidor OpenAI-Compatible SIN Kivy. Diseñado para correr en
Termux + proot-distro (Debian) en tu Redmi 12R Pro.

Uso:
  python3 main_headless.py                    # Modo interactivo
  python3 main_headless.py --port 5000        # Puerto custom
  python3 main_headless.py --ram-limit 2048   # Limite RAM en MB
  python3 main_headless.py --daemon           # Modo daemon (background)

Endpoints:
  GET  /v1/models           - Lista modelos disponibles
  POST /v1/chat/completions - Chat completion (OpenAI-compatible)
  GET  /health              - Status del motor + recursos
  GET  /                    - Info general
"""

import json
import os
import sys
import time
import uuid
import threading
import socket
import logging
import argparse
import signal
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ============================================================
#  INICIALIZACION - Antes de importar modulos pesados
# ============================================================

# Tunear GC para ARM antes de cargar nada
from src.core.shared.resource_governor import (
    tune_gc_for_arm, set_process_priority_low,
    limit_open_files, init_governor, get_governor
)

tune_gc_for_arm()
set_process_priority_low()
limit_open_files()

# Ahora importar los modulos del engine
from src.core.shared.contracts import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
    IntentPayload, RoutingPayload, PlanStep, ExecutionPlan,
    SandboxResult, MerkleNode, ChatMessage, ChatRequest,
    MCTSNode, MCTSPlanner, ConstraintSolver, Constraint,
    TimeoutEnforcer, CodeConstraintBuilder, Z3Solver, HAS_Z3,
    SymbolicExecutor, KPathAnalyzer
)
from src.core.shared.db_initializer import (
    initialize_databases, get_data_dir, get_db_path, get_projects_dir
)
from src.core.level1_semantic_engine.parser import SemanticParser
from src.core.level2_macro_router.router import MacroRouter
from src.core.level3_graph_ast.engine import GraphASTEngine
from src.core.level4_apa_planner.planner import APAPlanner
from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache
from src.core.orchestrator import TitanOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TITAN")


# ============================================================
#  SERVIDOR HTTP OPENAI-COMPATIBLE (Sin Kivy)
# ============================================================

class TitanHTTPHandler(BaseHTTPRequestHandler):
    """Handler HTTP compatible con la API de OpenAI."""

    orchestrator = None
    governor = None

    def log_message(self, format, *args):
        logger.info("HTTP: %s", format % args)

    def do_GET(self):
        if self.path == '/v1/models':
            self._send_json({
                "object": "list",
                "data": [{"id": "titan-omniscale-x", "object": "model",
                          "created": int(time.time()), "owned_by": "titan-local"}]
            })
        elif self.path == '/':
            solver_name = "Z3" if HAS_Z3 else "AC-3"
            gov = self.governor
            res_status = gov.get_status() if gov else {}
            self._send_json({
                "status": "active",
                "model": "titan-omniscale-x",
                "version": "13.0-headless",
                "endpoints": ["/v1/chat/completions", "/v1/models", "/health"],
                "pipeline_levels": 8,
                "solver": solver_name,
                "platform": "termux-proot",
                "resources": res_status,
                "features": ["MCTS", f"{solver_name}_Solver", "Timeout_Enforcement",
                             "Theorem_Cache", "Skeleton_Hash", "K_Path_Limiting",
                             "Symbolic_Execution", "Abortive_Protocol",
                             "Partial_Reasoning", "Contextual_CodeGen",
                             "Resource_Governor"],
                "description": f"TITAN OMNISCALE X v13 - Headless ({solver_name}) for Termux"
            })
        elif self.path == '/health':
            gov = self.governor
            solver_name = "Z3" if HAS_Z3 else "AC-3"
            health = {
                "status": "healthy",
                "solver": solver_name,
                "has_z3": HAS_Z3,
                "uptime_s": int(time.time() - START_TIME) if 'START_TIME' in dir() else 0,
            }
            if gov:
                health["resources"] = gov.get_status()
                # Marcar unhealthy si RAM critica
                if gov.is_ram_critical():
                    health["status"] = "degraded"
                    health["reason"] = f"RAM critical: {gov._ram_usage_mb:.0f}MB"
            self._send_json(health)
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        if self.path == '/v1/chat/completions':
            self._handle_chat_completions()
        else:
            self._send_json({"error": "Not found"}, status=404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _handle_chat_completions(self):
        # Pre-request: preparar recursos
        gov = self.governor
        if gov:
            gov.pre_request()
            # Rechazar si RAM critica
            if gov.is_ram_critical():
                self._send_json({
                    "error": {"message": "Server overloaded - RAM critical. Retry later.",
                              "type": "server_overloaded"}
                }, status=503)
                return

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": {"message": f"Invalid JSON: {str(e)}",
                "type": "invalid_request_error"}}, status=400)
            return

        messages = data.get("messages", [])
        if not messages:
            self._send_json({"error": {"message": "No messages provided",
                "type": "invalid_request_error"}}, status=400)
            return

        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        if not user_msg:
            self._send_json({"error": {"message": "No user message found",
                "type": "invalid_request_error"}}, status=400)
            return

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.orchestrator.execute(user_msg))
            loop.close()

            # Razonamiento Parcial
            if result.get("partial_reasoning"):
                response = self._build_partial_reasoning_response(data, result, user_msg)
                self._send_json(response)
                return

            # Respuesta Normal
            content_parts = [f"TITAN OMNISCALE X v13 - {result['status']}"]

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
                content_parts.append(f"\nCache hit: {result['cache_source']} (hits: {result.get('cache_hits', 0)})")

            solver_status = result.get('solver_status', 'N/A')
            mcts_sims = result.get('mcts_simulations', 0)
            mcts_depth = result.get('mcts_depth_reached', 0)
            paths_explored = result.get('paths_explored', 0)
            paths_pruned = result.get('paths_pruned', 0)

            solver_name = "Z3" if HAS_Z3 else "AC-3"
            meta_parts = [
                f"\nTime: {result.get('processing_time_ms', 0)}ms",
                f"Route: {result.get('route', 'N/A')}",
                f"Hash: {result.get('hash', 'N/A')}",
                f"Solver({solver_name}): {solver_status}",
                f"MCTS: {mcts_sims} sims, depth {mcts_depth}",
            ]
            if paths_explored:
                meta_parts.append(f"Paths: {paths_explored} explored, {paths_pruned} pruned")

            # Agregar info de recursos
            if gov:
                res = gov.get_status()
                meta_parts.append(f"RAM: {res['ram_usage_mb']}MB/{res['ram_limit_mb']}MB")
                meta_parts.append(f"CPU: {res['cpu_usage_pct']}%")

            content_parts.append(" | ".join(meta_parts))
            response_content = "\n".join(content_parts)

            response = {
                "id": f"titan-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": data.get("model", "titan-omniscale-x"),
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": response_content},
                    "finish_reason": "stop"}],
                "usage": {"prompt_tokens": len(user_msg.split()),
                    "completion_tokens": len(response_content.split()),
                    "total_tokens": len(user_msg.split()) + len(response_content.split())},
                "titan_metadata": {
                    "status": result["status"],
                    "hash": result.get("hash", "N/A"),
                    "processing_time_ms": result.get("processing_time_ms", 0),
                    "route": result.get("route", ""),
                    "criticality": result.get("criticality", 0),
                    "solver_type": solver_name,
                    "solver_status": solver_status,
                    "solver_proof": result.get("solver_proof"),
                    "mcts_simulations": mcts_sims,
                    "mcts_depth_reached": mcts_depth,
                    "cache_hit": bool(result.get("cache_source")),
                    "paths_explored": paths_explored,
                    "paths_pruned": paths_pruned,
                    "symbolic_execution": True,
                    "platform": "termux-proot",
                }
            }
            self._send_json(response)

        except Exception as e:
            logger.error("Error processing request: %s", e, exc_info=True)

            error_content = f"TITAN OMNISCALE X v13 - Internal Error\n{str(e)}\n\nTry reformulating your request."

            self._send_json({
                "id": f"titan-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "titan-omniscale-x",
                "choices": [{"index": 0, "message": {
                    "role": "assistant",
                    "content": error_content},
                    "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        finally:
            if gov:
                gov.post_request()

    def _build_partial_reasoning_response(self, data, result, user_msg):
        partial = result.get("partial_reasoning_payload", {})
        response = {
            "id": f"titan-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", "titan-omniscale-x"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": partial.get("content", result.get("explanations", [""])[0] if result.get("explanations") else ""),
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
        return response

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._set_cors_headers()
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ============================================================
#  FUNCIONES AUXILIARES
# ============================================================

def get_ip():
    """Obtiene la IP local del telefono."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def print_banner(ip, port, solver_name, governor):
    """Imprime el banner de inicio en la terminal."""
    res = governor.get_status() if governor else {}
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║  TITAN OMNISCALE X v13 - HEADLESS SERVER                   ║
║  Motor de IA Quirurgico Local ({solver_name})                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Conecta Cline/Aide/OpenCode a:                              ║
║  http://{ip}:{port}/v1                                       ║
║                                                              ║
║  Endpoints:                                                  ║
║    GET  /v1/models        - Modelos disponibles              ║
║    POST /v1/chat/completions - Chat completion               ║
║    GET  /health           - Status + recursos                ║
║                                                              ║
║  Recursos:                                                   ║
║    Solver: {solver_name} | MCTS: adaptativo                    ║
║    RAM: {res.get('ram_usage_mb', 0):.0f}MB / {res.get('ram_limit_mb', '?')}MB limite           ║
║    GC tuned for ARM | Priority: low                          ║
║                                                              ║
║  Ctrl+C para detener                                         ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

START_TIME = time.time()

def main():
    parser = argparse.ArgumentParser(
        description="TITAN OMNISCALE X v13 - Headless Server"
    )
    parser.add_argument(
        '--port', type=int, default=5000,
        help='Puerto del servidor (default: 5000)'
    )
    parser.add_argument(
        '--host', type=str, default='0.0.0.0',
        help='Host para bind (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--ram-limit', type=int, default=2048,
        help='Limite RAM en MB (default: 2048)'
    )
    parser.add_argument(
        '--daemon', action='store_true',
        help='Correr como daemon (background)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Modo debug con logs verbose'
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Inicializar Resource Governor
    governor = init_governor(ram_limit_mb=args.ram_limit)

    # Inicializar bases de datos
    initialize_databases()

    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info("TITAN OMNISCALE X v13.0 - Headless Server")
    logger.info(f"Solver: {solver_name} | MCTS Adaptive | Symbolic Exec | Resource Governor")
    logger.info(f"RAM limit: {args.ram_limit}MB | GC tuned for ARM | Process priority: low")

    # Crear orchestrator
    orchestrator = TitanOrchestrator()

    # Configurar handler
    TitanHTTPHandler.orchestrator = orchestrator
    TitanHTTPHandler.governor = governor

    # Obtener IP
    ip = get_ip()

    # Banner
    print_banner(ip, args.port, solver_name, governor)

    # Crear servidor
    try:
        server = ThreadedHTTPServer((args.host, args.port), TitanHTTPHandler)
    except OSError as e:
        logger.error(f"No se pudo iniciar el servidor: {e}")
        logger.error(f"¿Puerto {args.port} en uso? Intenta: --port 5001")
        sys.exit(1)

    # Signal handler para shutdown limpio
    def shutdown_handler(signum, frame):
        logger.info("Shutting down gracefully...")
        governor.stop_monitoring()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Modo daemon
    if args.daemon:
        logger.info("Running as daemon on port %d", args.port)
        server.serve_forever()
    else:
        # Modo interactivo - servir en thread, mantener terminal activa
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        logger.info(f"Server listening on http://{ip}:{args.port}")

        # Loop interactivo simple
        try:
            while True:
                try:
                    cmd = input("").strip()
                    if cmd.lower() in ('quit', 'exit', 'q', 'stop'):
                        break
                    elif cmd.lower() == 'status':
                        status = governor.get_status()
                        print(f"  CPU: {status['cpu_usage_pct']}% | RAM: {status['ram_usage_mb']}MB/{status['ram_limit_mb']}MB")
                        print(f"  Throttle: {status['thermal_throttle']} | MCTS: {status['adaptive_mcts_sims']} sims")
                        print(f"  Requests: {status['stats']['requests_served']} | GC forced: {status['stats']['gc_forced']}")
                    elif cmd.lower() == 'help':
                        print("  Commands: status | quit | help")
                except EOFError:
                    break
        except KeyboardInterrupt:
            pass

        governor.stop_monitoring()
        server.shutdown()
        logger.info("Server stopped.")


if __name__ == '__main__':
    main()
