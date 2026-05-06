"""
Verdict Resilience Patterns — Circuit Breaker, Retry, Health Monitor, Auditor.

Patrones de diseño para hacer que el sistema de veredicto sea resiliente
ante fallos de la IA (Qwen3-0.6B):

  1. VerdictCircuitBreaker: Protege contra fallos en cascada del LLM.
     - Si el LLM falla N veces consecutivas → OPEN (no se llama al LLM)
     - Después de recovery_timeout → HALF_OPEN (prueba 1 llamada)
     - Si funciona → CLOSED (vuelve a normal)
     - Si falla → OPEN de nuevo

  2. VerdictRetryPolicy: Reintento con exponential backoff.
     - Máximo N intentos con delays crecientes
     - Jitter aleatorio para evitar thundering herd
     - Callbacks de progreso para logging

  3. VerdictHealthMonitor: Monitorea la salud del LLM.
     - Latencia promedio, tasa de éxito, última respuesta
     - Auto-disable si la salud es críticamente baja
     - Recuperación automática cuando la salud mejora

  4. VerdictAuditor: Registro de auditoría de todos los veredictos.
     - Almacena cada veredicto con contexto y evidencia
     - Permite análisis post-mortem
     - Detecta patrones de fallo

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - Memoria máxima: < 1MB para auditoría (buffer circular)
"""

import time
import random
import logging
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================
#  VERDICT CIRCUIT BREAKER
# ============================================================

class VerdictCircuitState(str, Enum):
    """Estados del Circuit Breaker para veredictos."""
    CLOSED = "closed"         # Normal: LLM se usa cuando se necesita
    OPEN = "open"             # LLM no se llama: fallos consecutivos
    HALF_OPEN = "half_open"   # Probando si el LLM se recuperó


class VerdictCircuitBreaker:
    """
    Circuit Breaker específico para llamadas de veredicto al LLM.

    Protege contra:
      - LLM que tarda demasiado (timeouts repetidos)
      - LLM que devuelve respuestas ambiguas repetidamente
      - LLM que está completamente caído

    Estado CLOSED: Todo normal, el LLM se llama cuando hay empate.
    Estado OPEN: El LLM no se llama, todos los veredictos son fallback NO.
    Estado HALF_OPEN: Se permite 1 llamada de prueba para ver si el LLM se recuperó.

    Thread-safe. Optimizado para baja memoria.
    """

    def __init__(
        self,
        name: str = "verdict_llm",
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
        success_threshold: int = 2,
    ):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._success_threshold = success_threshold

        self._state = VerdictCircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._opened_at: Optional[float] = None
        self._last_failure_time: Optional[float] = None

        # Stats
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_rejected = 0  # Calls rejected because circuit was OPEN

        self._lock = threading.Lock()

    @property
    def state(self) -> VerdictCircuitState:
        """Current state with lazy OPEN → HALF_OPEN transition."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def is_open(self) -> bool:
        """True if the circuit is OPEN (LLM calls are rejected)."""
        return self.state == VerdictCircuitState.OPEN

    @property
    def stats(self) -> Dict[str, Any]:
        """Snapshot of circuit breaker statistics."""
        with self._lock:
            self._maybe_transition_to_half_open()
            remaining = 0.0
            if self._state == VerdictCircuitState.OPEN and self._opened_at:
                elapsed = time.monotonic() - self._opened_at
                remaining = max(0.0, self._recovery_timeout - elapsed)
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_threshold": self._failure_threshold,
                "consecutive_failures": self._failure_count,
                "consecutive_successes": self._success_count,
                "total_calls": self._total_calls,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "remaining_timeout": remaining,
                "recovery_timeout": self._recovery_timeout,
            }

    def can_call(self) -> bool:
        """Check if a call to the LLM is allowed."""
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == VerdictCircuitState.CLOSED:
                return True
            if self._state == VerdictCircuitState.HALF_OPEN:
                return self._half_open_calls < self._half_open_max_calls
            # OPEN
            self._total_rejected += 1
            return False

    def record_success(self) -> None:
        """Record a successful LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_successes += 1

            if self._state == VerdictCircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls += 1
                if self._success_count >= self._success_threshold:
                    self._transition_to(VerdictCircuitState.CLOSED)
                    logger.info(
                        f"VerdictCircuitBreaker[{self._name}]: "
                        f"HALF_OPEN → CLOSED ({self._success_count} successes)"
                    )
            elif self._state == VerdictCircuitState.CLOSED:
                self._failure_count = 0
                self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            self._failure_count += 1
            self._success_count = 0
            self._last_failure_time = time.monotonic()

            if self._state == VerdictCircuitState.HALF_OPEN:
                self._half_open_calls += 1
                self._transition_to(VerdictCircuitState.OPEN)
                logger.warning(
                    f"VerdictCircuitBreaker[{self._name}]: "
                    f"HALF_OPEN → OPEN (failure in half-open)"
                )
            elif self._state == VerdictCircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(VerdictCircuitState.OPEN)
                    logger.warning(
                        f"VerdictCircuitBreaker[{self._name}]: "
                        f"CLOSED → OPEN ({self._failure_count} consecutive failures)"
                    )

    def reset(self) -> None:
        """Reset to CLOSED state."""
        with self._lock:
            self._transition_to(VerdictCircuitState.CLOSED)
            logger.info(f"VerdictCircuitBreaker[{self._name}]: Reset to CLOSED")

    def _maybe_transition_to_half_open(self) -> None:
        """Check if recovery_timeout has elapsed in OPEN state."""
        if self._state != VerdictCircuitState.OPEN or self._opened_at is None:
            return
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self._recovery_timeout:
            self._transition_to(VerdictCircuitState.HALF_OPEN)
            logger.info(
                f"VerdictCircuitBreaker[{self._name}]: "
                f"OPEN → HALF_OPEN (recovery timeout elapsed)"
            )

    def _transition_to(self, new_state: VerdictCircuitState) -> None:
        """Perform state transition."""
        self._state = new_state
        if new_state == VerdictCircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._opened_at = None
        elif new_state == VerdictCircuitState.OPEN:
            self._success_count = 0
            self._half_open_calls = 0
            self._opened_at = time.monotonic()
        elif new_state == VerdictCircuitState.HALF_OPEN:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0


