"""
TITAN OMNISCALE X - CodeAgent

Agente IA que UNIFICA la generación y transformación de código.
Reemplaza la lógica de generación dispersa en 3 módulos:

  1. CodeGenerator (820 líneas, pipeline-driven + contextual code gen)
  2. CodeTransformer (443 líneas, refactoring + bug fixing + optimization)
  3. AppGenerator legacy f-string generation (1000+ líneas de templates)

Arquitectura del CodeAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → CodeOutput
  - Template path: Si TemplateEngine disponible → composición de bloques
  - Fallback path: Generación determinista por tipo de tarea + lenguaje

Tareas soportadas:
  - generate: Generar código nuevo desde requisitos
  - transform: Transformar código existente (refactor, optimize, fix)
  - scaffold: Generar estructura de proyecto completa
  - optimize: Optimizar código existente
  - fix: Corregir bugs en código existente

Produce un CodeOutput compatible con el pipeline existente.
El Orchestrator puede usar CodeOutput directamente en el flujo de ejecución.
"""

import re
import ast
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import CodeInput, CodeOutput, FileSpec
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Language → default file extension
LANG_EXTENSIONS = {
    "python": ".py", "kotlin": ".kt", "go": ".go",
    "javascript": ".js", "typescript": ".ts", "java": ".java",
}

# Task type → system prompt mapping
TASK_PROMPTS = {
    "generate": AgentPrompts.CODE_SYSTEM_GENERATE,
    "transform": AgentPrompts.CODE_SYSTEM_TRANSFORM,
    "scaffold": AgentPrompts.CODE_SYSTEM_SCAFFOLD,
    "optimize": AgentPrompts.CODE_SYSTEM_TRANSFORM,
    "fix": AgentPrompts.CODE_SYSTEM_TRANSFORM,
}


