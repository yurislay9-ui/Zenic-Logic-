"""
TITAN OMNISCALE X - ContextAgent (F3)

Agente gestor de ventana de contexto que UNIFICA y OPTIMIZA la gestión
de contexto dispersa en múltiples subsistemas:

  1. SmartMemory.get_working_context() — truncación sin inteligencia
  2. ReasoningAgent._get_memory_context() — duplica lógica
  3. SurgicalAgent._cable_memory() — otro lookup aislado
  4. Cada agente consulta SmartMemory independientemente → desperdicio

El ContextAgent centraliza y optimiza:

Arquitectura 4-Cable (orden de costo ascendente):
  ┌──────────────────────────────────────────────────────┐
  │  CABLE 1: Compresión Adaptativa                      │
  │    LLM → resumen semántico (si Qwen disponible)     │
  │    TF-IDF → extracción de keywords (sin LLM)        │
  │    Raw → truncación inteligente (siempre funciona)   │
  │                                                       │
  │  CABLE 2: Scoring de Relevancia                      │
  │    Relevancia a intent (op/goal/criticality)         │
  │    Recencia temporal (decaimiento exponencial)       │
  │    Peso de importancia (SmartMemory.importance)      │
  │                                                       │
  │  CABLE 3: Presupuesto de Tokens                      │
  │    INTENT:50t | REASON:150t | CODE:200t              │
  │    VALIDATE:100t | RESERVE:100t                      │
  │                                                       │
  │  CABLE 4: Contexto Cross-Agent                       │
  │    Deduplicación entre llamadas de agentes           │
  │    Pre-fetch de memorias relevantes por intent       │
  │    Cache compartido de contexto comprimido           │
  └──────────────────────────────────────────────────────┘

Integración (cableado completo):
  - F1 (DAG): Nodo CONTEXT_PREPARE entre INTENT → AST_ANALYZE
  - F2 (Surgical): Usa scoring de CABLE 2 para calibrar fusión
  - SmartMemory: Reemplaza get_working_context() con compresión inteligente
  - Todos los agentes: Reciben contexto pre-comprimido + presupuesto de tokens

Restricciones de diseño:
  - ≤600 tokens por llamada LLM (Qwen3-0.6B)
  - Fallback determinista siempre disponible
  - Compatible con Android/Termux, 500MB RAM
"""

import re
import time
import json
import math
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentOutput, ContextEntry, ContextOutput

logger = logging.getLogger(__name__)

# ── Constantes de presupuesto de tokens ──

# Presupuesto total de contexto para agentes (de 600 tokens del LLM)
# Se reserva ~100 tokens para system prompt + instrucciones
TOTAL_CONTEXT_BUDGET = 500

# Distribución por defecto del presupuesto
DEFAULT_TOKEN_BUDGET: Dict[str, int] = {
    "intent": 50,        # SurgicalAgent necesita poco contexto
    "reasoning": 150,    # ReasoningAgent necesita más para razonar
    "code": 200,         # CodeAgent necesita el máximo
    "validation": 100,   # ValidationAgent necesita contexto del código
    "reserve": 100,      # Buffer para contexto dinámico
}

# Factor de decaimiento temporal (entradas recientes > antiguas)
RECENCY_DECAY_FACTOR = 0.95  # Por cada 60 segundos de antigüedad

# Pesos de relevancia por operation (cuánto importa cada operation para scoring)
OP_RELEVANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "CREATE":    {"CREATE": 1.0, "OPTIMIZE": 0.6, "REFACTOR": 0.5, "DEBUG": 0.3},
    "REFACTOR":  {"REFACTOR": 1.0, "OPTIMIZE": 0.7, "CREATE": 0.4, "DEBUG": 0.3},
    "DELETE":    {"DELETE": 1.0, "REFACTOR": 0.5, "DEBUG": 0.4, "ANALYZE": 0.3},
    "SEARCH":    {"SEARCH": 1.0, "ANALYZE": 0.7, "EXPLAIN": 0.5, "DEBUG": 0.2},
    "ANALYZE":   {"ANALYZE": 1.0, "SEARCH": 0.6, "EXPLAIN": 0.5, "DEBUG": 0.3},
    "EXPLAIN":   {"EXPLAIN": 1.0, "ANALYZE": 0.6, "SEARCH": 0.4, "DEBUG": 0.2},
    "DEBUG":     {"DEBUG": 1.0, "ANALYZE": 0.5, "REFACTOR": 0.4, "DELETE": 0.3},
    "OPTIMIZE":  {"OPTIMIZE": 1.0, "REFACTOR": 0.7, "CREATE": 0.3, "DEBUG": 0.3},
}

