#!/usr/bin/env python3
"""
TITAN OMNISCALE X - Headless Server for Termux/proot-distro

Servidor OpenAI-Compatible SIN interfaz grafica. Disenado para correr en
Termux + proot-distro (Debian) en tu Redmi 12R Pro.

Uso:
  python3 main_headless.py                    # Modo interactivo
  python3 main_headless.py --port 5000        # Puerto custom
  python3 main_headless.py --ram-limit 4096   # Limite RAM en MB
  python3 main_headless.py --daemon           # Modo daemon (background)

Endpoints:
  GET  /v1/models           - Lista modelos disponibles
  POST /v1/chat/completions - Chat completion (OpenAI-compatible)
  GET  /health              - Status del motor + recursos
  GET  /                    - Info general
"""

import sys
import os
import time
import logging
import argparse
import signal
import threading

# ============================================================
#  INICIALIZACION - Antes de importar modulos pesados
# ============================================================

# Cargar .env ANTES de cualquier otro import (variables de entorno)
from src.core.env_loader import load_env
load_env()

from src.core.shared.resource_governor import (
    tune_gc_for_arm, set_process_priority_low,
    limit_open_files, init_governor,
)

tune_gc_for_arm()
set_process_priority_low()
limit_open_files()

# Importar modulos del engine
from src.core.shared.contracts import HAS_Z3
from src.core.shared.db_initializer import initialize_databases
from src.core.shared._version import TITAN_VERSION_STR, TITAN_FULL_NAME

# Use DAGOrchestrator as primary, with TitanOrchestrator as fallback
try:
    from src.core.dag_orchestrator import DAGOrchestrator
    _ORCHESTRATOR_CLASS = DAGOrchestrator
    _ORCHESTRATOR_NAME = f"DAGOrchestrator ({TITAN_VERSION_STR})"
except ImportError:
    from src.core.orchestrator import TitanOrchestrator
    _ORCHESTRATOR_CLASS = TitanOrchestrator
    _ORCHESTRATOR_NAME = f"TitanOrchestrator ({TITAN_VERSION_STR})"

