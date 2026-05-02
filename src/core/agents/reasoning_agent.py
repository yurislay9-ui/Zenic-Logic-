"""
TITAN OMNISCALE X - ReasoningAgent

Agente IA que UNIFICA el razonamiento avanzado del sistema.
Reemplaza la lógica de razonamiento dispersa en 2 motores:

  1. ReasoningEngine (720 líneas, 3 modos step_by_step/self_reflect/with_context)
  2. ThinkingEngine.reason() + chain_of_thought() (858 líneas, general reasoning)

Arquitectura del ReasoningAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → ReasoningOutput
  - SemanticEngine path: Si embeddings disponibles → clasificación + contexto
  - SmartMemory path: RAG con soluciones previas
  - Fallback path: Razonamiento determinista por tipo de problema (sin LLM)

Produce un ReasoningOutput compatible con ReasoningResult del pipeline existente.
El Orchestrator puede convertir ReasoningOutput → ReasoningResult directamente.
"""

import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import (
    ReasoningInput, ReasoningOutput, ReasoningStep,
)
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Reasoning configuration
MAX_REASONING_STEPS = 3
MIN_CONFIDENCE_ACCEPT = 0.5

# Problem type → fallback response templates
PROBLEM_TEMPLATES = {
    "api": "Design a REST API with proper endpoints, request/response schemas, "
           "authentication middleware, and error handling. Use FastAPI for the "
           "framework and SQLite for persistence.",
    "auth": "Implement JWT-based authentication with token refresh, password "
            "hashing (bcrypt/PBKDF2), RBAC for authorization, and API key "
            "support for service-to-service communication.",
    "database": "Design a normalized database schema with proper foreign keys, "
                "indexes for query performance, parameterized queries for "
                "security, and migration scripts for schema evolution.",
    "invoice": "Build an invoice system with line items, tax calculation, "
               "discount support, PDF generation, and payment tracking.",
    "inventory": "Create an inventory management system with stock tracking, "
                 "low-stock alerts, movement history, and reporting.",
    "crm": "Develop a CRM with lead pipeline management, contact tracking, "
           "sales stage progression, and conversion analytics.",
    "automation": "Design an automation workflow with triggers, scheduled "
                  "actions, error handling, and notification dispatch.",
}

# Problem type detection keywords (EN + ES)
PROBLEM_KEYWORDS = {
    "api": ["api", "endpoint", "rest", "servidor", "server"],
    "auth": ["auth", "login", "seguridad", "security", "jwt", "token"],
    "database": ["database", "datos", "schema", "base de datos", "db"],
    "invoice": ["invoice", "factura", "billing", "cobro", "pago"],
    "inventory": ["inventory", "inventario", "stock", "almacen"],
    "crm": ["crm", "cliente", "customer", "ventas", "sales"],
    "automation": ["automat", "workflow", "schedule", "scheduler"],
}