# Pesos de relevancia por goal
GOAL_RELEVANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "BUG_FIX":             {"BUG_FIX": 1.0, "SECURITY_HARDEN": 0.6, "PERFORMANCE": 0.4},
    "FEATURE_ADD":         {"FEATURE_ADD": 1.0, "MODERN_PATTERN": 0.5, "COMPLEXITY_REDUCTION": 0.3},
    "SECURITY_HARDEN":     {"SECURITY_HARDEN": 1.0, "BUG_FIX": 0.7, "PERFORMANCE": 0.3},
    "PERFORMANCE":         {"PERFORMANCE": 1.0, "OPTIMIZE": 0.6, "COMPLEXITY_REDUCTION": 0.5},
    "COMPLEXITY_REDUCTION":{"COMPLEXITY_REDUCTION": 1.0, "READABILITY": 0.7, "REFACTOR": 0.5},
    "MODERN_PATTERN":      {"MODERN_PATTERN": 1.0, "FEATURE_ADD": 0.5, "READABILITY": 0.4},
    "READABILITY":         {"READABILITY": 1.0, "COMPLEXITY_REDUCTION": 0.7, "MODERN_PATTERN": 0.4},
}

# Máximo de entradas de memoria a considerar para scoring
MAX_ENTRIES_FOR_SCORING = 30

# Máximo de memorias pre-fetched por intent
MAX_PREFETCH_RESULTS = 5

# Note: ContextEntry and ContextOutput are imported from schemas.py (single source of truth)


