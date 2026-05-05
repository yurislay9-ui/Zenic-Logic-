"""
MiniAIEngine bounded task methods (tasks 1-7).
"""

import re
import json
import logging
from typing import Optional, Dict, Any, List

from ._imports import (
    IntentResult,
    MAX_TOKENS_CLASSIFY, MAX_TOKENS_EXTRACT, MAX_TOKENS_PATTERN,
    MAX_TOKENS_TEMPLATE, MAX_TOKENS_GENERATE, MAX_TOKENS_EXPLAIN,
    MAX_TOKENS_SUBTASK,
)


class BoundedTasksMixin:
    """7 Bounded Task methods for MiniAIEngine."""

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