class ReasoningAgent(BaseAgent[ReasoningOutput]):
    """
    Agente de razonamiento avanzado que unifica ReasoningEngine + ThinkingEngine.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según modo (step_by_step/self_reflect/with_context)
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback con razonamiento determinista
    4. Contexto inyectado desde SmartMemory + SemanticEngine

    Modos de razonamiento:
    - step_by_step: Descompone el problema en pasos explícitos
    - self_reflect: Genera → evalúa → refina (más confiable, más costoso)
    - with_context: Razonamiento con inyección de memoria + semántica
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="reasoning")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt según el modo de razonamiento."""
        if isinstance(input_data, ReasoningInput):
            query = input_data.query
            mode = input_data.mode
            context = input_data.context
        elif isinstance(input_data, str):
            query = input_data
            mode = "step_by_step"
            context = ""
        else:
            query = str(input_data)
            mode = "step_by_step"
            context = ""

        # Select system prompt based on mode
        mode_prompts = {
            "step_by_step": AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP,
            "self_reflect": AgentPrompts.REASONING_SYSTEM_SELF_REFLECT,
            "with_context": AgentPrompts.REASONING_SYSTEM_WITH_CONTEXT,
        }
        system_prompt = mode_prompts.get(mode, AgentPrompts.REASONING_SYSTEM_STEP_BY_STEP)

        # Build user prompt
        user_prompt = AgentPrompts.REASONING_USER.format(query=query[:500])

        # Inject context if available
        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"additional_context": context[:300]}
            )

        # Inject memory context if available
        mem_ctx = self._get_memory_context(query)
        if mem_ctx:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"relevant_experience": mem_ctx[:300]}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[ReasoningOutput]:
        """Parsea la respuesta del LLM a un ReasoningOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_reasoning_output(json_data, source="llm")

        # Try to extract structured answer from text
        return self._parse_free_text_reasoning(cleaned, source="llm")

    def fallback(self, input_data: Any) -> ReasoningOutput:
        """
        Fallback determinista: razonamiento por tipo de problema.

        Sin LLM, sin embeddings, 100% determinista.
        Prioriza: SmartMemory cache → SemanticEngine → Template reasoning
        """
        start = time.time()

        if isinstance(input_data, ReasoningInput):
            query = input_data.query
            mode = input_data.mode
            context = input_data.context
            max_steps = input_data.max_steps
        elif isinstance(input_data, str):
            query = input_data
            mode = "step_by_step"
            context = ""
            max_steps = 3
        else:
            query = str(input_data)
            mode = "step_by_step"
            context = ""
            max_steps = 3

        # 1. SmartMemory cache lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(query)
                if cached and cached.get("response"):
                    answer = cached["response"]
                    steps = self._build_fallback_steps(query, max_steps)
                    duration_ms = int((time.time() - start) * 1000)
                    self._update_stats("fallback", duration_ms)
                    return ReasoningOutput(
                        answer=answer[:500],
                        confidence=0.5,
                        mode=mode,
                        steps=steps,
                        source="fallback",
                        total_duration_ms=duration_ms,
                    )
            except Exception as e:
                logger.debug(f"ReasoningAgent: SmartMemory lookup failed: {e}")

        # 2. SemanticEngine-assisted reasoning
        semantic_info = {}
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                sem_result = self._semantic_engine.classify_intent(query)
                if sem_result and sem_result.confidence > 0.3:
                    semantic_info = {
                        "operation": sem_result.operation,
                        "goal": sem_result.goal,
                        "confidence": sem_result.confidence,
                    }
            except Exception as e:
                logger.debug(f"ReasoningAgent: SemanticEngine failed: {e}")

        # 3. Deterministic fallback reasoning
        answer = self._deterministic_reason(query, semantic_info)
        steps = self._build_fallback_steps(query, max_steps, answer)

        # Build context_used list
        context_used = []
        if semantic_info:
            context_used.append(
                f"semantic:{semantic_info['operation']}/{semantic_info['goal']}"
            )

        # Memory hits
        memory_hits = 0
        if self._smart_memory:
            try:
                if self._semantic_engine and self._semantic_engine.is_loaded:
                    similar = self._smart_memory.find_similar_solutions(query, top_k=2)
                    memory_hits = len(similar)
                    context_used.extend(
                        f"memory:{s.get('similarity', 0):.2f}" for s in similar
                    )
            except Exception:
                pass

        # Save to memory
        self._save_to_memory(query, answer, mode)

        # Estimate confidence
        confidence = 0.3
        if semantic_info and semantic_info.get("confidence", 0) > 0.5:
            confidence = 0.4
        if memory_hits > 0:
            confidence += 0.05

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        return ReasoningOutput(
            answer=answer,
            confidence=min(confidence, 0.5),
            mode=mode,
            steps=steps,
            refinements=0,
            context_used=context_used,
            memory_hits=memory_hits,
            source="fallback",
            total_duration_ms=duration_ms,
        )

    # ============================================================
    #  CONVERSION: ReasoningOutput → ReasoningResult (pipeline compat)
    # ============================================================

    def to_reasoning_result(self, output: ReasoningOutput) -> Any:
        """
        Convierte ReasoningOutput a ReasoningResult para compatibilidad
        con el pipeline existente (Phase 8 API).
        """
        from src.core.reasoning_engine import ReasoningMode, ReasoningResult, ReasoningStep as REStep

        mode_map = {
            "step_by_step": ReasoningMode.STEP_BY_STEP,
            "self_reflect": ReasoningMode.SELF_REFLECT,
            "with_context": ReasoningMode.WITH_CONTEXT,
        }
        mode = mode_map.get(output.mode, ReasoningMode.FALLBACK)

        # Convert steps
        converted_steps = []
        for s in output.steps:
            converted_steps.append(REStep(
                step_number=s.step_number,
                thought=s.description,
                conclusion=s.conclusion,
                confidence=0.5,
                source=output.source,
            ))

        return ReasoningResult(
            answer=output.answer,
            confidence=output.confidence,
            mode=mode,
            steps=converted_steps,
            total_duration_ms=output.total_duration_ms,
            refinements=output.refinements,
            context_used=bool(output.context_used),
            memory_hits=output.memory_hits,
            source=output.source,
        )

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def reason(self, query: str, mode: str = "step_by_step",
               context: str = "", max_steps: int = 3) -> ReasoningOutput:
        """
        Método principal de razonamiento (sin AgentRunner).

        Para razonamiento con LLM, usar:
            output = agent.classify_with_runner(runner, query, mode, context)
        """
        input_data = ReasoningInput(
            query=query, mode=mode, context=context, max_steps=max_steps
        )
        return self.fallback(input_data)

    def reason_with_runner(self, runner: Any, query: str,
                           mode: str = "step_by_step",
                           context: str = "",
                           max_steps: int = 3) -> ReasoningOutput:
        """Razona usando AgentRunner (LLM → fallback)."""
        input_data = ReasoningInput(
            query=query, mode=mode, context=context, max_steps=max_steps
        )
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, ReasoningOutput):
            return result.data

        return self.fallback(input_data)

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _get_memory_context(self, query: str) -> str:
        """Obtiene contexto relevante de SmartMemory."""
        if not self._smart_memory:
            return ""
        parts = []

        try:
            working = self._smart_memory.get_working_context(max_tokens=100)
            if working:
                parts.append(working)
        except Exception:
            pass

        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(query, top_k=1)
                for sol in similar:
                    parts.append(f"Past: {sol['solution'][:100]}")
            except Exception:
                pass

        return " | ".join(parts) if parts else ""

    def _save_to_memory(self, query: str, answer: str,
                        mode: str) -> None:
        """Guarda resultado en SmartMemory."""
        if not self._smart_memory:
            return
        try:
            self._smart_memory.save_to_cache(query, answer[:500], mode, "", 0.6)
        except Exception as e:
            logger.debug(f"ReasoningAgent: Memory save failed: {e}")

    def _deterministic_reason(self, problem: str,
                              semantic_info: Dict[str, Any]) -> str:
        """Razonamiento determinista basado en tipo de problema."""
        problem_lower = problem.lower()

        # Detect problem type
        detected_type = None
        best_score = 0
        for ptype, keywords in PROBLEM_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in problem_lower)
            if score > best_score:
                best_score = score
                detected_type = ptype

        # Get template response
        if detected_type and detected_type in PROBLEM_TEMPLATES:
            answer = PROBLEM_TEMPLATES[detected_type]
        else:
            answer = (
                "Based on analysis, this requires a structured implementation with: "
                "(1) Data models and validation, (2) Business logic with error "
                "handling, (3) API endpoints or automation workflows, "
                "(4) Tests for critical paths."
            )

        # Enhance with semantic info if available
        if semantic_info:
            op = semantic_info.get("operation", "UNKNOWN")
            goal = semantic_info.get("goal", "UNKNOWN")
            answer = (
                f"Semantic classification: {op}/{goal}. {answer}"
            )

        return answer

    def _build_fallback_steps(self, problem: str, max_steps: int,
                              final_answer: str = "") -> List[ReasoningStep]:
        """Construye pasos de razonamiento deterministas."""
        steps = []
        problem_lower = problem.lower()

        # Step 1: Identify problem type
        type_desc = "general software engineering"
        for ptype, keywords in PROBLEM_KEYWORDS.items():
            if any(kw in problem_lower for kw in keywords):
                type_desc = ptype
                break

        steps.append(ReasoningStep(
            step_number=1,
            description=f"Identified problem type: {type_desc}",
            conclusion=f"This is a {type_desc} problem requiring structured implementation.",
        ))

        # Step 2: Apply standard patterns
        if max_steps >= 2:
            steps.append(ReasoningStep(
                step_number=2,
                description="Apply standard patterns for this problem type",
                conclusion="Apply: validate inputs, process business logic, "
                           "handle errors gracefully, return structured results.",
            ))

        # Step 3: Final conclusion
        if max_steps >= 3:
            steps.append(ReasoningStep(
                step_number=3,
                description="Synthesize final answer",
                conclusion=final_answer[:200] if final_answer else
                           "Implementation should follow established patterns "
                           "with proper error handling and validation.",
            ))

        return steps[:max_steps]

    def _json_to_reasoning_output(self, data: Dict[str, Any],
                                  source: str = "llm") -> Optional[ReasoningOutput]:
        """Convierte un dict JSON a ReasoningOutput."""
        answer = str(data.get("answer", "")).strip()
        if not answer:
            return None

        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        # Parse steps
        steps = []
        raw_steps = data.get("steps", [])
        if isinstance(raw_steps, list):
            for i, s in enumerate(raw_steps):
                if isinstance(s, dict):
                    steps.append(ReasoningStep(
                        step_number=s.get("step_number", i + 1),
                        description=s.get("description", ""),
                        conclusion=s.get("conclusion", ""),
                    ))

        refinements = data.get("refinements", 0)
        try:
            refinements = int(refinements)
        except (ValueError, TypeError):
            refinements = 0

        context_used = data.get("context_used", [])
        if isinstance(context_used, str):
            context_used = [context_used]

        return ReasoningOutput(
            answer=answer,
            confidence=confidence,
            mode="step_by_step",
            steps=steps,
            refinements=refinements,
            context_used=context_used if isinstance(context_used, list) else [],
            memory_hits=0,
            source=source,
        )

    def _parse_free_text_reasoning(self, text: str,
                                   source: str = "llm") -> Optional[ReasoningOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Extract conclusion markers
        conclusion = text
        markers = ["therefore", "thus", "conclusion:", "so,", "hence",
                    "por lo tanto", "en conclusión", "resultado:"]
        text_lower = text.lower()
        for marker in markers:
            idx = text_lower.find(marker)
            if idx >= 0:
                conclusion = text[idx + len(marker):].strip()[:300]
                break

        # Estimate confidence from text
        confidence = 0.5
        certainty = ["certainly", "clearly", "definitely", "obviously"]
        hedging = ["maybe", "perhaps", "might", "could be", "possibly"]
        if any(m in text_lower for m in certainty):
            confidence += 0.1
        if any(m in text_lower for m in hedging):
            confidence -= 0.1

        return ReasoningOutput(
            answer=text[:500],
            confidence=max(0.1, min(0.9, confidence)),
            mode="step_by_step",
            steps=[ReasoningStep(
                step_number=1,
                description="Free-text reasoning from LLM",
                conclusion=conclusion[:300],
            )],
            source=source,
        )
