#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  TITAN OMNISCALE X v18 — MOTOR DE DIAGNOSTICO COMPLETO         ║
║  Logger Debug Engine para Termux                                ║
║                                                                  ║
║  Intercepta TODOS los puntos criticos del sistema:              ║
║    - Ciclo de vida del request HTTP (entrada → salida)          ║
║    - Carga/descarga de modelos (MiniAI + Semantic)              ║
║    - Veredicto engine (consensus, LLM calls, circuit breaker)   ║
║    - Resource Governor (RAM, CPU, thermal, GC)                  ║
║    - ModelManager (lazy load, auto-unload, RAM pressure)        ║
║    - Orchestrator pipeline (8 niveles)                          ║
║    - ThreadPoolExecutors (creacion, shutdown, submit)           ║
║    - Thread lifecycle (creacion, muerte, daemon)                ║
║    - Excepciones silenciosas (swallowed, logged as debug)       ║
║    - Signal handlers (SIGINT, SIGTERM)                          ║
║    - Async event loop (run_in_executor, tasks)                  ║
║                                                                  ║
║  USO:                                                            ║
║    python3 logger_debug.py                    # Modo completo    ║
║    python3 logger_debug.py --fast             # Solo FastAPI     ║
║    python3 logger_debug.py --stdlib           # Solo stdlib      ║
║    python3 logger_debug.py --port 5001        # Puerto custom    ║
║    python3 logger_debug.py --no-preload       # Sin precarga     ║
║                                                                  ║
║  El log se guarda en:                                            ║
║    ./titan_debug_<timestamp>.log                                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import logging
import argparse
import signal
import threading
import traceback
import gc
import atexit
import concurrent.futures
import json
import inspect
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# ════════════════════════════════════════════════════════════════════
#  CONFIGURACION DEL SISTEMA DE LOGGING
# ════════════════════════════════════════════════════════════════════

_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          f"titan_debug_{_TIMESTAMP}.log")

