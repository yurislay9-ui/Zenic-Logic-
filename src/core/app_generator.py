"""
TITAN OMNISCALE X - AppGenerator (Real App Generation for PYMEs)

Sistema de generación de aplicaciones COMPLETAS para pequeñas y medianas empresas.
Genera proyectos Python reales, ejecutables, no solo snippets.

Estrategia: TEMPLATE-DRIVEN + AI-GUIDED
  - Templates completos y probados → garantizan que FUNCIONAN
  - Qwen personaliza los templates → adaptados al negocio del cliente
  - Pipeline verifica el resultado → calidad asegurada

Tipos de app que puede generar:
  1. Web API (FastAPI + SQLite) - Backend REST para cualquier negocio
  2. CRM - Gestión de clientes y ventas
  3. Inventario - Control de stock y almacén
  4. Facturación - Generación de facturas y cobros
  5. Task Manager - Gestión de tareas y proyectos
  6. Auth System - Autenticación y usuarios
  7. Report Generator - Generación de reportes automáticos
  8. Dashboard - Panel de control con datos en tiempo real

Cada app generada incluye:
  - main.py (FastAPI app con todos los endpoints)
  - models.py (modelos de datos con dataclasses)
  - database.py (configuración SQLite)
  - services.py (lógica de negocio)
  - templates/ (HTML con Jinja2)
  - requirements.txt
  - README.md

Optimizado para:
  - Sin GPU, sin servidor externo, sin dependencias pesadas
  - FastAPI + SQLite + Jinja2 = stack ligero para PYME
  - Corre en el mismo Redmi 12R Pro
"""

import os
import re
import json
import time
import secrets
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# === Project Output Configuration ===
PROJECTS_DIR = os.path.join(os.path.expanduser("~"), ".titan_omniscale", "projects")