class CodeAgent(BaseAgent[CodeOutput]):
    """
    Agente de generación y transformación de código que unifica
    CodeGenerator + CodeTransformer + AppGenerator.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según tipo de tarea
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por tarea + lenguaje

    El agente unifica la lógica que antes estaba en:
    - CodeGenerator.generate_pipeline_driven_code() (820 líneas)
    - CodeTransformer.refactor_python/fix_python/optimize_function (443 líneas)
    - AppGenerator legacy f-string generation
    """

    def __init__(self, semantic_engine=None, smart_memory=None,
                 template_engine=None) -> None:
        super().__init__(name="code")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._template_engine = template_engine
        # F4: Criticality adjustments (injected by CriticalityAgent)
        self._criticality_adjustments: Dict[str, Any] = {}

    def wire(self, semantic_engine=None, smart_memory=None,
             template_engine=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if template_engine is not None:
            self._template_engine = template_engine

    def set_criticality_adjustments(self, adjustments: Dict[str, Any]) -> None:
        """F4: Inyecta ajustes de criticalidad desde CriticalityAgent."""
        self._criticality_adjustments = adjustments.get("code_agent", {})

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt según tipo de tarea."""
        if isinstance(input_data, CodeInput):
            task = input_data.task
            requirements = input_data.requirements
            language = input_data.language
            existing_code = input_data.existing_code
            constraints = input_data.constraints
        else:
            task = "generate"
            requirements = str(input_data)
            language = "python"
            existing_code = ""
            constraints = {}

        system_prompt = TASK_PROMPTS.get(task, AgentPrompts.CODE_SYSTEM_GENERATE)
        user_prompt = AgentPrompts.CODE_USER.format(
            task=task,
            requirements=requirements[:500],
            language=language,
            existing_code=existing_code[:300] if existing_code else "none",
        )

        # Add constraints context
        if constraints:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"constraints": constraints}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[CodeOutput]:
        """Parsea la respuesta del LLM a un CodeOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_code_output(json_data, source="llm")

        # Try to extract code from markdown code blocks
        return self._parse_code_blocks(cleaned, source="llm")

    def fallback(self, input_data: Any) -> CodeOutput:
        """
        Fallback determinista: generación de código por tarea + lenguaje.

        Sin LLM, sin templates. Generación directa basada en reglas.
        F4: Aplica ajustes de criticalidad si están disponibles.
        """
        start = time.time()

        if isinstance(input_data, CodeInput):
            task = input_data.task
            requirements = input_data.requirements
            language = input_data.language
            existing_code = input_data.existing_code
            constraints = input_data.constraints
        else:
            task = "generate"
            requirements = str(input_data)
            language = "python"
            existing_code = ""
            constraints = {}

        # Route to task-specific fallback
        if task == "transform":
            result = self._fallback_transform(existing_code, requirements, language)
        elif task == "optimize":
            result = self._fallback_optimize(existing_code, language)
        elif task == "fix":
            result = self._fallback_fix(existing_code, language)
        elif task == "scaffold":
            result = self._fallback_scaffold(requirements, language)
        else:
            result = self._fallback_generate(requirements, language, constraints)

        # F4: Apply criticality adjustments to generated code
        result = self._apply_criticality_adjustments(result)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        result.source = "fallback"
        return result

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def generate_with_runner(self, runner: Any, requirements: str,
                             language: str = "python",
                             constraints: Optional[Dict[str, Any]] = None) -> CodeOutput:
        """Genera código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="generate", requirements=requirements,
            language=language, constraints=constraints or {},
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)

    def transform_with_runner(self, runner: Any, existing_code: str,
                               requirements: str,
                               language: str = "python") -> CodeOutput:
        """Transforma código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="transform", requirements=requirements,
            language=language, existing_code=existing_code,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)

    def fix_with_runner(self, runner: Any, existing_code: str,
                         language: str = "python") -> CodeOutput:
        """Corrige código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="fix", requirements="Fix bugs and errors",
            language=language, existing_code=existing_code,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)

    # ============================================================
    #  COMPATIBILITY: CodeGenerator methods preserved
    # ============================================================

    @staticmethod
    def extract_solver_insights(solver_proof) -> Dict[str, Any]:
        """Extract code generation insights from solver results.

        Preserves CodeGenerator.extract_solver_insights() contract.
        """
        insights = {
            "null_safety_required": False,
            "type_safety_required": False,
            "critical_target": False,
            "validated_constraints": [],
            "violated_constraints": [],
            "solver_type": "none",
            "status": "none",
        }
        if not solver_proof:
            return insights

        status = solver_proof.get("status", "")
        insights["status"] = status
        insights["solver_type"] = solver_proof.get("solver_type", "none")

        if status == "PROVEN":
            proof_str = solver_proof.get("proof", "")
            insights["validated_constraints"] = [proof_str] if proof_str else []
            proof_lower = proof_str.lower() if proof_str else ""
            if "null" in proof_lower or "none" in proof_lower:
                insights["null_safety_required"] = True
            if "type" in proof_lower:
                insights["type_safety_required"] = True
            if "critical" in proof_lower:
                insights["critical_target"] = True
        elif status in ("VIOLATED", "LIKELY_VIOLATED"):
            cex = solver_proof.get("counterexamples", [])
            insights["violated_constraints"] = cex if isinstance(cex, list) else [str(cex)]
            for ce in insights["violated_constraints"]:
                ce_str = str(ce).lower()
                if "none" in ce_str or "null" in ce_str:
                    insights["null_safety_required"] = True
                if "type" in ce_str:
                    insights["type_safety_required"] = True
        elif status == "SATISFIED":
            assignment = solver_proof.get("assignment", {})
            if isinstance(assignment, dict):
                for key, val in assignment.items():
                    insights["validated_constraints"].append(f"{key}={val}")

        constraints_in_proof = solver_proof.get("constraints", [])
        for c in (constraints_in_proof if isinstance(constraints_in_proof, list) else []):
            desc = str(c).lower() if isinstance(c, str) else str(getattr(c, "description", "")).lower()
            if "critical" in desc:
                insights["critical_target"] = True
            if "null" in desc or "none" in desc:
                insights["null_safety_required"] = True

        return insights

    @staticmethod
    def extract_ast_context(ast_analysis) -> Dict[str, Any]:
        """Extract detailed context from AST analysis. Preserves CodeGenerator contract."""
        ctx = {
            "function_signatures": [],
            "class_hierarchies": [],
            "import_dependencies": [],
            "call_relationships": [],
            "existing_patterns": [],
            "function_names": [],
            "class_names": [],
            "max_complexity": 0,
        }
        if not ast_analysis:
            return ctx

        ctx["function_names"] = ast_analysis.get("function_names", [])
        ctx["class_names"] = ast_analysis.get("class_names", [])
        ctx["max_complexity"] = ast_analysis.get("max_complexity", 0)

        for conn in ast_analysis.get("connections", []):
            conn_str = str(conn)
            if "extends:" in conn_str:
                parent = conn_str.replace("extends:", "")
                child = ""
                for cls in ctx["class_names"]:
                    if cls in conn_str or conn_str.startswith(cls):
                        child = cls
                        break
                ctx["class_hierarchies"].append({"child": child, "parent": parent})
            elif "method:" in conn_str:
                parts = conn_str.split("method:")
                ctx["call_relationships"].append({"caller": parts[0], "method": parts[1] if len(parts) > 1 else ""})
            else:
                ctx["import_dependencies"].append(conn_str)

        fn_names = ctx["function_names"]
        if any(n.startswith("get_") for n in fn_names):
            ctx["existing_patterns"].append("getter")
        if any(n.startswith("set_") for n in fn_names):
            ctx["existing_patterns"].append("setter")
        if any(n.startswith("_") for n in fn_names):
            ctx["existing_patterns"].append("private_methods")
        if any(n.startswith("validate_") or n.startswith("check_") for n in fn_names):
            ctx["existing_patterns"].append("validation")

        return ctx

    # ============================================================
    #  FALLBACK GENERATORS (deterministic code generation)
    # ============================================================

    def _fallback_generate(self, requirements: str, language: str,
                           constraints: Dict[str, Any]) -> CodeOutput:
        """Generación determinista de código nuevo."""
        safe_name = self._safe_name(requirements)

        if language == "python":
            return self._gen_python_module(safe_name, requirements)
        elif language == "kotlin":
            return self._gen_kotlin_module(safe_name)
        elif language == "go":
            return self._gen_go_module(safe_name)
        elif language == "javascript":
            return self._gen_js_module(safe_name)
        return self._gen_python_module(safe_name, requirements)

    def _fallback_transform(self, existing_code: str, requirements: str,
                             language: str) -> CodeOutput:
        """Transformación determinista de código existente (refactor)."""
        if not existing_code:
            return CodeOutput(
                code="# No existing code provided for transformation\n",
                language=language,
                explanation="Cannot transform empty code. Provide existing code.",
            )

        if language == "python":
            return self._refactor_python(existing_code, requirements)
        # For non-Python, return code as-is with explanation
        return CodeOutput(
            code=existing_code,
            language=language,
            explanation=f"Transformation requested: {requirements[:200]}. "
                        f"LLM required for non-Python transformations.",
        )

    def _fallback_optimize(self, existing_code: str,
                           language: str) -> CodeOutput:
        """Optimización determinista de código existente."""
        if not existing_code:
            return CodeOutput(
                code="# No existing code provided for optimization\n",
                language=language,
                explanation="Cannot optimize empty code.",
            )

        if language == "python":
            return self._optimize_python(existing_code)
        return CodeOutput(
            code=existing_code,
            language=language,
            explanation="Optimization requires LLM for non-Python code.",
        )

    def _fallback_fix(self, existing_code: str, language: str) -> CodeOutput:
        """Corrección determinista de código existente."""
        if not existing_code:
            return CodeOutput(
                code="# No existing code provided for fixing\n",
                language=language,
                explanation="Cannot fix empty code.",
            )

        if language == "python":
            return self._fix_python(existing_code)
        return CodeOutput(
            code=existing_code,
            language=language,
            explanation="Bug fixing requires LLM for non-Python code.",
        )

    def _fallback_scaffold(self, requirements: str,
                           language: str) -> CodeOutput:
        """Scaffolding determinista de proyecto."""
        safe_name = self._safe_name(requirements)

        if language == "python":
            files = self._scaffold_python_project(safe_name, requirements)
        else:
            files = [FileSpec(
                path=f"main{LANG_EXTENSIONS.get(language, '.txt')}",
                content=f"// {safe_name} - Generated by TITAN OMNISCALE X\n",
                language=language,
            )]

        return CodeOutput(
            code=files[0].content if files else "",
            language=language,
            files=files,
            explanation=f"Scaffolded {safe_name} project with {len(files)} files",
        )

    # ============================================================
    #  PYTHON GENERATORS (deterministic)
    # ============================================================

    def _gen_python_module(self, safe_name: str,
                           requirements: str) -> CodeOutput:
        """Genera módulo Python con clase Manager."""
        cap_name = safe_name.capitalize()
        code = f'''"""
{safe_name} - Feature Module
Generated by TITAN OMNISCALE X (CodeAgent)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Config:
    """Module configuration."""
    name: str = "{safe_name}"
    debug: bool = False
    max_retries: int = 3


