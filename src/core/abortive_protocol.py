"""
Abortive Protocol - Auto-subdivision when solver timeout.

Si el solver hace timeout (15s), el sistema:
1. Hace rollback al estado pristino anterior
2. Subdivide automaticamente la tarea en unidades logicas
3. EJECUTA cada subtask a traves del pipeline completo (no solo plan)
4. Combina los resultados de cada subtask
5. Valida el resultado combinado en sandbox
6. Si pasa -> commit SUCCESS; si subtask timeout -> subdividir recursivamente (max depth 2)
7. Si la combinacion falla -> devolver Razonamiento Parcial con token de resumption
"""

import gc
import logging

from src.config.loader import get_solver_timeout_ms
from src.core.shared.db_initializer import get_projects_dir
from src.core.shared.contracts import OperationType
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.step_dispatcher import StepDispatcher

logger = logging.getLogger(__name__)

# === Extracted Constants (previously hardcoded inline) ===
MAX_SUBTASKS = 5                   # Max subtasks for abortive protocol
MAX_DEEP_SUBTASKS = 3              # Max deep subtasks for recursive subdivision
MAX_ABORTIVE_DEPTH = 2             # Max recursion depth for abortive protocol
ABORTIVE_SANDBOX_TTL_MULTIPLIER = 5 # Abortive workspace TTL multiplier
ABORTIVE_SANDBOX_TTL_MIN = 300      # Minimum abortive workspace TTL
SUBTASK_SANDBOX_TTL_MULTIPLIER = 2  # Subtask workspace TTL multiplier
SUBTASK_SANDBOX_TTL_MIN = 60       # Minimum subtask workspace TTL