@dataclass
class GeneratedProject:
    """Resultado de la generación de un proyecto."""
    name: str = ""
    template_type: str = ""
    path: str = ""
    files: List[str] = field(default_factory=list)
    main_file: str = ""
    endpoints: List[Dict[str, str]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, generated, verified, failed
    error: str = ""
    generation_time_s: float = 0.0


class AppGenerator:
    """
    Generador de aplicaciones completas para PYMEs.

    Genera proyectos Python reales y ejecutables usando templates
    Jinja2 externos + bloques de logica componibles, personalizados
    por el ThinkingEngine.
    """

    def __init__(self, thinking_engine=None, template_engine=None):
        self._thinking = thinking_engine
        self._template_engine = template_engine
        os.makedirs(PROJECTS_DIR, exist_ok=True)

        # Lazy-init template engine if not provided
        if self._template_engine is None:
            try:
                from src.core.template_engine import TemplateEngine
                self._template_engine = TemplateEngine()
            except ImportError:
                logger.warning("AppGenerator: TemplateEngine not available, using legacy f-string generation")

    # ================================================================
    #  MAIN ENTRY POINT
    # ================================================================

    def generate_app(self, request: str, project_name: str = "",
                     output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación completa. Usa TemplateEngine si disponible,
        sino usa el generador legacy con f-strings.
        """
        if self._template_engine:
            return self.generate_app_v2(request, project_name, output_dir)
        return self.generate_app_legacy(request, project_name, output_dir)

    def generate_app_v2(self, request: str, project_name: str = "",
                        output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación usando TemplateEngine + bloques componibles.

        Estrategia: BLOCKS + AI ASSEMBLER
          1. ThinkingEngine analiza requisitos y planifica
          2. TemplateEngine sugiere bloques relevantes
          3. Bloques se componen en la app final
          4. Resultado: codigo funcional, no stubs
        """
        start_time = time.time()

        # Step 1: Plan generation
        if self._thinking:
            plan = self._thinking.plan_generation(request)
        else:
            plan = self._fallback_plan(request)

        # Step 2: Suggest blocks based on description
        suggested_blocks = self._template_engine.suggest_blocks(request)

        # Step 3: Generate project name and output dir
        if not project_name:
            project_name = self._generate_project_name(plan.template_type, request)
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, project_name)
        os.makedirs(output_dir, exist_ok=True)

        # Step 4: Build composition plan
        from src.core.template_engine import CompositionPlan
        composition = CompositionPlan(
            base_template="apps/base",
            app_template=plan.template_type if plan.template_type != "generic" else "",
            blocks=suggested_blocks,
            variables={
                "project_name": project_name,
                "app_name": project_name,
                "template_type": plan.template_type,
                "db_name": project_name + ".db",
                "port": plan.config_vars.get("port", 8000),
                "secret_key": plan.config_vars.get("secret_key", secrets.token_hex(32)),
                "debug": True,
                "version": "1.0.0",
            },
            entities=plan.entities,
        )

        # Step 5: Render all files via TemplateEngine
        generated = GeneratedProject(
            name=project_name,
            template_type=plan.template_type,
            path=output_dir,
            entities=plan.entities,
            endpoints=plan.endpoints,
        )

        try:
            files = self._template_engine.render_app(composition)

            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                generated.files.append(filepath)

            generated.main_file = "main.py"
            generated.status = "generated"
            generated.generation_time_s = time.time() - start_time

            logger.info(f"AppGenerator v2: Generated {project_name} with {len(files)} files, {len(suggested_blocks)} blocks in {generated.generation_time_s:.1f}s")

        except Exception as e:
            generated.status = "failed"
            generated.error = str(e)
            generated.generation_time_s = time.time() - start_time
            logger.error(f"AppGenerator v2: Failed to generate {project_name}: {e}")

        return generated

    def generate_app_legacy(self, request: str, project_name: str = "",
                            output_dir: str = "") -> GeneratedProject:
        """
        Genera una aplicación completa a partir de una descripción en lenguaje natural.

        Args:
            request: Descripción de lo que el cliente necesita
            project_name: Nombre del proyecto (opcional, se genera si no se da)
            output_dir: Directorio de salida (opcional, default: ~/.titan_omniscale/projects/)

        Returns:
            GeneratedProject con todos los archivos generados
        """
        start_time = time.time()

        # Step 1: Use ThinkingEngine to plan the generation
        if self._thinking:
            plan = self._thinking.plan_generation(request)
        else:
            plan = self._fallback_plan(request)

        # Step 2: Generate project name
        if not project_name:
            project_name = self._generate_project_name(plan.template_type, request)

        # Step 3: Setup output directory
        if not output_dir:
            output_dir = os.path.join(PROJECTS_DIR, project_name)
        os.makedirs(output_dir, exist_ok=True)

        # Step 4: Generate all project files
        generated = GeneratedProject(
            name=project_name,
            template_type=plan.template_type,
            path=output_dir,
            entities=plan.entities,
            endpoints=plan.endpoints,
        )

        try:
            # Generate core files
            files = {}

            files["requirements.txt"] = self._gen_requirements(plan)
            files["database.py"] = self._gen_database(plan, project_name)
            files["models.py"] = self._gen_models(plan, project_name)
            files["services.py"] = self._gen_services(plan, project_name)
            files["main.py"] = self._gen_main(plan, project_name)
            files["config.py"] = self._gen_config(plan, project_name)

            # Generate HTML templates
            os.makedirs(os.path.join(output_dir, "templates"), exist_ok=True)
            files["templates/base.html"] = self._gen_base_template(plan, project_name)
            files["templates/dashboard.html"] = self._gen_dashboard_template(plan, project_name)
            files["templates/list.html"] = self._gen_list_template(plan, project_name)
            files["templates/form.html"] = self._gen_form_template(plan, project_name)

            # Generate static files
            os.makedirs(os.path.join(output_dir, "static"), exist_ok=True)
            files["static/style.css"] = self._gen_css(plan, project_name)

            # Generate README
            files["README.md"] = self._gen_readme(plan, project_name)

            # Write all files
            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                generated.files.append(filepath)

            generated.main_file = "main.py"
            generated.status = "generated"
            generated.generation_time_s = time.time() - start_time

            logger.info(f"AppGenerator: Generated {project_name} with {len(files)} files in {generated.generation_time_s:.1f}s")

        except Exception as e:
            generated.status = "failed"
            generated.error = str(e)
            generated.generation_time_s = time.time() - start_time
            logger.error(f"AppGenerator: Failed to generate {project_name}: {e}")

        return generated

    # ================================================================
    #  CORE FILE GENERATORS
    # ================================================================

    def _gen_requirements(self, plan) -> str:
        """Genera requirements.txt."""
        base = [
            "fastapi>=0.100.0",
            "uvicorn>=0.23.0",
            "jinja2>=3.1.0",
            "python-multipart>=0.0.6",
        ]

        # Add based on template
        if plan.template_type in ["invoice_billing", "report_generator"]:
            base.append("weasyprint>=59.0")
        if plan.template_type in ["email_automation", "email_sender", "notification_service"]:
            base.append("aiosmtplib>=3.0.0")
        if plan.template_type in ["scheduler", "scheduled_report"]:
            base.append("apscheduler>=3.10.0")
        if plan.template_type in ["data_pipeline", "data_sync"]:
            base.append("aiohttp>=3.8.0")

        return "\n".join(base) + "\n"

    def _gen_database(self, plan, project_name: str) -> str:
        """Genera database.py - Configuración SQLite con init automático."""
        entities = plan.entities
        table_creates = []
        for entity in entities:
            name = entity.get("name", "Item")
            fields = entity.get("fields", [])
            # Validate entity name — only alphanumeric + underscore allowed
            if not re.match(r'^[a-zA-Z_]\w*$', name.lower()):
                raise ValueError(f"Invalid entity name: {name}. Only alphanumeric characters and underscores allowed.")
            columns = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
            for f in fields:
                parts = f.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "str"
                sql_type = {"int": "INTEGER", "float": "REAL", "bool": "INTEGER",
                            "str": "TEXT", "datetime": "TEXT", "list": "TEXT",
                            "dict": "TEXT"}.get(ftype, "TEXT")
                columns.append(f"{fname} {sql_type}")
            table_creates.append(
                f'CREATE TABLE IF NOT EXISTS {name.lower()} (\n'
                + ",\n".join(f"        {c}" for c in columns)
                + "\n    )"
            )

        tables_sql = "\n\n    ".join(table_creates) if table_creates else "CREATE TABLE IF NOT EXISTS item (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)"

        return f'''"""
{project_name} - Database Configuration
Auto-generated by TITAN OMNISCALE X
"""
import sqlite3
import os
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "{plan.config_vars.get('db_name', project_name + '.db')}")

def get_connection() -> sqlite3.Connection:
    """Obtiene conexión a la base de datos SQLite."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    """Inicializa la base de datos con las tablas necesarias."""
    conn = get_connection()
    try:
        conn.executescript("""
    {tables_sql}
    """)
        conn.commit()
    finally:
        conn.close()

def execute_query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Ejecuta una query SELECT y devuelve resultados como lista de dicts."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def execute_insert(sql: str, params: tuple = ()) -> int:
    """Ejecuta INSERT/UPDATE/DELETE y devuelve el lastrowid."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def execute_update(sql: str, params: tuple = ()) -> int:
    """Ejecuta UPDATE/DELETE y devuelve filas afectadas."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()

# Inicializar DB al importar
init_db()
'''

    def _gen_models(self, plan, project_name: str) -> str:
        """Genera models.py - Modelos de datos con dataclasses."""
        entities = plan.entities
        model_classes = []

        for entity in entities:
            name = entity.get("name", "Item")
            fields = entity.get("fields", [])

            field_defs = ["    id: Optional[int] = None"]
            for f in fields:
                parts = f.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "str"
                py_type = {"int": "int", "float": "float", "bool": "bool",
                           "str": "str", "datetime": "str", "list": "str",
                           "dict": "str"}.get(ftype, "str")
                default = 'None' if py_type in ("int", "float") else '""' if py_type == "str" else "None"
                field_defs.append(f"    {fname}: Optional[{py_type}] = {default}")

            fields_str = "\n".join(field_defs)
            model_classes.append(f'''@dataclass
class {name}:
    """Modelo de datos para {name}."""
{fields_str}

    def to_dict(self) -> Dict[str, Any]:
        return {{k: v for k, v in asdict(self).items() if v is not None}}

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "{name}":
        return cls(**{{k: v for k, v in row.items() if k in cls.__dataclass_fields__}})''')

        models_str = "\n\n\n".join(model_classes) if model_classes else '''@dataclass
class Item:
    """Modelo genérico."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}'''

        return f'''"""
{project_name} - Data Models
Auto-generated by TITAN OMNISCALE X
"""
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from datetime import datetime

{models_str}
'''

    def _gen_services(self, plan, project_name: str) -> str:
        """Genera services.py - Lógica de negocio."""
        entities = plan.entities
        service_methods = []

        for entity in entities:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            fields = entity.get("fields", [])

            # Build field params for create
            create_params = []
            insert_cols = ["id"]
            insert_vals = ["NULL"]
            for f in fields:
                parts = f.split(":")
                fname = parts[0]
                create_params.append(fname)
                insert_cols.append(fname)
                insert_vals.append(f"?")

            params_str = ", ".join(create_params)
            cols_str = ", ".join(insert_cols)
            vals_str = ", ".join(insert_vals)
            param_tuple = ", ".join(create_params)

            update_sets = []
            for f in fields:
                parts = f.split(":")
                fname = parts[0]
                update_sets.append(f"{fname} = ?")
            update_sets.append("id = id")
            update_str = ", ".join(update_sets[:len(fields)])
            update_params = ", ".join(create_params) + ", item_id"

            service_methods.append(f'''
    # === {name} CRUD ===

    @staticmethod
    def list_{name_lower}s(search: str = "", page: int = 1, per_page: int = 20) -> List[Dict]:
        """Lista todos los {name_lower}s con búsqueda opcional."""
        offset = (page - 1) * per_page
        if search:
            return execute_query(
                "SELECT * FROM {name_lower} WHERE name LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (f"%{{search}}%", per_page, offset)
            )
        return execute_query(
            "SELECT * FROM {name_lower} ORDER BY id DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )

    @staticmethod
    def get_{name_lower}(item_id: int) -> Optional[Dict]:
        """Obtiene un {name_lower} por ID."""
        results = execute_query("SELECT * FROM {name_lower} WHERE id = ?", (item_id,))
        return results[0] if results else None

    @staticmethod
    def create_{name_lower}({params_str}) -> int:
        """Crea un nuevo {name_lower}."""
        now = datetime.now().isoformat()
        return execute_insert(
            "INSERT INTO {name_lower} ({cols_str}) VALUES ({vals_str})",
            ({param_tuple},)
        )

    @staticmethod
    def update_{name_lower}(item_id: int, {params_str}) -> int:
        """Actualiza un {name_lower} existente."""
        return execute_update(
            "UPDATE {name_lower} SET {update_str} WHERE id = ?",
            ({update_params},)
        )

    @staticmethod
    def delete_{name_lower}(item_id: int) -> int:
        """Elimina un {name_lower}."""
        return execute_update("DELETE FROM {name_lower} WHERE id = ?", (item_id,))

    @staticmethod
    def count_{name_lower}s(search: str = "") -> int:
        """Cuenta el total de {name_lower}s."""
        if search:
            result = execute_query("SELECT COUNT(*) as cnt FROM {name_lower} WHERE name LIKE ?", (f"%{{search}}%",))
        else:
            result = execute_query("SELECT COUNT(*) as cnt FROM {name_lower}")
        return result[0]["cnt"] if result else 0''')

        services_str = "\n".join(service_methods) if service_methods else '''
    # === Generic Item CRUD ===

    @staticmethod
    def list_items(search: str = "", page: int = 1, per_page: int = 20) -> List[Dict]:
        offset = (page - 1) * per_page
        if search:
            return execute_query("SELECT * FROM item WHERE name LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                                 (f"%{search}%", per_page, offset))
        return execute_query("SELECT * FROM item ORDER BY id DESC LIMIT ? OFFSET ?", (per_page, offset))

    @staticmethod
    def get_item(item_id: int) -> Optional[Dict]:
        results = execute_query("SELECT * FROM item WHERE id = ?", (item_id,))
        return results[0] if results else None

    @staticmethod
    def create_item(name: str, description: str = "") -> int:
        now = datetime.now().isoformat()
        return execute_insert("INSERT INTO item (id, name, description, created_at) VALUES (NULL, ?, ?, ?)",
                              (name, description, now))

    @staticmethod
    def delete_item(item_id: int) -> int:
        return execute_update("DELETE FROM item WHERE id = ?", (item_id,))'''

        # Add dashboard stats method
        stats_methods = self._gen_stats_methods(plan)

        return f'''"""
{project_name} - Business Services
Auto-generated by TITAN OMNISCALE X
"""
from datetime import datetime
from typing import List, Dict, Any, Optional

from database import execute_query, execute_insert, execute_update


class Service:
    """Capa de servicios - Lógica de negocio."""
{services_str}

{stats_methods}
'''

    def _gen_stats_methods(self, plan) -> str:
        """Genera métodos de estadísticas para el dashboard."""
        stats = []
        for entity in plan.entities[:3]:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            stats.append(f'''
    @staticmethod
    def get_{name_lower}_stats() -> Dict[str, Any]:
        """Obtiene estadísticas de {name_lower}s."""
        total = execute_query("SELECT COUNT(*) as cnt FROM {name_lower}")
        recent = execute_query("SELECT * FROM {name_lower} ORDER BY id DESC LIMIT 5")
        return {{
            "total": total[0]["cnt"] if total else 0,
            "recent": recent,
        }}''')

        return "\n".join(stats) if stats else '''
    @staticmethod
    def get_dashboard_stats() -> Dict[str, Any]:
        """Obtiene estadísticas generales del dashboard."""
        return {"total": 0, "recent": []}'''

    def _gen_main(self, plan, project_name: str) -> str:
        """Genera main.py - Aplicación FastAPI completa."""
        entities = plan.entities
        endpoints = plan.endpoints

        # Generate API routes
        api_routes = []
        for entity in entities:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            fields = entity.get("fields", [])
            create_params = ["name: str"]
            for f in fields[1:]:
                parts = f.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "str"
                create_params.append(f"{fname}: Optional[{ftype}] = None")

            params_str = ", ".join(create_params)

            api_routes.append(f'''
# === {name} API Routes ===

@app.get("/api/{name_lower}s")
async def api_list_{name_lower}s(search: str = "", page: int = 1):
    results = Service.list_{name_lower}s(search=search, page=page)
    total = Service.count_{name_lower}s(search=search)
    return {{"items": results, "total": total, "page": page}}

@app.get("/api/{name_lower}s/{{item_id}}")
async def api_get_{name_lower}(item_id: int):
    item = Service.get_{name_lower}(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="{name} not found")
    return item

@app.post("/api/{name_lower}s")
async def api_create_{name_lower}({params_str}):
    item_id = Service.create_{name_lower}({", ".join(f.split(":")[0] for f in ["name:str"] + fields[1:])})
    return {{"id": item_id, "status": "created"}}

@app.put("/api/{name_lower}s/{{item_id}}")
async def api_update_{name_lower}(item_id: int, {params_str}):
    updated = Service.update_{name_lower}(item_id, {", ".join(f.split(":")[0] for f in ["name:str"] + fields[1:])})
    return {{"updated": updated}}

@app.delete("/api/{name_lower}s/{{item_id}}")
async def api_delete_{name_lower}(item_id: int):
    deleted = Service.delete_{name_lower}(item_id)
    return {{"deleted": deleted}}''')

        # Generate HTML routes
        html_routes = []
        for entity in entities[:3]:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            html_routes.append(f'''
@app.get("/{name_lower}s")
async def page_{name_lower}s(request: Request, search: str = "", page: int = 1):
    items = Service.list_{name_lower}s(search=search, page=page)
    total = Service.count_{name_lower}s(search=search)
    return templates.TemplateResponse("list.html", {{
        "request": request,
        "items": items,
        "total": total,
        "page": page,
        "entity_name": "{name}",
        "entity_name_lower": "{name_lower}",
    }})''')

        api_routes_str = "\n".join(api_routes) if api_routes else '''
@app.get("/api/items")
async def api_list_items(search: str = "", page: int = 1):
    results = Service.list_items(search=search, page=page)
    return {"items": results}'''

        html_routes_str = "\n".join(html_routes) if html_routes else '''
@app.get("/items")
async def page_items(request: Request):
    items = Service.list_items()
    return templates.TemplateResponse("list.html", {
        "request": request, "items": items, "entity_name": "Item"
    })'''

        return f'''"""
{project_name} - Main Application
Auto-generated by TITAN OMNISCALE X

Run with: uvicorn main:app --host 0.0.0.0 --port {plan.config_vars.get('port', 8000)} --reload
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional
import os

from database import init_db
from services import Service

# ============================================================
#  APP SETUP
# ============================================================

app = FastAPI(
    title="{project_name}",
    description="{plan.template_type.replace('_', ' ').title()} - Generated by TITAN OMNISCALE X",
    version="1.0.0",
)

# Static files and templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


# ============================================================
#  DASHBOARD
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard principal."""
    stats = Service.get_dashboard_stats() if hasattr(Service, 'get_dashboard_stats') else {{}}
    return templates.TemplateResponse("dashboard.html", {{
        "request": request,
        "app_name": "{project_name}",
        "stats": stats,
    }})


# ============================================================
#  API ROUTES
# ============================================================

@app.get("/health")
async def health_check():
    return {{"status": "ok", "app": "{project_name}"}}
{api_routes_str}


# ============================================================
#  HTML PAGES
# ============================================================

{html_routes_str}


# ============================================================
#  ERROR HANDLERS
# ============================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={{"error": "Not found"}})
    return templates.TemplateResponse("dashboard.html", {{
        "request": request, "app_name": "{project_name}", "error": "Page not found"
    }})

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={{"error": "Internal server error"}})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port={plan.config_vars.get('port', 8000)})
'''

    def _gen_config(self, plan, project_name: str) -> str:
        """Genera config.py."""
        return f'''"""
{project_name} - Configuration
Auto-generated by TITAN OMNISCALE X
"""
import os

class Config:
    """Application configuration."""
    APP_NAME = "{project_name}"
    APP_TYPE = "{plan.template_type}"
    DEBUG = True
    PORT = {plan.config_vars.get('port', 8000)}
    HOST = "0.0.0.0"
    SECRET_KEY = "{plan.config_vars.get('secret_key', secrets.token_hex(32))}"
    DATABASE_NAME = "{plan.config_vars.get('db_name', project_name + '.db')}"

    # Pagination
    ITEMS_PER_PAGE = 20

    # Dates
    DATE_FORMAT = "%Y-%m-%d"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SECRET_KEY = os.environ.get("SECRET_KEY", Config.SECRET_KEY)
'''

    # ================================================================
    #  HTML TEMPLATE GENERATORS
    # ================================================================

    def _gen_base_template(self, plan, project_name: str) -> str:
        """Genera templates/base.html - Layout base."""
        return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{{{% block title %}}}}{project_name}{{{{% endblock %}}}}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">
            <a href="/">{project_name}</a>
        </div>
        <div class="nav-links">
            <a href="/">Dashboard</a>
            {''.join(f'<a href="/{e["name"].lower()}s">{e["name"]}s</a>' for e in plan.entities[:5])}
        </div>
    </nav>
    <main class="container">
        {{{{% block content %}}}}
        {{{{% endblock %}}}}
    </main>
    <footer class="footer">
        <p>{project_name} - Powered by TITAN OMNISCALE X</p>
    </footer>
