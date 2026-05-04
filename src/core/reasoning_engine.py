"""
TITAN OMNISCALE X - ReasoningEngine (Phase 8.1)

Motor de RAZONAMIENTO AVANZADO que va más allá de las tareas bounded de MiniAI.

3 modos de razonamiento:
  1. step_by_step()    - Razonamiento estructurado paso a paso
  2. self_reflect()    - Auto-evaluación y corrección (generate → evaluate → refine)
  3. reason_with_context() - Razonamiento completo con inyección de memoria + semántica

Principios:
  - Todo tiene fallback determinístico (sin modelo)
  - Budget de razonamiento acotado (max 3-5 pasos, ~200 tok/paso)
  - Cada paso produce un resultado estructurado verificable
  - Compatible con Qwen3-0.6B (n_ctx=2048)

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (~25-30 tok/s en ARM)
"""

import re
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# === Reasoning Configuration ===
MAX_REASONING_STEPS = 3
MAX_TOKENS_PER_STEP = 250
MAX_REFLECT_ITERATIONS = 2
REASONING_TIMEOUT_S = 20.0
MIN_CONFIDENCE_ACCEPT = 0.5  # Minimum confidence to accept a reasoning result


class ReasoningMode(Enum):
    """Available reasoning modes."""
    STEP_BY_STEP = "step_by_step"
    SELF_REFLECT = "self_reflect"
    WITH_CONTEXT = "with_context"
    FALLBACK = "fallback"


@dataclass
class ReasoningStep:
    """A single step in a reasoning chain."""
    step_number: int
    thought: str = ""
    conclusion: str = ""
    confidence: float = 0.0
    duration_ms: float = 0.0
    source: str = "llm"  # "llm" or "fallback"


