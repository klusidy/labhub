from __future__ import annotations
import os, yaml
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class DeviceConfig:
    id: str
    driver: str
    options: Dict[str, Any]


@dataclass
class HubConfig:
    devices: List[DeviceConfig]


DEFAULT_CONFIG_PATH = os.environ.get("LABHUB_CONFIG", os.path.join(os.getcwd(), "config.yaml"))


def load_config(path: str | None = None) -> HubConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    devices = [DeviceConfig(id=d["id"], driver=d["driver"], options=d.get("conn", {})) for d in raw.get("devices", [])]
    return HubConfig(devices=devices)
