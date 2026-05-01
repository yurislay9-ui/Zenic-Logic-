"""
TITAN OMNISCALE X - Config Loader v13 (Full YAML)

Cargador de configuracion que lee TODOS los archivos YAML:
- settings.yaml: configuracion general del motor
- timeouts.yaml: presupuestos computacionales (Z3, MCTS, K-Paths)
- critical_nodes.yaml: patrones de nodos criticos para el router

Compatible con Android (import condicional de pyyaml).
"""

import json
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def _load_yaml(filename):
    """Carga un archivo YAML, con fallback a valores por defecto."""
    config_path = Path(__file__).resolve().parent / filename
    if config_path.exists() and HAS_YAML:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def load_settings():
    """
    Carga la configuracion completa desde todos los archivos YAML.
    Combina settings.yaml, timeouts.yaml y critical_nodes.yaml
    en un unico diccionario estructurado.
    """
    settings = _load_yaml("settings.yaml")
    timeouts = _load_yaml("timeouts.yaml")
    critical = _load_yaml("critical_nodes.yaml")

    # Valores por defecto si los YAML estan ausentes o pyyaml no esta instalado
    defaults = {
        "project_dir": ".",
        "engine_limits": {
            "solver_timeout_ms": 15000,       # 15s quirurgico como dice el doc
            "solver_fast_timeout_ms": 5000,    # 5s moderado
            "sandbox_timeout_s": 5,
            "mcts_max_depth": 5,
            "mcts_max_simulations": 100,
            "max_k_paths": 10,
        },
        "critical_nodes": [
            "auth", "login", "signin", "signup", "password", "token",
            "crypto", "cipher", "encrypt", "decrypt", "hash", "salt",
            "payment", "stripe", "paypal", "transaction", "billing",
            "db", "database", "sql", "migration", "schema",
            "session", "cookie", "jwt", "oauth", "saml",
        ],
        "critical_patterns": [
            "auth/*",
            "*_crypto.*",
            "transactions/*",
        ],
    }

    # Mergear settings.yaml
    if settings:
        if "project_dir" in settings:
            defaults["project_dir"] = settings["project_dir"]
        if "engine_limits" in settings:
            defaults["engine_limits"].update(settings["engine_limits"])

    # Mergear timeouts.yaml (valores con prioridad sobre settings.yaml)
    if timeouts:
        if "z3_timeout_seconds" in timeouts:
            defaults["engine_limits"]["solver_timeout_ms"] = timeouts["z3_timeout_seconds"] * 1000
        if "max_k_paths" in timeouts:
            defaults["engine_limits"]["max_k_paths"] = timeouts["max_k_paths"]
        if "mcts_max_depth" in timeouts:
            defaults["engine_limits"]["mcts_max_depth"] = timeouts["mcts_max_depth"]

    # Mergear critical_nodes.yaml
    if critical:
        if "critical_patterns" in critical:
            defaults["critical_patterns"] = critical["critical_patterns"]
        if "critical_nodes" in critical:
            defaults["critical_nodes"] = critical["critical_nodes"]

    return defaults


def get_solver_timeout_ms(settings=None):
    """Obtiene el timeout del solver quirurgico (15s por defecto)."""
    s = settings or load_settings()
    return s.get("engine_limits", {}).get("solver_timeout_ms", 15000)


def get_solver_fast_timeout_ms(settings=None):
    """Obtiene el timeout del solver rapido (5s por defecto)."""
    s = settings or load_settings()
    return s.get("engine_limits", {}).get("solver_fast_timeout_ms", 5000)


def get_mcts_config(settings=None):
    """Obtiene la configuracion de MCTS."""
    s = settings or load_settings()
    limits = s.get("engine_limits", {})
    return {
        "max_depth": limits.get("mcts_max_depth", 5),
        "max_simulations": limits.get("mcts_max_simulations", 100),
        "timeout_ms": limits.get("solver_fast_timeout_ms", 5000),
    }


def get_k_path_limit(settings=None):
    """Obtiene el limite K-Paths (10 por defecto)."""
    s = settings or load_settings()
    return s.get("engine_limits", {}).get("max_k_paths", 10)


def get_sandbox_timeout_s(settings=None):
    """Obtiene el timeout del sandbox en segundos."""
    s = settings or load_settings()
    return s.get("engine_limits", {}).get("sandbox_timeout_s", 5)


def get_critical_patterns(settings=None):
    """Obtiene los patrones de nodos criticos para el router."""
    s = settings or load_settings()
    return s.get("critical_patterns", [])


def get_critical_nodes(settings=None):
    """Obtiene la lista de nodos criticos (keywords)."""
    s = settings or load_settings()
    return s.get("critical_nodes", [])
