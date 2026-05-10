"""
TITAN OMNISCALE X - AutomationEngine (Workflow Automation for PYMEs)

Thin facade: all implementation lives in automation_parts sub-modules.
This module re-exports the public API for backward compatibility.

Sub-modules:
  - automation_parts.types:        TriggerType/ActionType enums, Trigger/Action/Workflow/WorkflowExecution dataclasses, constants
  - automation_parts.crud:         CoreCRUDMixin (CRUD operations for workflows)
  - automation_parts.execution:    ExecutionMixin (workflow execution logic)
  - automation_parts.project_gen:  ProjectGenMixin (project generation from workflows)
  - automation_parts.engine:       AutomationEngine class (inherits all mixins)

Public API:
  Classes:    AutomationEngine, TriggerType, ActionType, Trigger, Action, Workflow,
              WorkflowExecution
  Constants:  DB_DIR, DB_PATH, PROJECTS_DIR
"""

from .automation_parts import (
    DB_DIR,
    DB_PATH,
    PROJECTS_DIR,
    TriggerType,
    ActionType,
    Trigger,
    Action,
    Workflow,
    WorkflowExecution,
    AutomationEngine,
)

__all__ = [
    "DB_DIR",
    "DB_PATH",
    "PROJECTS_DIR",
    "TriggerType",
    "ActionType",
    "Trigger",
    "Action",
    "Workflow",
    "WorkflowExecution",
    "AutomationEngine",
]
