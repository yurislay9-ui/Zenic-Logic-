"""
TITAN OMNISCALE X - Macro Router (Pure Python)

Router de criticidad basado en patrones.
Sin dependencias externas.
"""
from src.core.shared.contracts import IntentPayload, RoutingPayload, CriticalityLevel, RoutePath, OperationType


class MacroRouter:
    CRITICAL_PATTERNS = ["auth", "login", "crypto", "db"]

    def route(self, intent):
        is_critical = any(p in intent.target.lower() for p in self.CRITICAL_PATTERNS)
        if is_critical or intent.op in [OperationType.DELETE, OperationType.REFACTOR]:
            return RoutingPayload(
                intent=intent, criticality=CriticalityLevel.SURGICAL_CRITICAL,
                route=RoutePath.DEEP_PATH, reason="Nodo critico u operacion de riesgo."
            )
        if intent.op == OperationType.CREATE:
            return RoutingPayload(
                intent=intent, criticality=CriticalityLevel.DEEP_MODERATE,
                route=RoutePath.DEEP_PATH, reason="Creacion requiere planificacion."
            )
        return RoutingPayload(
            intent=intent, criticality=CriticalityLevel.FAST_STANDARD,
            route=RoutePath.FAST_PATH, reason="Operacion estandar."
        )
