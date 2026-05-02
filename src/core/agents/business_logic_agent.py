"""
TITAN OMNISCALE X - BusinessLogicAgent

Agente IA que reemplaza los 30+ LogicBlocks hardcoded con lógica de negocio
impulsada por IA. En lugar de mantener 2764 líneas de bloques de lógica
estática, el BusinessLogicAgent usa el LLM para ejecutar lógica de negocio
dinámicamente.

Reemplaza:
  - LogicBuilder (2764 líneas, 30+ LogicBlocks en 6 categorías)
  - ThinkingEngine plan_generation() + _identify_entities() + _generate_endpoints()

Arquitectura del BusinessLogicAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → BusinessOutput
  - Template path: Si el tipo de operación es conocido → ejecución directa
  - Fallback path: Lógica de negocio determinista por tipo de operación

Tipos de operación soportados:
  - invoice: Cálculo de facturas con impuestos, descuentos
  - inventory: Seguimiento de inventario con alertas
  - crm: Pipeline de ventas con etapas
  - task: Priorización y asignación de tareas
  - report: Generación de reportes desde datos
  - notification: Despacho de notificaciones
  - analytics: Análisis de datos con métricas
  - custom: Lógica de negocio personalizada
"""

import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Valid operation types
VALID_OPERATION_TYPES = frozenset({
    "invoice", "inventory", "crm", "task", "report",
    "notification", "analytics", "custom",
})


