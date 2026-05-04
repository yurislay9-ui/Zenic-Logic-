"""
ZENIC LOGIC - NicheAutoScraper (Inversión de Control de Conocimiento)

Motor de auto-aprendizaje que conecta el GitHubScrapAgent (Nivel 5)
con el NicheLoader para auto-actualizar los YAML de nichos basándose
en repositorios trending de GitHub.

Arquitectura:
  1. Cron Scheduler: ejecuta scraping periódicamente
  2. Trending Analyzer: detecta patrones emergentes en repos populares
  3. Dependency Extractor: analiza package.json/go.mod/requirements.txt via AST
  4. Niche Updater: fusiona nuevos patrones en los YAML existentes
  5. Evolution Tracker: registra mutaciones para auditoría

Flujo:
  GitHub Trending → ScrapAgent → AST Engine → Pattern Extractor
      → NicheLoader.update_niche() → YAML actualizado → Auditoría

El sistema MUTA y APRENDE solo. Sin intervención manual.
"""

import os
import json
import time
import logging
import threading
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

# === Evolution DB ===
EVOLUTION_DB = os.path.join(
    os.path.expanduser("~"), ".titan_omniscale", "db", "niche_evolution.sqlite"
)


@dataclass
class EvolutionEntry:
    """Registro de una mutación en un nicho."""
    niche_name: str
    mutation_type: str  # "entity_added", "field_added", "block_added", "pattern_updated"
    description: str
    source_repo: str
    timestamp: float = 0.0
    old_value: str = ""
    new_value: str = ""
    approved: bool = True  # Auto-approved by default

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class TrendingAnalyzer:
    """
    Analiza repositorios trending de GitHub para detectar
    patrones emergentes que deban incorporarse a los nichos.
    """

    # Patrones de dependencias por lenguaje
    DEP_PATTERNS = {
        "python": {
            "file": "requirements.txt",
            "parse": "requirements",
        },
        "javascript": {
            "file": "package.json",
            "parse": "package_json",
        },
        "go": {
            "file": "go.mod",
            "parse": "gomod",
        },
        "rust": {
            "file": "Cargo.toml",
            "parse": "cargotoml",
        },
    }

    # Mapeo de librerías populares a entidades/blocks de nichos
    LIBRARY_TO_BLOCK = {
        # Auth
        "fastapi-users": "jwt_auth",
        "authlib": "jwt_auth",
        "python-jose": "jwt_auth",
        "passport": "jwt_auth",
        "next-auth": "jwt_auth",
        # Payments
        "stripe": "stripe_payments",
        "razorpay": "stripe_payments",
        # Email
        "sendgrid": "email_smtp",
        "nodemailer": "email_smtp",
        "celery": "task_scheduler",
        # Data
        "pandas": "data_analyzer",
        "numpy": "data_analyzer",
        "polars": "data_analyzer",
        # PDF
        "weasyprint": "pdf_generator",
        "reportlab": "pdf_generator",
        "pdfkit": "pdf_generator",
        # Notifications
        "firebase-admin": "notification_manager",
        "onesignal": "notification_manager",
        # Webhooks
        "svix": "webhook_server",
        # Sheets
        "gspread": "google_sheets",
        # Inventory
        "stockpy": "inventory_tracker",
        # CRM
        "hubspot-api-client": "crm_pipeline",
    }

    # Mapeo de librerías a entidades que debería tener el nicho
    LIBRARY_TO_ENTITIES = {
        "stripe": [{"name": "Payment", "fields": ["amount:float", "currency:str", "status:str", "customer_id:str", "created_at:datetime"]}],
        "sendgrid": [{"name": "EmailLog", "fields": ["recipient:str", "subject:str", "status:str", "sent_at:datetime"]}],
        "firebase-admin": [{"name": "PushNotification", "fields": ["token:str", "title:str", "body:str", "sent_at:datetime"]}],
        "pandas": [{"name": "Dataset", "fields": ["name:str", "source:str", "rows:int", "columns:int", "created_at:datetime"]}],
    }

    def __init__(self, scrap_agent=None):
        self._scrap_agent = scrap_agent
        self._evolution_log: List[EvolutionEntry] = []

    async def analyze_trending(self, language: str = "python", since: str = "weekly") -> List[Dict[str, Any]]:
        """
        Analiza repositorios trending de GitHub para detectar patrones emergentes.

        Args:
            language: Lenguaje de programación a filtrar
            since: Período de tiempo (daily, weekly, monthly)

        Returns:
            Lista de dicts con info de repos y patrones detectados
        """
        if not self._scrap_agent:
            logger.warning("TrendingAnalyzer: No scrap agent available")
            return []

        results = []

        try:
            # Buscar repos trending vía GitHub search
            query = f"stars:>100 language:{language} topic:saas OR topic:startup OR topic:web-app"
            code = await self._scrap_agent.fetch_github_code(query, language)

            if not code:
                # Fallback: buscar por tópicos de nicho
                for niche_topic in ["healthcare", "fintech", "ecommerce", "education", "saas"]:
                    q = f"topic:{niche_topic} language:{language} stars:>50"
                    c = await self._scrap_agent.fetch_github_code(q, language)
                    if c:
                        results.append({
                            "topic": niche_topic,
                            "language": language,
                            "patterns_detected": self._extract_patterns(c, language),
                        })

            if code:
                results.append({
                    "topic": "trending",
                    "language": language,
                    "patterns_detected": self._extract_patterns(code, language),
                })

        except Exception as e:
            logger.error(f"TrendingAnalyzer: Error analyzing trending: {e}")

        return results

    def _extract_patterns(self, code: str, language: str) -> Dict[str, Any]:
        """
        Extrae patrones de dependencias y estructura de código.
        """
        patterns = {
            "libraries": [],
            "suggested_blocks": [],
            "suggested_entities": [],
        }

        # Detectar imports/requires
        import re
        if language == "python":
            imports = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE)
        elif language in ("javascript", "typescript"):
            imports = re.findall(r'(?:import|require)\s*\(?[\'"]([^\'"/]+)', code)
        else:
            imports = []

        for lib in set(imports):
            lib_lower = lib.lower().replace("-", "_").replace(".", "_")
            # Check if this library maps to a block
            if lib_lower in self.LIBRARY_TO_BLOCK:
                block = self.LIBRARY_TO_BLOCK[lib_lower]
                if block not in patterns["suggested_blocks"]:
                    patterns["suggested_blocks"].append(block)
                    patterns["libraries"].append(lib)

            # Check if this library suggests entities
            if lib_lower in self.LIBRARY_TO_ENTITIES:
                for entity in self.LIBRARY_TO_ENTITIES[lib_lower]:
                    if entity not in patterns["suggested_entities"]:
                        patterns["suggested_entities"].append(entity)

        return patterns

    def get_evolution_log(self, niche_name: str = "") -> List[EvolutionEntry]:
        """Obtiene el log de evolución, filtrado por nicho opcionalmente."""
        if niche_name:
            return [e for e in self._evolution_log if e.niche_name == niche_name]
        return list(self._evolution_log)


