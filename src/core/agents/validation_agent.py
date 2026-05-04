"""
TITAN OMNISCALE X - ValidationAgent

Agente IA que UNIFICA la validación de código y cadenas lógicas.
Reemplaza la lógica de validación dispersa en 2 módulos:

  1. ChainValidator (250 líneas, pre-execution validation)
  2. CodeTransformer bug detection (partial, within fix_python)

Arquitectura del ValidationAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → ValidationOutput
  - Rule path: Reglas deterministas de validación por tipo de target
  - Fallback path: Validación determinista por reglas estáticas (sin LLM)

Tipos de validación soportados:
  - code: Validación de código (seguridad, calidad, bugs)
  - chain: Validación de cadenas lógicas (compatibilidad, completitud)
  - config: Validación de configuración (schemas, valores)

Produce un ValidationOutput compatible con ChainValidator.ValidationResult.
"""

import re
import ast
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import ValidationInput, ValidationOutput, ValidationIssue
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Security vulnerability patterns
SECURITY_PATTERNS = [
    (r'\beval\s*\(', "dangerous_eval", "Use of eval() is a security risk", "error"),
    (r'\bexec\s*\(', "dangerous_exec", "Use of exec() is a security risk", "error"),
    (r'\bos\.system\s*\(', "command_injection", "os.system() allows command injection", "error"),
    (r'\bsubprocess\.call\s*\([^)]*shell\s*=\s*True', "shell_injection",
     "subprocess with shell=True allows injection", "error"),
    (r'\binput\s*\(', "unvalidated_input", "input() without validation", "warning"),
    (r'\bpickle\.loads?\s*\(', "pickle_deserialization", "Pickle deserialization is unsafe", "error"),
    (r'\byaml\.load\s*\([^)]*\)', "yaml_unsafe_load", "Use yaml.safe_load() instead", "warning"),
    (r'\bhashlib\.md5\b', "weak_hash_md5", "MD5 is cryptographically broken", "warning"),
    (r'\bhashlib\.sha1\b', "weak_hash_sha1", "SHA-1 is cryptographically weak", "warning"),
    (r'SELECT\s+\*\s+FROM', "select_star", "SELECT * may expose sensitive data", "info"),
    (r'\.format\s*\(', "format_injection", "str.format() can be exploited if user-controlled", "warning"),
    (r'%[sdfi]', "old_style_format", "Old-style string formatting (%s)", "info"),
]

# Code quality patterns
QUALITY_PATTERNS = [
    (r'except\s*:', "bare_except", "Bare except catches all exceptions including SystemExit",
     "warning"),
    (r'except\s+Exception\s*:', "broad_exception", "Catching Exception is very broad", "info"),
    (r'pass\s*$', "empty_block", "Empty block (pass) - add implementation or comment",
     "info"),
    (r'TODO|FIXME|HACK|XXX', "todo_comment", "Unresolved TODO/FIXME comment", "info"),
    (r'print\s*\(', "print_statement", "print() found - consider using logging", "info"),
]

# Chain validation rules
CHAIN_COMPATIBILITY_RULES = {
    ("data", "validation"): "good",
    ("validation", "data"): "good",
    ("data", "business_logic"): "good",
    ("validation", "business_logic"): "warning",
    ("business_logic", "validation"): "warning",
}