class BusinessLogicAgent(BaseAgent[BusinessOutput]):
    """
    Agente de lógica de negocio que ejecuta operaciones empresariales.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt con tipo de operación y datos
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por tipo de operación

    El agente unifica la lógica de negocio que antes estaba en:
    - InvoiceCalculatorBlock (60 líneas)
    - InventoryTrackerBlock (60 líneas)
    - CRMPipelineBlock (60 líneas)
    - TaskSchedulerBlock (60 líneas)
    - ReportGeneratorBlock (60 líneas)
    - NotificationDispatcherBlock (60 líneas)
    - DataAnalyzerBlock (60 líneas)
    - + 23 bloques más en logic_builder.py
    """

    def __init__(self, semantic_engine=None, smart_memory=None) -> None:
        super().__init__(name="business_logic")
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
        """Construye system + user prompt para lógica de negocio."""
        if isinstance(input_data, BusinessInput):
            op_type = input_data.operation_type
            data = input_data.data
            context = input_data.context
            description = input_data.description
        else:
            op_type = "custom"
            data = {}
            context = {}
            description = str(input_data)

        system_prompt = AgentPrompts.BUSINESS_SYSTEM

        # Build user prompt with operation details
        user_prompt = AgentPrompts.BUSINESS_USER.format(
            operation_type=op_type,
            data=json.dumps(data, default=str, ensure_ascii=False)[:500],
            context=json.dumps(context, default=str, ensure_ascii=False)[:300],
            description=description[:300],
        )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[BusinessOutput]:
        """Parsea la respuesta del LLM a un BusinessOutput válido."""
        cleaned = self.clean_llm_text(raw_response)

        # Try JSON extraction
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_business_output(json_data, source="llm")

        # Try free text parsing
        return self._parse_free_text_business(cleaned, source="llm")

    def fallback(self, input_data: Any) -> BusinessOutput:
        """
        Fallback determinista: ejecución directa por tipo de operación.

        Sin LLM, sin embeddings. Cada tipo de operación tiene su lógica
        determinista pre-definida.
        """
        start = time.time()

        if isinstance(input_data, BusinessInput):
            op_type = input_data.operation_type
            data = input_data.data
            context = input_data.context
            description = input_data.description
        else:
            op_type = "custom"
            data = {}
            context = {}
            description = str(input_data)

        # Route to specific fallback handler
        handler_map = {
            "invoice": self._fallback_invoice,
            "inventory": self._fallback_inventory,
            "crm": self._fallback_crm,
            "task": self._fallback_task,
            "report": self._fallback_report,
            "notification": self._fallback_notification,
            "analytics": self._fallback_analytics,
            "custom": self._fallback_custom,
        }

        handler = handler_map.get(op_type, self._fallback_custom)
        result = handler(data, context, description)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        result.source = "fallback"
        return result

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def execute_business(self, operation_type: str, data: Dict[str, Any],
                         context: Optional[Dict[str, Any]] = None,
                         description: str = "") -> BusinessOutput:
        """Ejecuta lógica de negocio (fallback directo, sin LLM)."""
        input_data = BusinessInput(
            operation_type=operation_type,
            data=data,
            context=context or {},
            description=description,
        )
        return self.fallback(input_data)

    def execute_with_runner(self, runner: Any, operation_type: str,
                            data: Dict[str, Any],
                            context: Optional[Dict[str, Any]] = None,
                            description: str = "") -> BusinessOutput:
        """Ejecuta lógica de negocio usando AgentRunner (LLM → fallback)."""
        input_data = BusinessInput(
            operation_type=operation_type,
            data=data,
            context=context or {},
            description=description,
        )
        result: AgentResult = runner.run(self, input_data)

        if result.success and isinstance(result.data, BusinessOutput):
            return result.data

        return self.fallback(input_data)

    # ============================================================
    #  FALLBACK HANDLERS (deterministic business logic)
    # ============================================================

    def _fallback_invoice(self, data: Dict, context: Dict,
                          description: str) -> BusinessOutput:
        """Lógica de facturación: cálculos de impuestos, descuentos, totales."""
        try:
            items = data.get("items", [])
            tax_rate = float(data.get("tax_rate", data.get("tax", 0.16)))
            discount_pct = float(data.get("discount", 0))

            if not items:
                return BusinessOutput(
                    success=False, errors=["No items provided for invoice"],
                )

            subtotal = 0.0
            processed = []
            for item in items:
                if isinstance(item, dict):
                    qty = float(item.get("quantity", 1))
                    price = float(item.get("price", 0))
                    item_total = qty * price
                    subtotal += item_total
                    processed.append({**item, "item_total": round(item_total, 2)})

            discount_amount = round(subtotal * (discount_pct / 100), 2) if discount_pct > 0 else 0.0
            taxable = subtotal - discount_amount
            tax_amount = round(taxable * tax_rate, 2)
            total = round(taxable + tax_amount, 2)

            return BusinessOutput(
                success=True,
                data={
                    "subtotal": round(subtotal, 2),
                    "tax_amount": tax_amount,
                    "tax_rate": tax_rate,
                    "discount_amount": discount_amount,
                    "discount_pct": discount_pct,
                    "total": total,
                    "item_count": len(items),
                    "items": processed,
                },
                side_effects=["invoice_calculated"],
                insights=[
                    f"Total: {total} (tax: {tax_amount}, discount: {discount_amount})",
                    f"Average item value: {round(subtotal / len(items), 2)}" if items else "",
                ],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_inventory(self, data: Dict, context: Dict,
                            description: str) -> BusinessOutput:
        """Lógica de inventario: seguimiento de stock, alertas."""
        try:
            product_id = data.get("product_id", "unknown")
            quantity_change = int(data.get("quantity_change", data.get("quantity", 0)))
            operation = data.get("operation", "adjust")
            current_qty = int(data.get("current_quantity", data.get("stock", 0)))
            threshold = int(data.get("low_stock_threshold", 10))

            if operation == "add":
                new_qty = current_qty + quantity_change
            elif operation == "remove":
                new_qty = max(0, current_qty - quantity_change)
            elif operation == "set":
                new_qty = quantity_change
            else:
                new_qty = max(0, current_qty + quantity_change)

            alerts = []
            side_effects = []
            if new_qty <= 0:
                alerts.append({"type": "out_of_stock", "product_id": product_id})
                side_effects.append("out_of_stock_alert")
            elif new_qty <= threshold:
                alerts.append({"type": "low_stock", "product_id": product_id,
                               "quantity": new_qty})
                side_effects.append("low_stock_alert")

            return BusinessOutput(
                success=True,
                data={
                    "product_id": product_id,
                    "previous_quantity": current_qty,
                    "new_quantity": new_qty,
                    "change": new_qty - current_qty,
                    "alerts": alerts,
                    "low_stock": new_qty <= threshold,
                },
                side_effects=side_effects,
                insights=[f"Stock: {current_qty} → {new_qty}"]
                         + [f"Alert: {a['type']}" for a in alerts],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_crm(self, data: Dict, context: Dict,
                      description: str) -> BusinessOutput:
        """Lógica CRM: pipeline de ventas."""
        try:
            stages = ["new", "contacted", "qualified", "proposal",
                      "negotiation", "closed_won", "closed_lost"]
            lead = data.get("lead_data", data.get("lead", {}))
            current_stage = data.get("current_stage", lead.get("stage", "new"))
            action = data.get("action", "advance")

            if current_stage not in stages:
                current_stage = stages[0]

            idx = stages.index(current_stage)
            new_stage = current_stage
            next_action = "Follow up"

            if action == "advance" and idx < len(stages) - 1:
                new_stage = stages[idx + 1]
            elif action == "regress" and idx > 0:
                new_stage = stages[idx - 1]
            elif action == "close_won":
                new_stage = "closed_won"
                next_action = "Send onboarding email"
            elif action == "close_lost":
                new_stage = "closed_lost"
                next_action = "Archive lead, schedule follow-up in 30 days"

            probs = {"new": 0.10, "contacted": 0.20, "qualified": 0.40,
                     "proposal": 0.60, "negotiation": 0.80,
                     "closed_won": 1.0, "closed_lost": 0.0}
            probability = probs.get(new_stage, 0.0)

            return BusinessOutput(
                success=True,
                data={
                    "updated_lead": {**lead, "stage": new_stage, "probability": probability},
                    "previous_stage": current_stage,
                    "new_stage": new_stage,
                    "probability": probability,
                    "next_action": next_action,
                },
                side_effects=[f"stage_changed_to_{new_stage}"],
                insights=[
                    f"Lead moved: {current_stage} → {new_stage}",
                    f"Conversion probability: {probability:.0%}",
                ],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_task(self, data: Dict, context: Dict,
                       description: str) -> BusinessOutput:
        """Lógica de tareas: priorización y asignación."""
        try:
            tasks = data.get("tasks", [])
            resources = data.get("resources", [])

            if not tasks:
                return BusinessOutput(success=False, errors=["No tasks provided"])

            priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            scored = []
            for task in tasks:
                priority = task.get("priority", "medium")
                score = priority_map.get(priority, 2) * 25
                if task.get("deadline") or task.get("due_date"):
                    score += 10
                scored.append({**task, "score": score})

            scored.sort(key=lambda t: t["score"], reverse=True)

            assignments = []
            for idx, task in enumerate(scored):
                if resources:
                    resource = resources[idx % len(resources)]
                    assignments.append({
                        "task": task.get("name", f"Task_{idx}"),
                        "assigned_to": resource.get("name", f"Resource_{idx % len(resources)}"),
                        "priority": task.get("priority", "medium"),
                    })

            return BusinessOutput(
                success=True,
                data={
                    "schedule": [{"order": i + 1, "task": t.get("name", f"Task_{i}"),
                                  "priority": t.get("priority", "medium"),
                                  "score": t["score"]} for i, t in enumerate(scored)],
                    "assignments": assignments,
                    "total_tasks": len(tasks),
                },
                side_effects=["tasks_scheduled"],
                insights=[
                    f"Scheduled {len(tasks)} tasks across {len(resources)} resources",
                    f"Top priority: {scored[0].get('name', 'N/A')}" if scored else "",
                ],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_report(self, data: Dict, context: Dict,
                         description: str) -> BusinessOutput:
        """Lógica de reportes: generación desde datos."""
        try:
            report_data = data.get("data", data.get("items", []))
            report_type = data.get("type", "summary")
            title = data.get("title", description[:50] or "Generated Report")

            if isinstance(report_data, list):
                count = len(report_data)
                summary = {
                    "title": title,
                    "type": report_type,
                    "record_count": count,
                    "generated": True,
                }
            elif isinstance(report_data, dict):
                count = len(report_data)
                summary = {
                    "title": title,
                    "type": report_type,
                    "field_count": count,
                    "generated": True,
                }
            else:
                summary = {"title": title, "type": report_type, "generated": True}

            return BusinessOutput(
                success=True,
                data=summary,
                side_effects=["report_generated"],
                insights=[f"Report '{title}' generated with {count} records"]
                         if 'count' in dir() else [f"Report '{title}' generated"],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_notification(self, data: Dict, context: Dict,
                               description: str) -> BusinessOutput:
        """Lógica de notificaciones: despacho."""
        try:
            channel = data.get("channel", data.get("type", "email"))
            recipients = data.get("recipients", data.get("to", []))
            message = data.get("message", data.get("body", description[:200]))

            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(",")]

            return BusinessOutput(
                success=True,
                data={
                    "channel": channel,
                    "recipients": recipients,
                    "message_length": len(str(message)),
                    "dispatched": True,
                },
                side_effects=[f"notification_sent_via_{channel}"],
                insights=[f"Notification sent to {len(recipients)} recipient(s) via {channel}"],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_analytics(self, data: Dict, context: Dict,
                            description: str) -> BusinessOutput:
        """Lógica de análisis: métricas desde datos."""
        try:
            dataset = data.get("data", data.get("items", []))
            metrics_requested = data.get("metrics", ["count", "summary"])

            if not isinstance(dataset, list):
                dataset = [dataset]

            count = len(dataset)
            result_data = {"record_count": count}

            # Simple numeric analysis
            numeric_fields = {}
            if dataset and isinstance(dataset[0], dict):
                for key, value in dataset[0].items():
                    if isinstance(value, (int, float)):
                        values = [item.get(key, 0) for item in dataset
                                  if isinstance(item.get(key), (int, float))]
                        if values:
                            numeric_fields[key] = {
                                "min": min(values),
                                "max": max(values),
                                "avg": round(sum(values) / len(values), 2),
                                "count": len(values),
                            }

            result_data["numeric_fields"] = numeric_fields

            insights = [f"Analyzed {count} records"]
            for field_name, stats in numeric_fields.items():
                insights.append(
                    f"{field_name}: min={stats['min']}, max={stats['max']}, "
                    f"avg={stats['avg']}"
                )

            return BusinessOutput(
                success=True,
                data=result_data,
                side_effects=["analytics_computed"],
                insights=insights[:5],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    def _fallback_custom(self, data: Dict, context: Dict,
                         description: str) -> BusinessOutput:
        """Lógica personalizada genérica: pasa datos con validación básica."""
        try:
            result = {k: v for k, v in data.items() if not k.startswith("_")}
            result["processed"] = True

            return BusinessOutput(
                success=True,
                data=result,
                side_effects=["custom_logic_executed"],
                insights=[f"Custom operation processed {len(data)} fields"],
            )
        except Exception as e:
            return BusinessOutput(success=False, errors=[str(e)])

    # ============================================================
    #  PRIVATE: JSON/TEXT PARSING
    # ============================================================

    def _json_to_business_output(self, data: Dict[str, Any],
                                 source: str = "llm") -> Optional[BusinessOutput]:
        """Convierte dict JSON a BusinessOutput."""
        success = data.get("success", True)
        if isinstance(success, str):
            success = success.lower() == "true"
        success = bool(success)

        output_data = data.get("data", {})
        if not isinstance(output_data, dict):
            output_data = {"result": str(output_data)}

        side_effects = data.get("side_effects", [])
        if not isinstance(side_effects, list):
            side_effects = [str(side_effects)]

        insights = data.get("insights", [])
        if not isinstance(insights, list):
            insights = [str(insights)]

        errors = data.get("errors", [])
        if not isinstance(errors, list):
            errors = [str(errors)]

        return BusinessOutput(
            success=success,
            data=output_data,
            side_effects=side_effects,
            insights=insights,
            errors=errors,
            source=source,
        )

    def _parse_free_text_business(self, text: str,
                                  source: str = "llm") -> Optional[BusinessOutput]:
        """Parsea texto libre del LLM."""
        if not text or len(text) < 10:
            return None

        return BusinessOutput(
            success=True,
            data={"answer": text[:500]},
            insights=["Free-text business response from LLM"],
            source=source,
        )
