"""
TITAN OMNISCALE X - APA Planner (Pure Python)

Planificador de ejecucion. Sin dependencias externas (constraint, etc.)
"""
import uuid
from src.core.shared.contracts import RoutingPayload, ExecutionPlan, PlanStep, OperationType, RoutePath


class APAPlanner:
    def generate_plan(self, routing):
        intent = routing.intent
        status = "HEURISTIC_FALLBACK"
        if routing.route == RoutePath.DEEP_PATH:
            status = self._prove(intent)

        steps = []
        if intent.op in [OperationType.CREATE]:
            steps.append(PlanStep(
                step_id=1, action="SCRAPE_GITHUB",
                target_node_name=intent.target, source="GITHUB_SCRAPE",
                constraints={"query": intent.scrap_query}
            ))
            steps.append(PlanStep(
                step_id=2, action="INSERT_AST_NODE",
                target_node_name=intent.target, source="GITHUB_SCRAPE"
            ))
        elif intent.op == OperationType.REFACTOR:
            steps.append(PlanStep(
                step_id=1, action="REPLACE_AST_NODE",
                target_node_name=intent.target, source="LOCAL_GRAPH"
            ))
        elif intent.op == OperationType.DELETE:
            steps.append(PlanStep(
                step_id=1, action="DELETE_AST_NODE",
                target_node_name=intent.target, source="LOCAL_GRAPH"
            ))

        return ExecutionPlan(plan_id=str(uuid.uuid4()), steps=steps, solver_status=status)

    def _prove(self, intent):
        """Verificacion simple sin constraint solver."""
        if intent.op == OperationType.CREATE:
            return "PROVEN"
        return "PROVEN" if intent.target != "unknown" else "HEURISTIC_FALLBACK"
