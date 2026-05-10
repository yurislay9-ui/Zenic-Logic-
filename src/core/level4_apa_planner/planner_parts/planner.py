"""APAPlanner main class combining all mixins.

FIX (Phase 2): Added retry with backoff for MCTS search. If the
MCTS search returns None (no actions available), we retry with a
broader action set. Also added retry for solver transient failures.

FIX (v16.1): Added z3_mcts_enabled config flag. When disabled (default
on ARM/Termux), Z3+MCTS is skipped for ALL criticality levels, reducing
latency by ~20-30s per high_crit request. The DAG pipeline still works
normally — only formal verification is skipped.
"""

import uuid
import time

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
    - z3_mcts_enabled flag para desactivar verificacion formal (default: False)
    """

    def __init__(self):
        self.settings = load_settings()
        self.solver_timeout_ms = get_solver_timeout_ms(self.settings)
        self.solver_fast_timeout_ms = get_solver_fast_timeout_ms(self.settings)
        mcts_config = get_mcts_config(self.settings)
        self.MCTS_MAX_DEPTH = mcts_config["max_depth"]
        self.MCTS_MAX_SIMULATIONS = mcts_config["max_simulations"]
        self.mcts_timeout_ms = mcts_config["timeout_ms"]
        # MCTS stats (updated by _run_mcts_with_retry)
        self._last_mcts_simulations = 0
        self._last_mcts_depth = 0

        # Check if Z3+MCTS is enabled via config
        from src.config.loader import get_z3_mcts_enabled
        self.z3_mcts_enabled = get_z3_mcts_enabled(self.settings)

        solver_name = "Z3" if HAS_Z3 else "AC-3"
        solver_status = "ENABLED" if self.z3_mcts_enabled else "DISABLED"
        logger.info(
            "APA Planner: Solver=%s, Z3+MCTS=%s, MCTS depth=%d, Solver timeout=%dms",
            solver_name, solver_status, self.MCTS_MAX_DEPTH, self.solver_timeout_ms
        )

    def generate_plan(self, routing):
        intent = routing.intent
        solver_result = None
        best_action_hint = None
        governor = get_governor()

        # Throttle CPU entre requests pesados
        governor.cpu_throttle_sleep()

        # ── Determine if Z3+MCTS should be skipped ──
        import os as _os
        crit_level = getattr(routing, 'criticality', 2)
        crit_path = {1: "low_crit", 2: "standard", 3: "high_crit"}.get(crit_level, "standard")
        skip_solver = _os.environ.get("TITAN_SKIP_SOLVER", "0") == "1"
        skip_mcts = _os.environ.get("TITAN_SKIP_MCTS", "0") == "1"

        # Skip Z3+MCTS when:
        # 1. Criticality is low_crit or standard (already skips SOLVER_VERIFY in DAG)
        # 2. z3_mcts_enabled is False (config flag, default on ARM)
        # 3. TITAN_SKIP_SOLVER env var is set
        should_skip_solver_mcts = (
            crit_path in ("low_crit", "standard")
            or not self.z3_mcts_enabled
            or skip_solver
        )

        if should_skip_solver_mcts:
            reason = crit_path if crit_path in ("low_crit", "standard") else (
                "config_disabled" if not self.z3_mcts_enabled else "env_skip"
            )
            logger.info(
                "APAPlanner: SKIP solver+MCTS (%s) for crit=%d — heuristic steps only",
                reason, crit_level
            )
            steps = self._build_steps(intent, routing, best_action_hint=None)
            return ExecutionPlan(
                plan_id=str(uuid.uuid4()),
                steps=steps,
                solver_status="SKIPPED_" + crit_path.upper(),
                solver_proof=None,
                mcts_simulations=0,
                mcts_depth_reached=0
            )

        # ── HIGH_CRIT with Z3+MCTS enabled: Run full solver + MCTS ──
        # Timeout adaptativo segun carga del sistema
        adaptive_solver_timeout = governor.get_adaptive_solver_timeout(self.solver_timeout_ms)

        # Ejecutar solver si la ruta lo requiere (and not globally skipped)
        if not skip_solver:
            solver_result = self._run_solver_with_retry(
                routing, intent, adaptive_solver_timeout
            )
        else:
            logger.info("APAPlanner: Solver SKIPPED by TITAN_SKIP_SOLVER=1")

        # MCTS con simulaciones adaptativas (and not globally skipped)
        if not skip_mcts:
            adaptive_sims = governor.get_adaptive_mcts_simulations(self.MCTS_MAX_SIMULATIONS)
            adaptive_mcts_timeout = governor.get_adaptive_solver_timeout(self.mcts_timeout_ms)
            best_action_hint = self._run_mcts_with_retry(
                intent, adaptive_sims, adaptive_mcts_timeout
            )
        else:
            logger.info("APAPlanner: MCTS SKIPPED by TITAN_SKIP_MCTS=1")
            self._last_mcts_simulations = 0
            self._last_mcts_depth = 0

        # Generar pasos del plan
        steps = self._build_steps(intent, routing, best_action_hint)

        # Determinar solver status
        solver_status = self._determine_solver_status(solver_result, routing)

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            steps=steps,
            solver_status=solver_status,
            solver_proof=solver_result,
            mcts_simulations=self._last_mcts_simulations,
            mcts_depth_reached=self._last_mcts_depth
        )

    def _run_solver_with_retry(self, routing, intent, adaptive_timeout):
        """Run solver with retry for transient failures.

        FIX (Phase 2): Z3 can fail transiently (resource limits, internal
        errors). Retry up to 2 times with fresh solver instances.
        """
        max_solver_attempts = 2
        solver_result = None

        for attempt in range(1, max_solver_attempts + 1):
            try:
                if routing.route == RoutePath.SURGICAL_PATH:
                    solver_result = self._run_smt_solver(intent, adaptive_timeout)
                elif routing.route == RoutePath.DEEP_PATH:
                    solver_result = self._run_fast_solver(intent)
                else:
                    solver_result = None
                return solver_result
            except Exception as e:
                if attempt < max_solver_attempts:
                    delay = 0.5 * (2 ** (attempt - 1))
                    logger.warning(
                        "APAPlanner: Solver attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt, max_solver_attempts, e, delay
                    )
                    time.sleep(delay)
                else:
                    logger.warning("APAPlanner: Solver failed after %d attempts: %s", max_solver_attempts, e)
                    return None

    def _run_mcts_with_retry(self, intent, adaptive_sims, adaptive_timeout):
        """Run MCTS search with retry — broaden action set on failure.

        FIX (Phase 2): If MCTS returns None on first attempt (no actions
        found for the initial state), retry once with a broader action
        generator that includes a fallback 'QUICK_ANALYSIS' action.
        """
        mcts = MCTSPlanner(
            max_depth=self.MCTS_MAX_DEPTH,
            max_simulations=adaptive_sims,
            timeout_ms=adaptive_timeout
        )

        initial_state = {
            "target": intent.target,
            "op": intent.op,
            "goal": intent.goal,
            "depth": 0,
            "taken_actions": [],
        }

        best_action_hint = mcts.search(
            initial_state,
            action_generator=self._action_generator,
            reward_function=self._reward_function
        )

        # Store MCTS stats for ExecutionPlan
        self._last_mcts_simulations = mcts.simulations_run
        self._last_mcts_depth = mcts.depth_reached

        # If MCTS found no actions, retry with fallback
        if best_action_hint is None:
            logger.debug("APAPlanner: MCTS returned None — retrying with fallback action generator")
            mcts2 = MCTSPlanner(
                max_depth=max(2, self.MCTS_MAX_DEPTH - 1),
                max_simulations=max(10, adaptive_sims // 2),
                timeout_ms=max(2000, adaptive_timeout // 2)
            )

            def _broad_action_generator(state, depth):
                """Fallback generator that always provides at least one action."""
                actions = self._action_generator(state, depth)
                if not actions:
                    actions = ["QUICK_ANALYSIS"]
                return actions

            best_action_hint = mcts2.search(
                initial_state,
                action_generator=_broad_action_generator,
                reward_function=self._reward_function
            )

            # Update stats from retry
            self._last_mcts_simulations = mcts.simulations_run + mcts2.simulations_run
            self._last_mcts_depth = max(mcts.depth_reached, mcts2.depth_reached)

        return best_action_hint
