"""
Unit tests for NicheLoader

Tests loading of YAML niche templates, pattern matching / search,
domain filtering, compliance filtering, and cross-niche analysis.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from src.core.niche_loader import (
    NicheLoader, NicheTemplate, NICHE_ROOT, YAML_AVAILABLE,
    get_niche_loader,
)


# ============================================================
#  Fixtures & Sample Data
# ============================================================

SAMPLE_NICHE_YAML = """
niche:
  name: clinic_management
  domain: healthcare
  subdomain: clinic
  description: Clinic management system with appointments and patient records
  scale: medium

composition:
  base_template: apps/base
  app_template: apps/fastapi_app
  blocks:
    - jwt_auth
    - crud_service
    - email_smtp
    - task_scheduler
  variables:
    project_name: clinic_app

entities:
  - name: Patient
    fields:
      - name: name
        type: str
      - name: email
        type: str
  - name: Appointment
    fields:
      - name: date
        type: datetime
      - name: status
        type: str

workflow:
  typical_paths:
    - "Patient → Create Appointment → Notify"
  triggers:
    - "appointment_created:Send confirmation email"

features:
  core:
    - Patient management
    - Appointment scheduling
  advanced:
    - Email notifications
  optional:
    - SMS reminders

risk_assessment:
  data_sensitivity: high
  compliance:
    - HIPAA
    - GDPR
  backup_frequency: hourly
  access_control: rbac
  audit_trail: true
"""

SAMPLE_NICHE_YAML_2 = """
niche:
  name: restaurant_pos
  domain: hospitality
  subdomain: restaurant
  description: Restaurant point of sale and inventory management
  scale: small

composition:
  base_template: apps/base
  blocks:
    - crud_service
    - inventory_tracker
    - stripe_payments

entities:
  - name: MenuItem
    fields:
      - name: name
        type: str
      - name: price
        type: float

workflow:
  typical_paths: []
  triggers: []

features:
  core:
    - Order management
  advanced: []
  optional: []

risk_assessment:
  data_sensitivity: low
  compliance: []
  backup_frequency: daily
  access_control: basic
  audit_trail: false
"""


@pytest.fixture
def niche_dir(tmp_path):
    """Create a niche directory structure with sample YAML files."""
    domains = tmp_path / "niches"
    healthcare = domains / "healthcare"
    healthcare.mkdir(parents=True)
    hospitality = domains / "hospitality"
    hospitality.mkdir(parents=True)

    if YAML_AVAILABLE:
        (healthcare / "clinic.yaml").write_text(SAMPLE_NICHE_YAML, encoding="utf-8")
        (hospitality / "restaurant.yaml").write_text(SAMPLE_NICHE_YAML_2, encoding="utf-8")

    return domains


@pytest.fixture
def niche_loader(niche_dir):
    """Create a NicheLoader pointing at the temp niche directory."""
    return NicheLoader(niche_root=str(niche_dir))


@pytest.fixture
def loaded_niche_loader(niche_loader):
    """Create and load a NicheLoader with sample data."""
    if not YAML_AVAILABLE:
        pytest.skip("PyYAML not available")
    niche_loader.load_all()
    return niche_loader


# ============================================================
#  NicheTemplate Dataclass Tests
# ============================================================

class TestNicheTemplate:
    """Tests for NicheTemplate dataclass and methods."""

    def test_keywords_extraction(self):
        """Should extract keywords from name, domain, and description."""
        niche = NicheTemplate(
            name="clinic_management", domain="healthcare",
            subdomain="clinic",
            description="Clinic management system",
            scale="medium",
        )
        kw = niche.keywords
        assert "clinic" in kw
        assert "management" in kw
        assert "healthcare" in kw

    def test_entity_count(self):
        """Should count entities correctly."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            entities=[{"name": "A"}, {"name": "B"}],
        )
        assert niche.entity_count == 2

    def test_total_fields(self):
        """Should count total fields across entities."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            entities=[
                {"fields": [{"name": "x"}, {"name": "y"}]},
                {"fields": [{"name": "z"}]},
            ],
        )
        assert niche.total_fields == 3

    def test_to_composition_plan(self):
        """Should convert to CompositionPlan with correct fields."""
        niche = NicheTemplate(
            name="test", domain="d", subdomain="s",
            description="desc", scale="small",
            blocks=["jwt_auth", "crud_service"],
            variables={"key": "val"},
        )
        plan = niche.to_composition_plan()
        assert plan.blocks == ["jwt_auth", "crud_service"]
        assert plan.variables == {"key": "val"}


# ============================================================
#  Loading Tests
# ============================================================

class TestNicheLoading:
    """Tests for NicheLoader loading behavior."""

    def test_load_all_returns_count(self, loaded_niche_loader):
        """load_all should return the number of niches loaded."""
        # Already loaded in fixture; verify it worked
        assert loaded_niche_loader._loaded is True

    def test_load_empty_directory(self, tmp_path):
        """Should handle empty niche root gracefully."""
        loader = NicheLoader(niche_root=str(tmp_path / "empty"))
        count = loader.load_all()
        assert count == 0

    def test_load_nonexistent_directory(self, tmp_path):
        """Should return 0 for nonexistent directory."""
        loader = NicheLoader(niche_root=str(tmp_path / "nonexistent"))
        count = loader.load_all()
        assert count == 0

    def test_invalid_yaml_skipped(self, niche_dir):
        """Should skip YAML files missing the 'niche' key."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        # Write invalid YAML
        (niche_dir / "healthcare" / "bad.yaml").write_text("invalid: true", encoding="utf-8")
        loader = NicheLoader(niche_root=str(niche_dir))
        count = loader.load_all()
        # Should still load valid niches
        assert count >= 2