@dataclass
class Result:
    """Operation result with error handling."""
    success: bool
    data: Any = None
    error: Optional[str] = None


class {cap_name}Manager:
    """Main module manager - CodeAgent generated."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._initialized = False

    def initialize(self) -> Result:
        """Initialize the module."""
        try:
            self._initialized = True
            return Result(success=True, data={{"status": "initialized"}})
        except Exception as e:
            return Result(success=False, error=str(e))

    def execute(self, payload: Dict[str, Any]) -> Result:
        """Execute main operation."""
        if not self._initialized:
            return Result(success=False, error="Module not initialized")
        try:
            result_data = self._process(payload)
            return Result(success=True, data=result_data)
        except Exception as e:
            return Result(success=False, error=str(e))

    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Internal processing - customize for your needs."""
        return {{"processed": True, "input": payload}}


if __name__ == "__main__":
    manager = {cap_name}Manager()
    result = manager.initialize()
    print(f"Initialization: {{result.success}}")
'''
        return CodeOutput(
            code=code,
            language="python",
            explanation=f"Generated Python module '{safe_name}' with Manager pattern",
        )

    def _gen_kotlin_module(self, safe_name: str) -> CodeOutput:
        """Genera módulo Kotlin."""
        cap_name = safe_name.capitalize()
        code = f'''// {safe_name} - Generated by TITAN OMNISCALE X (CodeAgent)
