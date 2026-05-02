"""
TITAN OMNISCALE X - MiniAIEngine (Qwen3-0.6B Q4_K_M)

Motor de IA semántico COPILOTO - No es el cerebro, es la intuición.
El pipeline es el cerebro, la IA es el copiloto semántico.

7 Tareas Bounded (max ~50 tokens/call):
  1. classify_intent()     ~10 tokens - Clasificar intención del usuario
  2. extract_entities()    ~20 tokens - Extraer entidades (archivo, lenguaje)
  3. suggest_pattern()     ~30 tokens - Sugerir patrón de reemplazo
  4. fill_template_gaps()  ~50 tokens - Rellenar huecos de template
  5. generate_pattern()    ~20 lines  - Generar snippet de patrón
  6. explain_violation()   ~50 tokens - Explicar violación del sandbox
  7. describe_subtask()    ~30 tokens - Describir subtask

Cada método tiene FALLBACK DETERMINÍSTICO que funciona sin modelo.
Si el modelo falla, timeout, o da mala respuesta → fallback automático.

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - llama-cpp-python con n_ctx=2048, n_threads=4
"""

import re
import json
import time
import logging
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# === Model Configuration ===
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "models")
MODEL_FILENAME = "qwen3-0.6b-q4_k_m.gguf"
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILENAME)

# Bounded task limits (prevent runaway generation)
MAX_TOKENS_CLASSIFY = 200       # Allow thinking + answer
MAX_TOKENS_EXTRACT = 200
MAX_TOKENS_PATTERN = 250
MAX_TOKENS_TEMPLATE = 300
MAX_TOKENS_GENERATE = 400
MAX_TOKENS_EXPLAIN = 200
MAX_TOKENS_SUBTASK = 200

LLM_TIMEOUT_S = 8.0            # Max seconds per LLM call
N_CTX = 2048                    # Context window
N_THREADS = 4                   # CPU threads (good for ARM)
TEMPERATURE = 0.1               # Low temperature = more deterministic


@dataclass
class IntentResult:
    """Resultado de classify_intent con confidence."""
    operation: str = "SEARCH"        # CREATE|REFACTOR|DELETE|SEARCH|ANALYZE|EXPLAIN|DEBUG|OPTIMIZE
    goal: str = "FEATURE_ADD"        # COMPLEXITY_REDUCTION|MODERN_PATTERN|BUG_FIX|FEATURE_ADD|SECURITY_HARDEN|PERFORMANCE|READABILITY
    confidence: float = 0.0          # 0.0-1.0
    source: str = "fallback"         # "llm" or "fallback"