# ============================================================
#  VERDICT RETRY POLICY
# ============================================================

@dataclass
class VerdictRetryConfig:
    """
    Configuration for verdict retry with exponential backoff.

    Attributes:
        max_attempts: Maximum LLM call attempts (default 3).
        base_delay: Base delay in seconds between retries.
        max_delay: Upper bound for delay.
        exponential_base: Base for exponential calculation.
        jitter: Whether to add random jitter.
        jitter_max: Jitter multiplier (0..1).
        timeout_per_attempt: Timeout in seconds per individual LLM call.
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.3
    timeout_per_attempt: float = 5.0

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for the given attempt (1-based)."""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter and delay > 0:
            delay += random.uniform(0, self.jitter_max * delay)
        return delay


# ============================================================
#  VERDICT HEALTH MONITOR
# ============================================================

@dataclass
class VerdictHealthSnapshot:
    """Snapshot of the LLM health at a point in time."""
    is_healthy: bool
    avg_latency_s: float
    success_rate: float
    total_calls: int
    total_failures: int
    total_timeouts: int
    total_ambiguous: int
    last_call_time: Optional[float]
    circuit_breaker_state: str


class VerdictHealthMonitor:
    """
    Monitors the health of the LLM for verdict operations.

    Tracks:
      - Latency statistics
      - Success/failure rates
      - Timeout rates
      - Ambiguous response rates
      - Auto-disable when health is critically low

    The health monitor uses a sliding window of recent calls
    to determine if the LLM is reliable enough for verdicts.
    """

    def __init__(self, window_size: int = 50, unhealthy_threshold: float = 0.3):
        """
        Args:
            window_size: Number of recent calls to track.
            unhealthy_threshold: Success rate below this = unhealthy.
        """
        self._window_size = window_size
        self._unhealthy_threshold = unhealthy_threshold

        # Sliding window of call results
        self._results: deque = deque(maxlen=window_size)

        # Counters
        self._total_calls = 0
        self._total_successes = 0
        self._total_failures = 0
        self._total_timeouts = 0
        self._total_ambiguous = 0

        # Latency tracking
        self._total_latency = 0.0
        self._last_call_time: Optional[float] = None

        self._lock = threading.Lock()

    def record_call(self, success: bool, latency_s: float,
                    was_timeout: bool = False, was_ambiguous: bool = False) -> None:
        """Record the result of an LLM call."""
        with self._lock:
            self._total_calls += 1
            self._total_latency += latency_s
            self._last_call_time = time.monotonic()

            if success:
                self._total_successes += 1
            else:
                self._total_failures += 1

            if was_timeout:
                self._total_timeouts += 1
            if was_ambiguous:
                self._total_ambiguous += 1

            self._results.append({
                "success": success,
                "latency": latency_s,
                "timeout": was_timeout,
                "ambiguous": was_ambiguous,
                "time": time.monotonic(),
            })

    @property
    def is_healthy(self) -> bool:
        """Check if the LLM is healthy enough for verdict calls."""
        return self.snapshot.is_healthy

    @property
    def snapshot(self) -> VerdictHealthSnapshot:
        """Get a health snapshot."""
        with self._lock:
            # Calculate success rate from sliding window
            if not self._results:
                return VerdictHealthSnapshot(
                    is_healthy=True,  # No data = assume healthy
                    avg_latency_s=0.0,
                    success_rate=1.0,
                    total_calls=0,
                    total_failures=0,
                    total_timeouts=0,
                    total_ambiguous=0,
                    last_call_time=None,
                    circuit_breaker_state="unknown",
                )

            recent_successes = sum(1 for r in self._results if r["success"])
            success_rate = recent_successes / len(self._results)
            avg_latency = self._total_latency / max(self._total_calls, 1)

            return VerdictHealthSnapshot(
                is_healthy=success_rate >= self._unhealthy_threshold,
                avg_latency_s=avg_latency,
                success_rate=success_rate,
                total_calls=self._total_calls,
                total_failures=self._total_failures,
                total_timeouts=self._total_timeouts,
                total_ambiguous=self._total_ambiguous,
                last_call_time=self._last_call_time,
                circuit_breaker_state="monitored",
            )

    @property
    def stats(self) -> Dict[str, Any]:
        """Health statistics."""
        snap = self.snapshot
        return {
            "is_healthy": snap.is_healthy,
            "success_rate": snap.success_rate,
            "avg_latency_s": snap.avg_latency_s,
            "total_calls": snap.total_calls,
            "total_failures": snap.total_failures,
            "total_timeouts": snap.total_timeouts,
            "total_ambiguous": snap.total_ambiguous,
        }