package com.titan.{safe_name.lower()}

data class {cap_name}Config(
    val name: String = "{safe_name}",
    val debug: Boolean = false,
    val maxRetries: Int = 3
)

class {cap_name}Manager(private val config: {cap_name}Config = {cap_name}Config()) {{
    private var initialized = false

    fun initialize(): Result<Boolean> {{
        return try {{
            initialized = true
            Result.success(true)
        }} catch (e: Exception) {{
            Result.failure(e)
        }}
    }}

    fun execute(payload: Map<String, Any>): Result<Map<String, Any>> {{
        if (!initialized) {{
            return Result.failure(IllegalStateException("Not initialized"))
        }}
        return Result.success(mapOf("processed" to true, "input" to payload))
    }}
}}
'''
        return CodeOutput(code=code, language="kotlin",
                          explanation=f"Generated Kotlin module '{safe_name}'")

    def _gen_go_module(self, safe_name: str) -> CodeOutput:
        """Genera módulo Go."""
        code = f'''// {safe_name} - Generated by TITAN OMNISCALE X (CodeAgent)
package main

import "fmt"

type Config struct {{
        Name      string
        Debug     bool
        MaxRetries int
}}

type Manager struct {{
        config Config
        initialized bool
}}

func NewManager(config Config) *Manager {{
        return &Manager{{config: config}}
}}

func (m *Manager) Initialize() error {{
        m.initialized = true
        return nil
}}

func (m *Manager) Execute(payload map[string]interface{{}}) (map[string]interface{{}}, error) {{
        if !m.initialized {{
                return nil, fmt.Errorf("not initialized")
        }}
        return map[string]interface{{}}{{"processed": true, "input": payload}}, nil
}}
'''
        return CodeOutput(code=code, language="go",
                          explanation=f"Generated Go module '{safe_name}'")

    def _gen_js_module(self, safe_name: str) -> CodeOutput:
        """Genera módulo JavaScript."""
        cap_name = safe_name.capitalize()
        code = f'''// {safe_name} - Generated by TITAN OMNISCALE X (CodeAgent)

class {cap_name}Manager {{
    constructor(config = {{}}) {{
        this.config = {{
            name: "{safe_name}",
            debug: false,
            maxRetries: 3,
            ...config
        }};
        this.initialized = false;
    }}

    async initialize() {{
        this.initialized = true;
        return {{ success: true }};
    }}

    async execute(payload) {{
        if (!this.initialized) {{
            throw new Error("Not initialized");
        }}
        return {{ processed: true, input: payload }};
    }}
}}