</body>
</html>'''

    def _gen_dashboard_template(self, plan, project_name: str) -> str:
        """Genera templates/dashboard.html."""
        entity_cards = []
        for entity in plan.entities[:4]:
            name = entity.get("name", "Item")
            name_lower = name.lower()
            entity_cards.append(f'''
            <div class="card">
                <h3>{name}s</h3>
                <p>Gestionar {name_lower}s</p>
                <a href="/{name_lower}s" class="btn">Ver {name}s</a>
            </div>''')

        cards_str = "\n".join(entity_cards) if entity_cards else '''
            <div class="card">
                <h3>Bienvenido</h3>
                <p>Sistema listo para usar.</p>
            </div>'''

        return f'''{{% extends "base.html" %}}

{{% block title %}}}}Dashboard - {project_name}{{% endblock %}}

{{% block content %}}}}
<h1>Dashboard</h1>
<div class="grid">
    {cards_str}
</div>

{{% if stats %}}}}
<div class="stats-section">
    <h2>Estadísticas</h2>
    <div class="grid">
        {{% for key, value in stats.items() %}}}}
        <div class="stat-card">
            <span class="stat-value">{{{{ value }}}}</span>
            <span class="stat-label">{{{{ key }}}}</span>
        </div>
        {{% endfor %}}}}
    </div>