class AbortiveProtocol:
    """Handles the Abortive Protocol for auto-subdivision when solver timeout."""

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: BaseOrchestrator (or subclass) instance for accessing pipeline components.
        """
        self._orchestrator = orchestrator
        self._step_dispatcher = StepDispatcher(orchestrator)

    async def handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        """
        Protocolo Abortivo del documento de arquitectura (Gap 4 Fix):

        Si el solver hace timeout (15s), el sistema:
        1. Hace rollback al estado pristino anterior
        2. Subdivide automaticamente la tarea en unidades logicas
        3. EJECUTA cada subtask a traves del pipeline completo (no solo plan)
        4. Combina los resultados de cada subtask
        5. Valida el resultado combinado en sandbox
        6. Si pasa -> commit SUCCESS; si subtask timeout -> subdividir recursivamente (max depth 2)
        7. Si la combinacion falla -> devolver Razonamiento Parcial con token de resumption
        """
        import time

        orch = self._orchestrator
        logger.warning("PROTOCOLO ABORTIVO activado para: %s", intent.target)

        # Crear workspace AISLADO para el protocolo abortivo
        abortive_workspace = orch._isolation_manager.create_workspace(
            ttl_seconds=max(orch.sandbox.timeout_seconds * ABORTIVE_SANDBOX_TTL_MULTIPLIER, ABORTIVE_SANDBOX_TTL_MIN)
        )

        # Rollback
        p_dir = str(get_projects_dir())
        orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)

        solver_timeout = plan.solver_proof.get("timeout_ms", get_solver_timeout_ms(orch.settings)) if plan.solver_proof else get_solver_timeout_ms(orch.settings)

        # Generar subtareas automaticamente (limit to 5 for memory safety)
        subtasks = self.generate_subtasks(intent, ast_analysis, plan)[:MAX_SUBTASKS]

        # EJECUTAR cada subtask a traves del pipeline completo
        subtask_results = []
        for i, subtask_msg in enumerate(subtasks):
            try:
                result = await self.execute_subtask(subtask_msg, depth=0, max_depth=MAX_ABORTIVE_DEPTH)
                subtask_results.append(result)
            except Exception as e:
                logger.error("Subtask %d failed: %s", i, e)
                subtask_results.append({
                    "subtask": subtask_msg,
                    "status": "ERROR",
                    "code": "",
                    "message": str(e),
                })

        # Recoger gc tras operaciones pesadas
        gc.collect()

        # Combinar resultados de subtasks
        combined_code = self.merge_subtask_results(subtask_results, intent.language)

        if combined_code:
            # Validar resultado combinado en sandbox
            orch.ledger.snapshot(intent.target, p_dir, workspace=abortive_workspace)
            trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)

            if trial.status == "PASS" and combined_code:
                # Commit resultado combinado en workspace aislado
                node = orch.ledger.commit(intent.target, combined_code, p_dir,
                                           workspace=abortive_workspace)
                # Release sandbox workspace after successful commit
                try:
                    orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                except Exception:
                    pass
                orch.cache.save(intent, "PROVEN",
                              {"h": node.hash_sha256[:8], "code": combined_code},
                              combined_code, intent.language)
                elapsed = int((time.time() - start_time) * 1000)
                orch._analysis.log_request(intent, "ABORTIVE_SUCCESS", elapsed,
                                solver_status="TIMEOUT_SUBDIVIDE_REQUIRED")
                return {
                    "status": "SUCCESS", "code": combined_code,
                    "hash": node.hash_sha256[:12], "error": "",
                    "processing_time_ms": elapsed,
                    "route": routing.route,
                    "criticality": routing.criticality,
                    "solver_status": "ABORTIVE_RESOLVED",
                    "solver_proof": plan.solver_proof,
                    "mcts_simulations": plan.mcts_simulations,
                    "mcts_depth_reached": plan.mcts_depth_reached,
                    "ast_analysis": ast_analysis,
                    "explanations": [
                        f"Protocolo Abortivo: Solver timeout ({solver_timeout}ms) para '{intent.target}'.",
                        f"Tarea subdividida y ejecutada en {len(subtasks)} subtareas.",
                        f"Resultado combinado valido (sandbox PASS).",
                    ],
                    "subtasks": subtask_results,
                    "warnings": trial.warnings,
                    "metrics": trial.metrics,
                    "paths_explored": trial.paths_explored,
                    "paths_pruned": trial.paths_pruned,
                }
            elif trial.status == "FAIL_K_PATH":
                # K-Path exceeded -> rollback + partial reasoning with resumption
                orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)
                orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                elapsed = int((time.time() - start_time) * 1000)
                return orch._partial_reasoning.build_partial_reasoning_response(
                    intent, routing, plan, ast_analysis, trial, start_time,
                    subtask_results=subtask_results, combined_code=combined_code
                )
            else:
                # Other failure -> rollback + partial reasoning with resumption
                orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)
                orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                elapsed = int((time.time() - start_time) * 1000)
                # Build a synthetic SandboxResult for the partial reasoning response
                from src.core.shared.contracts import SandboxResult
                trial_for_partial = SandboxResult(
                    status="FAIL",
                    error_message=trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed",
                    warnings=trial.warnings if hasattr(trial, 'warnings') else [],
                    paths_explored=trial.paths_explored if hasattr(trial, 'paths_explored') else 0,
                    paths_pruned=trial.paths_pruned if hasattr(trial, 'paths_pruned') else 0,
                )
                return orch._partial_reasoning.build_partial_reasoning_response(
                    intent, routing, plan, ast_analysis, trial_for_partial, start_time,
                    subtask_results=subtask_results, combined_code=combined_code
                )

        # No combined code could be produced — release workspace before returning
        orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
        elapsed = int((time.time() - start_time) * 1000)
        from src.core.shared.contracts import SandboxResult
        no_code_trial = SandboxResult(
            status="FAIL",
            error_message="No code produced by any subtask",
            warnings=[],
            paths_explored=0,
            paths_pruned=0,
        )
        return orch._partial_reasoning.build_partial_reasoning_response(
            intent, routing, plan, ast_analysis, no_code_trial, start_time,
            subtask_results=subtask_results, combined_code=""
        )

    def generate_subtasks(self, intent, ast_analysis, plan=None):
        """
        Genera subtareas enriquecidas (SubtaskDescriptor) a partir de una tarea
        que excedio el presupuesto del solver.
        """
        orch = self._orchestrator
        # Extract parent pipeline context
        solver_insights = orch._code_gen.extract_solver_insights(plan.solver_proof) if plan else {}
        mcts_hints = []
        if plan and plan.steps:
            mcts_hints = [s.action for s in plan.steps[:3]]

        parent_violations = []
        if plan and plan.solver_proof and isinstance(plan.solver_proof, dict):
            for key in ["null_safety", "type_safety", "invariant_safety"]:
                sub_result = plan.solver_proof.get(key)
                if isinstance(sub_result, dict) and not sub_result.get("verified", True):
                    parent_violations.append(f"{key}: {sub_result.get('proof', 'violation detected')}")

        parent_context = {
            "ast_analysis": ast_analysis,
            "solver_status": plan.solver_status if plan else "UNKNOWN",
            "mcts_simulations": plan.mcts_simulations if plan else 0,
            "mcts_depth": plan.mcts_depth_reached if plan else 0,
        }

        subtasks = []

        if intent.raw_code:
            function_names = ast_analysis.get("function_names", [])
            if function_names:
                for fn_name in function_names:
                    subtasks.append(SubtaskDescriptor(
                        message=f"{intent.op.lower()} function {fn_name} in {intent.target} "
                                f"with goal {intent.goal}",
                        target=fn_name,
                        operation=intent.op,
                        goal=intent.goal,
                        solver_insights=solver_insights,
                        mcts_hints=mcts_hints,
                        parent_violations=parent_violations,
                        parent_context=parent_context,
                        depth=0,
                    ))
            else:
                subtasks.append(SubtaskDescriptor(
                    message=f"analyze structure of {intent.target}",
                    target=intent.target,
                    operation="ANALYZE",
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"{intent.op.lower()} {intent.target} with goal {intent.goal}",
                    target=intent.target,
                    operation=intent.op,
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
        else:
            if intent.op == OperationType.CREATE:
                subtasks.append(SubtaskDescriptor(
                    message=f"create interfaces and types for {intent.target}",
                    target=intent.target,
                    operation="CREATE",
                    goal="INTERFACE_DEFINITION",
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"implement core logic for {intent.target}",
                    target=intent.target,
                    operation="CREATE",
                    goal="IMPLEMENTATION",
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"add error handling and validation for {intent.target}",
                    target=intent.target,
                    operation="CREATE",
                    goal="SECURITY_HARDEN",
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
            elif intent.op in [OperationType.REFACTOR, OperationType.OPTIMIZE]:
                subtasks.append(SubtaskDescriptor(
                    message=f"analyze patterns in {intent.target}",
                    target=intent.target,
                    operation="ANALYZE",
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"apply optimizations to {intent.target}",
                    target=intent.target,
                    operation=intent.op,
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
            elif intent.op == OperationType.DEBUG:
                subtasks.append(SubtaskDescriptor(
                    message=f"trace execution in {intent.target}",
                    target=intent.target,
                    operation="DEBUG",
                    goal="TRACE",
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"apply minimal fix to {intent.target}",
                    target=intent.target,
                    operation="DEBUG",
                    goal="BUG_FIX",
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
            else:
                subtasks.append(SubtaskDescriptor(
                    message=f"analyze {intent.target} part 1",
                    target=intent.target,
                    operation="ANALYZE",
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))
                subtasks.append(SubtaskDescriptor(
                    message=f"analyze {intent.target} part 2",
                    target=intent.target,
                    operation="ANALYZE",
                    goal=intent.goal,
                    solver_insights=solver_insights,
                    mcts_hints=mcts_hints,
                    parent_violations=parent_violations,
                    parent_context=parent_context,
                    depth=0,
                ))

        if not subtasks:
            subtasks.append(SubtaskDescriptor(
                message=f"process {intent.target}",
                target=intent.target,
                operation=intent.op,
                goal=intent.goal,
                solver_insights=solver_insights,
                mcts_hints=mcts_hints,
                parent_violations=parent_violations,
                parent_context=parent_context,
                depth=0,
            ))

        return subtasks

    async def execute_subtask(self, subtask, depth=0, max_depth=2):
        """
        Execute a single subtask through the full pipeline.

        Accepts both SubtaskDescriptor (enriched) and str (legacy).
        Uses StepDispatcher for unified step execution instead of
        duplicating the dispatch logic.
        """
        import time

        orch = self._orchestrator

        # Handle both SubtaskDescriptor and str (backward compatible)
        if isinstance(subtask, SubtaskDescriptor):
            subtask_msg = subtask.message
            subtask_context = subtask
            depth = subtask.depth if subtask.depth > 0 else depth
        else:
            subtask_msg = str(subtask)
            subtask_context = None

        if depth >= max_depth:
            return {"status": "MAX_DEPTH_REACHED", "code": "", "message": subtask_msg}

        try:
            sub_intent = orch.parser.parse(subtask_msg)
        except Exception as e:
            return {"status": "ERROR", "code": "", "message": f"Parse error: {e}"}

        sub_ast = {}
        if sub_intent.raw_code:
            sub_ast = orch.ast_engine.analyze_structure(sub_intent.raw_code, sub_intent.language)

        # Cache check
        cache_hit = orch.cache.lookup(sub_intent, sub_intent.raw_code, sub_intent.language)
        if cache_hit:
            return {"status": "CACHED", "code": cache_hit["data"].get("code", "")}

        sub_routing = orch.router.route(sub_intent)
        sub_plan = orch.planner.generate_plan(sub_routing)

        if sub_plan.solver_status == "TIMEOUT_SUBDIVIDE_REQUIRED":
            # Recursive subdivision
            deeper_subtasks = self.generate_subtasks(sub_intent, sub_ast, sub_plan)
            results = []
            for ds in deeper_subtasks[:MAX_DEEP_SUBTASKS]:
                result = await self.execute_subtask(ds, depth + 1, max_depth)
                results.append(result)
            combined = self.merge_subtask_results(results, sub_intent.language)
            return combined

        # Execute plan steps using StepDispatcher (unified logic)
        code = sub_intent.raw_code or ""
        explanations = []
        lang = sub_intent.language

        result_code, code, explanations = await self._step_dispatcher.execute_plan_steps(
            sub_plan, sub_intent, code, explanations, lang, sub_ast,
        )

        final_code = result_code if result_code else code

        # Sandbox validation con workspace AISLADO para subtask
        subtask_workspace = orch._isolation_manager.create_workspace(
            ttl_seconds=max(orch.sandbox.timeout_seconds * SUBTASK_SANDBOX_TTL_MULTIPLIER, SUBTASK_SANDBOX_TTL_MIN)
        )
        p_dir = str(get_projects_dir())
        orch.ledger.snapshot(sub_intent.target, p_dir, workspace=subtask_workspace)
        trial = await orch.sandbox.validate_code(final_code, lang, sub_intent.target)

        if trial.status == "PASS" and final_code:
            node = orch.ledger.commit(sub_intent.target, final_code, p_dir,
                                       workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            orch.cache.save(sub_intent, "PROVEN",
                          {"h": node.hash_sha256[:8], "code": final_code},
                          final_code, lang)
            return {"status": "SUCCESS", "code": final_code, "hash": node.hash_sha256[:12],
                    "explanations": explanations}
        elif trial.status == "FAIL_K_PATH":
            orch.ledger.rollback(sub_intent.target, p_dir, workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            return {"status": "K_PATH_EXCEEDED", "code": final_code,
                    "error": trial.error_message, "explanations": explanations}
        else:
            orch.ledger.rollback(sub_intent.target, p_dir, workspace=subtask_workspace)
            orch._isolation_manager.release_workspace(subtask_workspace.sandbox_id)
            return {"status": "ROLLBACK", "code": final_code,
                    "error": trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed",
                    "explanations": explanations}

    def merge_subtask_results(self, subtask_results, language="python"):
        """
        Combine code from multiple subtasks into one coherent module (Gap 4 Fix).
        """
        code_parts = []
        for result in subtask_results:
            if isinstance(result, dict):
                code = result.get("code", "")
                if code and result.get("status") not in ["ERROR", "MAX_DEPTH_REACHED"]:
                    code_parts.append(code)

        if not code_parts:
            return ""

        if language == "python":
            return self.merge_python_code(code_parts)
        elif language == "kotlin":
            return self.merge_block_code(code_parts, "//", "package")
        elif language == "go":
            return self.merge_go_code(code_parts)
        elif language == "javascript":
            return self.merge_block_code(code_parts, "//", None)
        return self.merge_python_code(code_parts)

    @staticmethod
    def merge_python_code(code_parts):
        """Merge Python code blocks: collect imports, deduplicate, then concatenate bodies."""
        all_imports = []
        all_bodies = []

        for code in code_parts:
            lines = code.split('\n')
            imports = []
            body = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(('import ', 'from ')) and not stripped.startswith('#'):
                    imports.append(stripped)
                else:
                    body.append(line)

            all_imports.extend(imports)
            all_bodies.append('\n'.join(body))

        seen_imports = set()
        unique_imports = []
        for imp in all_imports:
            if imp not in seen_imports:
                seen_imports.add(imp)
                unique_imports.append(imp)

        result = '\n'.join(unique_imports)
        if unique_imports:
            result += '\n\n'
        result += '\n\n'.join(all_bodies)
        return result

    @staticmethod
    def merge_go_code(code_parts):
        """Merge Go code: collect package + imports, then concatenate functions."""
        all_imports = []
        all_bodies = []
        package_line = "package main"

        for code in code_parts:
            lines = code.split('\n')
            in_import_block = False
            import_lines = []
            body_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('package '):
                    package_line = stripped
                    continue
                if stripped == 'import (' or stripped.startswith('import '):
                    if stripped.startswith('import '):
                        import_lines.append(stripped.replace('import ', '').strip('"'))
                    in_import_block = stripped == 'import ('
                    continue
                if in_import_block:
                    if stripped == ')':
                        in_import_block = False
                    else:
                        import_lines.append(stripped.strip('"'))
                    continue
                body_lines.append(line)

            all_imports.extend(import_lines)
            all_bodies.append('\n'.join(body_lines))

        seen = set()
        unique_imports = [i for i in all_imports if i not in seen and not seen.add(i)]

        result = package_line + '\n\n'
        if unique_imports:
            result += 'import (\n'
            for imp in unique_imports:
                result += f'\t"{imp}"\n'
            result += ')\n\n'
        result += '\n\n'.join(all_bodies)
        return result

    @staticmethod
    def merge_block_code(code_parts, comment_prefix, skip_prefix):
        """Generic merge for C-style languages: skip duplicate headers."""
        seen_headers = set()
        all_lines = []
        for code in code_parts:
            lines = code.split('\n')
            for line in lines:
                stripped = line.strip()
                if skip_prefix and stripped.startswith(skip_prefix):
                    if stripped not in seen_headers:
                        seen_headers.add(stripped)
                        all_lines.append(line)
                    continue
                all_lines.append(line)
            all_lines.append('')
        return '\n'.join(all_lines)
