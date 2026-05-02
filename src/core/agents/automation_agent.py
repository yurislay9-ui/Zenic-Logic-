"""
TITAN OMNISCALE X - AutomationAgent

Agente IA que UNIFICA el diseño de automatizaciones.
Reemplaza la lógica de inferencia dispersa en AutomationEngine:

  1. AutomationEngine._infer_trigger() - keyword-based trigger inference
  2. AutomationEngine._infer_actions() - keyword-based action inference
  3. AutomationEngine._parse_schedule() - regex schedule parsing
  4. AutomationEngine._extract_name() - simple name extraction

Arquitectura del AutomationAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → AutomationOutput
  - Semantic path: Si SemanticEngine disponible → clasificación + contexto
  - Fallback path: Inferencia determinista por keywords (sin LLM)

Tipos de trigger soportados:
  - manual: Ejecución manual
  - schedule: Programado (cron, interval)
  - event: Basado en eventos
  - webhook: HTTP endpoint

Tipos de acción soportados:
  - email, http, db, file, webhook, notification, transform, schedule, log

Produce un AutomationOutput compatible con AutomationEngine.Workflow.
"""

import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import (
    AutomationInput, AutomationOutput, TriggerSpec, ActionSpec, ScheduleSpec,
)
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Trigger inference keywords (EN + ES)
TRIGGER_KEYWORDS = {
    "schedule": [
        "cada", "every", "diario", "daily", "semanal", "weekly",
        "mensual", "monthly", "hora", "hourly", "cron", "schedule",
        "programado", "periódico", "periodico", "a las",
    ],
    "event": [
        "cuando", "when", "si", "if", "al detectar", "on event",
        "detecte", "ocurra", "trigger",
    ],
    "webhook": [
        "webhook", "callback", "http post", "endpoint", "api call",
        "recibir", "petición",
    ],
}

# Action inference keywords (EN + ES)
ACTION_KEYWORDS = {
    "email": ["email", "correo", "enviar", "mail", "smtp", "notificar por correo"],
    "notification": ["notificar", "alertar", "notification", "alert", "avisar"],
    "report": ["reporte", "report", "informe", "resumen", "summary"],
    "db": ["backup", "respaldo", "base de datos", "database", "db", "sql"],
    "http": ["api", "webhook", "http", "request", "endpoint", "servicio"],
    "file": ["archivo", "file", "csv", "excel", "documento", "exportar"],
    "transform": ["transformar", "procesar", "convertir", "parse", "etl"],
    "schedule": ["programar", "schedule", "planificar", "cron"],
    "log": ["log", "registrar", "audit", "auditoría"],
}

# Schedule parsing patterns
SCHEDULE_PATTERNS = {
    "hourly": ["cada hora", "hourly", "cada 1 hora", "every hour"],
    "daily": ["diario", "daily", "cada día", "cada dia", "every day"],
    "weekly": ["semanal", "weekly", "cada semana", "lunes", "monday", "mon"],
    "monthly": ["mensual", "monthly", "cada mes"],
}