</div>
{{% endif %}}}}
{{% endblock %}}'''

    def _gen_list_template(self, plan, project_name: str) -> str:
        """Genera templates/list.html - Lista de entidades con CRUD."""
        return '''{% extends "base.html" %}

{% block title %}{{ entity_name }}s - {{ app_name }}{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ entity_name }}s</h1>
    <div class="actions">
        <form method="get" class="search-form">
            <input type="text" name="search" placeholder="Buscar..." value="{{ search|default('') }}">
            <button type="submit" class="btn">Buscar</button>
        </form>
        <button class="btn btn-primary" onclick="openCreateForm()">+ Nuevo {{ entity_name }}</button>
    </div>
</div>

<div class="table-container">
    <table class="data-table">
        <thead>
            <tr>
                <th>ID</th>
                <th>Nombre</th>
                <th>Creado</th>
                <th>Acciones</th>
            </tr>
        </thead>
        <tbody>
            {% for item in items %}
            <tr>
                <td>{{ item.id }}</td>
                <td>{{ item.name|default('') }}</td>
                <td>{{ item.created_at|default('') }}</td>
                <td class="actions-cell">
                    <button class="btn btn-sm" onclick="editItem({{ item.id }})">Editar</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteItem({{ item.id }})">Eliminar</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="pagination">
    {% if page > 1 %}
    <a href="?page={{ page - 1 }}" class="btn">&laquo; Anterior</a>
    {% endif %}
    <span>Página {{ page }}</span>