# ============================================================
#  Query Tests
# ============================================================

class TestNicheQuery:
    """Tests for niche retrieval and search."""

    def test_get_by_name(self, loaded_niche_loader):
        """Should retrieve a niche by exact name."""
        niche = loaded_niche_loader.get("clinic_management")
        assert niche is not None
        assert niche.name == "clinic_management"

    def test_get_nonexistent(self, loaded_niche_loader):
        """Should return None for nonexistent niche name."""
        assert loaded_niche_loader.get("nonexistent") is None

    def test_get_plan(self, loaded_niche_loader):
        """Should return a CompositionPlan for a niche."""
        plan = loaded_niche_loader.get_plan("clinic_management")
        assert plan is not None
        assert "jwt_auth" in plan.blocks

    def test_get_plan_nonexistent(self, loaded_niche_loader):
        """Should return None for nonexistent niche plan."""
        assert loaded_niche_loader.get_plan("nonexistent") is None

    def test_list_domains(self, loaded_niche_loader):
        """Should list all available domains."""
        domains = loaded_niche_loader.list_domains()
        assert "healthcare" in domains
        assert "hospitality" in domains

    def test_list_niches_all(self, loaded_niche_loader):
        """Should list all niche names."""
        niches = loaded_niche_loader.list_niches()
        assert "clinic_management" in niches
        assert "restaurant_pos" in niches

    def test_list_niches_by_domain(self, loaded_niche_loader):
        """Should filter niches by domain."""
        niches = loaded_niche_loader.list_niches(domain="healthcare")
        assert "clinic_management" in niches
        assert "restaurant_pos" not in niches

    def test_get_by_domain(self, loaded_niche_loader):
        """Should return all niches for a domain."""
        niches = loaded_niche_loader.get_by_domain("healthcare")
        assert len(niches) >= 1
        assert all(n.domain == "healthcare" for n in niches)


# ============================================================
#  Search Tests
# ============================================================

class TestNicheSearch:
    """Tests for keyword-based niche search."""

    def test_search_by_name(self, loaded_niche_loader):
        """Should find niche by name match."""
        results = loaded_niche_loader.search("clinic_management")
        assert len(results) >= 1
        assert any(n.name == "clinic_management" for n in results)

    def test_search_by_domain(self, loaded_niche_loader):
        """Should find niches by domain match."""
        results = loaded_niche_loader.search("healthcare")
        assert len(results) >= 1

    def test_search_by_description_keywords(self, loaded_niche_loader):
        """Should find niches matching description keywords."""
        results = loaded_niche_loader.search("appointment scheduling")
        assert len(results) >= 1

    def test_search_no_results(self, loaded_niche_loader):
        """Should return empty for no matching query."""
        results = loaded_niche_loader.search("quantum_computing_space_station")
        assert results == []

    def test_search_respects_limit(self, loaded_niche_loader):
        """Should respect the limit parameter."""
        results = loaded_niche_loader.search("management", limit=1)
        assert len(results) <= 1

    def test_suggest_for_description(self, loaded_niche_loader):
        """Should suggest niches with relevance scores."""
        suggestions = loaded_niche_loader.suggest_for_description(
            "healthcare clinic with patient management"
        )
        assert len(suggestions) >= 1
        assert "relevance_score" in suggestions[0]
        assert "name" in suggestions[0]