class ValidationAgent(BaseAgent[ValidationOutput]):
    """
    Agente de validación que unifica ChainValidator + code quality checks.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según tipo de target
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por reglas estáticas

    El agente unifica la lógica que antes estaba en:
    - ChainValidator.validate() (250 líneas)
    - CodeTransformer bug detection (partial)
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="validation")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para validación."""
        if isinstance(input_data, ValidationInput):
            target = input_data.target
            content = input_data.content
            rules = input_data.rules
            language = input_data.language
        else:
            target = "code"
            content = str(input_data)
            rules = []
            language = "python"

        system_prompt = AgentPrompts.VALIDATION_SYSTEM
        user_prompt = AgentPrompts.VALIDATION_USER.format(
            target=target,
            content=content[:800],
            rules=", ".join(rules) if rules else "standard",
            language=language,
        )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[ValidationOutput]:
        """Parsea la respuesta del LLM a un ValidationOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_validation_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_validation(cleaned, source="llm")

    def fallback(self, input_data: Any) -> ValidationOutput:
        """
        Fallback determinista: validación por reglas estáticas.

        Sin LLM, sin embeddings. Reglas deterministas de seguridad,
        calidad y compatibilidad.
        """
        start = time.time()

        if isinstance(input_data, ValidationInput):
            target = input_data.target
            content = input_data.content
            rules = input_data.rules
            language = input_data.language
        else:
            target = "code"
            content = str(input_data)
            rules = []
            language = "python"

        # Route to target-specific validation
        if target == "chain":
            output = self._validate_chain(content)
        elif target == "config":
            output = self._validate_config(content)
        else:
            output = self._validate_code(content, language, rules)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        output.source = "fallback"
        return output

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def validate_with_runner(self, runner: Any, target: str, content: str,
                              rules: Optional[List[str]] = None,
                              language: str = "python") -> ValidationOutput:
        """Valida usando AgentRunner (LLM → fallback)."""
        input_data = ValidationInput(
            target=target, content=content,
            rules=rules or [], language=language,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, ValidationOutput):
            return result.data
        return self.fallback(input_data)

    # ============================================================
    #  COMPATIBILITY: ChainValidator contract preserved
    # ============================================================

    def to_validation_result(self, output: ValidationOutput) -> Any:
        """
        Convierte ValidationOutput a ChainValidator.ValidationResult
        para compatibilidad con el pipeline existente.
        """
        from src.core.chain_validator import ValidationResult, ValidationError

        result = ValidationResult()
        for issue in output.issues:
            if issue.severity == "error":
                result.add_error(
                    code=issue.code,
                    message=issue.message,
                    block_name="",
                )
            else:
                result.add_warning(
                    code=issue.code,
                    message=issue.message,
                    block_name="",
                )

        return result

    # ============================================================
    #  CODE VALIDATION (deterministic)
    # ============================================================

    def _validate_code(self, code: str, language: str,
                       rules: List[str]) -> ValidationOutput:
        """Validación determinista de código."""
        if not code:
            return ValidationOutput(
                is_valid=True, issues=[],
                suggestions=["No code provided for validation"],
                risk_score=0.0,
            )

        issues = []

        # Security patterns (always checked)
        for pattern, code_id, message, severity in SECURITY_PATTERNS:
            matches = list(re.finditer(pattern, code, re.IGNORECASE))
            for match in matches:
                line_num = code[:match.start()].count('\n') + 1
                issues.append(ValidationIssue(
                    severity=severity,
                    code=code_id,
                    message=message,
                    line=line_num,
                    suggestion=self._get_fix_suggestion(code_id),
                ))

        # Quality patterns (if rules include "quality")
        if not rules or "quality" in rules or "all" in rules:
            for pattern, code_id, message, severity in QUALITY_PATTERNS:
                matches = list(re.finditer(pattern, code, re.IGNORECASE))
                for match in matches:
                    line_num = code[:match.start()].count('\n') + 1
                    issues.append(ValidationIssue(
                        severity=severity,
                        code=code_id,
                        message=message,
                        line=line_num,
                        suggestion=self._get_fix_suggestion(code_id),
                    ))

        # Python-specific AST analysis
        if language == "python":
            issues.extend(self._validate_python_ast(code))

        # Calculate risk score
        risk_score = self._calculate_risk_score(issues)

        # Generate suggestions
        suggestions = self._generate_suggestions(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=suggestions,
            risk_score=risk_score,
        )

    def _validate_python_ast(self, code: str) -> List[ValidationIssue]:
        """Validación de Python via AST analysis."""
        issues = []
        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Missing return in function that returns elsewhere
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    has_return = any(
                        isinstance(n, ast.Return) and n.value is not None
                        for n in ast.walk(node)
                    )
                    if has_return and node.body:
                        last_stmt = node.body[-1]
                        if not isinstance(last_stmt, (ast.Return, ast.Raise)):
                            issues.append(ValidationIssue(
                                severity="warning",
                                code="missing_return",
                                message=f"Function '{node.name}' may not return on all paths",
                                line=node.lineno,
                                suggestion="Add a return statement at the end of the function",
                            ))

                    # Resource leak: open() without with
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            func = getattr(child, 'func', None)
                            if isinstance(func, ast.Name) and func.id == 'open':
                                call_line = child.lineno
                                issues.append(ValidationIssue(
                                    severity="warning",
                                    code="resource_leak",
                                    message=f"Potential resource leak: open() without 'with' in '{node.name}'",
                                    line=call_line,
                                    suggestion="Use 'with open(...) as f:' to ensure file closure",
                                ))

                # Bare except
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="bare_except",
                        message="Bare 'except:' catches all exceptions including SystemExit",
                        line=node.lineno,
                        suggestion="Use 'except Exception:' instead",
                    ))

        except SyntaxError as e:
            issues.append(ValidationIssue(
                severity="error",
                code="syntax_error",
                message=f"Syntax error: {str(e)}",
                line=e.lineno or 0,
                suggestion="Fix the syntax error before proceeding",
            ))

        return issues

    # ============================================================
    #  CHAIN VALIDATION (deterministic)
    # ============================================================

    def _validate_chain(self, chain_data: Any) -> ValidationOutput:
        """Validación determinista de cadenas lógicas."""
        issues = []

        # Parse chain data
        if isinstance(chain_data, str):
            try:
                import json
                chain = json.loads(chain_data)
            except Exception:
                chain = {"blocks": []}
        elif isinstance(chain_data, dict):
            chain = chain_data
        else:
            # Handle LogicChain objects
            chain = {
                "blocks": getattr(chain_data, 'blocks', []),
            }
            if hasattr(chain_data, '_blocks'):
                raw_blocks = chain_data._blocks
                chain["blocks"] = raw_blocks

        blocks = chain.get("blocks", [])
        if not blocks:
            return ValidationOutput(
                is_valid=True,
                issues=[ValidationIssue(
                    severity="info", code="empty_chain",
                    message="Chain has no blocks to execute",
                    suggestion="Add blocks to the chain",
                )],
                suggestions=["Consider adding processing blocks"],
                risk_score=0.0,
            )

        # Validate each block
        for i, block in enumerate(blocks):
            block_dict = block if isinstance(block, dict) else {}
            block_name = block_dict.get("name", getattr(block, 'name', f'block_{i}'))
            block_type = block_dict.get("type", getattr(block, 'category', ''))

            if not block_name or block_name == f'block_{i}':
                issues.append(ValidationIssue(
                    severity="warning", code="missing_name",
                    message=f"Block at index {i} has no name",
                    line=i,
                    suggestion="Give each block a descriptive name",
                ))

        # Check block compatibility
        if len(blocks) > 1:
            for i in range(len(blocks) - 1):
                current = blocks[i]
                next_block = blocks[i + 1]
                current_cat = self._get_block_category(current)
                next_cat = self._get_block_category(next_block)

                rule = CHAIN_COMPATIBILITY_RULES.get((current_cat, next_cat))
                if rule == "warning":
                    issues.append(ValidationIssue(
                        severity="info",
                        code="compatibility_hint",
                        message=f"Block {i} ({current_cat}) → Block {i+1} ({next_cat}): consider reordering",
                        line=i,
                        suggestion=f"Consider placing validation before {current_cat} blocks",
                    ))

        # Check chain length
        if len(blocks) > 10:
            issues.append(ValidationIssue(
                severity="info", code="long_chain",
                message=f"Chain has {len(blocks)} blocks - consider splitting",
                suggestion="Split into sub-chains for maintainability",
            ))

        risk_score = self._calculate_risk_score(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=[f"Chain has {len(blocks)} blocks"] + [
                f"Fix: {i.message}" for i in issues if i.severity == "error"
            ],
            risk_score=risk_score,
        )

    # ============================================================
    #  CONFIG VALIDATION (deterministic)
    # ============================================================

    def _validate_config(self, config_data: Any) -> ValidationOutput:
        """Validación determinista de configuración."""
        issues = []

        if isinstance(config_data, str):
            try:
                import json
                config = json.loads(config_data)
            except Exception:
                # Try YAML
                try:
                    import yaml
                    config = yaml.safe_load(config_data) or {}
                except Exception:
                    issues.append(ValidationIssue(
                        severity="error", code="invalid_format",
                        message="Config is not valid JSON or YAML",
                        suggestion="Check syntax and format",
                    ))
                    return ValidationOutput(is_valid=False, issues=issues,
                                           risk_score=0.8)
        elif isinstance(config_data, dict):
            config = config_data
        else:
            config = {}

        # Check for common config issues
        if config.get("DEBUG") or config.get("debug"):
            issues.append(ValidationIssue(
                severity="info", code="debug_enabled",
                message="DEBUG mode is enabled - disable in production",
                suggestion="Set DEBUG=false for production",
            ))

        if config.get("SECRET_KEY") in ("change-this", "change-this-in-production", ""):
            issues.append(ValidationIssue(
                severity="error", code="weak_secret_key",
                message="Default SECRET_KEY detected - security risk",
                suggestion="Generate a strong secret key for production",
            ))

        risk_score = self._calculate_risk_score(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=[i.suggestion for i in issues if i.suggestion],
            risk_score=risk_score,
        )

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _get_block_category(self, block: Any) -> str:
        """Obtiene la categoría de un bloque."""
        if isinstance(block, dict):
            return block.get("category", block.get("type", "unknown"))
        return getattr(block, 'category', getattr(block, 'name', 'unknown'))

    def _calculate_risk_score(self, issues: List[ValidationIssue]) -> float:
        """Calcula risk score basado en issues encontrados."""
        if not issues:
            return 0.0

        weights = {"error": 0.3, "warning": 0.1, "info": 0.02}
        score = sum(weights.get(i.severity, 0.02) for i in issues)
        return min(1.0, score)

    def _generate_suggestions(self, issues: List[ValidationIssue]) -> List[str]:
        """Genera sugerencias de los issues encontrados."""
        suggestions = []
        error_types = set()
        for issue in issues:
            if issue.severity == "error" and issue.code not in error_types:
                error_types.add(issue.code)
                if issue.suggestion:
                    suggestions.append(issue.suggestion)

        if not suggestions:
            suggestions.append("No critical issues found")

        return suggestions[:5]

    def _get_fix_suggestion(self, code: str) -> str:
        """Sugerencia de fix para un tipo de issue."""
        fix_map = {
            "dangerous_eval": "Replace eval() with ast.literal_eval() or json.loads()",
            "dangerous_exec": "Avoid exec() - use functions instead",
            "command_injection": "Use subprocess.run() with shell=False",
            "shell_injection": "Use subprocess with shell=False and pass args as list",
            "pickle_deserialization": "Use json or msgpack instead of pickle",
            "yaml_unsafe_load": "Use yaml.safe_load() instead of yaml.load()",
            "weak_hash_md5": "Use hashlib.sha256() or stronger",
            "weak_hash_sha1": "Use hashlib.sha256() or stronger",
            "bare_except": "Use 'except Exception:' instead of bare 'except:'",
            "broad_exception": "Catch more specific exceptions",
            "select_star": "Specify columns explicitly instead of SELECT *",
            "format_injection": "Use f-strings or validate format arguments",
            "unvalidated_input": "Validate and sanitize all user input",
            "resource_leak": "Use 'with' statement for file/resource handling",
            "missing_return": "Add return statement on all code paths",
        }
        return fix_map.get(code, "Review and fix this issue")

    def _json_to_validation_output(self, data: Dict[str, Any],
                                    source: str = "llm") -> Optional[ValidationOutput]:
        """Convierte dict JSON a ValidationOutput."""
        is_valid = data.get("is_valid", True)
        if isinstance(is_valid, str):
            is_valid = is_valid.lower() == "true"

        # Parse issues
        issues = []
        for i_data in data.get("issues", []):
            if isinstance(i_data, dict):
                issues.append(ValidationIssue(
                    severity=str(i_data.get("severity", "warning")),
                    code=str(i_data.get("code", "")),
                    message=str(i_data.get("message", "")),
                    line=int(i_data.get("line", 0)),
                    suggestion=str(i_data.get("suggestion", "")),
                ))

        suggestions = data.get("suggestions", [])
        if isinstance(suggestions, str):
            suggestions = [suggestions]

        risk_score = data.get("risk_score", 0.0)
        try:
            risk_score = float(risk_score)
            risk_score = max(0.0, min(1.0, risk_score))
        except (ValueError, TypeError):
            risk_score = 0.0

        return ValidationOutput(
            is_valid=bool(is_valid),
            issues=issues,
            suggestions=suggestions if isinstance(suggestions, list) else [],
            risk_score=risk_score,
            source=source,
        )

    def _parse_free_text_validation(self, text: str,
                                     source: str = "llm") -> Optional[ValidationOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Try to extract issues from text
        issues = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith(('-', '*', '•')):
                issues.append(ValidationIssue(
                    severity="warning",
                    code="llm_detected",
                    message=line.lstrip('-*• '),
                    suggestion="Review this issue",
                ))

        is_valid = len(issues) == 0

        return ValidationOutput(
            is_valid=is_valid,
            issues=issues[:10],
            suggestions=["Review LLM findings"] if issues else ["No issues found"],
            risk_score=0.1 if issues else 0.0,
            source=source,
        )
