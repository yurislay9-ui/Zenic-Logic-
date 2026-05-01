"""
TITAN OMNISCALE X - Macro Router v13 (MoE Clasificador con Firmas Topologicas)

Router de criticidad con clasificacion MoE (Mixture of Experts).
Implementa el Principio de Aislamiento Quirurgico (PAQ).

MEJORAS v13:
- Lee el Grafo AST del Nivel 3 para firmas topologicas reales
- Lee patrones criticos desde configuracion YAML
- Consulta complejidad y conexiones de nodos desde SQLite
- Clasifica por criticidad basada en estructura + semantica

Sin dependencias externas. Compatible con Android.
"""

import json
import sqlite3
import logging
from src.core.shared.contracts import (
    IntentPayload, RoutingPayload, CriticalityLevel, RoutePath, OperationType
)
from src.config.loader import load_settings, get_critical_nodes, get_critical_patterns
from src.core.shared.db_initializer import get_db_path

logger = logging.getLogger(__name__)


class MacroRouter:
    """
    Router de criticidad con clasificacion MoE.

    Implementa el Nivel 2 del documento de arquitectura:
    - Criticidad 3 (Quirurgica): auth, crypto, payments, db -> SURGICAL_PATH
    - Criticidad 2 (Moderada): API, controllers, services -> DEEP_PATH
    - Criticidad 1 (Rapida): UI, config, explain -> FAST_PATH
    - Regla del 80/20: 80% del codigo recibe tratamiento estandar

    Ahora lee el Grafo AST (Nivel 3) para clasificar basado en:
    - Firmas topologicas del nodo en el grafo
    - Complejidad del nodo
    - Conexiones a nodos criticos
    - Patrones criticos desde YAML
    """

    MODERATE_PATTERNS = [
        "api", "endpoint", "route", "controller", "service",
        "model", "repository", "factory", "builder",
        "config", "settings", "environment", "deploy",
    ]

    def __init__(self):
        self.settings = load_settings()
        self.critical_patterns = get_critical_patterns(self.settings)
        self.critical_keywords = get_critical_nodes(self.settings)

    def route(self, intent):
        """Enruta basado en criticidad semantica + firmas topologicas del grafo AST."""
        target_lower = intent.target.lower()
        context_lower = (intent.context or "").lower()

        # Paso 1: Verificar firmas topologicas en el Grafo AST (Nivel 3)
        ast_critical = self._check_ast_criticality(intent.target)

        # Paso 2: Verificar criticidad semantica (keywords en target y contexto)
        is_critical_keyword = self._check_critical_keywords(target_lower, context_lower)

        # Paso 3: Verificar patrones criticos globales desde YAML
        is_critical_pattern = self._check_critical_patterns(target_lower)

        # Combinar senales de criticidad
        is_critical = ast_critical or is_critical_keyword or is_critical_pattern

        is_moderate = any(p in target_lower for p in self.MODERATE_PATTERNS)

        # Nivel 3: Quirurgico
        if is_critical:
            if intent.op in [OperationType.DELETE, OperationType.REFACTOR]:
                return RoutingPayload(
                    intent=intent,
                    criticality=CriticalityLevel.SURGICAL_CRITICAL,
                    route=RoutePath.SURGICAL_PATH,
                    reason="Operacion de riesgo en nodo critico. Pipeline completo + Z3 activado."
                )
            return RoutingPayload(
                intent=intent,
                criticality=CriticalityLevel.SURGICAL_CRITICAL,
                route=RoutePath.SURGICAL_PATH,
                reason="Nodo critico detectado. Pipeline completo + Constraint Solver activado."
            )

        # Operaciones de modificacion en nodos no-criticos
        if intent.op in [OperationType.DELETE, OperationType.REFACTOR, OperationType.OPTIMIZE]:
            return RoutingPayload(
                intent=intent,
                criticality=CriticalityLevel.DEEP_MODERATE,
                route=RoutePath.DEEP_PATH,
                reason="Operacion de modificacion requiere planificacion y validacion."
            )

        if intent.op == OperationType.CREATE:
            return RoutingPayload(
                intent=intent,
                criticality=CriticalityLevel.DEEP_MODERATE,
                route=RoutePath.DEEP_PATH,
                reason="Creacion de codigo requiere busqueda de patrones y validacion."
            )

        if is_moderate or intent.op in [OperationType.ANALYZE, OperationType.DEBUG]:
            return RoutingPayload(
                intent=intent,
                criticality=CriticalityLevel.DEEP_MODERATE,
                route=RoutePath.DEEP_PATH,
                reason="Analisis de componente moderado."
            )

        # Nivel 1: Rapido
        return RoutingPayload(
            intent=intent,
            criticality=CriticalityLevel.FAST_STANDARD,
            route=RoutePath.FAST_PATH,
            reason="Operacion estandar. Respuesta directa."
        )

    def _check_critical_keywords(self, target_lower, context_lower):
        """Verifica si el target o contexto contienen keywords criticos desde YAML."""
        for keyword in self.critical_keywords:
            if keyword in target_lower or keyword in context_lower:
                return True
        return False

    def _check_critical_patterns(self, target_lower):
        """Verifica si el target coincide con patrones criticos globales desde YAML."""
        import fnmatch
        for pattern in self.critical_patterns:
            if fnmatch.fnmatch(target_lower, pattern):
                return True
        return False

    def _check_ast_criticality(self, target_name):
        """
        Consulta el Grafo AST (Nivel 3) para verificar si el nodo target
        es critico basado en su topologia en el grafo.

        Firma topologica: un nodo es critico si:
        1. Su nombre contiene keywords criticos, o
        2. Esta conectado a nodos criticos (distancia <= 2 en el grafo)
        3. Tiene alta centralidad (muchas conexiones entrantes)
        """
        try:
            with sqlite3.connect(get_db_path("graph_ast.sqlite")) as conn:
                conn.row_factory = sqlite3.Row

                # Buscar el nodo por nombre
                rows = conn.execute(
                    "SELECT name, node_type, connections, complexity FROM ast_nodes WHERE name LIKE ?",
                    (f"%{target_name}%",)
                ).fetchall()

                if not rows:
                    return False

                for row in rows:
                    name = row["name"].lower()
                    node_type = row["node_type"]
                    connections_raw = row["connections"]
                    complexity = row["complexity"]

                    # Criterio 1: Nombre del nodo contiene keyword critico
                    for keyword in self.critical_keywords:
                        if keyword in name:
                            logger.debug("AST critical match (keyword): %s contains %s", name, keyword)
                            return True

                    # Criterio 2: Conectado a nodos criticos
                    try:
                        connections = json.loads(connections_raw) if connections_raw else []
                        for conn_item in connections:
                            conn_str = str(conn_item).lower()
                            for keyword in self.critical_keywords:
                                if keyword in conn_str:
                                    logger.debug("AST critical match (connection): %s -> %s", name, conn_str)
                                    return True
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # Criterio 3: Alta centralidad (nodo con muchas conexiones = critico)
                    if node_type == "function" and complexity > 15:
                        logger.debug("AST critical match (high complexity): %s complexity=%d", name, complexity)
                        return True

        except Exception as e:
            logger.debug("AST criticality check error: %s", e)

        return False