# Colores ANSI para Termux
class C:
    """ANSI color codes for terminal output."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BG_RED  = "\033[41m"
    BG_YEL  = "\033[43m"
    BG_CYAN = "\033[46m"

# Estadísticas globales de diagnóstico
class DiagStats:
    """Global diagnostic statistics tracker."""
    def __init__(self):
        self.start_time = time.time()
        self.requests_total = 0
        self.requests_completed = 0
        self.requests_failed = 0
        self.requests_timeout = 0
        self.model_loads = 0
        self.model_unloads = 0
        self.verdict_calls = 0
        self.verdict_fallbacks = 0
        self.executor_shutdowns = 0
        self.executor_creations = 0
        self.gc_forced = 0
        self.thermal_throttles = 0
        self.ram_critical_events = 0
        self.auto_unload_events = 0
        self.exceptions = []
        self.thread_creations = 0
        self.thread_deaths = 0
        self.signal_handlers_called = 0
        self.active_threads = {}
        self.pipeline_steps = []
        self.last_request_start = None
        self.last_request_end = None
        self._lock = threading.Lock()

    def record_exception(self, source: str, exc: Exception, context: str = ""):
        with self._lock:
            self.exceptions.append({
                "time": time.time(),
                "source": source,
                "type": type(exc).__name__,
                "message": str(exc),
                "context": context,
                "traceback": traceback.format_exc(),
            })

    def summary(self) -> str:
        uptime = time.time() - self.start_time
        lines = [
            f"",
            f"{'='*70}",
            f"  RESUMEN DE DIAGNOSTICO — TITAN OMNISCALE X v18",
            f"{'='*70}",
            f"  Uptime: {uptime:.1f}s ({uptime/60:.1f} min)",
            f"  Requests: {self.requests_total} total, {self.requests_completed} ok, {self.requests_failed} fail, {self.requests_timeout} timeout",
            f"  Model loads: {self.model_loads} | Unloads: {self.model_unloads}",
            f"  Verdict calls: {self.verdict_calls} | Fallbacks: {self.verdict_fallbacks}",
            f"  Executor creations: {self.executor_creations} | Shutdowns: {self.executor_shutdowns}",
            f"  GC forced: {self.gc_forced} | Thermal throttles: {self.thermal_throttles}",
            f"  RAM critical events: {self.ram_critical_events}",
            f"  Auto-unload events: {self.auto_unload_events}",
            f"  Thread creations: {self.thread_creations} | Deaths tracked: {self.thread_deaths}",
            f"  Signal handlers called: {self.signal_handlers_called}",
            f"  Active threads: {threading.active_count()}",
            f"  Total exceptions captured: {len(self.exceptions)}",
            f"  Last request: start={self.last_request_start}, end={self.last_request_end}",
        ]

        if self.exceptions:
            lines.append(f"")
            lines.append(f"  ULTIMAS 5 EXCEPCIONES:")
            for exc in self.exceptions[-5:]:
                lines.append(f"    [{exc['type']}] {exc['source']}: {exc['message'][:100]}")
                if exc['context']:
                    lines.append(f"      Context: {exc['context'][:100]}")

        lines.append(f"{'='*70}")
        return "\n".join(lines)


# Instancia global
diag = DiagStats()


# ════════════════════════════════════════════════════════════════════
#  FORMATTER PERSONALIZADO PARA EL LOG DE DIAGNOSTICO
# ════════════════════════════════════════════════════════════════════

class DiagFormatter(logging.Formatter):
    """Formatter that adds diagnostic metadata to every log entry."""

    COLORS = {
        "DEBUG":    C.CYAN,
        "INFO":     C.GREEN,
        "WARNING":  C.YELLOW,
        "ERROR":    C.RED,
        "CRITICAL": C.MAGENTA,
    }

    def __init__(self, use_color=True, write_file=True):
        super().__init__()
        self.use_color = use_color
        self.write_file = write_file

    def format(self, record):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        logger_name = record.name

        # Thread info
        thread_name = threading.current_thread().name
        thread_id = threading.current_thread().ident

        # Active thread count
        active = threading.active_count()

        # RAM al momento del log
        ram_mb = _get_ram_mb()

        # Color
        if self.use_color:
            color = self.COLORS.get(level, "")
            reset = C.RESET
        else:
            color = ""
            reset = ""

        # Formato principal
        msg = (
            f"{ts} {color}[{level:8s}]{reset} "
            f"[{logger_name}] "
            f"[T:{thread_name}#{thread_id}] "
            f"[RAM:{ram_mb:.0f}MB] [Threads:{active}] "
            f"{record.getMessage()}"
        )

        # Extra fields
        extras = []
        for field in ["request_id", "pipeline_level", "trace_id", "tenant_id",
                       "processing_time_ms", "status", "source"]:
            value = getattr(record, field, None)
            if value is not None:
                extras.append(f"{field}={value}")
        if extras:
            msg += f" | {' '.join(extras)}"

        # Exception
        if record.exc_info and record.exc_info[0] is not None:
            exc_text = "".join(traceback.format_exception(*record.exc_info))
            msg += f"\n{exc_text}"

        return msg


class FileFormatter(logging.Formatter):
    """Plain text formatter for log file (no ANSI codes)."""

    def format(self, record):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname
        logger_name = record.name
        thread_name = threading.current_thread().name
        ram_mb = _get_ram_mb()
        active = threading.active_count()

        msg = (
            f"{ts} [{level:8s}] [{logger_name}] "
            f"[T:{thread_name}] [RAM:{ram_mb:.0f}MB] [Threads:{active}] "
            f"{record.getMessage()}"
        )

        if record.exc_info and record.exc_info[0] is not None:
            exc_text = "".join(traceback.format_exception(*record.exc_info))
            msg += f"\n{exc_text}"

        return msg


def _get_ram_mb() -> float:
    """Get current process RSS in MB."""
    try:
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) / 1024
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        pass
    return 0.0


def setup_diagnostic_logging(level=logging.DEBUG):
    """Configure the diagnostic logging system."""
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler with colors
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(DiagFormatter(use_color=True, write_file=True))
    root.addHandler(console)

    # File handler (plain text)
    file_handler = logging.FileHandler(_LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(FileFormatter())
    root.addHandler(file_handler)

    # Set ALL existing loggers to DEBUG
    for name in list(logging.Logger.manager.loggerDict.keys()):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = True

    return logging.getLogger("DIAG")


# ════════════════════════════════════════════════════════════════════
#  MONKEY-PATCHING: INTERCEPTAR TODOS LOS PUNTOS CRITICOS
# ════════════════════════════════════════════════════════════════════

log = None  # Will be initialized in main()


def patch_threadpool_executor():
    """Monkey-patch ThreadPoolExecutor to track all submit/shutdown calls."""
    original_submit = concurrent.futures.ThreadPoolExecutor.submit
    original_shutdown = concurrent.futures.ThreadPoolExecutor.shutdown
    original_init = concurrent.futures.ThreadPoolExecutor.__init__

    _tracked_executors = {}
    _executor_lock = threading.Lock()
    _executor_counter = [0]

    def patched_init(self, max_workers=None, *args, **kwargs):
        with _executor_lock:
            _executor_counter[0] += 1
            executor_id = _executor_counter[0]
            _tracked_executors[id(self)] = {
                "id": executor_id,
                "max_workers": max_workers,
                "created_at": time.time(),
                "created_from": "".join(traceback.format_stack()[-4:-1]),
                "submits": 0,
                "shutdown": False,
            }

        diag.executor_creations += 1
        log.warning(
            f"⚡ EXECUTOR CREADO #{executor_id} (max_workers={max_workers}) "
            f"— Thread: {threading.current_thread().name}"
        )
        log.debug(f"   Stack: {''.join(traceback.format_stack()[-4:-1])}")

        # Call original
        if max_workers is not None:
            original_init(self, max_workers=max_workers, *args, **kwargs)
        else:
            original_init(self, *args, **kwargs)

    def patched_submit(self, fn, *args, **kwargs):
        executor_info = _tracked_executors.get(id(self), {})
        executor_id = executor_info.get("id", "?")

        if executor_info.get("shutdown"):
            log.error(
                f"🔴 SUBMIT A EXECUTOR SHUTDOWN #{executor_id}! "
                f"fn={fn.__name__ if hasattr(fn, '__name__') else fn} — "
                f"Esto va a CRASHEAR con RuntimeError!"
            )
            log.error(f"   Executor fue cerrado en: {executor_info.get('shutdown_at', '?')}")
            log.error(f"   Creado desde: {executor_info.get('created_from', '?')[:200]}")

        with _executor_lock:
            if id(self) in _tracked_executors:
                _tracked_executors[id(self)]["submits"] += 1

        fn_name = fn.__name__ if hasattr(fn, '__name__') else str(fn)[:50]
        log.debug(
            f"📤 EXECUTOR SUBMIT #{executor_id} fn={fn_name} "
            f"(total submits: {executor_info.get('submits', 0) + 1})"
        )

        return original_submit(self, fn, *args, **kwargs)

    def patched_shutdown(self, wait=True, *, cancel_futures=False):
        executor_info = _tracked_executors.get(id(self), {})
        executor_id = executor_info.get("id", "?")

        with _executor_lock:
            if id(self) in _tracked_executors:
                _tracked_executors[id(self)]["shutdown"] = True
                _tracked_executors[id(self)]["shutdown_at"] = time.time()
                _tracked_executors[id(self)]["shutdown_from"] = "".join(traceback.format_stack()[-4:-1])

        diag.executor_shutdowns += 1
        log.warning(
            f"🔴 EXECUTOR SHUTDOWN #{executor_id} (wait={wait}) — "
            f"Submits totales: {executor_info.get('submits', 0)} — "
            f"Thread: {threading.current_thread().name}"
        )
        log.debug(f"   Shutdown llamado desde: {''.join(traceback.format_stack()[-4:-1])}")

        # Call original with compatible signature
        try:
            import inspect as _inspect
            sig = _inspect.signature(original_shutdown)
            params = list(sig.parameters.keys())
            if 'cancel_futures' in params:
                return original_shutdown(self, wait=wait, cancel_futures=cancel_futures)
            else:
                return original_shutdown(self, wait=wait)
        except Exception as e:
            log.warning(f"   Shutdown signature fallback: {e}")
            return original_shutdown(self, wait=wait)

    concurrent.futures.ThreadPoolExecutor.__init__ = patched_init
    concurrent.futures.ThreadPoolExecutor.submit = patched_submit
    concurrent.futures.ThreadPoolExecutor.shutdown = patched_shutdown

    log.info("✅ Monkey-patch: ThreadPoolExecutor interceptado")


def patch_threading():
    """Monkey-patch threading.Thread to track thread lifecycle."""
    original_init = threading.Thread.__init__
    original_start = threading.Thread.start
    original_join = threading.Thread.join

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        diag.thread_creations += 1
        creator = "".join(traceback.format_stack()[-4:-1])
        # NOTA: self.ident es None hasta que se llama a start()
        # Guardamos por nombre en vez de ident para evitar colisiones
        with diag._lock:
            diag.active_threads[id(self)] = {
                "name": self.name,
                "daemon": self.daemon,
                "ident": self.ident,  # None hasta start()
                "created_at": time.time(),
                "created_from": creator[:200],
            }
        log.debug(
            f"🧵 THREAD CREADO: {self.name} (daemon={self.daemon}) "
            f"— Thread activos: {threading.active_count()}"
        )

    def patched_start(self):
        log.debug(
            f"🧵 THREAD START: {self.name} "
            f"— Thread activos: {threading.active_count()}"
        )
        return original_start(self)

    def patched_join(self, timeout=None):
        log.debug(
            f"🧵 THREAD JOIN: {self.name} (timeout={timeout})"
        )
        result = original_join(self, timeout=timeout)
        if not self.is_alive():
            diag.thread_deaths += 1
            log.debug(f"🧵 THREAD MUERTO: {self.name}")
        return result

    threading.Thread.__init__ = patched_init
    threading.Thread.start = patched_start
    threading.Thread.join = patched_join

    log.info("✅ Monkey-patch: threading.Thread interceptado")


def patch_gc():
    """Monkey-patch gc.collect to track forced GC calls."""
    original_collect = gc.collect

    def patched_collect(generation=None):
        diag.gc_forced += 1
        ram_before = _get_ram_mb()
        caller = traceback.format_stack()[-2].strip()

        if generation is not None:
            result = original_collect(generation)
            log.warning(
                f"🗑️ GC COLLECT gen-{generation}: {result} objects freed — "
                f"RAM: {ram_before:.0f}MB → {_get_ram_mb():.0f}MB"
            )
        else:
            result = original_collect()
            log.warning(
                f"🗑️ GC COLLECT FULL: {result} objects freed — "
                f"RAM: {ram_before:.0f}MB → {_get_ram_mb():.0f}MB"
            )

        log.debug(f"   GC llamado desde: {caller[:150]}")
        return result

    gc.collect = patched_collect
    log.info("✅ Monkey-patch: gc.collect interceptado")


def patch_signal():
    """Monkey-patch signal.signal to track signal handler registration."""
    original_signal = signal.signal

    def patched_signal(signum, handler):
        sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        handler_name = handler.__name__ if hasattr(handler, '__name__') else str(handler)[:50]
        log.warning(
            f"📡 SIGNAL HANDLER REGISTRADO: {sig_name} → {handler_name}"
        )
        log.debug(f"   Registrado desde: {''.join(traceback.format_stack()[-3:-1])[:200]}")
        return original_signal(signum, handler)

    signal.signal = patched_signal
    log.info("✅ Monkey-patch: signal.signal interceptado")


# ════════════════════════════════════════════════════════════════════
#  PATCHES ESPECIFICOS DEL MOTOR TITAN
# ════════════════════════════════════════════════════════════════════

def patch_mini_ai_lifecycle():
    """Patch MiniAIEngine lifecycle to track model load/unload."""
    try:
        from src.core.mini_ai_parts._lifecycle import ModelLifecycleMixin

        original_load = ModelLifecycleMixin.load_model
        original_unload = ModelLifecycleMixin.unload_model

        def patched_load(self):
            log.warning(f"🔄 MiniAI: load_model() llamado — Thread: {threading.current_thread().name}")
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")
            result = original_load(self)
            diag.model_loads += 1
            if result:
                log.warning(f"✅ MiniAI: Modelo cargado exitosamente")
            else:
                log.warning(f"⚠️ MiniAI: load_model() retornó False (sin modelo)")
            return result

        def patched_unload(self):
            diag.model_unloads += 1
            log.warning(
                f"🔴 MiniAI: unload_model() llamado — "
                f"Executor: {self._executor} | "
                f"VerdictExecutor: {getattr(self, '_verdict_executor', 'N/A')} — "
                f"Thread: {threading.current_thread().name}"
            )
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")

            # Check: is this being called during an active request?
            if diag.last_request_start and not diag.last_request_end:
                log.error(
                    f"🚨 CRITICAL: unload_model() llamado DURANTE un request activo! "
                    f"Request empezó: {diag.last_request_start}"
                )

            result = original_unload(self)

            log.warning(
                f"🔴 MiniAI: unload_model() completado — "
                f"Executor después: {self._executor} | "
                f"VerdictExecutor después: {getattr(self, '_verdict_executor', 'N/A')}"
            )
            return result

        ModelLifecycleMixin.load_model = patched_load
        ModelLifecycleMixin.unload_model = patched_unload
        log.info("✅ Monkey-patch: MiniAIEngine lifecycle interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear MiniAIEngine lifecycle: {e}")


def patch_model_manager():
    """Patch ModelManager unload methods to track model swap."""
    try:
        from src.core.model_mgr_parts.unload import UnloadMixin

        original_unload_semantic = UnloadMixin.unload_semantic
        original_unload_ai = UnloadMixin.unload_ai
        original_unload_all = UnloadMixin.unload_all

        def patched_unload_semantic(self, reason="manual"):
            log.warning(f"🔴 ModelManager: unload_semantic() — reason={reason}")
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")
            return original_unload_semantic(self, reason)

        def patched_unload_ai(self, reason="manual"):
            diag.auto_unload_events += 1
            log.warning(f"🔴 ModelManager: unload_ai() — reason={reason}")
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")
            return original_unload_ai(self, reason)

        def patched_unload_all(self, reason="manual"):
            log.warning(f"🔴 ModelManager: unload_all() — reason={reason}")
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")
            return original_unload_all(self, reason)

        UnloadMixin.unload_semantic = patched_unload_semantic
        UnloadMixin.unload_ai = patched_unload_ai
        UnloadMixin.unload_all = patched_unload_all
        log.info("✅ Monkey-patch: ModelManager unload interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear ModelManager: {e}")

    # Also patch auto-unload monitor
    try:
        from src.core.model_mgr_parts.monitor import AutoUnloadMixin

        original_check_idle = AutoUnloadMixin._check_idle_unload
        original_check_ram = AutoUnloadMixin._check_ram_pressure

        def patched_check_idle(self):
            log.debug(f"⏰ AutoUnload: _check_idle_unload() llamado")
            return original_check_idle(self)

        def patched_check_ram(self):
            ram_mb = _get_ram_mb()
            log.debug(
                f"💾 AutoUnload: _check_ram_pressure() — RAM: {ram_mb:.0f}MB"
            )
            return original_check_ram(self)

        AutoUnloadMixin._check_idle_unload = patched_check_idle
        AutoUnloadMixin._check_ram_pressure = patched_check_ram
        log.info("✅ Monkey-patch: AutoUnload monitor interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear AutoUnload: {e}")


def patch_resource_governor():
    """Patch ResourceGovernor to track RAM/CPU/thermal events."""
    try:
        from src.core.shared.governor_parts.api import APIMixin

        original_pre_request = APIMixin.pre_request
        original_post_request = APIMixin.post_request
        original_is_ram_critical = APIMixin.is_ram_critical

        def patched_pre_request(self):
            ram_mb = _get_ram_mb()
            log.info(
                f"📥 Governor: pre_request() — RAM: {ram_mb:.0f}MB / {self.ram_limit_mb}MB "
                f"(critical={ram_mb > self.ram_limit_mb * 0.95})"
            )
            return original_pre_request(self)

        def patched_post_request(self):
            ram_mb = _get_ram_mb()
            log.info(
                f"📤 Governor: post_request() — RAM: {ram_mb:.0f}MB / {self.ram_limit_mb}MB"
            )
            return original_post_request(self)

        def patched_is_ram_critical(self):
            result = original_is_ram_critical(self)
            if result:
                diag.ram_critical_events += 1
                log.error(
                    f"🚨 RAM CRITICAL! {_get_ram_mb():.0f}MB / {self.ram_limit_mb}MB "
                    f"— Requests seran rechazados (503)"
                )
            return result

        APIMixin.pre_request = patched_pre_request
        APIMixin.post_request = patched_post_request
        APIMixin.is_ram_critical = patched_is_ram_critical
        log.info("✅ Monkey-patch: ResourceGovernor API interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear ResourceGovernor: {e}")

    # Patch monitor
    try:
        from src.core.shared.governor_parts.monitor import MonitorMixin

        original_auto_gc = MonitorMixin._auto_gc
        original_check_thermal = MonitorMixin._check_thermal

        def patched_auto_gc(self):
            log.debug(f"🗑️ Governor: _auto_gc() — RAM: {self._ram_usage_mb:.0f}MB / threshold: {self.gc_threshold_mb}MB")
            return original_auto_gc(self)

        def patched_check_thermal(self):
            was_throttle = self._thermal_throttle
            result = original_check_thermal(self)
            if self._thermal_throttle < was_throttle:
                diag.thermal_throttles += 1
                log.warning(
                    f"🔥 THERMAL THROTTLE: {was_throttle:.2f} → {self._thermal_throttle:.2f} "
                    f"(CPU: {self._cpu_usage*100:.0f}%)"
                )
            return result

        MonitorMixin._auto_gc = patched_auto_gc
        MonitorMixin._check_thermal = patched_check_thermal
        log.info("✅ Monkey-patch: ResourceGovernor Monitor interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear Governor Monitor: {e}")

    # Patch model_swap
    try:
        from src.core.shared.governor_parts.model_swap import ModelSwapMixin

        original_should_unload = ModelSwapMixin.should_unload_models

        def patched_should_unload(self):
            result = original_should_unload(self)
            if result != "none":
                log.warning(
                    f"🔄 ModelSwap: should_unload_models() = {result} "
                    f"(RAM: {self._ram_usage_mb:.0f}MB / {self.ram_limit_mb}MB)"
                )
            return result

        ModelSwapMixin.should_unload_models = patched_should_unload
        log.info("✅ Monkey-patch: ModelSwap interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear ModelSwap: {e}")


def patch_verdict_engine():
    """Patch VerdictEngine to track verdict pipeline."""
    try:
        from src.core.verdict_parts.verdict_engine import VerdictEngine

        original_verdict = VerdictEngine.verdict
        original_shutdown = VerdictEngine.shutdown

        def patched_verdict(self, text, code="", language="python",
                           question="Should this code be approved?", context=None):
            diag.verdict_calls += 1
            log.info(
                f"⚖️ VerdictEngine: verdict() llamado (total={diag.verdict_calls}) — "
                f"LLM available: {self._mini_ai is not None and self._mini_ai.is_loaded}"
            )
            try:
                result = original_verdict(self, text, code, language, question, context)
                log.info(
                    f"⚖️ VerdictEngine: resultado = {result.verdict.value} "
                    f"(source={result.source}, confidence={result.confidence:.2f}, "
                    f"llm_used={result.llm_used})"
                )
                return result
            except Exception as e:
                diag.verdict_fallbacks += 1
                diag.record_exception("VerdictEngine.verdict", e)
                log.error(f"⚖️ VerdictEngine: EXCEPCION en verdict(): {e}")
                raise

        def patched_shutdown(self):
            log.warning(
                f"🔴 VerdictEngine: shutdown() llamado — "
                f"Executor: {self._executor} — "
                f"Thread: {threading.current_thread().name}"
            )
            log.debug(f"   Stack: {''.join(traceback.format_stack()[-5:-1])[:300]}")

            if diag.last_request_start and not diag.last_request_end:
                log.error(
                    f"🚨 CRITICAL: VerdictEngine.shutdown() llamado DURANTE request activo!"
                )

            return original_shutdown(self)

        VerdictEngine.verdict = patched_verdict
        VerdictEngine.shutdown = patched_shutdown
        log.info("✅ Monkey-patch: VerdictEngine interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear VerdictEngine: {e}")

    # Patch VerdictMixin in MiniAIEngine
    try:
        from src.core.mini_ai_parts._verdict_mixin import VerdictMixin

        original_verdict_mixin = VerdictMixin.verdict
        original_ensure_executor = VerdictMixin._ensure_verdict_executor

        def patched_verdict_mixin(self, question, context="", evidence_for="",
                                   evidence_against="", consensus_hint=0.0):
            diag.verdict_calls += 1
            executor_state = getattr(self, '_verdict_executor', 'MISSING')
            log.info(
                f"⚖️ VerdictMixin: verdict() llamado — "
                f"Executor: {executor_state} — "
                f"Model loaded: {self.is_loaded}"
            )
            try:
                result = original_verdict_mixin(
                    self, question, context, evidence_for, evidence_against, consensus_hint
                )
                log.info(
                    f"⚖️ VerdictMixin: resultado = {result.get('verdict')} "
                    f"(source={result.get('source')}, confidence={result.get('confidence', 0):.2f})"
                )
                return result
            except Exception as e:
                diag.verdict_fallbacks += 1
                diag.record_exception("VerdictMixin.verdict", e)
                log.error(f"⚖️ VerdictMixin: EXCEPCION: {e}")
                raise

        def patched_ensure_executor(self):
            executor_before = getattr(self, '_verdict_executor', 'MISSING')
            result = original_ensure_executor(self)
            executor_after = getattr(self, '_verdict_executor', 'MISSING')

            if executor_before is None and executor_after is not None:
                log.warning(
                    f"⚡ VerdictMixin: _ensure_verdict_executor() recreó executor "
                    f"(era None → nuevo) — Esto es normal después de unload_model()"
                )
            return result

        VerdictMixin.verdict = patched_verdict_mixin
        VerdictMixin._ensure_verdict_executor = patched_ensure_executor
        log.info("✅ Monkey-patch: VerdictMixin interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear VerdictMixin: {e}")


def patch_fastapi_app():
    """Patch FastAPI chat completions endpoint to track request lifecycle."""
    try:
        # We'll patch at the module level since FastAPI creates routes at import time
        # Instead, we patch the middleware and helper functions
        import src.server.fastapi_app as fastapi_mod

        # Patch _run_orchestrator if it exists
        if hasattr(fastapi_mod, '_run_orchestrator'):
            original_run = fastapi_mod._run_orchestrator

            def patched_run(orchestrator, user_msg):
                diag.requests_total += 1
                diag.last_request_start = time.time()
                diag.last_request_end = None
                log.warning(
                    f"🌐 FASTAPI: _run_orchestrator() llamado — "
                    f"msg='{user_msg[:50]}...' — "
                    f"Request #{diag.requests_total}"
                )
                try:
                    result = original_run(orchestrator, user_msg)
                    diag.requests_completed += 1
                    diag.last_request_end = time.time()
                    elapsed = diag.last_request_end - diag.last_request_start
                    log.warning(
                        f"🌐 FASTAPI: _run_orchestrator() completado — "
                        f"Tiempo: {elapsed:.2f}s"
                    )
                    return result
                except Exception as e:
                    diag.requests_failed += 1
                    diag.last_request_end = time.time()
                    diag.record_exception("_run_orchestrator", e, user_msg[:100])
                    log.error(f"🌐 FASTAPI: _run_orchestrator() FALLO: {e}")
                    raise

            fastapi_mod._run_orchestrator = patched_run
            log.info("✅ Monkey-patch: FastAPI _run_orchestrator interceptado")
        else:
            log.warning("⚠️ No se encontró _run_orchestrator en fastapi_app")

    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear FastAPI app: {e}")


def patch_http_handler():
    """Patch stdlib HTTP handler to track request lifecycle."""
    try:
        from src.server.http_parts._post_mixin import PostMixin

        original_handle_chat = PostMixin._handle_chat_completions

        def patched_handle_chat(self):
            diag.requests_total += 1
            diag.last_request_start = time.time()
            diag.last_request_end = None
            log.warning(
                f"🌐 STDLIB: _handle_chat_completions() llamado — "
                f"Request #{diag.requests_total} — "
                f"Client: {self.client_address[0]}"
            )
            try:
                result = original_handle_chat(self)
                diag.requests_completed += 1
                diag.last_request_end = time.time()
                elapsed = diag.last_request_end - diag.last_request_start
                log.warning(
                    f"🌐 STDLIB: _handle_chat_completions() completado — "
                    f"Tiempo: {elapsed:.2f}s"
                )
                return result
            except TimeoutError:
                diag.requests_timeout += 1
                diag.last_request_end = time.time()
                log.error(f"🌐 STDLIB: REQUEST TIMEOUT!")
                raise
            except Exception as e:
                diag.requests_failed += 1
                diag.last_request_end = time.time()
                diag.record_exception("_handle_chat_completions", e)
                log.error(f"🌐 STDLIB: _handle_chat_completions() FALLO: {e}")
                raise

        PostMixin._handle_chat_completions = patched_handle_chat
        log.info("✅ Monkey-patch: HTTP handler _handle_chat_completions interceptado")
    except ImportError as e:
        log.warning(f"⚠️ No se pudo patchear HTTP handler: {e}")


def patch_asyncio():
    """Patch asyncio.run_in_executor to track async->sync bridging."""
    try:
        import asyncio
        original_run_in_executor = asyncio.AbstractEventLoop.run_in_executor

        def patched_run_in_executor(self, executor, func, *args):
            fn_name = func.__name__ if hasattr(func, '__name__') else str(func)[:50]
            log.debug(
                f"🔄 ASYNC: run_in_executor() — fn={fn_name} — "
                f"executor={executor}"
            )
            return original_run_in_executor(self, executor, func, *args)

        asyncio.AbstractEventLoop.run_in_executor = patched_run_in_executor
        log.info("✅ Monkey-patch: asyncio run_in_executor interceptado")
    except Exception as e:
        log.warning(f"⚠️ No se pudo patchear asyncio: {e}")


# ════════════════════════════════════════════════════════════════════
#  MONITOR DE THREADS EN BACKGROUND
# ════════════════════════════════════════════════════════════════════

class ThreadMonitor:
    """Background thread that periodically logs thread and resource status."""

    def __init__(self, interval=10.0):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DIAG-ThreadMonitor")
        self._thread.start()
        log.info(f"📊 Thread monitor iniciado (interval={self.interval}s)")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._report()
            except Exception as e:
                log.debug(f"Thread monitor error: {e}")
            self._stop.wait(timeout=self.interval)

    def _report(self):
        ram_mb = _get_ram_mb()
        active = threading.active_count()
        threads = threading.enumerate()

        # Find notable threads
        notable = []
        for t in threads:
            if t.name not in ("MainThread", "DIAG-ThreadMonitor"):
                notable.append(f"{t.name}(daemon={t.daemon})")

        log.info(
            f"📊 STATUS: RAM={ram_mb:.0f}MB | Threads={active} | "
            f"Notable: {', '.join(notable[:10]) if notable else 'none'}"
        )

        # Check for dead executors
        try:
            # If there are very few threads but model is "loaded", something is wrong
            if ram_mb > 300 and active < 5:
                log.warning(
                    f"⚠️ ANOMALY: RAM={ram_mb:.0f}MB but only {active} threads — "
                    f"Model may be loaded but executor threads are dead"
                )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
#  EXCEPTION HOOK GLOBAL
# ════════════════════════════════════════════════════════════════════

_original_excepthook = sys.excepthook

def _diag_excepthook(exc_type, exc_value, exc_tb):
    """Global exception handler that captures ALL uncaught exceptions."""
    diag.record_exception("uncaught", exc_value)

    log.critical(
        f"💥 UNCAUGHT EXCEPTION: [{exc_type.__name__}] {exc_value}"
    )
    log.critical(
        f"   Traceback:\n{''.join(traceback.format_exception(exc_type, exc_value, exc_tb))}"
    )

    # Also call original
    _original_excepthook(exc_type, exc_value, exc_tb)

sys.excepthook = _diag_excepthook


# Thread exception handler for threads
_original_thread_excepthook = getattr(threading, 'excepthook', None)

def _diag_thread_excepthook(args):
    """Handler for uncaught exceptions in threads."""
    diag.record_exception(f"thread:{args.thread.name}", args.exc_value)

    log.critical(
        f"💥 UNCAUGHT THREAD EXCEPTION in '{args.thread.name}': "
        f"[{args.exc_type.__name__}] {args.exc_value}"
    )
    log.critical(
        f"   Traceback:\n{''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb))}"
    )

    if _original_thread_excepthook:
        _original_thread_excepthook(args)

if hasattr(threading, 'excepthook'):
    threading.excepthook = _diag_thread_excepthook


# ════════════════════════════════════════════════════════════════════
#  ATEXIT: RESUMEN FINAL
# ════════════════════════════════════════════════════════════════════

def _atexit_summary():
    """Print diagnostic summary on exit."""
    log.warning("=" * 70)
    log.warning("  PROCESO TERMINANDO — Resumen de Diagnostico")
    log.warning("=" * 70)
    log.warning(diag.summary())
    log.warning(f"  Log completo guardado en: {_LOG_FILE}")
    log.warning("=" * 70)

    # Also print to stdout for Termux visibility
    print(diag.summary())
    print(f"\n  Log completo: {_LOG_FILE}")

atexit.register(_atexit_summary)


# ════════════════════════════════════════════════════════════════════
#  FUNCION PRINCIPAL
# ════════════════════════════════════════════════════════════════════

def main():
    global log

    parser = argparse.ArgumentParser(
        description=f"TITAN OMNISCALE X v18 — Motor de Diagnostico Completo"
    )
    parser.add_argument('--port', type=int, default=5000,
                        help='Puerto del servidor (default: 5000, mismo que main_headless.py)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host para bind (default: 0.0.0.0)')
    parser.add_argument('--ram-limit', type=int, default=4096,
                        help='Limite RAM en MB (default: 4096)')
    parser.add_argument('--server', type=str, default='stdlib',
                        choices=['stdlib', 'fastapi'],
                        help='Tipo de servidor')
    parser.add_argument('--auth', action='store_true',
                        help='Habilitar autenticacion')
    parser.add_argument('--no-preload', action='store_true',
                        help='No precargar modelos')
    parser.add_argument('--interval', type=float, default=10.0,
                        help='Intervalo del monitor de threads (default: 10s)')
    args = parser.parse_args()

    # ── 1. Configurar logging de diagnostico ──
    log = setup_diagnostic_logging(level=logging.DEBUG)

    print(f"\n{'='*70}")
    print(f"  TITAN OMNISCALE X v18 — MOTOR DE DIAGNOSTICO")
    print(f"{'='*70}")
    print(f"  Log file: {_LOG_FILE}")
    print(f"  Server: {args.server} | Port: {args.port}")
    print(f"  RAM limit: {args.ram_limit}MB")
    print(f"{'='*70}\n")

    log.warning("=" * 70)
    log.warning("  INICIANDO MOTOR DE DIAGNOSTICO COMPLETO")
    log.warning("=" * 70)
    log.warning(f"  Log file: {_LOG_FILE}")
    log.warning(f"  Python: {sys.version}")
    log.warning(f"  Platform: {sys.platform}")
    log.warning(f"  PID: {os.getpid()}")
    log.warning(f"  CWD: {os.getcwd()}")
    log.warning(f"  Server mode: {args.server}")
    log.warning(f"  RAM limit: {args.ram_limit}MB")
    log.warning("=" * 70)

    # ── 2. Aplicar monkey-patches ANTES de importar el motor ──
    log.warning("🔧 Aplicando monkey-patches...")

    # Core patches (no imports needed)
    patch_threadpool_executor()
    patch_threading()
    patch_gc()
    patch_signal()
    patch_asyncio()

    # ── 3. Inicializar el motor TITAN ──
    log.warning("🚀 Inicializando motor TITAN OMNISCALE X...")

    try:
        from src.core.env_loader import load_env
        load_env()
        log.info("✅ env_loader cargado")
    except Exception as e:
        log.error(f"❌ Error cargando env_loader: {e}")
        diag.record_exception("env_loader", e)

    try:
        from src.core.shared.resource_governor import (
            tune_gc_for_arm, set_process_priority_low,
            limit_open_files, init_governor,
        )
        tune_gc_for_arm()
        set_process_priority_low()
        limit_open_files()
        log.info("✅ Resource governor utils inicializados")
    except Exception as e:
        log.error(f"❌ Error inicializando governor utils: {e}")
        diag.record_exception("governor_utils", e)

    # Import version
    try:
        from src.core.shared._version import TITAN_VERSION_STR, TITAN_FULL_NAME
        log.info(f"✅ Version: {TITAN_FULL_NAME}")
    except Exception as e:
        log.warning(f"⚠️ No se pudo importar version: {e}")

    # ── 4. Aplicar patches del motor TITAN ──
    log.warning("🔧 Aplicando patches del motor TITAN...")
    patch_mini_ai_lifecycle()
    patch_model_manager()
    patch_resource_governor()
    patch_verdict_engine()
    patch_fastapi_app()
    patch_http_handler()

    # ── 5. Inicializar bases de datos ──
    try:
        from src.core.shared.db_initializer import initialize_databases
        initialize_databases()
        log.info("✅ Bases de datos inicializadas")
    except Exception as e:
        log.error(f"❌ Error inicializando bases de datos: {e}")
        diag.record_exception("db_initializer", e)

    # ── 6. Crear Resource Governor ──
    try:
        governor = init_governor(ram_limit_mb=args.ram_limit)
        log.info(f"✅ ResourceGovernor creado (RAM limit={args.ram_limit}MB)")
    except Exception as e:
        log.error(f"❌ Error creando governor: {e}")
        diag.record_exception("init_governor", e)
        governor = None

    # ── 7. Crear Orchestrator ──
    orchestrator = None
    try:
        try:
            from src.core.dag_orchestrator import DAGOrchestrator
            orchestrator = DAGOrchestrator()
            log.info("✅ DAGOrchestrator creado")
        except ImportError:
            from src.core.orchestrator import TitanOrchestrator
            orchestrator = TitanOrchestrator()
            log.info("✅ TitanOrchestrator creado (fallback)")
    except Exception as e:
        log.error(f"❌ Error creando orchestrator: {e}")
        diag.record_exception("orchestrator_create", e)
        sys.exit(1)

    # Connect governor with ModelManager
    if governor and hasattr(orchestrator, '_model_mgr'):
        governor.set_model_manager(orchestrator._model_mgr)
        log.info("✅ Governor conectado con ModelManager")

    # ── 8. Precargar modelos ──
    if not args.no_preload and hasattr(orchestrator, '_model_mgr'):
        log.warning("🔄 Precargando modelos...")
        try:
            _mgr = orchestrator._model_mgr
            t0 = time.time()
            _ = _mgr.semantic_engine
            t1 = time.time()
            log.warning(f"✅ SemanticEngine cargado en {t1-t0:.1f}s")
            _ = _mgr.mini_ai_engine
            t2 = time.time()
            log.warning(f"✅ MiniAIEngine cargado en {t2-t1:.1f}s")
            log.warning(f"✅ Todos los modelos listos ({t2-t0:.1f}s total)")
        except Exception as e:
            log.error(f"❌ Error precargando modelos: {e}")
            diag.record_exception("model_preload", e)
    else:
        log.info("ℹ️ Precarga de modelos deshabilitada")

    # ── 9. Crear AuthService ──
    auth_service = None
    if args.auth or args.server == 'fastapi':
        try:
            from src.core.auth_service import AuthService
            auth_service = AuthService()
            auth_service.ensure_admin()
            log.info("✅ AuthService inicializado")
        except Exception as e:
            log.warning(f"⚠️ AuthService init falló: {e}")
            auth_service = None

    # ── 10. Crear Rate Limiter ──
    rate_limiter = None
    try:
        from src.server import RateLimiter
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
                )
                log.info("✅ TenantRateLimiter creado")
            except ImportError:
                rate_limiter = RateLimiter(
                    max_requests_per_minute=_rl_rpm,
                    burst_size=_rl_burst,
                    global_max_concurrent=_rl_concurrent,
                )
                log.info("✅ RateLimiter creado (no tenant)")
        else:
            rate_limiter = RateLimiter(
                max_requests_per_minute=_rl_rpm,
                burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
            )
            log.info("✅ RateLimiter creado")
    except Exception as e:
        log.warning(f"⚠️ RateLimiter init falló: {e}")
        rate_limiter = None

    # ── 11. Configurar handler compartido ──
    try:
        from src.server import configure_handler, get_local_ip
        configure_handler(orchestrator, governor=governor,
                          start_time=time.time(), platform_tag="termux-debug",
                          rate_limiter=rate_limiter)
        log.info("✅ HTTP handler configurado")
    except Exception as e:
        log.error(f"❌ Error configurando handler: {e}")
        diag.record_exception("configure_handler", e)

    # ── 12. Iniciar Thread Monitor ──
    thread_monitor = ThreadMonitor(interval=args.interval)
    thread_monitor.start()

    # ── 13. Obtener IP ──
    try:
        ip = get_local_ip()
    except Exception:
        ip = "0.0.0.0"

    # ── 14. Iniciar servidor ──
    if args.server == 'fastapi':
        _start_fastapi(orchestrator, governor, auth_service, rate_limiter, ip, args)
    else:
        _start_stdlib(orchestrator, governor, rate_limiter, ip, args)

    # ── 15. Cleanup ──
    thread_monitor.stop()
    if governor:
        governor.stop_monitoring()


def _start_fastapi(orchestrator, governor, auth_service, rate_limiter, ip, args):
    """Start the FastAPI server with diagnostic logging."""
    global log

    try:
        from src.server.fastapi_app import run_fastapi_server
    except ImportError:
        log.error("❌ FastAPI no instalado. Instala con: pip install fastapi uvicorn")
        sys.exit(1)

    log.warning(f"🌐 Iniciando servidor FastAPI en http://{ip}:{args.port}")
    log.warning(f"   Endpoints: /v1/chat/completions, /v1/models, /health")

    print(f"\n{'='*70}")
    print(f"  TITAN OMNISCALE X v18 — DIAGNOSTIC MODE [FastAPI]")
    print(f"  http://{ip}:{args.port}/v1")
    print(f"  Log: {_LOG_FILE}")
    print(f"{'='*70}\n")

    try:
        run_fastapi_server(
            orchestrator=orchestrator,
            host=args.host,
            port=args.port,
            auth_service=auth_service,
            rate_limiter=rate_limiter,
            governor=governor,
            platform_tag="termux-debug",
        )
    except KeyboardInterrupt:
        log.warning("🛑 KeyboardInterrupt recibido — apagando...")
        if governor:
            governor.stop_monitoring()
    except Exception as e:
        log.critical(f"💥 FastAPI server CRASH: {e}")
        diag.record_exception("fastapi_server", e)
        raise


def _start_stdlib(orchestrator, governor, rate_limiter, ip, args):
    """Start the stdlib HTTP server with diagnostic logging."""
    global log

    from src.server import TitanHTTPHandler, ThreadedHTTPServer

    log.warning(f"🌐 Iniciando servidor stdlib en http://{ip}:{args.port}")

    try:
        server = ThreadedHTTPServer((args.host, args.port), TitanHTTPHandler)
    except OSError as e:
        log.error(f"❌ No se pudo iniciar servidor: {e}")
        sys.exit(1)

    # Signal handler with diagnostic logging
    def shutdown_handler(signum, frame):
        diag.signal_handlers_called += 1
        sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        log.warning(
            f"📡 SIGNAL {sig_name} recibido — iniciando shutdown limpio "
            f"(signal #{diag.signal_handlers_called})"
        )
        log.debug(f"   Signal frame: {frame}")

        # Dump state before shutdown
        log.warning(f"   Requests pendientes: total={diag.requests_total}, "
                     f"completed={diag.requests_completed}, "
                     f"failed={diag.requests_failed}")
        log.warning(f"   Model loads: {diag.model_loads}, unloads: {diag.model_unloads}")
        log.warning(f"   Executor shutdowns: {diag.executor_shutdowns}")

        if governor:
            governor.stop_monitoring()
        server.shutdown()
        try:
            from src.server.http_handler import _shutdown_loop
            _shutdown_loop()
        except ImportError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print(f"\n{'='*70}")
    print(f"  TITAN OMNISCALE X v18 — DIAGNOSTIC MODE [Stdlib]")
    print(f"{'='*70}")
    print(f"")
    print(f"  >>> CLINE / AIDE / OPENCODE — CONFIGURA ESTA URL:")
    print(f"      http://{ip}:{args.port}/v1")
    print(f"")
    if ip.startswith("169.254."):
        print(f"  [!] IP link-local detectada (datos moviles)")
        print(f"      Si Cline no conecta, intenta: http://127.0.0.1:{args.port}/v1")
        print(f"      O configura TITAN_BIND_IP en .env con tu IP real")
    print(f"  Log: {_LOG_FILE}")
    print(f"{'='*70}")
    print(f"\n  Comandos interactivos:")
    print(f"    status  — Ver estado del sistema")
    print(f"    models  — Ver estado de modelos")
    print(f"    diag    — Ver resumen de diagnostico")
    print(f"    threads — Listar threads activos")
    print(f"    ram     — Ver uso de RAM detallado")
    print(f"    help    — Lista de comandos")
    print(f"    quit    — Detener servidor\n")

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    log.warning(f"✅ Servidor escuchando en http://{ip}:{args.port}")

    # Interactive loop
    try:
        while True:
            try:
                cmd = input("").strip().lower()
                if cmd in ('quit', 'exit', 'q', 'stop'):
                    break
                elif cmd == 'status':
                    _cmd_status(governor, orchestrator)
                elif cmd == 'models':
                    _cmd_models(orchestrator)
                elif cmd == 'diag':
                    print(diag.summary())
                elif cmd == 'threads':
                    _cmd_threads()
                elif cmd == 'ram':
                    _cmd_ram(governor)
                elif cmd == 'help':
                    print("  Comandos: status | models | diag | threads | ram | quit | help")
                elif cmd:
                    print(f"  Comando desconocido: {cmd} (escribe 'help')")
            except EOFError:
                break
    except KeyboardInterrupt:
        pass

    log.warning("🛑 Cerrando servidor...")
    if governor:
        governor.stop_monitoring()
    server.shutdown()
    try:
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
    except ImportError:
        pass
    log.warning("✅ Servidor detenido")


# ════════════════════════════════════════════════════════════════════
#  COMANDOS INTERACTIVOS
# ════════════════════════════════════════════════════════════════════

def _cmd_status(governor, orchestrator):
    """Show system status."""
    ram_mb = _get_ram_mb()
    active = threading.active_count()
    threads = threading.enumerate()

    print(f"\n  === ESTADO DEL SISTEMA ===")
    print(f"  RAM: {ram_mb:.0f}MB")
    if governor:
        res = governor.get_status()
        print(f"  CPU: {res.get('cpu_usage_pct', 0):.1f}%")
        print(f"  RAM limit: {res.get('ram_limit_mb', 0)}MB")
        print(f"  Thermal throttle: {res.get('thermal_throttle', 0):.2f}")
        print(f"  MCTS sims: {res.get('adaptive_mcts_sims', 0)}")
        print(f"  Requests served: {res.get('stats', {}).get('requests_served', 0)}")
        print(f"  GC forced: {res.get('stats', {}).get('gc_forced', 0)}")
    print(f"  Active threads: {active}")
    print(f"  Diagnostics: loads={diag.model_loads}, unloads={diag.model_unloads}, "
          f"executor_shutdowns={diag.executor_shutdowns}")
    print(f"  Verdicts: calls={diag.verdict_calls}, fallbacks={diag.verdict_fallbacks}")
    print(f"  Exceptions captured: {len(diag.exceptions)}")


def _cmd_models(orchestrator):
    """Show model status."""
    print(f"\n  === ESTADO DE MODELOS ===")
    if hasattr(orchestrator, '_model_mgr'):
        mgr = orchestrator._model_mgr
        ms = mgr.stats
        print(f"  SemanticEngine: {'LOADED' if ms['semantic_loaded'] else 'UNLOADED'} "
              f"(loads={ms['semantic_loads']}, unloads={ms['semantic_unloads']})")
        print(f"  MiniAIEngine:  {'LOADED' if ms['ai_loaded'] else 'UNLOADED'} "
              f"(loads={ms['ai_loads']}, unloads={ms['ai_unloads']})")
        print(f"  Auto-unloads: {ms['auto_unloads']} | RAM: {ms['current_ram_mb']}MB")

        # Check engine internals
        if mgr._mini_ai_engine:
            ai = mgr._mini_ai_engine
            print(f"  MiniAI internals:")
            print(f"    is_loaded: {ai.is_loaded}")
            print(f"    _executor: {ai._executor}")
            print(f"    _verdict_executor: {getattr(ai, '_verdict_executor', 'N/A')}")
            print(f"    stats: {ai.stats}")
    else:
        print("  ModelManager no disponible")


def _cmd_threads():
    """List active threads."""
    print(f"\n  === THREADS ACTIVOS ({threading.active_count()}) ===")
    for t in threading.enumerate():
        # Buscar info de creacion por id() del objeto thread
        info = diag.active_threads.get(id(t), {})
        created_from = info.get('created_from', 'unknown')[:80]
        print(f"  {t.name} (daemon={t.daemon}, ident={t.ident})")
        if created_from != 'unknown':
            print(f"    Creado desde: {created_from}")


def _cmd_ram(governor):
    """Show detailed RAM usage."""
    print(f"\n  === USO DE RAM ===")
    ram_mb = _get_ram_mb()
    print(f"  RSS: {ram_mb:.0f}MB")

    if governor:
        res = governor.get_status()
        print(f"  Limit: {res.get('ram_limit_mb', 0)}MB")
        print(f"  Usage: {res.get('ram_usage_mb', 0):.1f}MB")
        pct = res.get('ram_usage_mb', 0) / max(res.get('ram_limit_mb', 1), 1) * 100
        print(f"  Percent: {pct:.1f}%")
        print(f"  Critical: {pct > 95}")

    # GC stats
    gc_stats = gc.get_stats()
    for i, stat in enumerate(gc_stats):
        print(f"  GC gen-{i}: collections={stat.collections}, collected={stat.collected}, "
              f"uncollectable={stat.uncollectable}")

    # Object counts by type (top 10)
    counts = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda x: -x[1])[:10]
    print(f"\n  Top 10 object types:")
    for name, count in top:
        print(f"    {name}: {count}")


# ════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    main()
