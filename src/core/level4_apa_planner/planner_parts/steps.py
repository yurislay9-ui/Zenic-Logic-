"""Mixin: Step building and solver status for APAPlanner."""

from ._imports import PlanStep, OperationType, RoutePath


class StepsMixin:
    """Mixin providing plan step building and solver status determination."""

    def _build_steps(self, intent, routing, best_action_hint):
        """Construye los pasos del plan basado en la ruta y MCTS."""
        steps = []
        step_id = 1

        if routing.route == RoutePath.SURGICAL_PATH:
            steps.append(PlanStep(step_id=step_id, action="ANALYZE_STRUCTURE",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"depth": "full", "include_metrics": True}))
            step_id += 1

            if intent.op == OperationType.CREATE:
                steps.append(PlanStep(step_id=step_id, action="SCRAPE_PATTERNS",
                    target_node_name=intent.target, source="GITHUB_SCRAPE",
                    constraints={"query": intent.scrap_query, "max_results": 3}))
                step_id += 1
                steps.append(PlanStep(step_id=step_id, action="GENERATE_CODE",
                    target_node_name=intent.target, source="TEMPLATE_ENGINE",
                    constraints={"require_validation": True, "security_check": True}))
                step_id += 1

            elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
                steps.append(PlanStep(step_id=step_id, action="ANALYZE_PATTERNS",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"detect_smells": True, "metrics": True}))
                step_id += 1
                steps.append(PlanStep(step_id=step_id, action="REPLACE_AST_NODE",
                    target_node_name=intent.target, source="SURGICAL_GRAPH",
                    constraints={"preserve_interface": True, "security_check": True}))
                step_id += 1

            elif intent.op == OperationType.DEBUG:
                steps.append(PlanStep(step_id=step_id, action="TRACE_EXECUTION",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"symbolic": True, "k_path_limit": 10}))
                step_id += 1
                steps.append(PlanStep(step_id=step_id, action="PATCH_FIX",
                    target_node_name=intent.target, source="FIX_ENGINE",
                    constraints={"minimal_change": True}))
                step_id += 1

            elif intent.op == OperationType.DELETE:
                steps.append(PlanStep(step_id=step_id, action="CHECK_DEPENDENCIES",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"k_path_limit": 10}))
                step_id += 1
                steps.append(PlanStep(step_id=step_id, action="DELETE_AST_NODE",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"cascade": True}))
                step_id += 1

            else:
                steps.append(PlanStep(step_id=step_id, action="FULL_ANALYSIS",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"deep": True}))
                step_id += 1

            # Validacion simbolica obligatoria para ruta quirurgica
            steps.append(PlanStep(step_id=step_id, action="SYMBOLIC_VALIDATION",
                target_node_name=intent.target, source="SANDBOX",
                constraints={"k_path_limit": 10, "mock_externals": True}))

        elif routing.route == RoutePath.DEEP_PATH:
            steps.append(PlanStep(step_id=step_id, action="ANALYZE_STRUCTURE",
                target_node_name=intent.target, source="LOCAL_GRAPH",
                constraints={"depth": "standard"}))
            step_id += 1

            if intent.op == OperationType.CREATE:
                steps.append(PlanStep(step_id=step_id, action="SCRAPE_PATTERNS",
                    target_node_name=intent.target, source="GITHUB_SCRAPE",
                    constraints={"query": intent.scrap_query, "max_results": 2}))
                step_id += 1
                steps.append(PlanStep(step_id=step_id, action="GENERATE_CODE",
                    target_node_name=intent.target, source="TEMPLATE_ENGINE",
                    constraints={"require_validation": True}))
                step_id += 1

            elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
                steps.append(PlanStep(step_id=step_id, action="REPLACE_AST_NODE",
                    target_node_name=intent.target, source="SURGICAL_GRAPH",
                    constraints={"preserve_interface": True}))
                step_id += 1

            elif intent.op == OperationType.ANALYZE:
                steps.append(PlanStep(step_id=step_id, action="QUALITY_REPORT",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"include_suggestions": True}))
                step_id += 1

            elif intent.op == OperationType.DEBUG:
                steps.append(PlanStep(step_id=step_id, action="TRACE_EXECUTION",
                    target_node_name=intent.target, source="LOCAL_GRAPH",
                    constraints={"k_path_limit": 10}))
                step_id += 1

            else:
                steps.append(PlanStep(step_id=step_id, action="ANALYZE_AND_RESPOND",
                    target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
                step_id += 1

            steps.append(PlanStep(step_id=step_id, action="SYNTAX_VALIDATION",
                target_node_name=intent.target, source="SANDBOX",
                constraints={"basic": True}))

        else:  # FAST_PATH
            steps.append(PlanStep(step_id=step_id, action="QUICK_ANALYSIS",
                target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
            if intent.op == OperationType.EXPLAIN:
                steps.append(PlanStep(step_id=step_id+1, action="EXPLAIN_CODE",
                    target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))
            elif intent.op == OperationType.SEARCH:
                steps.append(PlanStep(step_id=step_id+1, action="SEARCH_DEFINITION",
                    target_node_name=intent.target, source="LOCAL_GRAPH", constraints={}))

        return steps

    def _determine_solver_status(self, solver_result, routing):
        """Determina el estado del solver basado en resultados reales."""
        if solver_result is None:
            if routing.route == RoutePath.FAST_PATH:
                return "SKIPPED_FAST_PATH"
            return "HEURISTIC_FALLBACK"

        status = solver_result.get("status", "UNKNOWN")

        if status in ("PROVEN", "SATISFIED"):
            return "PROVEN"
        elif status == "LIKELY_PROVEN":
            return "PROVEN_WITHIN_DEPTH_LIMIT"
        elif status == "TIMEOUT":
            return "TIMEOUT_SUBDIVIDE_REQUIRED"
        elif status in ("UNSATISFIABLE", "VIOLATED"):
            return "CONSTRAINTS_VIOLATED"
        elif status == "LIKELY_VIOLATED":
            return "LIKELY_VIOLATED"
        else:
            return "HEURISTIC_FALLBACK"
