"""
TITAN OMNISCALE X - Config Loader (Pure Python)

Cargador de configuracion con import condicional de pyyaml.
Compatible con Android.
"""
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_settings():
    config_path = Path(__file__).resolve().parent / "settings.yaml"
    if config_path.exists() and HAS_YAML:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {"project_dir": ".", "engine_limits": {}, "critical_nodes": []}
