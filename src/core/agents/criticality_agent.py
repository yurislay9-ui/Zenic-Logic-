"""
TITAN OMNISCALE X - CriticalityAgent (F4)

Agente de Ruteo Dinámico de Criticalidad que UNIFICA la lógica de
criticalidad dispersa en 5 subsistemas:

  1. MacroRouter.route() — keywords + AST topology (Nivel 2)
  2. TitanAgent.CRITICALITY_PATHS — mapping estático int→path
  3. SurgicalAgent._infer_criticality() — keywords en mensaje
  4. ContextAgent._allocate_budget() — ajusta presupuesto por goal
  5. SmartMemory.compute_importance() — peso por operación

Problemas que resuelve:
  - Type mismatch: IntentOutput.criticality=str vs RoutingPayload.criticality=int
  - Criticalidad estática: no se adapta al contexto semántico
  - Lógica duplicada: 3 sitios infieren criticalidad independientemente
  - Sin retroalimentación: no aprende de operaciones previas

Arquitectura 3-Cable (orden de costo ascendente):
  ┌──────────────────────────────────────────────────────────┐
  │  CABLE 1: LLM Inference (si Qwen disponible)           │
  │    Prompt → "Rate criticality of {op}/{goal} on {target}"│
  │    Parse → level:int + reason:str + adjustments:dict     │
  │                                                          │
  │  CABLE 2: Semantic Engine (si embeddings disponibles)   │
  │    Comparar operación vs patrones críticos conocidos     │
  │    Similarity score → nivel de criticalidad              │
  │                                                          │
  │  CABLE 3: Deterministic Multi-Signal (siempre funciona) │
  │    MacroRouter keywords + SurgicalAgent keywords +       │
  │    SmartMemory importance + ContextAgent budget signals  │
  │    Fusión ponderada → criticality level                  │
  └──────────────────────────────────────────────────────────┘

Output: CriticalityOutput unificado que alimenta:
  - F1 (DAG): path selection (low_crit/standard/high_crit)
  - F2 (Surgical): ajusta fusión de señales
  - F3 (Context): modifica presupuesto de tokens
  - CodeAgent: ajusta generación (validación, seguridad, errores)
  - BusinessLogicAgent: ajusta ejecución (auditoría, rollback)

Restricciones de diseño:
  - ≤600 tokens por llamada LLM (Qwen3-0.6B)
  - Fallback determinista siempre disponible
  - Compatible con Android/Termux, 500MB RAM
  - Resuelve type mismatch: siempre produce int (1/2/3)
"""

import re
import time
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentOutput, CriticalityInput, CriticalityOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# ── Constantes de Criticalidad ──

# Niveles canónicos (igual que CriticalityLevel en types.py)
LEVEL_FAST = 1         # FAST_STANDARD
LEVEL_MODERATE = 2     # DEEP_MODERATE
LEVEL_SURGICAL = 3     # SURGICAL_CRITICAL

# Mapeo string → int (resuelve type mismatch)
STR_TO_LEVEL: Dict[str, int] = {
    "standard": 1, "fast": 1, "low": 1, "1": 1,
    "moderate": 2, "deep": 2, "medium": 2, "2": 2,
    "critical": 3, "surgical": 3, "high": 3, "3": 3,
    "fast_standard": 1, "deep_moderate": 2, "surgical_critical": 3,
}

# Mapeo int → DAG path (resuelve routing)
LEVEL_TO_PATH: Dict[int, str] = {
    1: "low_crit",
    2: "standard",
    3: "high_crit",
}

# Palabras clave críticas por categoría
CRITICAL_KEYWORDS = frozenset({
    "auth", "login", "password", "token", "session", "crypto",
    "encrypt", "decrypt", "hash", "ssl", "tls", "certificate",
    "payment", "credit", "debit", "bank", "transaction",
    "database", "migration", "schema", "sql", "query",
    "admin", "root", "superuser", "permission", "privilege",
    "secret", "key", "private", "credential", "api_key",
    "inject", "xss", "csrf", "vulnerability", "exploit",
    "firewall", "network", "proxy", "vpn",
})

MODERATE_KEYWORDS = frozenset({
    "api", "endpoint", "route", "controller", "service",
    "model", "repository", "factory", "builder",
    "config", "settings", "environment", "deploy",
    "middleware", "handler", "processor", "manager",
    "orchestrator", "coordinator", "scheduler",
})

