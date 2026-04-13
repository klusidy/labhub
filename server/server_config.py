"""
Server-level configuration loaded from server.yaml.

This module is the single source of truth for all server settings that do not
change over the server's lifetime: network, logging, scripting paths, InfluxDB,
and custom GUI mounts.

Dependencies: stdlib + pyyaml only (no FastAPI) — safe to import from the launcher.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger("labhub.server_config")

ENV_VAR = "LABHUB_SERVER_CONFIG"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ServerSection:
    host: str = "127.0.0.1"
    port: int = 8212
    max_workers: int = 8  # Thread pool size for blocking driver operations


@dataclass
class LoggingSection:
    level: str = "INFO"
    file: Optional[str] = None


@dataclass
class ScriptingSection:
    macros: Optional[str] = None
    python: Optional[str] = None
    startup_folder: Optional[str] = None


@dataclass
class InfluxSection:
    enabled: bool = False
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "labhub"
    bucket: str = "labhub"
    exe_path: Optional[str] = None
    stop_on_exit: bool = False
    batch_size: int = 100
    flush_interval_ms: int = 1000
    max_retries: int = 3
    snapshot_interval: float = 10.0


@dataclass
class CustomGuiEntry:
    device_id: str
    route: str
    dist: str  # path to dist directory (relative to project root, or absolute)


@dataclass
class ServerConfig:
    """Complete server configuration loaded from server.yaml."""

    # Source metadata (not in YAML)
    config_file: Path = field(default_factory=lambda: Path("server.yaml"))

    # YAML sections
    server: ServerSection = field(default_factory=ServerSection)
    devices: str = "./config.yaml"
    profile: str = "./profile.yaml"
    logging: LoggingSection = field(default_factory=LoggingSection)
    scripting: ScriptingSection = field(default_factory=ScriptingSection)
    influx: InfluxSection = field(default_factory=InfluxSection)
    custom_guis: List[CustomGuiEntry] = field(default_factory=list)

    # Resolved absolute paths (computed in __post_init__)
    devices_path: Optional[Path] = field(default=None, init=False, repr=False)
    profile_path: Optional[Path] = field(default=None, init=False, repr=False)
    macros_path: Optional[Path] = field(default=None, init=False, repr=False)
    python_path: Optional[Path] = field(default=None, init=False, repr=False)
    startup_folder_path: Optional[Path] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._resolve_paths()

    def _resolve_paths(self):
        """Resolve all relative paths against server.yaml's directory."""
        base = self.config_file.parent

        self.devices_path = (base / self.devices).resolve()
        self.profile_path = (base / self.profile).resolve()

        if self.scripting.macros:
            self.macros_path = (base / self.scripting.macros).resolve()
        else:
            self.macros_path = None

        if self.scripting.python:
            self.python_path = (base / self.scripting.python).resolve()
        else:
            self.python_path = None

        if self.scripting.startup_folder:
            self.startup_folder_path = (base / self.scripting.startup_folder).resolve()
        else:
            self.startup_folder_path = None

    def to_influx_cfg(self):
        """Convert to the existing InfluxCfg dataclass (used by influx.py)."""
        from .loader import InfluxCfg

        s = self.influx
        return InfluxCfg(
            enabled=s.enabled,
            url=s.url,
            token=s.token,
            org=s.org,
            bucket=s.bucket,
            exe_path=s.exe_path,
            stop_on_exit=s.stop_on_exit,
            batch_size=s.batch_size,
            flush_interval_ms=s.flush_interval_ms,
            max_retries=s.max_retries,
            snapshot_interval=s.snapshot_interval,
        )

    def resolve_gui_dist(self, entry: CustomGuiEntry) -> Path:
        """Resolve a custom GUI dist path (relative to project root, or absolute)."""
        p = Path(entry.dist)
        if p.is_absolute():
            return p
        project_root = Path(__file__).resolve().parents[1]
        return (project_root / p).resolve()


# ── Singleton ────────────────────────────────────────────────────────────────

_config: Optional[ServerConfig] = None


def get_server_config() -> ServerConfig:
    """Get the loaded server config singleton. Loads defaults if not yet set."""
    global _config
    if _config is None:
        _config = load_server_config()
    return _config


def set_server_config(cfg: ServerConfig) -> None:
    """Set the server config singleton (called early in main.py)."""
    global _config
    _config = cfg


# ── Load / Save ──────────────────────────────────────────────────────────────


