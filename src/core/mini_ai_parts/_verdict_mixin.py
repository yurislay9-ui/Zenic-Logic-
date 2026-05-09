"""
VerdictMixin - Agrega la capacidad de veredicto binario al MiniAIEngine.

La IA SOLO puede responder YES o NO. Nada más.
Si la IA da una respuesta ambigua, se cuenta como NO.
Si la IA no responde (timeout), se cuenta como NO.

v17.1 MEJORAS DE RESILIENCIA:
  - Circuit Breaker: Protege contra LLM caído
  - Retry con exponential backoff: Reintento inteligente
  - Health Monitor: Seguimiento de salud del LLM
  - Multi-attempt consensus: Pregunta N veces, mayoría gana
  - Auditoría: Registro de todas las decisiones
  - Timeout cascade: Si el LLM está lento, se adapta
"""

import re
import os
import time
import logging
import concurrent.futures
from typing import Optional, Dict, Any, List

from ._imports import IntentResult, LLM_TIMEOUT_S

logger = logging.getLogger(__name__)

# === Configuración estricta para veredictos ===
VERDICT_MAX_TOKENS = 10          # Solo necesita 1 token
VERDICT_TEMPERATURE = 0.0        # Determinismo absoluto
VERDICT_TIMEOUT_S = 15.0         # Timeout por intento (was 5s, too short for ARM)
VERDICT_MAX_RETRIES = 3          # Reintentos con exponential backoff
VERDICT_BASE_DELAY = 1.0         # Delay base entre reintentos (segundos)
VERDICT_MAX_DELAY = 10.0         # Delay máximo entre reintentos
VERDICT_CONSENSUS_ATTEMPTS = int(os.environ.get("TITAN_VERDICT_CONSENSUS", "1"))  # ARM: 1 attempt (was 3, too many LLM timeouts)
VERDICT_CONSENSUS_THRESHOLD = 2  # Mínimo de YES para verdict YES

VERDICT_SYSTEM_PROMPT = (
    "You are a binary decision maker. "
    "Reply with ONLY one word: YES or NO. "
    "Never explain. Never add anything else."
)

# Importar patrones de resiliencia
try:
    from ..verdict_parts.resilience import (
        VerdictCircuitBreaker,
        VerdictRetryConfig,
        VerdictHealthMonitor,
        VerdictAuditor,
        VerdictAuditEntry,
        VerdictResilienceOrchestrator,
    )
    _RESILIENCE_AVAILABLE = True
except ImportError:
    _RESILIENCE_AVAILABLE = False


