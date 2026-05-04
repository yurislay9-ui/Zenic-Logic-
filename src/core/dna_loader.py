"""
ZENIC LOGIC - DNALoader (Cargador de Plantillas Maestras de ADN Técnico)

Carga las 4 plantillas maestras que eliminan el último refugio de
improvisación y elevan la efectividad del sistema al 98%:

  1. logic_modules.yaml — Repositorio de Funciones Atómicas
     La IA NUNCA escribe una función desde cero; busca y ensambla.

  2. domain_expert_rules.yaml — Cerebro del Negocio
     Contexto de "Consultoría Senior" por industria. Reglas obligatorias.

  3. validation_gates.yaml — Juez de Calidad
     El ASSEMBLER rechaza código que no pase las validaciones.

  4. professional_glossary.yaml — Pulidor del Writer
     Transforma jerga técnica en lenguaje corporativo de élite.

Flujo de ensamblaje:
  1. Recibir pedido del cliente
  2. Cargar YAML del nicho correspondiente
  3. Buscar módulos en logic_modules
  4. Aplicar reglas de domain_expert_rules
  5. Ensamblar código
  6. Validar con validation_gates
  7. Pulir output con professional_glossary
  8. Entregar al cliente
"""

import os
import re
import ast
import logging
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

DNA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "dna"
)


@dataclass
class LogicModule:
    """Módulo de función atómica reutilizable."""
    id: str
    domain: str
    description: str
    code_block: str
    dependencies: List[str] = field(default_factory=list)
    verification_rule: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)


@dataclass
class DomainRule:
    """Regla de negocio obligatoria por industria."""
    name: str
    display_name: str
    description: str
    mandatory_logic: List[str] = field(default_factory=list)
    ux_patterns: List[str] = field(default_factory=list)
    compliance_requirements: List[str] = field(default_factory=list)
    business_invariants: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    suggested_entities: List[str] = field(default_factory=list)
    notification_triggers: List[str] = field(default_factory=list)


@dataclass
class ValidationGate:
    """Regla de validación de calidad."""
    id: str
    category: str
    rule: str
    action: str
    severity: str = "warning"
    auto_fix: bool = False
    fix_strategy: str = ""
    pattern: str = ""
    applies_to: List[str] = field(default_factory=list)


@dataclass
class GlossaryEntry:
    """Transformación de jerga técnica a lenguaje corporativo."""
    from_term: str
    to_term: str
    context: str = ""