# ============================================================
#  Compliance Filtering Tests
# ============================================================

class TestComplianceFiltering:
    """Tests for compliance and risk-based filtering."""

    def test_filter_by_compliance(self, loaded_niche_loader):
        """Should filter niches by compliance regulation."""
        hipaa = loaded_niche_loader.filter_by_compliance("HIPAA")
        assert len(hipaa) >= 1
        assert any(n.name == "clinic_management" for n in hipaa)

    def test_filter_by_compliance_no_match(self, loaded_niche_loader):
        """Should return empty when no niches match compliance."""
        results = loaded_niche_loader.filter_by_compliance("SOX")
        assert results == []

    def test_filter_by_sensitivity(self, loaded_niche_loader):
        """Should filter niches by data sensitivity level."""
        high = loaded_niche_loader.filter_by_sensitivity("high")
        assert len(high) >= 1
        assert all(n.data_sensitivity == "high" for n in high)

    def test_filter_by_scale(self, loaded_niche_loader):
        """Should filter niches by scale."""
        small = loaded_niche_loader.filter_by_scale("small")
        assert len(small) >= 1
        assert all(n.scale == "small" for n in small)


# ============================================================
#  Cross-Niche Analysis Tests
# ============================================================

class TestCrossNicheAnalysis:
    """Tests for cross-niche block and entity frequency analysis."""

    def test_get_common_blocks(self, loaded_niche_loader):
        """Should return block frequency across niches."""
        blocks = loaded_niche_loader.get_common_blocks()
        assert "crud_service" in blocks
        assert blocks["crud_service"] == 2  # Both niches use crud_service

    def test_get_common_entities(self, loaded_niche_loader):
        """Should return entity name frequency across niches."""
        entities = loaded_niche_loader.get_common_entities()
        # Each niche has unique entity names
        assert len(entities) > 0

    def test_get_domain_overview(self, loaded_niche_loader):
        """Should return overview with statistics per domain."""
        overview = loaded_niche_loader.get_domain_overview()
        assert "healthcare" in overview
        assert overview["healthcare"]["niche_count"] >= 1
        assert overview["healthcare"]["total_entities"] >= 1


# ============================================================
#  Stats Tests
# ============================================================

class TestNicheLoaderStats:
    """Tests for NicheLoader stats property."""

    def test_stats_structure(self, loaded_niche_loader):
        """Stats should contain expected keys."""
        stats = loaded_niche_loader.stats
        assert "total_niches" in stats
        assert "total_domains" in stats
        assert "yaml_available" in stats
        assert "loaded" in stats

    def test_stats_auto_loads(self, niche_loader):
        """Stats should trigger auto-load if not loaded."""
        if not YAML_AVAILABLE:
            pytest.skip("PyYAML not available")
        assert not niche_loader._loaded
        stats = niche_loader.stats
        assert niche_loader._loaded

    def test_stats_niche_count(self, loaded_niche_loader):
        """Should report correct number of loaded niches."""
        stats = loaded_niche_loader.stats
        assert stats["total_niches"] >= 2


# ============================================================
#  Singleton Tests
# ============================================================

class TestNicheSingleton:
    """Tests for get_niche_loader singleton."""

    def test_singleton_returns_same_instance(self):
        """get_niche_loader should return the same instance."""
        import src.core.niche_loader as mod
        mod._niche_loader_instance = None
        loader1 = get_niche_loader()
        loader2 = get_niche_loader()
        assert loader1 is loader2
        mod._niche_loader_instance = None

    def test_singleton_is_niche_loader_type(self):
        """Singleton should be a NicheLoader instance."""
        import src.core.niche_loader as mod
        mod._niche_loader_instance = None
        loader = get_niche_loader()
        assert isinstance(loader, NicheLoader)
        mod._niche_loader_instance = None

    def test_singleton_thread_safe(self):
        """Singleton should be thread-safe."""
        import src.core.niche_loader as mod
        import threading
        mod._niche_loader_instance = None
        results = []
        def get_loader():
            results.append(get_niche_loader())
        threads = [threading.Thread(target=get_loader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is results[0] for r in results)
        mod._niche_loader_instance = None