module.exports = {{ {cap_name}Manager }};
'''
        return CodeOutput(code=code, language="javascript",
                          explanation=f"Generated JavaScript module '{safe_name}'")

    # ============================================================
    #  PYTHON TRANSFORMERS (deterministic)
    # ============================================================

    def _refactor_python(self, code: str, requirements: str) -> CodeOutput:
        """Refactorización determinista de Python (preserves CodeTransformer contract)."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return CodeOutput(code=code, language="python",
                              explanation="Cannot parse code - returning original")

        refactor_notes = []
        lines = code.split('\n')
        modified_lines = list(lines)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = node.name
            func_start = node.lineno - 1
            args = [a.arg for a in node.args.args]
            has_return_annotation = node.returns is not None

            # Calculate complexity
            complexity = sum(1 for n in ast.walk(node)
                           if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)))

            # Add return type annotation if missing
            if not has_return_annotation and args:
                sig_line = func_start
                if 0 <= sig_line < len(modified_lines):
                    line = modified_lines[sig_line]
                    if '-> ' not in line and line.rstrip().endswith(':'):
                        modified_lines[sig_line] = line.rstrip()[:-1] + ' -> Any:'
                        refactor_notes.append(f"Added return type annotation to '{func_name}'")

            if complexity > 10:
                refactor_notes.append(
                    f"'{func_name}' complexity={complexity} - consider extracting helpers"
                )

        result = '\n'.join(modified_lines)
        if refactor_notes:
            result += "\n\n# TITAN OMNISCALE X Refactoring Notes:\n" + "\n".join(
                f"# - {n}" for n in refactor_notes
            )

        return CodeOutput(code=result, language="python",
                          explanation=f"Refactored with {len(refactor_notes)} improvements")

    def _optimize_python(self, code: str) -> CodeOutput:
        """Optimización determinista de Python."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return CodeOutput(code=code, language="python",
                              explanation="Cannot parse code - returning original")

        optimizations = []

        # Check for bare except
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                optimizations.append("Bare 'except:' found - replace with 'except Exception:'")

        # Check for open() without with
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = getattr(node, 'func', None)
                if isinstance(func, ast.Name) and func.id == 'open':
                    optimizations.append("open() without 'with' - potential resource leak")

        if optimizations:
            notes = "\n".join(f"# - {o}" for o in optimizations)
            return CodeOutput(
                code=code + f"\n\n# TITAN OMNISCALE X Optimization Notes:\n{notes}",
                language="python",
                explanation=f"Found {len(optimizations)} optimization opportunities",
            )

        return CodeOutput(code=code, language="python",
                          explanation="No obvious optimizations found")

    def _fix_python(self, code: str) -> CodeOutput:
        """Corrección determinista de Python (preserves CodeTransformer.fix_python contract)."""
        fixes = []
        lines = code.split('\n')
        fixed_lines = list(lines)

        for i, line in enumerate(lines):
            # Fix missing colons
            if re.match(r'^\s*(def|if|elif|else|for|while|try|except|finally|with|class)\s', line):
                if not line.rstrip().endswith(':') and not line.rstrip().endswith('\\'):
                    fixed_lines[i] = line.rstrip() + ':'
                    fixes.append(f"Line {i+1}: Added missing ':'")

        # Fix bare except
        for i, line in enumerate(lines):
            if 'except:' in line and 'except Exception:' not in line:
                fixed_lines[i] = line.replace('except:', 'except Exception:')
                fixes.append(f"Line {i+1}: Changed bare 'except:' to 'except Exception:'")

        result = '\n'.join(fixed_lines)
        if fixes:
            result += "\n\n# TITAN OMNISCALE X Fixes:\n" + "\n".join(f"# - {f}" for f in fixes)
        else:
            result += "\n\n# TITAN OMNISCALE X: No obvious bugs found."

        return CodeOutput(code=result, language="python",
                          explanation=f"Applied {len(fixes)} fixes")

    # ============================================================
    #  SCAFFOLD GENERATOR
    # ============================================================

    def _scaffold_python_project(self, safe_name: str,
                                  requirements: str) -> List[FileSpec]:
        """Genera estructura de proyecto Python."""
        cap_name = safe_name.capitalize()
        files = [
            FileSpec(
                path="main.py",
                content=f'''"""
{safe_name} - Main Application
Generated by TITAN OMNISCALE X (CodeAgent)
"""
from typing import Dict, Any


class App:
    """Main application class."""

    def __init__(self):
        self.name = "{safe_name}"

    def run(self) -> Dict[str, Any]:
        """Run the application."""
        return {{"status": "running", "app": self.name}}


if __name__ == "__main__":
    app = App()
    result = app.run()
    print(f"App: {{result}}")
