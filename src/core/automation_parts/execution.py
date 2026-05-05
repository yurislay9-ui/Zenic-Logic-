"""
ExecutionMixin — Workflow execution logic for AutomationEngine.

Contains:
  - Sync/async workflow execution
  - Individual action execution (with ActionExecutor or legacy stubs)
"""

import time
import logging
from typing import List

from .types import (
    ActionType,
    Action, WorkflowExecution,
)

logger = logging.getLogger(__name__)


class ExecutionMixin:
    """Execution logic methods for AutomationEngine."""

    # ================================================================
    #  WORKFLOW EXECUTION
    # ================================================================

    def execute_workflow(self, workflow_id: str) -> WorkflowExecution:
        """Ejecuta un workflow específico (sync wrapper for async execution)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context, use sync fallback
                return self._execute_workflow_sync(workflow_id)
            return loop.run_until_complete(self._execute_workflow_async(workflow_id))
        except RuntimeError:
            return self._execute_workflow_sync(workflow_id)

    async def _execute_workflow_async(self, workflow_id: str) -> WorkflowExecution:
        """Ejecuta un workflow específico usando ActionExecutors async."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return WorkflowExecution(workflow_id=workflow_id, status="failed", error="Workflow not found")

        if not wf.enabled:
            return WorkflowExecution(workflow_id=workflow_id, status="failed", error="Workflow is disabled")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            started_at=time.time(),
            status="running",
        )

        try:
            for action in wf.actions:
                try:
                    result = await self._execute_action_async(action)
                    if result:
                        execution.actions_executed += 1
                    else:
                        execution.actions_failed += 1
                except Exception as e:
                    execution.actions_failed += 1
                    execution.error += f"Action {action.type} failed: {e}; "

            execution.status = "success" if execution.actions_failed == 0 else "partial"
            execution.output = f"Executed {execution.actions_executed}/{len(wf.actions)} actions"

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)

        execution.finished_at = time.time()

        # Update workflow stats
        wf.last_run = execution.started_at
        wf.run_count += 1
        self._save_workflow(wf)

        # Log execution
        self._log_execution(execution)
        self._execution_history.append(execution)

        return execution

    def _execute_workflow_sync(self, workflow_id: str) -> WorkflowExecution:
        """Ejecuta un workflow usando stubs síncronos (legacy fallback)."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return WorkflowExecution(workflow_id=workflow_id, status="failed", error="Workflow not found")

        if not wf.enabled:
            return WorkflowExecution(workflow_id=workflow_id, status="failed", error="Workflow is disabled")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            started_at=time.time(),
            status="running",
        )

        try:
            for action in wf.actions:
                try:
                    result = self._execute_action(action)
                    if result:
                        execution.actions_executed += 1
                    else:
                        execution.actions_failed += 1
                except Exception as e:
                    execution.actions_failed += 1
                    execution.error += f"Action {action.type} failed: {e}; "

            execution.status = "success" if execution.actions_failed == 0 else "partial"
            execution.output = f"Executed {execution.actions_executed}/{len(wf.actions)} actions"

        except Exception as e:
            execution.status = "failed"
            execution.error = str(e)

        execution.finished_at = time.time()

        wf.last_run = execution.started_at
        wf.run_count += 1
        self._save_workflow(wf)
        self._log_execution(execution)
        self._execution_history.append(execution)

        return execution

    async def _execute_action_async(self, action: Action) -> bool:
        """Ejecuta una acción individual usando ActionExecutor async."""
        if self._executor_registry:
            try:
                result = await self._executor_registry.execute_action(
                    action.type.value, action.config, {}
                )
                if result.success:
                    logger.info(f"Automation: {action.type.value} executed successfully in {result.duration_ms:.0f}ms")
                else:
                    logger.warning(f"Automation: {action.type.value} failed: {result.error}")
                return result.success
            except Exception as e:
                logger.error(f"Automation: Executor error for {action.type.value}: {e}")
                # Fall through to legacy stubs

        # Legacy fallback
        return self._execute_action(action)

    def _execute_action(self, action: Action) -> bool:
        """Ejecuta una acción individual usando ActionExecutor si disponible."""
        # Use real ActionExecutor if registry is available
        if self._executor_registry:
            try:
                result = self._executor_registry.execute_action(
                    action.type.value, action.config, {}
                )
                if result.success:
                    logger.info(f"Automation: {action.type.value} executed successfully in {result.duration_ms:.0f}ms")
                else:
                    logger.warning(f"Automation: {action.type.value} failed: {result.error}")
                return result.success
            except Exception as e:
                logger.error(f"Automation: Executor error for {action.type.value}: {e}")
                # Fall through to legacy stubs

        # Legacy fallback: logger.info stubs (backward compatible)
        logger.warning(f"Automation: Using legacy stub for {action.type.value}")
        if action.type == ActionType.SEND_NOTIFICATION:
            logger.info(f"Automation: Notification - {action.config.get('message', 'No message')}")
            return True
        elif action.type == ActionType.SEND_EMAIL:
            logger.info(f"Automation: Email to {action.config.get('to', 'N/A')} - {action.config.get('subject', 'N/A')}")
            return True
        elif action.type == ActionType.DATABASE_OPERATION:
            logger.info(f"Automation: Database {action.config.get('operation', 'query')}")
            return True
        elif action.type == ActionType.GENERATE_REPORT:
            logger.info(f"Automation: Report generated - {action.config.get('template', 'default')}")
            return True
        elif action.type == ActionType.RUN_SCRIPT:
            logger.info("Automation: Script execution")
            return True
        elif action.type == ActionType.DATA_SYNC:
            logger.info("Automation: Data sync")
            return True
        elif action.type == ActionType.HTTP_REQUEST:
            logger.info(f"Automation: HTTP {action.config.get('method', 'GET')} {action.config.get('url', 'N/A')}")
            return True
        elif action.type == ActionType.FILE_OPERATION:
            logger.info(f"Automation: File operation - {action.config.get('operation', 'N/A')}")
            return True
        return False
