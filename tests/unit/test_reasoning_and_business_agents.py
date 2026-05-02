"""
Unit tests for ReasoningAgent and BusinessLogicAgent (Phase F3)

Tests the unified reasoning and business logic agents that replace
ReasoningEngine + ThinkingEngine + 30+ LogicBlocks.
"""

import pytest
from unittest.mock import MagicMock

from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
from src.core.agents.schemas import ReasoningInput, ReasoningOutput, BusinessInput, BusinessOutput
from src.core.agents.base import AgentResult


# ============================================================
#  ReasoningAgent Fixtures
# ============================================================

@pytest.fixture
def reasoning_agent():
    return ReasoningAgent()


@pytest.fixture
def reasoning_agent_with_memory():
    agent = ReasoningAgent()
    mock_memory = MagicMock()
    mock_memory.check_cache.return_value = None
    mock_memory.save_to_cache = MagicMock()
    mock_memory.get_working_context.return_value = ""
    mock_memory.find_similar_solutions.return_value = []
    agent.wire(smart_memory=mock_memory)
    return agent, mock_memory


# ============================================================
#  ReasoningAgent: Fallback Reasoning
# ============================================================

class TestReasoningAgentFallback:
    """Tests for deterministic fallback reasoning."""

    def test_api_problem_type(self, reasoning_agent):
        """Should detect API problems and provide template response."""
        result = reasoning_agent.fallback(ReasoningInput(query="How to create a REST API?"))
        assert result.source == "fallback"
        assert "API" in result.answer or "api" in result.answer.lower()

    def test_auth_problem_type(self, reasoning_agent):
        """Should detect auth problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="Implement login auth"))
        assert result.source == "fallback"
        assert "auth" in result.answer.lower() or "JWT" in result.answer

    def test_invoice_problem_type(self, reasoning_agent):
        """Should detect invoice problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build invoice system"))
        assert result.source == "fallback"
        assert "invoice" in result.answer.lower() or "factura" in result.answer.lower()

    def test_crm_problem_type(self, reasoning_agent):
        """Should detect CRM problems."""
        result = reasoning_agent.fallback(ReasoningInput(query="CRM for customers"))
        assert result.source == "fallback"
        assert "crm" in result.answer.lower() or "CRM" in result.answer

    def test_unknown_problem_type(self, reasoning_agent):
        """Should handle unknown problem types with generic response."""
        result = reasoning_agent.fallback(ReasoningInput(query="Random question about life"))
        assert result.source == "fallback"
        assert result.answer  # Should produce some answer

    def test_fallback_steps_structure(self, reasoning_agent):
        """Should produce structured reasoning steps."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build auth system", max_steps=3))
        assert len(result.steps) >= 1
        assert result.steps[0].step_number == 1
        assert result.steps[0].description
        assert result.steps[0].conclusion

    def test_fallback_confidence_is_low(self, reasoning_agent):
        """Fallback confidence should be in the 0-0.5 range."""
        result = reasoning_agent.fallback(ReasoningInput(query="Build something"))
        assert 0.0 <= result.confidence <= 0.5

    def test_mode_preserved(self, reasoning_agent):
        """Should preserve the requested reasoning mode."""
        result = reasoning_agent.fallback(ReasoningInput(query="test", mode="self_reflect"))
        assert result.mode == "self_reflect"

    def test_spanish_query(self, reasoning_agent):
        """Should handle Spanish queries."""
        result = reasoning_agent.fallback(ReasoningInput(query="crear sistema de autenticación"))
        assert result.source == "fallback"
        assert result.answer


class TestReasoningAgentLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt_step_by_step(self, reasoning_agent):
        """Should build step_by_step prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="How to build an API?", mode="step_by_step")
        )
        assert "step-by-step" in system.lower() or "step by step" in system.lower()
        assert "build an API" in user

    def test_build_prompt_self_reflect(self, reasoning_agent):
        """Should build self_reflect prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="Is this correct?", mode="self_reflect")
        )
        assert "self-reflect" in system.lower() or "critique" in system.lower()

    def test_build_prompt_with_context(self, reasoning_agent):
        """Should build with_context prompt."""
        system, user = reasoning_agent.build_prompt(
            ReasoningInput(query="Build auth", mode="with_context", context="Using FastAPI")
        )
        assert "context" in system.lower() or "context" in user.lower()

    def test_parse_json_response(self, reasoning_agent):
        """Should parse valid JSON reasoning response."""
        raw = '{"answer":"Use JWT tokens","confidence":0.8,"steps":[{"step_number":1,"description":"Setup auth","conclusion":"Use JWT"}],"refinements":0}'
        result = reasoning_agent.parse_response(raw, None)
        assert result is not None
        assert result.answer == "Use JWT tokens"
        assert result.confidence == 0.8
        assert len(result.steps) == 1
        assert result.source == "llm"

    def test_parse_free_text_response(self, reasoning_agent):
        """Should parse free text when no JSON found."""
        raw = "The best approach is to use JWT tokens for authentication. Therefore, implement JWT middleware."
        result = reasoning_agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_parse_empty_response(self, reasoning_agent):
        """Should handle empty responses."""
        result = reasoning_agent.parse_response("", None)
        assert result is None

    def test_reason_with_runner_llm_success(self, reasoning_agent):
        """Should use LLM result when runner succeeds."""
        mock_runner = MagicMock()
        llm_output = ReasoningOutput(
            answer="Use FastAPI", confidence=0.8, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = reasoning_agent.reason_with_runner(mock_runner, "Build API")
        assert result.answer == "Use FastAPI"
        assert result.source == "llm"

    def test_reason_with_runner_fallback(self, reasoning_agent):
        """Should use fallback when runner fails."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error"
        )
        result = reasoning_agent.reason_with_runner(mock_runner, "Build auth")
        assert result.source == "fallback"


