"""
Unit tests for BusinessLogicAgent.

Tests the agent that replaces 30+ hardcoded LogicBlocks with
AI-driven business logic:
  - Invoice calculation (tax, discount, total)
  - Inventory tracking (stock levels, alerts)
  - CRM pipeline (lead stage advancement)
  - Task scheduling (prioritization, assignment)
  - Report generation
  - Notification dispatch
  - Analytics computation
  - Custom operations
  - Criticality adjustments (F4)
  - LLM response parsing
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.business_logic_agent import BusinessLogicAgent, VALID_OPERATION_TYPES
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.base import AgentResult


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def agent():
    """BusinessLogicAgent without external dependencies (pure fallback mode)."""
    return BusinessLogicAgent()


@pytest.fixture
def agent_with_memory():
    """BusinessLogicAgent with mocked SmartMemory."""
    agent = BusinessLogicAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


# ============================================================
#  Test: Invoice Fallback
# ============================================================

class TestBusinessInvoiceFallback:
    """Tests for invoice calculation fallback logic."""

    def test_invoice_basic_calculation(self, agent):
        """Should calculate subtotal, tax, discount, and total."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={
                "items": [
                    {"name": "Widget", "quantity": 2, "price": 50.0},
                    {"name": "Gadget", "quantity": 1, "price": 100.0},
                ],
                "tax_rate": 0.16,
                "discount": 10,
            },
        ))
        assert result.success is True
        assert result.data["subtotal"] == 200.0
        assert result.data["discount_amount"] == 20.0
        assert result.data["tax_amount"] == 28.8
        assert result.data["total"] == 208.8
        assert result.data["item_count"] == 2
        assert result.source == "fallback"

    def test_invoice_no_discount(self, agent):
        """Should handle zero discount."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={
                "items": [{"name": "A", "quantity": 1, "price": 100.0}],
                "tax_rate": 0.16,
            },
        ))
        assert result.success is True
        assert result.data["discount_amount"] == 0.0
        assert result.data["discount_pct"] == 0

    def test_invoice_no_items(self, agent):
        """Should fail when no items provided."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": []},
        ))
        assert result.success is False
        assert "No items" in result.errors[0]

    def test_invoice_default_tax_rate(self, agent):
        """Should use 0.16 as default tax rate."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        ))
        assert result.success is True
        assert result.data["tax_rate"] == 0.16


# ============================================================
#  Test: Inventory Fallback
# ============================================================

class TestBusinessInventoryFallback:
    """Tests for inventory tracking fallback logic."""

    def test_inventory_add_stock(self, agent):
        """Should add stock correctly."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P001",
                "quantity_change": 10,
                "operation": "add",
                "current_quantity": 5,
            },
        ))
        assert result.success is True
        assert result.data["new_quantity"] == 15
        assert result.data["previous_quantity"] == 5

    def test_inventory_remove_stock(self, agent):
        """Should remove stock and not go below zero."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P001",
                "quantity_change": 20,
                "operation": "remove",
                "current_quantity": 15,
            },
        ))
        assert result.success is True
        assert result.data["new_quantity"] == 0
        assert any(a["type"] == "out_of_stock" for a in result.data["alerts"])

    def test_inventory_low_stock_alert(self, agent):
        """Should trigger low stock alert when below threshold."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P002",
                "quantity_change": 8,
                "operation": "remove",
                "current_quantity": 15,
                "low_stock_threshold": 10,
            },
        ))
        assert result.data["low_stock"] is True
        assert any(a["type"] == "low_stock" for a in result.data["alerts"])

    def test_inventory_set_stock(self, agent):
        """Should set stock to exact value."""
        result = agent.fallback(BusinessInput(
            operation_type="inventory",
            data={
                "product_id": "P003",
                "quantity_change": 50,
                "operation": "set",
                "current_quantity": 30,
            },
        ))
        assert result.data["new_quantity"] == 50


# ============================================================
#  Test: CRM Fallback
# ============================================================

