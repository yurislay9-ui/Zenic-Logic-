"""
MiniAIEngine main class — v16.1 Verdict Architecture + Generative Capabilities.

CAMBIO FUNDAMENTAL (v16 → v17):
  ANTES: La IA hacía 7 tareas bounded (clasificar, extraer, generar, etc.)
  AHORA: La IA SOLO emite veredictos binarios (SÍ/NO) como árbitro final

CAMBIO v17 → v17.1:
  - Las 7 tareas bounded son ahora 100% determinísticas (NUNCA llaman al LLM)
  - El veredicto tiene Circuit Breaker, Retry con backoff, Health Monitor
  - Multi-attempt consensus: Pregunta 3 veces, mayoría gana
  - Auditoría completa de todas las decisiones

CAMBIO v16.1:
  - Añadido GenerativeMixin: el LLM ahora puede generar código, texto y
    completar código, más allá del veredicto binario YES/NO
  - VerdictMixin sigue como gate de validación para código generado
  - Patrones de uso: generate_code() → verdict() → aceptar/rechazar

Las 7 tareas originales ahora las hace código determinístico.
MiniAIEngine conserva los métodos legacy para compatibilidad,
pero internamente NUNCA llaman al LLM.

Métodos que usan la IA:
  - verdict(): Arbitraje binario SÍ/NO (resiliencia completa)
  - generate_code(): Generación de código desde descripción
  - generate_text(): Generación de texto
  - complete_code(): Completar código parcial
"""

from ._imports import IntentResult
from ._lifecycle import ModelLifecycleMixin
from ._tasks import BoundedTasksMixin
from ._fallbacks import FallbackMethodsMixin
from ._verdict_mixin import VerdictMixin
from ._generative_mixin import GenerativeMixin
from typing import Optional


class MiniAIEngine(ModelLifecycleMixin, BoundedTasksMixin, FallbackMethodsMixin, VerdictMixin, GenerativeMixin):
    """
    Motor de IA para ZENIC LOGIC v16.1 - Verdict + Generative Architecture.

    Filosofía (v16.1): La IA arbitra Y genera.
    - Veredicto: La IA solo responde SÍ/NO cuando hay empate en el consenso
    - Generación: La IA puede generar código, texto y completar código
    - Validación: Veredicto como gate de seguridad para código generado
    - Todas las tareas bounded siguen siendo 100% determinísticas

    Resiliencia (v17.1+):
    - Circuit Breaker: Si el LLM falla 3 veces, se abre
    - Retry con backoff: Reintento inteligente con delays crecientes
    - Multi-attempt consensus: 3 preguntas, mayoría gana
    - Health Monitor: Tracking de salud en tiempo real
    - Auditoría: Registro de todas las decisiones

    Compatibilidad:
    - Los 7 métodos bounded siguen funcionando (determinísticos, sin IA)
    - El método verdict() es el punto de entrada para arbitraje
    - generate_code() para generación de código con LLM
    - Los agentes que usaban _call_llm() siguen funcionando
    """

    def __init__(self, model_path: Optional[str] = None, auto_load: bool = True):
        self._init_lifecycle(model_path=model_path, auto_load=auto_load)
        self._init_verdict()
