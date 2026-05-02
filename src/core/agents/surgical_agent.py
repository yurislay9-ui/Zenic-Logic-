"""
TITAN OMNISCALE X - SurgicalAgent (F2)

Agente quirúrgico de clasificación de intención que UNIFICA y REEMPLAZA
la lógica dispersa en 3 subsistemas redundantes:

  1. SemanticParser (TF-IDF + keyword maps) — level1_semantic_engine/parser.py
  2. SemanticEngine._fallback_classify() — semantic_engine.py
  3. MiniAIEngine.classify_intent() — mini_ai_engine.py

El IntentAgent original (594 líneas) se comprime aquí con fusión
multi-señal quirúrgica en ~250 líneas.

Arquitectura SurgicalAgent:
  ┌─────────────────────────────────────────────────┐
  │  CABLE 1: SmartMemory cache ──► hit? → return   │
  │  CABLE 2: SemanticEngine embed ──► high conf? →  │
  │  CABLE 3: LLM (AgentRunner) ──► valid JSON? →   │
  │  CABLE 4: TF-IDF determinista ──► always works   │
  └─────────────────────────────────────────────────┘

Fusión multi-señal:
  - Si LLM + SemanticEngine coinciden → confianza ALTA (0.7-1.0)
  - Si solo LLM o solo Semantic → confianza MEDIA (0.4-0.7)
  - Si solo TF-IDF → confianza BAJA (0.0-0.4)
  - Calibración: Ajusta confianza según historial de aciertos

Restricciones de diseño:
  - ≤600 tokens por llamada LLM (Qwen3-0.6B)
  - Fallback determinista siempre disponible
  - Compatible con Android/Termux, 500MB RAM
"""

import re
import time
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.prompts import AgentPrompts

logger = logging.getLogger(__name__)

# ── Constantes compartidas (reutilizadas desde IntentAgent original) ──

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

# ── Mapas de keywords quirúrgicos (EN + ES, ultra-compactos) ──

OP_KW: Dict[str, List[str]] = {
    "CREATE":   ["create","new","add","build","make","crear","nuevo","generar"],
    "REFACTOR": ["refactor","restructure","clean","simplify","refactorizar","limpiar"],
    "DELETE":   ["delete","remove","eliminate","drop","eliminar","borrar","quitar"],
    "SEARCH":   ["search","find","where","locate","buscar","encontrar","donde"],
    "ANALYZE":  ["analyze","review","check","inspect","audit","analizar","revisar","verificar"],
    "EXPLAIN":  ["explain","describe","how does","why","explicar","describir","como funciona"],
    "DEBUG":    ["debug","fix","correct","bug","error","depurar","corregir","arreglar","fallo"],
    "OPTIMIZE": ["optimize","improve","faster","performance","optimizar","mejorar","acelerar"],
}

GOAL_KW: Dict[str, List[str]] = {
    "BUG_FIX":           ["bug","fix","error","broken","crash","corregir","fallo","falla"],
    "FEATURE_ADD":       ["add","new","feature","implement","agregar","nueva","implementar"],
    "SECURITY_HARDEN":   ["security","auth","token","crypto","vulnerability","seguridad"],
    "PERFORMANCE":       ["optimize","fast","slow","latency","optimizar","rapido","lento"],
    "COMPLEXITY_REDUCTION":["simplify","reduce","complex","simplificar","reducir","complejo"],
    "MODERN_PATTERN":    ["modern","update","migrate","moderno","actualizar","migrar"],
    "READABILITY":       ["readable","clean","document","legible","limpio","documentar"],
}

CRIT_KW: Dict[str, List[str]] = {
    "critical": ["auth","login","password","token","jwt","secret","crypto","ssl","permiso"],
    "moderate": ["database","db","migration","config","base de datos","migracion"],
}

# Extension → language (compacto)
EXT_LANG = {
    ".py":"python",".kt":"kotlin",".go":"go",".js":"javascript",".ts":"typescript",
    ".java":"java",".rs":"rust",".rb":"ruby",".cpp":"cpp",".c":"c",".h":"c",
}