class TestBusinessCRMFallback:
    """Tests for CRM pipeline fallback logic."""

    def test_crm_advance_stage(self, agent):
        """Should advance lead to next stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "lead_data": {"name": "Acme Corp"},
                "current_stage": "new",
                "action": "advance",
            },
        ))
        assert result.success is True
        assert result.data["new_stage"] == "contacted"
        assert result.data["previous_stage"] == "new"

    def test_crm_close_won(self, agent):
        """Should move lead to closed_won stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "lead_data": {"name": "Big Corp"},
                "current_stage": "negotiation",
                "action": "close_won",
            },
        ))
        assert result.data["new_stage"] == "closed_won"
        assert result.data["probability"] == 1.0
        assert "Send onboarding" in result.data["next_action"]

    def test_crm_close_lost(self, agent):
        """Should move lead to closed_lost stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "current_stage": "proposal",
                "action": "close_lost",
            },
        ))
        assert result.data["new_stage"] == "closed_lost"
        assert result.data["probability"] == 0.0

    def test_crm_regress_stage(self, agent):
        """Should regress lead to previous stage."""
        result = agent.fallback(BusinessInput(
            operation_type="crm",
            data={
                "current_stage": "proposal",
                "action": "regress",
            },
        ))
        assert result.data["new_stage"] == "qualified"


# ============================================================
#  Test: Task Fallback
# ============================================================

class TestBusinessTaskFallback:
    """Tests for task scheduling fallback logic."""

    def test_task_prioritization(self, agent):
        """Should sort tasks by priority score."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={
                "tasks": [
                    {"name": "Low task", "priority": "low"},
                    {"name": "Critical task", "priority": "critical"},
                    {"name": "Medium task", "priority": "medium"},
                ],
            },
        ))
        assert result.success is True
        schedule = result.data["schedule"]
        assert schedule[0]["task"] == "Critical task"
        assert schedule[-1]["task"] == "Low task"

    def test_task_assignment(self, agent):
        """Should assign tasks to resources round-robin."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={
                "tasks": [
                    {"name": "Task A", "priority": "high"},
                    {"name": "Task B", "priority": "medium"},
                ],
                "resources": [
                    {"name": "Alice"},
                    {"name": "Bob"},
                ],
            },
        ))
        assignments = result.data["assignments"]
        assert len(assignments) == 2
        assert assignments[0]["assigned_to"] == "Alice"
        assert assignments[1]["assigned_to"] == "Bob"

    def test_task_no_tasks(self, agent):
        """Should fail when no tasks provided."""
        result = agent.fallback(BusinessInput(
            operation_type="task",
            data={"tasks": []},
        ))
        assert result.success is False
        assert "No tasks" in result.errors[0]


# ============================================================
#  Test: Report / Notification / Analytics / Custom Fallbacks
# ============================================================

class TestBusinessOtherFallbacks:
    """Tests for report, notification, analytics, and custom fallbacks."""

    def test_report_generation_list(self, agent):
        """Should generate a report summary from list data."""
        result = agent.fallback(BusinessInput(
            operation_type="report",
            data={
                "data": [{"id": 1}, {"id": 2}],
                "title": "Sales Report",
            },
        ))
        assert result.success is True
        assert result.data["title"] == "Sales Report"
        assert result.data["record_count"] == 2

    def test_notification_dispatch(self, agent):
        """Should dispatch a notification."""
        result = agent.fallback(BusinessInput(
            operation_type="notification",
            data={
                "channel": "email",
                "recipients": ["user@example.com"],
                "message": "Hello!",
            },
        ))
        assert result.success is True
        assert result.data["channel"] == "email"
        assert result.data["dispatched"] is True

    def test_notification_string_recipients(self, agent):
        """Should handle comma-separated string recipients."""
        result = agent.fallback(BusinessInput(
            operation_type="notification",
            data={
                "recipients": "a@x.com, b@x.com",
            },
        ))
        assert len(result.data["recipients"]) == 2

    def test_analytics_basic(self, agent):
        """Should compute basic analytics from data."""
        result = agent.fallback(BusinessInput(
            operation_type="analytics",
            data={
                "data": [
                    {"age": 25, "salary": 50000},
                    {"age": 35, "salary": 70000},
                    {"age": 45, "salary": 90000},
                ],
            },
        ))
        assert result.success is True
        assert result.data["record_count"] == 3
        assert "age" in result.data["numeric_fields"]
        assert "salary" in result.data["numeric_fields"]

    def test_custom_operation(self, agent):
        """Should pass through custom data with processed flag."""
        result = agent.fallback(BusinessInput(
            operation_type="custom",
            data={"key1": "value1", "_internal": "hidden"},
        ))
        assert result.success is True
        assert result.data["processed"] is True
        assert "key1" in result.data
        assert "_internal" not in result.data


# ============================================================
#  Test: Criticality Adjustments (F4)
# ============================================================

class TestBusinessCriticalityAdjustments:
    """Tests for F4 criticality-aware adjustments on business logic."""

    def test_no_adjustments_by_default(self, agent):
        """Should not modify result when no adjustments set."""
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        # No F4 audit entries should be present
        assert not any("F4:" in i for i in result.insights)

    def test_audit_trail_adjustment(self, agent):
        """Should add audit trail when audit_trail is enabled."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": True,
                "validation_layers": 1,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("audit:" in se for se in result.side_effects)
        assert "_audit" in result.data

    def test_validation_layers_2(self, agent):
        """Should add data integrity insight for validation layers >= 2."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 2,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Data integrity check" in i for i in result.insights)

    def test_validation_layers_3_with_rollback(self, agent):
        """Should add rollback and cross-reference insights for level 3."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 3,
                "rollback": True,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Cross-reference" in i for i in result.insights)
        assert any("Rollback" in i for i in result.insights)

    def test_idempotency_check(self, agent):
        """Should add idempotency insight when enabled."""
        agent.set_criticality_adjustments({
            "business_agent": {
                "audit_trail": False,
                "validation_layers": 1,
                "idempotency_check": True,
            }
        })
        result = agent.fallback(BusinessInput(
            operation_type="invoice",
            data={"items": [{"quantity": 1, "price": 50.0}]},
        ))
        assert any("Idempotency" in i for i in result.insights)


