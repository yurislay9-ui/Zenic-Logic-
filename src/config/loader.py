import yaml
from pathlib import Path

def load_settings() -> dict:
    config_path = Path(__file__).resolve().parent / "settings.yaml"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {"project_dir": ".", "engine_limits": {}, "critical_nodes": []}