# Goals que elevan criticalidad automáticamente
GOAL_CRITICALITY_MAP: Dict[str, int] = {
    "SECURITY_HARDEN": 3,
    "BUG_FIX": 2,
    "COMPLEXITY_REDUCTION": 1,
    "MODERN_PATTERN": 1,
    "FEATURE_ADD": 2,
    "PERFORMANCE": 2,
    "READABILITY": 1,
}

# Operations que elevan criticalidad automáticamente
OP_CRITICALITY_MAP: Dict[str, int] = {
    "DELETE": 3,
    "REFACTOR": 2,
    "DEBUG": 2,
    "OPTIMIZE": 2,
    "CREATE": 2,
    "SEARCH": 1,
    "ANALYZE": 1,
    "EXPLAIN": 1,
}

# Ajustes comportamentales por nivel de criticalidad
CRITICALITY_ADJUSTMENTS: Dict[int, Dict[str, Any]] = {
    1: {  # FAST_STANDARD
        "code_agent": {
            "extra_validation": False,
            "security_checks": False,
            "error_handling": "basic",
            "docstring_level": "minimal",
            "max_complexity": 15,
        },
        "business_agent": {
            "audit_trail": False,
            "validation_layers": 1,
            "rollback": False,
            "idempotency_check": False,
        },
        "context_budget_modifier": 0.8,   # Less context needed
        "sandbox_strictness": "standard",
        "solver_required": False,
    },
    2: {  # DEEP_MODERATE
        "code_agent": {
            "extra_validation": True,
            "security_checks": False,
            "error_handling": "comprehensive",
            "docstring_level": "standard",
            "max_complexity": 10,
        },
        "business_agent": {
            "audit_trail": True,
            "validation_layers": 2,
            "rollback": True,
            "idempotency_check": False,
        },
        "context_budget_modifier": 1.0,   # Standard budget
        "sandbox_strictness": "strict",
        "solver_required": False,
    },
    3: {  # SURGICAL_CRITICAL
        "code_agent": {
            "extra_validation": True,
            "security_checks": True,
            "error_handling": "defensive",
            "docstring_level": "full",
            "max_complexity": 5,
        },
        "business_agent": {
            "audit_trail": True,
            "validation_layers": 3,
            "rollback": True,
            "idempotency_check": True,
        },
        "context_budget_modifier": 1.3,   # More context for critical ops
        "sandbox_strictness": "surgical",
        "solver_required": True,
    },
}