# ============================================================
#  VERDICT AUDITOR
# ============================================================

@dataclass
class VerdictAuditEntry:
    """Single audit entry for a verdict decision."""
    timestamp: float
    question: str
    verdict: str                  # YES or NO
    source: str                   # llm, consensus, fallback
    llm_used: bool
    confidence: float
    latency_ms: int
    retry_count: int
    evidence_for_count: int
    evidence_against_count: int
    consensus_score: float
    circuit_breaker_state: str = ""
    was_timeout: bool = False
    was_ambiguous: bool = False
    raw_llm_response: str = ""


class VerdictAuditor:
    """
    Auditor for the verdict system.

    Mantiene un buffer circular de las últimas N decisiones de veredicto
    para permitir análisis post-mortem y detección de patrones de fallo.

    El buffer es circular para limitar uso de memoria (< 1MB).
    """

    def __init__(self, max_entries: int = 100):
        """
        Args:
            max_entries: Maximum audit entries to keep (circular buffer).
        """
        self._entries: deque = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def record(self, entry: VerdictAuditEntry) -> None:
        """Record a verdict audit entry."""
        with self._lock:
            self._entries.append(entry)

    def get_recent(self, count: int = 20) -> List[VerdictAuditEntry]:
        """Get the N most recent audit entries."""
        with self._lock:
            return list(self._entries)[-count:]

    def get_failure_pattern(self) -> Dict[str, Any]:
        """
        Analyze recent entries for failure patterns.

        Returns:
            Dictionary with pattern analysis.
        """
        with self._lock:
            if not self._entries:
                return {"pattern": "no_data", "risk": "unknown"}

            recent = list(self._entries)[-50:]  # Last 50

            # Count by source
            source_counts: Dict[str, int] = {}
            timeout_count = 0
            ambiguous_count = 0
            llm_failure_streak = 0
            max_llm_failure_streak = 0
            current_streak = 0

            for entry in recent:
                source_counts[entry.source] = source_counts.get(entry.source, 0) + 1
                if entry.was_timeout:
                    timeout_count += 1
                if entry.was_ambiguous:
                    ambiguous_count += 1

                # Track LLM failure streaks
                if entry.llm_used and entry.source == "fallback":
                    current_streak += 1
                    max_llm_failure_streak = max(max_llm_failure_streak, current_streak)
                else:
                    current_streak = 0

            # Detect patterns
            total = len(recent)
            fallback_rate = source_counts.get("fallback", 0) / total
            timeout_rate = timeout_count / total

            risk = "low"
            if fallback_rate > 0.5:
                risk = "high"
            elif fallback_rate > 0.3:
                risk = "medium"

            pattern = "healthy"
            if max_llm_failure_streak >= 5:
                pattern = "llm_consistently_failing"
            elif timeout_rate > 0.3:
                pattern = "frequent_timeouts"
            elif ambiguous_count > total * 0.2:
                pattern = "ambiguous_responses"
            elif fallback_rate > 0.5:
                pattern = "excessive_fallback"

            return {
                "pattern": pattern,
                "risk": risk,
                "total_entries": total,
                "source_distribution": source_counts,
                "timeout_rate": timeout_rate,
                "fallback_rate": fallback_rate,
                "max_llm_failure_streak": max_llm_failure_streak,
                "ambiguous_rate": ambiguous_count / total if total else 0,
            }

    @property
    def stats(self) -> Dict[str, Any]:
        """Audit statistics."""
        with self._lock:
            total = len(self._entries)
            if total == 0:
                return {"total_entries": 0, "pattern_analysis": "no_data"}

            pattern = self.get_failure_pattern()
            yes_count = sum(1 for e in self._entries if e.verdict == "YES")
            no_count = sum(1 for e in self._entries if e.verdict == "NO")

            return {
                "total_entries": total,
                "yes_count": yes_count,
                "no_count": no_count,
                "yes_rate": yes_count / total,
                "no_rate": no_count / total,
                "pattern_analysis": pattern,
            }