</div>

<!-- Create/Edit Modal -->
<div id="itemModal" class="modal" style="display:none">
    <div class="modal-content">
        <h2 id="modalTitle">Nuevo {{ entity_name }}</h2>
        <form id="itemForm">
            <div class="form-group">
                <label>Nombre</label>
                <input type="text" name="name" required>
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-primary">Guardar</button>
                <button type="button" class="btn" onclick="closeModal()">Cancelar</button>
            </div>
        </form>
    </div>
</div>

<script>
const entityName = "{{ entity_name_lower }}";
let editingId = null;

function openCreateForm() {
    editingId = null;
    document.getElementById('modalTitle').textContent = 'Nuevo ' + entityName;
    document.getElementById('itemForm').reset();
    document.getElementById('itemModal').style.display = 'block';
}

function editItem(id) {
    editingId = id;
    document.getElementById('modalTitle').textContent = 'Editar ' + entityName;
    fetch('/api/' + entityName + 's/' + id)
        .then(r => r.json())
        .then(data => {
            const form = document.getElementById('itemForm');
            form.name.value = data.name || '';
            document.getElementById('itemModal').style.display = 'block';
        });
}

function deleteItem(id) {
    if (confirm('Eliminar este elemento?')) {
        fetch('/api/' + entityName + 's/' + id, {method: 'DELETE'})
            .then(() => location.reload());
    }
}

