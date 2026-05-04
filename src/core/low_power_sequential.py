"""
ZENIC LOGIC - LowPowerSequentialMode (Dinámico Basado en Hardware)

Modo "Low-Power Sequential" dinámico que hace que el DAG evalúe
la temperatura y batería del dispositivo, y fuerce la ejecución
secuencial de la Capa 4 (Architect, Planner, Risk) cuando el
hardware está bajo estrés.

Problema:
  En Android/Termux, cuando el CPU está bajo carga (>70% por >30s),
  el kernel de Android puede matar procesos por "thermal throttling"
  o "battery drain". La ejecución paralela de Architect+Planner+Risk
  dispara picos de CPU que activan estos bloqueos.

Solución:
  1. El DAG evalúa constantemente: temperatura, batería, CPU
  2. Si el hardware está estresado, desactiva la ejecución paralela
  3. Fuerza Capa 4 a ser estrictamente secuencial
  4. Reduce agresividad de MCTS y solver timeouts
  5. Puede postponer tareas no-críticas (auto-scraping, indexing)

Modos de operación:
  - NORMAL:     Paralelo completo, todos los agentes activos
  - CONSERVATIVE: Secuencial en Capa 4, MCTS reducido 50%
  - EMERGENCY:  Secuencial total, solo agentes críticos, MCTS mínimo
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


class PowerMode(Enum):
    """Modos de energía del sistema."""
    NORMAL = "normal"           # Paralelo completo
    CONSERVATIVE = "conservative"  # Secuencial en Capa 4
    EMERGENCY = "emergency"     # Secuencial total, mínimo recurso


@dataclass
class HardwareState:
    """Estado del hardware en un momento dado."""
    cpu_usage: float = 0.0       # 0.0 - 1.0
    ram_usage_mb: float = 0.0
    ram_limit_mb: float = 2048
    temperature_c: float = 45.0  # Estimada
    battery_level: float = 100.0  # 0-100%
    battery_charging: bool = True
    thermal_throttle: float = 1.0  # 1.0 = normal, 0.5 = reducido

    @property
    def ram_pct(self) -> float:
        return (self.ram_usage_mb / self.ram_limit_mb * 100) if self.ram_limit_mb > 0 else 0


class LowPowerSequentialMode:
    """
    Evaluador de modo de energía que decide si la ejecución
    debe ser paralela o secuencial basándose en el estado del hardware.

    Integrado con el DAGOrchestrator y el ResourceGovernor para
    tomar decisiones dinámicas durante la ejecución del pipeline.
    """

    # Umbrales para cambiar de modo
    CPU_CONSERVATIVE_THRESHOLD = 0.65     # 65% CPU → conservativo
    CPU_EMERGENCY_THRESHOLD = 0.85        # 85% CPU → emergencia
    RAM_CONSERVATIVE_THRESHOLD = 0.70     # 70% RAM → conservativo
    RAM_EMERGENCY_THRESHOLD = 0.90        # 90% RAM → emergencia
    TEMP_CONSERVATIVE_THRESHOLD = 55.0    # 55°C → conservativo
    TEMP_EMERGENCY_THRESHOLD = 65.0       # 65°C → emergencia
    BATTERY_CONSERVATIVE_THRESHOLD = 30.0 # 30% batería → conservativo
    BATTERY_EMERGENCY_THRESHOLD = 15.0    # 15% batería → emergencia

    # Duración mínima en un modo antes de poder cambiar (evita flapping)
    MODE_STICKINESS_SECONDS = 30.0

    def __init__(self, governor=None):
        self._governor = governor
        self._current_mode = PowerMode.NORMAL
        self._mode_since = time.time()
        self._history: deque = deque(maxlen=100)
        self._forced_mode: Optional[PowerMode] = None

    def set_governor(self, governor):
        """Conecta con el ResourceGovernor existente."""
        self._governor = governor

    def force_mode(self, mode: Optional[PowerMode]):
        """Fuerza un modo específico (para testing o configuración manual)."""
        self._forced_mode = mode
        if mode:
            self._current_mode = mode
            self._mode_since = time.time()
            logger.info(f"LowPowerSequential: Forced mode to {mode.value}")

    def evaluate(self) -> PowerMode:
        """
        Evalúa el estado actual del hardware y determina el modo óptimo.

        Returns:
            PowerMode actual después de la evaluación
        """
        # If forced mode, use it
        if self._forced_mode:
            self._current_mode = self._forced_mode
            return self._current_mode

        # Read hardware state
        hw = self._read_hardware_state()

        # Calculate scores for each mode
        emergency_score = 0
        conservative_score = 0

        # CPU
        if hw.cpu_usage > self.CPU_EMERGENCY_THRESHOLD:
            emergency_score += 3
        elif hw.cpu_usage > self.CPU_CONSERVATIVE_THRESHOLD:
            conservative_score += 2

        # RAM
        if hw.ram_pct > self.RAM_EMERGENCY_THRESHOLD * 100:
            emergency_score += 3
        elif hw.ram_pct > self.RAM_CONSERVATIVE_THRESHOLD * 100:
            conservative_score += 2

        # Temperature
        if hw.temperature_c > self.TEMP_EMERGENCY_THRESHOLD:
            emergency_score += 3
        elif hw.temperature_c > self.TEMP_CONSERVATIVE_THRESHOLD:
            conservative_score += 2

        # Battery (only if not charging)
        if not hw.battery_charging:
            if hw.battery_level < self.BATTERY_EMERGENCY_THRESHOLD:
                emergency_score += 2
            elif hw.battery_level < self.BATTERY_CONSERVATIVE_THRESHOLD:
                conservative_score += 2

        # Thermal throttle
        if hw.thermal_throttle < 0.5:
            emergency_score += 2
        elif hw.thermal_throttle < 0.8:
            conservative_score += 1

        # Determine mode
        if emergency_score >= 4:
            new_mode = PowerMode.EMERGENCY
        elif emergency_score >= 2 or conservative_score >= 3:
            new_mode = PowerMode.CONSERVATIVE
        else:
            new_mode = PowerMode.NORMAL

        # Apply stickiness (don't change mode too quickly)
        time_in_mode = time.time() - self._mode_since
        if new_mode != self._current_mode:
            if time_in_mode < self.MODE_STICKINESS_SECONDS:
                # Block downgrade during stickiness, but always allow upgrade to more restrictive mode
                if self._mode_rank(new_mode) < self._mode_rank(self._current_mode):
                    new_mode = self._current_mode  # Stay in current (more restrictive) mode
            else:
                self._mode_since = time.time()

        # Log mode changes
        if new_mode != self._current_mode:
            logger.warning(
                f"LowPowerSequential: Mode change {self._current_mode.value} → {new_mode.value} "
                f"(CPU={hw.cpu_usage:.0%}, RAM={hw.ram_pct:.0f}%, Temp={hw.temperature_c:.0f}°C, "
                f"Battery={hw.battery_level:.0f}%)"
            )

        self._current_mode = new_mode

        # Record in history
        self._history.append({
            "timestamp": time.time(),
            "mode": new_mode.value,
            "cpu": hw.cpu_usage,
            "ram_pct": hw.ram_pct,
            "temp": hw.temperature_c,
            "battery": hw.battery_level,
        })

        return self._current_mode

    def _read_hardware_state(self) -> HardwareState:
        """Lee el estado actual del hardware."""
        hw = HardwareState()

        # From governor if available
        if self._governor:
            hw.cpu_usage = getattr(self._governor, '_cpu_usage', 0.0)
            hw.ram_usage_mb = getattr(self._governor, '_ram_usage_mb', 0.0)
            hw.ram_limit_mb = getattr(self._governor, 'ram_limit_mb', 2048)
            hw.thermal_throttle = getattr(self._governor, '_thermal_throttle', 1.0)

        # Read temperature from thermal zone (Android/Linux)
        hw.temperature_c = self._read_temperature()

        # Read battery level (Android)
        hw.battery_level, hw.battery_charging = self._read_battery()

        return hw

    def _read_temperature(self) -> float:
        """Lee la temperatura del CPU desde /sys/class/thermal/."""
        # Try common thermal zones
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",  # Generic
            "/sys/class/thermal/thermal_zone1/temp",  # CPU
            "/sys/class/thermal/thermal_zone2/temp",  # GPU
            "/sys/class/hwmon/hwmon0/temp1_input",    # hwmon
        ]

        for path in thermal_paths:
            try:
                with open(path, "r") as f:
                    raw = int(f.read().strip())
                    # Some report in millidegrees, some in degrees
                    if raw > 1000:
                        return raw / 1000.0
                    return float(raw)
            except (FileNotFoundError, PermissionError, ValueError):
                continue

        # Fallback: estimate from CPU usage and thermal throttle
        if self._governor:
            cpu = getattr(self._governor, '_cpu_usage', 0.3)
            throttle = getattr(self._governor, '_thermal_throttle', 1.0)
            # Rough estimate: idle=38°C, 100% CPU=70°C, throttle reduces
            estimated = 38 + (cpu * 35) * throttle
            return estimated

        return 45.0  # Safe default

    def _read_battery(self) -> tuple:
        """Lee el nivel de batería (Android/Termux)."""
        battery_path = "/sys/class/power_supply/battery"

        level = 100.0
        charging = True

        try:
            # Battery level
            cap_path = os.path.join(battery_path, "capacity")
            if os.path.isfile(cap_path):
                with open(cap_path, "r") as f:
                    level = float(f.read().strip())

            # Charging status
            status_path = os.path.join(battery_path, "status")
            if os.path.isfile(status_path):
                with open(status_path, "r") as f:
                    status = f.read().strip().lower()
                    charging = status in ("charging", "full")

        except (FileNotFoundError, PermissionError, ValueError):
            pass

        return level, charging

    @staticmethod
    def _mode_rank(mode: PowerMode) -> int:
        """Ranking de severidad de modos (mayor = más restrictivo)."""
        return {
            PowerMode.NORMAL: 0,
            PowerMode.CONSERVATIVE: 1,
            PowerMode.EMERGENCY: 2,
        }.get(mode, 0)

    # ================================================================
    #  DECISION API - Usada por DAGOrchestrator
    # ================================================================

    def should_run_parallel_layer4(self) -> bool:
        """
        ¿Debería la Capa 4 (Architect, Planner, Risk) ejecutarse en paralelo?

        Returns:
            True si paralelo, False si secuencial
        """
        mode = self.evaluate()
        return mode == PowerMode.NORMAL

    def should_run_parallel_agents(self) -> bool:
        """
        ¿Deberían los agentes ejecutarse en paralelo?

        Returns:
            True si paralelo, False si secuencial
        """
        mode = self.evaluate()
        return mode != PowerMode.EMERGENCY

    def get_mcts_scale(self) -> float:
        """
        Factor de escala para simulaciones MCTS según el modo.

        Returns:
            1.0 (normal), 0.5 (conservative), 0.25 (emergency)
        """
        mode = self.evaluate()
        scales = {
            PowerMode.NORMAL: 1.0,
            PowerMode.CONSERVATIVE: 0.5,
            PowerMode.EMERGENCY: 0.25,
        }
        return scales.get(mode, 1.0)

    def get_solver_timeout_scale(self) -> float:
        """
        Factor de escala para solver timeout según el modo.

        Returns:
            1.0 (normal), 0.7 (conservative), 0.4 (emergency)
        """
        mode = self.evaluate()
        scales = {
            PowerMode.NORMAL: 1.0,
            PowerMode.CONSERVATIVE: 0.7,
            PowerMode.EMERGENCY: 0.4,
        }
        return scales.get(mode, 1.0)

    def should_postpone_non_critical(self) -> bool:
        """
        ¿Deberían postponerse tareas no críticas (auto-scraping, indexing)?

        Returns:
            True si se debe postponer
        """
        mode = self.evaluate()
        return mode != PowerMode.NORMAL

    def get_active_agents(self) -> list:
        """
        Lista de agentes que deberían estar activos según el modo.

        En EMERGENCY, solo los agentes críticos del pipeline principal.
        """
        mode = self.evaluate()

        # All agents (normal mode)
        all_agents = [
            "INTENT", "DECOMPOSER", "EXTRACTOR",
            "ARCHITECT", "PLANNER", "RISK",
            "WRITER", "ASSEMBLER", "FORMATTER",
        ]

        # Critical agents only (emergency mode)
        critical_agents = [
            "INTENT", "EXTRACTOR", "WRITER", "FORMATTER",
        ]

        if mode == PowerMode.EMERGENCY:
            return critical_agents
        elif mode == PowerMode.CONSERVATIVE:
            # Skip RISK in conservative (it's optional)
            return [a for a in all_agents if a != "RISK"]
        else:
            return all_agents

    def get_execution_order(self, layer: int = 4) -> list:
        """
        Orden de ejecución para una capa del DAG según el modo.

        En NORMAL: todos en paralelo
        En CONSERVATIVE/EMERGENCY: uno a uno, ordenados por prioridad
        """
        mode = self.evaluate()

        if mode == PowerMode.NORMAL:
            return ["parallel"]

        if layer == 4:
            # Capa 4: Architect → Planner → Risk (prioridad de seguridad)
            if mode == PowerMode.CONSERVATIVE:
                return ["ARCHITECT", "PLANNER"]  # Skip RISK
            else:  # EMERGENCY
                return ["ARCHITECT"]  # Solo lo esencial

        return ["sequential"]

    @property
    def current_mode(self) -> PowerMode:
        """Modo actual sin re-evaluar."""
        return self._current_mode

    @property
    def hardware_state(self) -> HardwareState:
        """Estado actual del hardware."""
        return self._read_hardware_state()

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del modo de energía."""
        hw = self._read_hardware_state()
        return {
            "current_mode": self._current_mode.value,
            "cpu_usage": round(hw.cpu_usage * 100, 1),
            "ram_pct": round(hw.ram_pct, 1),
            "temperature_c": round(hw.temperature_c, 1),
            "battery_level": round(hw.battery_level, 1),
            "battery_charging": hw.battery_charging,
            "thermal_throttle": round(hw.thermal_throttle, 2),
            "parallel_layer4": self.should_run_parallel_layer4(),
            "parallel_agents": self.should_run_parallel_agents(),
            "mcts_scale": self.get_mcts_scale(),
            "solver_timeout_scale": self.get_solver_timeout_scale(),
            "active_agents": self.get_active_agents(),
            "postpone_non_critical": self.should_postpone_non_critical(),
            "history_entries": len(self._history),
            "forced_mode": self._forced_mode.value if self._forced_mode else None,
        }