class NicheAutoUpdater:
    """
    Actualizador automático de nichos YAML.

    Conecta el TrendingAnalyzer con el NicheLoader para:
    1. Detectar patrones emergentes de GitHub
    2. Comparar con los nichos existentes
    3. Fusionar nuevos bloques/entidades si son relevantes
    4. Guardar los YAML actualizados
    """

    def __init__(self, niche_loader=None, scrap_agent=None):
        self._loader = niche_loader
        self._analyzer = TrendingAnalyzer(scrap_agent)
        self._niche_root = ""
        self._mutations_count = 0
        self._last_scan = 0.0
        self._copied_niches = set()
        self._copied_entities = set()

        if niche_loader:
            self._niche_root = niche_loader._root

    async def auto_update(self, language: str = "python") -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de auto-actualización.

        1. Analiza trending repos
        2. Para cada patrón detectado, busca nichos relevantes
        3. Fusiona nuevos bloques/entidades
        4. Guarda cambios en YAML

        Returns:
            Dict con estadísticas de la actualización
        """
        if not self._loader or not YAML_AVAILABLE:
            return {"error": "NicheLoader or PyYAML not available"}

        self._last_scan = time.time()
        mutations = []

        # Step 1: Analyze trending
        trending_results = await self._analyzer.analyze_trending(language)

        # Step 2: For each trending result, find matching niches
        for result in trending_results:
            patterns = result.get("patterns_detected", {})
            suggested_blocks = patterns.get("suggested_blocks", [])
            suggested_entities = patterns.get("suggested_entities", [])

            if not suggested_blocks and not suggested_entities:
                continue

            # Search for niches that match the topic
            topic = result.get("topic", "")
            matching_niches = self._loader.search(topic, limit=5)

            for niche in matching_niches:
                # Step 3: Merge new blocks
                # Use a copy of the blocks list to avoid mutating shared objects
                if id(niche) not in self._copied_niches:
                    niche.blocks = niche.blocks.copy()
                    self._copied_niches.add(id(niche))
                for block in suggested_blocks:
                    if block not in niche.blocks:
                        niche.blocks.append(block)
                        entry = EvolutionEntry(
                            niche_name=niche.name,
                            mutation_type="block_added",
                            description=f"Bloque '{block}' añadido por detección de librería trending",
                            source_repo=f"github:trending:{topic}",
                            old_value="",
                            new_value=block,
                        )
                        self._analyzer._evolution_log.append(entry)
                        mutations.append(entry)

                # Step 4: Merge new entities
                # Use a copy of the entities list to avoid mutating shared objects
                if id(niche) not in self._copied_entities:
                    niche.entities = niche.entities.copy()
                    self._copied_entities.add(id(niche))
                for entity in suggested_entities:
                    entity_name = entity.get("name", "")
                    existing_names = [e.get("name", "") for e in niche.entities]
                    if entity_name not in existing_names:
                        niche.entities.append(entity)
                        entry = EvolutionEntry(
                            niche_name=niche.name,
                            mutation_type="entity_added",
                            description=f"Entidad '{entity_name}' añadida por patrón trending",
                            source_repo=f"github:trending:{topic}",
                            old_value="",
                            new_value=entity_name,
                        )
                        self._analyzer._evolution_log.append(entry)
                        mutations.append(entry)

                # Step 5: Save updated YAML
                if mutations:
                    self._save_niche_yaml(niche)

        self._mutations_count += len(mutations)

        return {
            "mutations_applied": len(mutations),
            "total_mutations": self._mutations_count,
            "trending_analyzed": len(trending_results),
            "last_scan": self._last_scan,
            "mutations_detail": [
                {
                    "niche": m.niche_name,
                    "type": m.mutation_type,
                    "new_value": m.new_value,
                    "source": m.source_repo,
                }
                for m in mutations[:20]  # Limit detail to 20
            ],
        }

    def _save_niche_yaml(self, niche) -> bool:
        """Guarda un nicho actualizado de vuelta a su archivo YAML."""
        if not YAML_AVAILABLE or not niche.yaml_path:
            return False

        try:
            data = {
                "niche": {
                    "name": niche.name,
                    "domain": niche.domain,
                    "subdomain": niche.subdomain,
                    "description": niche.description,
                    "scale": niche.scale,
                },
                "composition": {
                    "base_template": niche.base_template,
                    "app_template": niche.app_template,
                    "blocks": niche.blocks,
                    "variables": niche.variables,
                },
                "entities": niche.entities,
                "workflow": {
                    "typical_paths": niche.typical_paths,
                    "triggers": niche.triggers,
                },
                "features": {
                    "core": niche.core_features,
                    "advanced": niche.advanced_features,
                    "optional": niche.optional_features,
                },
                "risk_assessment": {
                    "data_sensitivity": niche.data_sensitivity,
                    "compliance": niche.compliance,
                    "backup_frequency": niche.backup_frequency,
                    "access_control": niche.access_control,
                    "audit_trail": niche.audit_trail,
                },
            }

            with open(niche.yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

            logger.info(f"NicheAutoUpdater: Saved updated niche '{niche.name}'")
            return True

        except Exception as e:
            logger.error(f"NicheAutoUpdater: Error saving niche '{niche.name}': {e}")
            return False

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del auto-updater."""
        return {
            "total_mutations": self._mutations_count,
            "last_scan": self._last_scan,
            "evolution_entries": len(self._analyzer._evolution_log),
            "yaml_available": YAML_AVAILABLE,
        }


