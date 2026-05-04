"""
ZENIC LOGIC - NicheLoader (YAML-Driven Niche Template Registry)

Cargador de plantillas YAML de nichos que permite al TemplateEngine
descubrir, cargar y resolver CompositionPlans desde definiciones
declarativas por dominio/nicho.

Arquitectura:
  1. Escanea src/templates/niches/<domain>/<niche>.yaml
  2. Carga cada YAML en un NicheTemplate dataclass
  3. Resuelve nichos por nombre, dominio, o keywords
  4. Convierte NicheTemplate → CompositionPlan para el TemplateEngine
  5. Sugiere nichos relevantes basado en descripcion del usuario

Ventajas:
  - Declarativo: agregar nichos sin tocar Python
  - Escalable: 100+ nichos sin impacto en rendimiento (lazy loading)
  - Descubrible: busqueda por dominio, nombre, keywords, compliance
  - Extensible: schema YAML evoluciona sin romper compatibilidad
"""

import os
import logging
import threading
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from .template_engine import CompositionPlan, TemplateBlock

logger = logging.getLogger(__name__)

# === Niche Root ===
NICHE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "niches")


@dataclass
class NicheTemplate:
    """Definicion declarativa de un nicho de negocio."""
    name: str
    domain: str
    subdomain: str
    description: str
    scale: str  # small, medium, large, enterprise

    # Composition
    base_template: str = "apps/base"
    app_template: str = ""
    blocks: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Entities
    entities: List[Dict[str, Any]] = field(default_factory=list)

    # Workflow
    typical_paths: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)

    # Features
    core_features: List[str] = field(default_factory=list)
    advanced_features: List[str] = field(default_factory=list)
    optional_features: List[str] = field(default_factory=list)

    # Risk
    data_sensitivity: str = "medium"
    compliance: List[str] = field(default_factory=list)
    backup_frequency: str = "daily"
    access_control: str = "basic"
    audit_trail: bool = False

    # Metadata
    yaml_path: str = ""
    loaded_at: str = ""

    def to_composition_plan(self) -> CompositionPlan:
        """Convierte este NicheTemplate en un CompositionPlan usable por TemplateEngine."""
        return CompositionPlan(
            base_template=self.base_template,
            app_template=self.app_template,
            blocks=list(self.blocks),
            variables=dict(self.variables),
            entities=list(self.entities),
        )

    @property
    def keywords(self) -> Set[str]:
        """Extrae keywords del nombre, dominio y descripcion para busqueda."""
        words = set()
        for source in [self.name, self.domain, self.subdomain, self.description]:
            for word in source.lower().replace("_", " ").replace("-", " ").split():
                if len(word) > 2:
                    words.add(word)
        # Agregar features como keywords
        for feat in self.core_features + self.advanced_features:
            for word in feat.lower().split():
                if len(word) > 3:
                    words.add(word)
        return words

    @property
    def entity_count(self) -> int:
        """Numero de entidades en este nicho."""
        return len(self.entities)

    @property
    def total_fields(self) -> int:
        """Total de campos en todas las entidades."""
        return sum(len(e.get("fields", [])) for e in self.entities)


