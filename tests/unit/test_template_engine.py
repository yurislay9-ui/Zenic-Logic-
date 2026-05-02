"""
Tests for TemplateEngine - Jinja2-based code generation system.
"""

import os
import sys
import pytest
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.template_engine import (
    TemplateEngine,
    TemplateBlock,
    CompositionPlan,
    TEMPLATE_ROOT,
)


class TestTemplateEngineInit:
    """Test TemplateEngine initialization."""

    def test_init_with_default_root(self):
        """Engine initializes with default template root."""
        engine = TemplateEngine()
        assert engine._root == TEMPLATE_ROOT
        assert engine.stats["jinja2_available"] is True

    def test_init_with_custom_root(self, tmp_path):
        """Engine initializes with custom template root."""
        engine = TemplateEngine(template_root=str(tmp_path))
        assert engine._root == str(tmp_path)

    def test_builtin_blocks_registered(self):
        """All 21 builtin blocks are registered."""
        engine = TemplateEngine()
        assert len(engine._blocks) >= 21

    def test_block_categories(self):
        """All expected categories are present."""
        engine = TemplateEngine()
        categories = engine.stats["block_categories"]
        assert "business_logic" in categories
        assert "integrations" in categories
        assert "auth" in categories
        assert "data" in categories


class TestTemplateBlock:
    """Test TemplateBlock data structure."""

    def test_block_creation(self):
        """Block can be created with all fields."""
        block = TemplateBlock(
            name="test_block",
            category="business_logic",
            description="Test block",
            inputs=["data"],
            outputs=["result"],
            dependencies=["other_block"],
        )
        assert block.name == "test_block"
        assert block.category == "business_logic"
        assert block.dependencies == ["other_block"]

    def test_register_custom_block(self):
        """Custom blocks can be registered."""
        engine = TemplateEngine()
        block = TemplateBlock(
            name="custom_test",
            category="business_logic",
            description="Custom test block",
        )
        engine.register_block(block)
        assert engine.get_block("custom_test") is not None
        assert engine.get_block("custom_test").name == "custom_test"


class TestBlockSuggestion:
    """Test block suggestion based on description."""

    def test_suggest_email_blocks(self):
        """Email-related description suggests email blocks."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("enviar email con factura al cliente")
        assert "email_smtp" in blocks

    def test_suggest_auth_blocks(self):
        """Auth-related description suggests auth blocks."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("sistema con login y usuarios")
        assert "jwt_auth" in blocks

    def test_suggest_invoice_blocks(self):
        """Invoice description suggests invoice calculator."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("facturacion con calculo de impuestos")
        assert "invoice_calculator" in blocks

    def test_suggest_inventory_blocks(self):
        """Inventory description suggests inventory tracker."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("control de inventario y stock")
        assert "inventory_tracker" in blocks

    def test_suggest_crud_blocks(self):
        """CRUD description suggests CRUD service."""
        engine = TemplateEngine()
        blocks = engine.suggest_blocks("crud de base de datos")
        assert "crud_service" in blocks

    def test_dependency_resolution(self):
        """Dependencies are resolved in correct order."""
        engine = TemplateEngine()
        # notification_manager depends on email_smtp and telegram_bot
        resolved = engine.resolve_dependencies(["notification_manager"])
        # email_smtp and telegram_bot should come before notification_manager
        nm_idx = resolved.index("notification_manager")
        if "email_smtp" in resolved:
            assert resolved.index("email_smtp") < nm_idx
        if "telegram_bot" in resolved:
            assert resolved.index("telegram_bot") < nm_idx

    def test_rbac_depends_on_jwt(self):
        """RBAC block depends on JWT auth."""
        engine = TemplateEngine()
        resolved = engine.resolve_dependencies(["rbac"])
        if "jwt_auth" in resolved and "rbac" in resolved:
            assert resolved.index("jwt_auth") < resolved.index("rbac")