def _default_search_paths() -> List[Path]:
    """Candidate paths when no explicit path or env var is provided."""
    return [
        Path.cwd() / "server.yaml",
        Path(__file__).resolve().parents[1] / "launcher" / "server_default.yaml",
    ]


def load_server_config(path: Optional[str] = None) -> ServerConfig:
    """
    Load server configuration.

    Resolution order:
      1. Explicit *path* argument
      2. LABHUB_SERVER_CONFIG environment variable
      3. ./server.yaml in cwd
      4. launcher/server_default.yaml
    """
    if path is None:
        env_path = os.environ.get(ENV_VAR)
        if env_path:
            path = env_path
        else:
            for candidate in _default_search_paths():
                if candidate.exists():
                    path = str(candidate)
                    break

    if path is None:
        logger.warning("No server.yaml found, using built-in defaults")
        return ServerConfig()

    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Server config not found: {resolved}")

    logger.info(f"Loading server config from: {resolved}")

    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    server_raw = raw.get("server") or {}
    logging_raw = raw.get("logging") or {}
    scripting_raw = raw.get("scripting") or {}
    influx_raw = raw.get("influx") or {}
    guis_raw = raw.get("custom_guis") or []

    return ServerConfig(
        config_file=resolved,
        server=ServerSection(
            host=server_raw.get("host", "127.0.0.1"),
            port=int(server_raw.get("port", 8212)),
            max_workers=int(server_raw.get("max_workers", 8)),
        ),
        devices=raw.get("devices", "./config.yaml"),
        profile=raw.get("profile", "./profile.yaml"),
        logging=LoggingSection(
            level=logging_raw.get("level", "INFO"),
            file=logging_raw.get("file"),
        ),
        scripting=ScriptingSection(
            macros=scripting_raw.get("macros"),
            python=scripting_raw.get("python"),
            startup_folder=scripting_raw.get("startup_folder"),
        ),
        influx=_parse_influx(influx_raw),
        custom_guis=[
            CustomGuiEntry(
                device_id=g["device_id"],
                route=g["route"],
                dist=g["dist"],
            )
            for g in guis_raw
            if "device_id" in g and "route" in g and "dist" in g
        ],
    )


def _parse_influx(raw: dict) -> InfluxSection:
    """Parse the influx section with safe defaults."""
    if not raw:
        return InfluxSection()
    return InfluxSection(
        enabled=raw.get("enabled", False),
        url=raw.get("url", "http://localhost:8086"),
        token=raw.get("token", ""),
        org=raw.get("org", "labhub"),
        bucket=raw.get("bucket", "labhub"),
        exe_path=raw.get("exe_path"),
        stop_on_exit=raw.get("stop_on_exit", False),
        batch_size=int(raw.get("batch_size", 100)),
        flush_interval_ms=int(raw.get("flush_interval_ms", 1000)),
        max_retries=int(raw.get("max_retries", 3)),
        snapshot_interval=float(raw.get("snapshot_interval", 10.0)),
    )


def save_server_config(cfg: ServerConfig, path: Optional[Path] = None) -> None:
    """
    Save server configuration to YAML (atomic write).
    Used by the launcher ConfigureDialog.
    """
    path = path or cfg.config_file

    data = {
        "server": {
            "host": cfg.server.host,
            "port": cfg.server.port,
            "max_workers": cfg.server.max_workers,
        },
        "devices": cfg.devices,
        "profile": cfg.profile,
        "logging": {
            "level": cfg.logging.level,
            "file": cfg.logging.file,
        },
        "scripting": {
            "macros": cfg.scripting.macros,
            "python": cfg.scripting.python,
            "startup_folder": cfg.scripting.startup_folder,
        },
        "influx": {
            "enabled": cfg.influx.enabled,
            "url": cfg.influx.url,
            "token": cfg.influx.token,
            "org": cfg.influx.org,
            "bucket": cfg.influx.bucket,
            "exe_path": cfg.influx.exe_path,
            "stop_on_exit": cfg.influx.stop_on_exit,
            "batch_size": cfg.influx.batch_size,
            "flush_interval_ms": cfg.influx.flush_interval_ms,
            "max_retries": cfg.influx.max_retries,
            "snapshot_interval": cfg.influx.snapshot_interval,
        },
        "custom_guis": [
            {"device_id": g.device_id, "route": g.route, "dist": g.dist}
            for g in cfg.custom_guis
        ],
    }

    temp_path = str(path) + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    Path(temp_path).replace(path)

    logger.info(f"Server config saved to: {path}")