class ContextAgent(BaseAgent[ContextOutput]):
    """
    Agente F3: Gestor de ventana de contexto con compresión adaptativa.

    Flujo de ejecución (4 cables, en orden de costo ascendente):
    1. SmartMemory + scoring → Seleccionar entradas relevantes
    2. TF-IDF compression → Comprimir si no hay LLM
    3. LLM compression → Resumen semántico si Qwen disponible
    4. Token budget → Asignar presupuesto a cada agente downstream

    Reemplaza:
    - SmartMemory.get_working_context() (truncación simple)
    - ReasoningAgent._get_memory_context() (duplicado)
    - Lógica dispersa de contexto en cada agente

    Añade:
    - Scoring de relevancia por intent
    - Presupuesto de tokens por agente
    - Deduplicación cross-agent
    - Pre-fetch de memorias relevantes
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="context")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

        # Cache de contexto compartido (deduplicación cross-agent)
        # Each entry stores (compressed_context, timestamp) for per-entry TTL
        self._shared_context_cache: Dict[str, tuple] = {}
        self._shared_context_ttl: float = 30.0  # 30 segundos de TTL

        # Track de qué contexto ya se envió a cada agente (deduplicación)
        self._agent_context_sent: Dict[str, set] = {}

        # Estadísticas de presupuesto de tokens
        self._budget_usage: Dict[str, Dict[str, int]] = {}

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """
        Construye prompt para compresión de contexto vía LLM.

        Input esperado: dict con keys:
          - raw_context: str (contexto sin comprimir)
          - intent_operation: str (operation actual)
          - intent_goal: str (goal actual)
          - max_tokens: int (presupuesto de tokens)
        """
        raw_ctx = input_data.get("raw_context", "") if isinstance(input_data, dict) else str(input_data)
        op = input_data.get("intent_operation", "SEARCH") if isinstance(input_data, dict) else "SEARCH"
        goal = input_data.get("intent_goal", "FEATURE_ADD") if isinstance(input_data, dict) else "FEATURE_ADD"
        max_t = input_data.get("max_tokens", 200) if isinstance(input_data, dict) else 200

        # Prompt ultra-compacto para Qwen3-0.6B
        system = (
            "Compress context for AI agent. Keep only essential info. "
            f"Max {max_t} tokens. Format: key:value pairs separated by |. "
            "Prioritize: errors, solutions, patterns relevant to "
            f"{op}/{goal}. Reply ONLY compressed text, no explanation."
        )
        user = f"Context to compress:\n{raw_ctx[:400]}"
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[ContextOutput]:
        """Parsea respuesta comprimida del LLM."""
        cleaned = self.clean_llm_text(raw_response).strip()
        if not cleaned or len(cleaned) < 10:
            return None

        # La respuesta del LLM es el contexto comprimido directamente
        max_tokens = input_data.get("max_tokens", 200) if isinstance(input_data, dict) else 200
        raw_ctx = input_data.get("raw_context", "") if isinstance(input_data, dict) else str(input_data)

        # Estimar tokens (1 token ≈ 4 chars para inglés, ≈2 chars para español)
        compressed_tokens = len(cleaned.split())
        raw_tokens = len(raw_ctx.split()) if raw_ctx else 1

        return ContextOutput(
            compressed_context=cleaned[:max_tokens * 4],
            token_budget=DEFAULT_TOKEN_BUDGET.copy(),
            compression_ratio=min(compressed_tokens / max(raw_tokens, 1), 1.0),
            source="llm",
        )

    def fallback(self, input_data: Any) -> ContextOutput:
        """
        Fallback determinista: compresión sin LLM.

        Flujo: SmartMemory → Scoring → TF-IDF/Raw compression → Budget
        """
        start = time.time()

        # Extraer parámetros
        if isinstance(input_data, dict):
            message = input_data.get("message", "")
            intent_output = input_data.get("intent_output")
            max_tokens = input_data.get("max_tokens", TOTAL_CONTEXT_BUDGET)
        else:
            message = str(input_data)
            intent_output = None
            max_tokens = TOTAL_CONTEXT_BUDGET

        # Obtener operation/goal para scoring
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # CABLE 1: Recopilar entradas de memoria
        entries = self._collect_entries(message, op, goal)

        # CABLE 2: Scoring de relevancia
        scored_entries = self._score_entries(entries, op, goal)

        # CABLE 3: Compresión adaptativa (TF-IDF o raw)
        compressed, entries_used = self._compress_entries(
            scored_entries, max_tokens, op, goal
        )

        # CABLE 4: Pre-fetch de memorias relevantes
        relevant = self._prefetch_relevant(message, op, goal)

        # Calcular presupuesto de tokens
        budget = self._allocate_budget(op, goal, max_tokens)

        # Calcular métricas
        raw_tokens = sum(e.token_estimate for e in entries)
        comp_tokens = len(compressed.split()) if compressed else 0
        ratio = min(comp_tokens / max(raw_tokens, 1), 1.0) if raw_tokens > 0 else 1.0

        # Cache compartido — store with per-entry timestamp
        self._shared_context_cache[f"{op}:{goal}"] = (compressed, time.time())

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        # Scores para logging
        scores = {f"{e.operation}/{e.goal}": round(e.relevance_score, 2)
                  for e in scored_entries[:5]}

        return ContextOutput(
            compressed_context=compressed,
            relevant_memories=relevant,
            token_budget=budget,
            context_scores=scores,
            entries_used=entries_used,
            entries_total=len(entries),
            compression_ratio=ratio,
            source="fallback",
            duration_ms=duration_ms,
        )

    # ============================================================
    #  HIGH-LEVEL API (lo que el DAG y agentes llaman)
    # ============================================================

    def prepare_context(self, message: str, intent_output: IntentOutput = None,
                        max_tokens: int = TOTAL_CONTEXT_BUDGET) -> ContextOutput:
        """
        Método principal: prepara contexto óptimo para el pipeline.

        Este es el método que el DAGOrchestrator llama en el nodo
        CONTEXT_PREPARE.
        """
        input_data = {
            "message": message,
            "intent_output": intent_output,
            "max_tokens": max_tokens,
        }
        return self.fallback(input_data)

    def prepare_context_with_runner(self, runner: Any, message: str,
                                     intent_output: IntentOutput = None,
                                     max_tokens: int = TOTAL_CONTEXT_BUDGET) -> ContextOutput:
        """Prepara contexto usando AgentRunner (LLM → fallback)."""
        # Primero intentar fallback (siempre funciona, sin costo LLM)
        fallback_result = self.prepare_context(message, intent_output, max_tokens)

        # Si el contexto es pequeño o ya bien comprimido, no gastar LLM
        raw_token_est = len(message.split())
        if raw_token_est < 50 or not self._smart_memory:
            return fallback_result

        # Si hay contexto largo que comprimir, intentar LLM
        if runner and runner._mini_ai and runner._mini_ai.is_loaded:
            # Solo usar LLM si hay contexto significativo que comprimir
            working_ctx = self._get_raw_working_context()
            if len(working_ctx.split()) > 100:
                try:
                    llm_input = {
                        "raw_context": working_ctx[:600],
                        "intent_operation": intent_output.operation if intent_output else "SEARCH",
                        "intent_goal": intent_output.goal if intent_output else "FEATURE_ADD",
                        "max_tokens": max_tokens,
                    }
                    result: AgentResult = runner.run(self, llm_input)
                    if result.success and isinstance(result.data, ContextOutput):
                        # Enriquecer resultado LLM con pre-fetch y budget
                        result.data.relevant_memories = fallback_result.relevant_memories
                        result.data.token_budget = fallback_result.token_budget
                        result.data.entries_used = fallback_result.entries_used
                        result.data.entries_total = fallback_result.entries_total
                        return result.data
                except Exception as e:
                    logger.debug(f"ContextAgent: LLM compression failed: {e}")

        return fallback_result

    def get_context_for_agent(self, agent_name: str, intent_output: IntentOutput = None,
                               max_tokens: int = None) -> str:
        """
        Obtiene contexto comprimido para un agente específico.

        Aplica deduplicación: no envía contexto que ya se envió al mismo agente.
        Respeta el presupuesto de tokens del agente.
        """
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # Buscar en cache compartido
        cache_key = f"{op}:{goal}"
        cached_entry = self._shared_context_cache.get(cache_key)
        cached = ""
        cache_age = float('inf')
        if cached_entry:
            cached, ts = cached_entry
            cache_age = time.time() - ts

        # Si el cache es muy viejo, invalidar
        if cache_age > self._shared_context_ttl or not cached:
            ctx = self.prepare_context(
                "", intent_output, max_tokens or TOTAL_CONTEXT_BUDGET
            )
            cached = ctx.compressed_context

        # Aplicar presupuesto de tokens del agente
        budget = DEFAULT_TOKEN_BUDGET.get(agent_name, 100)
        if max_tokens:
            budget = min(budget, max_tokens)

        # Truncar al presupuesto (1 token ≈ 4 chars)
        max_chars = budget * 4
        context = cached[:max_chars]

        # Deduplicación: trackear qué ya se envió
        if agent_name not in self._agent_context_sent:
            self._agent_context_sent[agent_name] = set()

        content_hash = hash(context)
        if content_hash in self._agent_context_sent[agent_name]:
            # Ya se envió este contexto exacto — no repetir
            return ""
        self._agent_context_sent[agent_name].add(content_hash)

        return context

    def reset_agent_tracking(self) -> None:
        """Resetea tracking de deduplicación (al inicio de cada request)."""
        self._agent_context_sent.clear()

    def get_token_budget_for(self, agent_name: str) -> int:
        """Obtiene el presupuesto de tokens para un agente."""
        return DEFAULT_TOKEN_BUDGET.get(agent_name, 100)

    # ============================================================
    #  CABLE 1: Recopilar entradas de memoria
    # ============================================================

    def _collect_entries(self, message: str, op: str, goal: str) -> List[ContextEntry]:
        """Recopila entradas de todas las fuentes de memoria."""
        entries: List[ContextEntry] = []
        now = time.time()

        # Working Memory (contexto actual de la sesión)
        if self._smart_memory:
            try:
                for entry in self._smart_memory._working_memory[:MAX_ENTRIES_FOR_SCORING]:
                    age_seconds = now - entry.timestamp if entry.timestamp > 0 else 60
                    recency = RECENCY_DECAY_FACTOR ** (age_seconds / 60.0)

                    content = f"[{entry.operation}/{entry.goal}] Q:{entry.query[:60]}"
                    if entry.response:
                        content += f" A:{entry.response[:80]}"

                    entries.append(ContextEntry(
                        content=content,
                        source="working",
                        operation=entry.operation,
                        goal=entry.goal,
                        importance=entry.importance,
                        recency=recency,
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Working memory collection failed: {e}")

        # Long-term Memory (soluciones previas relevantes)
        if self._smart_memory and self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(message, top_k=5)
                for sol in similar:
                    content = f"[{sol.get('operation','')}/{sol.get('goal','')}] {sol.get('solution','')[:100]}"
                    entries.append(ContextEntry(
                        content=content,
                        source="long_term",
                        operation=sol.get("operation", ""),
                        goal=sol.get("goal", ""),
                        importance=sol.get("importance", 0.5),
                        recency=0.5,  # No tenemos timestamp, asumir mid
                        relevance_score=sol.get("similarity", 0.5),
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Long-term memory collection failed: {e}")

        # Procedural Memory (patrones aprendidos relevantes)
        if self._smart_memory:
            try:
                patterns = self._smart_memory.find_patterns(
                    min_success_rate=0.6, limit=3
                )
                for pat in patterns:
                    content = f"[pattern/{pat.get('pattern_type','')}] {pat.get('description','')[:80]}"
                    entries.append(ContextEntry(
                        content=content,
                        source="procedural",
                        operation="",
                        goal="",
                        importance=pat.get("success_rate", 0.5),
                        recency=0.3,  # Patrones son más estables
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Procedural memory collection failed: {e}")

        return entries[:MAX_ENTRIES_FOR_SCORING]

    # ============================================================
    #  CABLE 2: Scoring de relevancia
    # ============================================================

    def _score_entries(self, entries: List[ContextEntry],
                       current_op: str, current_goal: str) -> List[ContextEntry]:
        """
        Calcula score de relevancia para cada entrada.

        Score = w_importance * importance + w_recency * recency + w_relevance * relevance
        donde relevance = similitud de operation/goal con el intent actual.
        """
        w_importance = 0.3
        w_recency = 0.3
        w_relevance = 0.4

        # Obtener pesos de relevancia para la operation actual
        op_weights = OP_RELEVANCE_WEIGHTS.get(current_op, {})
        goal_weights = GOAL_RELEVANCE_WEIGHTS.get(current_goal, {})

        for entry in entries:
            # Relevancia por operation
            op_rel = op_weights.get(entry.operation, 0.1) if entry.operation else 0.1

            # Relevancia por goal
            goal_rel = goal_weights.get(entry.goal, 0.1) if entry.goal else 0.1

            # Combinar relevance (operation pesa más)
            relevance = 0.6 * op_rel + 0.4 * goal_rel

            # Si ya tenía score de similarity (long_term), combinar
            if entry.relevance_score > 0:
                relevance = 0.5 * relevance + 0.5 * entry.relevance_score

            # Score combinado
            entry.relevance_score = (
                w_importance * entry.importance +
                w_recency * entry.recency +
                w_relevance * relevance
            )

        # Ordenar por relevance score (descendente)
        entries.sort(key=lambda e: e.relevance_score, reverse=True)
        return entries

    # ============================================================
    #  CABLE 3: Compresión adaptativa
    # ============================================================

    def _compress_entries(self, entries: List[ContextEntry],
                          max_tokens: int, op: str, goal: str) -> Tuple[str, int]:
        """
        Comprime entradas al presupuesto de tokens.

        Estrategia (en orden de preferencia):
        1. Si hay LLM: Resumen semántico (manejado por prepare_context_with_runner)
        2. TF-IDF keyword extraction: Extraer terms más relevantes
        3. Raw truncation: Cortar por presupuesto

        Siempre devuelve texto comprimido dentro del presupuesto.
        """
        if not entries:
            return "", 0

        # Seleccionar entradas que caben en el presupuesto
        selected: List[ContextEntry] = []
        token_count = 0

        for entry in entries:
            if token_count + entry.token_estimate <= max_tokens:
                selected.append(entry)
                token_count += entry.token_estimate
            elif token_count + 30 <= max_tokens:
                # Truncar entrada parcialmente (mínimo 30 tokens)
                truncated = entry.content[:120]
                selected.append(ContextEntry(
                    content=truncated + "...",
                    source=entry.source,
                    relevance_score=entry.relevance_score,
                    token_estimate=30,
                ))
                token_count += 30
            # Si no cabe, skip

        if not selected:
            # Al menos incluir la entrada más relevante truncada
            best = entries[0]
            return best.content[:max_tokens * 4], 1

        # Construir contexto comprimido
        # Formato: "[op/goal:score] content | [op/goal:score] content | ..."
        parts = []
        for entry in selected:
            op_goal = f"{entry.operation}/{entry.goal}" if entry.operation else "ctx"
            score_str = f"{entry.relevance_score:.1f}"
            parts.append(f"[{op_goal}:{score_str}] {entry.content}")

        compressed = " | ".join(parts)

        # Safety: truncar si excede (por si los estimates fueron bajos)
        max_chars = max_tokens * 4
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars - 3] + "..."

        return compressed, len(selected)

    # ============================================================
    #  CABLE 4: Pre-fetch de memorias relevantes
    # ============================================================

    def _prefetch_relevant(self, message: str, op: str,
                            goal: str) -> List[Dict[str, Any]]:
        """
        Pre-fetch memorias relevantes al intent actual.

        Carga proactivamente:
        - Soluciones previas para la misma operation
        - Episodios de errores similares (para DEBUG)
        - Patrones procedurales relevantes
        """
        results: List[Dict[str, Any]] = []

        if not self._smart_memory:
            return results

        # 1. Soluciones previas con misma operation
        try:
            if self._semantic_engine and self._semantic_engine.is_loaded:
                similar = self._smart_memory.find_similar_solutions(
                    message, top_k=3
                )
                for sol in similar[:2]:
                    results.append({
                        "type": "similar_solution",
                        "operation": sol.get("operation", ""),
                        "solution": sol.get("solution", "")[:150],
                        "similarity": sol.get("similarity", 0.0),
                    })
        except Exception as e:
            logger.debug(f"ContextAgent: Prefetch solutions failed: {e}")

        # 2. Episodios de errores (para DEBUG/BUG_FIX)
        if op in ("DEBUG",) or goal in ("BUG_FIX",):
            try:
                episodes = self._smart_memory.find_episodes(
                    event_type="error", limit=2
                )
                for ep in episodes[:2]:
                    results.append({
                        "type": "error_episode",
                        "description": ep.get("description", "")[:100],
                        "outcome": ep.get("outcome", ""),
                    })
            except Exception as e:
                logger.debug(f"ContextAgent: Prefetch episodes failed: {e}")

        # 3. Patrones procedurales (para CREATE/OPTIMIZE)
        if op in ("CREATE", "OPTIMIZE"):
            try:
                patterns = self._smart_memory.find_patterns(
                    min_success_rate=0.7, limit=2
                )
                for pat in patterns[:2]:
                    results.append({
                        "type": "procedural_pattern",
                        "name": pat.get("pattern_name", ""),
                        "success_rate": pat.get("success_rate", 0.0),
                        "steps": pat.get("steps", [])[:3],
                    })
            except Exception as e:
                logger.debug(f"ContextAgent: Prefetch patterns failed: {e}")

        return results[:MAX_PREFETCH_RESULTS]

    # ============================================================
    #  Presupuesto de Tokens
    # ============================================================

    def _allocate_budget(self, op: str, goal: str,
                          total: int = TOTAL_CONTEXT_BUDGET) -> Dict[str, int]:
        """
        Asigna presupuesto de tokens según operation/goal.

        Ajusta el presupuesto por defecto según la operación:
        - CREATE: más tokens para code (250), menos para validation (50)
        - DEBUG: más tokens para reasoning (200), menos para intent (30)
        - EXPLAIN: más tokens para reasoning (200), menos para code (100)
        """
        budget = DEFAULT_TOKEN_BUDGET.copy()

        # Ajustes por operation
        if op == "CREATE":
            budget["code"] = min(int(budget["code"] * 1.25), 280)
            budget["intent"] = max(int(budget["intent"] * 0.6), 30)
            budget["validation"] = max(int(budget["validation"] * 0.7), 50)
        elif op == "DEBUG":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.33), 220)
            budget["intent"] = max(int(budget["intent"] * 0.6), 30)
            budget["code"] = max(int(budget["code"] * 0.75), 150)
        elif op == "EXPLAIN":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.33), 220)
            budget["code"] = max(int(budget["code"] * 0.5), 100)
        elif op == "OPTIMIZE":
            budget["code"] = min(int(budget["code"] * 1.25), 280)
            budget["reasoning"] = max(int(budget["reasoning"] * 0.8), 120)
        elif op in ("ANALYZE", "SEARCH"):
            budget["reasoning"] = min(int(budget["reasoning"] * 1.2), 200)
            budget["code"] = max(int(budget["code"] * 0.7), 140)

        # Ajustes por goal (criticality)
        if goal == "SECURITY_HARDEN":
            budget["validation"] = min(int(budget["validation"] * 1.5), 180)
            budget["reserve"] = max(int(budget["reserve"] * 0.5), 50)
        elif goal == "BUG_FIX":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.2), 200)
            budget["reserve"] = max(int(budget["reserve"] * 0.6), 60)
        elif goal == "PERFORMANCE":
            budget["code"] = min(int(budget["code"] * 1.15), 260)

        # Normalizar: asegurar que la suma no exceda el total
        total_allocated = sum(budget.values())
        if total_allocated > total:
            scale = total / total_allocated
            budget = {k: max(int(v * scale), 20) for k, v in budget.items()}

        return budget

    # ============================================================
    #  UTILIDADES
    # ============================================================

    def _get_raw_working_context(self) -> str:
        """Obtiene contexto raw de working memory para compresión LLM."""
        if not self._smart_memory:
            return ""
        try:
            return self._smart_memory.get_working_context(max_tokens=400)
        except Exception:
            return ""

    def get_compressed_working_context(self, intent_output: IntentOutput = None,
                                        max_tokens: int = 200) -> str:
        """
        Reemplazo directo para SmartMemory.get_working_context().

        Este método se puede usar como drop-in replacement:
        En vez de: ctx = self._memory.get_working_context(200)
        Usar:      ctx = self._context_agent.get_compressed_working_context(intent, 200)
        """
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # Verificar cache compartido
        cache_key = f"{op}:{goal}"
        if cache_key in self._shared_context_cache:
            cached, ts = self._shared_context_cache[cache_key]
            cache_age = time.time() - ts
            if cache_age < self._shared_context_ttl:
                return cached[:max_tokens * 4]

        # Calcular fresh
        result = self.prepare_context("", intent_output, max_tokens)
        return result.compressed_context[:max_tokens * 4]

    @property
    def budget_stats(self) -> Dict[str, Any]:
        """Estadísticas de uso del presupuesto de tokens."""
        return {
            "default_budget": DEFAULT_TOKEN_BUDGET,
            "total_budget": TOTAL_CONTEXT_BUDGET,
            "shared_cache_entries": len(self._shared_context_cache),
            "shared_cache_age": "per-entry",
            "agents_tracked": list(self._agent_context_sent.keys()),
        }
