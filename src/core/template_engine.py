"""
TITAN OMNISCALE X - TemplateEngine (Jinja2-Powered Code Generation)

Motor de templates externos que reemplaza los f-strings inline.
Carga templates .j2 desde src/templates/, los compone con bloques,
y genera codigo funcional, no stubs.

Arquitectura:
  1. Carga templates .j2 desde el filesystem
  2. Herencia: base template → app template → bloques especializados
  3. Composicion: incluye bloques de logica/integracion segun necesidad
  4. Validacion: verifica que todos los placeholders esten llenos
  5. Genera codigo funcional con SQL parametrizado

Ventajas sobre f-strings:
  - Mantenible: editar template sin tocar Python
  - Extensible: agregar bloques sin modificar core
  - Testeable: templates se pueden validar independientemente
  - Seguro: SQL parametrizado por defecto
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, Template, TemplateError
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

logger = logging.getLogger(__name__)

# === Template Root ===
TEMPLATE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


@dataclass
class TemplateBlock:
    """Bloque de codigo reutilizable y pre-construido."""
    name: str
    category: str  # business_logic, integrations, auth, data
    description: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    template_path: str = ""  # Relative to TEMPLATE_ROOT


@dataclass
class CompositionPlan:
    """Plan de composicion de templates generado por la AI."""
    base_template: str = "apps/base"
    app_template: str = ""
    blocks: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    entities: List[Dict[str, Any]] = field(default_factory=list)


class TemplateEngine:
    """
    Motor de templates Jinja2 para generacion de codigo.

    Carga templates desde el filesystem, los compone con bloques
    especializados, y genera codigo funcional completo.
    """

    def __init__(self, template_root: str = ""):
        self._root = template_root or TEMPLATE_ROOT
        self._blocks: Dict[str, TemplateBlock] = {}
        self._env: Optional[Any] = None

        if JINJA2_AVAILABLE:
            self._env = Environment(
                loader=FileSystemLoader(self._root),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
                autoescape=False,  # We generate code, not HTML
            )
            # Custom filters
            self._env.filters["pascal"] = self._pascal_case
            self._env.filters["snake"] = self._snake_case
            self._env.filters["camel"] = self._camel_case
            self._env.filters["sql_type"] = self._python_to_sql_type
            self._env.filters["sql_param"] = self._to_sql_param
            self._env.filters["default_val"] = self._default_value

        self._register_builtin_blocks()
        logger.info(f"TemplateEngine: Initialized with root={self._root}, jinja2={'yes' if JINJA2_AVAILABLE else 'no'}")

    # ================================================================
    #  CORE RENDERING
    # ================================================================

    def render(self, template_path: str, variables: Dict[str, Any]) -> str:
        """
        Renderiza un template con las variables dadas.

        Args:
            template_path: Ruta relativa al template (e.g. "apps/base/main.py.j2")
            variables: Variables para el template

        Returns:
            Codigo generado como string
        """
        if not JINJA2_AVAILABLE:
            return self._fallback_render(template_path, variables)

        try:
            template = self._env.get_template(template_path)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"TemplateEngine: Error rendering {template_path}: {e}")
            return self._fallback_render(template_path, variables)

    def render_string(self, template_str: str, variables: Dict[str, Any]) -> str:
        """Renderiza un string como template Jinja2."""
        if not JINJA2_AVAILABLE:
            return self._simple_substitute(template_str, variables)

        try:
            template = self._env.from_string(template_str)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"TemplateEngine: Error rendering string: {e}")
            return self._simple_substitute(template_str, variables)

    def render_app(self, plan: CompositionPlan) -> Dict[str, str]:
        """
        Renderiza una aplicacion completa a partir de un CompositionPlan.

        Returns:
            Dict mapping filepath -> generated code
        """
        files = {}
        variables = self._prepare_variables(plan)

        # Render core files from base template
        base_files = ["main.py", "database.py", "models.py", "services.py",
                      "config.py", "validators.py", "requirements.txt"]

        for filename in base_files:
            template_path = self._resolve_template(plan, filename)
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[filename] = content

        # Render HTML templates
        html_files = ["base.html", "dashboard.html", "list.html", "form.html"]
        for filename in html_files:
            template_path = self._resolve_template(plan, f"templates/{filename}")
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[f"templates/{filename}"] = content

        # Render CSS
        css_template = self._resolve_template(plan, "static/style.css")
        if css_template:
            files["static/style.css"] = self.render(css_template, variables)

        # Render block-specific files
        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block and block.template_path:
                block_content = self.render(block.template_path, variables)
                if block_content:
                    block_filename = f"blocks/{block_name}.py"
                    files[block_filename] = block_content

        # Render Dockerfile
        docker_template = self._resolve_template(plan, "Dockerfile")
        if docker_template:
            files["Dockerfile"] = self.render(docker_template, variables)

        # Render README
        readme_template = self._resolve_template(plan, "README.md")
        if readme_template:
            files["README.md"] = self.render(readme_template, variables)

        return files

    def render_automation(self, plan: CompositionPlan) -> Dict[str, str]:
        """Renderiza un proyecto de automatizacion completo."""
        files = {}
        variables = self._prepare_variables(plan)

        auto_files = ["main.py", "workflows.py", "actions.py", "config.py", "requirements.txt"]

        for filename in auto_files:
            template_path = self._resolve_automation_template(plan, filename)
            if template_path:
                content = self.render(template_path, variables)
                if content:
                    files[filename] = content

        # Render block-specific action executors
        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block and block.template_path:
                block_content = self.render(block.template_path, variables)
                if block_content:
                    files[f"executors/{block_name}.py"] = block_content

        return files

    # ================================================================
    #  BLOCK REGISTRY
    # ================================================================

    def register_block(self, block: TemplateBlock):
        """Registra un bloque de codigo reutilizable."""
        self._blocks[block.name] = block
        logger.debug(f"TemplateEngine: Registered block '{block.name}' ({block.category})")

    def get_block(self, name: str) -> Optional[TemplateBlock]:
        """Obtiene un bloque por nombre."""
        return self._blocks.get(name)

    def list_blocks(self, category: str = "") -> List[TemplateBlock]:
        """Lista bloques disponibles, opcionalmente filtrados por categoria."""
        if category:
            return [b for b in self._blocks.values() if b.category == category]
        return list(self._blocks.values())

    def resolve_dependencies(self, block_names: List[str]) -> List[str]:
        """
        Resuelve dependencias entre bloques y devuelve el orden correcto.

        Usa ordenamiento topologico para que los bloques dependientes
        aparezcan despues de sus dependencias.
        """
        resolved = []
        visited = set()
        visiting = set()

        def visit(name: str):
            if name in visited:
                return
            if name in visiting:
                logger.warning(f"TemplateEngine: Circular dependency detected for {name}")
                return

            visiting.add(name)
            block = self._blocks.get(name)
            if block:
                for dep in block.dependencies:
                    visit(dep)
            visiting.discard(name)
            visited.add(name)
            resolved.append(name)

        for name in block_names:
            visit(name)

        return resolved

    def suggest_blocks(self, description: str) -> List[str]:
        """
        Sugiere bloques relevantes basado en una descripcion.

        Usa keyword matching para identificar que bloques son relevantes.
        En futuras versiones, usara SemanticEngine.
        """
        desc_lower = description.lower()
        suggested = []

        for block in self._blocks.values():
            # Check if block keywords match description
            block_keywords = block.name.replace("_", " ").split()
            desc_words = set(desc_lower.split())

            # Match by name keywords
            name_match = any(kw in desc_lower for kw in block_keywords)

            # Match by description keywords
            desc_keywords = block.description.lower().split()
            desc_match = any(kw in desc_lower for kw in desc_keywords if len(kw) > 3)

            # Match by category
            category_keywords = {
                "business_logic": ["calcular", "logica", "procesar", "calculate", "logic", "business"],
                "integrations": ["email", "smtp", "api", "webhook", "stripe", "whatsapp", "telegram"],
                "auth": ["auth", "login", "usuario", "password", "jwt", "token", "rol"],
                "data": ["crud", "base de datos", "database", "migracion", "backup", "query"],
            }
            cat_keywords = category_keywords.get(block.category, [])
            cat_match = any(kw in desc_lower for kw in cat_keywords)

            if name_match or desc_match or cat_match:
                suggested.append(block.name)

        # Resolve dependencies
        return self.resolve_dependencies(suggested)

    # ================================================================
    #  TEMPLATE RESOLUTION
    # ================================================================

    def _resolve_template(self, plan: CompositionPlan, filename: str) -> Optional[str]:
        """Resuelve la ruta del template mas especifico disponible."""
        # Try app-specific template first
        if plan.app_template:
            app_path = f"apps/{plan.app_template}/{filename}.j2"
            if self._template_exists(app_path):
                return app_path

        # Try base template
        base_path = f"apps/base/{filename}.j2"
        if self._template_exists(base_path):
            return base_path

        # No template found
        logger.debug(f"TemplateEngine: No template found for {filename}")
        return None

    def _resolve_automation_template(self, plan: CompositionPlan, filename: str) -> Optional[str]:
        """Resuelve la ruta del template de automatizacion."""
        if plan.app_template:
            app_path = f"automations/{plan.app_template}/{filename}.j2"
            if self._template_exists(app_path):
                return app_path

        base_path = f"automations/base/{filename}.j2"
        if self._template_exists(base_path):
            return base_path

        return None

    def _template_exists(self, path: str) -> bool:
        """Verifica si un template existe en el filesystem."""
        full_path = os.path.join(self._root, path)
        return os.path.isfile(full_path)

    # ================================================================
    #  VARIABLE PREPARATION
    # ================================================================

    def _prepare_variables(self, plan: CompositionPlan) -> Dict[str, Any]:
        """Prepara las variables para renderizar templates."""
        variables = dict(plan.variables)

        # Add entities with processed fields
        processed_entities = []
        for entity in plan.entities:
            processed = self._process_entity(entity)
            processed_entities.append(processed)
        variables["entities"] = processed_entities

        # Add block info
        variables["blocks"] = []
        for block_name in plan.blocks:
            block = self._blocks.get(block_name)
            if block:
                variables["blocks"].append({
                    "name": block.name,
                    "category": block.category,
                    "description": block.description,
                    "inputs": block.inputs,
                    "outputs": block.outputs,
                })

        # Ensure required variables
        variables.setdefault("project_name", "app")
        variables.setdefault("app_name", variables.get("project_name", "app"))
        variables.setdefault("template_type", "generic")
        variables.setdefault("db_name", variables.get("project_name", "app") + ".db")
        variables.setdefault("port", 8000)
        variables.setdefault("secret_key", "change-this-in-production")
        variables.setdefault("debug", True)
        variables.setdefault("version", "1.0.0")

        return variables

    def _process_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa una entidad para generar variables de template."""
        name = entity.get("name", "Item")
        fields = entity.get("fields", [])

        processed_fields = []
        for f in fields:
            parts = f.split(":")
            fname = parts[0]
            ftype = parts[1] if len(parts) > 1 else "str"

            processed_fields.append({
                "name": fname,
                "type": ftype,
                "sql_type": self._python_to_sql_type(ftype),
                "pascal_name": self._pascal_case(fname),
                "snake_name": self._snake_case(fname),
                "default": self._default_value(ftype),
                "is_fk": fname.endswith("_id") and fname != "id",
                "fk_ref": fname.replace("_id", "") if fname.endswith("_id") and fname != "id" else None,
                "is_indexed": fname in ["name", "status", "type", "category", "date",
                                        "customer_id", "product_id", "user_id", "project_id"],
                "is_unique": fname in ["email", "sku", "code", "slug", "token"],
                "input_type": {"int": "number", "float": "number", "datetime": "datetime-local",
                               "bool": "checkbox"}.get(ftype, "text"),
            })

        return {
            "name": name,
            "name_lower": name.lower(),
            "name_pascal": self._pascal_case(name),
            "name_snake": self._snake_case(name),
            "fields": processed_fields,
            "has_fk": any(f["is_fk"] for f in processed_fields),
        }

    # ================================================================
    #  BUILTIN BLOCK REGISTRATION
    # ================================================================

    def _register_builtin_blocks(self):
        """Registra los bloques de codigo pre-construidos."""
        # Business Logic blocks
        builtin_blocks = [
            TemplateBlock(
                name="invoice_calculator",
                category="business_logic",
                description="Calculo de facturas con impuestos, descuentos y totales",
                inputs=["items", "tax_rate", "discount"],
                outputs=["subtotal", "tax_amount", "discount_amount", "total"],
                dependencies=[],
                template_path="blocks/business_logic/invoice_calculator.py.j2",
            ),
            TemplateBlock(
                name="inventory_tracker",
                category="business_logic",
                description="Seguimiento de inventario con alertas de stock bajo",
                inputs=["product_id", "quantity_change"],
                outputs=["new_quantity", "alerts"],
                dependencies=[],
                template_path="blocks/business_logic/inventory_tracker.py.j2",
            ),
            TemplateBlock(
                name="crm_pipeline",
                category="business_logic",
                description="Pipeline de ventas con etapas y conversion",
                inputs=["lead_data", "stage"],
                outputs=["updated_lead", "next_action"],
                dependencies=[],
                template_path="blocks/business_logic/crm_pipeline.py.j2",
            ),
            TemplateBlock(
                name="task_scheduler",
                category="business_logic",
                description="Priorizacion y asignacion de tareas",
                inputs=["tasks", "resources"],
                outputs=["schedule", "assignments"],
                dependencies=[],
                template_path="blocks/business_logic/task_scheduler.py.j2",
            ),
            TemplateBlock(
                name="report_generator",
                category="business_logic",
                description="Generacion de reportes desde datos",
                inputs=["data", "template", "format"],
                outputs=["report_content", "metadata"],
                dependencies=[],
                template_path="blocks/business_logic/report_generator.py.j2",
            ),
            TemplateBlock(
                name="notification_manager",
                category="business_logic",
                description="Gestion de notificaciones multi-canal",
                inputs=["recipient", "message", "channels"],
                outputs=["delivery_status"],
                dependencies=["email_smtp", "telegram_bot"],
                template_path="blocks/business_logic/notification_manager.py.j2",
            ),
            TemplateBlock(
                name="data_analyzer",
                category="business_logic",
                description="Analisis estadistico y metricas de datos",
                inputs=["dataset", "metrics"],
                outputs=["analysis_result", "summary"],
                dependencies=[],
                template_path="blocks/business_logic/data_analyzer.py.j2",
            ),
            # Integration blocks
            TemplateBlock(
                name="email_smtp",
                category="integrations",
                description="Envio real de emails via SMTP",
                inputs=["to", "subject", "body", "html"],
                outputs=["message_id", "status"],
                dependencies=[],
                template_path="blocks/integrations/email_smtp.py.j2",
            ),
            TemplateBlock(
                name="whatsapp_api",
                category="integrations",
                description="Envio de mensajes WhatsApp Business API",
                inputs=["phone", "message", "template"],
                outputs=["message_id", "status"],
                dependencies=[],
                template_path="blocks/integrations/whatsapp_api.py.j2",
            ),
            TemplateBlock(
                name="stripe_payments",
                category="integrations",
                description="Procesamiento de pagos con Stripe",
                inputs=["amount", "currency", "customer_id"],
                outputs=["payment_id", "status"],
                dependencies=[],
                template_path="blocks/integrations/stripe_payments.py.j2",
            ),
            TemplateBlock(
                name="google_sheets",
                category="integrations",
                description="Lectura y escritura de Google Sheets",
                inputs=["sheet_id", "range", "data"],
                outputs=["rows", "status"],
                dependencies=[],
                template_path="blocks/integrations/google_sheets.py.j2",
            ),
            TemplateBlock(
                name="telegram_bot",
                category="integrations",
                description="Bot de Telegram para notificaciones",
                inputs=["chat_id", "message"],
                outputs=["message_id", "status"],
                dependencies=[],
                template_path="blocks/integrations/telegram_bot.py.j2",
            ),
            TemplateBlock(
                name="webhook_server",
                category="integrations",
                description="Servidor webhook para recibir notificaciones",
                inputs=["path", "handler"],
                outputs=["endpoint_url", "status"],
                dependencies=[],
                template_path="blocks/integrations/webhook_server.py.j2",
            ),
            TemplateBlock(
                name="pdf_generator",
                category="integrations",
                description="Generacion de PDFs desde HTML/templates",
                inputs=["template", "data", "output_path"],
                outputs=["pdf_path", "status"],
                dependencies=[],
                template_path="blocks/integrations/pdf_generator.py.j2",
            ),
            # Auth blocks
            TemplateBlock(
                name="jwt_auth",
                category="auth",
                description="Autenticacion JWT completa con login, registro, refresh",
                inputs=["username", "password", "role"],
                outputs=["token", "user_id", "role"],
                dependencies=[],
                template_path="blocks/auth/jwt_auth.py.j2",
            ),
            TemplateBlock(
                name="api_key_auth",
                category="auth",
                description="Autenticacion por API key",
                inputs=["api_key"],
                outputs=["authenticated", "identity"],
                dependencies=[],
                template_path="blocks/auth/api_key_auth.py.j2",
            ),
            TemplateBlock(
                name="rbac",
                category="auth",
                description="Control de acceso basado en roles",
                inputs=["user_role", "resource", "action"],
                outputs=["allowed", "reason"],
                dependencies=["jwt_auth"],
                template_path="blocks/auth/rbac.py.j2",
            ),
            # Data blocks
            TemplateBlock(
                name="crud_service",
                category="data",
                description="Servicio CRUD con SQL parametrizado y validacion",
                inputs=["entity", "data"],
                outputs=["result", "status"],
                dependencies=[],
                template_path="blocks/data/crud_service.py.j2",
            ),
            TemplateBlock(
                name="migration",
                category="data",
                description="Sistema de migraciones incrementales",
                inputs=["schema_version", "changes"],
                outputs=["migration_sql", "status"],
                dependencies=[],
                template_path="blocks/data/migration.py.j2",
            ),
            TemplateBlock(
                name="backup_restore",
                category="data",
                description="Backup y restauracion de base de datos",
                inputs=["db_path", "backup_dir"],
                outputs=["backup_path", "status"],
                dependencies=[],
                template_path="blocks/data/backup_restore.py.j2",
            ),
            TemplateBlock(
                name="seed_data",
                category="data",
                description="Generacion de datos iniciales/seed",
                inputs=["schema", "count"],
                outputs=["insert_sql", "status"],
                dependencies=[],
                template_path="blocks/data/seed_data.py.j2",
            ),
        ]

        for block in builtin_blocks:
            self.register_block(block)

    # ================================================================
    #  UTILITY METHODS
    # ================================================================

    @staticmethod
    def _pascal_case(s: str) -> str:
        return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))

    @staticmethod
    def _snake_case(s: str) -> str:
        import re
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', s)
        return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    @staticmethod
    def _camel_case(s: str) -> str:
        parts = s.replace("-", "_").split("_")
        return parts[0] + "".join(w.capitalize() for w in parts[1:])

    @staticmethod
    def _python_to_sql_type(py_type: str) -> str:
        mapping = {
            "int": "INTEGER", "float": "REAL", "bool": "INTEGER",
            "str": "TEXT", "datetime": "TEXT", "date": "TEXT",
            "list": "TEXT", "dict": "TEXT", "bytes": "BLOB",
            "Decimal": "REAL",
        }
        return mapping.get(py_type, "TEXT")

    @staticmethod
    def _to_sql_param(value: Any) -> str:
        """Convierte un valor a parametro SQL seguro (?)."""
        return "?"  # Always use parameterized queries

    @staticmethod
    def _default_value(py_type: str) -> str:
        mapping = {
            "int": "None", "float": "None", "bool": "None",
            "str": '""', "datetime": "None", "date": "None",
            "list": "[]", "dict": "{}",
        }
        return mapping.get(py_type, "None")

    # ================================================================
    #  FALLBACK (when Jinja2 is not available)
    # ================================================================

    def _fallback_render(self, template_path: str, variables: Dict[str, Any]) -> str:
        """Fallback: carga template como texto y hace substitucion simple."""
        full_path = os.path.join(self._root, template_path)
        if not os.path.isfile(full_path):
            return f"# Template not found: {template_path}\n"

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self._simple_substitute(content, variables)

    @staticmethod
    def _simple_substitute(template_str: str, variables: Dict[str, Any]) -> str:
        """Substitucion simple de {{ variable }} sin Jinja2."""
        import re
        def replace_var(match):
            var_name = match.group(1).strip()
            # Navigate nested dicts
            parts = var_name.split(".")
            value = variables
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, f"{{{{{var_name}}}}}")
                else:
                    return f"{{{{{var_name}}}}}"
            return str(value) if value is not None else f"{{{{{var_name}}}}}"

        # Replace {{ variable }} patterns
        result = re.sub(r'\{\{\s*([^}]+)\s*\}\}', replace_var, template_str)
        # Remove {% %} blocks (simple approach - just keep the content)
        result = re.sub(r'\{%\s*end.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*if\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*for\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*block\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*extends\s+.*?\s*%\}', '', result)
        result = re.sub(r'\{%\s*include\s+.*?\s*%\}', '', result)

        return result

    @property
    def available_templates(self) -> List[str]:
        """Lista templates disponibles en el filesystem."""
        templates = []
        for root, dirs, files in os.walk(self._root):
            for f in files:
                if f.endswith(".j2"):
                    rel = os.path.relpath(os.path.join(root, f), self._root)
                    templates.append(rel)
        return sorted(templates)

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del motor de templates."""
        return {
            "template_root": self._root,
            "jinja2_available": JINJA2_AVAILABLE,
            "registered_blocks": len(self._blocks),
            "block_categories": list(set(b.category for b in self._blocks.values())),
            "available_templates": len(self.available_templates),
        }
