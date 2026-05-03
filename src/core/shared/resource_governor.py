"""
TITAN OMNISCALE X - Resource Governor v16 (Termux/proot-distro)

Monitor y limitador de recursos para que el engine no chupe
todos los recursos del telefono.

Implementa:
- CPU throttle: duerme entre operaciones pesadas para evitar throttling termico
- RAM guard: monitorea uso de memoria y fuerza GC cuando se acerca al limite
- Thermal protection: reduce agresividad del solver si la CPU esta caliente
- Adaptive budgets: ajusta MCTS simulaciones y timeouts segun carga del sistema
- Process nice: baja prioridad del proceso para que el telefono siga usable
- Model swap: notifica al ModelManager cuando hay presión de RAM

CAMBIO TECNOLÓGICO v16 - Integración con ModelManager:
- get_model_ram_status(): informa al ModelManager del estado de RAM
- should_unload_models(): recomienda descargar modelos si RAM crítica
- set_model_manager(): conecta con el gestor de modelos híbrido

Compatible con Termux + proot-distro (Debian ARM).
Sin dependencias externas. Usa solo stdlib.
"""

import os
import gc
import time
import threading
import logging
import resource
from typing import Dict

logger = logging.getLogger(__name__)


class ResourceGovernor:
    """
    Governor de recursos que protege el telefono del overheating y OOM.

    Tu Redmi 12R Pro tiene 12+8GB RAM (20GB total con virtual).
    Esto no significa que debamos usarlo todo. El governor mantiene:

    - RAM limit: 2GB max para el engine (deja 18GB para Android)
    - CPU throttle: 70% max (deja 30% para el SO)
    - Thermal: si el proceso lleva >30s a >60% CPU, reduce agresividad
    - GC agresivo: cada 60s o cuando RAM > 1.5GB
    """

    # Limites conservadores para un telefono
    DEFAULT_RAM_LIMIT_MB = 2048       # 2GB max para el engine
    DEFAULT_GC_THRESHOLD_MB = 1536    # Forzar GC a 1.5GB
    DEFAULT_CPU_SLEEP_MS = 50         # 50ms sleep entre ops pesadas
    DEFAULT_CPU_SAMPLE_INTERVAL = 5   # Muestrear cada 5s
    THERMAL_SCALE_BACK_THRESHOLD = 30  # Si >30s a alta CPU, reducir

    def __init__(self, ram_limit_mb=None, gc_threshold_mb=None):
        self.ram_limit_mb = ram_limit_mb or self.DEFAULT_RAM_LIMIT_MB
        self.gc_threshold_mb = gc_threshold_mb or self.DEFAULT_GC_THRESHOLD_MB

        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._cpu_usage = 0.0
        self._ram_usage_mb = 0.0
        self._last_cpu_check = time.time()
        self._high_cpu_start = None  # Cuando empezo el pico de CPU
        self._thermal_throttle = 1.0  # 1.0 = normal, 0.5 = reducir a la mitad
        self._gc_count = 0
        self._request_count = 0
        self._model_manager = None  # Ref to ModelManager for model swap

        # Stats
        self.stats = {
            "gc_forced": 0,
            "thermal_throttles": 0,
            "ram_peaks": 0,
            "requests_served": 0,
        }

        logger.info(
            "ResourceGovernor: RAM limit=%dMB, GC threshold=%dMB",
            self.ram_limit_mb, self.gc_threshold_mb
        )

    def start_monitoring(self):
        """Inicia el thread de monitoreo en background."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()
        logger.info("ResourceGovernor: monitoring started")

    def stop_monitoring(self):
        """Detiene el thread de monitoreo."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("ResourceGovernor: monitoring stopped")

    def _monitor_loop(self):
        """Loop principal del monitor que corre en background."""
        while not self._stop_event.is_set():
            try:
                self._update_cpu_usage()
                self._update_ram_usage()
                self._check_thermal()
                self._auto_gc()
            except Exception as e:
                logger.debug("Monitor error: %s", e)

            self._stop_event.wait(timeout=self.DEFAULT_CPU_SAMPLE_INTERVAL)

    def _update_cpu_usage(self):
        """Estima el uso de CPU leyendo /proc/stat (Linux/proot)."""
        try:
            # Metodo 1: Leer /proc/stat (disponible en proot-distro Debian)
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            values = [int(x) for x in line.split()[1:]]
            idle = values[3]
            total = sum(values)

            time.sleep(0.1)

            with open('/proc/stat', 'r') as f:
                line = f.readline()
            values2 = [int(x) for x in line.split()[1:]]
            idle2 = values2[3]
            total2 = sum(values2)

            delta_idle = idle2 - idle
            delta_total = total2 - total
            if delta_total > 0:
                self._cpu_usage = 1.0 - (delta_idle / delta_total)
        except (FileNotFoundError, PermissionError, ValueError):
            # Fallback: estimar basado en tiempo de proceso
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
                user_time = usage.ru_utime
                wall_time = time.time() - self._last_cpu_check
                if wall_time > 0:
                    self._cpu_usage = min(user_time / wall_time, 1.0)
                self._last_cpu_check = time.time()
            except Exception:
                self._cpu_usage = 0.3  # Asumir uso moderado

    def _update_ram_usage(self):
        """Mide el uso de RAM del proceso actual."""
        try:
            # Metodo 1: /proc/self/status (mas preciso en Linux)
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        self._ram_usage_mb = int(line.split()[1]) / 1024
                        break
        except (FileNotFoundError, PermissionError):
            # Fallback: resource module
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
                # ru_maxrss es en KB en Linux
                self._ram_usage_mb = usage.ru_maxrss / 1024
            except Exception:
                self._ram_usage_mb = 0

    def _check_thermal(self):
        """Verifica si hay riesgo de throttling termico y reduce agresividad."""
        if self._cpu_usage > 0.7:
            if self._high_cpu_start is None:
                self._high_cpu_start = time.time()
            else:
                elapsed = time.time() - self._high_cpu_start
                if elapsed > self.THERMAL_SCALE_BACK_THRESHOLD:
                    # Reducir agresividad al 60%
                    self._thermal_throttle = max(0.4, self._thermal_throttle * 0.8)
                    self.stats["thermal_throttles"] += 1
                    logger.warning(
                        "Thermal throttle: CPU >70%% por %.0fs, "
                        "reduciendo agresividad a %.0f%%",
                        elapsed, self._thermal_throttle * 100
                    )
        else:
            # CPU normal: restaurar gradualmente
            if self._high_cpu_start is not None:
                self._high_cpu_start = None
            self._thermal_throttle = min(1.0, self._thermal_throttle * 1.05)

    def _auto_gc(self):
        """Fuerza garbage collection si la RAM se acerca al limite."""
        if self._ram_usage_mb > self.gc_threshold_mb:
            collected = gc.collect(2)  # Full collection
            self._gc_count += 1
            self.stats["gc_forced"] += 1
            logger.info(
                "Auto-GC: RAM=%.0fMB > threshold=%.0fMB, collected %d objects",
                self._ram_usage_mb, self.gc_threshold_mb, collected
            )

    # ============================================================
    #  API PUBLICA - Usada por el engine para controlar recursos
    # ============================================================

    def cpu_throttle_sleep(self):
        """
        Duerme un poco entre operaciones pesadas para evitar
        que la CPU se pegue al 100%% y el telefono se caliente.

        El sleep es adaptativo: si la CPU esta alta, duerme mas.
        """
        if self._cpu_usage > 0.8:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS * 3  # 150ms
        elif self._cpu_usage > 0.6:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS * 2  # 100ms
        else:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS       # 50ms

        # Aplicar throttle termico
        sleep_ms = int(sleep_ms / self._thermal_throttle)

        time.sleep(sleep_ms / 1000.0)

    def get_adaptive_mcts_simulations(self, base_simulations=100):
        """
        Ajusta las simulaciones MCTS segun la carga del sistema.

        Si el telefono esta tranquilo: 100 simulaciones (max)
        Si la CPU esta alta: reduce proporcionalmente
        Si hay throttle termico: reduce aun mas
        """
        if self._cpu_usage > 0.8:
            scale = 0.3
        elif self._cpu_usage > 0.6:
            scale = 0.5
        elif self._cpu_usage > 0.4:
            scale = 0.7
        else:
            scale = 1.0

        # Aplicar throttle termico
        scale *= self._thermal_throttle

        # Nunca menos de 10 simulaciones
        adaptive = max(10, int(base_simulations * scale))

        if adaptive < base_simulations:
            logger.info(
                "MCTS adaptive: %d -> %d sims (CPU=%.0f%%, throttle=%.0f%%)",
                base_simulations, adaptive,
                self._cpu_usage * 100, self._thermal_throttle * 100
            )

        return adaptive

    def get_adaptive_solver_timeout(self, base_timeout_ms=15000):
        """
        Ajusta el timeout del solver segun recursos disponibles.

        Si hay poca RAM: reduce timeout (evitar que Z3 consuma mas)
        Si hay throttle termico: reduce timeout
        Si el sistema esta tranquilo: timeout completo
        """
        scale = self._thermal_throttle

        if self._ram_usage_mb > self.ram_limit_mb * 0.8:
            scale *= 0.6  # Reducir mucho si RAM casi al limite
        elif self._ram_usage_mb > self.ram_limit_mb * 0.5:
            scale *= 0.8

        adaptive = max(3000, int(base_timeout_ms * scale))
        return adaptive

    def pre_request(self):
        """Llama antes de cada request para preparar el sistema."""
        self._request_count += 1
        self.stats["requests_served"] += 1

        # GC ligero antes de cada request (gen 0 solo)
        gc.collect(0)

    def post_request(self):
        """Llama despues de cada request para limpiar."""
        # GC de generacion 1 despues de cada request
        gc.collect(1)

        # Si la RAM esta alta, hacer full GC
        self._update_ram_usage()
        if self._ram_usage_mb > self.gc_threshold_mb * 0.8:
            gc.collect(2)

    def get_z3_memory_limit_mb(self):
        """
        Limite de memoria para Z3 solver.
        Z3 puede consumir muchisima RAM. Lo limitamos a 512MB
        en el telefono para dejar espacio al resto.
        """
        available = self.ram_limit_mb - self._ram_usage_mb
        # Max 512MB para Z3, o lo que quede menos 256MB
        return max(128, min(512, int(available - 256)))

    def is_ram_critical(self):
        """Retorna True si la RAM esta al limite y hay que rechazar requests."""
        return self._ram_usage_mb > self.ram_limit_mb * 0.95

    def set_model_manager(self, model_manager):
        """
        Conecta el ResourceGovernor con el ModelManager para model swap.

        Cuando el governor detecta presión de RAM, puede recomendar
        al ModelManager que descargue modelos para liberar memoria.
        """
        self._model_manager = model_manager
        logger.info("ResourceGovernor: Connected to ModelManager for model swap")

    def should_unload_models(self) -> str:
        """
        Recomienda al ModelManager descargar modelos según presión de RAM.

        Returns:
            "none" - No se necesita descargar nada
            "semantic" - Descargar SemanticEngine (~150MB)
            "ai" - Descargar MiniAIEngine (~378MB)
            "all" - Descargar ambos (~530MB)
        """
        if self._ram_usage_mb > self.ram_limit_mb * 0.9:
            return "all"
        if self._ram_usage_mb > self.ram_limit_mb * 0.75:
            return "ai"
        if self._ram_usage_mb > self.ram_limit_mb * 0.6:
            return "semantic"
        return "none"

    def get_model_ram_status(self) -> Dict:
        """
        Retorna estado de RAM para que el ModelManager tome decisiones.

        El ModelManager consulta esto antes de cargar un modelo para
        decidir si hay presupuesto suficiente o si debe descargar otro.
        """
        return {
            "ram_usage_mb": round(self._ram_usage_mb, 1),
            "ram_limit_mb": self.ram_limit_mb,
            "ram_available_mb": round(self.ram_limit_mb - self._ram_usage_mb, 1),
            "ram_usage_pct": round(self._ram_usage_mb / self.ram_limit_mb * 100, 1),
            "thermal_throttle": round(self._thermal_throttle, 2),
            "recommendation": self.should_unload_models(),
        }

    def get_status(self):
        """Retorna el estado actual del governor para el endpoint /health."""
        return {
            "cpu_usage_pct": round(self._cpu_usage * 100, 1),
            "ram_usage_mb": round(self._ram_usage_mb, 1),
            "ram_limit_mb": self.ram_limit_mb,
            "thermal_throttle": round(self._thermal_throttle, 2),
            "adaptive_mcts_sims": self.get_adaptive_mcts_simulations(),
            "adaptive_solver_timeout_ms": self.get_adaptive_solver_timeout(),
            "z3_memory_limit_mb": self.get_z3_memory_limit_mb(),
            "stats": self.stats,
        }