function closeModal() {
    document.getElementById('itemModal').style.display = 'none';
}

document.getElementById('itemForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const data = {name: this.name.value};
    const url = editingId
        ? '/api/' + entityName + 's/' + editingId
        : '/api/' + entityName + 's';
    const method = editingId ? 'PUT' : 'POST';
    fetch(url, {method: method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)})
        .then(() => { closeModal(); location.reload(); });
});
</script>
{% endblock %}'''

    def _gen_form_template(self, plan, project_name: str) -> str:
        """Genera templates/form.html - Formulario de creación/edición."""
        fields_html = []
        for entity in plan.entities[:1]:
            for f in entity.get("fields", []):
                parts = f.split(":")
                fname = parts[0]
                ftype = parts[1] if len(parts) > 1 else "str"
                input_type = {"int": "number", "float": "number", "datetime": "datetime-local",
                              "bool": "checkbox"}.get(ftype, "text")
                fields_html.append(f'''
            <div class="form-group">
                <label for="{fname}">{fname.replace("_", " ").title()}</label>
                <input type="{input_type}" id="{fname}" name="{fname}">
            </div>''')

        fields_str = "\n".join(fields_html) if fields_html else '''
            <div class="form-group">
                <label for="name">Nombre</label>
                <input type="text" id="name" name="name" required>
            </div>'''

        return '''{% extends "base.html" %}

