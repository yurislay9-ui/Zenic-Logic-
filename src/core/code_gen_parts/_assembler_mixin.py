"""
CodeAssembler — Connects Jinja2 templates + niche YAML + executors
to generate REAL functional code instead of stubs.

This is the bridge that closes GAP 1:
  Before: CodeGenerator._process() → {"processed": True, "input": payload}
  After:  CodeAssembler assembles real modules from .j2 templates

Architecture:
  1. resolve_modules() — maps intent → blocks → templates
  2. assemble_project() — renders templates + wires imports
  3. build_service_method() — generates _process() with REAL logic
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Block → Template mapping (matches src/templates/blocks/) ──
BLOCK_TEMPLATE_MAP = {
    # Auth
    "jwt_auth": "blocks/auth/jwt_auth.py.j2",
    "api_key_auth": "blocks/auth/api_key_auth.py.j2",
    "rbac": "blocks/auth/rbac.py.j2",
    # Data
    "crud_service": "blocks/data/crud_service.py.j2",
    "seed_data": "blocks/data/seed_data.py.j2",
    "backup_restore": "blocks/data/backup_restore.py.j2",
    "database_migrations": "blocks/data/database_migrations.py.j2",
    # Integrations
    "stripe_payments": "blocks/integrations/stripe_payments.py.j2",
    "email_smtp": "blocks/integrations/email_smtp.py.j2",
    "telegram_bot": "blocks/integrations/telegram_bot.py.j2",
    "webhook_server": "blocks/integrations/webhook_server.py.j2",
    "pdf_generator": "blocks/integrations/pdf_generator.py.j2",
    "google_sheets": "blocks/integrations/google_sheets.py.j2",
    # Business Logic
    "notification_manager": "blocks/business_logic/notification_manager.py.j2",
    "data_analyzer": "blocks/business_logic/data_analyzer.py.j2",
    "inventory_tracker": "blocks/business_logic/inventory_tracker.py.j2",
    "invoice_calculator": "blocks/business_logic/invoice_calculator.py.j2",
    "crm_pipeline": "blocks/business_logic/crm_pipeline.py.j2",
    "report_generator": "blocks/business_logic/report_generator.py.j2",
}

# ── Keyword → Block suggestion mapping ──
KEYWORD_BLOCK_MAP = {
    "auth": ["jwt_auth"],
    "login": ["jwt_auth"],
    "token": ["jwt_auth"],
    "password": ["jwt_auth"],
    "jwt": ["jwt_auth"],
    "rol": ["jwt_auth", "rbac"],
    "rbac": ["rbac"],
    "api key": ["api_key_auth"],
    "crud": ["crud_service"],
    "database": ["crud_service", "backup_restore"],
    "db": ["crud_service"],
    "sql": ["crud_service"],
    "stripe": ["stripe_payments"],
    "payment": ["stripe_payments"],
    "pago": ["stripe_payments"],
    "subscription": ["stripe_payments"],
    "email": ["email_smtp"],
    "correo": ["email_smtp"],
    "smtp": ["email_smtp"],
    "telegram": ["telegram_bot"],
    "bot": ["telegram_bot"],
    "webhook": ["webhook_server"],
    "pdf": ["pdf_generator"],
    "invoice": ["invoice_calculator", "pdf_generator"],
    "factura": ["invoice_calculator", "pdf_generator"],
    "notification": ["notification_manager"],
    "notificacion": ["notification_manager"],
    "analytics": ["data_analyzer"],
    "analisis": ["data_analyzer"],
    "inventory": ["inventory_tracker"],
    "inventario": ["inventory_tracker"],
    "crm": ["crm_pipeline"],
    "backup": ["backup_restore"],
    "report": ["report_generator"],
    "google sheets": ["google_sheets"],
    "seed": ["seed_data"],
}


class CodeAssembler:
    """Assembles real functional code from Jinja2 templates and niche data."""

    def __init__(self, template_engine=None):
        self._template_engine = template_engine

    # ================================================================
    #  PUBLIC API
    # ================================================================

    def resolve_blocks(self, description: str, niche_plan=None) -> List[str]:
        """Resolve which blocks are needed based on description + niche.

        Args:
            description: User's description of what they want
            niche_plan: Optional CompositionPlan from NicheLoader

        Returns:
            Ordered list of block names (dependencies resolved)
        """
        blocks = set()

        # 1. From niche plan if available
        if niche_plan and hasattr(niche_plan, 'blocks'):
            for b in niche_plan.blocks:
                if b in BLOCK_TEMPLATE_MAP:
                    blocks.add(b)

        # 2. From keyword matching
        desc_lower = description.lower()
        for keyword, block_list in KEYWORD_BLOCK_MAP.items():
            if keyword in desc_lower:
                for b in block_list:
                    blocks.add(b)

        # 3. Always add crud_service if entities exist (every app needs CRUD)
        if niche_plan and hasattr(niche_plan, 'entities') and niche_plan.entities:
            if len(niche_plan.entities) > 0:
                blocks.add("crud_service")

        # 4. Resolve dependency order
        return self._resolve_dependencies(list(blocks))

    def assemble_project(self, description: str, niche_plan=None,
                         project_name: str = "titan_app",
                         entities: Optional[List[Dict]] = None) -> Dict[str, str]:
        """Assemble a complete project with REAL functional code.

        Args:
            description: What the user wants to build
            niche_plan: Optional CompositionPlan from NicheLoader
            project_name: Name for the generated project
            entities: List of entity dicts from niche YAML

        Returns:
            Dict mapping filename → file content (all real code)
        """
        blocks = self.resolve_blocks(description, niche_plan)
        entities = entities or []
        if niche_plan and hasattr(niche_plan, 'entities') and niche_plan.entities:
            entities = niche_plan.entities

        # Prepare template variables
        variables = self._prepare_variables(project_name, entities, blocks)

        # Render each block
        files = {}
        for block_name in blocks:
            content = self._render_block(block_name, variables)
            if content:
                files[f"blocks/{block_name}.py"] = content

        # Generate entity models
        if entities:
            models_code = self._generate_pydantic_models(entities, project_name)
            files["models.py"] = models_code

        # Generate main.py with proper imports
        main_code = self._generate_main(project_name, blocks, entities)
        files["main.py"] = main_code

        # Generate requirements.txt
        files["requirements.txt"] = self._generate_requirements(blocks)

        # Generate config
        files["config.py"] = self._generate_config(project_name, entities)

        return files

    def build_service_method(self, entity: Dict, operation: str = "crud") -> str:
        """Build a REAL _process() method for a given entity and operation.

        This replaces the stub: return {"processed": True, "input": payload}
        With actual CRUD/transform/validation logic.

        Args:
            entity: Entity dict with 'name', 'fields', etc.
            operation: Type of operation ("crud", "analytics", "notification", etc.)

        Returns:
            Python code string for the _process method
        """
        entity_name = entity.get("name", "item")
        table_name = entity_name.lower() + "s"
        fields = entity.get("fields", [])

        if operation == "crud":
            return self._build_crud_process(entity_name, table_name, fields)
        elif operation == "analytics":
            return self._build_analytics_process(entity_name, table_name, fields)
        elif operation == "notification":
            return self._build_notification_process(entity_name, fields)
        else:
            return self._build_crud_process(entity_name, table_name, fields)

    # ================================================================
    #  BLOCK RENDERING
    # ================================================================

    def _render_block(self, block_name: str, variables: Dict) -> Optional[str]:
        """Render a single block template with variables."""
        template_path = BLOCK_TEMPLATE_MAP.get(block_name)
        if not template_path:
            logger.warning(f"CodeAssembler: No template for block '{block_name}'")
            return None

        # Try Jinja2 rendering via TemplateEngine
        if self._template_engine:
            try:
                content = self._template_engine.render(template_path, variables)
                if content and len(content) > 50:  # Real content, not empty
                    return content
            except Exception as e:
                logger.warning(f"CodeAssembler: Template render failed for {block_name}: {e}")

        # Fallback: read template file and do simple substitution
        return self._fallback_render(template_path, variables)

    def _fallback_render(self, template_path: str, variables: Dict) -> Optional[str]:
        """Fallback rendering without Jinja2."""
        # Find template file
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        full_path = os.path.join(template_dir, template_path)
        if not os.path.exists(full_path):
            # Try absolute path from project root
            full_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", template_path)

        if not os.path.exists(full_path):
            logger.warning(f"CodeAssembler: Template not found: {template_path}")
            return None

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Simple {{ variable }} substitution
            for key, value in variables.items():
                content = content.replace("{{ " + key + " }}", str(value))
                content = content.replace("{{" + key + "}}", str(value))

            return content
        except Exception as e:
            logger.error(f"CodeAssembler: Fallback render failed: {e}")
            return None

    # ================================================================
    #  CODE GENERATION — REAL LOGIC, NOT STUBS
    # ================================================================

    def _build_crud_process(self, entity_name: str, table_name: str,
                            fields: List[Dict]) -> str:
        """Generate a REAL _process() method with CRUD operations."""
        field_names = [f.get("name", "field") for f in fields]
        param_str = ", ".join('"%s"' % f for f in field_names)
        search_col = field_names[0] if field_names else "name"

        # Use string formatting (not f-string) to avoid nested brace issues
        return '''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """CRUD operations for {entity} — REAL logic, not a stub."""
        action = payload.get("action", "list")
        from src.core.executors.database_executor import DatabaseExecutor

        db = DatabaseExecutor()

        if action == "create":
            data = payload.get("data", {{}})
            columns = [{params}]
            values = [data.get(col) for col in columns]
            placeholders = ", ".join(["?" for _ in columns])
            col_str = ", ".join(columns)
            db.execute_query(
                "INSERT INTO {table} (" + col_str + ") VALUES (" + placeholders + ")",
                values
            )
            return {{"success": True, "action": "create", "entity": "{entity}"}}

        elif action == "read":
            item_id = payload.get("id")
            result = db.execute_query(
                "SELECT * FROM {table} WHERE id = ?", (item_id,)
            )
            return {{"success": True, "data": result, "entity": "{entity}"}}

        elif action == "update":
            item_id = payload.get("id")
            data = payload.get("data", {{}})
            set_parts = [str(k) + " = ?" for k in data.keys()]
            set_clause = ", ".join(set_parts)
            values = list(data.values()) + [item_id]
            db.execute_query(
                "UPDATE {table} SET " + set_clause + " WHERE id = ?", values
            )
            return {{"success": True, "action": "update", "entity": "{entity}"}}

        elif action == "delete":
            item_id = payload.get("id")
            db.execute_query(
                "DELETE FROM {table} WHERE id = ?", (item_id,)
            )
            return {{"success": True, "action": "delete", "entity": "{entity}"}}

        elif action == "list":
            limit = payload.get("limit", 50)
            offset = payload.get("offset", 0)
            result = db.execute_query(
                "SELECT * FROM {table} LIMIT ? OFFSET ?", (limit, offset)
            )
            return {{"success": True, "data": result, "entity": "{entity}"}}

        elif action == "search":
            query = payload.get("query", "")
            column = payload.get("search_column", "{search_col}")
            result = db.execute_query(
                "SELECT * FROM {table} WHERE " + column + " LIKE ?", ("%" + query + "%",)
            )
            return {{"success": True, "data": result, "entity": "{entity}"}}

        return {{"success": False, "error": "Unknown action: " + str(action)}}
'''.format(entity=entity_name, table=table_name, params=param_str, search_col=search_col)

    def _build_analytics_process(self, entity_name: str, table_name: str,
                                  fields: List[Dict]) -> str:
        """Generate a REAL _process() method with analytics logic."""
        numeric_fields = [f for f in fields
                         if f.get("type", "").lower() in ("float", "int", "integer", "number", "decimal")]
        num_names = [f.get("name", "count") for f in numeric_fields] or ["count"]

        return f'''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Analytics for {entity_name} — REAL aggregation logic."""
        action = payload.get("action", "summary")
        from src.core.executors.database_executor import DatabaseExecutor

        db = DatabaseExecutor()

        if action == "summary":
            result = db.execute_query("SELECT COUNT(*) as total FROM {table_name}")
            return {{"success": True, "summary": result, "entity": "{entity_name}"}}

        elif action == "aggregate":
            metric = payload.get("metric", "{num_names[0]}")
            period = payload.get("period", "daily")
            result = db.execute_query(
                f"SELECT date(created_at) as period, {{metric}} FROM {table_name} GROUP BY period ORDER BY period"
            )
            return {{"success": True, "data": result, "metric": metric, "entity": "{entity_name}"}}

        elif action == "distribution":
            column = payload.get("column", "status")
            result = db.execute_query(
                f"SELECT {{column}}, COUNT(*) as count FROM {table_name} GROUP BY {{column}}"
            )
            return {{"success": True, "distribution": result, "entity": "{entity_name}"}}

        return {{"success": False, "error": f"Unknown analytics action: {{action}}"}}
