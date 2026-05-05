"""Mixin: RAM budget management for ModelManager."""

import time
import gc
import platform

from ._imports import logger


class RAMMixin:
    """Mixin providing RAM budget checking and management."""

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
            if platform.system() == 'Darwin':
                return usage.ru_maxrss / 1024 / 1024  # macOS: bytes -> MB
            return usage.ru_maxrss / 1024  # Linux: KB -> MB
        except Exception:
            pass
        return 0.0