{% block title %}{{ entity_name }} - Form{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ entity_name }}</h1>
</div>
<form class="form-container" method="POST" action="/api/{{ entity_name_lower }}s">
''' + fields_str + '''
    <div class="form-actions">
        <button type="submit" class="btn btn-primary">Guardar</button>
        <a href="/{{ entity_name_lower }}s" class="btn">Cancelar</a>
    </div>
</form>
{% endblock %}'''

    def _gen_css(self, plan, project_name: str) -> str:
        """Genera static/style.css - Estilos CSS profesionales."""
        return '''/* TITAN OMNISCALE X - Generated Styles */
:root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --danger: #dc2626;
    --success: #16a34a;
    --warning: #f59e0b;
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text: #1e293b;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --radius: 8px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}

/* Navbar */
.navbar {
    background: var(--primary);
    color: white;
    padding: 0 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 56px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.nav-brand a { color: white; text-decoration: none; font-size: 1.25rem; font-weight: 700; }
.nav-links a { color: rgba(255,255,255,0.9); text-decoration: none; margin-left: 1.5rem; font-size: 0.95rem; }
.nav-links a:hover { color: white; }

/* Container */
.container { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }

/* Grid */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }

/* Cards */
.card {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--border);
}
.card h3 { margin-bottom: 0.5rem; color: var(--primary); }
.card p { color: var(--text-muted); margin-bottom: 1rem; }

/* Stat cards */
.stat-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    padding: 1.25rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--border);
}
.stat-value { display: block; font-size: 2rem; font-weight: 700; color: var(--primary); }
.stat-label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem; }

/* Buttons */
.btn {
    display: inline-block;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--card-bg);
    color: var(--text);
    text-decoration: none;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.15s ease;
}
.btn:hover { background: var(--bg); }
.btn-primary { background: var(--primary); color: white; border-color: var(--primary); }
.btn-primary:hover { background: var(--primary-dark); }
.btn-danger { background: var(--danger); color: white; border-color: var(--danger); }
.btn-sm { padding: 0.25rem 0.75rem; font-size: 0.8rem; }

/* Table */
.table-container { overflow-x: auto; margin-top: 1rem; }
.data-table { width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: var(--radius); overflow: hidden; }
.data-table th, .data-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border); }
.data-table th { background: var(--bg); font-weight: 600; color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; }
.data-table tr:hover { background: rgba(37, 99, 235, 0.03); }
.actions-cell { white-space: nowrap; }
.actions-cell .btn { margin-right: 0.25rem; }

/* Page header */
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.actions { display: flex; gap: 0.75rem; align-items: center; }
.search-form { display: flex; gap: 0.5rem; }
.search-form input { padding: 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); }

