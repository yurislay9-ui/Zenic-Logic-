"""
A40 DeterministicPipeline — SINGLE RESPONSIBILITY: Execute all 7 deterministic tasks without AI.

Deterministic pipeline that replaces ALL MiniAIEngine tasks.
No AI. No LLM calls. Pure algorithmic processing.

7 Deterministic Tasks:
  1. classify_intent()    → Keyword scoring
  2. extract_entities()   → Regex extraction + extension mapping
  3. suggest_pattern()    → Heuristic lookup table
  4. fill_template_gaps() → Context mapping + defaults
  5. generate_pattern()   → Template library composition
  6. explain_violation()  → Violation catalog lookup
  7. describe_subtask()   → Name auto-composition

Ported from:
  - verdict_parts/deterministic_pipeline.py (standalone class)
  - mini_ai_parts/_tasks.py (BoundedTasksMixin)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from ..resilience import BaseAgent
from ..schemas import PipelineResult, IntentResult, EntityResult

# ──────────────────────────────────────────────────────────────
# EXTENSION → LANGUAGE MAPPING
# ──────────────────────────────────────────────────────────────

EXT_LANG_MAP: Dict[str, str] = {
    ".py": "python", ".kt": "kotlin", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
    ".h": "c", ".hpp": "cpp", ".swift": "swift", ".scala": "scala",
}

# ──────────────────────────────────────────────────────────────
# OPERATION KEYWORDS (Task 1: classify_intent)
# ──────────────────────────────────────────────────────────────

OP_KEYWORDS: Dict[str, List[str]] = {
    "CREATE": [
        "create", "build", "make", "generate", "add", "implement",
        "desarrollar", "crear", "construir", "generar", "agregar", "implementar",
    ],
    "REFACTOR": [
        "refactor", "restructure", "reorganize", "clean", "simplify",
        "refactorizar", "reestructurar", "reorganizar", "limpiar", "simplificar",
    ],
    "DELETE": [
        "delete", "remove", "drop", "clear", "purge",
        "eliminar", "borrar", "quitar", "limpiar",
    ],
    "SEARCH": [
        "search", "find", "locate", "query", "look for",
        "buscar", "encontrar", "localizar", "consultar",
    ],
    "ANALYZE": [
        "analyze", "review", "audit", "inspect", "evaluate",
        "analizar", "revisar", "auditar", "inspeccionar", "evaluar",
    ],
    "EXPLAIN": [
        "explain", "describe", "document", "clarify", "understand",
        "explicar", "describir", "documentar", "aclarar", "entender",
    ],
    "DEBUG": [
        "debug", "fix", "repair", "troubleshoot", "diagnose",
        "depurar", "arreglar", "reparar", "solucionar", "diagnosticar",
    ],
    "OPTIMIZE": [
        "optimize", "improve", "enhance", "speed up", "accelerate",
        "optimizar", "mejorar", "acelerar", "rendimiento",
    ],
}

GOAL_KEYWORDS: Dict[str, List[str]] = {
    "FEATURE_ADD": [
        "feature", "functionality", "capability", "new", "extend",
        "característica", "funcionalidad", "capacidad", "nuevo", "extender",
    ],
    "BUG_FIX": [
        "bug", "error", "issue", "problem", "crash", "fail",
        "error", "problema", "fallo", "cuelgue", "falla",
    ],
    "SECURITY_HARDEN": [
        "security", "vulnerability", "auth", "protect", "sanitize",
        "seguridad", "vulnerabilidad", "proteger", "sanitizar",
    ],
    "PERFORMANCE": [
        "performance", "speed", "latency", "throughput", "efficiency",
        "rendimiento", "velocidad", "latencia", "eficiencia",
    ],
    "COMPLEXITY_REDUCTION": [
        "simplify", "reduce", "streamline", "clean", "refactor",
        "simplificar", "reducir", "limpiar",
    ],
    "MODERN_PATTERN": [
        "modernize", "update", "upgrade", "migrate", "latest",
        "modernizar", "actualizar", "migrar",
    ],
    "READABILITY": [
        "readable", "clear", "document", "comment", "naming",
        "legible", "claro", "documentar", "comentar",
    ],
}

# ──────────────────────────────────────────────────────────────
# PATTERN HEURISTICS (Task 3: suggest_pattern)
# ──────────────────────────────────────────────────────────────

PATTERN_HEURISTICS: List[tuple] = [
    (["async", "await", "coroutine", "asincrono"], "async_await"),
    (["validate", "validar", "check", "verify", "verificar"], "validator"),
    (["repository", "repo", "database", "db", "base de datos"], "repository"),
    (["factory", "create", "creator", "fabrica"], "factory"),
    (["middleware", "interceptor", "pipeline"], "middleware"),
    (["observer", "subscribe", "event", "listen", "escuchar"], "observer"),
    (["security", "auth", "login", "token", "seguridad"], "security"),
    (["cache", "memoize", "store", "cachear"], "cache"),
    (["singleton", "single", "unique", "unico"], "singleton"),
]

# ──────────────────────────────────────────────────────────────
# PATTERN LIBRARY (Task 5: generate_pattern)
# ──────────────────────────────────────────────────────────────

PATTERN_LIBRARY: Dict[str, Dict[str, str]] = {
    "python": {
        "async_await": "async def {name}({params}):\n    result = await {operation}({params})\n    return result\n",
        "validator": "def {name}(data: dict) -> bool:\n    required = {required_fields}\n    return all(k in data for k in required)\n",
        "repository": "class {class_name}:\n    def __init__(self, db):\n        self.db = db\n    def get_by_id(self, id: str):\n        return self.db.query(id)\n",
        "factory": "def create_{name}(type_: str):\n    handlers = {handler_map}\n    return handlers.get(type_, DefaultHandler)\n",
        "middleware": "def {name}(func):\n    def wrapper(*args, **kwargs):\n        pre_process(*args)\n        result = func(*args, **kwargs)\n        post_process(result)\n        return result\n    return wrapper\n",
        "observer": "class {class_name}:\n    def __init__(self):\n        self._observers = []\n    def subscribe(self, observer):\n        self._observers.append(observer)\n    def notify(self, event):\n        for obs in self._observers:\n            obs.on_event(event)\n",
        "security": "import hashlib, secrets\n\ndef hash_password(password: str) -> str:\n    salt = secrets.token_hex(16)\n    return hashlib.sha256((salt + password).encode()).hexdigest()\n",
        "cache": "from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef {name}(key):\n    return expensive_lookup(key)\n",
        "singleton": "class {class_name}:\n    _instance = None\n    def __new__(cls):\n        if cls._instance is None:\n            cls._instance = super().__new__(cls)\n        return cls._instance\n",
        "default": "def {name}(data):\n    \"\"\"Generated by ZENIC LOGIC v18\"\"\"\n    return data\n",
    },
    "javascript": {
        "async_await": "async function {name}({params}) {\n    const result = await {operation}({params});\n    return result;\n}\n",
        "validator": "function {name}(data) {\n    const required = {required_fields};\n    return required.every(k => k in data);\n}\n",
        "default": "function {name}(data) {\n    return data;\n}\n",
    },
    "typescript": {
        "default": "function {name}(data: any): any {\n    return data;\n}\n",
    },
}

# ──────────────────────────────────────────────────────────────
# VIOLATION CATALOG (Task 6: explain_violation)
# ──────────────────────────────────────────────────────────────

VIOLATION_CATALOG: Dict[str, str] = {
    "exec_call": "Use of exec() allows arbitrary code execution, which is a critical security risk.",
    "eval_call": "Use of eval() allows arbitrary code execution, which is a critical security risk.",
    "import_call": "Dynamic import via __import__() can load untrusted modules at runtime.",
    "os_system": "os.system() executes shell commands, vulnerable to injection attacks.",
    "subprocess_call": "subprocess calls can execute arbitrary system commands.",
    "pickle_load": "pickle.loads() can deserialize malicious objects leading to RCE.",
    "yaml_unsafe": "yaml.load() without SafeLoader can execute arbitrary Python code.",
    "sensitive_file": "Access to sensitive system files (/etc, /proc, /sys) detected.",
    "rm_rf": "Dangerous rm -rf command detected, can destroy entire filesystems.",
    "socket_raw": "Raw socket creation detected, may indicate network-level exploits.",
    "null_pointer": "Potential null/None dereference detected.",
    "type_mismatch": "Type mismatch detected in function call.",
    "unreachable": "Unreachable code detected after return statement.",
    "unused_import": "Unused import detected.",
}

# Gap defaults for template filling (Task 4)
GAP_DEFAULTS: Dict[str, str] = {
    "NAME": "generated",
    "CLASS_NAME": "GeneratedClass",
    "FUNC_NAME": "generated_function",
    "RETURN_TYPE": "Any",
    "PARAMS": "self",
    "BODY": "pass",
    "DOCSTRING": "Generated by ZENIC LOGIC v18",
    "IMPORT": "import os",
    "VAR_NAME": "result",
    "TYPE": "str",
    "OPERATION": "process",
    "REQUIRED_FIELDS": "['id', 'name']",
    "HANDLER_MAP": "{}",
}


class DeterministicPipeline(BaseAgent[PipelineResult]):
    """
    A40: Execute all 7 deterministic tasks without AI.

    Single Responsibility: Deterministic task pipeline ONLY.
    Method: Pure algorithmic processing (no LLM, no AI).
    Fallback: Return empty results with low confidence.
    """

    def __init__(self, **kwargs):
        super().__init__(name="A40_DeterministicPipeline", **kwargs)

    def execute(self, input_data: Any) -> PipelineResult:
        """
        Execute all 7 deterministic tasks.

        input_data can be:
          - dict with 'text', 'code' (optional), 'language' (optional), 'context' (optional)
          - str (raw text, treated as query)
        """
        text, code, language, context = self._parse_input(input_data)

        # Task 1: Classify intent
        classify = self._classify_intent(text)

        # Task 2: Extract entities
        extract = self._extract_entities(text)

        # Task 3: Suggest pattern
        target = extract.get("file", "") if isinstance(extract, dict) else "target"
        pattern = self._suggest_pattern(target, text)

        # Task 4: Fill template gaps (only if template provided)
        template = context.get("template", "") if isinstance(context, dict) else ""
        fill = self._fill_template_gaps(template, context) if template else {
            "result": "", "confidence": 1.0, "source": "deterministic",
        }

        # Task 5: Generate pattern (only if code context provided)
        if code:
            generate = self._generate_pattern(
                pattern.get("result", "default") if isinstance(pattern, dict) else "default",
                language, context,
            )
        else:
            generate = {
                "result": "", "confidence": 1.0, "source": "deterministic",
            }

        # Task 6: Explain violation (only if violations provided)
        violations = context.get("violations", []) if isinstance(context, dict) else []
        explain = self._explain_violation(code, violations)

        # Task 7: Describe subtask
        action = classify.get("operation", "process") if isinstance(classify, dict) else "process"
        subtask = self._describe_subtask(target or "target", action)

        return PipelineResult(
            classify=classify,
            extract=extract,
            pattern=pattern,
            fill=fill,
            generate=generate,
            explain=explain,
            subtask=subtask,
            source="deterministic",
        )

    def _parse_input(self, input_data: Any) -> tuple:
        """Parse input into (text, code, language, context)."""
        if isinstance(input_data, str):
            return input_data, "", "python", {}
        elif isinstance(input_data, dict):
            text = input_data.get("text", input_data.get("query", ""))
            code = input_data.get("code", "")
            language = input_data.get("language", "python")
            context = input_data.get("context", {})
            return text, code, language, context
        return "", "", "python", {}

    # ──────────────────────────────────────────────────────────
    #  TASK 1: classify_intent
    # ──────────────────────────────────────────────────────────

    def _classify_intent(self, text: str) -> Dict[str, Any]:
        """Classify user intent using keyword scoring (EN + ES)."""
        if not text:
            return {"operation": "SEARCH", "goal": "FEATURE_ADD", "confidence": 0.0, "source": "deterministic"}

        text_lower = text.lower()

        # Score operations
        best_op = "SEARCH"
        best_op_score = 0
        for op, keywords in OP_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_op_score:
                best_op_score = score
                best_op = op

        # Score goals
        best_goal = "FEATURE_ADD"
        best_goal_score = 0
        for goal, keywords in GOAL_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_goal_score:
                best_goal_score = score
                best_goal = goal

        # Confidence based on match strength
        total_keywords = len(text_lower.split())
        confidence = min(0.9, (best_op_score + best_goal_score) / max(total_keywords, 1) * 3)
        confidence = max(0.3, confidence)

        return {
            "operation": best_op,
            "goal": best_goal,
            "confidence": round(confidence, 2),
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 2: extract_entities
    # ──────────────────────────────────────────────────────────

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract entities (file, language, function) using regex."""
        if not text:
            return {"file": "", "lang": "unknown", "function": None, "confidence": 0.0, "source": "deterministic"}

        # File extraction
        file_match = re.search(
            r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text
        )
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = EXT_LANG_MAP.get(ext, "unknown")

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

        # Language from keywords (fallback)
        if lang == "unknown":
            text_lower = text.lower()
            if "python" in text_lower or "def " in text:
                lang = "python"
            elif "javascript" in text_lower or "function " in text or "const " in text:
                lang = "javascript"
            elif "typescript" in text_lower or ": string" in text or ": number" in text:
                lang = "typescript"
            elif "kotlin" in text_lower or "fun " in text:
                lang = "kotlin"
            elif "golang" in text_lower or "go " in text_lower or "func " in text:
                lang = "go"

        confidence = 0.9 if file_name else (0.6 if lang != "unknown" else 0.2)

        return {
            "file": file_name,
            "lang": lang,
            "function": function,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 3: suggest_pattern
    # ──────────────────────────────────────────────────────────

    def _suggest_pattern(self, target: str, description: str) -> Dict[str, Any]:
        """Suggest a code pattern using heuristics."""
        desc_lower = description.lower()
        target_lower = target.lower()
        combined = f"{desc_lower} {target_lower}"

        for keywords, pattern_name in PATTERN_HEURISTICS:
            if any(kw in combined for kw in keywords):
                return {
                    "result": f"{pattern_name}_pattern",
                    "confidence": 0.8,
                    "source": "deterministic",
                }

        return {
            "result": "default_pattern",
            "confidence": 0.3,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 4: fill_template_gaps
    # ──────────────────────────────────────────────────────────

    def _fill_template_gaps(
        self, template: str, context: Any
    ) -> Dict[str, Any]:
        """Fill template gaps with context and defaults."""
        if not template:
            return {"result": "", "confidence": 1.0, "source": "deterministic"}

        gaps = re.findall(r'__GAP_(\w+)__', template)
        if not gaps:
            return {"result": template, "confidence": 1.0, "source": "deterministic"}

        ctx = context if isinstance(context, dict) else {}
        result = template
        for gap in gaps:
            gap_lower = gap.lower()
            # Try context first (case-insensitive)
            value = None
            if gap_lower in ctx:
                value = ctx[gap_lower]
            elif gap in ctx:
                value = ctx[gap]
            elif gap in GAP_DEFAULTS:
                value = GAP_DEFAULTS[gap]
            else:
                value = f"placeholder_{gap_lower}"

            result = result.replace(f"__GAP_{gap}__", str(value))

        all_filled = not re.search(r'__GAP_\w+__', result)
        confidence = 1.0 if all_filled else 0.5

        return {
            "result": result,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 5: generate_pattern
    # ──────────────────────────────────────────────────────────

    def _generate_pattern(
        self, pattern_desc: str, language: str = "python",
        context: Any = None,
    ) -> Dict[str, Any]:
        """Generate code snippet from template library."""
        ctx = context if isinstance(context, dict) else {}
        lang_patterns = PATTERN_LIBRARY.get(language, PATTERN_LIBRARY["python"])

        # Find pattern by description
        desc_lower = pattern_desc.lower()
        pattern_name = "default"

        for keywords, name in PATTERN_HEURISTICS:
            if any(kw in desc_lower for kw in keywords):
                pattern_name = name
                break

        # Get template
        template = lang_patterns.get(pattern_name, lang_patterns.get("default", ""))

        # Fill placeholders
        try:
            result = template.format(
                name=ctx.get("name", ctx.get("func_name", "generated")),
                class_name=ctx.get("class_name", "GeneratedClass"),
                params=ctx.get("params", "data"),
                operation=ctx.get("operation", "process"),
                required_fields=str(ctx.get("required_fields", "['id', 'name']")),
                handler_map=str(ctx.get("handler_map", "{}")),
            )
        except (KeyError, IndexError):
            result = template

        confidence = 0.9 if pattern_name != "default" else 0.5

        return {
            "result": result,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 6: explain_violation
    # ──────────────────────────────────────────────────────────

    def _explain_violation(
        self, code: str, violations: List[str]
    ) -> Dict[str, Any]:
        """Explain violations using catalog."""
        if not violations:
            return {
                "result": "No violations detected." if not code else "No violations detected.",
                "confidence": 1.0,
                "source": "deterministic",
            }

        explanations = []
        for v in violations[:5]:
            v_lower = v.lower()
            explanation = None
            for key, msg in VIOLATION_CATALOG.items():
                if key in v_lower or any(kw in v_lower for kw in key.split("_")):
                    explanation = msg
                    break
            if not explanation:
                explanation = f"Code violation detected: {v}"
            explanations.append(explanation)

        return {
            "result": "; ".join(explanations),
            "confidence": 0.95,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 7: describe_subtask
    # ──────────────────────────────────────────────────────────

    def _describe_subtask(
        self, target: str, action: str, context: str = ""
    ) -> Dict[str, Any]:
        """Generate a descriptive name for a subtask."""
        safe_target = re.sub(r'[^a-z0-9_]', '_', target.lower()).strip('_')
        safe_action = re.sub(r'[^a-z0-9_]', '_', action.lower()).strip('_')

        name = re.sub(r'_+', '_', f"{safe_action}_{safe_target}").strip('_')

        if not name or len(name) < 3:
            name = "unnamed_subtask"

        return {
            "result": name,
            "confidence": 0.9,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  INDIVIDUAL TASK ACCESS (for partial execution)
    # ──────────────────────────────────────────────────────────

    def classify_intent(self, text: str) -> Dict[str, Any]:
        """Public API: Task 1 — classify intent."""
        return self._classify_intent(text)

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Public API: Task 2 — extract entities."""
        return self._extract_entities(text)

    def suggest_pattern(self, target: str, description: str) -> Dict[str, Any]:
        """Public API: Task 3 — suggest pattern."""
        return self._suggest_pattern(target, description)

    def fill_template_gaps(self, template: str, context: Any = None) -> Dict[str, Any]:
        """Public API: Task 4 — fill template gaps."""
        return self._fill_template_gaps(template, context or {})

    def generate_pattern(self, pattern_desc: str, language: str = "python",
                         context: Any = None) -> Dict[str, Any]:
        """Public API: Task 5 — generate pattern."""
        return self._generate_pattern(pattern_desc, language, context)

    def explain_violation(self, code: str, violations: List[str] = None) -> Dict[str, Any]:
        """Public API: Task 6 — explain violation."""
        return self._explain_violation(code, violations or [])

    def describe_subtask(self, target: str, action: str) -> Dict[str, Any]:
        """Public API: Task 7 — describe subtask."""
        return self._describe_subtask(target, action)

    def fallback(self, input_data: Any) -> PipelineResult:
        """Fallback: Return empty pipeline result."""
        return PipelineResult(source="fallback")