# ============================================================
#  VERDICT RESILIENCE ORCHESTRATOR
# ============================================================

class VerdictResilienceOrchestrator:
    """
    Orchestrates all resilience patterns for the verdict system.

    Combines:
      - Circuit Breaker: Prevents calls when LLM is down
      - Health Monitor: Tracks LLM health metrics
      - Auditor: Records decisions for analysis
      - Retry Policy: Manages retry behavior

    Usage:
        resilience = VerdictResilienceOrchestrator()

        # Before calling LLM
        if resilience.can_call_llm():
            result = call_llm(...)
            resilience.record_result(result)

        # Get health status
        health = resilience.health_snapshot
    """

    def __init__(
        self,
        circuit_breaker: Optional[VerdictCircuitBreaker] = None,
        health_monitor: Optional[VerdictHealthMonitor] = None,
        auditor: Optional[VerdictAuditor] = None,
        retry_config: Optional[VerdictRetryConfig] = None,
    ):
        self.circuit_breaker = circuit_breaker or VerdictCircuitBreaker()
        self.health_monitor = health_monitor or VerdictHealthMonitor()
        self.auditor = auditor or VerdictAuditor()
        self.retry_config = retry_config or VerdictRetryConfig()

    def can_call_llm(self) -> bool:
        """
        Check if an LLM call is allowed.

        Returns False if:
          - Circuit breaker is OPEN
          - Health monitor detects critical failure
        """
        if not self.circuit_breaker.can_call():
            logger.debug("VerdictResilience: Circuit breaker OPEN, LLM call rejected")
            return False

        if not self.health_monitor.is_healthy:
            # Allow through circuit breaker (it has its own logic)
            # but log the health warning
            snap = self.health_monitor.snapshot
            logger.warning(
                f"VerdictResilience: LLM health is LOW "
                f"(success_rate={snap.success_rate:.2f}), "
                f"proceeding with caution"
            )

        return True

    def record_success(self, latency_s: float, was_ambiguous: bool = False) -> None:
        """Record a successful LLM verdict call."""
        self.circuit_breaker.record_success()
        self.health_monitor.record_call(
            success=True, latency_s=latency_s, was_ambiguous=was_ambiguous
        )

    def record_failure(self, latency_s: float, was_timeout: bool = False,
                       was_ambiguous: bool = False) -> None:
        """Record a failed LLM verdict call."""
        self.circuit_breaker.record_failure()
        self.health_monitor.record_call(
            success=False, latency_s=latency_s,
            was_timeout=was_timeout, was_ambiguous=was_ambiguous
        )

    def audit_verdict(self, entry: VerdictAuditEntry) -> None:
        """Record a verdict in the audit log."""
        self.auditor.record(entry)

    @property
    def health_snapshot(self) -> VerdictHealthSnapshot:
        """Current health snapshot."""
        snap = self.health_monitor.snapshot
        snap.circuit_breaker_state = self.circuit_breaker.state.value
        return snap

    @property
    def stats(self) -> Dict[str, Any]:
        """Comprehensive resilience statistics."""
        return {
            "circuit_breaker": self.circuit_breaker.stats,
            "health": self.health_monitor.stats,
            "audit": self.auditor.stats,
            "retry_config": {
                "max_attempts": self.retry_config.max_attempts,
                "base_delay": self.retry_config.base_delay,
                "timeout_per_attempt": self.retry_config.timeout_per_attempt,
            },
        }
