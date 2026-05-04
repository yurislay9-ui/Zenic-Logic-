"""
Partial Reasoning Manager - Response Contract for OpenAI-compatible partial responses.

Construye respuestas de Razonamiento Parcial como especifica el documento.
Incluye resumption_token y state para resume_from_partial().
"""

import gc
import json
import time
import uuid
import threading
import logging

from src.core.shared.db_initializer import get_projects_dir
from src.core.shared.contracts import OperationType, GoalType
from src.core.subtask_descriptor import SubtaskDescriptor

logger = logging.getLogger(__name__)


class PartialReasoningManager:
    """Manages partial reasoning responses and resumption tokens."""

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: TitanOrchestrator instance for accessing pipeline components.
        """
        self._orchestrator = orchestrator

    def build_partial_reasoning_response(self, intent, routing, plan, ast_analysis, trial, start_time,
                                          subtask_results=None, combined_code=""):
        """
        Construye la respuesta de Razonamiento Parcial como especifica el documento.
        (Gap 5 Fix): Now includes resumption_token and state for resume_from_partial().

        Devuelve un payload JSON con:
        - Mensaje explicativo del estado
        - tool_calls con zenith_mcts_plan para subdivision
        - resumption token para reanudar ejecucion parcial
        - Metadata del solver, K-Paths, y hash estructural
        """
        orch = self._orchestrator
        elapsed = int((time.time() - start_time) * 1000)
        k_path_eval = trial.paths_explored
        k_path_limit = orch.sandbox.k_path_limit

        # Generar subtareas para el tool_call
        subtasks = orch._abortive.generate_subtasks(intent, ast_analysis, plan)

        subtask_1 = "Levantamiento algoritmico de interfaces genericas de aislamiento (Mock Boundaries)."
        subtask_2 = "Despliegue quirurgico condicionado de la logica central evaluado independientemente."

        if len(subtasks) >= 2:
            subtask_1 = subtasks[0].message if isinstance(subtasks[0], SubtaskDescriptor) else str(subtasks[0])
            subtask_2 = subtasks[1].message if isinstance(subtasks[1], SubtaskDescriptor) else str(subtasks[1])

        # Construir el mensaje de razonamiento parcial
        solver_type = "Z3" if plan.solver_proof and plan.solver_proof.get("solver_type") == "Z3" else "SMT"
        content = (
            f"Analisis Estructural (Nivel 4 | Reflexion Sandbox): "
            f"La mutacion exigida cruza el umbral de seguridad matematica "
            f"(Demostracion interrumpida por {solver_type} Solver timeout). "
            f"El mapeo profundo AST infiere que este injerto impacta sobre "
            f"{k_path_eval} rutas perimetricas criticas "
            f"(K-Paths eval={k_path_eval} -> Aborted limit={k_path_limit}). "
            f"Para salvaguardar la inviolabilidad del codigo y prevenir una regresion silente, "
            f"procedo a subdividir la instruccion genesis en dos operaciones de encapsulamiento."
        )

        # Gap 5: Generate resumption token and store state for later resume
        resumption_token = uuid.uuid4().hex
        resumption_state = {
            "token": resumption_token,
            "subtasks": subtasks,
            "subtask_results": subtask_results or [],
            "original_intent": {
                "op": intent.op,
                "target": intent.target,
                "goal": intent.goal,
                "language": intent.language,
                "raw_code": intent.raw_code,
                "scrap_query": intent.scrap_query,
                "confidence": intent.confidence,
            },
            "partial_code": combined_code,
            "created_at": time.time(),
        }
        with orch._resumptions_lock:
            orch._pending_resumptions[resumption_token] = resumption_state

        # Clean up old resumptions: TTL-based (30 min) + count-based (keep last 100)
        _RESUMPTION_TTL_SECONDS = 30 * 60  # 30 minutes
        with orch._resumptions_lock:
            # Remove entries older than TTL
            now = time.time()
            expired_keys = [
                k for k, v in orch._pending_resumptions.items()
                if now - v.get("created_at", 0) > _RESUMPTION_TTL_SECONDS
            ]
            for k in expired_keys:
                del orch._pending_resumptions[k]

            # Also enforce max count
            if len(orch._pending_resumptions) > 100:
                oldest_keys = sorted(
                    orch._pending_resumptions.keys(),
                    key=lambda k: orch._pending_resumptions[k].get("created_at", 0)
                )
                for k in oldest_keys[:len(oldest_keys) - 100]:
                    del orch._pending_resumptions[k]

        return {
            "status": "PARTIAL_REASONING",
            "code": combined_code,
            "hash": "N/A",
            "error": trial.error_message,
            "processing_time_ms": elapsed,
            "route": routing.route,
            "criticality": routing.criticality,
            "solver_status": plan.solver_status,
            "ast_analysis": ast_analysis,
            "explanations": [content],
            "partial_reasoning": True,
            # OpenAI-compatible partial reasoning payload
            "partial_reasoning_payload": {
                "content": content,
                "tool_calls": [
                    {
                        "id": f"call_zenith_mcts_fragmentation_{uuid.uuid4().hex[:4]}",
                        "type": "function",
                        "function": {
                            "name": "zenith_mcts_plan",
                            "arguments": json.dumps({
                                "subtask_1_isolation": subtask_1,
                                "subtask_2_mutation": subtask_2,
                            })
                        }
                    }
                ],
                "finish_reason": "tool_calls",
            },
            # Gap 5: Resumption data for partial reasoning
            "resumption": {
                "token": resumption_token,
                "subtasks": subtasks,
                "original_intent": {
                    "op": intent.op,
                    "target": intent.target,
                    "goal": intent.goal,
                    "language": intent.language,
                },
                "partial_code": combined_code,
                "completed_subtasks": sum(
                    1 for r in (subtask_results or [])
                    if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                ),
                "total_subtasks": len(subtask_results or []),
            },
            "usage_metadata": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                f"zenith_{solver_type.lower()}_compute_time_ms": plan.solver_proof.get("timeout_ms", 0) if plan.solver_proof else 0,
                "zenith_k_path_eval": k_path_eval,
                "structural_theorem_hash": "null_overload",
            },
            "warnings": trial.warnings,
            "paths_explored": trial.paths_explored,
            "paths_pruned": trial.paths_pruned,
        }

    async def resume_from_partial(self, resumption_token, subtask_index=None):
        """
        Resume execution from a partial reasoning state (Gap 5 Fix).

        Takes a resumption_token from a previous PARTIAL_REASONING response
        and re-executes the remaining subtasks that haven't succeeded yet,
        then combines results and returns the final output.

        MEJORA: Now uses isolated workspaces and preserves SubtaskDescriptor
        context from parent pipeline (solver insights, MCTS hints, violations).

        Args:
            resumption_token: The token from a previous PARTIAL_REASONING response
            subtask_index: If provided, only re-execute this specific subtask index.
                          If None, re-execute all non-successful subtasks.

        Returns:
            dict with the same format as execute() or handle_abortive_protocol()
        """
        start_time = time.time()
        orch = self._orchestrator

        # Lookup resumption state
        with orch._resumptions_lock:
            state = orch._pending_resumptions.get(resumption_token)
            if not state:
                return {
                    "status": "ERROR",
                    "code": "",
                    "hash": "N/A",
                    "error": f"Invalid or expired resumption token: {resumption_token[:8]}...",
                    "processing_time_ms": 0,
                }

        original_intent_data = state["original_intent"]
        previous_results = state.get("subtask_results", [])
        partial_code = state.get("partial_code", "")
        subtasks_raw = state.get("subtasks", [])

        # Reconstruct SubtaskDescriptors from serialized state
        subtasks = []
        for st in subtasks_raw:
            if isinstance(st, SubtaskDescriptor):
                subtasks.append(st)
            elif isinstance(st, dict):
                # Deserialize from dict (e.g., from JSON)
                subtasks.append(SubtaskDescriptor(
                    message=st.get("message", ""),
                    target=st.get("target", ""),
                    operation=st.get("operation", ""),
                    goal=st.get("goal", ""),
                    solver_insights=st.get("solver_insights", {}),
                    mcts_hints=st.get("mcts_hints", []),
                    parent_violations=st.get("parent_violations", []),
                    parent_context=st.get("parent_context", {}),
                    depth=st.get("depth", 0),
                ))
            elif isinstance(st, str):
                # Legacy string subtask
                subtasks.append(SubtaskDescriptor(message=st))
            else:
                subtasks.append(SubtaskDescriptor(message=str(st)))

        # Reconstruct intent
        from src.core.shared.contracts import IntentPayload
        intent = IntentPayload(
            op=original_intent_data.get("op", OperationType.SEARCH),
            target=original_intent_data.get("target", "unknown"),
            goal=original_intent_data.get("goal", GoalType.FEATURE_ADD),
            language=original_intent_data.get("language", "python"),
            raw_code=original_intent_data.get("raw_code", ""),
            scrap_query=original_intent_data.get("scrap_query", ""),
            confidence=original_intent_data.get("confidence", 0.0),
        )

        # Determine which subtasks to re-execute
        if subtask_index is not None:
            # Re-execute only the specified subtask
            indices_to_run = [subtask_index] if 0 <= subtask_index < len(subtasks) else []
        else:
            # Re-execute all subtasks that didn't succeed
            indices_to_run = []
            for i, result in enumerate(previous_results):
                if isinstance(result, dict) and result.get("status") not in ("SUCCESS", "CACHED"):
                    indices_to_run.append(i)
            # Also include any subtasks beyond previous_results length
            for i in range(len(previous_results), len(subtasks)):
                indices_to_run.append(i)

        if not indices_to_run:
            # All subtasks already succeeded; just combine and validate
            combined_code = partial_code if partial_code else orch._abortive.merge_subtask_results(previous_results, intent.language)
            if combined_code:
                # Use isolated workspace for resume validation
                resume_workspace = orch._isolation_manager.create_workspace(ttl_seconds=120)
                p_dir = str(get_projects_dir())
                orch.ledger.snapshot(intent.target, p_dir, workspace=resume_workspace)
                trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)
                if trial.status == "PASS":
                    node = orch.ledger.commit(intent.target, combined_code, p_dir, workspace=resume_workspace)
                    orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
                    with orch._resumptions_lock:
                        orch._pending_resumptions.pop(resumption_token, None)
                    elapsed = int((time.time() - start_time) * 1000)
                    return {
                        "status": "SUCCESS", "code": combined_code,
                        "hash": node.hash_sha256[:12], "error": "",
                        "processing_time_ms": elapsed,
                        "explanations": ["Resumed partial reasoning: all subtasks completed successfully."],
                    }
                else:
                    orch.ledger.rollback(intent.target, p_dir, workspace=resume_workspace)
                    orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
            else:
                # No combined code — no workspace was created in this branch
                pass
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "status": "PARTIAL_REASONING",
                "code": combined_code,
                "hash": "N/A",
                "error": "Resumed but combined result still fails validation",
                "processing_time_ms": elapsed,
            }

        # Execute remaining subtasks with enriched context
        new_results = list(previous_results)  # Copy existing results
        # Extend list to accommodate indices beyond current length
        while len(new_results) < len(subtasks):
            new_results.append(None)
        for idx in indices_to_run:
            if idx < len(subtasks):
                try:
                    result = await orch._abortive.execute_subtask(subtasks[idx], depth=0, max_depth=2)
                    new_results[idx] = result
                except Exception as e:
                    new_results[idx] = {
                        "status": "ERROR",
                        "code": "",
                        "message": str(e),
                    }

        gc.collect()

        # Combine all results (including previously successful ones)
        combined_code = orch._abortive.merge_subtask_results(new_results, intent.language)

        # Use isolated workspace for combined result validation
        resume_workspace = orch._isolation_manager.create_workspace(ttl_seconds=180)

        if combined_code:
            p_dir = str(get_projects_dir())
            orch.ledger.snapshot(intent.target, p_dir, workspace=resume_workspace)
            trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)

            if trial.status == "PASS" and combined_code:
                node = orch.ledger.commit(intent.target, combined_code, p_dir, workspace=resume_workspace)
                orch.cache.save(intent, "PROVEN",
                              {"h": node.hash_sha256[:8], "code": combined_code},
                              combined_code, intent.language)
                elapsed = int((time.time() - start_time) * 1000)

                # Remove resumption state since we succeeded
                with orch._resumptions_lock:
                    orch._pending_resumptions.pop(resumption_token, None)
                orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)

                return {
                    "status": "SUCCESS",
                    "code": combined_code,
                    "hash": node.hash_sha256[:12],
                    "error": "",
                    "processing_time_ms": elapsed,
                    "subtasks": new_results,
                    "explanations": [
                        f"Resumed partial reasoning: {len(indices_to_run)} subtasks re-executed.",
                        f"Combined result passes sandbox validation.",
                    ],
                    "warnings": trial.warnings,
                    "metrics": trial.metrics,
                    "paths_explored": trial.paths_explored,
                    "paths_pruned": trial.paths_pruned,
                }
            else:
                orch.ledger.rollback(intent.target, p_dir, workspace=resume_workspace)
                orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
                # Update the resumption state with new results
                with orch._resumptions_lock:
                    orch._pending_resumptions[resumption_token]["subtask_results"] = new_results
                    orch._pending_resumptions[resumption_token]["partial_code"] = combined_code
                elapsed = int((time.time() - start_time) * 1000)
                return {
                    "status": "PARTIAL_REASONING",
                    "code": combined_code,
                    "hash": "N/A",
                    "error": trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed after resume",
                    "processing_time_ms": elapsed,
                    "subtasks": new_results,
                    "resumption": {
                        "token": resumption_token,
                        "completed_subtasks": sum(
                            1 for r in new_results
                            if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                        ),
                        "total_subtasks": len(new_results),
                    },
                    "explanations": [
                        f"Resumed partial reasoning: {len(indices_to_run)} subtasks re-executed.",
                        f"Combined result still fails sandbox validation.",
                    ],
                    "warnings": trial.warnings if hasattr(trial, 'warnings') else [],
                }

        elapsed = int((time.time() - start_time) * 1000)
        orch._isolation_manager.release_workspace(resume_workspace.sandbox_id)
        return {
            "status": "PARTIAL_REASONING",
            "code": "",
            "hash": "N/A",
            "error": "No code produced after resumption",
            "processing_time_ms": elapsed,
            "subtasks": new_results,
            "resumption": {
                "token": resumption_token,
                "completed_subtasks": sum(
                    1 for r in new_results
                    if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                ),
                "total_subtasks": len(new_results),
            },
        }