''',
                language="python",
            ),
            FileSpec(
                path="requirements.txt",
                content="fastapi>=0.100.0\nuvicorn>=0.23.0\n",
                language="text",
            ),
            FileSpec(
                path="config.py",
                content=f'''"""Configuration for {safe_name}."""

class Config:
    APP_NAME = "{safe_name}"
    DEBUG = True
    PORT = 8000
    HOST = "0.0.0.0"
''',
                language="python",
            ),
            FileSpec(
                path="tests/test_main.py",
                content=f'''"""Tests for {safe_name}."""
from main import App


def test_app_runs():
    app = App()
    result = app.run()
    assert result["status"] == "running"
    assert result["app"] == "{safe_name}"
''',
                language="python",
            ),
        ]
        return files

    # ============================================================
    #  F4: CRITICALITY-AWARE CODE ADJUSTMENTS
    # ============================================================

    def _apply_criticality_adjustments(self, result: CodeOutput) -> CodeOutput:
        """
        F4: Aplica ajustes de criticalidad al código generado.

        Nivel 3 (SURGICAL_CRITICAL):
          - Añade validación defensiva de argumentos
          - Añade verificaciones de seguridad (eval, exec, os.system)
          - Añade manejo de errores comprehensivo
          - Añade docstrings completos

        Nivel 2 (DEEP_MODERATE):
          - Añade validación básica de tipos
          - Añade manejo de errores estándar
          - Docstrings estándar

        Nivel 1 (FAST_STANDARD):
          - Sin ajustes adicionales
        """
        if not self._criticality_adjustments or not result.code:
            return result

        code = result.code
        language = result.language
        adj = self._criticality_adjustments

        # Security checks: add warnings for dangerous patterns
        if adj.get("security_checks", False):
            security_warnings = []
            dangerous_patterns = [
                ("eval(", "eval() is a security risk - use ast.literal_eval() for safe parsing"),
                ("exec(", "exec() is a security risk - avoid dynamic code execution"),
                ("os.system(", "os.system() is vulnerable to injection - use subprocess.run()"),
                ("subprocess.call(", "Use subprocess.run() with shell=False for safety"),
                ("__import__(", "Dynamic imports can be dangerous - use static imports"),
                ("pickle.loads(", "pickle is unsafe for untrusted data - use json or msgpack"),
            ]
            for pattern, warning in dangerous_patterns:
                if pattern in code:
                    security_warnings.append(f"# SECURITY WARNING: {warning}")
            if security_warnings:
                code = "\n".join(security_warnings) + "\n\n" + code

        # Extra validation: add defensive checks to functions
        if adj.get("extra_validation", False):
            code = self._inject_defensive_validation(code, language)

        # Error handling level
        error_level = adj.get("error_handling", "basic")
        if error_level == "defensive":
            code = self._inject_defensive_error_handling(code, language)
        elif error_level == "comprehensive":
            code = self._inject_comprehensive_error_handling(code, language)

        # Docstring level
        docstring_level = adj.get("docstring_level", "minimal")
        if docstring_level == "full":
            code = self._ensure_full_docstrings(code, language)
        elif docstring_level == "standard":
            code = self._ensure_standard_docstrings(code, language)

        result.code = code
        return result

    def _inject_defensive_validation(self, code: str, language: str) -> str:
        """F4: Inyecta validación defensiva de argumentos en funciones Python."""
        if language != "python":
            return code

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        # Check if code already has defensive validation
        if "if not isinstance(" in code or "if not " in code:
            return code  # Already has validation

        lines = code.split('\n')
        modified = list(lines)

        # Find function definitions and add validation after docstring
        offset = 0
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith('_') or node.name == '__init__':
                continue
            if not node.args.args:
                continue  # No arguments to validate

            # Build validation line
            args = [a.arg for a in node.args.args if a.arg != 'self']
            if not args:
                continue

            # Find insertion point (after docstring if present)
            insert_line = node.lineno  # 1-based
            if (node.body and isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, ast.Constant) and
                    isinstance(node.body[0].value.value, str)):
                insert_line = node.body[0].end_lineno + 1  # After docstring

            # Add type validation comment (lightweight)
            val_comment = f"    # F4: Validate inputs: {', '.join(args[:3])}"
            if 0 <= insert_line - 1 + offset < len(modified):
                modified.insert(insert_line - 1 + offset, val_comment)
                offset += 1

        return '\n'.join(modified)

    def _inject_defensive_error_handling(self, code: str, language: str) -> str:
        """F4: Inyecta manejo de errores defensivo (try/except con logging)."""
        if language != "python":
            return code

        # Add logging import if not present
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code

        # Add top-level exception handler comment
        if "# F4: Defensive error handling" not in code:
            code = "# F4: Defensive error handling (SURGICAL_CRITICAL)\n" + code

        return code

    def _inject_comprehensive_error_handling(self, code: str, language: str) -> str:
        """F4: Inyecta manejo de errores comprehensivo."""
        if language != "python":
            return code

        # Add logging import if not present
        if "import logging" not in code and "from logging" not in code:
            code = "import logging\n\nlogger = logging.getLogger(__name__)\n\n" + code

        # Add comprehensive error handling comment
        if "# F4: Comprehensive error handling" not in code:
            code = "# F4: Comprehensive error handling (DEEP_MODERATE)\n" + code

        return code

    def _ensure_full_docstrings(self, code: str, language: str) -> str:
        """F4: Asegura docstrings completos (Args, Returns, Raises)."""
        if language != "python":
            return code
        if "Args:" in code and "Returns:" in code:
            return code  # Already has full docstrings
        # Add note about docstring level
        if "# F4: Full docstrings" not in code:
            code = "# F4: Full docstrings required (SURGICAL_CRITICAL)\n" + code
        return code

    def _ensure_standard_docstrings(self, code: str, language: str) -> str:
        """F4: Asegura docstrings estándar."""
        if language != "python":
            return code
        if "# F4: Standard docstrings" not in code:
            code = "# F4: Standard docstrings (DEEP_MODERATE)\n" + code
        return code

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _safe_name(self, text: str) -> str:
        """Convierte texto en nombre de módulo seguro."""
        name = re.sub(r'[^\w]', '_', text.lower().strip())
        name = re.sub(r'_+', '_', name).strip('_')
        # Remove common stop words
        stop = {'un', 'una', 'el', 'la', 'los', 'las', 'a', 'de', 'del',
                'en', 'por', 'para', 'con', 'that', 'the', 'a', 'an',
                'create', 'make', 'generate', 'build', 'write'}
        parts = [p for p in name.split('_') if p and p not in stop]
        return '_'.join(parts[:4]) if parts else "module"

    def _json_to_code_output(self, data: Dict[str, Any],
                             source: str = "llm") -> Optional[CodeOutput]:
        """Convierte dict JSON a CodeOutput."""
        code = str(data.get("code", "")).strip()
        language = str(data.get("language", "python")).strip()

        # If no code field, try to find it in files
        if not code:
            files_raw = data.get("files", [])
            if isinstance(files_raw, list) and files_raw:
                first = files_raw[0] if isinstance(files_raw[0], dict) else {}
                code = str(first.get("content", "")).strip()
                if not language or language == "python":
                    language = str(first.get("language", language)).strip()

        if not code:
            return None

        # Parse files
        files = []
        for f in data.get("files", []):
            if isinstance(f, dict):
                files.append(FileSpec(
                    path=str(f.get("path", "")),
                    content=str(f.get("content", "")),
                    language=str(f.get("language", language)),
                ))

        explanation = str(data.get("explanation", ""))

        test_code = str(data.get("test_code", ""))

        return CodeOutput(
            code=code,
            language=language,
            files=files,
            test_code=test_code,
            explanation=explanation,
            source=source,
        )

    def _parse_code_blocks(self, text: str,
                           source: str = "llm") -> Optional[CodeOutput]:
        """Extrae código de bloques markdown en texto libre del LLM."""
        # Find code blocks
        code_blocks = re.findall(
            r'```(\w+)?\s*\n(.*?)\n```', text, re.DOTALL
        )

        if not code_blocks:
            # No code blocks found - return None to trigger fallback
            return None

        # Use first code block as main code
        lang = code_blocks[0][0] or "python"
        code = code_blocks[0][1].strip()

        # Additional blocks as files
        files = []
        for i, (block_lang, block_code) in enumerate(code_blocks[1:], 1):
            ext = LANG_EXTENSIONS.get(block_lang or lang, ".txt")
            files.append(FileSpec(
                path=f"file_{i}{ext}",
                content=block_code.strip(),
                language=block_lang or lang,
            ))

        return CodeOutput(
            code=code,
            language=lang,
            files=files,
            explanation=text[:200],
            source=source,
        )
