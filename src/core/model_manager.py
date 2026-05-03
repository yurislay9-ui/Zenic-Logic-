"""
TITAN OMNISCALE X - Model Manager v16 (Hybrid Lazy Loading + Auto-Unload)

Gestor de modelos que maximiza el rendimiento en el Redmi 12R Pro:
- Lazy Loading: Los modelos solo se cargan cuando se necesitan
- Auto-Unload: Los modelos se descargan tras N minutos de inactividad
- RAM Budget: Control estricto de memoria para no quemar el teléfono
- Model Swap: Carga/descarga dinámica según demanda

Esto permite que el engine arranque en <5s (vs ~60s cargando todo)
y consuma ~50MB RAM idle (vs ~730MB con ambos modelos cargados).

Uso:
    manager = ModelManager()
    # Los modelos NO se cargan hasta que se necesitan

    with manager.semantic_engine() as engine:
        result = engine.classify_intent("crear modulo auth")
    # Tras idle_timeout, el modelo se auto-descarga

Flujo de RAM:
    Idle:          ~50MB  (solo SQLite + estructuras)
    Semantic only: ~200MB (+fastembed ~150MB)
    LLM only:      ~430MB (+Qwen ~378MB)
    Full:          ~730MB (ambos modelos)
    Auto-unload:   Vuelve a ~50MB tras 5 min sin uso

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Termux + proot-distro (Debian ARM)
"""

import os
import time
import threading
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# === Configuration from environment ===
IDLE_TIMEOUT_S = int(os.environ.get("TITAN_MODEL_IDLE_TIMEOUT", "300"))  # 5 min default
RAM_BUDGET_MB = int(os.environ.get("TITAN_RAM_BUDGET_MB", "768"))  # Max RAM for models
ENABLE_AUTO_UNLOAD = os.environ.get("TITAN_AUTO_UNLOAD", "1") == "1"
ENABLE_LAZY_LOAD = os.environ.get("TITAN_LAZY_LOAD", "1") == "1"


