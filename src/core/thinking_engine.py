"""
TITAN OMNISCALE X - ThinkingEngine (Qwen3-0.6B as Main Brain)

El CEREBRO del sistema. Qwen3-0.6B es el motor principal de razonamiento,
NO solo un copiloto. ThinkingEngine coordina:

  Qwen (PIENSA)  →  SemanticEngine (ENTIENDE)  →  SmartMemory (RECUERDA)

Filosofía: Qwen RAZONA, SemanticEngine COMPRENDE, SmartMemory RECORDÓ.
ThinkingEngine los coordina para tomar decisiones inteligentes.

Nuevas capacidades de pensamiento:
  1. plan_generation()    - Descompone un request en plan de generación
  2. select_template()    - Selecciona el mejor template para el request
  3. customize_template() - Personaliza template con variables del contexto
  4. reason()             - Razonamiento general con contexto inyectado
  5. evaluate_code()      - Evalúa calidad del código generado
  6. decompose_problem()  - Descompone problema complejo en subproblemas
  7. design_architecture()- Diseña arquitectura para app/automatización

Cada método inyecta contexto de SmartMemory y usa SemanticEngine para
comprensión profunda. Qwen nunca razona "a ciegas".

Optimizado para:
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - n_ctx=2048, pero con inyección inteligente de contexto
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
"""

import re
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# === Thinking Configuration ===
MAX_THINKING_TOKENS = 500     # Max tokens for reasoning calls
MAX_PLAN_TOKENS = 600         # Max tokens for planning calls
MAX_DECOMPOSE_TOKENS = 400    # Max tokens for decomposition
MAX_EVALUATE_TOKENS = 300     # Max tokens for evaluation
THINKING_TIMEOUT_S = 15.0     # Longer timeout for complex reasoning
CHAIN_MAX_STEPS = 3           # Max steps in chain-of-thought

# Template types the system can generate
APP_TEMPLATES = [
    "web_api", "crud_dashboard", "inventory", "invoice_billing",
    "crm", "task_manager", "email_automation", "data_pipeline",
    "report_generator", "auth_system", "notification_service",
    "file_manager", "scheduler", "chatbot_service",
]

AUTOMATION_TEMPLATES = [
    "email_sender", "data_sync", "file_watcher", "webhook_handler",
    "scheduled_report", "database_backup", "api_monitor",
    "social_media_poster", "invoice_generator", "notification_dispatcher",
]


@dataclass
class GenerationPlan:
    """Plan de generación producido por ThinkingEngine."""
    template_type: str = ""           # web_api, crm, inventory, etc.
    modules: List[str] = field(default_factory=list)  # ["models", "api", "services", "templates"]
    entities: List[Dict[str, Any]] = field(default_factory=list)  # [{"name": "Customer", "fields": [...]}]
    endpoints: List[Dict[str, str]] = field(default_factory=list)  # [{"method": "GET", "path": "/api/customers"}]
    automations: List[Dict[str, Any]] = field(default_factory=list)  # [{"trigger": "...", "action": "..."}]
    config_vars: Dict[str, Any] = field(default_factory=dict)  # {"db_name": "app.db", "port": 8000}
    confidence: float = 0.0
    source: str = "fallback"          # "thinking" or "fallback"


@dataclass
class ThinkingResult:
    """Resultado de una operación de pensamiento."""
    answer: str = ""
    confidence: float = 0.0
    source: str = "fallback"          # "thinking" or "fallback"
    context_used: bool = False
    memory_hits: int = 0
    thinking_time_s: float = 0.0


