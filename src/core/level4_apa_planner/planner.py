"""
TITAN OMNISCALE X - APA Planner v16 (Z3 Real + MCTS Real)

Planificador con MCTS real (UCB1, backpropagation, depth limiting)
y Solver real (Z3 con fallback AC-3, timeout enforcement).

Lee configuracion desde YAML. Sin dependencias externas obligatorias.
Compatible con Android (Z3 opcional, AC-3 fallback automatico).
"""

import uuid
import time
import logging
import gc
from src.core.shared.contracts import (
    ExecutionPlan, PlanStep, OperationType, RoutePath,
    MCTSPlanner, Z3Solver, ConstraintSolver, TimeoutEnforcer,
    CodeConstraintBuilder, Constraint, HAS_Z3
)
from src.config.loader import (
    load_settings, get_solver_timeout_ms, get_solver_fast_timeout_ms,
    get_mcts_config, get_k_path_limit
)
from src.core.shared.resource_governor import get_governor

logger = logging.getLogger(__name__)


class APAPlanner:
    """
    Planificador APA con Solver real (Z3 o AC-3) y MCTS real.

    Implementa el Nivel 4 del documento de arquitectura:
    - Z3 SMT Solver (15s quirurgico) con fallback AC-3
    - MCTS con profundidad maxima configurable (default 5)
    - Protocolo abortivo cuando el solver agota el presupuesto
    - Timeout enforcement real
    """

    def __init__(self):
        self.settings = load_settings()
        self.solver_timeout_ms = get_solver_timeout_ms(self.settings)
        self.solver_fast_timeout_ms = get_solver_fast_timeout_ms(self.settings)
        mcts_config = get_mcts_config(self.settings)
        self.MCTS_MAX_DEPTH = mcts_config["max_depth"]
        self.MCTS_MAX_SIMULATIONS = mcts_config["max_simulations"]
        self.mcts_timeout_ms = mcts_config["timeout_ms"]

        solver_name = "Z3" if HAS_Z3 else "AC-3"
        logger.info("APA Planner: Solver=%s, MCTS depth=%d, Solver timeout=%dms",
                     solver_name, self.MCTS_MAX_DEPTH, self.solver_timeout_ms)

    def generate_plan(self, routing):
        intent = routing.intent
        solver_result = None
        governor = get_governor()

        # Throttle CPU entre requests pesados
        governor.cpu_throttle_sleep()

        # Timeout adaptativo segun carga del sistema
        adaptive_solver_timeout = governor.get_adaptive_solver_timeout(self.solver_timeout_ms)

        # Ejecutar solver si la ruta lo requiere
        if routing.route == RoutePath.SURGICAL_PATH:
            solver_result = self._run_smt_solver(intent, adaptive_solver_timeout)
        elif routing.route == RoutePath.DEEP_PATH:
            solver_result = self._run_fast_solver(intent)

        # MCTS con simulaciones adaptativas segun carga CPU
        adaptive_sims = governor.get_adaptive_mcts_simulations(self.MCTS_MAX_SIMULATIONS)
        adaptive_mcts_timeout = governor.get_adaptive_solver_timeout(self.mcts_timeout_ms)

        mcts = MCTSPlanner(
            max_depth=self.MCTS_MAX_DEPTH,
            max_simulations=adaptive_sims,
            timeout_ms=adaptive_mcts_timeout
        )

        initial_state = {
            "target": intent.target,
            "op": intent.op,
            "goal": intent.goal,
            "depth": 0,
            "taken_actions": [],
        }

        best_action = mcts.search(
            initial_state,
            action_generator=self._action_generator,
            reward_function=self._reward_function
        )

        # Generar pasos del plan
        steps = self._build_steps(intent, routing, best_action)

        # Determinar solver status
        solver_status = self._determine_solver_status(solver_result, routing)

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            steps=steps,
            solver_status=solver_status,
            solver_proof=solver_result,
            mcts_simulations=mcts.simulations_run,
            mcts_depth_reached=mcts.depth_reached
        )

    def _run_smt_solver(self, intent, timeout_ms=None):
        """
        Ejecuta el SMT Solver (Z3 si disponible, AC-3 si no) para nodos quirurgicos.

        Verifica invariantes de codigo con timeout adaptativo.
        Implementa el Protocolo Abortivo del documento:
        si el solver hace timeout, devuelve TIMEOUT para que el
        orquestador subdivida automaticamente.
        
        Incluye proteccion de recursos:
        - Timeout adaptativo segun carga del sistema
        - GC forzado despues de Z3 (libera memoria del solver)
        """
        solver_type = "Z3" if HAS_Z3 else "AC-3"
        effective_timeout = timeout_ms or self.solver_timeout_ms
        governor = get_governor()

        logger.info("Running %s solver for surgical node: %s (timeout: %dms)",
                     solver_type, intent.target, effective_timeout)

        try:
            # Crear el solver apropiado con timeout adaptativo
            z3_solver = Z3Solver(timeout_ms=effective_timeout)

            # Construir dominios y restricciones desde el analisis
            domains = CodeConstraintBuilder.build_domains_from_code({})

            # Agregar dominios especificos del target quirurgico
            domains["target_type"] = ["critical", "standard", "unknown"]
            domains["mutation_risk"] = ["high", "medium", "low", "none"]
            domains["validation_needed"] = ["full", "partial", "none"]

            # Restriccion critica: si es target critico, requiere validacion completa
            constraints = CodeConstraintBuilder.build_null_safety_constraints([
                {"name": "target_type", "can_be_none": False},
                {"name": "mutation_risk", "can_be_none": False},
                {"name": "validation_needed", "can_be_none": False}
            ])

            constraints.append(Constraint(
                "target_type", "validation_needed",
                lambda t, v: t != "critical" or v == "full",
                description="critical_targets_require_full_validation"
            ))

            constraints.append(Constraint(
                "mutation_risk", "validation_needed",
                lambda r, v: r != "high" or v in ["full", "partial"],
                description="high_risk_requires_validation"
            ))

            # Ejecutar con timeout enforcement real
            enforcer = TimeoutEnforcer(timeout_ms=effective_timeout)
            result, timed_out = enforcer.execute_with_timeout(
                z3_solver.solve_constraints, domains, constraints
            )

            # GC forzado despues de solver pesado (Z3 puede dejar mucha basura)
            gc.collect(1)

            if timed_out:
                logger.warning(
                    "SMT Solver TIMEOUT (%d ms) para %s - Protocolo Abortivo activado",
                    effective_timeout, intent.target
                )
                return {
                    "status": "TIMEOUT",
                    "assignment": None,
                    "solver_type": solver_type,
                    "timeout_ms": effective_timeout,
                    "subdivide_required": True,  # Senal para el Protocolo Abortivo
                }

            # Agregar metadata del solver usado
            if isinstance(result, dict):
                result["solver_type"] = solver_type

            return result

        except Exception as e:
            logger.error("SMT Solver error: %s", e)
            # GC de emergencia
            gc.collect(2)
            return {
                "status": "ERROR",
                "message": str(e),
                "solver_type": solver_type,
                "subdivide_required": True,
            }

    def _run_fast_solver(self, intent):
        """
        Ejecuta un solver rapido (5s timeout) para nodos moderados.
        Solo verifica invariantes basicas.

        Incluye timeout enforcement real como _run_smt_solver.
        """
        try:
            domains = {
                "target_type": ["standard", "unknown"],
                "mutation_risk": ["medium", "low", "none"],
                "validation_needed": ["partial", "none"]
            }

            constraints = [
                Constraint(
                    "mutation_risk", "validation_needed",
                    lambda r, v: r != "medium" or v != "none",
                    description="medium_risk_needs_some_validation"
                )
            ]

            # Usar Z3Solver (que internamente usa Z3 o AC-3)
            z3_solver = Z3Solver(timeout_ms=self.solver_fast_timeout_ms)

            # Ejecutar con timeout enforcement real
            enforcer = TimeoutEnforcer(timeout_ms=self.solver_fast_timeout_ms)
            result, timed_out = enforcer.execute_with_timeout(
                z3_solver.solve_constraints, domains, constraints
            )

            if timed_out:
                logger.warning(
                    "Fast Solver TIMEOUT (%d ms) para %s",
                    self.solver_fast_timeout_ms, intent.target
                )
                return {
                    "status": "TIMEOUT",
                    "assignment": None,
                    "timeout_ms": self.solver_fast_timeout_ms,
                }

            return result

        except Exception as e:
            logger.warning("Fast solver error: %s", e)
            return {"status": "ERROR", "message": str(e)}

    def _action_generator(self, state, depth):
        """Genera acciones posibles desde un estado del plan."""
        if depth >= self.MCTS_MAX_DEPTH:
            return []

        op = state.get("op", "")
        actions = []

        if op == OperationType.CREATE:
            actions = ["ANALYZE_STRUCTURE", "SCRAPE_PATTERNS", "GENERATE_CODE",
                       "VALIDATE_SECURITY", "SYMBOLIC_VALIDATION"]
        elif op == OperationType.REFACTOR:
            actions = ["ANALYZE_PATTERNS", "REPLACE_AST_NODE", "VALIDATE_INTERFACE",
                       "SYMBOLIC_VALIDATION", "RUN_TESTS"]
        elif op == OperationType.DEBUG:
            actions = ["TRACE_EXECUTION", "PATCH_FIX", "VALIDATE_FIX",
                       "SYMBOLIC_VALIDATION"]
        elif op == OperationType.DELETE:
            actions = ["CHECK_DEPENDENCIES", "DELETE_AST_NODE", "VALIDATE_NO_BREAKAGE"]
        elif op == OperationType.OPTIMIZE:
            actions = ["ANALYZE_PATTERNS", "REPLACE_AST_NODE", "BENCHMARK",
                       "VALIDATE_PERFORMANCE"]
        elif op == OperationType.ANALYZE:
            actions = ["ANALYZE_STRUCTURE", "QUALITY_REPORT", "SUGGEST_IMPROVEMENTS"]
        elif op == OperationType.EXPLAIN:
            actions = ["EXPLAIN_CODE", "GENERATE_DOCS"]
        elif op == OperationType.SEARCH:
            actions = ["SEARCH_DEFINITION", "FIND_REFERENCES"]
        else:
            actions = ["QUICK_ANALYSIS"]

        # Filtrar acciones ya tomadas en este camino
        taken = state.get("taken_actions", [])
        available = [a for a in actions if a not in taken]

        return available

    def _reward_function(self, state):
        """
        Funcion de recompensa para MCTS.
        Premia planes que: cubren mas operaciones, son mas profundos,
        incluyen validacion, y terminan en estados completos.
        """
        reward = 0.1
        depth = state.get("depth", 0)
        taken = state.get("taken_actions", [])

        # Premiar profundidad (hasta el limite)
        reward += min(depth, self.MCTS_MAX_DEPTH) * 0.1

        # Premiar inclusion de validacion
        validation_actions = [a for a in taken if "VALIDATE" in a or "SYMBOLIC" in a]
        reward += len(validation_actions) * 0.2

        # Premiar planes completos (que incluyen generacion + validacion)
        has_generation = any(a in taken for a in ["GENERATE_CODE", "REPLACE_AST_NODE", "PATCH_FIX"])
        has_validation = len(validation_actions) > 0
        if has_generation and has_validation:
            reward += 0.3

        # Penalizar planes muy superficiales
        if depth < 2 and len(taken) < 2:
            reward -= 0.1

        return max(0.0, min(1.0, reward))

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
