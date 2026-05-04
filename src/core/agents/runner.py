"""
TITAN OMNISCALE X - AgentRunner

Ejecuta agentes IA con timeout, retry, fallback automático y cache.
Cableado directo al MiniAIEngine existente (Qwen3-0.6B).
"""

import time
import json
import threading
import logging
from typing import Any, Dict, Optional, TypeVar

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.cache import AgentCache

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Límites de seguridad para llamadas al LLM
MAX_TOKENS_AGENT = 600          # Max tokens por llamada de agente
AGENT_TIMEOUT_S = 10.0          # Timeout por llamada
MAX_RETRIES = 1                 # Reintentos antes de fallback
TEMPERATURE_AGENT = 0.15        # Temperatura baja = más determinista


class AgentRunner:
    """
    Ejecutor de agentes con manejo robusto de errores.

    Flujo:
    1. Check cache → si hit, devolver resultado cacheado
    2. Build prompt → llamar al LLM vía MiniAIEngine
    3. Parse response → validar contra esquema
    4. Si falla → retry (1 vez)
    5. Si falla de nuevo → fallback determinista
    6. Cache resultado exitoso
    """

    def __init__(self, mini_ai=None, semantic_engine=None,
                 smart_memory=None, enable_cache: bool = True) -> None:
        """
        Args:
            mini_ai: Instancia de MiniAIEngine (Qwen3-0.6B)
            semantic_engine: Instancia de SemanticEngine (para cache semántico)
            smart_memory: Instancia de SmartMemory (para contexto)
            enable_cache: Si True, cachear resultados exitosos
        """
        self._mini_ai = mini_ai
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._cache = AgentCache() if enable_cache else None
        self._enable_cache = enable_cache
        self._total_calls = 0
        self._cache_hits = 0
        self._llm_calls = 0
        self._fallback_calls = 0
        self._stats_lock = threading.Lock()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "cache_hits": self._cache_hits,
            "llm_calls": self._llm_calls,
            "fallback_calls": self._fallback_calls,
            "cache_hit_rate": self._cache_hits / max(self._total_calls, 1),
            "cache_size": len(self._cache) if self._cache else 0,
        }

    def run(self, agent: BaseAgent, input_data: Any) -> AgentResult:
        """
        Ejecuta un agente con el flujo completo: cache → LLM → parse → fallback.

        Args:
            agent: Instancia del agente a ejecutar
            input_data: Datos de entrada para el agente

        Returns:
            AgentResult con el resultado de la ejecución
        """
        with self._stats_lock:
            self._total_calls += 1
        start_time = time.time()

        # 1. Check cache
        if self._enable_cache and self._cache is not None:
            cached = self._cache.get(agent.name, input_data)
            if cached is not None:
                with self._stats_lock:
                    self._cache_hits += 1
                agent._update_stats("cache", 0)
                return AgentResult(
                    success=True, data=cached,
                    source="cache", duration_ms=0, cache_hit=True,
                )

        # 2. Try LLM with retry
        if self._mini_ai and self._mini_ai.is_loaded:
            result = self._try_llm(agent, input_data, start_time)
            if result is not None:
                return result

        # 3. Fallback determinista
        return self._run_fallback(agent, input_data, start_time)

    def _try_llm(self, agent: BaseAgent, input_data: Any,
                 start_time: float) -> Optional[AgentResult]:
        """Intenta ejecutar el agente con el LLM. Retorna None si falla."""
        try:
            system_prompt, user_prompt = agent.build_prompt(input_data)
        except Exception as e:
            logger.warning(f"Agent {agent.name}: build_prompt failed: {e}")
            return None

        for attempt in range(MAX_RETRIES + 1):
            with self._stats_lock:
                self._llm_calls += 1
            try:
                # Llamar al MiniAIEngine
                raw_response = self._mini_ai._call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=MAX_TOKENS_AGENT,
                )

                if not raw_response:
                    if attempt < MAX_RETRIES:
                        continue
                    return None

                # Parsear la respuesta
                parsed = agent.parse_response(raw_response, input_data)
                if parsed is None:
                    if attempt < MAX_RETRIES:
                        continue
                    return None

                # Validar el output
                if not agent.validate_output(parsed):
                    if attempt < MAX_RETRIES:
                        continue
                    return None

                # Éxito!
                duration_ms = int((time.time() - start_time) * 1000)
                agent._update_stats("llm", duration_ms)

                # Cachear resultado exitoso
                if self._enable_cache and self._cache is not None:
                    self._cache.put(agent.name, input_data, parsed)

                return AgentResult(
                    success=True, data=parsed,
                    source="llm", duration_ms=duration_ms,
                )

            except Exception as e:
                logger.warning(f"Agent {agent.name}: LLM attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES:
                    continue

        return None

    def _run_fallback(self, agent: BaseAgent, input_data: Any,
                      start_time: float) -> AgentResult:
        """Ejecuta el fallback determinista del agente."""
        with self._stats_lock:
            self._fallback_calls += 1
        try:
            fallback_result = agent.fallback(input_data)
            duration_ms = int((time.time() - start_time) * 1000)
            # Note: agent.fallback() already calls _update_stats internally,
            # so we don't call it again here to avoid double-counting.

            return AgentResult(
                success=True, data=fallback_result,
                source="fallback", duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # Note: agent.fallback() may have already called _update_stats
            # before raising, so we only update if it didn't.
            logger.error(f"Agent {agent.name}: Even fallback failed: {e}")

            return AgentResult(
                success=False, data=None,
                source="error", error=str(e), duration_ms=duration_ms,
            )

    def run_raw(self, system_prompt: str, user_prompt: str,
                max_tokens: int = MAX_TOKENS_AGENT) -> Optional[str]:
        """
        Ejecución directa del LLM sin agente. Para uso interno.
        Retorna el texto crudo de la respuesta o None.
        """
        if not self._mini_ai or not self._mini_ai.is_loaded:
            return None

        try:
            return self._mini_ai._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(f"AgentRunner.run_raw failed: {e}")
            return None

    def clear_cache(self) -> None:
        """Limpia la caché de resultados."""
        if self._cache:
            self._cache.clear()

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None) -> None:
        """Actualiza las referencias a los motores (para cableado en caliente)."""
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    @property
    def cache(self):
        """Public accessor for agent cache."""
        return getattr(self, '_cache', None)

    @property
    def mini_ai(self):
        """Public accessor for mini AI engine."""
        return getattr(self, '_mini_ai', None)