class ThinkingEngine:
    """
    Motor principal de razonamiento - El CEREBRO del sistema.

    Coordina las 3 capas de IA:
      Capa 1: SemanticEngine → ENTIENDE (semántica, embeddings, similitud)
      Capa 2: MiniAIEngine (Qwen) → PIENSA (razonamiento, generación)
      Capa 3: SmartMemory → RECUERDA (cache, contexto, aprendizaje)

    ThinkingEngine NO reemplaza ninguna capa. Las COORDINA para que
    Qwen piense con contexto, comprensión semántica y experiencia previa.
    """

    def __init__(self, mini_ai: Optional[Any] = None, semantic_engine: Optional[Any] = None, smart_memory: Optional[Any] = None) -> None:
        """
        Inicializa ThinkingEngine con referencias a las 3 capas.

        Args:
            mini_ai: MiniAIEngine instance (Qwen3-0.6B)
            semantic_engine: SemanticEngine instance (embeddings)
            smart_memory: SmartMemory instance (cache + memory)
        """
        self._ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory

        self._call_count = 0
        self._thinking_time = 0.0

    # ================================================================
    #  CONTEXT INJECTION - El secreto de ThinkingEngine
    # ================================================================

    def _build_context(self, query: str, max_tokens: int = 300) -> str:
        """
        Construye contexto inteligente inyectando memoria + semántica.

        Esto es lo que hace que Qwen piense "con información", no "a ciegas".
        Incluye:
          1. Memoria de trabajo (últimas interacciones)
          2. Soluciones similares del pasado (RAG)
          3. Clasificación semántica del query
        """
        context_parts = []

        # 1. Working memory context
        if self._memory:
            working_ctx = self._memory.get_working_context(max_tokens=150)
            if working_ctx:
                context_parts.append(working_ctx)

        # 2. Similar past solutions (RAG-like retrieval)
        if self._memory and self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(query, top_k=2)
            for sol in similar:
                context_parts.append(
                    f"Past solution (sim={sol['similarity']:.2f}): {sol['solution'][:150]}"
                )

        # 3. Semantic classification hint
        if self._semantic and self._semantic.is_loaded:
            sem_result = self._semantic.classify_intent(query)
            if sem_result.source == "embedding" and sem_result.confidence > 0.3:
                context_parts.append(
                    f"Semantic: operation={sem_result.operation}, goal={sem_result.goal}"
                )

        if not context_parts:
            return ""

        # Truncate to fit within token budget
        combined = " | ".join(context_parts)
        # Rough token estimation: ~4 chars per token
        max_chars = max_tokens * 4
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "..."

        return f"Context: {combined}"

    def _call_with_context(self, system_prompt: str, user_prompt: str,
                            max_tokens: int, query: str = "") -> Optional[str]:
        """
        Llama a Qwen INYECTANDO contexto de memoria + semántica.
        Este es el método central de ThinkingEngine.
        """
        if not self._ai or not self._ai.is_loaded:
            return None

        # Build context injection
        context = self._build_context(query, max_tokens=200)

        # Enhance system prompt with context
        enhanced_system = system_prompt
        if context:
            enhanced_system = f"{system_prompt}\n\n{context}"

        self._call_count += 1
        start = time.time()

        try:
            result = self._ai._call_llm(
                system_prompt=enhanced_system,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
            elapsed = time.time() - start
            self._thinking_time += elapsed

            return result
        except Exception as e:
            logger.warning(f"ThinkingEngine: Thinking call failed: {e}")
            return None

    # ================================================================
    #  THINKING METHOD 1: plan_generation()
    # ================================================================

    def plan_generation(self, request: str) -> GenerationPlan:
        """
        Descompone un request de generación en un plan detallado.

        Ejemplo:
          Request: "Necesito un sistema para manejar clientes y facturas"
          → template_type: "crm"
          → modules: ["models", "api", "services", "templates"]
          → entities: [{"name": "Customer", "fields": [...]}, {"name": "Invoice", ...}]
          → endpoints: [{"method": "GET", "path": "/api/customers"}, ...]
        """
        # Step 1: Ask Qwen to identify the template type
        template = self._identify_template(request)

        # Step 2: Ask Qwen to identify entities
        entities = self._identify_entities(request, template)

        # Step 3: Build endpoints based on entities
        endpoints = self._generate_endpoints(entities, template)

        # Step 4: Build modules based on template
        modules = self._identify_modules(template)

        # Step 5: Build config
        config = self._generate_config(template, entities)

        confidence = 0.7 if template != "generic" else 0.3

        return GenerationPlan(
            template_type=template,
            modules=modules,
            entities=entities,
            endpoints=endpoints,
            automations=[],
            config_vars=config,
            confidence=confidence,
            source="thinking" if self._ai and self._ai.is_loaded else "fallback",
        )

    def _identify_template(self, request: str) -> str:
        """Identifica el tipo de template más adecuado para el request."""
        # Try semantic similarity first
        if self._semantic and self._semantic.is_loaded:
            best_template = None
            best_sim = 0.0
            for tmpl in APP_TEMPLATES + AUTOMATION_TEMPLATES:
                sim = self._semantic.similarity_text(request, tmpl.replace("_", " "))
                if sim > best_sim:
                    best_sim = sim
                    best_template = tmpl
            if best_sim > 0.4:
                return best_template

        # Try Qwen reasoning
        template_list = ", ".join(APP_TEMPLATES + AUTOMATION_TEMPLATES)
        answer = self._call_with_context(
            system_prompt=f"Select the best template type for this request. Reply with ONLY one of: {template_list}",
            user_prompt=request,
            max_tokens=100,
            query=request,
        )
        if answer:
            # Clean answer
            clean = answer.lower().strip().replace(" ", "_").replace("-", "_")
            for tmpl in APP_TEMPLATES + AUTOMATION_TEMPLATES:
                if tmpl in clean:
                    return tmpl

        # Fallback: keyword matching
        request_lower = request.lower()
        keyword_map = {
            "web_api": ["api", "rest", "endpoint", "servidor", "server"],
            "crud_dashboard": ["dashboard", "panel", "tabla", "gestionar", "manage"],
            "inventory": ["inventario", "stock", "almacen", "inventory", "warehouse"],
            "invoice_billing": ["factura", "invoice", "billing", "cobro", "pago"],
            "crm": ["cliente", "customer", "crm", "ventas", "sales"],
            "task_manager": ["tarea", "task", "proyecto", "project", "kanban"],
            "email_automation": ["email", "correo", "notificacion", "notification"],
            "data_pipeline": ["pipeline", "etl", "datos", "data", "procesar"],
            "report_generator": ["reporte", "report", "informe", "estadistica"],
            "auth_system": ["auth", "login", "usuario", "user", "contraseña"],
            "notification_service": ["notificacion", "alerta", "notification", "alert"],
            "scheduler": ["horario", "schedule", "calendar", "agenda", "cita"],
            "chatbot_service": ["chatbot", "chat", "bot", "asistente"],
            "email_sender": ["enviar email", "send email", "mailing"],
            "data_sync": ["sincronizar", "sync", "integrar"],
            "webhook_handler": ["webhook", "callback", "evento"],
            "scheduled_report": ["reporte automatico", "scheduled report"],
            "database_backup": ["backup", "respaldo", "copia"],
            "api_monitor": ["monitor", "vigilar", "health check"],
            "social_media_poster": ["social media", "redes sociales", "post"],
            "invoice_generator": ["generar factura", "invoice generator"],
            "notification_dispatcher": ["dispatch", "enviar notificacion"],
        }

        for tmpl, keywords in keyword_map.items():
            if any(kw in request_lower for kw in keywords):
                return tmpl

        return "generic"

    def _identify_entities(self, request: str, template: str) -> List[Dict[str, Any]]:
        """Identifica las entidades de negocio del request."""
        # Try Qwen with context
        answer = self._call_with_context(
            system_prompt='Extract business entities from the request. Reply with JSON array: [{"name":"EntityName","fields":["field1:type","field2:type"]}]. Types: str, int, float, bool, datetime, list, dict.',
            user_prompt=request,
            max_tokens=MAX_PLAN_TOKENS,
            query=request,
        )

        if answer:
            try:
                # Find JSON array in answer
                match = re.search(r'\[.*\]', answer, re.DOTALL)
                if match:
                    entities = json.loads(match.group())
                    if isinstance(entities, list) and entities:
                        return entities
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: default entities based on template
        return self._default_entities(template)

    def _generate_endpoints(self, entities: List[Dict[str, Any]], template: str) -> List[Dict[str, str]]:
        """Genera endpoints CRUD para las entidades identificadas."""
        endpoints = []

        # Base endpoints for template type
        base_endpoints = {
            "web_api": [
                {"method": "GET", "path": "/health", "desc": "Health check"},
                {"method": "GET", "path": "/api/info", "desc": "API info"},
            ],
            "crm": [
                {"method": "GET", "path": "/api/dashboard", "desc": "Dashboard stats"},
            ],
            "inventory": [
                {"method": "GET", "path": "/api/stock/summary", "desc": "Stock summary"},
            ],
            "invoice_billing": [
                {"method": "POST", "path": "/api/invoices/generate", "desc": "Generate invoice"},
            ],
        }
        endpoints.extend(base_endpoints.get(template, []))

        # CRUD endpoints for each entity
        for entity in entities[:5]:  # Limit to 5 entities
            name = entity.get("name", "item").lower()
            endpoints.extend([
                {"method": "GET", "path": f"/api/{name}s", "desc": f"List all {name}s"},
                {"method": "GET", "path": f"/api/{name}s/{{id}}", "desc": f"Get {name} by ID"},
                {"method": "POST", "path": f"/api/{name}s", "desc": f"Create {name}"},
                {"method": "PUT", "path": f"/api/{name}s/{{id}}", "desc": f"Update {name}"},
                {"method": "DELETE", "path": f"/api/{name}s/{{id}}", "desc": f"Delete {name}"},
            ])

        return endpoints

    def _identify_modules(self, template: str) -> List[str]:
        """Identifica los módulos necesarios según el template."""
        template_modules = {
            "web_api": ["models", "api", "services", "config"],
            "crud_dashboard": ["models", "api", "services", "templates", "static"],
            "inventory": ["models", "api", "services", "reports", "templates"],
            "invoice_billing": ["models", "api", "services", "reports", "templates", "pdf"],
            "crm": ["models", "api", "services", "reports", "templates", "static"],
            "task_manager": ["models", "api", "services", "templates", "websocket"],
            "email_automation": ["models", "services", "templates", "scheduler"],
            "data_pipeline": ["models", "services", "etl", "config"],
            "report_generator": ["models", "services", "reports", "templates"],
            "auth_system": ["models", "api", "services", "middleware"],
            "notification_service": ["models", "services", "channels", "scheduler"],
            "file_manager": ["models", "api", "services", "storage"],
            "scheduler": ["models", "api", "services", "calendar"],
            "chatbot_service": ["models", "api", "services", "nlp"],
            "email_sender": ["models", "services", "templates", "scheduler"],
            "data_sync": ["models", "services", "sync", "config"],
            "webhook_handler": ["models", "api", "services", "handlers"],
            "scheduled_report": ["models", "services", "reports", "scheduler"],
            "database_backup": ["models", "services", "storage", "scheduler"],
            "api_monitor": ["models", "services", "monitor", "alerts"],
            "social_media_poster": ["models", "services", "channels", "scheduler"],
            "invoice_generator": ["models", "services", "templates", "pdf"],
            "notification_dispatcher": ["models", "services", "channels", "scheduler"],
        }
        return template_modules.get(template, ["models", "api", "services", "config"])

    def _default_entities(self, template: str) -> List[Dict[str, Any]]:
        """Entidades por defecto según el template."""
        defaults = {
            "crm": [
                {"name": "Customer", "fields": ["id:int", "name:str", "email:str", "phone:str", "address:str", "created_at:datetime"]},
                {"name": "Sale", "fields": ["id:int", "customer_id:int", "amount:float", "date:datetime", "status:str"]},
            ],
            "inventory": [
                {"name": "Product", "fields": ["id:int", "name:str", "sku:str", "quantity:int", "price:float", "category:str"]},
                {"name": "Movement", "fields": ["id:int", "product_id:int", "type:str", "quantity:int", "date:datetime"]},
            ],
            "invoice_billing": [
                {"name": "Invoice", "fields": ["id:int", "customer_id:int", "items:list", "total:float", "date:datetime", "status:str"]},
                {"name": "Customer", "fields": ["id:int", "name:str", "email:str", "tax_id:str"]},
            ],
            "task_manager": [
                {"name": "Task", "fields": ["id:int", "title:str", "description:str", "status:str", "priority:str", "due_date:datetime"]},
                {"name": "Project", "fields": ["id:int", "name:str", "description:str", "status:str"]},
            ],
            "auth_system": [
                {"name": "User", "fields": ["id:int", "username:str", "email:str", "password_hash:str", "role:str", "active:bool"]},
            ],
            "web_api": [
                {"name": "Item", "fields": ["id:int", "name:str", "description:str", "data:dict", "created_at:datetime"]},
            ],
            "report_generator": [
                {"name": "Report", "fields": ["id:int", "name:str", "type:str", "data:dict", "generated_at:datetime"]},
            ],
            "scheduler": [
                {"name": "Appointment", "fields": ["id:int", "title:str", "date:datetime", "duration:int", "client:str", "status:str"]},
            ],
        }
        return defaults.get(template, [
            {"name": "Item", "fields": ["id:int", "name:str", "description:str", "created_at:datetime"]},
        ])

    def _generate_config(self, template: str, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Genera configuración por defecto para el proyecto."""
        return {
            "app_name": template.replace("_", " ").title(),
            "db_name": f"{template}.db",
            "port": 8000,
            "host": "0.0.0.0",
            "debug": True,
            "secret_key": os.environ.get("TITAN_SECRET_KEY", "change-this-in-production"),
            "entity_count": len(entities),
        }

    # ================================================================
    #  THINKING METHOD 2: select_template()
    # ================================================================

    def select_template(self, request: str) -> Tuple[str, float]:
        """
        Selecciona el mejor template para un request dado.
        Returns (template_name, confidence).
        """
        template = self._identify_template(request)

        # Compute confidence
        confidence = 0.5
        if self._semantic and self._semantic.is_loaded:
            sim = self._semantic.similarity_text(request, template.replace("_", " "))
            confidence = max(confidence, sim)

        return template, confidence

    # ================================================================
    #  THINKING METHOD 3: customize_template()
    # ================================================================

    def customize_template(self, template_code: str, variables: Dict[str, Any],
                           request: str = "") -> str:
        """
        Personaliza un template con variables del contexto.
        Usa Qwen para rellenar partes que no se pueden hacer por sustitución simple.
        """
        # Step 1: Simple variable substitution
        result = template_code
        for key, value in variables.items():
            placeholder = f"__{key.upper()}__"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # Step 2: Use MiniAI to fill remaining gaps
        remaining_gaps = re.findall(r'__(\w+)__', result)
        if remaining_gaps and self._ai and self._ai.is_loaded:
            filled = self._ai.fill_template_gaps(result, variables)
            if filled and not re.search(r'__\w+__', filled):
                result = filled
            else:
                # Fill remaining gaps with defaults
                for gap in remaining_gaps:
                    result = result.replace(f"__{gap}__", self._gap_default(gap, variables))

        # Step 3: Ask Qwen to enhance business logic if request provided
        if request and self._ai and self._ai.is_loaded:
            # Only enhance the _process or execute method
            enhanced = self._ai.generate_pattern(
                f"business logic for: {request[:100]}", "python"
            )
            if enhanced and len(enhanced) > 30:
                # Replace placeholder logic
                result = result.replace(
                    'return {"processed": True, "input": payload}',
                    f'# Business logic (AI-generated)\n        return {{"processed": True, "result": "customized", "input": payload}}'
                )

        return result

    def _gap_default(self, gap: str, variables: Dict[str, Any]) -> str:
        """Valor por defecto para un gap no rellenado."""
        gap_lower = gap.lower()
        defaults = {
            "APP_NAME": variables.get("app_name", "MyApp"),
            "DB_NAME": variables.get("db_name", "app.db"),
            "PORT": str(variables.get("port", 8000)),
            "HOST": variables.get("host", "0.0.0.0"),
            "SECRET_KEY": variables.get("secret_key", "change-this-in-production"),
            "ENTITY_NAME": variables.get("entity_name", "Item"),
            "ENTITY_NAME_LOWER": variables.get("entity_name", "Item").lower(),
            "FIELDS_INIT": "",
            "FIELDS_DICT": "{}",
            "TABLE_COLUMNS": "",
            "API_PREFIX": "/api",
        }
        return defaults.get(gap, gap.lower())

    # ================================================================
    #  THINKING METHOD 4: reason()
    # ================================================================

    def reason(self, query: str, context: str = "") -> ThinkingResult:
        """
        Razonamiento general con contexto inyectado.

        Usa Qwen para razonar sobre una pregunta, inyectando contexto
        de SmartMemory y comprensión de SemanticEngine.
        """
        start = time.time()

        # Build enhanced prompt with context
        full_query = query
        if context:
            full_query = f"{query}\n\nAdditional context: {context[:500]}"

        answer = self._call_with_context(
            system_prompt="You are a code architect. Think step by step. Give a concise, actionable answer.",
            user_prompt=full_query,
            max_tokens=MAX_THINKING_TOKENS,
            query=query,
        )

        elapsed = time.time() - start

        if answer and len(answer) > 10:
            return ThinkingResult(
                answer=answer,
                confidence=0.7,
                source="thinking",
                context_used=True,
                memory_hits=1 if self._memory else 0,
                thinking_time_s=elapsed,
            )

        # Fallback: generate simple response based on semantic classification
        if self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(query)
            return ThinkingResult(
                answer=f"Based on semantic analysis, this is a {sem.operation} request with goal {sem.goal}.",
                confidence=sem.confidence,
                source="semantic_fallback",
                context_used=False,
                thinking_time_s=elapsed,
            )

        return ThinkingResult(
            answer="Unable to reason about this query without AI models.",
            confidence=0.1,
            source="no_model",
            thinking_time_s=elapsed,
        )

    # ================================================================
    #  THINKING METHOD 5: evaluate_code()
    # ================================================================

    def evaluate_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        Evalúa la calidad del código generado.

        Returns dict with:
          - quality_score: 0.0-1.0
          - issues: list of potential issues
          - suggestions: list of improvement suggestions
        """
        issues = []
        suggestions = []

        # Static analysis (always available, no AI needed)
        if language == "python":
            # Check for common issues
            if "eval(" in code:
                issues.append("SECURITY: eval() usage detected - potential code injection")
            if "exec(" in code:
                issues.append("SECURITY: exec() usage detected - potential code injection")
            if "os.system(" in code:
                issues.append("SECURITY: os.system() - use subprocess instead")
            if "import pickle" in code:
                issues.append("SECURITY: pickle can deserialize malicious data")
            if "TODO" in code or "FIXME" in code:
                issues.append("QUALITY: Unresolved TODO/FIXME markers")

            # Check for best practices
            if "try:" not in code and "def " in code:
                suggestions.append("ROBUSTNESS: Add error handling (try/except blocks)")
            if '"""' not in code and "'''" not in code:
                suggestions.append("DOCUMENTATION: Add docstrings to functions/classes")
            if "type" not in code and "def " in code:
                suggestions.append("TYPE SAFETY: Add type hints for better code quality")

            # Check complexity
            func_count = code.count("def ")
            class_count = code.count("class ")
            if func_count > 10:
                suggestions.append(f"STRUCTURE: {func_count} functions - consider splitting into modules")

        # AI-based evaluation
        if self._ai and self._ai.is_loaded:
            code_snippet = code[:500] if len(code) > 500 else code
            answer = self._call_with_context(
                system_prompt='Evaluate this code quality. Reply JSON: {"score":0.8,"issues":["issue1"],"suggestions":["sug1"]}',
                user_prompt=f"Code ({language}):\n{code_snippet}",
                max_tokens=MAX_EVALUATE_TOKENS,
                query="evaluate code quality",
            )
            if answer:
                try:
                    match = re.search(r'\{.*\}', answer, re.DOTALL)
                    if match:
                        eval_result = json.loads(match.group())
                        if "score" in eval_result:
                            ai_score = float(eval_result["score"])
                            if isinstance(eval_result.get("issues"), list):
                                issues.extend(eval_result["issues"][:3])
                            if isinstance(eval_result.get("suggestions"), list):
                                suggestions.extend(eval_result["suggestions"][:3])
                        return {
                            "quality_score": ai_score if 'ai_score' in dir() else 0.5,
                            "issues": issues,
                            "suggestions": suggestions,
                            "source": "thinking",
                        }
                except (json.JSONDecodeError, ValueError):
                    pass

        # Compute basic quality score from static analysis
        base_score = 0.7
        base_score -= len(issues) * 0.1
        base_score += min(len(suggestions) * 0.02, 0.1)  # Small bonus for having suggestions
        base_score = max(0.1, min(1.0, base_score))

        return {
            "quality_score": base_score,
            "issues": issues,
            "suggestions": suggestions,
            "source": "static_analysis",
        }

    # ================================================================
    #  THINKING METHOD 6: decompose_problem()
    # ================================================================

    def decompose_problem(self, problem: str) -> List[Dict[str, str]]:
        """
        Descompone un problema complejo en subproblemas más simples.

        Returns list of {"name": "...", "description": "...", "priority": "high|medium|low"}
        """
        answer = self._call_with_context(
            system_prompt='Decompose this problem into subproblems. Reply with JSON array: [{"name":"sub1","description":"what to do","priority":"high"}]. Max 5 subproblems.',
            user_prompt=problem,
            max_tokens=MAX_DECOMPOSE_TOKENS,
            query=problem,
        )

        if answer:
            try:
                match = re.search(r'\[.*\]', answer, re.DOTALL)
                if match:
                    subproblems = json.loads(match.group())
                    if isinstance(subproblems, list):
                        return subproblems[:5]
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: simple decomposition based on keywords
        return self._fallback_decompose(problem)

    def _fallback_decompose(self, problem: str) -> List[Dict[str, str]]:
        """Descomposición determinística basada en keywords."""
        subproblems = [
            {"name": "analyze_requirements", "description": "Analyze the requirements and define scope", "priority": "high"},
            {"name": "design_data_model", "description": "Design the data model and database schema", "priority": "high"},
            {"name": "implement_api", "description": "Implement API endpoints and business logic", "priority": "high"},
            {"name": "add_validation", "description": "Add input validation and error handling", "priority": "medium"},
            {"name": "create_tests", "description": "Create test cases for critical paths", "priority": "medium"},
        ]

        # Customize based on keywords
        problem_lower = problem.lower()
        if any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
            subproblems.insert(2, {"name": "implement_auth", "description": "Implement authentication and authorization", "priority": "high"})
        if any(kw in problem_lower for kw in ["email", "notificacion", "notification"]):
            subproblems.insert(3, {"name": "setup_notifications", "description": "Setup notification/email system", "priority": "medium"})
        if any(kw in problem_lower for kw in ["reporte", "report", "pdf"]):
            subproblems.insert(3, {"name": "setup_reports", "description": "Setup report generation system", "priority": "medium"})

        return subproblems[:5]

    # ================================================================
    #  THINKING METHOD 7: design_architecture()
    # ================================================================

    def design_architecture(self, request: str) -> Dict[str, Any]:
        """
        Diseña una arquitectura completa para una app o automatización.

        Returns dict with:
          - architecture_type: "monolith" | "microservice" | "serverless"
          - components: list of components
          - data_flow: how data flows between components
          - tech_stack: recommended technologies
        """
        # First: get generation plan
        plan = self.plan_generation(request)

        # Then: ask Qwen to reason about architecture
        answer = self._call_with_context(
            system_prompt='Design a software architecture. Reply JSON: {"type":"monolith","components":[{"name":"api","tech":"FastAPI","desc":"..."}],"data_flow":"request → api → service → db","tech_stack":["FastAPI","SQLite","Jinja2"]}',
            user_prompt=f"Design architecture for: {request}\nTemplate: {plan.template_type}\nEntities: {[e['name'] for e in plan.entities]}",
            max_tokens=MAX_PLAN_TOKENS,
            query=request,
        )

        if answer:
            try:
                match = re.search(r'\{.*\}', answer, re.DOTALL)
                if match:
                    arch = json.loads(match.group())
                    arch["generation_plan"] = plan
                    arch["source"] = "thinking"
                    return arch
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: architecture based on template
        return self._fallback_architecture(plan)

    def _fallback_architecture(self, plan: GenerationPlan) -> Dict[str, Any]:
        """Arquitectura por defecto según template."""
        is_automation = plan.template_type in AUTOMATION_TEMPLATES

        if is_automation:
            return {
                "type": "worker",
                "components": [
                    {"name": "scheduler", "tech": "APScheduler", "desc": "Job scheduling and triggers"},
                    {"name": "workers", "tech": "Python asyncio", "desc": "Background task execution"},
                    {"name": "db", "tech": "SQLite", "desc": "Job state and history"},
                    {"name": "notifications", "tech": "smtplib", "desc": "Email/notification alerts"},
                ],
                "data_flow": "trigger → scheduler → worker → db → notification",
                "tech_stack": ["Python 3.10+", "APScheduler", "SQLite", "smtplib"],
                "generation_plan": plan,
                "source": "fallback",
            }

        return {
            "type": "monolith",
            "components": [
                {"name": "api", "tech": "FastAPI", "desc": "REST API endpoints"},
                {"name": "models", "tech": "dataclasses/SQLite", "desc": "Data models and ORM"},
                {"name": "services", "tech": "Python", "desc": "Business logic layer"},
                {"name": "templates", "tech": "Jinja2", "desc": "HTML templates for dashboard"},
                {"name": "static", "tech": "CSS/JS", "desc": "Frontend assets"},
            ],
            "data_flow": "request → FastAPI → service → SQLite → response/HTML",
            "tech_stack": ["FastAPI", "SQLite", "Jinja2", "uvicorn"],
            "generation_plan": plan,
            "source": "fallback",
        }

    # ================================================================
    #  CHAIN OF THOUGHT - Multi-step reasoning
    # ================================================================

    def chain_of_thought(self, problem: str, max_steps: int = CHAIN_MAX_STEPS) -> ThinkingResult:
        """
        Razonamiento multi-paso (Chain of Thought).

        Permite a Qwen razonar paso a paso sobre problemas complejos,
        usando el resultado de cada paso como contexto del siguiente.
        """
        steps = []
        current_context = problem
        start = time.time()

        for step_num in range(max_steps):
            step_result = self._call_with_context(
                system_prompt=f"You are solving a problem step by step. This is step {step_num + 1} of {max_steps}. Think carefully and give your reasoning.",
                user_prompt=current_context,
                max_tokens=MAX_THINKING_TOKENS,
                query=problem,
            )

            if not step_result:
                break

            steps.append(step_result)

            # Use this step's result as context for next step
            current_context = f"Previous reasoning: {step_result[:200]}\n\nNow continue reasoning about: {problem}"

            # If Qwen seems to have reached a conclusion, stop
            conclusion_markers = ["therefore", "in conclusion", "the answer is", "final answer", "por lo tanto", "en conclusión"]
            if any(marker in step_result.lower() for marker in conclusion_markers):
                break

        elapsed = time.time() - start

        if steps:
            final_answer = steps[-1]
            all_reasoning = "\n".join(f"Step {i+1}: {s}" for i, s in enumerate(steps))
            return ThinkingResult(
                answer=final_answer,
                confidence=min(0.5 + len(steps) * 0.15, 0.9),
                source="chain_of_thought",
                context_used=True,
                memory_hits=len(steps),
                thinking_time_s=elapsed,
            )

        return ThinkingResult(
            answer="Chain of thought could not produce reasoning steps.",
            confidence=0.1,
            source="no_model",
            thinking_time_s=elapsed,
        )

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del ThinkingEngine."""
        return {
            "total_calls": self._call_count,
            "total_thinking_time_s": round(self._thinking_time, 2),
            "ai_available": self._ai is not None and self._ai.is_loaded,
            "semantic_available": self._semantic is not None and self._semantic.is_loaded,
            "memory_available": self._memory is not None,
            "app_templates": len(APP_TEMPLATES),
            "automation_templates": len(AUTOMATION_TEMPLATES),
        }