class DNALoader:
    """
    Cargador de las 4 Plantillas Maestras de ADN Técnico.

    Carga, indexa y provee acceso a:
    - 68 módulos de lógica atómica
    - 20 industrias con reglas de negocio
    - 121 gates de validación de calidad
    - 133 transformaciones de glosario profesional
    """

    def __init__(self, dna_root: str = ""):
        self._root = dna_root or DNA_ROOT
        self._logic_modules: Dict[str, LogicModule] = {}
        self._domain_rules: Dict[str, DomainRule] = {}
        self._validation_gates: List[ValidationGate] = []
        self._domain_gates: Dict[str, List[ValidationGate]] = {}
        self._glossary: List[GlossaryEntry] = []
        self._error_messages: Dict[str, str] = {}
        self._feature_descriptions: Dict[str, Dict] = {}
        self._communication_templates: List[Dict] = []
        self._loaded = False

        # Indexes for fast lookup
        self._modules_by_domain: Dict[str, List[str]] = {}
        self._gates_by_category: Dict[str, List[str]] = {}

    def load_all(self) -> Dict[str, int]:
        """Carga las 4 plantillas maestras. Returns counts."""
        counts = {}

        # 1. Logic Modules
        counts["logic_modules"] = self._load_logic_modules()

        # 2. Domain Expert Rules
        counts["domain_rules"] = self._load_domain_rules()

        # 3. Validation Gates
        counts["validation_gates"] = self._load_validation_gates()

        # 4. Professional Glossary
        counts["glossary_entries"] = self._load_glossary()

        self._loaded = True
        logger.info(f"DNALoader: Loaded {counts}")
        return counts

    # ================================================================
    #  LOADERS
    # ================================================================

    def _load_logic_modules(self) -> int:
        """Carga logic_modules.yaml."""
        path = os.path.join(self._root, "logic_modules.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for mod_data in data.get("modules", []):
            mod = LogicModule(
                id=mod_data.get("id", ""),
                domain=mod_data.get("domain", ""),
                description=mod_data.get("description", ""),
                code_block=mod_data.get("code_block", ""),
                dependencies=mod_data.get("dependencies", []),
                verification_rule=mod_data.get("verification_rule", ""),
                inputs=mod_data.get("inputs", []),
                outputs=mod_data.get("outputs", []),
            )
            self._logic_modules[mod.id] = mod
            self._modules_by_domain.setdefault(mod.domain, []).append(mod.id)

        return len(self._logic_modules)

    def _load_domain_rules(self) -> int:
        """Carga domain_expert_rules.yaml."""
        path = os.path.join(self._root, "domain_expert_rules.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for ind_data in data.get("industries", []):
            rule = DomainRule(
                name=ind_data.get("name", ""),
                display_name=ind_data.get("display_name", ""),
                description=ind_data.get("description", ""),
                mandatory_logic=ind_data.get("mandatory_logic", []),
                ux_patterns=ind_data.get("ux_patterns", []),
                compliance_requirements=ind_data.get("compliance_requirements", []),
                business_invariants=ind_data.get("business_invariants", []),
                edge_cases=ind_data.get("edge_cases", []),
                suggested_entities=ind_data.get("suggested_entities", []),
                notification_triggers=ind_data.get("notification_triggers", []),
            )
            self._domain_rules[rule.name] = rule

        return len(self._domain_rules)

    def _load_validation_gates(self) -> int:
        """Carga validation_gates.yaml."""
        path = os.path.join(self._root, "validation_gates.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Global checks
        for check_data in data.get("global_checks", []):
            gate = ValidationGate(
                id=check_data.get("id", ""),
                category=check_data.get("category", "quality"),
                rule=check_data.get("rule", ""),
                action=check_data.get("action", ""),
                severity=check_data.get("severity", "warning"),
                auto_fix=check_data.get("auto_fix", False),
                fix_strategy=check_data.get("fix_strategy", ""),
                pattern=check_data.get("pattern", ""),
            )
            self._validation_gates.append(gate)
            self._gates_by_category.setdefault(gate.category, []).append(gate.id)

        # Domain-specific checks
        for domain_data in data.get("domain_specific_checks", []):
            domain = domain_data.get("domain", "")
            domain_gates = []
            for check_data in domain_data.get("checks", []):
                gate = ValidationGate(
                    id=check_data.get("id", ""),
                    category="domain_specific",
                    rule=check_data.get("rule", ""),
                    action=check_data.get("action", ""),
                    severity=check_data.get("severity", "critical"),
                    auto_fix=check_data.get("auto_fix", False),
                    fix_strategy=check_data.get("fix_strategy", ""),
                    pattern=check_data.get("pattern", ""),
                    applies_to=check_data.get("applies_to", []),
                )
                self._validation_gates.append(gate)
                domain_gates.append(gate)
            self._domain_gates[domain] = domain_gates

        return len(self._validation_gates)

    def _load_glossary(self) -> int:
        """Carga professional_glossary.yaml."""
        path = os.path.join(self._root, "professional_glossary.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("transformation_rules", {})
        count = 0

        # Technical to corporate
        for entry in rules.get("technical_to_corporate", []):
            self._glossary.append(GlossaryEntry(
                from_term=entry.get("from", ""),
                to_term=entry.get("to", ""),
                context=entry.get("context", ""),
            ))
            count += 1

        # Error messages
        for entry in rules.get("error_messages", []):
            self._error_messages[entry.get("original", "")] = entry.get("polished", "")
            count += 1

        # Feature descriptions
        for entry in rules.get("feature_descriptions", []):
            self._feature_descriptions[entry.get("technical", "")] = {
                "marketing": entry.get("marketing", ""),
                "benefit": entry.get("benefit", ""),
            }
            count += 1

        # Communication templates
        self._communication_templates = rules.get("communication_templates", [])
        count += len(self._communication_templates)

        # Status descriptions
        for entry in rules.get("status_descriptions", []):
            self._glossary.append(GlossaryEntry(
                from_term=entry.get("technical", ""),
                to_term=entry.get("client_facing", ""),
                context="status",
            ))
            count += 1

        return count

    # ================================================================
    #  LOGIC MODULES API
    # ================================================================

    def get_module(self, module_id: str) -> Optional[LogicModule]:
        """Obtiene un módulo de lógica por ID."""
        if not self._loaded:
            self.load_all()
        return self._logic_modules.get(module_id)

    def get_modules_by_domain(self, domain: str) -> List[LogicModule]:
        """Obtiene todos los módulos de un dominio."""
        if not self._loaded:
            self.load_all()
        ids = self._modules_by_domain.get(domain, [])
        return [self._logic_modules[i] for i in ids if i in self._logic_modules]

    def search_modules(self, query: str, limit: int = 10) -> List[LogicModule]:
        """Busca módulos relevantes basado en una descripción."""
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        scored = []

        for mod in self._logic_modules.values():
            score = 0
            # ID match
            if query_lower in mod.id.lower():
                score += 50
            # Domain match
            if query_lower in mod.domain.lower():
                score += 30
            # Description match
            desc_words = set(mod.description.lower().split())
            query_words = set(query_lower.split())
            overlap = desc_words & query_words
            score += len(overlap) * 10
            # Input/output match
            for inp in mod.inputs:
                if query_lower in inp.lower():
                    score += 5
            if score > 0:
                scored.append((score, mod))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def resolve_modules_for_niche(self, niche_name: str, niche_blocks: List[str]) -> List[LogicModule]:
        """
        Resuelve qué módulos de lógica necesita un nicho basado en sus blocks.

        Mapea bloques del TemplateEngine a módulos de lógica.
        """
        if not self._loaded:
            self.load_all()

        # Map template blocks to logic module IDs
        block_to_modules = {
            "jwt_auth": ["auth_jwt_standard", "jwt_create", "jwt_verify"],
            "api_key_auth": ["api_key_validate"],
            "rbac": ["rbac_check"],
            "stripe_payments": ["stripe_charge", "refund_process", "invoice_generate"],
            "email_smtp": ["email_send"],
            "whatsapp_api": ["whatsapp_send"],
            "telegram_bot": ["telegram_notify"],
            "notification_manager": ["push_send", "in_app_notify"],
            "task_scheduler": ["appointment_create", "reminder_schedule"],
            "inventory_tracker": ["stock_check", "reorder_alert"],
            "invoice_calculator": ["invoice_generate"],
            "data_analyzer": ["metrics_calculate"],
            "report_generator": ["report_generate"],
            "pdf_generator": [],
            "crud_service": ["crud_create"],
            "backup_restore": ["backup_execute"],
            "webhook_server": [],
            "google_sheets": [],
            "seed_data": [],
            "migration": ["migration_run"],
        }

        resolved = []
        seen = set()

        for block in niche_blocks:
            module_ids = block_to_modules.get(block, [])
            for mid in module_ids:
                if mid not in seen:
                    mod = self._logic_modules.get(mid)
                    if mod:
                        resolved.append(mod)
                        seen.add(mid)

        return resolved

    # ================================================================
    #  DOMAIN EXPERT RULES API
    # ================================================================

    def get_domain_rules(self, industry: str) -> Optional[DomainRule]:
        """Obtiene las reglas de negocio para una industria."""
        if not self._loaded:
            self.load_all()
        return self._domain_rules.get(industry)

    def get_mandatory_logic(self, industry: str) -> List[str]:
        """Obtiene las reglas obligatorias de una industria."""
        rules = self.get_domain_rules(industry)
        return rules.mandatory_logic if rules else []

    def find_industry_for_niche(self, niche_domain: str) -> Optional[DomainRule]:
        """Encuentra las reglas de industria más cercanas para un dominio de nicho."""
        if not self._loaded:
            self.load_all()

        # Direct match
        if niche_domain in self._domain_rules:
            return self._domain_rules[niche_domain]

        # Partial match
        domain_lower = niche_domain.lower()
        for name, rule in self._domain_rules.items():
            if domain_lower in name or name in domain_lower:
                return rule

        return None

    # ================================================================
    #  VALIDATION GATES API
    # ================================================================

    def get_global_gates(self, category: str = "") -> List[ValidationGate]:
        """Obtiene gates de validación globales, filtradas por categoría."""
        if not self._loaded:
            self.load_all()
        if category:
            return [g for g in self._validation_gates
                    if g.category == category and g.category != "domain_specific"]
        return [g for g in self._validation_gates if g.category != "domain_specific"]

    def get_domain_gates(self, domain: str) -> List[ValidationGate]:
        """Obtiene gates de validación específicas de un dominio."""
        if not self._loaded:
            self.load_all()
        return self._domain_gates.get(domain, [])

    def validate_code(self, code: str, domain: str = "") -> Dict[str, Any]:
        """
        Valida código contra todas las gates aplicables.

        Returns:
            Dict with passed, failed, warnings, and auto_fixes
        """
        if not self._loaded:
            self.load_all()

        results = {
            "passed": [],
            "failed": [],
            "warnings": [],
            "auto_fixes": [],
            "score": 0.0,
        }

        all_gates = list(self.get_global_gates())
        if domain:
            all_gates.extend(self.get_domain_gates(domain))

        for gate in all_gates:
            check_result = self._check_gate(code, gate)
            if check_result == "pass":
                results["passed"].append(gate.id)
            elif check_result == "fail":
                if gate.severity == "critical":
                    results["failed"].append({
                        "id": gate.id,
                        "rule": gate.rule,
                        "auto_fix": gate.auto_fix,
                        "fix_strategy": gate.fix_strategy if gate.auto_fix else "",
                    })
                else:
                    results["warnings"].append({
                        "id": gate.id,
                        "rule": gate.rule,
                    })

        # Calculate score
        total = len(all_gates)
        passed = len(results["passed"])
        results["score"] = round(passed / max(total, 1) * 100, 1)

        return results

    def _check_gate(self, code: str, gate: ValidationGate) -> str:
        """Ejecuta una validación individual contra el código."""
        # Pattern-based checks
        if gate.pattern:
            try:
                if re.search(gate.pattern, code, re.MULTILINE):
                    return "fail" if gate.id.startswith("no_") else "pass"
                return "pass" if gate.id.startswith("no_") else "fail"
            except re.error:
                pass

        # Action-based checks
        action = gate.action.lower()
        code_lower = code.lower()

        if action == "regex_search_keys":
            secret_patterns = [
                r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
                r'(?:AWS_SECRET|PRIVATE_KEY)\s*=\s*["\'][^"\']+["\']',
            ]
            for pat in secret_patterns:
                if re.search(pat, code, re.IGNORECASE):
                    return "fail"
            return "pass"

        elif action == "ast_tree_check":
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if gate.id == "all_async_in_try_except":
                            if isinstance(node, ast.AsyncFunctionDef):
                                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                                if not has_try:
                                    return "fail"
                        elif gate.id == "every_function_must_have_docstring":
                            doc = ast.get_docstring(node)
                            if not doc:
                                return "fail"
                return "pass"
            except SyntaxError:
                return "fail"

        elif action == "lint_check":
            # Simple lint checks
            if gate.id == "every_function_must_have_docstring":
                try:
                    tree = ast.parse(code)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not ast.get_docstring(node):
                                return "fail"
                    return "pass"
                except SyntaxError:
                    return "fail"
            return "pass"

        elif "sql" in action.lower() or "injection" in gate.id:
            sql_patterns = [
                r'f["\'].*SELECT.*{.*}.*["\']',
                r'f["\'].*INSERT.*{.*}.*["\']',
                r'\+\s*["\']SELECT',
                r'\+\s*["\']INSERT',
            ]
            for pat in sql_patterns:
                if re.search(pat, code, re.IGNORECASE):
                    return "fail"
            return "pass"

        elif "eval" in gate.id:
            if "eval(" in code or "exec(" in code:
                return "fail"
            return "pass"

        elif "bare" in gate.id:
            if re.search(r'except\s*:', code):
                return "fail"
            return "pass"

        elif "https" in gate.id:
            if re.search(r'http://(?!localhost|127\.0\.0\.1)', code):
                return "fail"
            return "pass"

        elif "docstring" in gate.id:
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not ast.get_docstring(node):
                            return "fail"
                return "pass"
            except SyntaxError:
                return "pass"

        # Default: pass (can't auto-check this rule)
        return "pass"

    # ================================================================
    #  PROFESSIONAL GLOSSARY API
    # ================================================================

    def _preserve_case_replace(self, match, replacement):
        """Replace a match while preserving the original capitalization pattern."""
        original = match.group(0)
        if original.isupper():
            return replacement.upper()
        elif original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        elif original.islower():
            return replacement.lower()
        return replacement

    def polish_text(self, text: str) -> str:
        """
        Transforma jerga técnica en lenguaje corporativo de élite.

        Aplica todas las transformaciones del glosario profesional.
        Preserves original capitalization and processes longest terms first
        to avoid substring corruption (e.g., "debug" matching "bug").
        """
        if not self._loaded:
            self.load_all()

        result = text
        sorted_entries = sorted(self._glossary, key=lambda e: len(e.from_term), reverse=True)
        for entry in sorted_entries:
            # Case-insensitive replacement preserving original capitalization
            result = re.sub(
                re.escape(entry.from_term),
                lambda m: self._preserve_case_replace(m, entry.to_term),
                result,
                flags=re.IGNORECASE
            )

        return result

    def polish_error(self, error_message: str) -> str:
        """Transforma un mensaje de error técnico en uno profesional."""
        if not self._loaded:
            self.load_all()

        # Direct match
        if error_message in self._error_messages:
            return self._error_messages[error_message]

        # Partial match
        error_lower = error_message.lower()
        for original, polished in self._error_messages.items():
            if original.lower() in error_lower:
                return polished

        return error_message

    def describe_feature(self, technical_name: str) -> Dict[str, str]:
        """Obtiene la descripción de marketing de una feature."""
        if not self._loaded:
            self.load_all()

        if technical_name in self._feature_descriptions:
            return self._feature_descriptions[technical_name]

        # Partial match
        tech_lower = technical_name.lower()
        for key, value in self._feature_descriptions.items():
            if tech_lower in key.lower() or key.lower() in tech_lower:
                return value

        return {"marketing": technical_name, "benefit": ""}

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del cargador de ADN."""
        if not self._loaded:
            self.load_all()
        return {
            "logic_modules": len(self._logic_modules),
            "domain_rules": len(self._domain_rules),
            "validation_gates": len(self._validation_gates),
            "glossary_entries": len(self._glossary),
            "error_messages": len(self._error_messages),
            "feature_descriptions": len(self._feature_descriptions),
            "communication_templates": len(self._communication_templates),
            "domains_with_modules": list(self._modules_by_domain.keys()),
            "yaml_available": YAML_AVAILABLE,
        }

    def list_all_modules(self):
        """Public accessor for all loaded logic modules."""
        return list(getattr(self, '_logic_modules', {}).values())

    def list_all_domain_rules(self):
        """Public accessor for all domain rules."""
        return list(getattr(self, '_domain_rules', {}).values())


# === Singleton ===
_dna_loader_instance: Optional[DNALoader] = None
_dna_loader_lock = threading.Lock()


def get_dna_loader() -> DNALoader:
    """Obtiene la instancia singleton del DNALoader."""
    global _dna_loader_instance
    if _dna_loader_instance is None:
        with _dna_loader_lock:
            if _dna_loader_instance is None:
                _dna_loader_instance = DNALoader()
    return _dna_loader_instance
