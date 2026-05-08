"""
VerdictEngine - El único punto donde la IA interviene, y solo emite SÍ o NO.

PRINCIPIO FUNDAMENTAL:
  La IA NUNCA genera, NUNCA clasifica, NUNCA valida, NUNCA explica.
  La IA SOLO responde una pregunta binaria cuando el sistema
  determinístico no puede decidir.

v17.1 MEJORAS DE RESILIENCIA:
  - Circuit Breaker: Protege contra fallos en cascada del LLM
  - Retry con exponential backoff: Recuperación de errores transitorios
  - Health Monitor: Seguimiento de salud del LLM en tiempo real
  - VerdictAuditor: Registro de auditoría de todas las decisiones
  - Multi-attempt consensus: Pregunta N veces, mayoría gana
  - Timeout cascade protection: Si el LLM está lento, se adapta
  - Fallback gradual: Consenso → LLM simple → LLM consensus → NO

Flujo del Veredicto (v17.1):
  1. DeterministicPipeline ejecuta todas las tareas
  2. EvidenceCollector recolecta evidencia
  3. ConsensusResolver evalúa consenso
  4. Si consenso ≥ HIGH → Decisión sin IA
  5. Si consenso < HIGH → VerdictEngine pide a Qwen:
     a. Check Circuit Breaker → si OPEN, fallback NO
     b. Check Health Monitor → si unhealthy, warning
     c. Multi-attempt consensus (3 intentos, mayoría gana)
     d. Si funciona → Audit y retornar
     e. Si falla → Retry con backoff (máx 3 veces)
     f. Si todo falla → Fallback NO (principio de precaución)

Garantías contra errores:
  - La IA solo puede responder "YES" o "NO" (cualquier otra cosa = NO)
  - Si la IA no responde en 5 segundos → Default conservador (NO)
  - Si la IA da una respuesta ambigua → Se cuenta como NO
  - Circuit Breaker evita llamadas cuando el LLM está caído
  - Health Monitor detecta degradación gradual
  - Auditoría permite análisis post-mortem
"""

import re
import time
import logging
import concurrent.futures
from typing import Optional, Dict, Any, List

from .types import (
    Verdict, Evidence, VerdictInput, VerdictOutput,
    ConsensusResult, VerdictConfidence,
)
from .evidence_collector import EvidenceCollector
from .consensus_resolver import ConsensusResolver
from .deterministic_pipeline import DeterministicPipeline

