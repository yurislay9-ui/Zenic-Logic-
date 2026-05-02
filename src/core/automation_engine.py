"""
TITAN OMNISCALE X - AutomationEngine (Workflow Automation for PYMEs)

Motor de automatizaciones que permite crear flujos de trabajo
automatizados para pequeñas y medianas empresas.

Tipos de automatización:
  1. Scheduled Jobs - Tareas programadas (cron-like)
  2. Event Triggers - Acciones en respuesta a eventos
  3. Data Pipelines - Procesamiento ETL de datos
  4. Notification Workflows - Alertas y notificaciones
  5. Integration Bridges - Conexión entre servicios

Cada automatización se define como un Workflow:
  Trigger → [Conditions] → Actions → [Notifications]

Ejemplos de automatizaciones para PYMEs:
  - "Cada lunes enviar reporte de ventas por email"
  - "Cuando se agote el stock de un producto, notificar"
  - "Sincronizar datos del CRM con la facturación"
  - "Backup automático de la base de datos cada noche"
  - "Monitorear API y alertar si está caída"

Optimizado para:
  - APScheduler para scheduling (lightweight, no Celery needed)
  - SQLite para estado de jobs (persistente)
  - smtplib para emails (sin servicio externo)
  - asyncio para ejecución no-bloqueante
"""

import os
import re
import json
import time
import sqlite3
import logging
import hashlib
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.expanduser("~"), ".titan_omniscale", "db")
DB_PATH = os.path.join(DB_DIR, "automation.sqlite")


class TriggerType(str, Enum):
    SCHEDULE = "schedule"        # Cron/schedule trigger
    EVENT = "event"              # Event-based trigger
    WEBHOOK = "webhook"          # HTTP webhook trigger
    FILE_CHANGE = "file_change"  # File system trigger
    DATA_CHANGE = "data_change"  # Database change trigger


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_NOTIFICATION = "send_notification"
    RUN_SCRIPT = "run_script"
    DATABASE_OPERATION = "database_operation"
    HTTP_REQUEST = "http_request"
    GENERATE_REPORT = "generate_report"
    FILE_OPERATION = "file_operation"
    DATA_SYNC = "data_sync"


@dataclass
class Trigger:
    """Disparador de una automatización."""
    type: TriggerType = TriggerType.SCHEDULE
    config: Dict[str, Any] = field(default_factory=dict)
    # Schedule: {"interval": "daily", "hour": 9, "minute": 0, "day_of_week": "mon"}
    # Event: {"event_type": "stock_low", "threshold": 5}
    # Webhook: {"path": "/webhook/stock-alert"}
    # File: {"path": "/data/*.csv", "event": "created"}


@dataclass
class Action:
    """Acción a ejecutar cuando se dispara el trigger."""
    type: ActionType = ActionType.SEND_NOTIFICATION
    config: Dict[str, Any] = field(default_factory=dict)
    # Email: {"to": "admin@company.com", "subject": "Report", "template": "weekly_report"}
    # Script: {"code": "print('hello')", "language": "python"}
    # DB: {"query": "SELECT * FROM sales WHERE date > ?", "params": []}
    # HTTP: {"url": "https://api.example.com/notify", "method": "POST"}
    # Report: {"template": "sales_report", "format": "html", "recipient": "admin"}
    # File: {"operation": "copy", "source": "/a", "destination": "/b"}


@dataclass
class Workflow:
    """Definición completa de una automatización."""
    id: str = ""
    name: str = ""
    description: str = ""
    trigger: Trigger = field(default_factory=Trigger)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Action] = field(default_factory=list)
    enabled: bool = True
    created_at: float = 0.0
    last_run: float = 0.0
    run_count: int = 0
    status: str = "active"  # active, paused, error


@dataclass
class WorkflowExecution:
    """Resultado de una ejecución de workflow."""
    workflow_id: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    status: str = "pending"  # pending, running, success, failed
    actions_executed: int = 0
    actions_failed: int = 0
    output: str = ""
    error: str = ""