/* Forms */
.form-container { max-width: 600px; background: var(--card-bg); padding: 2rem; border-radius: var(--radius); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.form-group { margin-bottom: 1.25rem; }
.form-group label { display: block; margin-bottom: 0.25rem; font-weight: 500; }
.form-group input, .form-group select, .form-group textarea {
    width: 100%; padding: 0.5rem; border: 1px solid var(--border); border-radius: var(--radius); font-size: 0.95rem;
}
.form-actions { display: flex; gap: 0.75rem; margin-top: 1.5rem; }

/* Modal */
.modal { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; }
.modal-content { background: var(--card-bg); padding: 2rem; border-radius: var(--radius); max-width: 500px; width: 90%; }

/* Pagination */
.pagination { display: flex; justify-content: center; gap: 1rem; margin-top: 2rem; align-items: center; }

/* Footer */
.footer { text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.85rem; margin-top: 3rem; }

/* Responsive */
@media (max-width: 768px) {
    .navbar { padding: 0 1rem; }
    .container { padding: 0 1rem; }
    .page-header { flex-direction: column; gap: 1rem; }
    .actions { flex-direction: column; width: 100%; }
    .search-form { width: 100%; }
    .search-form input { flex: 1; }
}
'''

    def _gen_readme(self, plan, project_name: str) -> str:
        """Genera README.md."""
        entity_list = "\n".join(f"- **{e['name']}**: {', '.join(f.split(':')[0] for f in e.get('fields', []))}" for e in plan.entities)
        endpoint_list = "\n".join(f"- `{ep.get('method', 'GET')} {ep.get('path', '/')}` - {ep.get('desc', '')}" for ep in plan.endpoints[:15])

        return f'''# {project_name}

> Auto-generated by **TITAN OMNISCALE X** - {plan.template_type.replace('_', ' ').title()}

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

Open http://localhost:{plan.config_vars.get('port', 8000)} in your browser.

## Entities

{entity_list if entity_list else "- Generic Item"}

## API Endpoints

{endpoint_list if endpoint_list else "- GET /health - Health check"}

## Tech Stack

- **FastAPI** - Modern async web framework
- **SQLite** - Embedded database (no server needed)
- **Jinja2** - HTML templates
- **uvicorn** - ASGI server

## Project Structure

```
{project_name}/
  main.py           # FastAPI application
  models.py         # Data models
  database.py       # Database configuration
  services.py       # Business logic
  config.py         # Configuration
  templates/        # HTML templates
  static/           # CSS/JS assets
  data/             # SQLite database (auto-created)
```
'''

    # ================================================================
    #  HELPER METHODS
    # ================================================================

    def _fallback_plan(self, request: str):
        """Plan de generación fallback sin ThinkingEngine."""
        from src.core.thinking_engine import GenerationPlan

        return GenerationPlan(
            template_type="generic",
            modules=["models", "api", "services", "templates"],
            entities=[{"name": "Item", "fields": ["name:str", "description:str", "created_at:datetime"]}],
            endpoints=[
                {"method": "GET", "path": "/api/items", "desc": "List items"},
                {"method": "POST", "path": "/api/items", "desc": "Create item"},
                {"method": "GET", "path": "/health", "desc": "Health check"},
            ],
            config_vars={"db_name": "app.db", "port": 8000},
            confidence=0.3,
            source="fallback",
        )

    def _generate_project_name(self, template_type: str, request: str) -> str:
        """Genera un nombre de proyecto válido."""
        # Clean request to make a project name
        name = re.sub(r'[^a-zA-Z0-9\s]', '', request.lower())
        words = name.split()[:3]
        if words:
            project_name = "_".join(words)
        else:
            project_name = template_type
        # Ensure it's a valid directory name
        project_name = re.sub(r'[^a-z0-9_]', '_', project_name).strip('_')
        if not project_name:
            project_name = "titan_app"

        # Add timestamp for uniqueness
        import time
        project_name += f"_{int(time.time()) % 100000}"

        return project_name

    # ================================================================
    #  LIST AVAILABLE TEMPLATES
    # ================================================================

    @staticmethod
    def list_templates() -> Dict[str, List[str]]:
        """Lista todos los templates disponibles."""
        return {
            "apps": [
                "web_api - API REST con FastAPI + SQLite",
                "crud_dashboard - Panel CRUD con dashboard",
                "inventory - Sistema de inventario y stock",
                "invoice_billing - Sistema de facturación",
                "crm - Gestión de clientes y ventas",
                "task_manager - Gestión de tareas y proyectos",
                "auth_system - Sistema de autenticación",
                "report_generator - Generador de reportes",
                "notification_service - Servicio de notificaciones",
                "scheduler - Sistema de agenda y citas",
                "chatbot_service - Servicio de chatbot",
                "file_manager - Gestor de archivos",
                "dashboard - Panel de control general",
            ],
            "automations": [
                "email_sender - Envío automático de emails",
                "data_sync - Sincronización de datos",
                "file_watcher - Monitoreo de archivos",
                "webhook_handler - Manejador de webhooks",
                "scheduled_report - Reportes programados",
                "database_backup - Backup automático de BD",
                "api_monitor - Monitor de APIs",
                "notification_dispatcher - Despacho de notificaciones",
            ],
        }
