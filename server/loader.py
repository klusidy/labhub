"""
Configuration and device loading utilities.

This module handles:
- Loading config.yaml (device definitions)
- Loading profile.yaml (device state snapshots)
"""

import os
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DeviceCfg:
    """Configuration for a single device."""

    id: str
    driver: str
    options: Dict[
        str, Any
    ]  # Full dict from config.yaml for that device (incl. id and driver)


@dataclass
class InfluxCfg:
    """InfluxDB configuration."""

    enabled: bool = False
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "labhub"
    bucket: str = "labhub"
    exe_path: Optional[str] = None  # Path to influxd executable for auto-start
    batch_size: int = 100  # Max points before flush
    flush_interval_ms: int = 1000  # Max time before flush
    max_retries: int = 3  # Retry attempts for failed writes
    snapshot_interval: float = 10.0  # Seconds between state snapshots


@dataclass
class HubCfg:
    """Complete hub configuration."""

    devices: List[DeviceCfg]
    influx: Optional[InfluxCfg] = None


def get_config_path() -> str:
    """
    Get the path to the active config file.

    Priority:
    1. LABHUB_CONFIG environment variable
    2. Default: launcher/config_default.yaml

    Returns:
        Absolute path to config file
    """
    env_cp = os.environ.get("LABHUB_CONFIG")
    if env_cp and str(env_cp).strip():
        return str(Path(env_cp).resolve())

    # Default to launcher/config_default.yaml
    default_path = (
        Path(__file__).resolve().parents[1] / "launcher" / "config_default.yaml"
    )
    return str(default_path)


def load_config(config_path: str | None = None) -> HubCfg:
    """
    Load device configuration from YAML file.

    Args:
        config_path: Optional explicit path. If None, uses get_config_path()

    Returns:
        HubCfg with list of device configurations

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    if config_path is None:
        config_path = get_config_path()

    config_path = str(Path(config_path).resolve())
    logger.info(f"Loading config from: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    devices: List[DeviceCfg] = []
    for d in raw.get("devices", []):
        if "id" not in d or "driver" not in d:
            logger.warning(f"Skipping device with missing 'id' or 'driver': {d}")
            continue
        devices.append(DeviceCfg(id=d["id"], driver=d["driver"], options=d))

    logger.info(f"Loaded {len(devices)} device(s) from config")

    # Parse InfluxDB configuration (optional)
    influx_cfg: Optional[InfluxCfg] = None
    influx_raw = raw.get("influx")
    if influx_raw and isinstance(influx_raw, dict):
        influx_cfg = InfluxCfg(
            enabled=influx_raw.get("enabled", False),
            url=influx_raw.get("url", "http://localhost:8086"),
            token=influx_raw.get("token", ""),
            org=influx_raw.get("org", "labhub"),
            bucket=influx_raw.get("bucket", "labhub"),
            exe_path=influx_raw.get("exe_path"),
            batch_size=influx_raw.get("batch_size", 100),
            flush_interval_ms=influx_raw.get("flush_interval_ms", 1000),
            max_retries=influx_raw.get("max_retries", 3),
            snapshot_interval=influx_raw.get("snapshot_interval", 10.0),
        )
        if influx_cfg.enabled:
            logger.info(f"InfluxDB configured: {influx_cfg.url} (bucket={influx_cfg.bucket})")

    return HubCfg(devices=devices, influx=influx_cfg)


# ===== Profile System =====


@dataclass
class PropertyProfile:
    """Profile entry for a single property."""

    value: Any
    policy: str  # "read" or "write"
    # Future: min, max, user-defined limits, etc.


@dataclass
class DeviceProfile:
    """Profile for a single device."""

    id: str
    properties: Dict[str, PropertyProfile]


@dataclass
class HubProfile:
    """Complete hub profile (device states)."""

    devices: List[DeviceProfile]


def get_profile_path() -> str:
    """
    Get the path to the active profile file.

    Priority:
    1. LABHUB_PROFILE environment variable
    2. Default: launcher/profile_default.yaml

    Returns:
        Absolute path to profile file
    """
    env_pp = os.environ.get("LABHUB_PROFILE")
    if env_pp and str(env_pp).strip():
        return str(Path(env_pp).resolve())

    # Default to launcher/profile_default.yaml
    default_path = (
        Path(__file__).resolve().parents[1] / "launcher" / "profile_default.yaml"
    )
    return str(default_path)


def load_profile(profile_path: str | None = None) -> HubProfile:
    """
    Load device profile (state snapshot) from YAML file.

    Profile structure:
    ```yaml
    devices:
      - id: device1
        properties:
          voltage:
            value: 5.0
            policy: write  # Apply on load
          current:
            value: 0.1
            policy: read   # Don't apply, just record
    ```

    Args:
        profile_path: Optional explicit path. If None, uses get_profile_path()

    Returns:
        HubProfile with device states

    Raises:
        FileNotFoundError: If profile file doesn't exist
        yaml.YAMLError: If profile file is invalid YAML
    """
    if profile_path is None:
        profile_path = get_profile_path()

    profile_path = str(Path(profile_path).resolve())

    # Profile file is optional - return empty if missing
    if not Path(profile_path).exists():
        logger.info(f"No profile file found at: {profile_path}")
        return HubProfile(devices=[])

    logger.info(f"Loading profile from: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    devices: List[DeviceProfile] = []
    for d in raw.get("devices", []):
        if "id" not in d:
            logger.warning(f"Skipping device profile with missing 'id': {d}")
            continue

        properties: Dict[str, PropertyProfile] = {}
        for prop_name, prop_data in d.get("properties", {}).items():
            if isinstance(prop_data, dict):
                properties[prop_name] = PropertyProfile(
                    value=prop_data.get("value"),
                    policy=prop_data.get("policy", "read"),
                )
            else:
                # Simple value without policy (default to "read")
                properties[prop_name] = PropertyProfile(value=prop_data, policy="read")

        devices.append(DeviceProfile(id=d["id"], properties=properties))

    logger.info(f"Loaded profile for {len(devices)} device(s)")
    return HubProfile(devices=devices)


def save_profile(profile: HubProfile, profile_path: str | None = None) -> None:
    """
    Save device profile (state snapshot) to YAML file.

    Args:
        profile: HubProfile to save
        profile_path: Optional explicit path. If None, uses get_profile_path()
    """
    if profile_path is None:
        profile_path = get_profile_path()

    profile_path = str(Path(profile_path).resolve())
    logger.debug(f"Saving profile to: {profile_path}")

    # Convert to dict for YAML serialization
    data = {"devices": []}
    for device in profile.devices:
        device_data = {"id": device.id, "properties": {}}
        for prop_name, prop_profile in device.properties.items():
            device_data["properties"][prop_name] = {
                "value": prop_profile.value,
                "policy": prop_profile.policy,
            }
        data["devices"].append(device_data)

    # Ensure directory exists
    Path(profile_path).parent.mkdir(parents=True, exist_ok=True)

    # Write atomically (write to temp file, then rename)
    temp_path = profile_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    # Atomic rename
    Path(temp_path).replace(profile_path)
    logger.debug(f"Profile saved successfully")