@dataclass
class ReasoningResult:
    """Result of a complete reasoning operation."""
    answer: str = ""
    confidence: float = 0.0
    mode: ReasoningMode = ReasoningMode.FALLBACK
    steps: List[ReasoningStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    refinements: int = 0
    context_used: bool = False
    memory_hits: int = 0
    source: str = "fallback"  # "llm", "fallback", "semantic"


class ReasoningEngine:
    """
    Motor de razonamiento avanzado para TITAN OMNISCALE X.

    Extiende MiniAIEngine con modos de razonamiento que producen
    resultados más confiables a través de:

    1. Descomposición explícita del problema
    2. Auto-evaluación y corrección
    3. Inyección inteligente de contexto

    Coordina las 3 capas de IA:
      Capa 1: SemanticEngine → comprensión profunda del problema
      Capa 2: MiniAIEngine (Qwen) → razonamiento
      Capa 3: SmartMemory → experiencia previa
    """

    def __init__(self, mini_ai: Optional[Any] = None, semantic_engine: Optional[Any] = None, smart_memory: Optional[Any] = None) -> None:
        self._ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._call_count = 0
        self._total_time = 0.0

    # ================================================================
    #  MODE 1: STEP-BY-STEP REASONING
    # ================================================================

    def step_by_step(self, problem: str, max_steps: int = MAX_REASONING_STEPS,
                     context: str = "") -> ReasoningResult:
        """
        Razonamiento estructurado paso a paso.

        Descompone el problema en pasos explícitos:
          Step 1: Identificar el tipo de problema
          Step 2: Aplicar el razonamiento adecuado
          Step 3: Llegar a una conclusión verificable

        Cada paso produce un resultado estructurado que alimenta el siguiente.
        Si un paso falla o tiene baja confianza, el sistema ajusta su enfoque.
        """
        start = time.time()
        self._call_count += 1
        steps: List[ReasoningStep] = []
        accumulated = f"Problem: {problem}"
        if context:
            accumulated += f"\nAdditional context: {context[:300]}"

        # Inject memory context
        mem_ctx = self._get_memory_context(problem)
        if mem_ctx:
            accumulated += f"\n{mem_ctx}"

        for step_num in range(1, max_steps + 1):
            step_start = time.time()
            step_prompt = self._build_step_prompt(step_num, max_steps, accumulated, problem)
            answer = self._call_ai(
                system_prompt=f"You are solving a problem step by step. Step {step_num} of {max_steps}. Think carefully and give a clear, concise answer for this step only.",
                user_prompt=step_prompt,
                max_tokens=MAX_TOKENS_PER_STEP,
            )
            duration_ms = (time.time() - step_start) * 1000

            if answer:
                # Extract conclusion from step
                conclusion = self._extract_conclusion(answer)
                confidence = self._estimate_confidence(answer, step_num, max_steps)
                step = ReasoningStep(
                    step_number=step_num,
                    thought=answer[:300],
                    conclusion=conclusion,
                    confidence=confidence,
                    duration_ms=duration_ms,
                    source="llm",
                )
                steps.append(step)
                accumulated += f"\nStep {step_num} conclusion: {conclusion}"
            else:
                # LLM failed for this step - use deterministic fallback
                fallback_conclusion = self._fallback_step(step_num, problem, steps)
                step = ReasoningStep(
                    step_number=step_num,
                    thought=fallback_conclusion,
                    conclusion=fallback_conclusion,
                    confidence=0.3,
                    duration_ms=duration_ms,
                    source="fallback",
                )
                steps.append(step)
                accumulated += f"\nStep {step_num} conclusion: {fallback_conclusion}"

        # Build final result
        final_conclusion = steps[-1].conclusion if steps else ""
        avg_confidence = sum(s.confidence for s in steps) / len(steps) if steps else 0.0
        total_ms = (time.time() - start) * 1000

        # If confidence is too low, try to enhance with semantic analysis
        if avg_confidence < MIN_CONFIDENCE_ACCEPT and self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(problem)
            if sem.confidence > avg_confidence:
                final_conclusion = f"Based on semantic analysis: {sem.operation}/{sem.goal}. {final_conclusion}"
                avg_confidence = (avg_confidence + sem.confidence) / 2

        # Save to memory
        self._save_to_memory(problem, final_conclusion, "step_by_step", avg_confidence)

        elapsed = time.time() - start
        self._total_time += elapsed

        return ReasoningResult(
            answer=final_conclusion,
            confidence=avg_confidence,
            mode=ReasoningMode.STEP_BY_STEP,
            steps=steps,
            total_duration_ms=total_ms,
            context_used=bool(mem_ctx),
            memory_hits=1 if mem_ctx else 0,
            source="llm" if any(s.source == "llm" for s in steps) else "fallback",
        )

    # ================================================================
    #  MODE 2: SELF-REFLECT (Generate → Evaluate → Refine)
    # ================================================================

    def self_reflect(self, problem: str, max_iterations: int = MAX_REFLECT_ITERATIONS,
                     context: str = "") -> ReasoningResult:
        """
        Razonamiento con auto-evaluación y corrección.

        Ciclo iterativo:
          1. GENERATE: Producir una respuesta inicial
          2. EVALUATE: Evaluar la calidad de la respuesta
          3. REFINE: Mejorar la respuesta basándose en la evaluación

        Se repite hasta alcanzar confianza aceptable o agotar iteraciones.
        Este es el modo más confiable pero también el más costoso en tokens.
        """
        start = time.time()
        self._call_count += 1
        all_steps: List[ReasoningStep] = []

        # Inject context
        mem_ctx = self._get_memory_context(problem)
        full_problem = problem
        if context:
            full_problem += f"\nContext: {context[:300]}"
        if mem_ctx:
            full_problem += f"\n{mem_ctx}"

        current_answer = ""
        current_confidence = 0.0
        eval_issues = []

        for iteration in range(1, max_iterations + 1):
            # PHASE 1: GENERATE
            gen_start = time.time()
            if iteration == 1:
                gen_answer = self._call_ai(
                    system_prompt="You are a careful problem solver. Give a clear, complete answer. Think about potential issues with your answer.",
                    user_prompt=full_problem,
                    max_tokens=MAX_TOKENS_PER_STEP + 50,
                )
            else:
                # Refine: include previous evaluation
                gen_answer = self._call_ai(
                    system_prompt="You are refining your previous answer based on self-evaluation. Improve it, fix issues, and make it more accurate.",
                    user_prompt=f"Original problem: {problem}\n\nPrevious answer: {current_answer}\n\nIssues found: {eval_issues}\n\nProvide an improved answer:",
                    max_tokens=MAX_TOKENS_PER_STEP + 50,
                )

            gen_duration = (time.time() - gen_start) * 1000

            if not gen_answer:
                # Fallback generation
                gen_answer = self._fallback_generate(problem, iteration)
                current_confidence = 0.3
            else:
                current_confidence = 0.6  # Base confidence for LLM generation

            current_answer = gen_answer

            all_steps.append(ReasoningStep(
                step_number=iteration * 2 - 1,
                thought=f"GENERATE (iteration {iteration})",
                conclusion=gen_answer[:300],
                confidence=current_confidence,
                duration_ms=gen_duration,
                source="llm" if gen_answer else "fallback",
            ))

            # PHASE 2: EVALUATE
            eval_start = time.time()
            eval_answer = self._call_ai(
                system_prompt='Evaluate this answer for correctness, completeness, and potential issues. Reply JSON: {"score":0.8,"issues":["issue1"],"missing":["what is missing"]}',
                user_prompt=f"Problem: {problem}\n\nAnswer: {current_answer[:500]}",
                max_tokens=200,
            )
            eval_duration = (time.time() - eval_start) * 1000

            eval_score = 0.5
            if eval_answer:
                try:
                    match = re.search(r'\{[^}]+\}', eval_answer, re.DOTALL)
                    if match:
                        eval_data = json.loads(match.group())
                        eval_score = float(eval_data.get("score", 0.5))
                        eval_issues = eval_data.get("issues", [])
                except (json.JSONDecodeError, ValueError, TypeError):
                    eval_issues = ["Could not parse evaluation"]
            else:
                # Fallback evaluation: basic heuristic checks
                eval_score, eval_issues = self._fallback_evaluate(current_answer, problem)

            all_steps.append(ReasoningStep(
                step_number=iteration * 2,
                thought=f"EVALUATE (iteration {iteration})",
                conclusion=f"Score: {eval_score:.2f}, Issues: {', '.join(eval_issues[:3]) if eval_issues else 'None'}",
                confidence=eval_score,
                duration_ms=eval_duration,
                source="llm" if eval_answer else "fallback",
            ))

            current_confidence = eval_score

            # If confidence is acceptable, stop refining
            if eval_score >= MIN_CONFIDENCE_ACCEPT + 0.2:  # Higher threshold for self-reflect
                break

        total_ms = (time.time() - start) * 1000

        # Save to memory
        self._save_to_memory(problem, current_answer, "self_reflect", current_confidence)

        return ReasoningResult(
            answer=current_answer,
            confidence=current_confidence,
            mode=ReasoningMode.SELF_REFLECT,
            steps=all_steps,
            total_duration_ms=total_ms,
            refinements=max(0, len(all_steps) // 2 - 1),
            context_used=bool(mem_ctx),
            memory_hits=1 if mem_ctx else 0,
            source="llm" if any(s.source == "llm" for s in all_steps) else "fallback",
        )

    # ================================================================
    #  MODE 3: REASON WITH CONTEXT (Full integration)
    # ================================================================

    def reason_with_context(self, problem: str, context: str = "") -> ReasoningResult:
        """
        Razonamiento completo con inyección inteligente de contexto.

        Combina:
          1. SemanticEngine: comprensión profunda del problema
          2. SmartMemory: soluciones previas relevantes (RAG)
          3. Working Memory: contexto de la sesión actual
          4. Qwen: razonamiento informado (no a ciegas)

        Este es el modo más inteligente pero requiere todas las capas activas.
        """
        start = time.time()
        self._call_count += 1
        context_parts = []
        memory_hits = 0

        # Layer 1: Semantic understanding
        semantic_info = {}
        if self._semantic and self._semantic.is_loaded:
            sem_result = self._semantic.classify_intent(problem)
            if sem_result.source == "embedding" and sem_result.confidence > 0.3:
                semantic_info = {
                    "operation": sem_result.operation,
                    "goal": sem_result.goal,
                    "confidence": sem_result.confidence,
                }
                context_parts.append(
                    f"Semantic analysis: operation={sem_result.operation}, goal={sem_result.goal} (conf={sem_result.confidence:.2f})"
                )

        # Layer 2: Similar past solutions (RAG)
        if self._memory and self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(problem, top_k=2)
            for sol in similar:
                context_parts.append(
                    f"Past solution (sim={sol['similarity']:.2f}): {sol['solution'][:150]}"
                )
                memory_hits += 1

        # Layer 3: Working memory context
        if self._memory:
            working_ctx = self._memory.get_working_context(max_tokens=150)
            if working_ctx:
                context_parts.append(working_ctx)

        # Layer 4: Additional context provided by caller
        if context:
            context_parts.append(f"User context: {context[:300]}")

        # Build enriched prompt
        enriched_context = " | ".join(context_parts) if context_parts else ""
        enriched_problem = problem
        if enriched_context:
            enriched_problem = f"{problem}\n\nRelevant context: {enriched_context}"

        # Reason with enriched context
        answer = self._call_ai(
            system_prompt="You are a knowledgeable problem solver with access to past experience and semantic understanding. Use the provided context to give the best possible answer. Be specific and actionable.",
            user_prompt=enriched_problem,
            max_tokens=MAX_TOKENS_PER_STEP + 100,
        )

        # Compute confidence
        if answer and len(answer) > 20:
            confidence = 0.7
            # Boost confidence if semantic + memory agree
            if semantic_info and semantic_info.get("confidence", 0) > 0.5:
                confidence += 0.1
            if memory_hits > 0:
                confidence += 0.05
            confidence = min(confidence, 0.95)
        elif answer:
            confidence = 0.4
        else:
            confidence = 0.1
            # Try fallback with semantic-only reasoning
            if semantic_info:
                answer = self._fallback_context_reasoning(problem, semantic_info)
                confidence = 0.35
            else:
                answer = self._fallback_generate(problem, 1)

        total_ms = (time.time() - start) * 1000

        # Save to memory
        self._save_to_memory(problem, answer[:500], "reason_with_context", confidence)

        # Track in working memory
        if self._memory:
            self._memory.add_working(problem, answer[:500],
                                     semantic_info.get("operation", "UNKNOWN"),
                                     semantic_info.get("goal", "UNKNOWN"),
                                     confidence)

        steps = [ReasoningStep(
            step_number=1,
            thought="Full context reasoning with semantic + memory injection",
            conclusion=answer[:300],
            confidence=confidence,
            duration_ms=total_ms,
            source="llm" if answer and confidence > 0.3 else "fallback",
        )]

        return ReasoningResult(
            answer=answer,
            confidence=confidence,
            mode=ReasoningMode.WITH_CONTEXT,
            steps=steps,
            total_duration_ms=total_ms,
            context_used=len(context_parts) > 0,
            memory_hits=memory_hits,
            source="llm" if confidence > 0.3 else "fallback",
        )

    # ================================================================
    #  AUTO-SELECT BEST MODE
    # ================================================================

    def reason(self, problem: str, mode: str = "auto", context: str = "") -> ReasoningResult:
        """
        Razonamiento automático - selecciona el mejor modo según el problema.

        Estrategia de selección:
          - Problema simple (1-2 conceptos) → step_by_step
          - Problema con posibles errores → self_reflect
          - Problema complejo con contexto → reason_with_context
          - Sin modelo → fallback determinístico
        """
        if not self._ai or not self._ai.is_loaded:
            # Even without model, honor the requested mode for result tracking
            if mode == "auto":
                return self._full_fallback(problem)
            # Return fallback with the requested mode set
            mode_map = {
                "step_by_step": ReasoningMode.STEP_BY_STEP,
                "self_reflect": ReasoningMode.SELF_REFLECT,
                "with_context": ReasoningMode.WITH_CONTEXT,
            }
            requested_mode = mode_map.get(mode, ReasoningMode.FALLBACK)
            result = self._full_fallback(problem)
            result.mode = requested_mode
            return result

        if mode != "auto":
            mode_map = {
                "step_by_step": self.step_by_step,
                "self_reflect": self.self_reflect,
                "with_context": self.reason_with_context,
            }
            selected_fn = mode_map.get(mode, self.step_by_step)
            if mode == "with_context":
                return selected_fn(problem, context)
            elif mode == "self_reflect":
                return selected_fn(problem, context=context)
            return selected_fn(problem)

        # Auto-select based on problem complexity
        complexity = self._estimate_complexity(problem)

        if complexity >= 0.7:
            # Complex: use context reasoning
            return self.reason_with_context(problem, context)
        elif complexity >= 0.4:
            # Medium: use self-reflection
            return self.self_reflect(problem, context=context)
        else:
            # Simple: use step-by-step
            return self.step_by_step(problem)

    # ================================================================
    #  INTERNAL HELPERS
    # ================================================================

    def _call_ai(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Call MiniAIEngine if available."""
        if not self._ai or not self._ai.is_loaded:
            return None
        try:
            return self._ai._call_llm(system_prompt, user_prompt, max_tokens)
        except Exception as e:
            logger.warning(f"ReasoningEngine: AI call failed: {e}")
            return None

    def _get_memory_context(self, query: str) -> str:
        """Get relevant context from SmartMemory."""
        if not self._memory:
            return ""
        parts = []

        # Working memory
        working = self._memory.get_working_context(max_tokens=100)
        if working:
            parts.append(working)

        # Similar past solutions
        if self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(query, top_k=1)
            for sol in similar:
                parts.append(f"Past: {sol['solution'][:100]}")

        return " | ".join(parts) if parts else ""

    def _save_to_memory(self, query: str, answer: str, mode: str, confidence: float) -> None:
        """Save reasoning result to memory for future use."""
        if not self._memory:
            return
        importance = min(confidence, 0.9)
        if confidence >= 0.6:
            self._memory.save_to_cache(query, answer[:500], mode, "", importance)

    def _build_step_prompt(self, step_num: int, max_steps: int,
                           accumulated: str, problem: str) -> str:
        """Build the prompt for a specific reasoning step."""
        if step_num == 1:
            return f"First, identify the type and key aspects of this problem:\n{accumulated}"
        elif step_num == max_steps:
            return f"Based on all previous analysis, provide the final conclusion:\nPrevious steps: {accumulated}\n\nOriginal problem: {problem}"
        else:
            return f"Based on previous analysis, apply reasoning step {step_num}:\n{accumulated}\n\nWhat is the next logical step?"

    def _extract_conclusion(self, text: str) -> str:
        """Extract the core conclusion from a reasoning step."""
        # Look for conclusion markers
        markers = ["therefore", "thus", "conclusion:", "so,", "hence",
                    "por lo tanto", "en conclusión", "resultado:"]
        text_lower = text.lower()
        for marker in markers:
            idx = text_lower.find(marker)
            if idx >= 0:
                return text[idx + len(marker):].strip()[:200]

        # Fallback: return last meaningful sentence
        sentences = re.split(r'[.!?]\s', text)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
        return meaningful[-1] if meaningful else text[:200]

    def _estimate_confidence(self, text: str, step_num: int, max_steps: int) -> float:
        """Estimate confidence of a reasoning step."""
        base = 0.5
        # Longer, more detailed answers tend to be better
        if len(text) > 50:
            base += 0.1
        if len(text) > 150:
            base += 0.05
        # Later steps benefit from earlier analysis
        base += (step_num / max_steps) * 0.15
        # Presence of certainty markers
        certainty = ["certainly", "clearly", "definitely", "obviously", "surely"]
        if any(m in text.lower() for m in certainty):
            base += 0.05
        # Presence of hedging
        hedging = ["maybe", "perhaps", "might", "could be", "possibly"]
        if any(m in text.lower() for m in hedging):
            base -= 0.1
        return max(0.1, min(0.95, base))

    def _estimate_complexity(self, problem: str) -> float:
        """Estimate problem complexity for auto mode selection."""
        score = 0.0
        # Longer problems tend to be more complex
        words = problem.split()
        if len(words) > 20:
            score += 0.2
        elif len(words) > 10:
            score += 0.1

        # Multiple concepts indicate complexity
        concept_markers = ["and", "but", "however", "also", "while", "additionally",
                          "y", "pero", "sin embargo", "además", "también"]
        for marker in concept_markers:
            if marker in problem.lower():
                score += 0.1

        # Technical terms increase complexity
        tech_terms = ["api", "database", "auth", "microservice", "pipeline",
                     "webhook", "scheduler", "orm", "cache", "async"]
        for term in tech_terms:
            if term in problem.lower():
                score += 0.1

        # Semantic confidence as complexity indicator
        if self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(problem)
            if sem.confidence < 0.3:
                score += 0.2  # Low confidence = complex

        return min(score, 1.0)

    # ================================================================
    #  FALLBACK METHODS (deterministic, no LLM)
    # ================================================================

    def _fallback_step(self, step_num: int, problem: str,
                       previous_steps: List[ReasoningStep]) -> str:
        """Deterministic fallback for a reasoning step."""
        problem_lower = problem.lower()

        if step_num == 1:
            # Classify the problem type
            if any(kw in problem_lower for kw in ["api", "endpoint", "rest"]):
                return "This is an API design problem requiring endpoint definition and data modeling."
            elif any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
                return "This is an authentication/authorization problem requiring security implementation."
            elif any(kw in problem_lower for kw in ["database", "datos", "schema"]):
                return "This is a data modeling problem requiring schema design and CRUD operations."
            elif any(kw in problem_lower for kw in ["automat", "workflow", "schedule"]):
                return "This is an automation problem requiring workflow design and action chaining."
            else:
                return "This appears to be a general software engineering problem requiring analysis and implementation."

        elif step_num == 2:
            return "Apply standard patterns: validate inputs, process business logic, handle errors gracefully, and return structured results."

        else:
            return "Implementation should follow established patterns with proper error handling and validation."

    def _fallback_generate(self, problem: str, iteration: int) -> str:
        """Deterministic fallback for answer generation."""
        problem_lower = problem.lower()

        # Template-based responses for common problem types
        if any(kw in problem_lower for kw in ["api", "endpoint", "rest"]):
            return "Design a REST API with proper endpoints, request/response schemas, authentication middleware, and error handling. Use FastAPI for the framework and SQLite for persistence."
        elif any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
            return "Implement JWT-based authentication with token refresh, password hashing (bcrypt/PBKDF2), RBAC for authorization, and API key support for service-to-service communication."
        elif any(kw in problem_lower for kw in ["database", "datos", "schema"]):
            return "Design a normalized database schema with proper foreign keys, indexes for query performance, parameterized queries for security, and migration scripts for schema evolution."
        elif any(kw in problem_lower for kw in ["invoice", "factura", "billing"]):
            return "Build an invoice system with line items, tax calculation, discount support, PDF generation, and payment tracking. Use parameterized SQL for all database operations."
        elif any(kw in problem_lower for kw in ["inventory", "stock", "almacen"]):
            return "Create an inventory management system with stock tracking, low-stock alerts, movement history, and reporting. Implement CRUD operations with validation."
        elif any(kw in problem_lower for kw in ["crm", "cliente", "customer"]):
            return "Develop a CRM with lead pipeline management, contact tracking, sales stage progression, and conversion analytics. Include email notification for stage changes."
        else:
            return f"Based on analysis, this requires a structured implementation with: (1) Data models and validation, (2) Business logic with error handling, (3) API endpoints or automation workflows, (4) Tests for critical paths."

    def _fallback_evaluate(self, answer: str, problem: str) -> Tuple[float, List[str]]:
        """Deterministic evaluation of an answer."""
        issues = []
        score = 0.5

        if len(answer) < 30:
            issues.append("Answer is too short to be complete")
            score -= 0.2
        if "TODO" in answer or "FIXME" in answer:
            issues.append("Answer contains unresolved TODO markers")
            score -= 0.1
        if re.search(r'\bpass\b', answer) and len(answer) < 100:
            issues.append("Answer appears to be a placeholder")
            score -= 0.15
        if any(kw in answer.lower() for kw in ["eval(", "exec(", "os.system("]):
            issues.append("Answer contains security risks")
            score -= 0.2

        # Positive indicators
        if "error" in answer.lower() or "exception" in answer.lower():
            score += 0.1  # Error handling is good
        if "valid" in answer.lower() or "check" in answer.lower():
            score += 0.05  # Validation is good

        return max(0.1, min(0.9, score)), issues

    def _fallback_context_reasoning(self, problem: str, semantic_info: Dict[str, Any]) -> str:
        """Fallback reasoning using semantic info only."""
        op = semantic_info.get("operation", "UNKNOWN")
        goal = semantic_info.get("goal", "UNKNOWN")
        return f"Based on semantic classification as {op}/{goal}, this requires a {op.lower()}-oriented approach focusing on {goal.lower().replace('_', ' ')}."

    def _full_fallback(self, problem: str) -> ReasoningResult:
        """Complete fallback when no AI model is available."""
        answer = self._fallback_generate(problem, 1)
        return ReasoningResult(
            answer=answer,
            confidence=0.25,
            mode=ReasoningMode.FALLBACK,
            steps=[ReasoningStep(
                step_number=1,
                thought="No AI model available, using deterministic fallback",
                conclusion=answer[:200],
                confidence=0.25,
                source="fallback",
            )],
            source="fallback",
        )

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del ReasoningEngine."""
        return {
            "total_calls": self._call_count,
            "total_time_s": round(self._total_time, 2),
            "ai_available": self._ai is not None and self._ai.is_loaded,
            "semantic_available": self._semantic is not None and self._semantic.is_loaded,
            "memory_available": self._memory is not None,
            "modes": ["step_by_step", "self_reflect", "with_context", "auto"],
        }