class NicheCronScheduler:
    """
    Scheduler de fondo que ejecuta auto-actualizaciones periódicamente.

    Ejecuta el NicheAutoUpdater en intervalos configurables:
    - Intervalo por defecto: 24 horas
    - Mínimo: 1 hora (para no abusar de la API de GitHub)
    - Thread daemon: no bloquea el shutdown del servidor
    """

    DEFAULT_INTERVAL_HOURS = 24
    MIN_INTERVAL_HOURS = 1

    def __init__(self, auto_updater: NicheAutoUpdater, interval_hours: float = 0):
        self._updater = auto_updater
        self._interval = max(interval_hours or self.DEFAULT_INTERVAL_HOURS, self.MIN_INTERVAL_HOURS)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_run = 0.0
        self._run_count = 0
        self._last_result: Dict[str, Any] = {}

    def start(self):
        """Inicia el scheduler en background."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"NicheCronScheduler: Started with interval={self._interval}h")

    def stop(self):
        """Detiene el scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("NicheCronScheduler: Stopped")

    def _run_loop(self):
        """Loop principal del scheduler."""
        # Wait initial delay (1 hour after start)
        initial_delay = min(self._interval * 3600, 3600)
        if self._stop_event.wait(timeout=initial_delay):
            return

        while not self._stop_event.is_set():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    self._last_result = loop.run_until_complete(
                        self._updater.auto_update()
                    )
                finally:
                    loop.close()

                self._last_run = time.time()
                self._run_count += 1

                logger.info(
                    f"NicheCronScheduler: Run #{self._run_count} complete, "
                    f"mutations={self._last_result.get('mutations_applied', 0)}"
                )

            except Exception as e:
                logger.error(f"NicheCronScheduler: Error in auto-update: {e}")

            # Wait for next interval
            self._stop_event.wait(timeout=self._interval * 3600)

    def trigger_now(self) -> Dict[str, Any]:
        """Fuerza una ejecución inmediata (síncrona, para API calls)."""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self._updater.auto_update())
            finally:
                loop.close()

            self._last_run = time.time()
            self._run_count += 1
            self._last_result = result
            return result

        except Exception as e:
            return {"error": str(e)}

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del scheduler."""
        return {
            "interval_hours": self._interval,
            "run_count": self._run_count,
            "last_run": self._last_run,
            "last_mutations": self._last_result.get("mutations_applied", 0),
            "is_running": self._thread is not None and self._thread.is_alive(),
        }
