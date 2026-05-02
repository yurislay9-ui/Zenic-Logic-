"""
TITAN OMNISCALE X - IntentAgent

Agente IA que UNIFICA la comprensión semántica del usuario.
Reemplaza la lógica de clasificación de intención dispersa en 3 sitios:

  1. SemanticParser (TF-IDF + keyword maps) — level1_semantic_engine/parser.py
  2. SemanticEngine._fallback_classify (keyword matching) — semantic_engine.py
  3. MiniAIEngine.classify_intent + _fallback_classify — mini_ai_engine.py

Arquitectura del IntentAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → IntentOutput
  - SemanticEngine path: Si embeddings disponibles → classify_intent → merge
  - Fallback path: TF-IDF determinista + regex (sin LLM, sin embeddings)

Siempre produce un IntentOutput compatible con el pipeline existente.
El Orchestrator puede convertir IntentOutput → IntentPayload directamente.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)


# ============================================================
#  VALID CONSTANTS (shared with MiniAIEngine for consistency)
# ============================================================

VALID_OPERATIONS = frozenset({
    "CREATE", "REFACTOR", "DELETE", "SEARCH",
    "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE",
})

VALID_GOALS = frozenset({
    "COMPLEXITY_REDUCTION", "MODERN_PATTERN", "BUG_FIX",
    "FEATURE_ADD", "SECURITY_HARDEN", "PERFORMANCE", "READABILITY",
})

VALID_LANGUAGES = frozenset({
    "python", "kotlin", "go", "javascript", "typescript",
    "java", "rust", "c", "cpp", "ruby",
})

# Extension → language mapping
EXT_LANG_MAP: Dict[str, str] = {
    ".py": "python", ".kt": "kotlin", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c", ".h": "c",
}

# Code fence lang → language mapping
FENCE_LANG_MAP: Dict[str, str] = {
    "python": "python", "py": "python",
    "kotlin": "kotlin", "kt": "kotlin",
    "go": "go", "golang": "go",
    "javascript": "javascript", "js": "javascript",
    "typescript": "typescript", "ts": "typescript",
    "java": "java", "rust": "rust", "rs": "rust",
    "c": "c", "cpp": "cpp", "c++": "cpp",
    "ruby": "ruby", "rb": "ruby",
}

# Keyword maps for fallback classification (EN + ES)
OP_KEYWORDS: Dict[str, List[str]] = {
    "CREATE": ["create", "new", "add", "implement", "build", "make",
               "crear", "nuevo", "agregar", "generar", "construir"],
    "REFACTOR": ["refactor", "restructure", "reorganize", "clean", "simplify",
                 "refactorizar", "reestructurar", "reorganizar", "limpiar"],
    "DELETE": ["delete", "remove", "eliminate", "drop", "prune",
               "eliminar", "borrar", "quitar"],
    "SEARCH": ["search", "find", "where", "locate", "grep",
               "buscar", "encontrar", "donde", "localizar"],
    "ANALYZE": ["analyze", "review", "check", "examine", "inspect", "audit",
                "analizar", "revisar", "verificar", "inspeccionar"],
    "EXPLAIN": ["explain", "describe", "what does", "how does", "why",
                "explicar", "describir", "como funciona", "que hace"],
    "DEBUG": ["debug", "fix", "correct", "bug", "error", "crash",
              "depurar", "corregir", "arreglar", "fallo"],
    "OPTIMIZE": ["optimize", "improve", "faster", "performance", "accelerate",
                 "optimizar", "mejorar", "acelerar", "rendimiento"],
}

GOAL_KEYWORDS: Dict[str, List[str]] = {
    "BUG_FIX": ["bug", "fix", "error", "wrong", "broken", "crash",
                "corregir", "arreglar", "fallo", "falla"],
    "FEATURE_ADD": ["add", "new", "feature", "implement", "extend",
                    "agregar", "nueva", "implementar", "extender"],
    "SECURITY_HARDEN": ["security", "auth", "login", "token", "crypto", "vulnerability",
                        "seguridad", "autenticacion", "vulnerabilidad"],
    "PERFORMANCE": ["optimize", "fast", "slow", "performance", "latency", "speed",
                    "optimizar", "rapido", "lento", "velocidad"],
    "MODERN_PATTERN": ["modern", "update", "upgrade", "migrate", "latest",
                       "moderno", "actualizar", "migrar"],
    "COMPLEXITY_REDUCTION": ["simplify", "reduce", "complex", "shorter",
                             "simplificar", "reducir", "complejo"],
    "READABILITY": ["readable", "clean", "comment", "document", "clear",
                    "legible", "limpio", "documentar", "claro"],
}

# Criticality keywords
CRITICALITY_KEYWORDS = {
    "critical": ["auth", "login", "password", "token", "jwt", "secret", "crypto",
                 "ssl", "tls", "certificate", "permission", "privilege",
                 "autenticacion", "contrasena", "secreto", "permiso"],
    "moderate": ["database", "db", "migration", "config", "setting",
                 "base de datos", "migracion", "configuracion"],
}


class IntentAgent(BaseAgent[IntentOutput]):
    """
    Agente de comprensión semántica que clasifica la intención del usuario.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt para el LLM con el mensaje del usuario
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → _classify_with_semantic_engine() si embeddings disponibles
    4. Si todo falla → fallback() con TF-IDF + regex determinista

    Produce siempre un IntentOutput que el Orchestrador convierte a IntentPayload.
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="intent")
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
        """Construye system + user prompt para clasificación de intención."""
        if isinstance(input_data, IntentInput):
            message = input_data.message
            context = input_data.context
        elif isinstance(input_data, str):
            message = input_data
            context = ""
        else:
            message = str(input_data)
            context = ""

        system_prompt = AgentPrompts.INTENT_SYSTEM
        user_prompt = AgentPrompts.INTENT_USER.format(message=message[:500])

        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"previous_context": context[:300]}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[IntentOutput]:
        """Parsea la respuesta del LLM a un IntentOutput válido."""
        # Limpiar texto del LLM (quitar think blocks, markdown)
        cleaned = self.clean_llm_text(raw_response)

        # Intentar extraer JSON
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_intent_output(json_data, source="llm")

        # Si no hay JSON, intentar parsear texto libre
        return self._parse_free_text(cleaned, source="llm")

    def fallback(self, input_data: Any) -> IntentOutput:
        """
        Fallback determinista: TF-IDF simplificado + regex.

        Sin LLM, sin embeddings, 100% determinista.
        Prioriza: SmartMemory cache → SemanticEngine → TF-IDF + regex
        """
        import time as _time
        start = _time.time()

        if isinstance(input_data, IntentInput):
            message = input_data.message
        elif isinstance(input_data, str):
            message = input_data
        else:
            message = str(input_data)

        # 1. SmartMemory cache lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(message)
                if cached and cached.get("operation") and cached.get("goal"):
                    op = cached["operation"]
                    goal = cached["goal"]
                    if op in VALID_OPERATIONS and goal in VALID_GOALS:
                        result = IntentOutput(
                            operation=op,
                            goal=goal,
                            target=cached.get("target", "unknown"),
                            language=cached.get("language", "python"),
                            entities=cached.get("entities", {}),
                            template_type=cached.get("template_type", "generic"),
                            criticality=cached.get("criticality", "standard"),
                            confidence=cached.get("importance", 0.5),
                            source="fallback",
                        )
                        self._update_stats("fallback", int((_time.time() - start) * 1000))
                        return result
            except Exception as e:
                logger.debug(f"IntentAgent: SmartMemory lookup failed: {e}")

        # 2. SemanticEngine classification (if available)
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                sem_result = self._semantic_engine.classify_intent(message)
                if sem_result and sem_result.confidence > 0.3:
                    target, lang = self._extract_target_and_language(message)
                    code_lang, raw_code = self._extract_code_block(message)
                    entities = self._extract_entities(message)

                    output = IntentOutput(
                        operation=sem_result.operation,
                        goal=sem_result.goal,
                        target=target,
                        language=code_lang or lang,
                        entities=entities,
                        template_type=self._infer_template_type(sem_result.operation, target),
                        criticality=self._infer_criticality(message),
                        confidence=sem_result.confidence,
                        source="fallback",
                    )

                    # Cache in SmartMemory
                    self._cache_in_smart_memory(message, output)

                    self._update_stats("fallback", int((_time.time() - start) * 1000))
                    return output
            except Exception as e:
                logger.debug(f"IntentAgent: SemanticEngine classification failed: {e}")

        # 3. Pure TF-IDF + regex fallback (no external deps)
        result = self._tfidf_fallback(message)
        self._update_stats("fallback", int((_time.time() - start) * 1000))
        return result

    # ============================================================
    #  CONVERSION: IntentOutput → IntentPayload (for pipeline compat)
    # ============================================================

    def to_intent_payload(self, output: IntentOutput, context: str = "") -> Any:
        """
        Convierte IntentOutput a IntentPayload para compatibilidad
        con el pipeline existente.

        Este método es el CABLE que conecta el nuevo sistema de agentes
        con el pipeline Legacy.
        """
        from src.core.shared.contracts import IntentPayload, OperationType, GoalType

        # Map string → OperationType/GoalType constants
        op = output.operation if output.operation in VALID_OPERATIONS else OperationType.SEARCH
        goal = output.goal if output.goal in VALID_GOALS else GoalType.FEATURE_ADD

        # Build scrap_query for GitHub search
        scrap_query = ""
        if op in [OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR]:
            scrap_query = f"modern {goal} {op} {output.language}"

        return IntentPayload(
            op=op,
            target=output.target or "unknown",
            goal=goal,
            scrap_query=scrap_query,
            confidence=output.confidence,
            language=output.language or "python",
            raw_code="",  # Se rellena aparte si hay código
            context=context,
        )

    # ============================================================
    #  CLASSIFY: Método principal de alto nivel
    # ============================================================

    def classify(self, message: str, context: str = "") -> IntentOutput:
        """
        Clasifica la intención del usuario.

        Este es el método que el Orchestrator debe llamar.
        Internamente usa AgentRunner.run() → LLM → fallback.

        Args:
            message: Mensaje del usuario
            context: Contexto adicional (conversación previa, etc.)

        Returns:
            IntentOutput con la clasificación completa
        """
        input_data = IntentInput(message=message, context=context)
        # NOTA: AgentRunner.run() se llama desde fuera (el Orchestrator lo tiene)
        # Aquí solo proporcionamos la lógica del agente.
        # El Orchestrator hace: runner.run(intent_agent, IntentInput(...))
        # Por conveniencia, también ofrecemos classify_direct():
        return self.fallback(input_data)

    def classify_with_runner(self, runner: Any, message: str,
                             context: str = "") -> IntentOutput:
        """
        Clasifica usando el AgentRunner completo (LLM + fallback).

        Args:
            runner: Instancia de AgentRunner
            message: Mensaje del usuario
            context: Contexto adicional

        Returns:
            IntentOutput
        """
        input_data = IntentInput(message=message, context=context)
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, IntentOutput):
            return result.data

        # Si todo falló, usar fallback directo
        return self.fallback(input_data)

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _json_to_intent_output(self, data: Dict[str, Any],
                               source: str = "llm") -> Optional[IntentOutput]:
        """Convierte un dict JSON a IntentOutput, validando campos."""
        operation = data.get("operation", "").upper()
        goal = data.get("goal", "").upper()

        if operation not in VALID_OPERATIONS:
            operation = "SEARCH"
        if goal not in VALID_GOALS:
            goal = "FEATURE_ADD"

        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {"raw": str(entities)}

        language = data.get("language", "python").lower()
        if language not in VALID_LANGUAGES:
            language = "python"

        target = str(data.get("target", "")).strip()
        template_type = str(data.get("template_type", "generic")).strip()
        criticality = str(data.get("criticality", "standard")).strip()
        if criticality not in ("standard", "moderate", "critical"):
            criticality = "standard"

        return IntentOutput(
            operation=operation,
            goal=goal,
            target=target,
            language=language,
            entities=entities,
            template_type=template_type,
            criticality=criticality,
            confidence=confidence,
            source=source,
        )

    def _parse_free_text(self, text: str, source: str = "llm") -> Optional[IntentOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        text_upper = text.upper().strip()

        # Intentar encontrar operación
        operation = "SEARCH"
        for op in VALID_OPERATIONS:
            if op in text_upper:
                operation = op
                break

        # Intentar encontrar goal
        goal = "FEATURE_ADD"
        for g in VALID_GOALS:
            if g in text_upper:
                goal = g
                break

        # Confidence baja para texto libre parseado
        return IntentOutput(
            operation=operation,
            goal=goal,
            confidence=0.4,
            source=source,
        )

    def _tfidf_fallback(self, message: str) -> IntentOutput:
        """
        Fallback TF-IDF simplificado + regex.
        Reemplaza la lógica del SemanticParser para clasificación sin modelo.
        """
        text_lower = message.lower()

        # --- Operation classification (keyword scoring) ---
        best_op = "SEARCH"
        best_op_score = 0
        for op, keywords in OP_KEYWORDS.items():
            score = 0
            for kw in keywords:
                # Word boundary match scores higher than substring
                if kw in text_lower.split():
                    score += 2
                elif kw in text_lower:
                    score += 1
            if score > best_op_score:
                best_op_score = score
                best_op = op

        # --- Goal classification (keyword scoring) ---
        best_goal = "FEATURE_ADD"
        best_goal_score = 0
        for goal, keywords in GOAL_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in text_lower.split():
                    score += 2
                elif kw in text_lower:
                    score += 1
            if score > best_goal_score:
                best_goal_score = score
                best_goal = goal

        # --- Target extraction (regex) ---
        target, lang = self._extract_target_and_language(message)
        code_lang, raw_code = self._extract_code_block(message)
        final_lang = code_lang or lang

        # --- Entities extraction ---
        entities = self._extract_entities(message)

        # --- Criticality ---
        criticality = self._infer_criticality(message)

        # --- Template type ---
        template_type = self._infer_template_type(best_op, target)

        # --- Confidence (0-0.5 range for fallback) ---
        confidence = min((best_op_score + best_goal_score) / 20.0, 0.5)

        output = IntentOutput(
            operation=best_op,
            goal=best_goal,
            target=target,
            language=final_lang,
            entities=entities,
            template_type=template_type,
            criticality=criticality,
            confidence=confidence,
            source="fallback",
        )

        # Cache in SmartMemory
        self._cache_in_smart_memory(message, output)

        return output

    @staticmethod
    def _extract_target_and_language(text: str) -> Tuple[str, str]:
        """Extrae el archivo objetivo y el lenguaje del texto."""
        # File extension match
        tgt = re.search(
            r'([\w\.\-]+(?:\.kt|\.py|\.go|\.js|\.ts|\.java|\.rs|\.c|\.cpp|\.h|\.rb))',
            text,
        )
        target = tgt.group(1) if tgt else "unknown"

        # Language from extension
        lang = "python"
        for ext, l in EXT_LANG_MAP.items():
            if ext in target:
                lang = l
                break

        return target, lang

    @staticmethod
    def _extract_code_block(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrae bloques de código de un mensaje (markdown fences)."""
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            lang_hint, code = matches[0]
            lang = FENCE_LANG_MAP.get(lang_hint.lower(), "python")
            return lang, code

        # Detect inline code indicators
        code_indicators = [
            'def ', 'class ', 'function ', 'fun ', 'func ',
            'import ', 'from ', 'package ',
        ]
        lines = text.strip().split('\n')
        code_lines = [l for l in lines if any(ind in l for ind in code_indicators)]
        if code_lines:
            return 'python', text.strip()

        return None, None

    @staticmethod
    def _extract_entities(text: str) -> Dict[str, Any]:
        """Extrae entidades nombradas del texto (funciones, clases, archivos)."""
        entities: Dict[str, Any] = {}

        # Function names (EN + ES keywords)
        func_match = re.search(
            r'(?:function|func|def|fun|funci[oó]n)\s+(\w+)', text, re.IGNORECASE
        )
        if func_match:
            entities["function"] = func_match.group(1)

        # Class names (EN + ES keywords)
        class_match = re.search(r'(?:class|clase)\s+(\w+)', text, re.IGNORECASE)
        if class_match:
            entities["class"] = class_match.group(1)

        # File names
        file_match = re.search(
            r'([\w\.\-]+\.(?:py|kt|go|js|ts|java|rs|c|cpp|h|rb))',
            text,
        )
        if file_match:
            entities["file"] = file_match.group(1)

        return entities

    @staticmethod
    def _infer_criticality(message: str) -> str:
        """Infiere la criticidad del mensaje."""
        text_lower = message.lower()
        for kw in CRITICALITY_KEYWORDS["critical"]:
            if kw in text_lower:
                return "critical"
        for kw in CRITICALITY_KEYWORDS["moderate"]:
            if kw in text_lower:
                return "moderate"
        return "standard"

    @staticmethod
    def _infer_template_type(operation: str, target: str) -> str:
        """Infiere el tipo de template basado en la operación y target."""
        target_lower = target.lower()

        if "api" in target_lower or "server" in target_lower or "endpoint" in target_lower:
            return "api"
        if "web" in target_lower or "page" in target_lower or "frontend" in target_lower:
            return "web"
        if "cli" in target_lower or "command" in target_lower:
            return "cli"
        if "data" in target_lower or "model" in target_lower or "schema" in target_lower:
            return "data"
        if "mobile" in target_lower or "app" in target_lower:
            return "mobile"
        if operation == "OPTIMIZE" or operation == "DEBUG":
            return "automation"

        return "generic"

    def _cache_in_smart_memory(self, message: str, output: IntentOutput) -> None:
        """Cache el resultado en SmartMemory si está disponible."""
        if not self._smart_memory:
            return
        try:
            self._smart_memory.save_to_cache(
                query=message,
                response=f"op={output.operation},goal={output.goal}",
                operation=output.operation,
                goal=output.goal,
                importance=output.confidence,
            )
        except Exception as e:
            logger.debug(f"IntentAgent: Failed to cache in SmartMemory: {e}")