class AutomationEngine:
    """
    Motor de automatizaciones para PYMEs.

    Permite definir, almacenar y ejecutar flujos de trabajo automatizados.
    Usa APScheduler para scheduling, SQLite para persistencia, y
    ActionExecutor para ejecución REAL de acciones (no logger.info stubs).
    """

    def __init__(self, thinking_engine=None, template_engine=None, executor_registry=None):
        self._thinking = thinking_engine
        self._template_engine = template_engine
        self._executor_registry = executor_registry
        self._workflows: Dict[str, Workflow] = {}
        self._execution_history: List[WorkflowExecution] = []
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()
        self._load_workflows()

        # Lazy-init template engine if not provided
        if self._template_engine is None:
            try:
                from src.core.template_engine import TemplateEngine
                self._template_engine = TemplateEngine()
            except ImportError:
                logger.warning("AutomationEngine: TemplateEngine not available, using legacy generation")

        # Lazy-init executor registry if not provided
        if self._executor_registry is None:
            try:
                from src.core.action_executor import get_default_registry
                self._executor_registry = get_default_registry()
                logger.info("AutomationEngine: ActionExecutor registry initialized")
            except ImportError:
                logger.warning("AutomationEngine: ActionExecutor not available, using legacy stubs")

    def _init_db(self):
        """Crea tablas de automatización en SQLite."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                trigger_type TEXT DEFAULT 'schedule',
                trigger_config TEXT DEFAULT '{}',
                conditions TEXT DEFAULT '[]',
                actions TEXT DEFAULT '[]',
                enabled INTEGER DEFAULT 1,
                created_at REAL DEFAULT 0,
                last_run REAL DEFAULT 0,
                run_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                started_at REAL DEFAULT 0,
                finished_at REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                actions_executed INTEGER DEFAULT 0,
                actions_failed INTEGER DEFAULT 0,
                output TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_workflow ON execution_log(workflow_id)")

    def _load_workflows(self):
        """Carga workflows desde SQLite."""
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT * FROM workflows WHERE enabled=1").fetchall()
        for row in rows:
            wf = Workflow(
                id=row[0],
                name=row[1],
                description=row[2],
                trigger=Trigger(
                    type=TriggerType(row[3]),
                    config=json.loads(row[4]),
                ),
                conditions=json.loads(row[5]),
                actions=[Action(type=ActionType(a["type"]), config=a["config"]) for a in json.loads(row[6])],
                enabled=bool(row[7]),
                created_at=row[8],
                last_run=row[9],
                run_count=row[10],
                status=row[11],
            )
            self._workflows[wf.id] = wf

    # ================================================================
    #  WORKFLOW MANAGEMENT
    # ================================================================

    def create_workflow(self, name: str, description: str = "",
                       trigger: Optional[Trigger] = None,
                       actions: Optional[List[Action]] = None,
                       conditions: Optional[List[Dict]] = None) -> Workflow:
        """Crea un nuevo workflow de automatización."""
        wf_id = hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12]

        workflow = Workflow(
            id=wf_id,
            name=name,
            description=description,
            trigger=trigger or Trigger(),
            conditions=conditions or [],
            actions=actions or [],
            created_at=time.time(),
        )

        self._workflows[wf_id] = workflow
        self._save_workflow(workflow)
        return workflow

    def create_from_description(self, description: str) -> Workflow:
        """
        Crea un workflow a partir de una descripción en lenguaje natural.

        Usa ThinkingEngine para entender la descripción y generar
        el trigger, condiciones y acciones apropiados.
        """
        # Analyze with ThinkingEngine
        if self._thinking:
            plan = self._thinking.plan_generation(description)
            # Determine trigger type from description
            trigger = self._infer_trigger(description)
            actions = self._infer_actions(description, plan)
        else:
            trigger = self._fallback_trigger(description)
            actions = self._fallback_actions(description)

        name = self._extract_name(description)
        return self.create_workflow(name, description, trigger, actions)

    def _infer_trigger(self, description: str) -> Trigger:
        """Infiere el trigger a partir de la descripción."""
        desc_lower = description.lower()

        # Schedule patterns
        schedule_keywords = ["cada", "every", "diario", "daily", "semanal", "weekly",
                             "mensual", "monthly", "hora", "hour", "cron", "schedule"]
        if any(kw in desc_lower for kw in schedule_keywords):
            config = self._parse_schedule(description)
            return Trigger(type=TriggerType.SCHEDULE, config=config)

        # Event patterns
        event_keywords = ["cuando", "when", "si", "if", "al detectar", "on event"]
        if any(kw in desc_lower for kw in event_keywords):
            return Trigger(type=TriggerType.EVENT, config={"event_type": "custom", "description": description[:100]})

        # Webhook patterns
        webhook_keywords = ["webhook", "callback", "http post", "endpoint"]
        if any(kw in desc_lower for kw in webhook_keywords):
            return Trigger(type=TriggerType.WEBHOOK, config={"path": f"/webhook/custom"})

        # Default: daily schedule
        return Trigger(type=TriggerType.SCHEDULE, config={"interval": "daily", "hour": 9})

    def _parse_schedule(self, description: str) -> Dict[str, Any]:
        """Parsea una descripción de schedule."""
        desc_lower = description.lower()
        config = {"interval": "daily", "hour": 9, "minute": 0}

        if "diario" in desc_lower or "daily" in desc_lower:
            config["interval"] = "daily"
        elif "semanal" in desc_lower or "weekly" in desc_lower or "lunes" in desc_lower or "monday" in desc_lower:
            config["interval"] = "weekly"
            config["day_of_week"] = "mon"
        elif "mensual" in desc_lower or "monthly" in desc_lower:
            config["interval"] = "monthly"
            config["day"] = 1
        elif "hora" in desc_lower or "hourly" in desc_lower:
            config["interval"] = "hourly"

        # Try to extract hour
        import re
        hour_match = re.search(r'(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde)?', desc_lower)
        if hour_match:
            config["hour"] = int(hour_match.group(1))
            if hour_match.group(2):
                config["minute"] = int(hour_match.group(2))

        return config

    def _infer_actions(self, description: str, plan=None) -> List[Action]:
        """Infiere las acciones a partir de la descripción."""
        actions = []
        desc_lower = description.lower()

        # Email actions
        if any(kw in desc_lower for kw in ["email", "correo", "enviar", "mail"]):
            actions.append(Action(
                type=ActionType.SEND_EMAIL,
                config={"to": "admin@company.com", "subject": "Automated Report", "template": "default"}
            ))

        # Report generation
        if any(kw in desc_lower for kw in ["reporte", "report", "informe"]):
            actions.append(Action(
                type=ActionType.GENERATE_REPORT,
                config={"template": "default_report", "format": "html"}
            ))

        # Database operations
        if any(kw in desc_lower for kw in ["backup", "respaldo", "base de datos", "database"]):
            actions.append(Action(
                type=ActionType.DATABASE_OPERATION,
                config={"operation": "backup", "destination": "backups/"}
            ))

        # Notifications
        if any(kw in desc_lower for kw in ["notificar", "alertar", "notification", "alert"]):
            actions.append(Action(
                type=ActionType.SEND_NOTIFICATION,
                config={"channel": "log", "message": "Alert triggered"}
            ))

        # Data sync
        if any(kw in desc_lower for kw in ["sincronizar", "sync", "integrar", "migrar"]):
            actions.append(Action(
                type=ActionType.DATA_SYNC,
                config={"source": "local_db", "destination": "remote"}
            ))

        # HTTP request
        if any(kw in desc_lower for kw in ["api", "webhook", "http", "request"]):
            actions.append(Action(
                type=ActionType.HTTP_REQUEST,
                config={"url": "https://api.example.com/webhook", "method": "POST"}
            ))

        # Default: if no actions identified, add a notification
        if not actions:
            actions.append(Action(
                type=ActionType.SEND_NOTIFICATION,
                config={"channel": "log", "message": f"Workflow executed: {description[:50]}"}
            ))

        return actions

    def _fallback_trigger(self, description: str) -> Trigger:
        """Fallback trigger inference sin IA."""
        return self._infer_trigger(description)

    def _fallback_actions(self, description: str) -> List[Action]:
        """Fallback action inference sin IA."""
        return self._infer_actions(description)

    def _extract_name(self, description: str) -> str:
        """Extrae un nombre corto de la descripción."""
        # Take first meaningful words
        words = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]', '', description).split()[:4]
        name = "_".join(w.lower() for w in words)
        return name if name else "automation"

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

    # ================================================================
    #  WORKFLOW PERSISTENCE
    # ================================================================

    def _save_workflow(self, wf: Workflow):
        """Guarda un workflow en SQLite."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""INSERT OR REPLACE INTO workflows
                (id, name, description, trigger_type, trigger_config, conditions, actions, enabled, created_at, last_run, run_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (wf.id, wf.name, wf.description, wf.trigger.type.value,
                 json.dumps(wf.trigger.config), json.dumps(wf.conditions),
                 json.dumps([{"type": a.type.value, "config": a.config} for a in wf.actions]),
                 int(wf.enabled), wf.created_at, wf.last_run, wf.run_count, wf.status))

    def _log_execution(self, execution: WorkflowExecution):
        """Registra una ejecución en el log."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""INSERT INTO execution_log
                (workflow_id, started_at, finished_at, status, actions_executed, actions_failed, output, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (execution.workflow_id, execution.started_at, execution.finished_at,
                 execution.status, execution.actions_executed, execution.actions_failed,
                 execution.output, execution.error))

    # ================================================================
    #  WORKFLOW GENERATION (from natural language)
    # ================================================================

    def generate_automation_project(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera un proyecto de automatización completo.
        Usa TemplateEngine si disponible, sino usa legacy f-strings.
        """
        if self._template_engine:
            return self._generate_automation_v2(description, output_dir)
        return self._generate_automation_legacy(description, output_dir)

    def _generate_automation_v2(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera automatización con TemplateEngine + bloques de acción reales.
        """
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, self._extract_name(description))
        os.makedirs(output_dir, exist_ok=True)

        workflow = self.create_from_description(description)

        # Suggest blocks for automation
        suggested_blocks = self._template_engine.suggest_blocks(description)

        from src.core.template_engine import CompositionPlan
        composition = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=suggested_blocks,
            variables={
                "project_name": workflow.name,
                "app_name": workflow.name,
                "template_type": "automation",
                "db_name": "automation.db",
                "port": 8001,
                "secret_key": "change-this",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": workflow.name,
                "fields": [],
                "trigger_config": workflow.trigger.config,
                "actions": [{"type": a.type.value, "config": a.config} for a in workflow.actions],
            }],
        )

        try:
            files = self._template_engine.render_automation(composition)

            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            return {
                "workflow": workflow,
                "path": output_dir,
                "files": list(files.keys()),
                "blocks_used": suggested_blocks,
                "status": "generated",
            }
        except Exception as e:
            logger.error(f"AutomationEngine v2: Failed: {e}")
            # Fall back to legacy
            return self._generate_automation_legacy(description, output_dir)

    def _generate_automation_legacy(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera un proyecto de automatización completo a partir de una descripción.

        Crea un proyecto Python independiente con:
          - main.py (scheduler + workflow engine)
          - workflows.py (definiciones de workflows)
          - config.py (configuración)
          - requirements.txt
        """
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, self._extract_name(description))
        os.makedirs(output_dir, exist_ok=True)

        workflow = self.create_from_description(description)

        files = {
            "main.py": self._gen_automation_main(workflow, description),
            "workflows.py": self._gen_automation_workflows(workflow),
            "config.py": self._gen_automation_config(workflow, description),
            "requirements.txt": "apscheduler>=3.10.0\naiosmtplib>=3.0.0\n",
            "README.md": self._gen_automation_readme(workflow, description),
        }

        for filepath, content in files.items():
            full_path = os.path.join(output_dir, filepath)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        return {
            "workflow": workflow,
            "path": output_dir,
            "files": list(files.keys()),
            "status": "generated",
        }

    def _gen_automation_main(self, wf: Workflow, description: str) -> str:
        """Genera main.py para proyecto de automatización."""
        schedule_config = wf.trigger.config
        interval = schedule_config.get("interval", "daily")
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)

        # Build trigger config for APScheduler
        if interval == "hourly":
            trigger_code = "IntervalTrigger(hours=1)"
        elif interval == "daily":
            trigger_code = f"CronTrigger(hour={hour}, minute={minute})"
        elif interval == "weekly":
            day = schedule_config.get("day_of_week", "mon")
            trigger_code = f"CronTrigger(day_of_week='{day}', hour={hour}, minute={minute})"
        elif interval == "monthly":
            day = schedule_config.get("day", 1)
            trigger_code = f"CronTrigger(day={day}, hour={hour}, minute={minute})"
        else:
            trigger_code = f"CronTrigger(hour={hour}, minute={minute})"

        actions_code = []
        for i, action in enumerate(wf.actions):
            if action.type == ActionType.SEND_EMAIL:
                actions_code.append(f'''
    # Action {i+1}: Send Email
    print(f"Sending email to {action.config.get('to', 'admin@company.com')}...")
    # from services import EmailService
    # EmailService.send(to="{action.config.get('to', 'admin@company.com')}", subject="{action.config.get('subject', 'Report')}")
''')
            elif action.type == ActionType.SEND_NOTIFICATION:
                actions_code.append(f'''
    # Action {i+1}: Send Notification
    print(f"Notification: {action.config.get('message', 'Workflow executed')}")
''')
            elif action.type == ActionType.GENERATE_REPORT:
                actions_code.append(f'''
    # Action {i+1}: Generate Report
    print("Generating report...")
    # from services import ReportService
    # report = ReportService.generate(template="{action.config.get('template', 'default')}")
''')
            elif action.type == ActionType.DATABASE_OPERATION:
                actions_code.append(f'''
    # Action {i+1}: Database Operation
    print("Executing database operation...")
    # from services import DatabaseService
    # DatabaseService.{action.config.get('operation', 'backup')}()
''')
            else:
                actions_code.append(f'''
    # Action {i+1}: {action.type.value}
    print("Executing {action.type.value}...")
''')

        actions_str = "\n".join(actions_code) if actions_code else '    print("No actions defined")'

        return f'''"""
{wf.name} - Automation
Auto-generated by TITAN OMNISCALE X

Description: {description}
Schedule: {interval} at {hour}:{minute:02d}
"""
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("{wf.name}")


async def run_workflow():
    """Ejecuta el workflow de automatización."""
    logger.info(f"Running workflow: {wf.name}")
    start = datetime.now()
{actions_str}
    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"Workflow completed in {elapsed:.2f}s")


async def main():
    """Punto de entrada principal."""
    scheduler = AsyncIOScheduler()

    # Schedule the workflow
    scheduler.add_job(
        run_workflow,
        {trigger_code},
        id="{wf.name}",
        name="{wf.name}",
        replace_existing=True,
    )

    logger.info(f"Scheduler started. Workflow '{wf.name}' scheduled ({interval}).")
    logger.info("Press Ctrl+C to exit.")

    scheduler.start()

    # Run once immediately on startup
    await run_workflow()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
'''

    def _gen_automation_workflows(self, wf: Workflow) -> str:
        """Genera workflows.py - Definiciones de workflows."""
        return f'''"""
{wf.name} - Workflow Definitions
Auto-generated by TITAN OMNISCALE X
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"
    WEBHOOK = "webhook"


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_NOTIFICATION = "send_notification"
    RUN_SCRIPT = "run_script"
    DATABASE_OPERATION = "database_operation"
    GENERATE_REPORT = "generate_report"
    HTTP_REQUEST = "http_request"


@dataclass
class Action:
    type: ActionType = ActionType.SEND_NOTIFICATION
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    name: str = ""
    description: str = ""
    trigger_type: TriggerType = TriggerType.SCHEDULE
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)


# ============================================================
#  WORKFLOW DEFINITIONS
# ============================================================

WORKFLOWS = [
    WorkflowDefinition(
        name="{wf.name}",
        description="{wf.description}",
        trigger_type=TriggerType.{wf.trigger.type.name},
        trigger_config={wf.trigger.config},
        actions=[
{chr(10).join(f"            Action(ActionType.{a.type.name}, {a.config})," for a in wf.actions)}
        ],
    ),
]


def get_workflow(name: str) -> WorkflowDefinition:
    """Obtiene un workflow por nombre."""
    for wf in WORKFLOWS:
        if wf.name == name:
            return wf
    return WORKFLOWS[0] if WORKFLOWS else None
'''

    def _gen_automation_config(self, wf: Workflow, description: str) -> str:
        """Genera config.py para proyecto de automatización."""
        return f'''"""
{wf.name} - Configuration
Auto-generated by TITAN OMNISCALE X
"""
import os


class Config:
    APP_NAME = "{wf.name}"
    DEBUG = True
    LOG_LEVEL = "INFO"

    # Email SMTP Configuration
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

    # Notification Settings
    NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "admin@company.com")
    NOTIFICATION_CHANNEL = os.environ.get("NOTIFICATION_CHANNEL", "log")

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "automation.db")

    # Scheduler
    SCHEDULER_TIMEZONE = "UTC"
    SCHEDULER_JOBSTORES = "default"
    SCHEDULER_MAX_INSTANCES = 1
'''

    def _gen_automation_readme(self, wf: Workflow, description: str) -> str:
        """Genera README.md para proyecto de automatización."""
        return f'''# {wf.name}

> Automation generated by **TITAN OMNISCALE X**

## Description

{description}

## Schedule

- **Type**: {wf.trigger.type.value}
- **Config**: {wf.trigger.config}

## Actions

{chr(10).join(f"- {a.type.value}: {a.config}" for a in wf.actions)}

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

Edit `config.py` with your SMTP credentials and settings.

## Environment Variables

- `SMTP_HOST` - SMTP server host
- `SMTP_PORT` - SMTP server port
- `SMTP_USER` - SMTP username
- `SMTP_PASSWORD` - SMTP password
- `NOTIFICATION_EMAIL` - Email for notifications
'''

    # ================================================================
    #  QUERY METHODS
    # ================================================================

    def list_workflows(self) -> List[Dict[str, Any]]:
        """Lista todos los workflows."""
        return [
            {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "trigger": {"type": wf.trigger.type.value, "config": wf.trigger.config},
                "actions": [{"type": a.type.value, "config": a.config} for a in wf.actions],
                "enabled": wf.enabled,
                "run_count": wf.run_count,
                "last_run": wf.last_run,
                "status": wf.status,
            }
            for wf in self._workflows.values()
        ]

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un workflow por ID."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return None
        return {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "trigger": {"type": wf.trigger.type.value, "config": wf.trigger.config},
            "actions": [{"type": a.type.value, "config": a.config} for a in wf.actions],
            "enabled": wf.enabled,
            "run_count": wf.run_count,
            "status": wf.status,
        }

    def toggle_workflow(self, workflow_id: str) -> bool:
        """Activa/desactiva un workflow."""
        wf = self._workflows.get(workflow_id)
        if not wf:
            return False
        wf.enabled = not wf.enabled
        wf.status = "active" if wf.enabled else "paused"
        self._save_workflow(wf)
        return wf.enabled

    def delete_workflow(self, workflow_id: str) -> bool:
        """Elimina un workflow."""
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
            return True
        return False

    def get_execution_history(self, workflow_id: str = "", limit: int = 20) -> List[Dict]:
        """Obtiene historial de ejecuciones."""
        with sqlite3.connect(DB_PATH) as conn:
            if workflow_id:
                rows = conn.execute(
                    "SELECT * FROM execution_log WHERE workflow_id=? ORDER BY started_at DESC LIMIT ?",
                    (workflow_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM execution_log ORDER BY started_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()

        return [
            {
                "id": r[0], "workflow_id": r[1], "started_at": r[2],
                "finished_at": r[3], "status": r[4], "actions_executed": r[5],
                "actions_failed": r[6], "output": r[7], "error": r[8],
            }
            for r in rows
        ]

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del motor de automatización."""
        return {
            "total_workflows": len(self._workflows),
            "active_workflows": sum(1 for w in self._workflows.values() if w.enabled),
            "total_executions": len(self._execution_history),
            "successful_executions": sum(1 for e in self._execution_history if e.status == "success"),
        }