class TestReasoningAgentConversion:
    """Tests for ReasoningOutput → ReasoningResult conversion."""

    def test_to_reasoning_result(self, reasoning_agent):
        """Should convert to ReasoningResult correctly."""
        from src.core.reasoning_engine import ReasoningMode, ReasoningResult

        output = ReasoningOutput(
            answer="Use JWT",
            confidence=0.7,
            mode="step_by_step",
            steps=[],
            source="llm",
        )
        result = reasoning_agent.to_reasoning_result(output)
        assert isinstance(result, ReasoningResult)
        assert result.answer == "Use JWT"
        assert result.mode == ReasoningMode.STEP_BY_STEP
        assert result.source == "llm"

    def test_to_reasoning_result_self_reflect(self, reasoning_agent):
        """Should map self_reflect mode correctly."""
        from src.core.reasoning_engine import ReasoningMode

        output = ReasoningOutput(mode="self_reflect")
        result = reasoning_agent.to_reasoning_result(output)
        assert result.mode == ReasoningMode.SELF_REFLECT


class TestReasoningAgentEdgeCases:
    """Edge case tests for ReasoningAgent."""

    def test_empty_query(self, reasoning_agent):
        """Should handle empty queries."""
        result = reasoning_agent.fallback(ReasoningInput(query=""))
        assert result is not None
        assert result.source == "fallback"

    def test_very_long_query(self, reasoning_agent):
        """Should handle very long queries."""
        long_query = "How to build " + "an API " * 200
        result = reasoning_agent.fallback(ReasoningInput(query=long_query))
        assert result is not None

    def test_stats_tracking(self, reasoning_agent):
        """Should track stats after fallback."""
        reasoning_agent.fallback(ReasoningInput(query="test"))
        stats = reasoning_agent.stats
        assert stats["name"] == "reasoning"
        assert stats["total_calls"] >= 1

    def test_wire_semantic_engine(self, reasoning_agent):
        """Should accept semantic engine via wire()."""
        mock_sem = MagicMock()
        mock_sem.is_loaded = True
        reasoning_agent.wire(semantic_engine=mock_sem)
        assert reasoning_agent._semantic_engine is mock_sem


