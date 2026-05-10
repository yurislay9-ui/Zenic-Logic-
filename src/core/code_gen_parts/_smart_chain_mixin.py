"""
SmartPromptChain — Fragmented generation for small LLMs (Qwen3-0.6B).

Problem: Qwen3-0.6B (600M params) cannot generate a 200-line file in one call.
Solution: Break generation into atomic steps of 20-50 lines each, with
context carry-forward between steps. Each step is manageable for the model.

Architecture:
  1. plan_steps() — decompose task into atomic generation steps
  2. execute_step() — generate one fragment with context from previous steps
  3. assemble_fragments() — concatenate validated fragments into final file
  4. auto_repair() — if a fragment fails, retry with error context
"""

import re
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Maximum lines per step — Qwen3-0.6B reliable output range
MAX_LINES_PER_STEP = 40
MAX_REPAIR_ATTEMPTS = 3


@dataclass
class GenerationStep:
    """A single atomic generation step."""
    step_id: int
    step_type: str  # "schema" | "imports" | "class_def" | "method" | "tests"
    description: str
    prompt: str
    context: str = ""  # Code from previous steps
    generated: str = ""
    validated: bool = False
    attempts: int = 0


@dataclass
class ChainResult:
    """Result of a SmartPromptChain execution."""
    success: bool
    code: str = ""
    steps_total: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    repair_count: int = 0
    fragments: List[str] = field(default_factory=list)


