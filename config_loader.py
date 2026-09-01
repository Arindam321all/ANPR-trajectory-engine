"""
Loads config.yaml once and exposes it as a simple singleton object so every
module (detector, tracker, analytics, API) reads consistent settings.
"""
import yaml
from pathlib import Path
from functools import lru_cache

CONFIG_PATH = Path(__file__).parent / "config.yaml"


@lru_cache(maxsize=1)
def get_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_camera(camera_id: str) -> dict:
    cfg = get_config()
    for cam in cfg["cameras"]:
        if cam["id"] == camera_id:
            return cam
    raise KeyError(f"Unknown camera_id: {camera_id}")


def all_camera_ids() -> list:
    return [c["id"] for c in get_config()["cameras"]]