# ============================================================
#  BusinessLogicAgent: Fallback Business Logic
# ============================================================

class TestBusinessLogicAgentFallback:
    """Tests for deterministic fallback business logic."""

    def test_invoice_calculation(self):
        """Should calculate invoices correctly."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {
            "items": [{"name": "Widget", "quantity": 2, "price": 10.0}],
            "tax_rate": 0.16,
            "discount": 0,
        })
        assert result.success is True
        assert result.data["subtotal"] == 20.0
        assert result.data["tax_amount"] == 3.2
        assert result.data["total"] == 23.2

    def test_invoice_with_discount(self):
        """Should calculate invoices with discount."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {
            "items": [{"name": "Widget", "quantity": 1, "price": 100.0}],
            "tax_rate": 0.10,
            "discount": 10,
        })
        assert result.success is True
        assert result.data["subtotal"] == 100.0
        assert result.data["discount_amount"] == 10.0
        assert result.data["tax_amount"] == 9.0  # 90 * 0.10
        assert result.data["total"] == 99.0

    def test_invoice_no_items(self):
        """Should fail gracefully when no items provided."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("invoice", {"items": []})
        assert result.success is False
        assert len(result.errors) > 0

    def test_inventory_add(self):
        """Should handle inventory add operation."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 5,
            "operation": "add",
            "current_quantity": 10,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 15
        assert result.data["change"] == 5

    def test_inventory_remove(self):
        """Should handle inventory remove operation."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 3,
            "operation": "remove",
            "current_quantity": 10,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 7

    def test_inventory_low_stock_alert(self):
        """Should generate low stock alert."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 8,
            "operation": "remove",
            "current_quantity": 10,
            "low_stock_threshold": 5,
        })
        assert result.success is True
        assert result.data["new_quantity"] == 2
        assert result.data["low_stock"] is True
        assert len(result.data["alerts"]) > 0

    def test_crm_advance_stage(self):
        """Should advance CRM pipeline stage."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("crm", {
            "current_stage": "new",
            "action": "advance",
        })
        assert result.success is True
        assert result.data["new_stage"] == "contacted"
        assert result.data["probability"] == 0.20

    def test_crm_close_won(self):
        """Should close CRM lead as won."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("crm", {
            "current_stage": "negotiation",
            "action": "close_won",
        })
        assert result.success is True
        assert result.data["new_stage"] == "closed_won"
        assert result.data["probability"] == 1.0

    def test_task_scheduling(self):
        """Should schedule and assign tasks."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("task", {
            "tasks": [
                {"name": "Fix bug", "priority": "critical"},
                {"name": "Add feature", "priority": "medium"},
            ],
            "resources": [{"name": "Alice"}, {"name": "Bob"}],
        })
        assert result.success is True
        assert result.data["total_tasks"] == 2
        assert len(result.data["assignments"]) == 2
        # Critical task should be first (higher score)
        assert result.data["schedule"][0]["task"] == "Fix bug"

    def test_notification_dispatch(self):
        """Should dispatch notifications."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("notification", {
            "channel": "email",
            "recipients": "alice@test.com, bob@test.com",
            "message": "Hello!",
        })
        assert result.success is True
        assert result.data["channel"] == "email"
        assert len(result.data["recipients"]) == 2

    def test_analytics(self):
        """Should compute analytics."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("analytics", {
            "data": [
                {"name": "A", "value": 10},
                {"name": "B", "value": 20},
                {"name": "C", "value": 30},
            ],
        })
        assert result.success is True
        assert result.data["record_count"] == 3
        assert "value" in result.data["numeric_fields"]
        assert result.data["numeric_fields"]["value"]["avg"] == 20.0

    def test_report_generation(self):
        """Should generate reports."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("report", {
            "title": "Sales Report",
            "data": [{"id": 1}, {"id": 2}],
        })
        assert result.success is True
        assert result.data["title"] == "Sales Report"
        assert result.data["record_count"] == 2

    def test_custom_operation(self):
        """Should handle custom operations."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("custom", {
            "field1": "value1",
            "field2": 42,
        })
        assert result.success is True
        assert result.data["processed"] is True


class TestBusinessLogicAgentLLMPath:
    """Tests for LLM prompt building and response parsing."""

    def test_build_prompt(self):
        """Should build business logic prompt."""
        agent = BusinessLogicAgent()
        system, user = agent.build_prompt(BusinessInput(
            operation_type="invoice",
            data={"items": [{"name": "Widget", "quantity": 1, "price": 10}]},
            description="Calculate invoice total",
        ))
        assert "business logic" in system.lower()
        assert "invoice" in user.lower()

    def test_parse_json_response(self):
        """Should parse valid JSON business response."""
        agent = BusinessLogicAgent()
        raw = '{"success":true,"data":{"total":23.2},"side_effects":["invoice_calculated"],"insights":["Total calculated"],"errors":[]}'
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.success is True
        assert result.data["total"] == 23.2
        assert result.source == "llm"

    def test_parse_free_text(self):
        """Should parse free text business response."""
        agent = BusinessLogicAgent()
        raw = "The invoice total is 23.20 including tax."
        result = agent.parse_response(raw, None)
        assert result is not None
        assert result.source == "llm"

    def test_execute_with_runner_llm(self):
        """Should use LLM result when runner succeeds."""
        agent = BusinessLogicAgent()
        mock_runner = MagicMock()
        llm_output = BusinessOutput(
            success=True, data={"total": 50.0}, source="llm"
        )
        mock_runner.run.return_value = AgentResult(
            success=True, data=llm_output, source="llm"
        )
        result = agent.execute_with_runner(mock_runner, "invoice", {"items": []})
        assert result.source == "llm"

    def test_execute_with_runner_fallback(self):
        """Should fallback when runner fails."""
        agent = BusinessLogicAgent()
        mock_runner = MagicMock()
        mock_runner.run.return_value = AgentResult(
            success=False, data=None, source="error"
        )
        result = agent.execute_with_runner(
            mock_runner, "invoice",
            {"items": [{"name": "X", "quantity": 1, "price": 10}]},
        )
        assert result.source == "fallback"
        assert result.success is True


class TestBusinessLogicAgentEdgeCases:
    """Edge case tests for BusinessLogicAgent."""

    def test_invalid_operation_type(self):
        """Should use custom handler for unknown types."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("unknown_type", {"data": "test"})
        assert result.success is True  # Custom handler always succeeds

    def test_stats_tracking(self):
        """Should track stats after operations."""
        agent = BusinessLogicAgent()
        agent.execute_business("custom", {"field": "value"})
        stats = agent.stats
        assert stats["name"] == "business_logic"
        assert stats["total_calls"] >= 1

    def test_wire_dependencies(self):
        """Should accept dependencies via wire()."""
        agent = BusinessLogicAgent()
        mock_sem = MagicMock()
        mock_mem = MagicMock()
        agent.wire(semantic_engine=mock_sem, smart_memory=mock_mem)
        assert agent._semantic_engine is mock_sem
        assert agent._smart_memory is mock_mem

    def test_inventory_zero_stock(self):
        """Should handle zero stock correctly."""
        agent = BusinessLogicAgent()
        result = agent.execute_business("inventory", {
            "product_id": "P001",
            "quantity_change": 10,
            "operation": "remove",
            "current_quantity": 5,
        })
        assert result.data["new_quantity"] == 0
        assert any(a["type"] == "out_of_stock" for a in result.data["alerts"])