from src.server import (
    TitanHTTPHandler, ThreadedHTTPServer,
    get_local_ip, configure_handler, RateLimiter,
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TITAN")


# ============================================================
#  BANNER
# ============================================================

def print_banner(ip, port, solver_name, governor, server_type="HYBRID MODE"):
    """Imprime el banner de inicio en la terminal."""
    res = governor.get_status() if governor else {}
    idle_min = int(os.environ.get("TITAN_MODEL_IDLE_TIMEOUT", "300")) // 60
    ram_budget = os.environ.get("TITAN_RAM_BUDGET_MB", "3072")
    auto_unload = "ON" if os.environ.get("TITAN_AUTO_UNLOAD", "1") == "1" else "OFF"
    rl_concurrent = os.environ.get("TITAN_RATE_LIMIT_CONCURRENT", "60")
    banner = f"""
+==============================================================+
|  TITAN OMNISCALE X {TITAN_VERSION_STR} - HEADLESS SERVER [{server_type}]    
|  Motor de IA Quirurgico Local ({solver_name})                   
+==============================================================+
|                                                              |
|  Conecta Cline/Aide/OpenCode a:                              |
|  http://{ip}:{port}/v1                                       |
|                                                              |
|  Endpoints:                                                  |
|    GET  /v1/models        - Modelos disponibles              |
|    POST /v1/chat/completions - Chat completion               |
|    GET  /health           - Status + recursos                |
|                                                              |
|  Recursos (Hybrid Lazy Loading):                             |
|    Solver: {solver_name} | MCTS: ARM-optimized                  |
|    RAM: {res.get('ram_usage_mb', 0):.0f}MB / {res.get('ram_limit_mb', '?')}MB limite           |
|    Models: Lazy (se cargan al primer request)               |
|    Auto-unload: {auto_unload} ({idle_min} min idle) | Budget: {ram_budget}MB           |
|    Rate limit: {rl_concurrent} concurrent | GC tuned for ARM        |
|    Priority: low                                             |
|                                                              |
|  Ctrl+C para detener                                         |
+==============================================================+
"""
    print(banner)


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

START_TIME = time.time()


def main():
    parser = argparse.ArgumentParser(
        description=f"TITAN OMNISCALE X {TITAN_VERSION_STR} - Headless Server"
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
        '--ram-limit', type=int, default=4096,
        help='Limite RAM en MB (default: 4096)'
    )
    parser.add_argument(
        '--daemon', action='store_true',
        help='Correr como daemon (background)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Modo debug con logs verbose'
    )
    parser.add_argument(
        '--server', type=str, default='stdlib',
        choices=['stdlib', 'fastapi'],
        help='Tipo de servidor: stdlib (legacy) o fastapi (SaaS)'
    )
    parser.add_argument(
        '--auth', action='store_true',
        help='Habilitar autenticacion (requiere fastapi server)'
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Inicializar Resource Governor
    governor = init_governor(ram_limit_mb=args.ram_limit)

    # Inicializar bases de datos
    initialize_databases()

    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info(f"{TITAN_FULL_NAME} - Headless Server")
    logger.info(f"Solver: {solver_name} | MCTS Adaptive | Symbolic Exec | Resource Governor")
    logger.info(f"RAM limit: {args.ram_limit}MB | GC tuned for ARM | Process priority: low")

    # Crear orchestrator (DAGOrchestrator preferred)
    # Con HYBRID MODE: los modelos se cargan lazy al primer request
    orchestrator = _ORCHESTRATOR_CLASS()
    logger.info(f"Orchestrator: {_ORCHESTRATOR_NAME} [HYBRID MODE]")

    # Conectar governor con ModelManager para model swap
    if hasattr(orchestrator, '_model_mgr'):
        governor.set_model_manager(orchestrator._model_mgr)

    # ── Precarga de modelos ──
    # Cargar modelos ANTES de empezar a servir requests para evitar
    # TimeoutError en el primer request (Qwen ~400MB + SemanticEngine ~150MB)
    preload = os.environ.get("TITAN_PRELOAD_MODELS", "1") == "1"
    if preload and hasattr(orchestrator, '_model_mgr'):
        logger.info("Preloading AI models (avoid first-request timeout)...")
        try:
            _mgr = orchestrator._model_mgr
            # Trigger lazy-load for both models
            t0 = time.time()
            _ = _mgr.semantic_engine   # loads ~150MB
            t1 = time.time()
            logger.info(f"  SemanticEngine loaded in {t1-t0:.1f}s")
            _ = _mgr.mini_ai_engine    # loads ~400MB (Qwen)
            t2 = time.time()
            logger.info(f"  MiniAIEngine loaded in {t2-t1:.1f}s")
            logger.info(f"All models ready ({t2-t0:.1f}s total)")
        except Exception as e:
            logger.warning(f"Model preload failed (will lazy-load on first request): {e}")
    else:
        logger.info("Model preload disabled (TITAN_PRELOAD_MODELS=0)")

    # Crear AuthService si --auth o --server fastapi
    auth_service = None
    if args.auth or args.server == 'fastapi':
        try:
            from src.core.auth_service import AuthService
            auth_service = AuthService()
            # Ensure admin exists
            auth_service.ensure_admin()
            logger.info("AuthService: initialized with tenant support")
        except Exception as e:
            logger.warning(f"AuthService init failed (auth disabled): {e}")
            auth_service = None

    # Crear rate limiter con soporte tenant si auth habilitado
    # Configurable via env vars for Cline and other tools that send rapid requests
    _rl_rpm = int(os.environ.get("TITAN_RATE_LIMIT_RPM", str(max(1, args.ram_limit // 64))))
    _rl_burst = int(os.environ.get("TITAN_RATE_LIMIT_BURST", "20"))
    _rl_concurrent = int(os.environ.get("TITAN_RATE_LIMIT_CONCURRENT", "60"))
    if auth_service is not None:
        try:
            from src.server.tenant_rate_limiter import TenantRateLimiter
            rate_limiter = TenantRateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
                default_user_rpm=_rl_rpm,
                default_user_burst=_rl_burst,
            )
        except ImportError:
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
    else:
        rate_limiter = RateLimiter(
            max_requests_per_minute=_rl_rpm,
            burst_size=_rl_burst,
            global_max_concurrent=_rl_concurrent,
        )

    # Configurar handler compartido con governor + rate limiter
    configure_handler(orchestrator, governor=governor,
                      start_time=START_TIME, platform_tag="termux-proot",
                      rate_limiter=rate_limiter)

    # Obtener IP
    ip = get_local_ip()

    # ── FastAPI Server Mode ────────────────────────────────
    if args.server == 'fastapi':
        try:
            from src.server.fastapi_app import run_fastapi_server
        except ImportError:
            logger.error("FastAPI no instalado. Instala con: pip install fastapi uvicorn")
            logger.error("Usa --server stdlib para el servidor legacy")
            sys.exit(1)

        print_banner(ip, args.port, solver_name, governor, server_type="FastAPI (SaaS)")
        logger.info("Server mode: FastAPI (SaaS-ready) | Auth: %s",
                    "enabled" if auth_service else "disabled")

        # Run FastAPI server (blocking)
        try:
            run_fastapi_server(
                orchestrator=orchestrator,
                host=args.host,
                port=args.port,
                auth_service=auth_service,
                rate_limiter=rate_limiter,
                governor=governor,
                platform_tag="termux-proot",
            )
        except KeyboardInterrupt:
            governor.stop_monitoring()
            logger.info("Server stopped.")
        return

    # ── Stdlib Server Mode (legacy) ────────────────────────

    # Banner
    print_banner(ip, args.port, solver_name, governor)

    # Crear servidor
    try:
        server = ThreadedHTTPServer((args.host, args.port), TitanHTTPHandler)
    except OSError as e:
        logger.error(f"No se pudo iniciar el servidor: {e}")
        logger.error(f"Puerto {args.port} en uso? Intenta: --port 5001")
        sys.exit(1)

    # Signal handler para shutdown limpio
    def shutdown_handler(signum, frame):
        logger.info("Shutting down gracefully...")
        governor.stop_monitoring()
        server.shutdown()
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
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
                        # Model status
                        if hasattr(orchestrator, '_model_mgr'):
                            ms = orchestrator._model_mgr.get_status()
                            for name, info in ms.get('models', {}).items():
                                print(f"  {name}: {info['status']}" + (f" (idle {info.get('idle_s', 0)}s)" if 'idle_s' in info else ""))
                    elif cmd.lower() == 'models':
                        if hasattr(orchestrator, '_model_mgr'):
                            ms = orchestrator._model_mgr.stats
                            print(f"  SemanticEngine: {'LOADED' if ms['semantic_loaded'] else 'UNLOADED'} (loads={ms['semantic_loads']}, unloads={ms['semantic_unloads']})")
                            print(f"  MiniAIEngine:  {'LOADED' if ms['ai_loaded'] else 'UNLOADED'} (loads={ms['ai_loads']}, unloads={ms['ai_unloads']})")
                            print(f"  Auto-unloads: {ms['auto_unloads']} | RAM: {ms['current_ram_mb']}MB")
                        else:
                            print("  ModelManager not available")
                    elif cmd.lower() == 'help':
                        print("  Commands: status | models | quit | help")
                except EOFError:
                    break
        except KeyboardInterrupt:
            pass

        governor.stop_monitoring()
        server.shutdown()
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
        logger.info("Server stopped.")


if __name__ == '__main__':
    main()
