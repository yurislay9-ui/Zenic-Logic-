"""APAPlanner main class combining all mixins."""

import uuid

from ._imports import (
    logger, HAS_Z3,
    ExecutionPlan, RoutePath, MCTSPlanner,
    load_settings, get_solver_timeout_ms, get_solver_fast_timeout_ms,
    get_mcts_config, get_governor
)
from .solver import SolverMixin
from .mcts import MCTSMixin
from .steps import StepsMixin


class APAPlanner(
    SolverMixin,
    MCTSMixin,
    StepsMixin,
):
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