class CriticalityAgent(BaseAgent[CriticalityOutput]):
    """
    Agente F4: Ruteo Dinámico de Criticalidad.

    Unifica la inferencia de criticalidad desde múltiples señales:
    1. LLM (si Qwen disponible) — comprensión semántica profunda
    2. Semantic Engine — comparación con patrones conocidos
    3. Determinista Multi-Signal — fusión de keywords + AST + memory

    Produce CriticalityOutput canónico que alimenta:
    - F1 (DAG): path selection
    - F2 (Surgical): calibración de fusión
    - F3 (Context): modificación de presupuesto
    - CodeAgent: ajuste de generación
    - BusinessLogicAgent: ajuste de ejecución
    """

    def __init__(self, semantic_engine=None, smart_memory=None,
                 macro_router=None) -> None:
        super().__init__(name="criticality")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._macro_router = macro_router
        # Historial de criticalidad para retroalimentación
        self._history: List[Dict[str, Any]] = []
        self._history_max = 50

    def wire(self, semantic_engine=None, smart_memory=None,
             macro_router=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if macro_router is not None:
            self._macro_router = macro_router

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye prompt para inferencia LLM de criticalidad."""
        if isinstance(input_data, CriticalityInput):
            op = input_data.operation
            goal = input_data.goal
            target = input_data.target
            context = input_data.context
            code_snippet = input_data.code_snippet
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""
            context = str(input_data)[:200]
            code_snippet = ""

        system = (
            "You are a criticality assessment engine. "
            "Rate how CRITICAL this operation is on a 1-3 scale:\n"
            "1 = FAST_STANDARD: safe read-only, simple query, explain\n"
            "2 = DEEP_MODERATE: creates code, modifies files, API changes\n"
            "3 = SURGICAL_CRITICAL: auth, crypto, payments, DB migration, "
            "security-sensitive operations\n\n"
            "Reply with ONLY a JSON object:\n"
            '{"level":1|2|3,"reason":"...","confidence":0.0-1.0}'
        )
        user = (
            f"Op:{op} Goal:{goal} Target:{target[:100]} "
            f"Ctx:{context[:150]} Code:{code_snippet[:100]}"
        )
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[CriticalityOutput]:
        """Parsea la respuesta del LLM a un CriticalityOutput."""
        cleaned = self.clean_llm_text(raw_response)
        json_data = self.extract_json(cleaned)

        if json_data and isinstance(json_data, dict):
            level = json_data.get("level", 2)
            if isinstance(level, str):
                level = STR_TO_LEVEL.get(level.lower(), 2)
            level = max(1, min(3, int(level)))

            reason = str(json_data.get("reason", "LLM inference"))[:200]
            confidence = float(json_data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])

            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "standard"),
                reason=reason,
                confidence=confidence,
                source="llm",
                adjustments=adjustments,
            )

        # Try to parse just a number
        num_match = re.search(r'[123]', cleaned)
        if num_match:
            level = int(num_match.group())
            adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])
            return CriticalityOutput(
                level=level,
                path=LEVEL_TO_PATH.get(level, "standard"),
                reason="LLM numeric response",
                confidence=0.4,
                source="llm",
                adjustments=adjustments,
            )

        return None

    def fallback(self, input_data: Any) -> CriticalityOutput:
        """
        Fallback determinista: Fusión Multi-Signal sin LLM.

        Combina señales de:
        1. Keywords críticos en target/context
        2. Operation type + Goal type
        3. SmartMemory importance (si disponible)
        4. MacroRouter AST topology (si disponible)
        """
        start = time.time()

        if isinstance(input_data, CriticalityInput):
            op = input_data.operation
            goal = input_data.goal
            target = input_data.target
            context = input_data.context
            code_snippet = input_data.code_snippet
            existing_level = input_data.existing_level
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""
            context = str(input_data)[:200]
            code_snippet = ""
            existing_level = None

        # ── Signal 1: Keyword analysis ──
        combined_text = f"{target} {context} {code_snippet}".lower()
        keyword_level = self._keyword_signal(combined_text)

        # ── Signal 2: Operation/Goal baseline ──
        op_level = OP_CRITICALITY_MAP.get(op, 1)
        goal_level = GOAL_CRITICALITY_MAP.get(goal, 1)
        baseline_level = max(op_level, goal_level)

        # ── Signal 3: SmartMemory importance ──
        memory_level = self._memory_signal(target, op, goal)

        # ── Signal 4: MacroRouter AST topology ──
        router_level = self._router_signal(target)

        # ── Signal 5: Historical pattern ──
        history_level = self._history_signal(op, target)

        # ── Fusión ponderada ──
        # Pesos: keyword(0.30) + baseline(0.25) + router(0.20) + memory(0.15) + history(0.10)
        signals = [
            (keyword_level, 0.30),
            (baseline_level, 0.25),
            (router_level, 0.20),
            (memory_level, 0.15),
            (history_level, 0.10),
        ]

        weighted_sum = sum(level * weight for level, weight in signals)
        total_weight = sum(w for _, w in signals)
        fused = weighted_sum / total_weight if total_weight > 0 else 2.0

        # Redondear al entero más cercano, con sesgo hacia arriba por seguridad
        level = min(3, max(1, int(fused + 0.4)))

        # Si hay una señal existente del MacroRouter, no bajar su nivel
        if existing_level is not None:
            existing_int = STR_TO_LEVEL.get(str(existing_level).lower(),
                                            int(existing_level) if str(existing_level).isdigit() else 1)
            level = max(level, existing_int)

        # Generar razón explicativa
        reason = self._build_reason(level, keyword_level, baseline_level,
                                     router_level, memory_level, history_level)
        adjustments = CRITICALITY_ADJUSTMENTS.get(level, CRITICALITY_ADJUSTMENTS[2])
        confidence = self._compute_confidence(signals, level)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        # Registrar en historial para retroalimentación
        self._record_history(op, goal, target, level)

        return CriticalityOutput(
            level=level,
            path=LEVEL_TO_PATH.get(level, "standard"),
            reason=reason,
            confidence=confidence,
            source="fallback",
            adjustments=adjustments,
        )

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def assess_with_runner(self, runner: Any, intent_output: Any,
                           message: str = "",
                           existing_criticality: Any = None) -> CriticalityOutput:
        """
        Evalúa criticalidad usando AgentRunner (LLM → fallback).

        Args:
            runner: AgentRunner con MiniAI engine
            intent_output: IntentOutput de SurgicalAgent (F2)
            message: Mensaje original del usuario
            existing_criticality: Criticalidad existente del MacroRouter

        Returns:
            CriticalityOutput unificado
        """
        # Normalizar existing_criticality a int
        existing_int = None
        if existing_criticality is not None:
            try:
                existing_int = STR_TO_LEVEL.get(
                    str(existing_criticality).lower(),
                    int(float(existing_criticality)),
                )
            except (ValueError, TypeError):
                existing_int = None

        # Extraer información del intent_output
        if isinstance(intent_output, IntentOutput):
            op = intent_output.operation
            goal = intent_output.goal
            target = intent_output.target
        elif intent_output and hasattr(intent_output, 'op'):
            op = getattr(intent_output, 'op', 'SEARCH')
            goal = getattr(intent_output, 'goal', 'FEATURE_ADD')
            target = getattr(intent_output, 'target', '')
        else:
            op = "SEARCH"
            goal = "FEATURE_ADD"
            target = ""

        input_data = CriticalityInput(
            operation=op,
            goal=goal,
            target=target,
            context=message[:300],
            code_snippet="",
            existing_level=existing_int,
        )

        # Intentar LLM si runner disponible
        if runner:
            try:
                result: AgentResult = runner.run(self, input_data)
                if result.success and isinstance(result.data, CriticalityOutput):
                    # No permitir que el LLM baje la criticalidad del MacroRouter
                    if existing_int is not None and result.data.level < existing_int:
                        result.data.level = existing_int
                        result.data.path = LEVEL_TO_PATH.get(existing_int, "standard")
                        result.data.adjustments = CRITICALITY_ADJUSTMENTS.get(
                            existing_int, CRITICALITY_ADJUSTMENTS[2]
                        )
                        result.data.reason += " (elevated by MacroRouter signal)"
                    # Registrar en historial
                    self._record_history(op, goal, target, result.data.level)
                    return result.data
            except Exception as e:
                logger.debug(f"CriticalityAgent LLM failed: {e}")

        # Fallback determinista
        return self.fallback(input_data)

    def assess_deterministic(self, operation: str, goal: str,
                             target: str = "", context: str = "",
                             existing_criticality: Any = None) -> CriticalityOutput:
        """
        Evaluación determinista directa (sin LLM).

        Útil para cuando no hay AgentRunner disponible o para
        evaluación rápida en el pipeline.
        """
        existing_int = None
        if existing_criticality is not None:
            existing_int = STR_TO_LEVEL.get(
                str(existing_criticality).lower(),
                int(existing_criticality) if str(existing_criticality).isdigit() else None
            )

        input_data = CriticalityInput(
            operation=operation,
            goal=goal,
            target=target,
            context=context[:300],
            existing_level=existing_int,
        )
        return self.fallback(input_data)

    @staticmethod
    def normalize_criticality(raw_value: Any) -> int:
        """
        Normaliza cualquier formato de criticalidad a int (1/2/3).

        Resuelve el type mismatch:
        - "standard"/"moderate"/"critical" → 1/2/3
        - "FAST_STANDARD"/"DEEP_MODERATE"/"SURGICAL_CRITICAL" → 1/2/3
        - 1/2/3 → 1/2/3
        - None → 2 (DEEP_MODERATE por defecto)
        """
        if raw_value is None:
            return LEVEL_MODERATE

        if isinstance(raw_value, int):
            return max(1, min(3, raw_value))

        return STR_TO_LEVEL.get(str(raw_value).lower(), LEVEL_MODERATE)

    @staticmethod
    def level_to_path(level: int) -> str:
        """Convierte nivel de criticalidad a DAG path."""
        return LEVEL_TO_PATH.get(level, "standard")

    # ============================================================
    #  SIGNAL METHODS (Multi-Signal Fusion)
    # ============================================================

    def _keyword_signal(self, combined_text: str) -> int:
        """Señal 1: Análisis de keywords críticos en texto combinado."""
        critical_hits = sum(1 for kw in CRITICAL_KEYWORDS if kw in combined_text)
        moderate_hits = sum(1 for kw in MODERATE_KEYWORDS if kw in combined_text)

        if critical_hits >= 2:
            return LEVEL_SURGICAL
        elif critical_hits >= 1:
            return LEVEL_MODERATE  # One critical keyword = at least moderate
        elif moderate_hits >= 2:
            return LEVEL_MODERATE
        elif moderate_hits >= 1:
            return max(LEVEL_FAST, LEVEL_MODERATE - 1)
        return LEVEL_FAST

    def _memory_signal(self, target: str, op: str, goal: str) -> int:
        """Señal 3: SmartMemory importance score."""
        if not self._smart_memory:
            return LEVEL_MODERATE  # Sin memoria → asumir moderado

        try:
            from src.core.smart_memory import SmartMemory
            importance = SmartMemory.compute_importance(
                target or "unknown", op, goal, success=True, response_length=0
            )
            # importance 0-1: mapear a criticalidad
            if importance >= 0.7:
                return LEVEL_SURGICAL
            elif importance >= 0.4:
                return LEVEL_MODERATE
            return LEVEL_FAST
        except Exception:
            return LEVEL_MODERATE

    def _router_signal(self, target: str) -> int:
        """Señal 4: MacroRouter AST topology check."""
        if not self._macro_router:
            return LEVEL_FAST

        try:
            # Crear un IntentPayload temporal para consultar MacroRouter
            from src.core.shared.contracts import IntentPayload, CriticalityLevel
            temp_intent = IntentPayload(target=target or "unknown")
            routing = self._macro_router.route(temp_intent)
            return routing.criticality
        except Exception:
            return LEVEL_FAST

    def _history_signal(self, op: str, target: str) -> int:
        """Señal 5: Patrones históricos de criticalidad."""
        if not self._history:
            return LEVEL_FAST

        target_lower = (target or "").lower()
        matching = [
            h for h in self._history
            if h.get("op") == op or target_lower in h.get("target", "").lower()
        ]

        if not matching:
            return LEVEL_FAST

        avg_level = sum(h.get("level", 1) for h in matching) / len(matching)
        return min(3, max(1, int(avg_level + 0.5)))

    def _compute_confidence(self, signals: List[Tuple[int, float]],
                            final_level: int) -> float:
        """Computa confianza basada en concordancia de señales."""
        if not signals:
            return 0.3

        # Contar señales que concuerdan con el nivel final
        agreeing = sum(1 for level, _ in signals if level == final_level)
        total = len(signals)
        agreement_ratio = agreeing / total if total > 0 else 0

        # Más señales que concuerdan → más confianza
        confidence = 0.3 + (agreement_ratio * 0.6)

        # Si todas concuerdan, confianza muy alta
        if agreement_ratio == 1.0:
            confidence = 0.95

        return max(0.2, min(0.99, confidence))

    def _build_reason(self, level: int, kw: int, baseline: int,
                      router: int, memory: int, history: int) -> str:
        """Construye razón explicativa de la criticalidad."""
        level_names = {1: "FAST_STANDARD", 2: "DEEP_MODERATE", 3: "SURGICAL_CRITICAL"}
        parts = [f"Level {level} ({level_names.get(level, 'UNKNOWN')})"]

        signals = {
            "keyword": kw, "baseline": baseline, "router": router,
            "memory": memory, "history": history,
        }
        elevating = [k for k, v in signals.items() if v >= level]
        if elevating:
            parts.append(f"elevated by: {', '.join(elevating)}")

        if level == 3:
            parts.append("Full pipeline + Z3 solver + security checks required")
        elif level == 2:
            parts.append("Standard pipeline with validation")
        else:
            parts.append("Fast path, minimal overhead")

        return ". ".join(parts)

    def _record_history(self, op: str, goal: str, target: str,
                        level: int) -> None:
        """Registra evaluación en historial para retroalimentación."""
        self._history.append({
            "op": op, "goal": goal, "target": target[:100],
            "level": level, "timestamp": time.time(),
        })
        # Mantener historial acotado
        if len(self._history) > self._history_max:
            self._history = self._history[-self._history_max:]