'''

    def _build_notification_process(self, entity_name: str, fields: List[Dict]) -> str:
        """Generate a REAL _process() method for notifications."""
        return f'''
    def _process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Notification for {entity_name} — REAL sending logic."""
        action = payload.get("action", "send")
        from src.core.executors.notification_executor import NotificationExecutor

        notifier = NotificationExecutor()

        if action == "send":
            channel = payload.get("channel", "email")
            message = payload.get("message", "")
            recipient = payload.get("recipient", "")
            result = notifier.execute({{
                "channel": channel,
                "message": message,
                "recipient": recipient,
                "subject": payload.get("subject", "Notification from {entity_name}"),
            }})
            return {{"success": result.success, "channel": channel, "entity": "{entity_name}"}}

        elif action == "broadcast":
            recipients = payload.get("recipients", [])
            message = payload.get("message", "")
            results = []
            for r in recipients:
                result = notifier.execute({{
                    "channel": payload.get("channel", "email"),
                    "message": message,
                    "recipient": r,
                }})
                results.append({{"recipient": r, "success": result.success}})
            return {{"success": True, "results": results, "entity": "{entity_name}"}}

        return {{"success": False, "error": f"Unknown notification action: {{action}}"}}
'''

    # ================================================================
    #  PROJECT SCAFFOLDING
    # ================================================================

    def _generate_pydantic_models(self, entities: List[Dict],
                                   project_name: str) -> str:
        """Generate Pydantic BaseModel classes from entity definitions."""
        lines = [
            f'"""',
            f'{project_name} - Data Models',
            f'Auto-generated by TITAN OMNISCALE X CodeAssembler',
            f'"""',
            '',
            'from typing import Optional, List, Dict, Any',
            'from datetime import datetime',
            'from pydantic import BaseModel, Field, validator',
            '',
            '',
        ]

        for entity in entities:
            name = entity.get("name", "Item")
            fields = entity.get("fields", [])

            # Create model
            lines.append(f'class {name}Create(BaseModel):')
            lines.append(f'    """Create schema for {name}."""')
            for field in fields:
                fname = field.get("name", "field")
                ftype = self._map_type(field.get("type", "str"))
                required = field.get("required", False)
                default = field.get("default")
                if required:
                    lines.append(f'    {fname}: {ftype}')
                elif default is not None:
                    if isinstance(default, str):
                        lines.append(f'    {fname}: {ftype} = "{default}"')
                    else:
                        lines.append(f'    {fname}: {ftype} = {default}')
                else:
                    lines.append(f'    {fname}: Optional[{ftype}] = None')
            lines.append('')
            lines.append('')

            # Update model
            lines.append(f'class {name}Update(BaseModel):')
            lines.append(f'    """Update schema for {name}."""')
            for field in fields:
                fname = field.get("name", "field")
                ftype = self._map_type(field.get("type", "str"))
                lines.append(f'    {fname}: Optional[{ftype}] = None')
            lines.append('')
            lines.append('')

            # Response model
            lines.append(f'class {name}Response(BaseModel):')
            lines.append(f'    """Response schema for {name}."""')
            lines.append(f'    id: int')
            for field in fields:
                fname = field.get("name", "field")
                ftype = self._map_type(field.get("type", "str"))
                lines.append(f'    {fname}: {ftype}')
            lines.append(f'    created_at: Optional[datetime] = None')
            lines.append('')
            lines.append('')

        return '\n'.join(lines)

    def _generate_main(self, project_name: str, blocks: List[str],
                        entities: List[Dict]) -> str:
        """Generate main.py with FastAPI app wiring real blocks."""
        import_lines = [
            f'"""',
            f'{project_name} - Main Application',
            f'Auto-generated by TITAN OMNISCALE X CodeAssembler',
            f'"""',
            '',
            'import os',
            'import logging',
            'from typing import Optional, List, Dict, Any',
            'from fastapi import FastAPI, HTTPException, Depends',
            'from fastapi.middleware.cors import CORSMiddleware',
            '',
            f'app = FastAPI(title="{project_name}", version="1.0.0")',
            '',
            'app.add_middleware(',
            '    CORSMiddleware,',
            '    allow_origins=["*"],',
            '    allow_credentials=True,',
            '    allow_methods=["*"],',
            '    allow_headers=["*"],',
            ')',
            '',
        ]

        # Import blocks
        for block_name in blocks:
            module_name = block_name
            class_name = self._block_to_class(block_name)
            import_lines.append(f'from blocks.{module_name} import {class_name}')
        import_lines.append('')
        import_lines.append('')

        # Import models if entities
        if entities:
            import_lines.append('from models import ' + ', '.join(
                self._block_to_class(e.get("name", "Item")) + "Create, " +
                self._block_to_class(e.get("name", "Item")) + "Response"
                for e in entities
            ))
            import_lines.append('')

        # Initialize blocks
        init_lines = ['logger = logging.getLogger(__name__)', '']
        for block_name in blocks:
            class_name = self._block_to_class(block_name)
            var_name = block_name
            init_lines.append(f'{var_name} = {class_name}()')
        init_lines.append('')

        # Health check
        health_lines = [
            '',
            '@app.get("/health")',
            'async def health():',
            '    return {"status": "ok", "service": "' + project_name + '"}',
            '',
        ]

        # Entity endpoints
        endpoint_lines = []
        for entity in entities:
            entity_name = entity.get("name", "Item")
            endpoint_lines.extend(self._generate_entity_endpoints(entity_name, entity))

        return '\n'.join(import_lines + init_lines + health_lines + endpoint_lines)

    def _generate_entity_endpoints(self, entity_name: str, entity: Dict) -> List[str]:
        """Generate CRUD endpoints for an entity."""
        cls = self._block_to_class(entity_name)
        table = entity_name.lower() + "s"
        lines = [
            f'',
            f'# ── {entity_name} endpoints ──',
            f'',
            f'@app.post("/v1/{table}")',
            f'async def create_{entity_name.lower()}(data: {cls}Create):',
            f'    """Create a new {entity_name}."""',
            f'    from src.core.executors.database_executor import DatabaseExecutor',
            f'    db = DatabaseExecutor()',
            f'    result = crud_service.create("{table}", data.dict())',
            f'    return {{"success": True, "data": result}}',
            f'',
            f'@app.get("/v1/{table}/{{item_id}}")',
            f'async def get_{entity_name.lower()}(item_id: int):',
            f'    """Get {entity_name} by ID."""',
            f'    result = crud_service.read("{table}", item_id)',
            f'    if not result:',
            f'        raise HTTPException(status_code=404, detail="{entity_name} not found")',
            f'    return result',
            f'',
            f'@app.get("/v1/{table}")',
            f'async def list_{entity_name.lower()}(limit: int = 50, offset: int = 0):',
            f'    """List all {entity_name}s."""',
            f'    return crud_service.list("{table}", limit, offset)',
            f'',
            f'@app.put("/v1/{table}/{{item_id}}")',
            f'async def update_{entity_name.lower()}(item_id: int, data: {cls}Create):',
            f'    """Update {entity_name} by ID."""',
            f'    result = crud_service.update("{table}", item_id, data.dict(exclude_unset=True))',
            f'    return {{"success": True, "data": result}}',
            f'',
            f'@app.delete("/v1/{table}/{{item_id}}")',
            f'async def delete_{entity_name.lower()}(item_id: int):',
            f'    """Delete {entity_name} by ID."""',
            f'    crud_service.delete("{table}", item_id)',
            f'    return {{"success": True}}',
        ]
        return lines

    def _generate_requirements(self, blocks: List[str]) -> str:
        """Generate requirements.txt based on blocks used."""
        requirements = {
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
            "pydantic>=2.0.0",
        }

        block_deps = {
            "jwt_auth": {"python-jose[cryptography]>=3.3.0", "passlib[bcrypt]>=1.7.4"},
            "stripe_payments": {"stripe>=7.0.0"},
            "email_smtp": {"aiosmtplib>=3.0.0"},
            "telegram_bot": {"aiohttp>=3.8.0"},
            "webhook_server": {"aiohttp>=3.8.0"},
            "pdf_generator": {"reportlab>=4.0.0"},
            "google_sheets": {"google-api-python-client>=2.0.0"},
            "crud_service": set(),
            "backup_restore": set(),
            "seed_data": set(),
            "notification_manager": {"aiosmtplib>=3.0.0"},
            "data_analyzer": set(),
            "inventory_tracker": set(),
            "invoice_calculator": set(),
            "crm_pipeline": set(),
            "report_generator": {"reportlab>=4.0.0"},
            "rbac": set(),
            "api_key_auth": set(),
            "database_migrations": set(),
        }

        for block in blocks:
            deps = block_deps.get(block, set())
            requirements.update(deps)

        return '\n'.join(sorted(requirements)) + '\n'

    def _generate_config(self, project_name: str, entities: List[Dict]) -> str:
        """Generate config.py with settings."""
        return f'''"""
{project_name} - Configuration
Auto-generated by TITAN OMNISCALE X CodeAssembler
"""

import os
from typing import Optional


class Settings:
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "{project_name}"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("PORT", "5000"))

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "{project_name}.sqlite")

    # Auth (if jwt_auth block used)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")


settings = Settings()
'''

    # ================================================================
    #  HELPERS
    # ================================================================

    @staticmethod
    def _map_type(yaml_type: str) -> str:
        """Map YAML type to Python type annotation."""
        mapping = {
            "str": "str", "string": "str", "text": "str",
            "int": "int", "integer": "int", "number": "int",
            "float": "float", "decimal": "float", "double": "float",
            "bool": "bool", "boolean": "bool",
            "date": "datetime", "datetime": "datetime",
            "list": "List[Any]", "array": "List[Any]",
            "dict": "Dict[str, Any]", "json": "Dict[str, Any]",
            "email": "str", "url": "str", "phone": "str",
        }
        return mapping.get(yaml_type.lower(), "str")

    @staticmethod
    def _block_to_class(block_name: str) -> str:
        """Convert block_name to PascalCase class name."""
        return ''.join(word.capitalize() for word in block_name.split('_'))

    def _prepare_variables(self, project_name: str, entities: List[Dict],
                           blocks: List[str]) -> Dict:
        """Prepare template variables for rendering."""
        entity_names = [e.get("name", "Item") for e in entities]
        entity_fields = {}
        for e in entities:
            name = e.get("name", "Item")
            fields = e.get("fields", [])
            entity_fields[name] = [f.get("name", "field") for f in fields]

        return {
            "project_name": project_name,
            "entities": entities,
            "entity_names": entity_names,
            "entity_fields": entity_fields,
            "blocks": blocks,
            "app_name": project_name,
            "version": "1.0.0",
        }

    def _resolve_dependencies(self, block_names: List[str]) -> List[str]:
        """Resolve block dependencies in correct order."""
        # Define dependency graph
        deps = {
            "rbac": ["jwt_auth"],
            "backup_restore": ["crud_service"],
            "seed_data": ["crud_service"],
        }

        resolved = []
        visited = set()

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            for dep in deps.get(name, []):
                if dep in block_names:
                    visit(dep)
            resolved.append(name)

        for name in block_names:
            visit(name)

        return resolved