class VerdictMixin:
    """
    Mixin que agrega capacidad de veredicto binario al MiniAIEngine.

    El veredicto es la ÚNICA forma en que la IA participa en las decisiones.
    La IA nunca genera, nunca clasifica, nunca explica.
    Solo dice SÍ o NO.

    v17.1: Ahora con patrones de resiliencia:
      - Circuit Breaker: Si el LLM falla 3 veces, se abre y no se llama más
      - Retry con backoff: Reintento inteligente con delays crecientes
      - Multi-attempt consensus: Pregunta 3 veces, mayoría decide
      - Health monitoring: Tracking de salud del LLM
      - Auditoría: Registro de todas las decisiones
    """

    def _init_verdict(self):
        """Inicializa el subsistema de veredicto con resiliencia."""
        self._verdict_count = 0
        self._verdict_yes = 0
        self._verdict_no = 0
        self._verdict_fallback = 0
        self._verdict_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # v17.1: Resilience patterns
        if _RESILIENCE_AVAILABLE:
            self._verdict_resilience = VerdictResilienceOrchestrator(
                circuit_breaker=VerdictCircuitBreaker(
                    name="verdict_llm",
                    failure_threshold=3,
                    recovery_timeout=60.0,
                    half_open_max_calls=1,
                    success_threshold=2,
                ),
                health_monitor=VerdictHealthMonitor(
                    window_size=50,
                    unhealthy_threshold=0.3,
                ),
                auditor=VerdictAuditor(max_entries=100),
                retry_config=VerdictRetryConfig(
                    max_attempts=VERDICT_MAX_RETRIES,
                    base_delay=VERDICT_BASE_DELAY,
                    max_delay=VERDICT_MAX_DELAY,
                    timeout_per_attempt=VERDICT_TIMEOUT_S,
                ),
            )
        else:
            self._verdict_resilience = None

        logger.info(
            f"VerdictMixin: Initialized with resilience="
            f"{_RESILIENCE_AVAILABLE}, "
            f"max_retries={VERDICT_MAX_RETRIES}, "
            f"consensus_attempts={VERDICT_CONSENSUS_ATTEMPTS}"
        )

    def verdict(self, question: str, context: str = "",
                evidence_for: str = "", evidence_against: str = "",
                consensus_hint: float = 0.0) -> Dict[str, Any]:
        """
        Pide a la IA un veredicto binario: SÍ o NO.

        Este es el ÚNICO método que debería usarse para interactuar con la IA.

        v17.1 Flujo con resiliencia:
          1. Check Circuit Breaker → si OPEN, fallback NO inmediato
          2. Check Health Monitor → si unhealthy, log warning
          3. Multi-attempt consensus: Pregunta N veces
          4. Mayoría decide (threshold = 2 de 3)
          5. Si todas fallan → fallback NO
          6. Auditar resultado

        Args:
            question: La pregunta binaria a responder
            context: Contexto adicional (resumen, no input crudo)
            evidence_for: Resumen de evidencia a favor
            evidence_against: Resumen de evidencia en contra
            consensus_hint: Score del consenso (-1.0 a 1.0)

        Returns:
            Dict con: verdict ("YES"/"NO"), confidence, source, raw_response
        """
        self._verdict_count += 1
        start = time.time()

        if not self.is_loaded:
            self._verdict_fallback += 1
            self._verdict_no += 1
            self._audit_verdict(
                question, "NO", "fallback_no_model", False, 0.0,
                int((time.time() - start) * 1000), 0,
                evidence_for, evidence_against, consensus_hint
            )
            return {
                "verdict": "NO",
                "confidence": 0.0,
                "source": "fallback_no_model",
                "raw_response": "",
                "time_ms": 0,
                "retry_count": 0,
            }

        # v17.1: Check Circuit Breaker
        if self._verdict_resilience and not self._verdict_resilience.can_call_llm():
            self._verdict_fallback += 1
            self._verdict_no += 1
            elapsed_ms = int((time.time() - start) * 1000)
            self._audit_verdict(
                question, "NO", "fallback_circuit_open", False, 0.0,
                elapsed_ms, 0, evidence_for, evidence_against, consensus_hint,
                circuit_breaker_state="open"
            )
            return {
                "verdict": "NO",
                "confidence": 0.0,
                "source": "fallback_circuit_open",
                "raw_response": "",
                "time_ms": elapsed_ms,
                "retry_count": 0,
            }

        # Build user prompt with evidence
        user_prompt = self._build_verdict_prompt(
            question, context, evidence_for, evidence_against, consensus_hint
        )

        # v17.1: Multi-attempt consensus
        if VERDICT_CONSENSUS_ATTEMPTS > 1:
            result = self._verdict_multi_attempt(
                user_prompt, question, start, evidence_for, evidence_against, consensus_hint
            )
        else:
            result = self._verdict_single_attempt(
                user_prompt, question, start, evidence_for, evidence_against, consensus_hint
            )

        return result

    def _build_verdict_prompt(self, question: str, context: str,
                               evidence_for: str, evidence_against: str,
                               consensus_hint: float) -> str:
        """Construye el prompt para el veredicto."""
        user_parts = [f"Question: {question}"]
        if evidence_for:
            user_parts.append(f"Evidence FOR: {evidence_for[:200]}")
        if evidence_against:
            user_parts.append(f"Evidence AGAINST: {evidence_against[:200]}")
        if consensus_hint != 0.0:
            user_parts.append(f"Consensus score: {consensus_hint:.2f}")
        if context:
            user_parts.append(f"Context: {context[:200]}")
        return "\n".join(user_parts)

    def _ensure_verdict_executor(self):
        """Ensure _verdict_executor is available, creating it lazily if needed.

        FIX (v18.1): After unload_model() shuts down _verdict_executor and
        sets it to None, subsequent verdict calls would crash with
        AttributeError: 'NoneType' object has no attribute 'submit'.
        This method lazily recreates the executor, matching the pattern
        used by _call_llm() for self._executor.
        """
        if getattr(self, '_verdict_executor', None) is None:
            self._verdict_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _verdict_single_attempt(self, user_prompt: str, question: str,
                                 start_time: float, evidence_for: str,
                                 evidence_against: str, consensus_hint: float) -> Dict[str, Any]:
        """
        Intenta obtener un veredicto con retry y exponential backoff.
        """
        raw_response = None
        retry_count = 0
        last_was_timeout = False
        last_was_ambiguous = False

        max_retries = VERDICT_MAX_RETRIES
        if self._verdict_resilience:
            max_retries = self._verdict_resilience.retry_config.max_attempts

        for attempt in range(max_retries):
            retry_count = attempt

            # Delay between retries (not on first attempt)
            if attempt > 0:
                delay = self._compute_retry_delay(attempt)
                logger.info(f"VerdictMixin: Retry {attempt}/{max_retries} after {delay:.1f}s")
                time.sleep(delay)

            # Try LLM with strict timeout
            try:
                self._ensure_verdict_executor()
                future = self._verdict_executor.submit(
                    self._verdict_llm_call, user_prompt
                )
                raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                if raw_response:
                    # Parse response
                    parsed = self._parse_verdict_response(raw_response)

                    if parsed is not None:
                        # Valid response!
                        latency_s = time.time() - start_time
                        self._record_verdict_success(
                            latency_s, parsed == "YES"
                        )
                        elapsed_ms = int(latency_s * 1000)

                        if parsed == "YES":
                            self._verdict_yes += 1
                        else:
                            self._verdict_no += 1

                        self._audit_verdict(
                            question, parsed, "llm", True,
                            min(abs(consensus_hint) + 0.3, 1.0),
                            elapsed_ms, retry_count,
                            evidence_for, evidence_against, consensus_hint,
                            raw_response=raw_response
                        )

                        return {
                            "verdict": parsed,
                            "confidence": min(abs(consensus_hint) + 0.3, 1.0),
                            "source": "llm",
                            "raw_response": raw_response,
                            "time_ms": elapsed_ms,
                            "retry_count": retry_count,
                        }
                    else:
                        # Ambiguous response
                        last_was_ambiguous = True
                        logger.warning(
                            f"VerdictMixin: Ambiguous response on attempt {attempt + 1}"
                        )
            except concurrent.futures.TimeoutError:
                last_was_timeout = True
                logger.warning(
                    f"VerdictMixin: Timeout ({VERDICT_TIMEOUT_S}s), attempt {attempt + 1}"
                )
            except Exception as e:
                logger.warning(f"VerdictMixin: LLM error on attempt {attempt + 1}: {e}")

        # All attempts failed
        latency_s = time.time() - start_time
        self._record_verdict_failure(
            latency_s, was_timeout=last_was_timeout, was_ambiguous=last_was_ambiguous
        )

        # Fallback: NO (principio de precaución)
        self._verdict_fallback += 1
        self._verdict_no += 1
        elapsed_ms = int((time.time() - start_time) * 1000)

        self._audit_verdict(
            question, "NO", "fallback", False, 0.0,
            elapsed_ms, retry_count,
            evidence_for, evidence_against, consensus_hint,
            was_timeout=last_was_timeout, was_ambiguous=last_was_ambiguous,
            raw_response=raw_response or ""
        )

        return {
            "verdict": "NO",
            "confidence": 0.0,
            "source": "fallback",
            "raw_response": raw_response or "",
            "time_ms": elapsed_ms,
            "retry_count": retry_count,
        }

    def _verdict_multi_attempt(self, user_prompt: str, question: str,
                                start_time: float, evidence_for: str,
                                evidence_against: str,
                                consensus_hint: float) -> Dict[str, Any]:
        """
        Multi-attempt consensus: Pregunta al LLM N veces y la mayoría decide.

        Esto reduce significativamente la probabilidad de un veredicto
        incorrecto por una respuesta aleatoria del modelo.

        Ejemplo: Si se pregunta 3 veces y 2+ dicen YES → verdict = YES
        """
        yes_count = 0
        no_count = 0
        raw_responses = []
        total_attempts = 0

        for i in range(VERDICT_CONSENSUS_ATTEMPTS):
            # Small delay between consensus attempts to let model cool down
            if i > 0:
                time.sleep(0.3)

            try:
                self._ensure_verdict_executor()
                future = self._verdict_executor.submit(
                    self._verdict_llm_call, user_prompt
                )
                raw = future.result(timeout=VERDICT_TIMEOUT_S)
                total_attempts += 1

                if raw:
                    raw_responses.append(raw)
                    parsed = self._parse_verdict_response(raw)
                    if parsed == "YES":
                        yes_count += 1
                    elif parsed == "NO":
                        no_count += 1
                    # None (ambiguous) counts as NO implicitly
                else:
                    no_count += 1  # No response = NO
            except concurrent.futures.TimeoutError:
                no_count += 1  # Timeout = NO
                total_attempts += 1
                logger.warning(
                    f"VerdictMixin: Consensus attempt {i + 1} timed out"
                )
            except Exception as e:
                no_count += 1
                total_attempts += 1
                logger.warning(
                    f"VerdictMixin: Consensus attempt {i + 1} failed: {e}"
                )

            # Early exit: If we already have a clear majority
            if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
                break
            if no_count >= VERDICT_CONSENSUS_THRESHOLD:
                break

        # Determine verdict by majority
        latency_s = time.time() - start_time
        elapsed_ms = int(latency_s * 1000)

        if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
            # Majority YES
            self._verdict_yes += 1
            self._record_verdict_success(latency_s, True)
            confidence = min(yes_count / total_attempts + 0.1, 1.0)

            self._audit_verdict(
                question, "YES", "llm_consensus", True,
                confidence, elapsed_ms, 0,
                evidence_for, evidence_against, consensus_hint,
                raw_response="; ".join(raw_responses[:3])
            )

            return {
                "verdict": "YES",
                "confidence": confidence,
                "source": "llm_consensus",
                "raw_response": "; ".join(raw_responses[:3]),
                "time_ms": elapsed_ms,
                "retry_count": 0,
                "consensus_detail": {
                    "yes_count": yes_count,
                    "no_count": no_count,
                    "total_attempts": total_attempts,
                },
            }
        else:
            # Majority NO (or tie → NO by precaution principle)
            self._verdict_no += 1
            was_all_failure = yes_count == 0 and no_count == 0
            if was_all_failure:
                self._verdict_fallback += 1
                source = "fallback"
            else:
                source = "llm_consensus"

            self._record_verdict_failure(
                latency_s, was_timeout=no_count > 0 and yes_count == 0
            )

            self._audit_verdict(
                question, "NO", source, yes_count > 0,
                0.0, elapsed_ms, 0,
                evidence_for, evidence_against, consensus_hint,
                raw_response="; ".join(raw_responses[:3])
            )

            return {
                "verdict": "NO",
                "confidence": 0.0 if was_all_failure else min(no_count / max(total_attempts, 1), 1.0),
                "source": source,
                "raw_response": "; ".join(raw_responses[:3]),
                "time_ms": elapsed_ms,
                "retry_count": 0,
                "consensus_detail": {
                    "yes_count": yes_count,
                    "no_count": no_count,
                    "total_attempts": total_attempts,
                },
            }

    def _compute_retry_delay(self, attempt: int) -> float:
        """Compute delay for retry with exponential backoff + jitter."""
        if self._verdict_resilience:
            return self._verdict_resilience.retry_config.compute_delay(attempt)
        # Fallback delay calculation
        import random
        delay = VERDICT_BASE_DELAY * (2 ** (attempt - 1))
        delay = min(delay, VERDICT_MAX_DELAY)
        delay += random.uniform(0, 0.3 * delay)
        return delay

    def _record_verdict_success(self, latency_s: float, was_yes: bool) -> None:
        """Record a successful verdict to resilience systems."""
        if self._verdict_resilience:
            self._verdict_resilience.record_success(latency_s, was_ambiguous=False)

    def _record_verdict_failure(self, latency_s: float,
                                 was_timeout: bool = False,
                                 was_ambiguous: bool = False) -> None:
        """Record a failed verdict to resilience systems."""
        if self._verdict_resilience:
            self._verdict_resilience.record_failure(
                latency_s, was_timeout=was_timeout, was_ambiguous=was_ambiguous
            )

    def _audit_verdict(self, question: str, verdict: str, source: str,
                        llm_used: bool, confidence: float, latency_ms: int,
                        retry_count: int, evidence_for: str = "",
                        evidence_against: str = "", consensus_score: float = 0.0,
                        was_timeout: bool = False, was_ambiguous: bool = False,
                        circuit_breaker_state: str = "",
                        raw_response: str = "") -> None:
        """Record verdict in the audit log."""
        if self._verdict_resilience and _RESILIENCE_AVAILABLE:
            entry = VerdictAuditEntry(
                timestamp=time.time(),
                question=question[:200],
                verdict=verdict,
                source=source,
                llm_used=llm_used,
                confidence=confidence,
                latency_ms=latency_ms,
                retry_count=retry_count,
                evidence_for_count=len(evidence_for) if evidence_for else 0,
                evidence_against_count=len(evidence_against) if evidence_against else 0,
                consensus_score=consensus_score,
                circuit_breaker_state=circuit_breaker_state or (
                    self._verdict_resilience.circuit_breaker.state.value
                ),
                was_timeout=was_timeout,
                was_ambiguous=was_ambiguous,
                raw_llm_response=raw_response[:100],  # Truncate for memory
            )
            self._verdict_resilience.audit_verdict(entry)

    def _verdict_llm_call(self, user_prompt: str) -> Optional[str]:
        """Llamada LLM específica para veredictos."""
        try:
            return self._call_llm(
                system_prompt=VERDICT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=VERDICT_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning(f"VerdictMixin: LLM call failed: {e}")
            return None

    @staticmethod
    def _parse_verdict_response(response: str) -> Optional[str]:
        """
        Parsea la respuesta del LLM. Solo acepta YES o NO.

        Reglas:
          - "YES" → "YES"
          - "NO" → "NO"
          - Cualquier otra cosa → None (cuenta como NO en el caller)
        """
        if not response:
            return None

        # Limpiar thinking blocks de Qwen3
        clean = response.strip()
        think_match = re.search(r'</think\s*>(.*)', clean, re.DOTALL)
        if think_match:
            clean = think_match.group(1).strip()

        # Tomar solo la primera palabra
        first_word = clean.split()[0].upper() if clean.split() else ""

        if first_word == "YES":
            return "YES"
        elif first_word == "NO":
            return "NO"
        elif "YES" in first_word:
            return "YES"
        elif "NO" in first_word:
            return "NO"

        # Ambiguo = None → se convierte en NO
        logger.warning(f"VerdictMixin: Ambiguous response: '{response[:50]}'")
        return None

    @property
    def verdict_stats(self) -> Dict[str, Any]:
        """Estadísticas de veredictos con resiliencia."""
        total = max(self._verdict_count, 1)
        base_stats = {
            "total_verdicts": self._verdict_count,
            "yes_count": self._verdict_yes,
            "no_count": self._verdict_no,
            "fallback_count": self._verdict_fallback,
            "yes_rate": self._verdict_yes / total,
            "no_rate": self._verdict_no / total,
            "fallback_rate": self._verdict_fallback / total,
            "llm_available": self.is_loaded,
            "consensus_attempts": VERDICT_CONSENSUS_ATTEMPTS,
            "max_retries": VERDICT_MAX_RETRIES,
        }
        if self._verdict_resilience:
            base_stats["resilience"] = self._verdict_resilience.stats
        return base_stats