class NicheLoader:
    """
    Cargador de plantillas YAML de nichos.

    Escanea el directorio de nichos, carga definiciones YAML,
    y provee busqueda/resolucion por nombre, dominio o keywords.
    """

    def __init__(self, niche_root: str = ""):
        self._root = niche_root or NICHE_ROOT
        self._niches: Dict[str, NicheTemplate] = {}
        self._domain_index: Dict[str, List[str]] = {}
        self._loaded = False

    # ================================================================
    #  LOADING
    # ================================================================

    def load_all(self) -> int:
        """
        Carga todas las plantillas YAML de nichos.

        Returns:
            Numero de nichos cargados
        """
        if not YAML_AVAILABLE:
            logger.warning("NicheLoader: PyYAML not available, cannot load niche templates")
            return 0

        if not os.path.isdir(self._root):
            logger.warning(f"NicheLoader: Niche root not found: {self._root}")
            return 0

        count = 0
        for root, dirs, files in os.walk(self._root):
            for f in files:
                if f.endswith(".yaml") or f.endswith(".yml"):
                    path = os.path.join(root, f)
                    try:
                        niche = self._load_yaml(path)
                        if niche:
                            self._niches[niche.name] = niche
                            # Index by domain
                            self._domain_index.setdefault(niche.domain, []).append(niche.name)
                            count += 1
                    except Exception as e:
                        logger.error(f"NicheLoader: Error loading {path}: {e}")

        self._loaded = True
        logger.info(f"NicheLoader: Loaded {count} niche templates from {self._root}")
        return count

    def _load_yaml(self, path: str) -> Optional[NicheTemplate]:
        """Carga un archivo YAML de nicho."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "niche" not in data:
            logger.warning(f"NicheLoader: Invalid niche YAML (missing 'niche' key): {path}")
            return None

        niche_data = data["niche"]
        comp_data = data.get("composition", {})
        entities_data = data.get("entities", [])
        workflow_data = data.get("workflow", {})
        features_data = data.get("features", {})
        risk_data = data.get("risk_assessment", {})

        # Parse triggers from "trigger:description" format
        triggers = []
        for t in workflow_data.get("triggers", []):
            triggers.append(str(t))

        return NicheTemplate(
            name=niche_data.get("name", ""),
            domain=niche_data.get("domain", ""),
            subdomain=niche_data.get("subdomain", ""),
            description=niche_data.get("description", ""),
            scale=niche_data.get("scale", "medium"),

            base_template=comp_data.get("base_template", "apps/base"),
            app_template=comp_data.get("app_template", ""),
            blocks=comp_data.get("blocks", []),
            variables=comp_data.get("variables", {}),

            entities=entities_data,

            typical_paths=workflow_data.get("typical_paths", []),
            triggers=triggers,

            core_features=features_data.get("core", []),
            advanced_features=features_data.get("advanced", []),
            optional_features=features_data.get("optional", []),

            data_sensitivity=risk_data.get("data_sensitivity", "medium"),
            compliance=risk_data.get("compliance", []),
            backup_frequency=risk_data.get("backup_frequency", "daily"),
            access_control=risk_data.get("access_control", "basic"),
            audit_trail=risk_data.get("audit_trail", False),

            yaml_path=path,
        )

    # ================================================================
    #  QUERY
    # ================================================================

    def get(self, name: str) -> Optional[NicheTemplate]:
        """Obtiene un nicho por nombre exacto."""
        if not self._loaded:
            self.load_all()
        return self._niches.get(name)

    def get_plan(self, name: str) -> Optional[CompositionPlan]:
        """Obtiene un CompositionPlan para un nicho por nombre."""
        niche = self.get(name)
        if niche:
            return niche.to_composition_plan()
        return None

    def list_domains(self) -> List[str]:
        """Lista todos los dominios disponibles."""
        if not self._loaded:
            self.load_all()
        return sorted(self._domain_index.keys())

    def list_niches(self, domain: str = "") -> List[str]:
        """Lista nichos, opcionalmente filtrados por dominio."""
        if not self._loaded:
            self.load_all()
        if domain:
            return sorted(self._domain_index.get(domain, []))
        return sorted(self._niches.keys())

    def get_by_domain(self, domain: str) -> List[NicheTemplate]:
        """Obtiene todos los nichos de un dominio."""
        if not self._loaded:
            self.load_all()
        names = self._domain_index.get(domain, [])
        return [self._niches[n] for n in names if n in self._niches]

    def search(self, query: str, limit: int = 10) -> List[NicheTemplate]:
        """
        Busca nichos relevantes basado en una consulta.

        Usa keyword matching contra nombre, dominio, descripcion y features.
        Retorna nichos ordenados por relevancia.
        """
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        query_words = set(query_lower.replace("_", " ").replace("-", " ").split())

        scored = []
        for niche in self._niches.values():
            score = 0

            # Exact name match (highest priority)
            if query_lower == niche.name.lower():
                score += 100
            elif query_lower in niche.name.lower():
                score += 50

            # Domain match
            if query_lower == niche.domain.lower():
                score += 40
            elif query_lower in niche.domain.lower():
                score += 20

            # Subdomain match
            if query_lower in niche.subdomain.lower():
                score += 15

            # Keyword overlap
            niche_kw = niche.keywords
            overlap = query_words & niche_kw
            score += len(overlap) * 10

            # Description match
            desc_words = set(niche.description.lower().split())
            desc_overlap = query_words & desc_words
            score += len(desc_overlap) * 5

            # Compliance match
            for comp in niche.compliance:
                if comp.lower() in query_lower:
                    score += 15

            # Scale match
            if any(w in query_lower for w in ["enterprise", "erp", "large"]):
                if niche.scale in ("enterprise", "large"):
                    score += 10

            if score > 0:
                scored.append((score, niche))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in scored[:limit]]

    def suggest_for_description(self, description: str) -> List[Dict[str, Any]]:
        """
        Sugiere nichos relevantes basado en una descripcion de proyecto.

        Returns:
            Lista de dicts con name, domain, description, relevance_score
        """
        results = self.search(description, limit=20)
        suggestions = []
        for niche in results:
            # Calculate relevance based on keyword overlap
            query_words = set(description.lower().replace("_", " ").split())
            niche_kw = niche.keywords
            overlap = query_words & niche_kw
            relevance = min(100, len(overlap) * 15)

            suggestions.append({
                "name": niche.name,
                "domain": niche.domain,
                "description": niche.description,
                "scale": niche.scale,
                "relevance_score": relevance,
                "entity_count": niche.entity_count,
                "blocks": niche.blocks,
                "compliance": niche.compliance,
            })
        return suggestions

    # ================================================================
    #  STATISTICS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del cargador de nichos."""
        if not self._loaded:
            self.load_all()

        total_entities = sum(n.entity_count for n in self._niches.values())
        total_fields = sum(n.total_fields for n in self._niches.values())

        sensitivity_dist = {}
        for n in self._niches.values():
            sensitivity_dist[n.data_sensitivity] = sensitivity_dist.get(n.data_sensitivity, 0) + 1

        scale_dist = {}
        for n in self._niches.values():
            scale_dist[n.scale] = scale_dist.get(n.scale, 0) + 1

        return {
            "total_niches": len(self._niches),
            "total_domains": len(self._domain_index),
            "total_entities": total_entities,
            "total_fields": total_fields,
            "sensitivity_distribution": sensitivity_dist,
            "scale_distribution": scale_dist,
            "yaml_available": YAML_AVAILABLE,
            "loaded": self._loaded,
        }

    # ================================================================
    #  COMPLIANCE FILTERING
    # ================================================================

    def filter_by_compliance(self, regulation: str) -> List[NicheTemplate]:
        """Filtra nichos que requieren una regulacion especifica."""
        if not self._loaded:
            self.load_all()
        reg_lower = regulation.lower()
        return [
            n for n in self._niches.values()
            if any(reg_lower in c.lower() for c in n.compliance)
        ]

    def filter_by_sensitivity(self, level: str) -> List[NicheTemplate]:
        """Filtra nichos por nivel de sensibilidad de datos."""
        if not self._loaded:
            self.load_all()
        return [n for n in self._niches.values() if n.data_sensitivity == level]

    def filter_by_scale(self, scale: str) -> List[NicheTemplate]:
        """Filtra nichos por escala."""
        if not self._loaded:
            self.load_all()
        return [n for n in self._niches.values() if n.scale == scale]

    # ================================================================
    #  CROSS-NICHE ANALYSIS
    # ================================================================

    def get_common_blocks(self) -> Dict[str, int]:
        """Retorna bloques usados y su frecuencia entre todos los nichos."""
        if not self._loaded:
            self.load_all()
        block_freq = {}
        for niche in self._niches.values():
            for block in niche.blocks:
                block_freq[block] = block_freq.get(block, 0) + 1
        return dict(sorted(block_freq.items(), key=lambda x: x[1], reverse=True))

    def get_common_entities(self) -> Dict[str, int]:
        """Retorna nombres de entidades y su frecuencia entre nichos."""
        if not self._loaded:
            self.load_all()
        entity_freq = {}
        for niche in self._niches.values():
            for entity in niche.entities:
                name = entity.get("name", "")
                if name:
                    entity_freq[name] = entity_freq.get(name, 0) + 1
        return dict(sorted(entity_freq.items(), key=lambda x: x[1], reverse=True))

    def get_domain_overview(self) -> Dict[str, Dict[str, Any]]:
        """Retorna overview de cada dominio con estadisticas."""
        if not self._loaded:
            self.load_all()
        overview = {}
        for domain, names in self._domain_index.items():
            niches = [self._niches[n] for n in names if n in self._niches]
            overview[domain] = {
                "niche_count": len(niches),
                "total_entities": sum(n.entity_count for n in niches),
                "total_fields": sum(n.total_fields for n in niches),
                "scales": list(set(n.scale for n in niches)),
                "compliance": list(set(c for n in niches for c in n.compliance)),
                "niche_names": sorted(names),
            }
        return overview


# === Singleton ===
_niche_loader_instance: Optional[NicheLoader] = None
_niche_loader_lock = threading.Lock()


def get_niche_loader() -> NicheLoader:
    """Obtiene la instancia singleton del NicheLoader."""
    global _niche_loader_instance
    if _niche_loader_instance is None:
        with _niche_loader_lock:
            if _niche_loader_instance is None:
                _niche_loader_instance = NicheLoader()
    return _niche_loader_instance