# Import resilience patterns
try:
    from .resilience import (
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

logger = logging.getLogger(__name__)

# === Configuración del VerdictEngine ===
VERDICT_TIMEOUT_S = 5.0           # Timeout estricto para la IA (5 segundos)
VERDICT_MAX_TOKENS = 10           # Solo necesita 1 token, damos margen
VERDICT_TEMPERATURE = 0.0         # 0.0 = determinismo absoluto
VERDICT_MAX_RETRIES = 3           # Reintentos con exponential backoff (antes 1)
VERDICT_CONSENSUS_ATTEMPTS = 3    # Preguntar N veces, mayoría gana
VERDICT_CONSENSUS_THRESHOLD = 2   # Mínimo de YES para verdict YES

VERDICT_PROMPT_TEMPLATE = """You are a binary decision maker. Based on the evidence below, answer with ONLY one word: YES or NO.

Evidence FOR: {evidence_for}
Evidence AGAINST: {evidence_against}
Consensus score: {score:.2f} (-1=NO, +1=YES)
Question: {question}

Answer with ONLY: YES or NO"""

FALLBACK_PROMPT_TEMPLATE = """Should this be approved? Answer ONLY: YES or NO

Context: {context}
Evidence summary: {summary}

Answer:"""


class VerdictEngine:
    """
    Motor de Veredicto: la IA solo dice SÍ o NO.

    v17.1: Ahora con patrones de resiliencia completos.

    Flujo completo con resiliencia:
      Input → DeterministicPipeline → EvidenceCollector →
      ConsensusResolver → (si empate) → Circuit Breaker check →
      Multi-attempt LLM consensus → Audit → SÍ o NO

    La IA nunca ve el input original del usuario.
    Solo ve un resumen de la evidencia y la pregunta binaria.
    Esto elimina la posibilidad de prompt injection y alucinaciones.
    """

    def __init__(self, mini_ai=None, semantic_engine=None,
                 smart_memory=None, auto_load: bool = True):
        """
        Args:
            mini_ai: Instancia de MiniAIEngine (Qwen3-0.6B) - OPCIONAL
            semantic_engine: Instancia de SemanticEngine - OPCIONAL
            smart_memory: Instancia de SmartMemory - OPCIONAL
            auto_load: Si True, carga el modelo al inicializar
        """
        self._mini_ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory

        # Subsistemas determinísticos (siempre disponibles)
        self._pipeline = DeterministicPipeline()
        self._evidence_collector = EvidenceCollector()
        self._consensus_resolver = ConsensusResolver()

        # Stats
        self._total_verdicts = 0
        self._llm_verdicts = 0
        self._consensus_verdicts = 0
        self._fallback_verdicts = 0
        self._yes_count = 0
        self._no_count = 0
        self._total_time = 0.0

        # Executor para timeout
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # v17.1: Resilience orchestrator
        if _RESILIENCE_AVAILABLE:
            self._resilience = VerdictResilienceOrchestrator(
                circuit_breaker=VerdictCircuitBreaker(
                    name="verdict_engine",
                    failure_threshold=3,
                    recovery_timeout=60.0,
                    half_open_max_calls=1,
                    success_threshold=2,
                ),
                health_monitor=VerdictHealthMonitor(
                    window_size=50,
                    unhealthy_threshold=0.3,
                ),
                auditor=VerdictAuditor(max_entries=200),
                retry_config=VerdictRetryConfig(
                    max_attempts=VERDICT_MAX_RETRIES,
                    base_delay=1.0,
                    max_delay=10.0,
                    timeout_per_attempt=VERDICT_TIMEOUT_S,
                ),
            )
        else:
            self._resilience = None

    def shutdown(self):
        """Shut down the internal ThreadPoolExecutor to prevent resource leaks.

        Call this when the VerdictEngine is no longer needed (e.g. on server
        shutdown).  Without this the executor's worker thread keeps running.
        """
        executor = getattr(self, '_executor', None)
        if executor is not None:
            executor.shutdown(wait=False)
            self._executor = None

    def __del__(self):
        """Ensure executor is cleaned up on garbage collection."""
        try:
            self.shutdown()
        except Exception:
            pass

        logger.info(
            f"VerdictEngine v17.1 initialized: "
            f"LLM={'available' if mini_ai and mini_ai.is_loaded else 'not available'}, "
            f"Semantic={'available' if semantic_engine and semantic_engine.is_loaded else 'not available'}, "
            f"Resilience={'enabled' if _RESILIENCE_AVAILABLE else 'basic'}"
        )

    # ================================================================
    #  MAIN API: Full verdict pipeline
    # ================================================================

    def verdict(self, text: str, code: str = "",
                language: str = "python",
                question: str = "Should this code be approved?",
                context: Optional[Dict[str, Any]] = None) -> VerdictOutput:
        """
        Ejecuta el pipeline completo de veredicto con resiliencia.

        Este es el punto de entrada principal. Recorre:
          1. DeterministicPipeline (tareas sin IA)
          2. EvidenceCollector (evidencia sin IA)
          3. ConsensusResolver (consenso sin IA)
          4. Si hay empate → Circuit Breaker check → LLM arbitraje
          5. Multi-attempt consensus para mayor confiabilidad
          6. Audit del resultado
        """
        start_time = time.time()
        self._total_verdicts += 1
        ctx = context or {}

        # === PASO 1: Ejecutar pipeline determinístico ===
        pipeline_results = self._pipeline.execute_all(text, code, language, ctx)

        # === PASO 2: Recolectar evidencia ===
        evidence = self._evidence_collector.collect_all_evidence(
            text, code, language
        )

        # Agregar evidencia de los resultados del pipeline
        from .types import EvidenceType
        for task_name, result in pipeline_results.items():
            if result.confidence >= 0.8:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.RULE_ENGINE,
                    favors=Verdict.YES,
                    weight=result.confidence,
                    source=f"pipeline_{task_name}",
                    detail=f"Pipeline task {task_name} succeeded with confidence {result.confidence:.2f}",
                ))

        # === PASO 3: Resolver consenso ===
        consensus = self._consensus_resolver.resolve(evidence, question)

        # === PASO 4: Decidir si necesita IA ===
        if not consensus.needs_llm:
            # Consenso claro: no necesita IA
            elapsed = time.time() - start_time
            self._total_time += elapsed

            if consensus.confidence in (VerdictConfidence.CERTAIN, VerdictConfidence.HIGH):
                self._consensus_verdicts += 1
            else:
                self._consensus_verdicts += 1

            if consensus.verdict == Verdict.YES:
                self._yes_count += 1
            else:
                self._no_count += 1

            # Build evidence summary
            evidence_summary = self._build_evidence_summary(consensus)

            # Audit consensus verdict
            self._audit_result(
                question, consensus.verdict.value, "consensus",
                False, abs(consensus.score), int(elapsed * 1000), 0,
                len(consensus.evidence_for), len(consensus.evidence_against),
                consensus.score
            )

            return VerdictOutput(
                verdict=consensus.verdict,
                confidence=abs(consensus.score),
                source="consensus",
                evidence_summary=evidence_summary,
                llm_used=False,
                llm_raw_response="",
                retry_count=0,
            )

        # === PASO 5: Arbitraje de IA con resiliencia ===
        verdict_input = VerdictInput(
            question=question,
            evidence_for=consensus.evidence_for,
            evidence_against=consensus.evidence_against,
            consensus_score=consensus.score,
            context=self._build_context_summary(text, code, pipeline_results),
        )

        return self._request_llm_verdict(verdict_input, start_time)

    # ================================================================
    #  DIRECT API: Ask LLM directly (only YES/NO)
    # ================================================================

    def ask_yes_no(self, question: str,
                   context: str = "",
                   evidence_for: Optional[List[Evidence]] = None,
                   evidence_against: Optional[List[Evidence]] = None) -> VerdictOutput:
        """
        Pregunta directamente a la IA una pregunta de SÍ o NO.

        v17.1: Ahora con circuit breaker, retry, y consensus.
        """
        start_time = time.time()
        self._total_verdicts += 1

        verdict_input = VerdictInput(
            question=question,
            evidence_for=evidence_for or [],
            evidence_against=evidence_against or [],
            consensus_score=0.0,
            context=context,
        )

        return self._request_llm_verdict(verdict_input, start_time)

    # ================================================================
    #  INTERNAL: LLM verdict request with full resilience
    # ================================================================

    def _request_llm_verdict(self, input_data: VerdictInput,
                              start_time: float) -> VerdictOutput:
        """
        Solicita un veredicto al LLM con resiliencia completa.

        v17.1 Flujo:
          1. Check Circuit Breaker → si OPEN, fallback NO inmediato
          2. Multi-attempt consensus (3 intentos, mayoría gana)
          3. Si majority clara → retornar
          4. Si no → Retry con exponential backoff (máx 3 rondas)
          5. Si todo falla → Fallback NO
          6. Auditar resultado
        """
        self._llm_verdicts += 1

        # v17.1: Check Circuit Breaker
        if self._resilience and not self._resilience.can_call_llm():
            elapsed = time.time() - start_time
            self._total_time += elapsed
            self._fallback_verdicts += 1
            self._no_count += 1

            evidence_summary = self._build_evidence_summary_from_input(input_data)

            logger.warning("VerdictEngine: Circuit breaker OPEN, using fallback NO")

            self._audit_result(
                input_data.question, "NO", "fallback_circuit_open",
                False, 0.0, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                circuit_breaker_state="open"
            )

            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=0.0,
                source="fallback_circuit_open",
                evidence_summary=evidence_summary + " [CIRCUIT BREAKER OPEN]",
                llm_used=False,
                llm_raw_response="",
                retry_count=0,
            )

        # Build prompt
        evidence_for_str = self._format_evidence(input_data.evidence_for[:3])
        evidence_against_str = self._format_evidence(input_data.evidence_against[:3])

        prompt = VERDICT_PROMPT_TEMPLATE.format(
            evidence_for=evidence_for_str,
            evidence_against=evidence_against_str,
            score=input_data.consensus_score,
            question=input_data.question,
        )

        # v17.1: Multi-attempt consensus
        if VERDICT_CONSENSUS_ATTEMPTS > 1 and self._mini_ai and self._mini_ai.is_loaded:
            return self._multi_attempt_consensus(
                input_data, prompt, start_time
            )

        # Fallback to single-attempt with retry
        return self._single_attempt_with_retry(
            input_data, prompt, start_time
        )

    def _multi_attempt_consensus(self, input_data: VerdictInput,
                                  prompt: str,
                                  start_time: float) -> VerdictOutput:
        """
        Multi-attempt consensus: Pregunta al LLM N veces y la mayoría decide.

        Esto es la principal defensa contra respuestas incorrectas del modelo:
        - Si el modelo da respuestas inconsistentes, la mayoría probablemente
          es correcta (ley de grandes números)
        - Si el modelo falla intermitentemente, algunos intentos pueden funcionar
        - El overhead es mínimo (3 llamadas rápidas de 1 token cada una)
        """
        yes_count = 0
        no_count = 0
        raw_responses = []
        total_attempts = 0
        any_timeout = False
        any_ambiguous = False

        for i in range(VERDICT_CONSENSUS_ATTEMPTS):
            # Small delay between consensus attempts
            if i > 0:
                time.sleep(0.2)

            try:
                future = self._executor.submit(
                    self._call_llm_safe, prompt, VERDICT_MAX_TOKENS
                )
                raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                total_attempts += 1

                if raw_response:
                    raw_responses.append(raw_response)
                    parsed = self._parse_verdict(raw_response)

                    if parsed == Verdict.YES:
                        yes_count += 1
                    elif parsed == Verdict.NO:
                        no_count += 1
                    else:
                        # Ambiguous
                        no_count += 1
                        any_ambiguous = True
                else:
                    no_count += 1
            except concurrent.futures.TimeoutError:
                total_attempts += 1
                no_count += 1
                any_timeout = True
                logger.warning(
                    f"VerdictEngine: Consensus attempt {i + 1} timed out"
                )
            except Exception as e:
                total_attempts += 1
                no_count += 1
                logger.warning(
                    f"VerdictEngine: Consensus attempt {i + 1} failed: {e}"
                )

            # Early exit: Clear majority
            if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
                break
            if no_count >= VERDICT_CONSENSUS_THRESHOLD:
                break

        # Determine verdict by majority
        elapsed = time.time() - start_time
        self._total_time += elapsed
        evidence_summary = self._build_evidence_summary_from_input(input_data)

        if yes_count >= VERDICT_CONSENSUS_THRESHOLD:
            # Majority YES
            self._yes_count += 1
            latency_s = elapsed
            self._record_success(latency_s, any_ambiguous)

            confidence = min(yes_count / max(total_attempts, 1) + 0.1, 1.0)

            self._audit_result(
                input_data.question, "YES", "llm_consensus",
                True, confidence, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                raw_response="; ".join(raw_responses[:3])
            )

            return VerdictOutput(
                verdict=Verdict.YES,
                confidence=confidence,
                source="llm_consensus",
                evidence_summary=evidence_summary,
                llm_used=True,
                llm_raw_response="; ".join(raw_responses[:3]),
                retry_count=0,
            )
        else:
            # Majority NO or tie → NO (precaution principle)
            self._no_count += 1
            all_failed = yes_count == 0 and no_count == 0
            if all_failed:
                self._fallback_verdicts += 1
                source = "fallback"
            else:
                source = "llm_consensus"

            self._record_failure(
                elapsed, was_timeout=any_timeout, was_ambiguous=any_ambiguous
            )

            self._audit_result(
                input_data.question, "NO", source,
                yes_count > 0, 0.0, int(elapsed * 1000), 0,
                len(input_data.evidence_for), len(input_data.evidence_against),
                input_data.consensus_score,
                was_timeout=any_timeout, was_ambiguous=any_ambiguous,
                raw_response="; ".join(raw_responses[:3])
            )

            confidence = 0.0 if all_failed else min(no_count / max(total_attempts, 1), 1.0)

            return VerdictOutput(
                verdict=Verdict.NO,
                confidence=confidence,
                source=source,
                evidence_summary=evidence_summary + (
                    " [FALLBACK: LLM unavailable]" if all_failed
                    else " [CONSENSUS: Majority NO]"
                ),
                llm_used=yes_count > 0 or no_count > 0,
                llm_raw_response="; ".join(raw_responses[:3]),
                retry_count=0,
            )

    def _single_attempt_with_retry(self, input_data: VerdictInput,
                                    prompt: str,
                                    start_time: float) -> VerdictOutput:
        """
        Single-attempt verdict with retry and exponential backoff.
        Used when multi-attempt consensus is disabled.
        """
        raw_response = None
        retry_count = 0
        any_timeout = False
        any_ambiguous = False

        max_retries = VERDICT_MAX_RETRIES
        if self._resilience:
            max_retries = self._resilience.retry_config.max_attempts

        if self._mini_ai and self._mini_ai.is_loaded:
            for attempt in range(max_retries):
                retry_count = attempt

                # Delay between retries
                if attempt > 0:
                    delay = self._compute_retry_delay(attempt)
                    logger.info(
                        f"VerdictEngine: Retry {attempt}/{max_retries} after {delay:.1f}s"
                    )
                    time.sleep(delay)

                try:
                    future = self._executor.submit(
                        self._call_llm_safe, prompt, VERDICT_MAX_TOKENS
                    )
                    raw_response = future.result(timeout=VERDICT_TIMEOUT_S)
                    if raw_response:
                        parsed = self._parse_verdict(raw_response)
                        if parsed is not None:
                            elapsed = time.time() - start_time
                            self._total_time += elapsed

                            self._record_success(
                                elapsed, was_ambiguous=False
                            )

                            if parsed == Verdict.YES:
                                self._yes_count += 1
                            else:
                                self._no_count += 1

                            evidence_summary = self._build_evidence_summary_from_input(input_data)

                            self._audit_result(
                                input_data.question, parsed.value, "llm",
                                True, abs(input_data.consensus_score) + 0.3,
                                int(elapsed * 1000), retry_count,
                                len(input_data.evidence_for), len(input_data.evidence_against),
                                input_data.consensus_score,
                                raw_response=raw_response
                            )

                            return VerdictOutput(
                                verdict=parsed,
                                confidence=abs(input_data.consensus_score) + 0.3,
                                source="llm",
                                evidence_summary=evidence_summary,
                                llm_used=True,
                                llm_raw_response=raw_response,
                                retry_count=retry_count,
                            )
                        else:
                            any_ambiguous = True
                except concurrent.futures.TimeoutError:
                    any_timeout = True
                    logger.warning(
                        f"VerdictEngine: LLM timed out after {VERDICT_TIMEOUT_S}s "
                        f"(attempt {attempt + 1})"
                    )
                except Exception as e:
                    logger.warning(f"VerdictEngine: LLM call failed: {e}")

        # Fallback: NO (principio de precaución)
        elapsed = time.time() - start_time
        self._total_time += elapsed
        self._fallback_verdicts += 1
        self._no_count += 1

        self._record_failure(
            elapsed, was_timeout=any_timeout, was_ambiguous=any_ambiguous
        )

        evidence_summary = self._build_evidence_summary_from_input(input_data)

        self._audit_result(
            input_data.question, "NO", "fallback",
            raw_response is not None, 0.0, int(elapsed * 1000), retry_count,
            len(input_data.evidence_for), len(input_data.evidence_against),
            input_data.consensus_score,
            was_timeout=any_timeout, was_ambiguous=any_ambiguous,
            raw_response=raw_response or ""
        )

        return VerdictOutput(
            verdict=Verdict.NO,
            confidence=0.0,
            source="fallback",
            evidence_summary=evidence_summary + " [FALLBACK: LLM unavailable or ambiguous]",
            llm_used=raw_response is not None,
            llm_raw_response=raw_response or "",
            retry_count=retry_count,
        )

    # ================================================================
    #  INTERNAL: Resilience helpers
    # ================================================================

    def _compute_retry_delay(self, attempt: int) -> float:
        """Compute delay for retry with exponential backoff + jitter."""
        if self._resilience:
            return self._resilience.retry_config.compute_delay(attempt)
        import random
        delay = 1.0 * (2 ** (attempt - 1))
        delay = min(delay, 10.0)
        delay += random.uniform(0, 0.3 * delay)
        return delay

    def _record_success(self, latency_s: float, was_ambiguous: bool = False) -> None:
        """Record success to resilience systems."""
        if self._resilience:
            self._resilience.record_success(latency_s, was_ambiguous)

    def _record_failure(self, latency_s: float, was_timeout: bool = False,
                         was_ambiguous: bool = False) -> None:
        """Record failure to resilience systems."""
        if self._resilience:
            self._resilience.record_failure(
                latency_s, was_timeout=was_timeout, was_ambiguous=was_ambiguous
            )

    def _audit_result(self, question: str, verdict: str, source: str,
                       llm_used: bool, confidence: float, latency_ms: int,
                       retry_count: int, evidence_for_count: int,
                       evidence_against_count: int, consensus_score: float,
                       was_timeout: bool = False, was_ambiguous: bool = False,
                       circuit_breaker_state: str = "",
                       raw_response: str = "") -> None:
        """Record result in audit log."""
        if self._resilience and _RESILIENCE_AVAILABLE:
            entry = VerdictAuditEntry(
                timestamp=time.time(),
                question=question[:200],
                verdict=verdict,
                source=source,
                llm_used=llm_used,
                confidence=confidence,
                latency_ms=latency_ms,
                retry_count=retry_count,
                evidence_for_count=evidence_for_count,
                evidence_against_count=evidence_against_count,
                consensus_score=consensus_score,
                circuit_breaker_state=circuit_breaker_state or (
                    self._resilience.circuit_breaker.state.value
                ),
                was_timeout=was_timeout,
                was_ambiguous=was_ambiguous,
                raw_llm_response=raw_response[:100],
            )
            self._resilience.audit_verdict(entry)

    # ================================================================
    #  INTERNAL: LLM call and parsing
    # ================================================================

    def _call_llm_safe(self, prompt: str, max_tokens: int) -> Optional[str]:
        """Llama al LLM de forma segura. No lanza excepciones."""
        try:
            return self._mini_ai._call_llm(
                system_prompt="You are a binary decision maker. Reply with ONLY one word: YES or NO. Never explain. Never add anything else.",
                user_prompt=prompt,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(f"VerdictEngine: Safe LLM call failed: {e}")
            return None

    def _parse_verdict(self, response: str) -> Optional[Verdict]:
        """
        Parsea la respuesta del LLM. Solo acepta YES o NO.

        Reglas estrictas:
          - "YES" → Verdict.YES
          - "NO" → Verdict.NO
          - Cualquier otra cosa → None (cuenta como NO en el caller)
          - Case insensitive
          - Solo la primera palabra de la respuesta
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

        # Solo aceptar YES o NO
        if first_word == "YES":
            return Verdict.YES
        elif first_word == "NO":
            return Verdict.NO
        elif "YES" in first_word:
            return Verdict.YES
        elif "NO" in first_word:
            return Verdict.NO

        # Cualquier otra cosa = ambiguo = None (se convierte en NO)
        logger.warning(
            f"VerdictEngine: Ambiguous LLM response: '{response[:50]}'. Defaulting to NO."
        )
        return None

    # ================================================================
    #  INTERNAL: Formatting helpers
    # ================================================================

    def _format_evidence(self, evidence: List[Evidence]) -> str:
        """Formatea evidencia para incluir en el prompt del LLM."""
        if not evidence:
            return "None"
        parts = []
        for e in evidence[:3]:  # Max 3 items
            parts.append(f"[{e.source}] {e.detail} (weight={e.weight:.1f})")
        return "; ".join(parts)

    def _build_evidence_summary(self, consensus: ConsensusResult) -> str:
        """Construye un resumen de la evidencia del consenso."""
        total_for = len(consensus.evidence_for)
        total_against = len(consensus.evidence_against)
        return (
            f"Consensus: {consensus.verdict.value} "
            f"(score={consensus.score:.2f}, "
            f"confidence={consensus.confidence.value}, "
            f"for={total_for}, against={total_against}, "
            f"signals={consensus.signals_count})"
        )

    def _build_evidence_summary_from_input(self, input_data: VerdictInput) -> str:
        """Construye resumen de evidencia desde VerdictInput."""
        return (
            f"Evidence: for={len(input_data.evidence_for)}, "
            f"against={len(input_data.evidence_against)}, "
            f"score={input_data.consensus_score:.2f}"
        )

    def _build_context_summary(self, text: str, code: str,
                                pipeline_results: Dict[str, Any]) -> str:
        """Construye resumen de contexto para el prompt."""
        parts = []
        if text:
            parts.append(f"Input: {text[:100]}")
        if code:
            parts.append(f"Code length: {len(code)} chars")
        classify = pipeline_results.get("classify")
        if classify and classify.success:
            parts.append(f"Classification: {classify.result}")
        return " | ".join(parts) if parts else "No additional context"

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del VerdictEngine con resiliencia."""
        total = max(self._total_verdicts, 1)
        base_stats = {
            "total_verdicts": self._total_verdicts,
            "llm_verdicts": self._llm_verdicts,
            "consensus_verdicts": self._consensus_verdicts,
            "fallback_verdicts": self._fallback_verdicts,
            "yes_count": self._yes_count,
            "no_count": self._no_count,
            "llm_rate": self._llm_verdicts / total,
            "consensus_rate": self._consensus_verdicts / total,
            "fallback_rate": self._fallback_verdicts / total,
            "yes_rate": self._yes_count / total,
            "no_rate": self._no_count / total,
            "avg_time_s": self._total_time / total,
            "llm_available": self._mini_ai is not None and self._mini_ai.is_loaded,
            "consensus_attempts": VERDICT_CONSENSUS_ATTEMPTS,
            "max_retries": VERDICT_MAX_RETRIES,
        }
        if self._resilience:
            base_stats["resilience"] = self._resilience.stats
        return base_stats

    @property
    def health(self) -> Dict[str, Any]:
        """Health status of the verdict system."""
        if self._resilience:
            snap = self._resilience.health_snapshot
            return {
                "is_healthy": snap.is_healthy,
                "success_rate": snap.success_rate,
                "avg_latency_s": snap.avg_latency_s,
                "circuit_breaker_state": snap.circuit_breaker_state,
            }
        return {
            "is_healthy": self._mini_ai is not None and self._mini_ai.is_loaded,
            "success_rate": "unknown",
            "avg_latency_s": "unknown",
            "circuit_breaker_state": "not_configured",
        }

    # ================================================================
    #  LIFECYCLE
    # ================================================================

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None) -> None:
        """Actualiza las referencias a los motores."""
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic = semantic_engine
        if smart_memory is not None:
            self._memory = smart_memory

        logger.info(
            f"VerdictEngine: Updated engines - "
            f"LLM={'available' if self._mini_ai and self._mini_ai.is_loaded else 'not available'}"
        )

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        if self._resilience:
            self._resilience.circuit_breaker.reset()
            logger.info("VerdictEngine: Circuit breaker reset to CLOSED")

    def get_audit_trail(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent audit entries as dictionaries."""
        if self._resilience and _RESILIENCE_AVAILABLE:
            entries = self._resilience.auditor.get_recent(count)
            return [
                {
                    "timestamp": e.timestamp,
                    "question": e.question,
                    "verdict": e.verdict,
                    "source": e.source,
                    "llm_used": e.llm_used,
                    "confidence": e.confidence,
                    "latency_ms": e.latency_ms,
                    "circuit_breaker_state": e.circuit_breaker_state,
                }
                for e in entries
            ]
        return []

    def get_failure_pattern(self) -> Dict[str, Any]:
        """Analyze recent verdicts for failure patterns."""
        if self._resilience:
            return self._resilience.auditor.get_failure_pattern()
        return {"pattern": "no_data", "risk": "unknown"}
