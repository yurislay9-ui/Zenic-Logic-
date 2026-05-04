"""
Unit tests for DNALoader

Tests loading of YAML templates (logic_modules, domain_rules,
validation_gates, glossary), parsing of dataclasses, and
validation gate checking logic.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, mock_open

from src.core.dna_loader import (
    DNALoader, LogicModule, DomainRule, ValidationGate, GlossaryEntry,
    get_dna_loader, YAML_AVAILABLE,
)


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def dna_loader(tmp_path):
    """Create a DNALoader with a temporary DNA root directory."""
    return DNALoader(dna_root=str(tmp_path))


@pytest.fixture
def dna_root_with_files(tmp_path):
    """Create a DNA root directory with sample YAML files."""
    dna_dir = tmp_path / "dna"
    dna_dir.mkdir()
    return dna_dir


SAMPLE_LOGIC_MODULES = """
modules:
  - id: auth_jwt_standard
    domain: authentication
    description: Standard JWT authentication module
    code_block: "def create_jwt(): pass"
    dependencies: ["pyjwt"]
    verification_rule: "jwt_present"
    inputs: ["username", "password"]
    outputs: ["token"]
  - id: stripe_charge
    domain: payments
    description: Stripe payment charge
    code_block: "def charge(): pass"
    dependencies: ["stripe"]
    inputs: ["amount", "currency"]
    outputs: ["charge_id"]
"""

SAMPLE_DOMAIN_RULES = """
industries:
  - name: healthcare
    display_name: Healthcare
    description: Healthcare industry rules
    mandatory_logic: ["hipaa_compliance", "patient_data_encryption"]
    ux_patterns: ["accessibility_first"]
    compliance_requirements: ["HIPAA"]
    business_invariants: ["patient_consent_required"]
  - name: fintech
    display_name: Financial Technology
    description: Fintech industry rules
    mandatory_logic: ["pci_compliance", "audit_trail"]
    compliance_requirements: ["PCI-DSS"]
"""

SAMPLE_VALIDATION_GATES = """
global_checks:
  - id: no_hardcoded_secrets
    category: security
    rule: "No hardcoded secrets"
    action: regex_search_keys
    severity: critical
    auto_fix: false
  - id: no_eval_usage
    category: security
    rule: "No eval() or exec() usage"
    action: check_eval
    severity: critical
    auto_fix: false
    pattern: "\\\\b(eval|exec)\\\\s*\\\\("
  - id: every_function_must_have_docstring
    category: quality
    rule: "Every function must have a docstring"
    action: lint_check
    severity: warning
domain_specific_checks:
  - domain: healthcare
    checks:
      - id: hipaa_data_encryption
        rule: "PHI must be encrypted"
        action: check_encryption
        severity: critical
"""

SAMPLE_GLOSSARY = """
transformation_rules:
  technical_to_corporate:
    - from: "refactor"
      to: "optimize"
      context: "code improvement"
  error_messages:
    - original: "NullPointerException"
      polished: "Unexpected value encountered"
  feature_descriptions:
    - technical: "auto_scaling"
      marketing: "Elastic Capacity"
      benefit: "Automatically adapts to demand"
  communication_templates:
    - name: "status_update"
      template: "Progress update: ..."
  status_descriptions:
    - technical: "build_failed"
      client_facing: "Setup requires attention"