class ModelManager:
    """
    Gestor híbrido de modelos AI para maximizar rendimiento en móvil.

    Estrategia: Lazy Load + Auto-Unload + RAM Budget
    - Los modelos se cargan SOLO cuando se necesitan (lazy)
    - Los modelos se DESCARGAN tras N minutos sin uso (auto-unload)
    - Si la RAM supera el presupuesto, se descarga el modelo menos usado

    Esto reduce el consumo de RAM de ~730MB permanente a ~50MB idle,
    protegiendo el teléfono del sobrecalentamiento y desgaste.
    """

    def __init__(self, lazy_load: bool = True, idle_timeout_s: int = None,
                 ram_budget_mb: int = None):
        self._lazy_load = lazy_load if ENABLE_LAZY_LOAD else False
        self._idle_timeout_s = idle_timeout_s or IDLE_TIMEOUT_S
        self._ram_budget_mb = ram_budget_mb or RAM_BUDGET_MB

        # Model instances (lazy-created)
        self._semantic_engine = None
        self._mini_ai_engine = None

        # Track last access time for auto-unload
        self._semantic_last_access = 0.0
        self._ai_last_access = 0.0

        # Lock for thread-safe model loading/unloading
        self._lock = threading.RLock()

        # Background monitor for auto-unload
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._monitor_interval = 30  # Check every 30 seconds

        # Stats
        self._stats = {
            "semantic_loads": 0,
            "semantic_unloads": 0,
            "ai_loads": 0,
            "ai_unloads": 0,
            "auto_unloads": 0,
            "ram_budget_exceeded": 0,
        }

        logger.info(
            f"ModelManager: lazy_load={self._lazy_load}, "
            f"idle_timeout={self._idle_timeout_s}s, "
            f"ram_budget={self._ram_budget_mb}MB, "
            f"auto_unload={ENABLE_AUTO_UNLOAD}"
        )

    # ================================================================
    #  SEMANTIC ENGINE ACCESS
    # ================================================================

    @property
    def semantic_engine(self):
        """
        Acceso directo al SemanticEngine. Carga lazy si es necesario.
        Para acceso con auto-unload protegido, usar semantic_engine_ctx().
        """
        with self._lock:
            self._ensure_semantic_loaded()
            self._semantic_last_access = time.time()
            return self._semantic_engine

    @contextmanager
    def semantic_engine_ctx(self):
        """
        Context manager para SemanticEngine con auto-unload tracking.

        Uso:
            with manager.semantic_engine_ctx() as engine:
                if engine and engine.is_loaded:
                    result = engine.classify_intent(text)
        """
        with self._lock:
            self._ensure_semantic_loaded()
            self._semantic_last_access = time.time()
        try:
            yield self._semantic_engine
        finally:
            self._semantic_last_access = time.time()

    def _ensure_semantic_loaded(self):
        """Carga SemanticEngine si no está cargado (lazy loading)."""
        if self._semantic_engine is not None and self._semantic_engine.is_loaded:
            return

        # Check RAM budget before loading
        if not self._check_ram_budget(150):  # fastembed needs ~150MB
            logger.warning(
                "ModelManager: RAM budget exceeded, cannot load SemanticEngine. "
                "Will try unloading AI engine first."
            )
            self._try_free_ram(needed_mb=150)

        from src.core.semantic_engine import SemanticEngine
        self._semantic_engine = SemanticEngine(auto_load=True)
        self._semantic_last_access = time.time()
        self._stats["semantic_loads"] += 1

        if self._semantic_engine.is_loaded:
            logger.info("ModelManager: SemanticEngine loaded (lazy)")
        else:
            logger.warning("ModelManager: SemanticEngine load failed, using fallbacks")

    # ================================================================
    #  MINI AI ENGINE ACCESS
    # ================================================================

    @property
    def mini_ai_engine(self):
        """
        Acceso directo al MiniAIEngine. Carga lazy si es necesario.
        Para acceso con auto-unload protegido, usar ai_engine_ctx().
        """
        with self._lock:
            self._ensure_ai_loaded()
            self._ai_last_access = time.time()
            return self._mini_ai_engine

    @contextmanager
    def ai_engine_ctx(self):
        """
        Context manager para MiniAIEngine con auto-unload tracking.

        Uso:
            with manager.ai_engine_ctx() as engine:
                if engine and engine.is_loaded:
                    result = engine.classify_intent(text)
        """
        with self._lock:
            self._ensure_ai_loaded()
            self._ai_last_access = time.time()
        try:
            yield self._mini_ai_engine
        finally:
            self._ai_last_access = time.time()

    def _ensure_ai_loaded(self):
        """Carga MiniAIEngine si no está cargado (lazy loading)."""
        if self._mini_ai_engine is not None and self._mini_ai_engine.is_loaded:
            return

        # Check RAM budget before loading
        if not self._check_ram_budget(400):  # Qwen needs ~400MB
            logger.warning(
                "ModelManager: RAM budget exceeded, cannot load MiniAIEngine. "
                "Will try unloading SemanticEngine first."
            )
            self._try_free_ram(needed_mb=400)

        from src.core.mini_ai_engine import MiniAIEngine
        self._mini_ai_engine = MiniAIEngine(auto_load=True)
        self._ai_last_access = time.time()
        self._stats["ai_loads"] += 1

        if self._mini_ai_engine.is_loaded:
            logger.info("ModelManager: MiniAIEngine loaded (lazy)")
        else:
            logger.warning("ModelManager: MiniAIEngine load failed, using fallbacks")

    # ================================================================
    #  MODEL UNLOADING
    # ================================================================

    def unload_semantic(self, reason: str = "manual"):
        """Descarga SemanticEngine para liberar ~150MB RAM."""
        with self._lock:
            if self._semantic_engine is not None:
                self._semantic_engine.unload_model()
                self._stats["semantic_unloads"] += 1
                logger.info(f"ModelManager: SemanticEngine unloaded ({reason})")

    def unload_ai(self, reason: str = "manual"):
        """Descarga MiniAIEngine para liberar ~378MB RAM."""
        with self._lock:
            if self._mini_ai_engine is not None:
                self._mini_ai_engine.unload_model()
                self._stats["ai_unloads"] += 1
                logger.info(f"ModelManager: MiniAIEngine unloaded ({reason})")

    def unload_all(self, reason: str = "manual"):
        """Descarga ambos modelos para liberar ~530MB RAM."""
        self.unload_semantic(reason)
        self.unload_ai(reason)

    # ================================================================
    #  AUTO-UNLOAD MONITOR
    # ================================================================

    def start_auto_unload_monitor(self):
        """Inicia el thread que monitorea y descarga modelos idle."""
        if not ENABLE_AUTO_UNLOAD:
            logger.info("ModelManager: Auto-unload disabled by config")
            return

        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._auto_unload_loop, daemon=True
        )
        self._monitor_thread.start()
        logger.info(
            f"ModelManager: Auto-unload monitor started "
            f"(timeout={self._idle_timeout_s}s, interval={self._monitor_interval}s)"
        )

    def stop_auto_unload_monitor(self):
        """Detiene el monitor de auto-unload."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("ModelManager: Auto-unload monitor stopped")

    def _auto_unload_loop(self):
        """Loop que descarga modelos tras idle timeout."""
        while not self._stop_event.is_set():
            try:
                self._check_idle_unload()
                self._check_ram_pressure()
            except Exception as e:
                logger.debug(f"Auto-unload monitor error: {e}")

            self._stop_event.wait(timeout=self._monitor_interval)

    def _check_idle_unload(self):
        """Descarga modelos que llevan mucho tiempo sin usarse."""
        now = time.time()

        # Check SemanticEngine idle
        if (self._semantic_engine is not None
                and self._semantic_engine.is_loaded
                and self._semantic_last_access > 0):
            idle_time = now - self._semantic_last_access
            if idle_time > self._idle_timeout_s:
                self.unload_semantic(reason=f"idle_{int(idle_time)}s")
                self._stats["auto_unloads"] += 1

        # Check MiniAIEngine idle
        if (self._mini_ai_engine is not None
                and self._mini_ai_engine.is_loaded
                and self._ai_last_access > 0):
            idle_time = now - self._ai_last_access
            if idle_time > self._idle_timeout_s:
                self.unload_ai(reason=f"idle_{int(idle_time)}s")
                self._stats["auto_unloads"] += 1

    def _check_ram_pressure(self):
        """Si la RAM está bajo presión, descargar modelos agresivamente."""
        try:
            ram_mb = self._get_current_ram_mb()
            if ram_mb > self._ram_budget_mb * 0.9:
                # RAM al 90% del presupuesto: descargar el modelo más idle
                logger.warning(
                    f"ModelManager: RAM pressure detected ({ram_mb:.0f}MB / "
                    f"{self._ram_budget_mb}MB budget). Unloading idle models."
                )
                self._stats["ram_budget_exceeded"] += 1

                # Unload the least recently used model
                if (self._semantic_last_access <= self._ai_last_access
                        and self._semantic_engine is not None
                        and self._semantic_engine.is_loaded):
                    self.unload_semantic(reason="ram_pressure")
                elif (self._mini_ai_engine is not None
                      and self._mini_ai_engine.is_loaded):
                    self.unload_ai(reason="ram_pressure")
        except Exception as e:
            logger.debug(f"RAM pressure check error: {e}")

    # ================================================================
    #  RAM BUDGET MANAGEMENT
    # ================================================================

    def _check_ram_budget(self, needed_mb: int) -> bool:
        """Verifica si hay presupuesto de RAM para cargar un modelo."""
        current_mb = self._get_current_ram_mb()
        return (current_mb + needed_mb) <= self._ram_budget_mb

    def _try_free_ram(self, needed_mb: int):
        """Intenta liberar RAM descargando modelos menos usados."""
        # Strategy: unload least recently used model first
        sem_idle = time.time() - self._semantic_last_access if self._semantic_last_access > 0 else 9999
        ai_idle = time.time() - self._ai_last_access if self._ai_last_access > 0 else 9999

        # Unload the most idle model
        if sem_idle >= ai_idle and self._semantic_engine and self._semantic_engine.is_loaded:
            self.unload_semantic(reason="free_ram_for_ai")
        elif self._mini_ai_engine and self._mini_ai_engine.is_loaded:
            self.unload_ai(reason="free_ram_for_semantic")

        # Force garbage collection
        import gc
        gc.collect(2)

    @staticmethod
    def _get_current_ram_mb() -> float:
        """Obtiene el uso actual de RAM del proceso en MB."""
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        return int(line.split()[1]) / 1024
        except (FileNotFoundError, PermissionError):
            pass
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return usage.ru_maxrss / 1024
        except Exception:
            pass
        return 0.0

    # ================================================================
    #  EAGER vs LAZY INIT (for DAGOrchestrator compatibility)
    # ================================================================

    def init_eager(self):
        """
        Carga ambos modelos inmediatamente (comportamiento original).
        Usar solo si se quiere el comportamiento v13/v15 sin lazy loading.
        """
        self._ensure_semantic_loaded()
        self._ensure_ai_loaded()
        logger.info("ModelManager: Eager init complete (both models loaded)")

    @property
    def semantic_loaded(self) -> bool:
        """True si SemanticEngine está cargado y listo."""
        return (self._semantic_engine is not None
                and self._semantic_engine.is_loaded)

    @property
    def ai_loaded(self) -> bool:
        """True si MiniAIEngine está cargado y listo."""
        return (self._mini_ai_engine is not None
                and self._mini_ai_engine.is_loaded)

    # ================================================================
    #  STATUS & STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del gestor de modelos."""
        return {
            **self._stats,
            "lazy_load_enabled": self._lazy_load,
            "auto_unload_enabled": ENABLE_AUTO_UNLOAD,
            "idle_timeout_s": self._idle_timeout_s,
            "ram_budget_mb": self._ram_budget_mb,
            "semantic_loaded": self.semantic_loaded,
            "ai_loaded": self.ai_loaded,
            "semantic_idle_s": int(time.time() - self._semantic_last_access) if self._semantic_last_access > 0 else -1,
            "ai_idle_s": int(time.time() - self._ai_last_access) if self._ai_last_access > 0 else -1,
            "current_ram_mb": round(self._get_current_ram_mb(), 1),
        }

    def get_status(self) -> Dict[str, Any]:
        """Estado completo para el endpoint /health."""
        status = {
            "model_manager": "active",
            "mode": "lazy" if self._lazy_load else "eager",
            "ram_current_mb": round(self._get_current_ram_mb(), 1),
            "ram_budget_mb": self._ram_budget_mb,
            "models": {
                "semantic_engine": {
                    "loaded": self.semantic_loaded,
                    "status": "active" if self.semantic_loaded else "unloaded",
                },
                "mini_ai_engine": {
                    "loaded": self.ai_loaded,
                    "status": "active" if self.ai_loaded else "unloaded",
                },
            },
        }
        if self.semantic_loaded:
            status["models"]["semantic_engine"]["idle_s"] = int(
                time.time() - self._semantic_last_access
            ) if self._semantic_last_access > 0 else 0
        if self.ai_loaded:
            status["models"]["mini_ai_engine"]["idle_s"] = int(
                time.time() - self._ai_last_access
            ) if self._ai_last_access > 0 else 0
        return status


# ============================================================
#  Singleton global - accesible desde cualquier módulo
# ============================================================

_manager = None

def get_model_manager() -> ModelManager:
    """Obtiene el singleton del ModelManager."""
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager

def init_model_manager(lazy_load: bool = True, idle_timeout_s: int = None,
                       ram_budget_mb: int = None) -> ModelManager:
    """Inicializa el ModelManager con configuración custom."""
    global _manager
    _manager = ModelManager(
        lazy_load=lazy_load,
        idle_timeout_s=idle_timeout_s,
        ram_budget_mb=ram_budget_mb,
    )
    _manager.start_auto_unload_monitor()
    return _manager