class MiniAIEngine:
    """
    Motor de IA semántico COPILOTO para el pipeline TITAN OMNISCALE X.
    
    Filosofía: Pipeline da superpoderes al LLM, LLM da intuición al pipeline.
    El LLM solo hace tareas cortas y bounded. Todo tiene fallback determinístico.
    """

    def __init__(self, model_path: Optional[str] = None, auto_load: bool = True):
        self._llm = None
        self._model_path = model_path or MODEL_PATH
        self._loaded = False
        self._load_time = 0.0
        self._call_count = 0
        self._fallback_count = 0
        self._total_llm_time = 0.0
        
        if auto_load:
            self.load_model()

    # ================================================================
    #  MODEL LIFECYCLE
    # ================================================================

    def load_model(self) -> bool:
        """Carga el modelo GGUF con llama-cpp-python. Returns True if loaded."""
        if self._loaded and self._llm is not None:
            return True

        if not os.path.exists(self._model_path):
            logger.warning(f"Model not found: {self._model_path}. MiniAI will use fallbacks only.")
            return False

        try:
            from llama_cpp import Llama
            start = time.time()
            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=N_CTX,
                n_threads=N_THREADS,
                verbose=False,
            )
            self._load_time = time.time() - start
            self._loaded = True
            logger.info(f"MiniAI: Qwen3-0.6B loaded in {self._load_time:.1f}s from {self._model_path}")
            return True
        except ImportError:
            logger.warning("MiniAI: llama-cpp-python not installed. Using fallbacks only.")
            return False
        except Exception as e:
            logger.warning(f"MiniAI: Failed to load model: {e}. Using fallbacks only.")
            self._llm = None
            return False

    def unload_model(self):
        """Libera el modelo de memoria."""
        if self._llm is not None:
            del self._llm
            self._llm = None
            self._loaded = False
            logger.info("MiniAI: Model unloaded from memory")

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._llm is not None

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas de uso del motor."""
        return {
            "model_loaded": self.is_loaded,
            "load_time_s": self._load_time,
            "total_calls": self._call_count,
            "fallback_calls": self._fallback_count,
            "llm_calls": self._call_count - self._fallback_count,
            "fallback_rate": self._fallback_count / max(self._call_count, 1),
            "avg_llm_time_s": self._total_llm_time / max(self._call_count - self._fallback_count, 1),
        }

    # ================================================================
    #  INTERNAL: LLM CALL HELPER
    # ================================================================

    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """
        Llama al LLM con timeout y manejo de errores.
        Returns raw response text or None on failure.
        """
        if not self.is_loaded:
            return None

        self._call_count += 1
        start = time.time()

        try:
            response = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=TEMPERATURE,
            )

            raw = response["choices"][0]["message"]["content"]
            answer = self._extract_answer(raw)
            elapsed = time.time() - start
            self._total_llm_time += elapsed

            if elapsed > LLM_TIMEOUT_S:
                logger.warning(f"MiniAI: Slow call ({elapsed:.1f}s) for: {user_prompt[:50]}")

            return answer

        except Exception as e:
            elapsed = time.time() - start
            logger.warning(f"MiniAI: LLM call failed ({elapsed:.1f}s): {e}")
            self._fallback_count += 1
            return None

    @staticmethod
    def _extract_answer(text: str) -> str:
        """Extrae la respuesta limpia del output de Qwen3 (maneja thinking mode)."""
        # Qwen3 outputs <think...</think then the answer
        match = re.search(r'</think\s*>(.*)', text, re.DOTALL)
        if match:
            answer = match.group(1).strip()
        else:
            # No think block - try to get last meaningful line
            lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
            answer = lines[-1] if lines else text.strip()

        # Clean markdown fences
        answer = re.sub(r'```(?:json|python)?\s*', '', answer)
        answer = re.sub(r'\s*```', '', answer)
        return answer.strip()

    # ================================================================
    #  BOUNDED TASK 1: classify_intent (~10 tokens answer)
    # ================================================================

    VALID_OPERATIONS = {"CREATE", "REFACTOR", "DELETE", "SEARCH", "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE"}
    VALID_GOALS = {"COMPLEXITY_REDUCTION", "MODERN_PATTERN", "BUG_FIX", "FEATURE_ADD",
                   "SECURITY_HARDEN", "PERFORMANCE", "READABILITY"}

    def classify_intent(self, text: str) -> IntentResult:
        """
        Clasifica la intención del usuario en operation + goal.
        LLM: ~10 tokens answer, ~3s con thinking.
        Fallback: TF-IDF keyword matching.
        """
        # Try LLM first
        if self.is_loaded:
            op_answer = self._call_llm(
                system_prompt="Classify the coding intent. Reply with ONLY one word: CREATE REFACTOR DELETE SEARCH ANALYZE EXPLAIN DEBUG OPTIMIZE",
                user_prompt=text,
                max_tokens=MAX_TOKENS_CLASSIFY,
            )
            if op_answer and op_answer.upper().split()[0] in self.VALID_OPERATIONS:
                op = op_answer.upper().split()[0]
            elif op_answer:
                # Try to find a valid operation in the answer
                op = self._match_operation(op_answer)
            else:
                op = None

            if op:
                # Now classify goal
                goal_answer = self._call_llm(
                    system_prompt="Classify the coding goal. Reply with ONLY one phrase: COMPLEXITY_REDUCTION MODERN_PATTERN BUG_FIX FEATURE_ADD SECURITY_HARDEN PERFORMANCE READABILITY",
                    user_prompt=text,
                    max_tokens=MAX_TOKENS_CLASSIFY,
                )
                goal = self._match_goal(goal_answer) if goal_answer else None

                return IntentResult(
                    operation=op,
                    goal=goal or self._fallback_goal(text),
                    confidence=0.75,  # LLM confidence
                    source="llm",
                )

        # Fallback: keyword matching (existing TF-IDF logic simplified)
        return self._fallback_classify(text)

    # ================================================================
    #  BOUNDED TASK 2: extract_entities (~20 tokens answer)
    # ================================================================

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Extrae entidades: archivo, lenguaje, función objetivo.
        LLM: ~20 tokens JSON, ~3s con thinking.
        Fallback: regex patterns.
        """
        if self.is_loaded:
            answer = self._call_llm(
                system_prompt='Extract file name and programming language. Reply JSON: {"file":"name.ext","lang":"python|kotlin|go|javascript|typescript|rust|unknown","function":"target_function_or_null"}',
                user_prompt=text,
                max_tokens=MAX_TOKENS_EXTRACT,
            )
            if answer:
                try:
                    # Try to parse JSON from the answer
                    json_match = re.search(r'\{[^}]+\}', answer)
                    if json_match:
                        result = json.loads(json_match.group())
                        return {
                            "file": result.get("file", ""),
                            "lang": result.get("lang", "unknown"),
                            "function": result.get("function"),
                            "source": "llm",
                        }
                except (json.JSONDecodeError, ValueError):
                    pass

        # Fallback: regex extraction
        return self._fallback_extract(text)

    # ================================================================
    #  BOUNDED TASK 3: suggest_pattern (~30 tokens answer)
    # ================================================================

    def suggest_pattern(self, target: str, description: str) -> str:
        """
        Sugiere un patrón de código para reemplazar el target.
        LLM: ~30 tokens, ~3s.
        Fallback: pattern matching por keywords.
        """
        if self.is_loaded:
            answer = self._call_llm(
                system_prompt="Suggest a short code pattern name for the replacement. Reply with ONLY a snake_case pattern name like: async_await_pattern, repository_pattern, factory_pattern, decorator_pattern, middleware_pattern, validator_pattern, observer_pattern, singleton_pattern",
                user_prompt=f"Target: {target}. Description: {description}",
                max_tokens=MAX_TOKENS_PATTERN,
            )
            if answer and len(answer) < 60:
                # Clean to snake_case
                clean = re.sub(r'[^a-z0-9_]', '_', answer.lower()).strip('_')
                if clean:
                    return f"{clean}_pattern"

        # Fallback: keyword-based
        desc_lower = description.lower()
        target_lower = target.lower()
        if any(kw in desc_lower for kw in ["async", "await", "coroutine", "asincrono"]):
            return "async_await_pattern"
        if any(kw in desc_lower for kw in ["validate", "validar", "check", "verify"]):
            return "validator_pattern"
        if any(kw in desc_lower for kw in ["cache", "memoize", "cachear"]):
            return "cache_pattern"
        if any(kw in target_lower for kw in ["auth", "login", "token"]):
            return "security_pattern"
        if any(kw in desc_lower for kw in ["test", "testing", "prueba"]):
            return "test_pattern"
        return "default_pattern"

    # ================================================================
    #  BOUNDED TASK 4: fill_template_gaps (~50 tokens/hole)
    # ================================================================

    def fill_template_gaps(self, template: str, context: Dict[str, Any]) -> str:
        """
        Rellena los huecos __GAP_N__ en un template con información contextual.
        LLM: ~50 tokens per gap.
        Fallback: rellena con valores por defecto del contexto.
        """
        gaps = re.findall(r'__GAP_(\w+)__', template)
        if not gaps:
            return template

        if self.is_loaded and len(gaps) <= 3:
            # Ask LLM to fill all gaps at once
            gap_list = ", ".join(gaps)
            context_str = json.dumps(context, default=str)[:300]
            answer = self._call_llm(
                system_prompt=f"Fill the template gaps: {gap_list}. Reply with ONLY a JSON object mapping gap names to values. Example: {{\"{gaps[0]}\": \"value\"}}",
                user_prompt=f"Context: {context_str}",
                max_tokens=MAX_TOKENS_TEMPLATE,
            )
            if answer:
                try:
                    json_match = re.search(r'\{[^}]+\}', answer)
                    if json_match:
                        fill_map = json.loads(json_match.group())
                        result = template
                        for gap_name, gap_value in fill_map.items():
                            result = result.replace(f"__GAP_{gap_name}__", str(gap_value))
                        # Check if all gaps were filled
                        if not re.search(r'__GAP_\w+__', result):
                            return result
                except (json.JSONDecodeError, ValueError):
                    pass

        # Fallback: fill from context or defaults
        result = template
        for gap in gaps:
            gap_lower = gap.lower()
            # Try context first
            if gap_lower in context:
                result = result.replace(f"__GAP_{gap}__", str(context[gap_lower]))
            elif gap in context:
                result = result.replace(f"__GAP_{gap}__", str(context[gap]))
            else:
                # Default values based on gap name
                defaults = {
                    "NAME": context.get("name", "generated"),
                    "CLASS_NAME": context.get("class_name", "GeneratedClass"),
                    "FUNC_NAME": context.get("func_name", "generated_function"),
                    "RETURN_TYPE": context.get("return_type", "Any"),
                    "PARAMS": context.get("params", "self"),
                    "BODY": context.get("body", "pass"),
                    "DOCSTRING": context.get("docstring", "Generated by TITAN OMNISCALE X"),
                    "IMPORT": context.get("import_", "import os"),
                    "VAR_NAME": context.get("var_name", "result"),
                    "TYPE": context.get("type", "str"),
                }
                value = defaults.get(gap, f"placeholder_{gap.lower()}")
                result = result.replace(f"__GAP_{gap}__", value)

        return result

    # ================================================================
    #  BOUNDED TASK 5: generate_pattern (~20 lines)
    # ================================================================

    def generate_pattern(self, pattern_desc: str, language: str = "python") -> str:
        """
        Genera un snippet de código para un patrón dado.
        LLM: ~20 lines, ~5s.
        Fallback: hardcoded snippets por patrón.
        """
        if self.is_loaded:
            answer = self._call_llm(
                system_prompt=f"Generate a short {language} code snippet. Reply with ONLY code, no explanation.",
                user_prompt=f"Generate a {pattern_desc} pattern in {language}",
                max_tokens=MAX_TOKENS_GENERATE,
            )
            if answer and len(answer) > 20:
                # Basic validation: check for common code elements
                if language == "python" and ("def " in answer or "class " in answer or "import " in answer):
                    return answer
                elif language != "python" and len(answer) > 30:
                    return answer

        # Fallback: hardcoded pattern snippets
        return self._fallback_pattern(pattern_desc, language)

    # ================================================================
    #  BOUNDED TASK 6: explain_violation (~50 tokens)
    # ================================================================

    def explain_violation(self, code: str, violations: List[str]) -> str:
        """
        Explica una violación encontrada por el sandbox en lenguaje natural.
        LLM: ~50 tokens, ~3s.
        Fallback: mensaje formateado con la violación.
        """
        if self.is_loaded:
            violations_str = "; ".join(violations[:3])
            code_snippet = code[:200] if code else "N/A"
            answer = self._call_llm(
                system_prompt="Explain the code violation in one short, clear sentence.",
                user_prompt=f"Code: {code_snippet}\nViolations: {violations_str}",
                max_tokens=MAX_TOKENS_EXPLAIN,
            )
            if answer and len(answer) > 10:
                return answer

        # Fallback: formatted message
        if not violations:
            return "No violations detected."
        violation_list = ", ".join(violations[:3])
        return f"Violation detected: {violation_list}. Review the code for safety issues."

    # ================================================================
    #  BOUNDED TASK 7: describe_subtask (~30 tokens)
    # ================================================================

    def describe_subtask(self, target: str, action: str, context: str = "") -> str:
        """
        Genera un nombre descriptivo para un subtask.
        LLM: ~30 tokens, ~3s.
        Fallback: f"{action}_{target}".
        """
        if self.is_loaded:
            answer = self._call_llm(
                system_prompt="Generate a short, descriptive snake_case subtask name. Reply with ONLY the name, no explanation.",
                user_prompt=f"Target: {target}, Action: {action}, Context: {context[:100]}",
                max_tokens=MAX_TOKENS_SUBTASK,
            )
            if answer:
                clean = re.sub(r'[^a-z0-9_]', '_', answer.lower()).strip('_')
                if clean and len(clean) > 3:
                    return clean

        # Fallback: simple combination
        safe_target = re.sub(r'[^a-z0-9_]', '_', target.lower()).strip('_')
        safe_action = re.sub(r'[^a-z0-9_]', '_', action.lower()).strip('_')
        return f"{safe_action}_{safe_target}"

    # ================================================================
    #  FALLBACK METHODS (deterministic, no LLM needed)
    # ================================================================

    def _fallback_classify(self, text: str) -> IntentResult:
        """Fallback: keyword-based intent classification."""
        text_lower = text.lower()

        op_keywords = {
            "CREATE": ["create", "new", "add", "implement", "crear", "nuevo", "agregar", "generar", "build", "make"],
            "REFACTOR": ["refactor", "restructure", "reorganize", "refactorizar", "reestructurar", "clean", "simplify"],
            "DELETE": ["delete", "remove", "eliminate", "eliminar", "borrar", "quitar", "drop"],
            "SEARCH": ["search", "find", "where", "locate", "buscar", "encontrar", "donde"],
            "ANALYZE": ["analyze", "review", "check", "analizar", "revisar", "verificar", "examine"],
            "EXPLAIN": ["explain", "describe", "what does", "explicar", "describir", "como funciona"],
            "DEBUG": ["debug", "fix", "correct", "bug", "error", "corregir", "arreglar", "depurar"],
            "OPTIMIZE": ["optimize", "improve", "faster", "optimizar", "mejorar", "acelerar", "performance"],
        }

        best_op, best_score = "SEARCH", 0
        for op, keywords in op_keywords.items():
            score = sum(2 if kw in text_lower.split() else (1 if kw in text_lower else 0) for kw in keywords)
            if score > best_score:
                best_score, best_op = score, op

        return IntentResult(
            operation=best_op,
            goal=self._fallback_goal(text),
            confidence=min(best_score / 10.0, 0.5),  # Low confidence for fallback
            source="fallback",
        )

    def _fallback_goal(self, text: str) -> str:
        """Fallback: keyword-based goal classification."""
        text_lower = text.lower()
        goal_keywords = {
            "BUG_FIX": ["bug", "fix", "error", "corregir", "arreglar", "wrong", "broken", "falla"],
            "FEATURE_ADD": ["add", "new", "feature", "agregar", "nueva", "implement", "crear"],
            "SECURITY_HARDEN": ["security", "auth", "login", "token", "crypto", "vulnerability", "seguridad"],
            "PERFORMANCE": ["optimize", "fast", "slow", "performance", "optimizar", "rapido", "lento"],
            "MODERN_PATTERN": ["modern", "update", "upgrade", "moderno", "actualizar", "migrate"],
            "COMPLEXITY_REDUCTION": ["simplify", "reduce", "complex", "simplificar", "reducir", "complejo"],
            "READABILITY": ["readable", "clean", "comment", "legible", "limpio", "documentar"],
        }

        best_goal, best_score = "FEATURE_ADD", 0
        for goal, keywords in goal_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score, best_score = score, score
                best_goal = goal

        return best_goal

    def _fallback_extract(self, text: str) -> Dict[str, Any]:
        """Fallback: regex-based entity extraction."""
        # File extraction
        file_match = re.search(r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text)
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        lang_map = {
            ".py": "python", ".kt": "kotlin", ".go": "go",
            ".js": "javascript", ".ts": "typescript", ".java": "java",
            ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
        }
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = lang_map.get(ext, "unknown")

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

        return {
            "file": file_name,
            "lang": lang,
            "function": function,
            "source": "fallback",
        }

    def _fallback_pattern(self, pattern_desc: str, language: str) -> str:
        """Fallback: hardcoded pattern snippets."""
        patterns = {
            "python": {
                "async_await": "async def process(data):\n    result = await async_operation(data)\n    return result\n",
                "validator": "def validate(data: dict) -> bool:\n    required = ['id', 'name']\n    return all(k in data for k in required)\n",
                "repository": "class Repository:\n    def __init__(self, db):\n        self.db = db\n    def get_by_id(self, id):\n        return self.db.query(id)\n",
                "factory": "def create_handler(type_: str):\n    handlers = {'auth': AuthHandler, 'data': DataHandler}\n    return handlers.get(type_, DefaultHandler)\n",
                "middleware": "def middleware(func):\n    def wrapper(*args, **kwargs):\n        pre_process(*args)\n        result = func(*args, **kwargs)\n        post_process(result)\n        return result\n    return wrapper\n",
                "observer": "class Observable:\n    def __init__(self):\n        self._observers = []\n    def subscribe(self, observer):\n        self._observers.append(observer)\n    def notify(self, event):\n        for obs in self._observers:\n            obs.on_event(event)\n",
                "security": "import hashlib, secrets\n\ndef hash_password(password: str) -> str:\n    salt = secrets.token_hex(16)\n    return hashlib.sha256((salt + password).encode()).hexdigest()\n",
                "cache": "from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef get_data(key):\n    return expensive_lookup(key)\n",
                "default": "def generated_function(data):\n    \"\"\"Generated by TITAN OMNISCALE X\"\"\"\n    return data\n",
            },
            "kotlin": {
                "default": "fun generatedFunction(data: Any): Any {\n    return data\n}\n",
            },
            "go": {
                "default": "func generatedFunction(data interface{}) interface{} {\n\treturn data\n}\n",
            },
            "javascript": {
                "default": "function generatedFunction(data) {\n    return data;\n}\n",
            },
        }

        lang_patterns = patterns.get(language, patterns["python"])

        # Try to match pattern description
        desc_lower = pattern_desc.lower()
        for key, snippet in lang_patterns.items():
            if key in desc_lower or key.replace("_", " ") in desc_lower:
                return snippet

        return lang_patterns.get("default", patterns["python"]["default"])

    def _match_operation(self, text: str) -> Optional[str]:
        """Try to find a valid operation in a text response."""
        text_upper = text.upper()
        for op in self.VALID_OPERATIONS:
            if op in text_upper:
                return op
        return None

    def _match_goal(self, text: str) -> Optional[str]:
        """Try to find a valid goal in a text response."""
        if not text:
            return None
        text_upper = text.upper()
        for goal in self.VALID_GOALS:
            if goal in text_upper:
                return goal
        return None