"""


@pytest.fixture
def populated_dna_loader(tmp_path):
    """Create a DNALoader with sample YAML files written to disk."""
    dna_dir = tmp_path / "dna"
    dna_dir.mkdir()

    if YAML_AVAILABLE:
        (dna_dir / "logic_modules.yaml").write_text(SAMPLE_LOGIC_MODULES, encoding="utf-8")
        (dna_dir / "domain_expert_rules.yaml").write_text(SAMPLE_DOMAIN_RULES, encoding="utf-8")
        (dna_dir / "validation_gates.yaml").write_text(SAMPLE_VALIDATION_GATES, encoding="utf-8")
        (dna_dir / "professional_glossary.yaml").write_text(SAMPLE_GLOSSARY, encoding="utf-8")

    loader = DNALoader(dna_root=str(dna_dir))
    return loader


# ============================================================
#  LogicModule Dataclass Tests
# ============================================================

class TestLogicModule:
    """Tests for LogicModule dataclass."""

    def test_create_logic_module(self):
        """Should create with all fields."""
        mod = LogicModule(
            id="test_mod", domain="auth", description="Test module",
            code_block="pass", dependencies=["dep1"],
            verification_rule="rule1", inputs=["in1"], outputs=["out1"],
        )
        assert mod.id == "test_mod"
        assert mod.domain == "auth"
        assert mod.dependencies == ["dep1"]

    def test_default_lists(self):
        """Should default to empty lists for list fields."""
        mod = LogicModule(id="m1", domain="d", description="desc", code_block="code")
        assert mod.dependencies == []
        assert mod.inputs == []
        assert mod.outputs == []

    def test_verification_rule_default(self):
        """Verification rule should default to empty string."""
        mod = LogicModule(id="m1", domain="d", description="desc", code_block="code")
        assert mod.verification_rule == ""


# ============================================================
#  DomainRule Dataclass Tests
# ============================================================

class TestDomainRule:
    """Tests for DomainRule dataclass."""

    def test_create_domain_rule(self):
        """Should create with mandatory and optional fields."""
        rule = DomainRule(
            name="healthcare", display_name="Healthcare",
            description="Healthcare rules",
            mandatory_logic=["hipaa"],
            compliance_requirements=["HIPAA"],
        )
        assert rule.name == "healthcare"
        assert rule.mandatory_logic == ["hipaa"]

    def test_default_fields(self):
        """Should default to empty lists for optional fields."""
        rule = DomainRule(name="x", display_name="X", description="d")
        assert rule.ux_patterns == []
        assert rule.edge_cases == []

    def test_notification_triggers_default(self):
        """Notification triggers should default to empty list."""
        rule = DomainRule(name="x", display_name="X", description="d")
        assert rule.notification_triggers == []


# ============================================================
#  DNALoader Loading Tests
# ============================================================

class TestDNALoading:
    """Tests for DNALoader.load_all and individual loaders."""

    def test_load_all_returns_counts(self, populated_dna_loader):
        """load_all should return counts for each template type."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        counts = populated_dna_loader.load_all()
        assert "logic_modules" in counts
        assert "domain_rules" in counts
        assert "validation_gates" in counts
        assert "glossary_entries" in counts

    def test_load_logic_modules(self, populated_dna_loader):
        """Should load logic modules from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mod = populated_dna_loader.get_module("auth_jwt_standard")
        assert mod is not None
        assert mod.domain == "authentication"

    def test_load_domain_rules(self, populated_dna_loader):
        """Should load domain expert rules from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.get_domain_rules("healthcare")
        assert rule is not None
        assert "HIPAA" in rule.compliance_requirements

    def test_load_validation_gates(self, populated_dna_loader):
        """Should load validation gates from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_global_gates()
        assert len(gates) > 0
        # Domain-specific gates should not appear in global
        assert all(g.category != "domain_specific" for g in gates)

    def test_load_glossary(self, populated_dna_loader):
        """Should load glossary entries from YAML."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        polished = populated_dna_loader.polish_text("refactor the code")
        assert "optimize" in polished.lower()

    def test_load_empty_directory(self, dna_loader):
        """Should handle empty DNA root gracefully."""
        counts = dna_loader.load_all()
        assert counts["logic_modules"] == 0
        assert counts["domain_rules"] == 0
        assert counts["validation_gates"] == 0
        assert counts["glossary_entries"] == 0

    def test_load_nonexistent_directory(self, tmp_path):
        """Should handle nonexistent DNA root gracefully."""
        loader = DNALoader(dna_root=str(tmp_path / "nonexistent"))
        counts = loader.load_all()
        assert all(v == 0 for v in counts.values())


# ============================================================
#  Logic Module Query Tests
# ============================================================

class TestLogicModuleQuery:
    """Tests for logic module retrieval and search."""

    def test_get_module_auto_loads(self, populated_dna_loader):
        """get_module should auto-load if not yet loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        # Don't call load_all first
        mod = populated_dna_loader.get_module("auth_jwt_standard")
        assert mod is not None

    def test_get_module_not_found(self, populated_dna_loader):
        """Should return None for nonexistent module."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        mod = populated_dna_loader.get_module("nonexistent_module")
        assert mod is None

    def test_get_modules_by_domain(self, populated_dna_loader):
        """Should return all modules for a specific domain."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mods = populated_dna_loader.get_modules_by_domain("authentication")
        assert len(mods) >= 1
        assert all(m.domain == "authentication" for m in mods)

    def test_search_modules_by_description(self, populated_dna_loader):
        """Should find modules matching description keywords."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        results = populated_dna_loader.search_modules("JWT authentication")
        assert len(results) >= 1
        assert any(m.id == "auth_jwt_standard" for m in results)


# ============================================================
#  Domain Rule Query Tests
# ============================================================

class TestDomainRuleQuery:
    """Tests for domain rule retrieval."""

    def test_get_mandatory_logic(self, populated_dna_loader):
        """Should return mandatory logic for an industry."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        mandatory = populated_dna_loader.get_mandatory_logic("healthcare")
        assert len(mandatory) > 0

    def test_find_industry_for_niche_direct(self, populated_dna_loader):
        """Should find industry by direct name match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("healthcare")
        assert rule is not None
        assert rule.name == "healthcare"

    def test_find_industry_for_niche_partial(self, populated_dna_loader):
        """Should find industry by partial name match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("health")
        assert rule is not None

    def test_find_industry_no_match(self, populated_dna_loader):
        """Should return None for no matching industry."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        rule = populated_dna_loader.find_industry_for_niche("nonexistent_industry")
        assert rule is None


# ============================================================
#  Validation Gate Tests
# ============================================================