# ============================================================
#  Test: LLM Path (build_prompt + parse_response)
# ============================================================

class TestBusinessLLMPath:
    """Tests for the LLM prompt building and response parsing."""

    def test_build_prompt_with_business_input(self, agent):
        """Should build system + user prompt from BusinessInput."""
        system, user = agent.build_prompt(BusinessInput(
            operation_type="invoice",
            data={"items": [{"price": 100}]},
            context={"region": "MX"},
            description="Calculate invoice total",
        ))
        assert "business" in system.lower()
        assert "invoice" in user

    def test_build_prompt_with_string(self, agent):
        """Should build prompt from plain string."""
        system, user = agent.build_prompt("simple business operation")
        assert "business" in system.lower()
        assert "custom" in user  # defaults to "custom" op type

    def test_parse_response_valid_json(self, agent):
        """Should parse valid JSON response from LLM."""
        raw = '{"success":true,"data":{"total":116},"side_effects":["calculated"],"insights":["done"],"errors":[]}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert result.data["total"] == 116
        assert result.source == "llm"

    def test_parse_response_free_text(self, agent):
        """Should parse free text when no JSON is found."""
        raw = "The invoice total is 116.0 with tax applied"
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert "answer" in result.data

    def test_parse_response_empty_text(self, agent):
        """Should return None for very short/empty text."""
        result = agent.parse_response("short", None)
        assert result is None


# ============================================================
#  Test: High-Level API
# ============================================================

class TestBusinessHighLevelAPI:
    """Tests for execute_business and execute_with_runner."""

    def test_execute_business_direct(self, agent):
        """Should execute business logic directly without LLM."""
        result = agent.execute_business(
            operation_type="invoice",
            data={"items": [{"quantity": 2, "price": 50.0}]},
        )
        assert result.success is True
        assert result.data["subtotal"] == 100.0

    def test_execute_with_runner_success(self, agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = BusinessOutput(
            success=True,
            data={"total": 200},
            source="llm",
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        )
        assert result.data["total"] == 200
        assert result.source == "llm"

    def test_execute_with_runner_failure_falls_back(self, agent):
        """Should fall back to deterministic logic when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, error="LLM timeout"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            data={"items": [{"quantity": 1, "price": 100.0}]},
        )
        assert result.success is True
        assert result.source == "fallback"


# ============================================================
#  Test: Wire and Dependencies
# ============================================================

class TestBusinessWireAndDeps:
    """Tests for wire() and dependency injection."""

    def test_wire_semantic_engine(self, agent):
        """Should update semantic engine reference via wire()."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        assert agent._semantic_engine is mock_se

    def test_wire_smart_memory(self, agent):
        """Should update smart memory reference via wire()."""
        mock_mem = MagicMock()
        agent.wire(smart_memory=mock_mem)
        assert agent._smart_memory is mock_mem

    def test_wire_none_does_not_overwrite(self, agent):
        """Wire with None should not overwrite existing reference."""
        mock_se = MagicMock()
        agent.wire(semantic_engine=mock_se)
        agent.wire(semantic_engine=None)
        assert agent._semantic_engine is mock_se

    def test_valid_operation_types(self):
        """VALID_OPERATION_TYPES should include all expected types."""
        assert "invoice" in VALID_OPERATION_TYPES
        assert "inventory" in VALID_OPERATION_TYPES
        assert "crm" in VALID_OPERATION_TYPES
        assert "custom" in VALID_OPERATION_TYPES

    def test_stats_tracking(self, agent):
        """Should track fallback call statistics."""
        agent.fallback(BusinessInput(
            operation_type="custom", data={"x": 1},
        ))
        stats = agent.stats
        assert stats["name"] == "business_logic"
        assert stats["total_calls"] >= 1