class AutomationAgent(BaseAgent[AutomationOutput]):
    """
    Agente de diseño de automatizaciones que unifica la inferencia
    de triggers, acciones y schedules desde lenguaje natural.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt con descripción de automatización
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por keywords

    El agente reemplaza:
    - AutomationEngine._infer_trigger() (keyword matching, 30 líneas)
    - AutomationEngine._infer_actions() (keyword matching, 55 líneas)
    - AutomationEngine._parse_schedule() (regex parsing, 25 líneas)
    - AutomationEngine._extract_name() (simple extraction, 5 líneas)
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="automation")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory

    def wire(self, semantic_engine=None, smart_memory=None) -> None:
        """Cablea dependencias."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt para automatización."""
        if isinstance(input_data, AutomationInput):
            description = input_data.description
            context = input_data.context
        else:
            description = str(input_data)
            context = {}

        system_prompt = AgentPrompts.AUTOMATION_SYSTEM
        user_prompt = AgentPrompts.AUTOMATION_USER.format(
            description=description[:500],
        )

        # Add context
        if context:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, context
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[AutomationOutput]:
        """Parsea la respuesta del LLM a un AutomationOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction first
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_automation_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_automation(cleaned, source="llm")

    def fallback(self, input_data: Any) -> AutomationOutput:
        """
        Fallback determinista: inferencia por keywords.

        Sin LLM, sin embeddings. Detección directa de triggers, acciones
        y schedules desde keywords en la descripción.
        """
        start = time.time()

        if isinstance(input_data, AutomationInput):
            description = input_data.description
            context = input_data.context
        else:
            description = str(input_data)
            context = {}

        # 1. SmartMemory lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(description)
                if cached and cached.get("response"):
                    duration_ms = int((time.time() - start) * 1000)
                    self._update_stats("fallback", duration_ms)
                    # Try to parse cached response as automation
                    try:
                        cached_data = eval(cached["response"])
                        if isinstance(cached_data, dict):
                            return self._json_to_automation_output(cached_data, source="fallback")
                    except Exception:
                        pass
            except Exception:
                pass

        # 2. Deterministic inference
        triggers = self._infer_triggers(description)
        actions = self._infer_actions(description)
        schedule = self._infer_schedule(description)
        name = self._extract_name(description)
        conditions = self._infer_conditions(description)

        # Save to memory
        if self._smart_memory:
            try:
                self._smart_memory.save_to_cache(
                    description, str(AutomationOutput(
                        name=name, triggers=triggers, actions=actions,
                        schedule=schedule, conditions=conditions,
                        description=description[:200],
                    )), "automation", "", 0.6,
                )
            except Exception:
                pass

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        return AutomationOutput(
            name=name,
            triggers=triggers,
            actions=actions,
            schedule=schedule,
            conditions=conditions,
            description=description[:200],
            source="fallback",
        )

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def design_with_runner(self, runner: Any, description: str,
                           context: Optional[Dict[str, Any]] = None) -> AutomationOutput:
        """Diseña automatización usando AgentRunner (LLM → fallback)."""
        input_data = AutomationInput(
            description=description,
            context=context or {},
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, AutomationOutput):
            return result.data
        return self.fallback(input_data)

    # ============================================================
    #  COMPATIBILITY: AutomationEngine methods preserved
    # ============================================================

    def to_workflow_dict(self, output: AutomationOutput) -> Dict[str, Any]:
        """
        Convierte AutomationOutput a formato compatible con
        AutomationEngine.Workflow para integración legacy.
        """
        return {
            "name": output.name,
            "description": output.description,
            "trigger": {
                "type": output.triggers[0].type if output.triggers else "schedule",
                "config": output.triggers[0].config if output.triggers else {},
            },
            "actions": [
                {"type": a.type, "config": a.config, "description": a.description}
                for a in output.actions
            ],
            "schedule": {
                "type": output.schedule.type,
                "interval_seconds": output.schedule.interval_seconds,
                "cron_expression": output.schedule.cron_expression,
            },
            "conditions": output.conditions,
        }

    # ============================================================
    #  DETERMINISTIC INFERENCE (fallback logic)
    # ============================================================

    def _infer_triggers(self, description: str) -> List[TriggerSpec]:
        """Infiere triggers desde la descripción por keywords."""
        desc_lower = description.lower()

        for trigger_type, keywords in TRIGGER_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                config = {}
                if trigger_type == "schedule":
                    config = self._parse_schedule_config(description)
                elif trigger_type == "event":
                    config = {"event_type": "custom", "description": description[:100]}
                elif trigger_type == "webhook":
                    config = {"path": "/webhook/custom"}

                return [TriggerSpec(
                    type=trigger_type,
                    config=config,
                    description=f"Auto-detected {trigger_type} trigger",
                )]

        # Default: daily schedule
        return [TriggerSpec(
            type="schedule",
            config={"interval": "daily", "hour": 9},
            description="Default daily schedule",
        )]

    def _infer_actions(self, description: str) -> List[ActionSpec]:
        """Infiere acciones desde la descripción por keywords."""
        desc_lower = description.lower()
        actions = []

        for action_type, keywords in ACTION_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                config = self._default_action_config(action_type, description)
                actions.append(ActionSpec(
                    type=action_type,
                    config=config,
                    description=f"Auto-detected {action_type} action",
                ))

        # Default: log notification if no actions detected
        if not actions:
            actions.append(ActionSpec(
                type="log",
                config={"message": f"Automation executed: {description[:50]}"},
                description="Default log action",
            ))

        return actions[:5]  # Max 5 actions

    def _infer_schedule(self, description: str) -> ScheduleSpec:
        """Infiere schedule desde la descripción."""
        desc_lower = description.lower()

        for sched_type, keywords in SCHEDULE_PATTERNS.items():
            if any(kw in desc_lower for kw in keywords):
                if sched_type == "hourly":
                    return ScheduleSpec(
                        type="interval", interval_seconds=3600,
                        description="Hourly execution",
                    )
                elif sched_type == "daily":
                    hour = self._extract_hour(description)
                    cron = f"0 {hour} * * *"
                    return ScheduleSpec(
                        type="cron", cron_expression=cron,
                        description=f"Daily at {hour}:00",
                    )
                elif sched_type == "weekly":
                    return ScheduleSpec(
                        type="cron", cron_expression="0 9 * * 1",
                        description="Weekly on Monday at 9:00",
                    )
                elif sched_type == "monthly":
                    return ScheduleSpec(
                        type="cron", cron_expression="0 9 1 * *",
                        description="Monthly on the 1st at 9:00",
                    )

        return ScheduleSpec(
            type="manual",
            description="Manual execution",
        )

    def _infer_conditions(self, description: str) -> List[str]:
        """Infiere condiciones desde la descripción."""
        conditions = []
        desc_lower = description.lower()

        if any(kw in desc_lower for kw in ["si", "if", "solo si", "only when"]):
            # Extract condition from "if/when X" pattern
            for pattern in [r'(?:si|if|when)\s+(.+?)(?:\s+(?:then|entonces|,|\.|$))',
                           r'(?:solo si|only when)\s+(.+?)(?:,|\.|$)']:
                match = re.search(pattern, desc_lower)
                if match:
                    conditions.append(match.group(1).strip()[:100])
                    break

        return conditions

    def _extract_name(self, description: str) -> str:
        """Extrae un nombre corto de la descripción."""
        # Remove common stop words and special chars
        words = re.sub(r'[^a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]', '', description).split()[:4]
        stop = {'un', 'una', 'el', 'la', 'los', 'las', 'a', 'de', 'del',
                'en', 'por', 'para', 'con', 'que', 'se', 'the', 'a', 'an',
                'create', 'make', 'generate', 'build', 'automate'}
        name_parts = [w.lower() for w in words if w.lower() not in stop]
        return "_".join(name_parts) if name_parts else "automation"

    # ============================================================
    #  PRIVATE HELPERS
    # ============================================================

    def _parse_schedule_config(self, description: str) -> Dict[str, Any]:
        """Parsea configuración de schedule desde descripción."""
        config = {"interval": "daily", "hour": 9, "minute": 0}
        desc_lower = description.lower()

        if "diario" in desc_lower or "daily" in desc_lower:
            config["interval"] = "daily"
        elif "semanal" in desc_lower or "weekly" in desc_lower:
            config["interval"] = "weekly"
            config["day_of_week"] = "mon"
        elif "mensual" in desc_lower or "monthly" in desc_lower:
            config["interval"] = "monthly"
            config["day"] = 1
        elif "hora" in desc_lower or "hourly" in desc_lower:
            config["interval"] = "hourly"

        # Extract hour
        hour = self._extract_hour(description)
        if hour != 9:
            config["hour"] = hour

        return config

    def _extract_hour(self, description: str) -> int:
        """Extrae hora desde descripción."""
        match = re.search(
            r'(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde)?',
            description.lower(),
        )
        if match:
            hour = int(match.group(1))
            if "pm" in description.lower() and hour < 12:
                hour += 12
            elif "am" in description.lower() and hour == 12:
                hour = 0
            return hour
        return 9

    def _default_action_config(self, action_type: str,
                                description: str) -> Dict[str, Any]:
        """Configuración por defecto para cada tipo de acción."""
        configs = {
            "email": {"to": "admin@company.com", "subject": "Automated Report",
                      "template": "default"},
            "notification": {"channel": "log", "message": description[:100]},
            "report": {"template": "default_report", "format": "html"},
            "db": {"operation": "backup", "destination": "backups/"},
            "http": {"url": "https://api.example.com/webhook", "method": "POST"},
            "file": {"operation": "export", "format": "csv"},
            "transform": {"source_format": "raw", "target_format": "structured"},
            "schedule": {"action": "schedule_next"},
            "log": {"level": "info", "message": description[:100]},
        }
        return configs.get(action_type, {"description": description[:100]})

    def _json_to_automation_output(self, data: Dict[str, Any],
                                    source: str = "llm") -> Optional[AutomationOutput]:
        """Convierte dict JSON a AutomationOutput."""
        name = str(data.get("name", "unnamed_automation")).strip()
        if not name:
            name = "unnamed_automation"

        # Parse triggers
        triggers = []
        for t in data.get("triggers", []):
            if isinstance(t, dict):
                triggers.append(TriggerSpec(
                    type=str(t.get("type", "manual")),
                    config=t.get("config", {}),
                    description=str(t.get("description", "")),
                ))

        # Parse actions
        actions = []
        for a in data.get("actions", []):
            if isinstance(a, dict):
                actions.append(ActionSpec(
                    type=str(a.get("type", "log")),
                    config=a.get("config", {}),
                    description=str(a.get("description", "")),
                ))

        # Parse schedule
        sched = data.get("schedule", {})
        if isinstance(sched, dict):
            schedule = ScheduleSpec(
                type=str(sched.get("type", "manual")),
                interval_seconds=int(sched.get("interval_seconds", 0)),
                cron_expression=str(sched.get("cron_expression", "")),
                description=str(sched.get("description", "")),
            )
        else:
            schedule = ScheduleSpec()

        # Parse conditions
        conditions = data.get("conditions", [])
        if isinstance(conditions, str):
            conditions = [conditions]

        description = str(data.get("description", ""))

        return AutomationOutput(
            name=name,
            triggers=triggers,
            actions=actions,
            schedule=schedule,
            conditions=conditions if isinstance(conditions, list) else [],
            description=description,
            source=source,
        )

    def _parse_free_text_automation(self, text: str,
                                     source: str = "llm") -> Optional[AutomationOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        if not text or len(text) < 10:
            return None

        # Extract name from first line
        lines = text.strip().split('\n')
        name = self._extract_name(lines[0])

        return AutomationOutput(
            name=name,
            triggers=[TriggerSpec(type="manual", description="Free-text trigger")],
            actions=[ActionSpec(type="log", config={"message": text[:200]},
                               description="Free-text action")],
            schedule=ScheduleSpec(type="manual"),
            description=text[:200],
            source=source,
        )