class TestValidationGates:
    """Tests for validation gate checking."""

    def test_validate_code_no_secrets(self, populated_dna_loader):
        """Clean code should pass secret detection."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'def hello():\n    """Greet."""\n    return "hello"'
        result = populated_dna_loader.validate_code(code)
        assert "score" in result

    def test_validate_code_with_secrets(self, populated_dna_loader):
        """Code with hardcoded secrets should fail validation."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'password = "super_secret_password_123"'
        result = populated_dna_loader.validate_code(code)
        assert len(result["failed"]) > 0

    def test_validate_code_with_eval(self, populated_dna_loader):
        """Code with eval() should fail validation."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        code = 'result = eval(user_input)'
        result = populated_dna_loader.validate_code(code)
        assert len(result["failed"]) > 0 or len(result["warnings"]) > 0

    def test_get_domain_gates(self, populated_dna_loader):
        """Should retrieve domain-specific gates."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_domain_gates("healthcare")
        assert len(gates) > 0

    def test_get_domain_gates_nonexistent(self, populated_dna_loader):
        """Should return empty list for unknown domain."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        gates = populated_dna_loader.get_domain_gates("nonexistent")
        assert gates == []


# ============================================================
#  Glossary / Polish Tests
# ============================================================

class TestGlossaryPolish:
    """Tests for professional glossary text polishing."""

    def test_polish_text(self, populated_dna_loader):
        """Should transform technical terms to corporate language."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_text("We need to refactor the module")
        assert "optimize" in result.lower()

    def test_polish_error(self, populated_dna_loader):
        """Should transform error messages to professional wording."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_error("NullPointerException")
        assert result == "Unexpected value encountered"

    def test_polish_error_no_match(self, populated_dna_loader):
        """Should return original error message when no match."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        result = populated_dna_loader.polish_error("SomeUnknownError")
        assert result == "SomeUnknownError"

    def test_describe_feature(self, populated_dna_loader):
        """Should return marketing description for a feature."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        desc = populated_dna_loader.describe_feature("auto_scaling")
        assert "marketing" in desc
        assert desc["marketing"] == "Elastic Capacity"


# ============================================================
#  Stats Tests
# ============================================================

class TestDNALoaderStats:
    """Tests for DNALoader stats property."""

    def test_stats_structure(self, populated_dna_loader):
        """Stats should contain expected keys."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        stats = populated_dna_loader.stats
        assert "logic_modules" in stats
        assert "domain_rules" in stats
        assert "validation_gates" in stats
        assert "glossary_entries" in stats
        assert "yaml_available" in stats

    def test_stats_auto_loads(self, populated_dna_loader):
        """Stats should trigger auto-load if not loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        assert not populated_dna_loader._loaded
        stats = populated_dna_loader.stats
        assert populated_dna_loader._loaded

    def test_stats_reports_yaml_availability(self, populated_dna_loader):
        """Stats should report YAML availability."""
        stats = populated_dna_loader.stats
        assert "yaml_available" in stats
        assert stats["yaml_available"] == YAML_AVAILABLE


# ============================================================
#  Singleton Tests
# ============================================================

class TestSingleton:
    """Tests for get_dna_loader singleton."""

    def test_singleton_returns_same_instance(self):
        """get_dna_loader should return the same instance."""
        import src.core.dna_loader as mod
        mod._dna_loader_instance = None
        loader1 = get_dna_loader()
        loader2 = get_dna_loader()
        assert loader1 is loader2
        # Clean up
        mod._dna_loader_instance = None

    def test_singleton_is_dna_loader_type(self):
        """Singleton should be a DNALoader instance."""
        import src.core.dna_loader as mod
        mod._dna_loader_instance = None
        loader = get_dna_loader()
        assert isinstance(loader, DNALoader)
        mod._dna_loader_instance = None

    def test_singleton_thread_safe(self):
        """Singleton should be thread-safe."""
        import src.core.dna_loader as mod
        import threading
        mod._dna_loader_instance = None
        results = []
        def get_loader():
            results.append(get_dna_loader())
        threads = [threading.Thread(target=get_loader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # All should be the same instance
        assert all(r is results[0] for r in results)
        mod._dna_loader_instance = None


# ============================================================
#  resolve_modules_for_niche Tests
# ============================================================

class TestResolveModules:
    """Tests for resolve_modules_for_niche."""

    def test_resolve_known_blocks(self, populated_dna_loader):
        """Should resolve known template blocks to logic modules."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["jwt_auth"]
        )
        # jwt_auth maps to auth_jwt_standard, jwt_create, jwt_verify
        assert any(m.id == "auth_jwt_standard" for m in modules)

    def test_resolve_unknown_blocks(self, populated_dna_loader):
        """Should return empty for blocks with no module mapping."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["pdf_generator"]
        )
        # pdf_generator maps to empty list
        assert len(modules) == 0

    def test_resolve_multiple_blocks(self, populated_dna_loader):
        """Should resolve multiple blocks without duplicates."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        populated_dna_loader.load_all()
        modules = populated_dna_loader.resolve_modules_for_niche(
            "test_niche", ["jwt_auth", "api_key_auth"]
        )
        # Both resolve modules; no duplicates
        ids = [m.id for m in modules]
        assert len(ids) == len(set(ids))
