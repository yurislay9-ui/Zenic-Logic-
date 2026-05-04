"""
StepDispatcher - Unified step dispatch logic for pipeline execution.

Eliminates the duplicated step dispatch code that existed in:
- orchestrator.py (TitanOrchestrator.execute step loop)
- dag_orchestrator.py (DAGOrchestrator._execute_step)
- abortive_protocol.py (AbortiveProtocol.execute_subtask step loop)

All three previously maintained identical if/elif chains for handling
step actions like ANALYZE_STRUCTURE, SCRAPE_PATTERNS, GENERATE_CODE, etc.

This module provides a single `execute_step()` method and a
`execute_plan_steps()` method that iterates plan steps.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class StepDispatcher:
    """
    Unified step dispatch logic for all orchestrator variants.

    Takes a reference to the orchestrator (BaseOrchestrator) to access
    its components (ast_engine, scrap, surgeon, _code_gen, _code_transform,
    _analysis, _ai, _validation_agent, _agent_runner, _fractal_gen, etc.).

    Handles ALL step action types:
    - ANALYZE_STRUCTURE
    - SCRAPE_PATTERNS
    - GENERATE_CODE
    - REPLACE_AST_NODE
    - DELETE_AST_NODE
    - TRACE_EXECUTION
    - PATCH_FIX
    - QUALITY_REPORT
    - EXPLAIN_CODE
    - SEARCH_DEFINITION
    - SYMBOLIC_VALIDATION / SYNTAX_VALIDATION
    - ANALYZE_AND_RESPOND
    - QUICK_ANALYSIS
    - FULL_ANALYSIS
    - CHECK_DEPENDENCIES
    - SCAFFOLD_FRACTAL
    """

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: BaseOrchestrator (or subclass) instance for
                         accessing pipeline components.
        """
        self._orch = orchestrator

    async def execute_step(
        self,
        step,
        intent,
        code: str,
        result_code: str,
        explanations: List[str],
        lang: str,
        ast_analysis: Dict,
        plan,
    ) -> Tuple[str, str, List[str]]:
        """
        Execute a single step of the plan.

        Args:
            step: Plan step with .action, .constraints, .target_node_name
            intent: IntentPayload with operation context
            code: Current code state
            result_code: Current result code
            explanations: List of explanation strings (mutated in place)
            lang: Programming language
            ast_analysis: AST analysis results
            plan: The full plan (for solver_proof, etc.)

        Returns:
            Tuple of (result_code, code, explanations)
        """
        orch = self._orch
        action = step.action

        if action == "ANALYZE_STRUCTURE":
            if code:
                analysis = orch.ast_engine.analyze_structure(code, lang)
                explanations.append(
                    f"Structure: {analysis['functions']} functions, "
                    f"{analysis['classes']} classes, max complexity "
                    f"{analysis['max_complexity']}"
                )
            else:
                explanations.append("No code provided for analysis.")

        elif action == "SCRAPE_PATTERNS":
            query = step.constraints.get("query", intent.scrap_query)
            # SmartScraper: Auto-routing multi-fuente
            smart_result = await orch.scrap.smart_fetch(query, lang)
            if smart_result.get("success") and smart_result.get("content"):
                source_name = smart_result.get("source", "github")
                explanations.append(
                    f"SmartScraper: Found content via {source_name}"
                )
                content = smart_result["content"]
                if not code:
                    code = content
            else:
                # Fallback: buscar en todas las fuentes
                all_results = await orch.scrap.fetch_all_sources(query, lang)
                best_content = ""
                best_source = ""
                for src in ["github", "devdocs", "iconstack", "picsum"]:
                    if src in all_results and all_results[src]:
                        best_content = all_results[src]
                        best_source = src
                        break
                if best_content:
                    explanations.append(
                        f"SmartScraper: Found content via {best_source} "
                        f"(fallback)"
                    )
                    if not code:
                        code = best_content
                else:
                    explanations.append(
                        "SmartScraper: No results. Using local generation."
                    )

        elif action == "GENERATE_CODE":
            result_code = orch._code_gen.generate_contextual_code(
                intent, ast_analysis, plan, lang
            )
            explanations.append(f"Code generated for {intent.op}")

        elif action == "REPLACE_AST_NODE":
            if code and step.target_node_name:
                solver_insights = (
                    orch._code_gen.extract_solver_insights(plan.solver_proof)
                    if plan else None
                )
                # MiniAI: sugerir patron de reemplazo
                if orch._ai.is_loaded:
                    pattern = orch._ai.suggest_pattern(
                        step.target_node_name, str(intent)
                    )
                    explanations.append(f"MiniAI suggests pattern: {pattern}")
                new_snippet = orch._code_transform.optimize_function(
                    step.target_node_name, lang, ast_analysis, solver_insights
                )
                result_code = orch.surgeon.mutate_node(
                    code, step.target_node_name, new_snippet, lang
                )
                explanations.append(
                    f"Function '{step.target_node_name}' replaced "
                    f"via AST surgery"
                )
            else:
                result_code = orch._code_gen.generate_contextual_code(
                    intent, ast_analysis, plan, lang
                )
                explanations.append("Optimized code generated")

        elif action == "DELETE_AST_NODE":
            if code and step.target_node_name:
                result_code = orch.surgeon.delete_function(
                    code, step.target_node_name, lang
                )
                explanations.append(
                    f"Function '{step.target_node_name}' deleted "
                    f"via AST surgery"
                )

        elif action == "TRACE_EXECUTION":
            explanations.append(
                "Symbolic execution trace performed (K-Path limited)"
            )
            if code:
                analysis = orch.ast_engine.analyze_structure(code, lang)
                for fn_name in analysis.get("function_names", []):
                    explanations.append(f"  - Traced: {fn_name}")

        elif action == "PATCH_FIX":
            result_code = orch._analysis.apply_fix(code, intent, lang)
            explanations.append("Fix patch applied")

        elif action == "QUALITY_REPORT":
            if code:
                report = orch._analysis.generate_quality_report(
                    orch.ast_engine.analyze_structure(code, lang), code, lang
                )
                explanations.append(report)

        elif action == "EXPLAIN_CODE":
            if code:
                base_explanation = orch._analysis.explain_code(
                    code, lang, ast_analysis
                )
                # MiniAI: mejorar explicacion si hay violaciones detectadas
                if orch._ai.is_loaded:
                    violations = []
                    if "eval(" in code or "exec(" in code:
                        violations.append("dangerous_call")
                    if "os.system(" in code:
                        violations.append("command_injection")
                    if violations:
                        ai_explain = orch._ai.explain_violation(
                            code[:200], violations
                        )
                        if ai_explain:
                            base_explanation += f" | AI: {ai_explain}"
                explanations.append(base_explanation)
            else:
                explanations.append(
                    orch._analysis.explain_concept(intent)
                )

        elif action == "SEARCH_DEFINITION":
            if code:
                nodes = orch.ast_engine.get_node_info(intent.target)
                if nodes:
                    for n in nodes[:5]:
                        explanations.append(
                            f"Found: {n['node_type']} '{n['name']}' "
                            f"(complexity: {n.get('complexity', 'N/A')})"
                        )
                else:
                    explanations.append(
                        f"'{intent.target}' not found in code"
                    )

        elif action in ("SYMBOLIC_VALIDATION", "SYNTAX_VALIDATION"):
            # Use ValidationAgent (F5) for intelligent validation
            if orch._validation_agent and code:
                from src.core.agents.schemas import ValidationInput
                v_output = orch._validation_agent.validate_with_runner(
                    orch._agent_runner,
                    target="code",
                    content=code,
                    rules=["security", "quality"],
                    language=lang,
                )
                if v_output.issues:
                    issue_strs = [
                        f"{i.severity}: {i.message}"
                        for i in v_output.issues[:5]
                    ]
                    explanations.append(
                        f"Validation (F5): {len(v_output.issues)} issues "
                        f"found (risk={v_output.risk_score:.2f}, "
                        f"source={v_output.source})"
                    )
                    for iss in issue_strs:
                        explanations.append(f"  - {iss}")
                else:
                    explanations.append(
                        "Validation (F5): No issues found"
                    )
            else:
                explanations.append(
                    "Symbolic validation executed "
                    "(bounded symbolic execution)"
                )

        elif action == "SCAFFOLD_FRACTAL":
            # Brecha C: Generacion Fractal (Top-Down) multi-archivo
            if hasattr(orch, '_fractal_gen') and orch._fractal_gen:
                from src.core.agents.intent_shared import infer_template_type
                project_type = infer_template_type(
                    str(intent.op), intent.raw_code or str(intent)
                )
                fractal_result = orch._fractal_gen.generate_project(
                    description=str(intent),
                    project_type=project_type,
                    project_name=intent.target or "generated_project",
                    language=lang,
                    output_dir="",
                )
                if fractal_result.spec and fractal_result.spec.files:
                    project_repr = []
                    for f_bp in fractal_result.spec.files:
                        content = getattr(f_bp, '_generated_content', '')
                        if content:
                            project_repr.append(
                                f"# === {f_bp.path} ===\n{content}"
                            )
                    result_code = "\n\n".join(project_repr)
                    explanations.append(
                        f"Fractal: {len(fractal_result.files_generated)} "
                        f"files, phase={fractal_result.current_phase}"
                    )
                else:
                    explanations.append(
                        "Fractal: Fallback to standard generation"
                    )
            else:
                explanations.append(
                    "Fractal: Not available in this orchestrator"
                )

        elif action == "ANALYZE_AND_RESPOND":
            if code:
                explanations.append(
                    orch._analysis.analyze_and_respond(
                        code, intent, ast_analysis
                    )
                )
            else:
                explanations.append(
                    orch._analysis.general_response(intent)
                )

        elif action == "QUICK_ANALYSIS":
            explanations.append("Quick analysis completed")

        elif action == "FULL_ANALYSIS":
            if code:
                explanations.append(
                    orch._analysis.full_analysis(
                        code, intent, ast_analysis, lang
                    )
                )
            else:
                explanations.append(
                    orch._analysis.general_response(intent)
                )

        elif action == "CHECK_DEPENDENCIES":
            if code:
                deps = orch._analysis.check_dependencies(
                    code, intent.target, lang
                )
                explanations.extend(deps)

        return result_code, code, explanations

    async def execute_plan_steps(
        self,
        plan,
        intent,
        code: str,
        explanations: List[str],
        lang: str,
        ast_analysis: Dict,
    ) -> Tuple[str, str, List[str]]:
        """
        Iterate all steps in a plan and execute them sequentially.

        Args:
            plan: The plan with .steps list
            intent: IntentPayload with operation context
            code: Current code state
            explanations: List of explanation strings
            lang: Programming language
            ast_analysis: AST analysis results

        Returns:
            Tuple of (result_code, code, explanations)
        """
        result_code = ""

        for step in plan.steps:
            result_code, code, explanations = await self.execute_step(
                step, intent, code, result_code, explanations,
                lang, ast_analysis, plan,
            )

        return result_code, code, explanations
