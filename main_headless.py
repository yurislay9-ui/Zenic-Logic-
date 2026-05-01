#!/usr/bin/env python3
"""
TITAN OMNISCALE X v13 - Headless Server for Termux/proot-distro

Servidor OpenAI-Compatible SIN Kivy. Disenado para correr en
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

import sys
import time
import logging
import argparse
import signal
import threading

# ============================================================
#  INICIALIZACION - Antes de importar modulos pesados
# ============================================================

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
from src.core.orchestrator import TitanOrchestrator
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

def print_banner(ip, port, solver_name, governor):
    """Imprime el banner de inicio en la terminal."""
    res = governor.get_status() if governor else {}
    banner = f"""
+==============================================================+
|  TITAN OMNISCALE X v13 - HEADLESS SERVER                     |
|  Motor de IA Quirurgico Local ({solver_name})                   |
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
|  Recursos:                                                   |
|    Solver: {solver_name} | MCTS: adaptativo                    |
|    RAM: {res.get('ram_usage_mb', 0):.0f}MB / {res.get('ram_limit_mb', '?')}MB limite           |
|    GC tuned for ARM | Priority: low                          |
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

    # Crear rate limiter (proteccion contra flood en ARM)
    rate_limiter = RateLimiter(
        max_requests_per_minute=args.ram_limit // 64,  # ~32 RPM for 2048MB
        burst_size=10,
        global_max_concurrent=20,
    )

    # Configurar handler compartido con governor + rate limiter
    configure_handler(orchestrator, governor=governor,
                      start_time=START_TIME, platform_tag="termux-proot",
                      rate_limiter=rate_limiter)

    # Obtener IP
    ip = get_local_ip()

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