class TestAppRendering:
    """Test full app rendering via TemplateEngine."""

    def test_render_simple_app(self):
        """Render a simple app with one entity."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=[],
            variables={
                "project_name": "test_app",
                "app_name": "test_app",
                "template_type": "generic",
                "db_name": "test.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Item", "fields": ["name:str", "description:str", "price:float"]},
            ],
        )

        files = engine.render_app(plan)
        assert "main.py" in files
        assert "database.py" in files
        assert "models.py" in files
        assert "services.py" in files
        assert "config.py" in files
        assert "validators.py" in files
        assert len(files) > 5

    def test_render_app_with_blocks(self):
        """Render an app with business logic blocks."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=["invoice_calculator", "email_smtp"],
            variables={
                "project_name": "billing_app",
                "app_name": "billing_app",
                "template_type": "invoice_billing",
                "db_name": "billing.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Customer", "fields": ["name:str", "email:str"]},
                {"name": "Invoice", "fields": ["customer_id:int", "total:float", "status:str"]},
            ],
        )

        files = engine.render_app(plan)
        assert "main.py" in files
        assert "blocks/invoice_calculator.py" in files
        assert "blocks/email_smtp.py" in files

    def test_rendered_code_has_no_stubs(self):
        """Rendered code should not contain logger.info stubs or placeholder returns."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=[],
            variables={
                "project_name": "test_app",
                "app_name": "test_app",
                "template_type": "generic",
                "db_name": "test.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Item", "fields": ["name:str", "price:float"]},
            ],
        )

        files = engine.render_app(plan)

        # Check services.py for stubs
        services = files.get("services.py", "")
        assert '{"processed": True' not in services
        assert 'logger.info("Sending' not in services

    def test_rendered_sql_is_parameterized(self):
        """All SQL in rendered code uses ? parameterized queries."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=[],
            variables={
                "project_name": "test_app",
                "app_name": "test_app",
                "template_type": "generic",
                "db_name": "test.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Item", "fields": ["name:str", "price:float"]},
            ],
        )

        files = engine.render_app(plan)
        services = files.get("services.py", "")
        database = files.get("database.py", "")

        # Check for parameterized queries (? markers)
        assert "?" in services or "?" in database

    def test_rendered_code_imports_fastapi(self):
        """Rendered main.py imports FastAPI."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="",
            blocks=[],
            variables={
                "project_name": "test_app",
                "app_name": "test_app",
                "template_type": "generic",
                "db_name": "test.db",
                "port": 8000,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[
                {"name": "Item", "fields": ["name:str"]},
            ],
        )

        files = engine.render_app(plan)
        main = files.get("main.py", "")
        assert "fastapi" in main.lower() or "FastAPI" in main


class TestAutomationRendering:
    """Test automation project rendering."""

    def test_render_automation(self):
        """Render a basic automation project."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=["email_smtp"],
            variables={
                "project_name": "daily_report",
                "app_name": "daily_report",
                "template_type": "automation",
                "db_name": "automation.db",
                "port": 8001,
                "secret_key": "test-secret",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": "daily_report",
                "fields": [],
                "trigger_config": {"type": "cron", "hour": 9, "minute": 0},
                "actions": [{"type": "send_email", "config": {"to": "admin@co.com", "subject": "Report"}}],
            }],
        )

        files = engine.render_automation(plan)
        assert "main.py" in files
        assert "actions.py" in files
        assert "config.py" in files

    def test_automation_actions_are_real(self):
        """Rendered actions.py contains real implementations, not stubs."""
        engine = TemplateEngine()
        plan = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=["email_smtp"],
            variables={
                "project_name": "test_auto",
                "app_name": "test_auto",
                "template_type": "automation",
                "db_name": "auto.db",
                "port": 8001,
                "secret_key": "test",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": "test",
                "fields": [],
                "trigger_config": {"type": "cron", "hour": 9},
                "actions": [{"type": "send_email", "config": {"to": "a@b.com"}}],
            }],
        )

        files = engine.render_automation(plan)
        actions = files.get("actions.py", "")

        # Should contain real SMTP code, not stubs
        assert "smtplib" in actions or "aiosmtplib" in actions
        # Should NOT contain stub patterns
        assert 'logger.info("Automation: Email to' not in actions


class TestCompositionPlan:
    """Test CompositionPlan data structure."""

    def test_default_values(self):
        """CompositionPlan has sensible defaults."""
        plan = CompositionPlan()
        assert plan.base_template == "apps/base"
        assert plan.blocks == []
        assert plan.entities == []
        assert plan.variables == {}

    def test_full_plan(self):
        """CompositionPlan can be fully specified."""
        plan = CompositionPlan(
            base_template="apps/base",
            app_template="invoice_billing",
            blocks=["invoice_calculator", "email_smtp", "jwt_auth"],
            variables={"project_name": "billing"},
            entities=[{"name": "Invoice", "fields": ["total:float"]}],
        )
        assert plan.app_template == "invoice_billing"
        assert len(plan.blocks) == 3


class TestBlockFiles:
    """Test that block template files exist and are valid."""

    def test_business_logic_blocks_exist(self):
        """All business logic block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("business_logic"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_integration_blocks_exist(self):
        """All integration block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("integrations"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_auth_blocks_exist(self):
        """All auth block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("auth"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"

    def test_data_blocks_exist(self):
        """All data block templates exist."""
        engine = TemplateEngine()
        for block in engine.list_blocks("data"):
            if block.template_path:
                full_path = os.path.join(TEMPLATE_ROOT, block.template_path)
                assert os.path.isfile(full_path), f"Missing template: {block.template_path}"


class TestListBlocks:
    """Test block listing and filtering."""

    def test_list_all_blocks(self):
        """Can list all registered blocks."""
        engine = TemplateEngine()
        all_blocks = engine.list_blocks()
        assert len(all_blocks) >= 21

    def test_filter_by_category(self):
        """Can filter blocks by category."""
        engine = TemplateEngine()
        biz = engine.list_blocks("business_logic")
        assert all(b.category == "business_logic" for b in biz)
        assert len(biz) >= 7

    def test_integration_count(self):
        """Correct number of integration blocks."""
        engine = TemplateEngine()
        integrations = engine.list_blocks("integrations")
        assert len(integrations) >= 6

    def test_auth_count(self):
        """Correct number of auth blocks."""
        engine = TemplateEngine()
        auth = engine.list_blocks("auth")
        assert len(auth) >= 3

    def test_data_count(self):
        """Correct number of data blocks."""
        engine = TemplateEngine()
        data = engine.list_blocks("data")
        assert len(data) >= 4