# ============================================================
#  Singleton global - accesible desde cualquier modulo
# ============================================================

_governor = None

def get_governor():
    """Obtiene el singleton del ResourceGovernor."""
    global _governor
    if _governor is None:
        _governor = ResourceGovernor()
    return _governor

def init_governor(ram_limit_mb=None):
    """Inicializa el governor con configuracion custom."""
    global _governor
    _governor = ResourceGovernor(ram_limit_mb=ram_limit_mb)
    _governor.start_monitoring()
    return _governor


# ============================================================
#  GC Tuning para ARM (configurar al inicio)
# ============================================================

def tune_gc_for_arm():
    """
    Ajusta los thresholds del GC para ARM donde la memoria
    es mas limitada y el GC puede ser mas costoso.

    Python default: (700, 10, 10) - muy agresivo para telefono
    Nuestro tuning: (1000, 15, 15) - menos frecuente pero mas efectivo
    """
    thresholds = gc.get_threshold()
    new_thresholds = (1000, 15, 15)

    if thresholds != new_thresholds:
        gc.set_threshold(*new_thresholds)
        logger.info(
            "GC tuned for ARM: %s -> %s",
            thresholds, new_thresholds
        )

    # Habilitar DEBUG para detectar ciclos de referencia
    # Solo en modo debug, no en produccion
    if os.environ.get('TITAN_DEBUG_GC'):
        gc.set_debug(gc.DEBUG_STATS)


def set_process_priority_low():
    """
    Baja la prioridad del proceso para que el telefono
    siga siendo responsivo mientras el engine trabaja.

    En proot-distro Debian: usa os.nice()
    En Termux nativo: usa os.nice() si tiene permisos
    """
    try:
        # Bajar prioridad (nice +10 = menor prioridad)
        os.nice(10)
        logger.info("Process priority lowered (nice +10)")
    except (PermissionError, AttributeError):
        logger.debug("Cannot lower process priority - running at default")


def limit_open_files(max_files=256):
    """
    Limita el numero de archivos abiertos para no agotar
    los file descriptors del sistema en Android.

    Cada SQLite connection usa un fd. Con 4 DBs + conexiones
    concurrentes, 256 es mas que suficiente.
    """
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft > max_files:
            resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, hard))
            logger.info("Open files limit: %d -> %d", soft, max_files)
    except (ValueError, AttributeError, OSError):
        pass