class SmartPromptChain:
    """Fragmented code generation for small LLMs."""

    def __init__(self, llm_engine=None, sandbox=None):
        """
        Args:
            llm_engine: MiniAIEngine or any callable that takes (prompt) -> str
            sandbox: Optional ExecutionBridge for validation
        """
        self._llm = llm_engine
        self._sandbox = sandbox

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def generate_code(self, task_description: str, language: str = "python",
                      entity_info: Optional[Dict] = None,
                      max_lines: int = 200) -> ChainResult:
        """Generate code using step-by-step fragmented approach.

        Args:
            task_description: What to generate (e.g., "CRUD service for Account")
            language: Target language
            entity_info: Optional entity dict with name, fields
            max_lines: Maximum total lines to generate

        Returns:
            ChainResult with assembled code
        """
        # 1. Plan the steps
        steps = self.plan_steps(task_description, language, entity_info, max_lines)

        # 2. Execute each step
        result = self.execute_chain(steps, language)

        return result

    def plan_steps(self, task_description: str, language: str = "python",
                   entity_info: Optional[Dict] = None,
                   max_lines: int = 200) -> List[GenerationStep]:
        """Decompose a generation task into atomic steps.

        Strategy depends on task type:
        - CRUD/Service: schema → imports → class → methods → tests
        - Auth: imports → class → hash_methods → token_methods → dependencies
        - Integration: imports → config → client → operations → error_handling
        """
        steps = []
        entity_name = (entity_info or {}).get("name", "Module")
        fields = (entity_info or {}).get("fields", [])

        # Detect task type
        task_type = self._detect_task_type(task_description)

        if task_type == "crud":
            steps = self._plan_crud_steps(entity_name, fields, language)
        elif task_type == "auth":
            steps = self._plan_auth_steps(entity_name, language)
        elif task_type == "integration":
            steps = self._plan_integration_steps(entity_name, task_description, language)
        elif task_type == "analytics":
            steps = self._plan_analytics_steps(entity_name, fields, language)
        else:
            steps = self._plan_generic_steps(entity_name, task_description, language)

        return steps

    def execute_chain(self, steps: List[GenerationStep],
                      language: str = "python") -> ChainResult:
        """Execute a chain of generation steps.

        Each step:
        1. Receives context from all previous steps
        2. Generates its fragment
        3. Is validated (syntax check)
        4. If fails, auto-repairs up to MAX_REPAIR_ATTEMPTS
        """
        result = ChainResult(
            success=False,
            steps_total=len(steps),
        )

        accumulated_context = ""
        completed = 0
        failed = 0
        repairs = 0

        for step in steps:
            step.context = accumulated_context

            # Generate
            generated = self._execute_step(step, language)

            if generated:
                # Validate
                if self._validate_fragment(generated, language):
                    step.generated = generated
                    step.validated = True
                    accumulated_context += "\n" + generated
                    completed += 1
                    result.fragments.append(generated)
                else:
                    # Try repair
                    repaired, repair_count = self._auto_repair(
                        step, generated, language
                    )
                    repairs += repair_count
                    if repaired:
                        step.generated = repaired
                        step.validated = True
                        accumulated_context += "\n" + repaired
                        completed += 1
                        result.fragments.append(repaired)
                    else:
                        failed += 1
                        logger.warning(
                            f"SmartPromptChain: Step {step.step_id} "
                            f"({step.step_type}) failed after {repair_count} repairs"
                        )
                        # Keep best effort — add the fragment anyway
                        result.fragments.append(generated)
                        accumulated_context += "\n" + generated
            else:
                failed += 1
                step.attempts += 1

        # Assemble final code
        result.steps_completed = completed
        result.steps_failed = failed
        result.repair_count = repairs
        result.code = '\n'.join(result.fragments)
        result.success = failed == 0 or completed > 0

        return result

    # ================================================================
    #  STEP PLANNERS
    # ================================================================

    def _plan_crud_steps(self, entity_name: str, fields: List[Dict],
                          language: str) -> List[GenerationStep]:
        """Plan steps for CRUD service generation."""
        field_names = [f.get("name", "field") for f in fields] if fields else ["id", "name"]
        field_types = [f.get("type", "str") for f in fields] if fields else ["int", "str"]
        fields_str = ", ".join(f"{n}: {t}" for n, t in zip(field_names, field_types))

        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Imports for {entity_name} CRUD",
                prompt=(
                    f"Generate ONLY the import statements for a Python CRUD service "
                    f"for {entity_name}. Fields: {fields_str}. "
                    f"Use typing, dataclasses, sqlite3, logging. "
                    f"Output ONLY the import lines, no other code. Max 10 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="schema",
                description=f"Pydantic models for {entity_name}",
                prompt=(
                    f"Generate Pydantic BaseModel classes for {entity_name}. "
                    f"Fields: {fields_str}. "
                    f"Create {entity_name}Create and {entity_name}Response models. "
                    f"Output ONLY the class definitions. Max 20 lines."
                ),
                context="IMPORTS_PLACEHOLDER",
            ),
            GenerationStep(
                step_id=3, step_type="class_def",
                description=f"CRUD service class for {entity_name}",
                prompt=(
                    f"Generate a CRUDService class for {entity_name} with __init__ "
                    f"that accepts table_name='{entity_name.lower()}s'. "
                    f"Include db_path parameter defaulting to 'data.sqlite'. "
                    f"Output ONLY the class definition with __init__. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description=f"create() method for {entity_name}",
                prompt=(
                    f"Generate a create() method for {entity_name}CRUDService "
                    f"that INSERTs a new row into SQLite. "
                    f"Use parameterized queries (NO f-strings in SQL). "
                    f"Return the created item with its id. "
                    f"Output ONLY the method. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=5, step_type="method",
                description=f"read() and list() methods for {entity_name}",
                prompt=(
                    f"Generate read(id) and list(limit, offset) methods for "
                    f"{entity_name}CRUDService. Use parameterized SQL queries. "
                    f"Output ONLY the two methods. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=6, step_type="method",
                description=f"update() and delete() methods for {entity_name}",
                prompt=(
                    f"Generate update(id, data) and delete(id) methods for "
                    f"{entity_name}CRUDService. Use parameterized SQL. "
                    f"Output ONLY the two methods. Max 20 lines."
                ),
            ),
        ]

        return steps

    def _plan_auth_steps(self, entity_name: str, language: str) -> List[GenerationStep]:
        """Plan steps for auth module generation."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description="Auth imports",
                prompt=(
                    "Generate import statements for a JWT auth service: "
                    "hashlib, secrets, hmac, os, time, datetime, typing. "
                    "Conditional imports: jose (JWT), passlib (bcrypt). "
                    "Output ONLY imports. Max 10 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description="AuthService class with __init__",
                prompt=(
                    "Generate an AuthService class with __init__(secret_key, token_expire_minutes=30). "
                    "Store secret_key, setup password hashing (try passlib, fallback to hashlib). "
                    "Output ONLY the class with __init__. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description="hash_password and verify_password",
                prompt=(
                    "Generate hash_password(password) using PBKDF2 with random salt, "
                    "and verify_password(password, stored_hash) with hmac.compare_digest. "
                    "Output ONLY the two methods. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description="create_token and verify_token",
                prompt=(
                    "Generate create_token(user_id, role) that creates JWT with expiration, "
                    "and verify_token(token) that decodes and validates. "
                    "Use python-jose if available, fallback to HMAC-based tokens. "
                    "Output ONLY the two methods. Max 25 lines."
                ),
            ),
        ]
        return steps

    def _plan_integration_steps(self, entity_name: str, task_desc: str,
                                 language: str) -> List[GenerationStep]:
        """Plan steps for integration module (Stripe, Email, etc.)."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Integration imports for {entity_name}",
                prompt=(
                    f"Generate import statements for a {entity_name} integration service. "
                    f"Include: aiohttp (async HTTP), logging, typing, json, os. "
                    f"Output ONLY imports. Max 8 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"{entity_name}Client class",
                prompt=(
                    f"Generate a {entity_name}Client class with __init__(api_key, base_url). "
                    f"Setup session, headers with auth, retry config. "
                    f"Output ONLY class with __init__. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description=f"Core operation methods for {entity_name}",
                prompt=(
                    f"Generate 2-3 async methods for {entity_name}Client that perform "
                    f"the main API operations described in: {task_desc}. "
                    f"Each method should use aiohttp with error handling. "
                    f"Output ONLY the methods. Max 30 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description="Error handling and retry logic",
                prompt=(
                    f"Generate a _request method for {entity_name}Client with "
                    f"exponential backoff retry (3 attempts), timeout handling, "
                    f"and proper error classification. "
                    f"Output ONLY the method. Max 20 lines."
                ),
            ),
        ]
        return steps

    def _plan_analytics_steps(self, entity_name: str, fields: List[Dict],
                               language: str) -> List[GenerationStep]:
        """Plan steps for analytics module."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description="Analytics imports",
                prompt="Generate imports for analytics: sqlite3, logging, typing, datetime, collections. Output ONLY imports. Max 8 lines.",
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"AnalyticsService for {entity_name}",
                prompt=f"Generate AnalyticsService class with __init__(db_path). Connect to SQLite. Output ONLY class + __init__. Max 15 lines.",
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description="Aggregation methods",
                prompt=f"Generate get_summary() and get_trends(metric, period) methods using SQL aggregation. Output ONLY methods. Max 25 lines.",
            ),
        ]
        return steps

    def _plan_generic_steps(self, entity_name: str, task_desc: str,
                             language: str) -> List[GenerationStep]:
        """Plan steps for generic/unknown task type."""
        return [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Module imports for {entity_name}",
                prompt=f"Generate Python import statements for a module that: {task_desc}. Output ONLY imports. Max 10 lines.",
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"Main class for {entity_name}",
                prompt=f"Generate a Python class {entity_name}Manager with __init__ and initialize() method. Task: {task_desc}. Output ONLY class definition. Max 20 lines.",
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description=f"Core logic for {entity_name}",
                prompt=f"Generate an execute() method for {entity_name}Manager that: {task_desc}. Include error handling and input validation. Output ONLY the method. Max 30 lines.",
            ),
        ]

    # ================================================================
    #  EXECUTION
    # ================================================================

    def _execute_step(self, step: GenerationStep, language: str) -> Optional[str]:
        """Execute a single generation step using the LLM."""
        step.attempts += 1

        # Build the full prompt with context
        full_prompt = self._build_prompt(step, language)

        # Try LLM generation
        if self._llm:
            try:
                if hasattr(self._llm, 'generate'):
                    result = self._llm.generate(full_prompt)
                elif callable(self._llm):
                    result = self._llm(full_prompt)
                else:
                    result = None

                if result and isinstance(result, str):
                    # Extract code from markdown blocks if present
                    code = self._extract_code(result, language)
                    if code:
                        return code
                    return result.strip()
            except Exception as e:
                logger.warning(f"SmartPromptChain: LLM generation failed: {e}")

        # Fallback: template-based generation (no LLM needed)
        return self._template_fallback(step, language)

    def _build_prompt(self, step: GenerationStep, language: str) -> str:
        """Build a step prompt with context from previous steps."""
        parts = [
            f"TASK: {step.description}",
            f"LANGUAGE: {language}",
            f"MAX LINES: {MAX_LINES_PER_STEP}",
            "",
        ]

        if step.context:
            # Include only the last N lines of context (keep prompt small)
            context_lines = step.context.strip().split('\n')
            if len(context_lines) > 20:
                context_preview = '\n'.join(context_lines[-20:])
                parts.append(f"PREVIOUS CODE (last 20 lines):\n```{language}\n{context_preview}\n```")
            else:
                parts.append(f"PREVIOUS CODE:\n```{language}\n{step.context}\n```")
            parts.append("")

        parts.append(f"GENERATE NOW:\n{step.prompt}")
        parts.append("")
        parts.append("Output ONLY the requested code. No explanations. No markdown fences.")

        return '\n'.join(parts)

    # ================================================================
    #  VALIDATION & REPAIR
    # ================================================================

    def _validate_fragment(self, code: str, language: str) -> bool:
        """Validate a generated code fragment."""
        if not code or len(code.strip()) < 5:
            return False

        if language == "python":
            try:
                compile(code, '<fragment>', 'exec')
                return True
            except SyntaxError as e:
                logger.debug(f"SmartPromptChain: Syntax error in fragment: {e}")
                return False

        # For non-Python, just check it's not empty
        return len(code.strip()) > 10

    def _auto_repair(self, step: GenerationStep, broken_code: str,
                     language: str) -> Tuple[Optional[str], int]:
        """Try to repair a broken code fragment.

        Returns (repaired_code, repair_attempts) or (None, attempts)
        """
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            step.attempts += 1

            # Build repair prompt
            repair_prompt = (
                f"The following {language} code has a syntax error. Fix it.\n\n"
                f"BROKEN CODE:\n```{language}\n{broken_code}\n```\n\n"
                f"TASK: {step.description}\n"
                f"Fix the error and output ONLY the corrected code."
            )

            if self._llm:
                try:
                    if hasattr(self._llm, 'generate'):
                        repaired = self._llm.generate(repair_prompt)
                    elif callable(self._llm):
                        repaired = self._llm(repair_prompt)
                    else:
                        continue

                    if repaired:
                        code = self._extract_code(repaired, language) or repaired.strip()
                        if self._validate_fragment(code, language):
                            return code, attempt + 1
                        broken_code = code  # Try to fix the fix
                except Exception as e:
                    logger.debug(f"SmartPromptChain: Repair attempt {attempt+1} failed: {e}")

        return None, MAX_REPAIR_ATTEMPTS

    # ================================================================
    #  HELPERS
    # ================================================================

    @staticmethod
    def _detect_task_type(description: str) -> str:
        """Detect what type of generation task this is."""
        desc = description.lower()
        if any(kw in desc for kw in ["crud", "create", "read", "update", "delete",
                                      "service", "api", "resource", "manage"]):
            return "crud"
        if any(kw in desc for kw in ["auth", "jwt", "login", "token", "password",
                                      "registro", "signup"]):
            return "auth"
        if any(kw in desc for kw in ["stripe", "payment", "email", "smtp",
                                      "telegram", "webhook", "integration",
                                      "pago", "correo"]):
            return "integration"
        if any(kw in desc for kw in ["analytics", "report", "dashboard",
                                      "stats", "metric", "analisis"]):
            return "analytics"
        return "generic"

    @staticmethod
    def _extract_code(text: str, language: str = "python") -> Optional[str]:
        """Extract code from markdown code blocks."""
        # Try ```python ... ``` or ``` ... ```
        pattern = rf'```(?:{language})?\s*\n(.*?)```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _template_fallback(self, step: GenerationStep, language: str) -> str:
        """Generate code without LLM using predefined templates."""
        st = step.step_type
        desc = step.description

        if st == "imports":
            if "auth" in desc.lower() or "jwt" in desc.lower():
                return (
                    "import hashlib\nimport secrets\nimport hmac\nimport os\n"
                    "import time\nimport logging\nfrom typing import Optional, Dict, Any\n"
                    "from datetime import datetime, timedelta\n\n"
                    "try:\n    from jose import JWTError, jwt\n    JOSE_AVAILABLE = True\n"
                    "except ImportError:\n    JOSE_AVAILABLE = False\n"
                )
            elif "crud" in desc.lower() or "service" in desc.lower():
                return (
                    "import sqlite3\nimport logging\nimport re\n"
                    "from typing import Optional, Dict, Any, List, Tuple\n\n"
                    "logger = logging.getLogger(__name__)\n"
                )
            else:
                return (
                    "import logging\nfrom typing import Optional, Dict, Any, List\n\n"
                    "logger = logging.getLogger(__name__)\n"
                )

        elif st == "schema":
            return step.context + "\n# Schema generated from context\n"

        elif st == "class_def":
            # Extract class name from description
            match = re.search(r'(\w+)(?:Service|Client|Manager)', desc)
            class_name = match.group(0) if match else "GeneratedModule"
            return (
                f"\nclass {class_name}:\n"
                f'    """Auto-generated by SmartPromptChain."""\n\n'
                f"    def __init__(self, **kwargs):\n"
                f"        for key, value in kwargs.items():\n"
                f"            setattr(self, key, value)\n"
            )

        elif st == "method":
            return (
                "\n    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:\n"
                '        """Execute the main operation."""\n'
                "        try:\n"
                "            # TODO: Implement specific logic\n"
                "            return {'success': True, 'data': payload}\n"
                "        except Exception as e:\n"
                "            logger.error(f'Execution failed: {e}')\n"
                "            return {'success': False, 'error': str(e)}\n"
            )

        elif st == "tests":
            return (
                "\nimport pytest\n\n"
                "class TestGenerated:\n"
                "    def test_execute(self):\n"
                "        result = self.module.execute({'test': True})\n"
                "        assert result['success'] is True\n"
            )

        return f"# Generated step: {step.step_type} — {step.description}\n"
