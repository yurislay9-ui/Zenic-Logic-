"""
ZENIC LOGIC - LowPowerSequentialMode (Dinamico Basado en Hardware)

Thin facade: all implementation lives in low_power_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - low_power_parts._imports:  PowerMode enum, HardwareState dataclass, shared constants
  - low_power_parts.evaluate:   EvaluateMixin (hardware stress evaluation: temperature, battery)
  - low_power_parts.decision:   DecisionMixin (decide whether to force sequential execution)
  - low_power_parts.mode:       LowPowerSequentialMode class (inherits all mixins)

Public API:
  Classes:    LowPowerSequentialMode, PowerMode, HardwareState
"""

from .low_power_parts import *  # noqa: F401,F403