FENCE_LANG = {
    "python":"python","py":"python","kotlin":"kotlin","kt":"kotlin",
    "go":"go","javascript":"javascript","js":"javascript",
    "typescript":"typescript","ts":"typescript","java":"java",
    "rust":"rust","rs":"rust","c":"c","cpp":"cpp","ruby":"ruby","rb":"ruby",
}


class SurgicalAgent(BaseAgent[IntentOutput]):
    """
    Agente quirúrgico F2: Clasificación de intención con fusión multi-señal.

    Flujo de ejecución (4 cables, en orden de costo ascendente):
    1. SmartMemory cache → Si hit, retorno inmediato (0ms LLM)
    2. SemanticEngine → Si embeddings disponibles y conf > 0.4, fusión con TF-IDF
    3. LLM via AgentRunner → Si disponible, intenta clasificación con Qwen3
    4. TF-IDF determinista → Siempre funciona, sin dependencias

    Fusión: Cuando múltiples señales coinciden, la confianza se calibra al alza.
    Cuando discrepan, la confianza se calibra a la baja.

    Reemplaza:
    - IntentAgent original (594 líneas) → SurgicalAgent (~250 líneas)
    - SemanticParser.classify() (Level 1)
    - MiniAIEngine.classify_intent()
    - SemanticEngine._fallback_classify()
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="surgical")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        # Calibración adaptativa: trackea aciertos por operation
        self._calibration: Dict[str, Dict[str, int]] = {
            op: {"hits": 0, "misses": 0} for op in VALID_OPERATIONS
        }

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
        """Construye prompt quirúrgico para clasificación de intención."""
        if isinstance(input_data, IntentInput):
            message = input_data.message
            context = input_data.context
        elif isinstance(input_data, str):
            message = input_data
            context = ""
        else:
            message = str(input_data)
            context = ""

        # Prompt ultra-compacto para Qwen3-0.6B (≤600 tokens)
        system = (
            "Classify intent. Reply ONLY JSON:\n"
            '{"operation":"CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE",'
            '"goal":"COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY",'
            '"target":"file_or_component","language":"python|kotlin|go|js|ts|java|rust|c|cpp|ruby",'
            '"entities":{"key":"value"},"template_type":"api|web|cli|data|mobile|automation|generic",'
            '"criticality":"standard|moderate|critical","confidence":0.0-1.0}'
        )
        user = f"Classify: {message[:400]}"
        if context:
            user += f"\nCtx: {context[:150]}"
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[IntentOutput]:
        """Parsea respuesta del LLM a IntentOutput válido."""
        cleaned = self.clean_llm_text(raw_response)
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._dict_to_output(json_data, source="llm")
        return self._parse_freetext(cleaned, source="llm")

    def fallback(self, input_data: Any) -> IntentOutput:
        """Fallback determinista: SmartMemory → SemanticEngine → TF-IDF."""
        start = time.time()

        if isinstance(input_data, IntentInput):
            message = input_data.message
        elif isinstance(input_data, str):
            message = input_data
        else:
            message = str(input_data)

        # CABLE 1: SmartMemory cache
        mem_result = self._cable_memory(message)
        if mem_result:
            self._update_stats("fallback", int((time.time() - start) * 1000))
            return mem_result

        # CABLE 2: SemanticEngine embeddings
        sem_result = self._cable_semantic(message)

        # CABLE 4: TF-IDF determinista (siempre disponible)
        tfidf_result = self._cable_tfidf(message)

        # FUSIÓN multi-señal
        fused = self._fuse_signals(tfidf_result, sem_result)

        # Cache en SmartMemory
        self._cache_result(message, fused)

        self._update_stats("fallback", int((time.time() - start) * 1000))
        return fused

    # ============================================================
    #  HIGH-LEVEL API (compatible con IntentAgent anterior)
    # ============================================================

    def classify(self, message: str, context: str = "") -> IntentOutput:
        """Clasifica intención. Método principal que el Orchestrator llama."""
        input_data = IntentInput(message=message, context=context)
        return self.fallback(input_data)

    def classify_with_runner(self, runner: Any, message: str,
                             context: str = "") -> IntentOutput:
        """Clasifica usando AgentRunner (LLM → fallback fusionado)."""
        input_data = IntentInput(message=message, context=context)
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, IntentOutput):
            # Fusión: combinar resultado LLM con TF-IDF para calibrar confianza
            tfidf_result = self._cable_tfidf(message)
            llm_result = result.data
            return self._fuse_signals(tfidf_result, llm_result)

        return self.fallback(input_data)

    def to_intent_payload(self, output: IntentOutput, context: str = "") -> Any:
        """
        CABLE de compatibilidad: Convierte IntentOutput → IntentPayload
        para el pipeline existente (MacroRouter, APAPlanner, etc.).
        """
        from src.core.shared.contracts import IntentPayload, OperationType, GoalType

        op = output.operation if output.operation in VALID_OPERATIONS else OperationType.SEARCH
        goal = output.goal if output.goal in VALID_GOALS else GoalType.FEATURE_ADD

        scrap_query = ""
        if op in (OperationType.CREATE, OperationType.OPTIMIZE, OperationType.REFACTOR):
            scrap_query = f"modern {goal} {op} {output.language}"

        return IntentPayload(
            op=op,
            target=output.target or "unknown",
            goal=goal,
            scrap_query=scrap_query,
            confidence=output.confidence,
            language=output.language or "python",
            raw_code="",
            context=context,
        )

    # ============================================================
    #  CALIBRACIÓN ADAPTATIVA (aprende de aciertos/fallos)
    # ============================================================

    def report_accuracy(self, operation: str, was_correct: bool) -> None:
        """Reporta si la clasificación fue correcta (feedback loop)."""
        if operation in self._calibration:
            if was_correct:
                self._calibration[operation]["hits"] += 1
            else:
                self._calibration[operation]["misses"] += 1

    def get_calibration_factor(self, operation: str) -> float:
        """Factor de calibración basado en historial (0.5-1.5)."""
        if operation not in self._calibration:
            return 1.0
        cal = self._calibration[operation]
        total = cal["hits"] + cal["misses"]
        if total < 3:
            return 1.0  # Sin datos suficientes
        accuracy = cal["hits"] / total
        # Factor > 1.0 = aumenta confianza (historial bueno)
        # Factor < 1.0 = reduce confianza (historial malo)
        return 0.5 + accuracy  # Rango: 0.5 - 1.5

    # ============================================================
    #  4 CABLES DE CLASIFICACIÓN (en orden de costo)
    # ============================================================

    def _cable_memory(self, message: str) -> Optional[IntentOutput]:
        """CABLE 1: SmartMemory cache lookup (0ms LLM)."""
        if not self._smart_memory:
            return None
        try:
            cached = self._smart_memory.check_cache(message)
            if cached and cached.get("operation") and cached.get("goal"):
                op = cached["operation"]
                goal = cached["goal"]
                if op in VALID_OPERATIONS and goal in VALID_GOALS:
                    return IntentOutput(
                        operation=op, goal=goal,
                        target=cached.get("target", "unknown"),
                        language=cached.get("language", "python"),
                        entities=cached.get("entities", {}),
                        template_type=cached.get("template_type", "generic"),
                        criticality=cached.get("criticality", "standard"),
                        confidence=min(cached.get("importance", 0.5) * 1.1, 1.0),
                        source="cache",
                    )
        except Exception as e:
            logger.debug(f"SurgicalAgent: Memory cable failed: {e}")
        return None

    def _cable_semantic(self, message: str) -> Optional[IntentOutput]:
        """CABLE 2: SemanticEngine embeddings classification."""
        if not self._semantic_engine or not self._semantic_engine.is_loaded:
            return None
        try:
            sem_result = self._semantic_engine.classify_intent(message)
            if sem_result and sem_result.confidence > 0.3:
                target, lang = self._extract_target_and_lang(message)
                code_lang, _ = self._extract_code_block(message)
                entities = self._extract_entities(message)
                return IntentOutput(
                    operation=sem_result.operation,
                    goal=sem_result.goal,
                    target=target,
                    language=code_lang or lang,
                    entities=entities,
                    template_type=self._infer_template(sem_result.operation, target),
                    criticality=self._infer_criticality(message),
                    confidence=sem_result.confidence,
                    source="semantic",
                )
        except Exception as e:
            logger.debug(f"SurgicalAgent: Semantic cable failed: {e}")
        return None

    def _cable_tfidf(self, message: str) -> IntentOutput:
        """CABLE 4: TF-IDF + regex determinista (siempre funciona)."""
        text_lower = message.lower()

        # Operation scoring (word boundary > substring)
        best_op, best_op_score = "SEARCH", 0
        for op, keywords in OP_KW.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_op_score:
                best_op, best_op_score = op, score

        # Goal scoring
        best_goal, best_goal_score = "FEATURE_ADD", 0
        for goal, keywords in GOAL_KW.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_goal_score:
                best_goal, best_goal_score = goal, score

        # Target + language extraction
        target, lang = self._extract_target_and_lang(message)
        code_lang, _ = self._extract_code_block(message)
        entities = self._extract_entities(message)

        # Confidence: normalizado al rango 0.0-0.5 para fallback
        confidence = min((best_op_score + best_goal_score) / 20.0, 0.5)

        return IntentOutput(
            operation=best_op, goal=best_goal,
            target=target, language=code_lang or lang,
            entities=entities,
            template_type=self._infer_template(best_op, target),
            criticality=self._infer_criticality(message),
            confidence=confidence,
            source="tfidf",
        )

    # ============================================================
    #  FUSIÓN MULTI-SEÑAL (corazón del SurgicalAgent)
    # ============================================================

    def _fuse_signals(self, primary: IntentOutput,
                      secondary: Optional[IntentOutput]) -> IntentOutput:
        """
        Fusiona dos señales de clasificación con calibración adaptativa.

        Reglas de fusión:
        - Si ambas coinciden en operation → confianza ALTA
        - Si discrepan → prima la señal con mayor confianza, pero se reduce
        - Calibración: se aplica factor adaptativo por operation
        """
        if secondary is None:
            # Sin segunda señal, aplicar calibración
            cal_factor = self.get_calibration_factor(primary.operation)
            primary.confidence = min(primary.confidence * cal_factor, 1.0)
            primary.source = primary.source  # Preservar origen
            return primary

        # Ambas señales disponibles
        if primary.operation == secondary.operation and primary.goal == secondary.goal:
            # CONCORDANCIA TOTAL: confianza alta
            confidence = min((primary.confidence + secondary.confidence) / 2 + 0.15, 1.0)
            source = f"{primary.source}+{secondary.source}"
        elif primary.operation == secondary.operation:
            # Concordancia parcial en operation
            confidence = max(primary.confidence, secondary.confidence) * 0.9
            # Usar goal de la señal con mayor confianza
            goal = primary.goal if primary.confidence >= secondary.confidence else secondary.goal
            primary.goal = goal
            source = f"{primary.source}+{secondary.source}"
        else:
            # DISCREPANCIA: prima la de mayor confianza, pero se reduce
            if secondary.confidence > primary.confidence + 0.15:
                # La secundaria es significativamente mejor
                primary.operation = secondary.operation
                primary.goal = secondary.goal
                confidence = secondary.confidence * 0.85
            else:
                confidence = primary.confidence * 0.85
            source = primary.source

        # Aplicar calibración adaptativa
        cal_factor = self.get_calibration_factor(primary.operation)
        primary.confidence = min(confidence * cal_factor, 1.0)
        primary.source = source

        return primary

    # ============================================================
    #  EXTRACTORES COMPACTOS (regex quirúrgico)
    # ============================================================

    @staticmethod
    def _extract_target_and_lang(text: str) -> Tuple[str, str]:
        """Extrae archivo objetivo y lenguaje del texto."""
        tgt = re.search(r'([\w\.\-]+\.(?:kt|py|go|js|ts|java|rs|c|cpp|h|rb))', text)
        target = tgt.group(1) if tgt else "unknown"
        lang = "python"
        for ext, l in EXT_LANG.items():
            if ext in target:
                lang = l
                break
        return target, lang

    @staticmethod
    def _extract_code_block(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrae bloques de código (markdown fences + inline detection)."""
        matches = re.findall(r'```(\w*)\n(.*?)```', text, re.DOTALL)
        if matches:
            lang_hint, code = matches[0]
            return FENCE_LANG.get(lang_hint.lower(), "python"), code
        # Inline code detection
        indicators = ['def ', 'class ', 'function ', 'fun ', 'func ', 'import ', 'from ']
        lines = text.strip().split('\n')
        if any(any(ind in l for ind in indicators) for l in lines):
            return 'python', text.strip()
        return None, None

    @staticmethod
    def _extract_entities(text: str) -> Dict[str, Any]:
        """Extrae entidades nombradas (funciones, clases, archivos)."""
        entities: Dict[str, Any] = {}
        func_m = re.search(r'(?:function|func|def|fun)\s+(\w+)', text, re.IGNORECASE)
        if func_m:
            entities["function"] = func_m.group(1)
        class_m = re.search(r'(?:class)\s+(\w+)', text, re.IGNORECASE)
        if class_m:
            entities["class"] = class_m.group(1)
        file_m = re.search(r'([\w\.\-]+\.(?:py|kt|go|js|ts|java|rs|c|cpp|h|rb))', text)
        if file_m:
            entities["file"] = file_m.group(1)
        return entities

    @staticmethod
    def _infer_criticality(message: str) -> str:
        """Infiere criticidad del mensaje."""
        text_lower = message.lower()
        for kw in CRIT_KW["critical"]:
            if kw in text_lower:
                return "critical"
        for kw in CRIT_KW["moderate"]:
            if kw in text_lower:
                return "moderate"
        return "standard"

    @staticmethod
    def _infer_template(operation: str, target: str) -> str:
        """Infiere template type según operation + target."""
        t = target.lower()
        if any(x in t for x in ("api", "server", "endpoint")):
            return "api"
        if any(x in t for x in ("web", "page", "frontend")):
            return "web"
        if any(x in t for x in ("cli", "command")):
            return "cli"
        if any(x in t for x in ("data", "model", "schema")):
            return "data"
        if any(x in t for x in ("mobile", "app")):
            return "mobile"
        if operation in ("OPTIMIZE", "DEBUG"):
            return "automation"
        return "generic"

    # ============================================================
    #  PARSING HELPERS
    # ============================================================

    def _dict_to_output(self, data: Dict[str, Any], source: str = "llm") -> Optional[IntentOutput]:
        """Convierte dict JSON a IntentOutput validado."""
        operation = data.get("operation", "").upper()
        goal = data.get("goal", "").upper()
        if operation not in VALID_OPERATIONS:
            operation = "SEARCH"
        if goal not in VALID_GOALS:
            goal = "FEATURE_ADD"

        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        except (ValueError, TypeError):
            confidence = 0.5

        language = data.get("language", "python").lower()
        if language not in VALID_LANGUAGES:
            language = "python"

        criticality = str(data.get("criticality", "standard")).strip()
        if criticality not in ("standard", "moderate", "critical"):
            criticality = "standard"

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {"raw": str(entities)}

        return IntentOutput(
            operation=operation, goal=goal,
            target=str(data.get("target", "")).strip(),
            language=language,
            entities=entities,
            template_type=str(data.get("template_type", "generic")).strip(),
            criticality=criticality,
            confidence=confidence,
            source=source,
        )

    def _parse_freetext(self, text: str, source: str = "llm") -> Optional[IntentOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        text_upper = text.upper().strip()
        operation = "SEARCH"
        for op in VALID_OPERATIONS:
            if op in text_upper:
                operation = op
                break
        goal = "FEATURE_ADD"
        for g in VALID_GOALS:
            if g in text_upper:
                goal = g
                break
        return IntentOutput(
            operation=operation, goal=goal,
            confidence=0.35, source=source,
        )

    def _cache_result(self, message: str, output: IntentOutput) -> None:
        """Cachea resultado en SmartMemory si disponible."""
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
            logger.debug(f"SurgicalAgent: Cache save failed: {e}")
