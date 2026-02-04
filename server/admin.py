"""
Admin API endpoints.

This module contains administrative endpoints for:
- Reloading devices from config
- Managing logging levels at runtime
- Applying property configurations
- Config file management (read, write, list drivers)
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

import yaml

from .schemas import ApplyPropertiesRequest
from .utils import set_level as set_logging_level, get_level as get_logging_level
from .loader import load_config, get_config_path

logger = logging.getLogger(__name__)

# Router will be included in main app
router = APIRouter(prefix="/api/v2/admin", tags=["admin"])

# Dependency injection - will be set by main.py
manager = None
profile_monitor = None


def get_manager():
    """Dependency to get device manager instance."""
    return manager


def get_profile_monitor():
    """Dependency to get profile monitor instance."""
    return profile_monitor


@router.post("/reload")
async def reload_all(manager=Depends(get_manager)):
    """
    Reload all devices from config.yaml without restarting the process.

    This endpoint performs a complete device reload:
    1. Stops all polling tasks
    2. Disconnects all devices
    3. Reloads config.yaml
    4. Reconnects all devices
    5. Restarts polling

    Returns:
        Dict with:
            - ok: True if successful
            - devices: List of reloaded device states

    Raises:
        HTTPException(500): Error during reload process

    Notes:
        - All devices are briefly unavailable during reload
        - WebSocket clients will receive state updates when devices reconnect
        - Config file is re-read from disk (changes take effect immediately)
    """
    logger.info("Reloading all devices from config...")

    try:
        await manager.stop_polling()
        await manager.remove_all()

        # Reinitialize devices from config
        cfg = load_config()
        await manager.initialize_devices(cfg)

        await manager.start_polling(500)  # TODO: Make polling interval configurable
        logger.info("Reload complete")

        devices = [d.model_dump() for d in await manager.list_devices()]
        return {"ok": True, "devices": devices}

    except Exception as e:
        logger.error(f"Failed to reload devices: {e}", exc_info=True)
        raise HTTPException(500, f"Error reloading devices: {str(e)}")


@router.post("/reload/{dev_id}")
async def reload_device(dev_id: str, manager=Depends(get_manager)):
    """
    Reload a single device from config.yaml.

    This endpoint reloads one device without affecting others:
    1. Stops polling for this device
    2. Disconnects device
    3. Re-reads config.yaml
    4. Reconnects device with updated config
    5. Restarts polling for this device

    Args:
        dev_id: Device identifier to reload

    Returns:
        Dict with:
            - ok: True if successful
            - devices: List of all device states after reload

    Raises:
        HTTPException(404): Device not found in config
        HTTPException(500): Error during reload

    Use cases:
        - Recovering from device errors
        - Applying config changes to one device
        - Reconnecting after hardware issues
    """
    logger.info(f"Reloading device: {dev_id}")

    try:
        # Remove existing device if present
        if dev_id in manager.devices:
            await manager.stop_polling_device(dev_id)
            await manager.remove_device(dev_id)

        # Find device in config and re-add
        cfg = load_config()
        device_found = False
        for d in cfg.devices:
            if d.id == dev_id:
                await manager.add_device(d.id, d.driver, d.options)
                await manager.start_polling_device(d.id)
                device_found = True
                logger.info(f"Device '{dev_id}' reloaded successfully")
                break

        if not device_found:
            logger.warning(f"Device '{dev_id}' not found in config")
            raise HTTPException(404, f"Device '{dev_id}' not found in config")

        devices = [d.model_dump() for d in await manager.list_devices()]
        return {"ok": True, "devices": devices}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reload device '{dev_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Error reloading device: {str(e)}")


@router.get("/loglevel")
async def get_loglevel(logger_name: str | None = None):
    """
    Get current logging level.

    Args:
        logger_name: Optional specific logger path (e.g., 'labhub.drivers').
                    If None, returns root 'labhub' logger level.

    Returns:
        Dict with:
            - logger: Logger name queried
            - level: Current level name (e.g., "INFO", "DEBUG")

    Examples:
        GET /api/v2/admin/loglevel
        GET /api/v2/admin/loglevel?logger_name=labhub.drivers
    """
    logger.debug(
        f"GET /api/v2/admin/loglevel - querying logger: {logger_name or 'labhub'}"
    )
    return {"logger": logger_name or "labhub", "level": get_logging_level(logger_name)}


@router.post("/loglevel")
async def set_loglevel(level: str, logger_name: str | None = None):
    """
    Set logging level at runtime.

    Changes the logging level for the specified logger without restarting
    the server. Useful for debugging production issues.

    Args:
        level: Level name (DEBUG, INFO, WARNING, ERROR, CRITICAL) or numeric value
        logger_name: Optional specific logger (e.g., 'labhub.drivers', 'labhub.drivers.kinesis').
                    If None, sets root 'labhub' logger.

    Returns:
        Dict with:
            - logger: Logger name modified
            - previous: Previous level name
            - new: New level name

    Raises:
        HTTPException(400): Invalid level name

    Examples:
        POST /api/v2/admin/loglevel?level=DEBUG
        POST /api/v2/admin/loglevel?level=WARNING&logger_name=labhub.drivers

    Notes:
        - Changes affect all child loggers unless they have explicit levels set
        - Setting to DEBUG may produce significant log volume
        - Changes are not persisted (reset on server restart)
    """
    logger.debug(
        f"POST /api/v2/admin/loglevel - setting {logger_name or 'labhub'} to {level}"
    )

    try:
        res = set_logging_level(level, logger_name)
        logger.info(
            f"Log level changed: {res['logger']} from {res['previous']} to {res['new']}"
        )
        return res
    except ValueError as e:
        logger.warning(f"Invalid log level requested: {level}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/influx/status")
async def get_influx_status(manager=Depends(get_manager)):
    """
    Get InfluxDB integration status and metrics.

    Returns:
        Dict with:
            - enabled: Whether InfluxDB is configured
            - running: Whether writer is active
            - url: InfluxDB URL (if configured)
            - bucket: Target bucket
            - queue_size: Pending writes
            - points_written: Total successful writes
            - points_dropped: Dropped due to errors/queue full
            - write_errors: Total write failures
            - last_error: Most recent error message (if any)

    Notes:
        - Returns {"enabled": False} if InfluxDB not configured
        - Useful for monitoring telemetry health
    """
    if not manager.influx:
        return {"enabled": False, "reason": "not_configured"}
    return manager.influx.get_status()


@router.post("/apply_properties")
async def apply_properties(req: ApplyPropertiesRequest, manager=Depends(get_manager)):
    """
    Apply properties from file or inline dict to devices.

    Bulk property updates across multiple devices. Does NOT restart devices,
    only updates property values.

    Args:
        req: ApplyPropertiesRequest containing either:
            - file_path: Path to properties.yaml
            - properties: Inline dict {dev_id: {prop: value}}

    Returns:
        Dict with:
            - status: "ok"
            - results: Dict[dev_id] = "success" | "skipped" | "error: <message>"

    Raises:
        HTTPException(400): Neither file_path nor properties provided
        HTTPException(404): Properties file not found
        HTTPException(500): Error applying properties

    Property File Format:
        ```yaml
        devices:
          device1:
            voltage: 5.0
            current: "$READOUT"  # Read current value
          device2:
            position: 100.0
        ```

    Notes:
        - Properties with "$READOUT" are read but not written
        - Invalid properties are logged and skipped
        - Other devices continue if one fails
        - State changes are published to event bus
    """
    logger.debug("POST /api/v2/admin/apply_properties")

    if req.file_path:
        path = Path(req.file_path)
        logger.info(f"Applying properties from file: {path}")

        if not path.exists():
            logger.warning(f"Properties file not found: {path}")
            raise HTTPException(404, f"Properties file not found: {path}")

        try:
            results = await manager.apply_properties_from_file(path)
        except Exception as e:
            logger.error(f"Failed to apply properties from file: {e}", exc_info=True)
            raise HTTPException(500, f"Error applying properties: {str(e)}")

    elif req.properties:
        logger.info(f"Applying inline properties to {len(req.properties)} device(s)")

        try:
            results = await manager.apply_properties_from_dict(req.properties)
        except Exception as e:
            logger.error(f"Failed to apply inline properties: {e}", exc_info=True)
            raise HTTPException(500, f"Error applying properties: {str(e)}")

    else:
        logger.warning("apply_properties called without file_path or properties")
        raise HTTPException(400, "Must provide file_path or properties")

    # Log summary
    success_count = sum(1 for r in results.values() if r == "success")
    error_count = sum(1 for r in results.values() if r.startswith("error:"))
    logger.info(f"Applied properties: {success_count} succeeded, {error_count} failed")

    return {"status": "ok", "results": results}


@router.get("/profile")
async def get_profile(monitor=Depends(get_profile_monitor)):
    """
    Get current profile information.

    Returns:
        Dict with:
            - path: Path to current profile file
            - raw: Raw YAML content as string
            - policies: Dict of device policies {dev_id: {prop_name: policy}}

    Notes:
        - Profile path determined by LABHUB_PROFILE env var or default
        - Useful for admin GUI to display profile tree
    """
    logger.debug("GET /api/v2/admin/profile")

    try:
        profile_path = monitor.profile_path

        raw_content = ""
        if profile_path and Path(profile_path).exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                raw_content = f.read()

        return {
            "path": str(profile_path) if profile_path else None,
            "raw": raw_content,
            "policies": monitor._policies,
        }

    except Exception as e:
        logger.error(f"Failed to read profile: {e}", exc_info=True)
        raise HTTPException(500, f"Error reading profile: {str(e)}")


@router.post("/profile/load")
async def load_profile_endpoint(
    file_path: str,
    switch_path: bool = True,
    monitor=Depends(get_profile_monitor),
):
    """
    Load profile from file and apply write-policy properties.

    Loads properties and policies from a profile file, applies properties with
    "write" policy to devices, and optionally switches to using this profile
    for future periodic saves.

    Args:
        file_path: Path to profile file to load
        switch_path: If True, use this profile for future saves (default: True)

    Returns:
        Dict with:
            - status: "ok"
            - profile_path: Current profile path after operation
            - loaded_from: Path that was loaded

    Raises:
        HTTPException(404): Profile file not found
        HTTPException(500): Error loading or applying profile

    Notes:
        - Only properties with "write" policy are applied
        - Value comparison done automatically (checks device CACHE)
        - Policies from loaded profile are preserved
        - If switch_path=False, loaded profile is applied but periodic
          saves continue using the original profile path
    """
    logger.debug(
        f"POST /api/v2/admin/profile/load - file_path={file_path}, switch_path={switch_path}"
    )

    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Profile file not found: {path}")
            raise HTTPException(404, f"Profile file not found: {path}")

        await monitor.load_profile(path, switch_path=switch_path)

        return {
            "status": "ok",
            "profile_path": str(monitor.profile_path),
            "loaded_from": str(path),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load profile: {e}", exc_info=True)
        raise HTTPException(500, f"Error loading profile: {str(e)}")


@router.post("/profile/save")
async def force_save_profile(monitor=Depends(get_profile_monitor)):
    """
    Force immediate profile save.

    Saves current device states to profile file immediately, without waiting
    for the next periodic save interval.

    Returns:
        Dict with:
            - status: "ok"
            - profile_path: Path where profile was saved

    Raises:
        HTTPException(500): Error saving profile

    Use cases:
        - Manual backup before risky operations
        - Ensuring latest state is persisted
        - Testing profile save functionality
    """
    logger.debug("POST /api/v2/admin/profile/save - forcing immediate save")

    try:
        await monitor.force_save()
        return {"status": "ok", "profile_path": str(monitor.profile_path)}

    except Exception as e:
        logger.error(f"Failed to force save profile: {e}", exc_info=True)
        raise HTTPException(500, f"Error saving profile: {str(e)}")


@router.post("/profile/policy")
async def set_property_policy(
    dev_id: str,
    prop_name: str,
    policy: str,
    monitor=Depends(get_profile_monitor),
):
    """
    Change policy for a specific device property.

    Sets whether a property should be restored ("write") or just monitored ("read")
    when loading profiles. The policy change is persisted in the next profile save.

    Args:
        dev_id: Device identifier
        prop_name: Property name
        policy: New policy - must be "read" or "write"

    Returns:
        Dict with:
            - status: "ok"
            - dev_id: Device ID
            - prop_name: Property name
            - policy: New policy value

    Raises:
        HTTPException(400): Invalid policy or cannot set "write" on read-only property
        HTTPException(500): Error setting policy

    Policy meanings:
        - "read": Monitor and save property value, but don't restore on load
        - "write": Restore property value when loading profile

    Notes:
        - Cannot set "write" policy on read-only properties
        - Policy is persisted immediately (triggers profile save)
        - Useful for controlling which properties are restored on startup
    """
    logger.debug(
        f"POST /api/v2/admin/profile/policy - dev_id={dev_id}, prop_name={prop_name}, policy={policy}"
    )

    try:
        await monitor.set_policy(dev_id, prop_name, policy)
        return {
            "status": "ok",
            "dev_id": dev_id,
            "prop_name": prop_name,
            "policy": policy,
        }

    except ValueError as e:
        logger.warning(f"Invalid policy request: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to set policy: {e}", exc_info=True)
        raise HTTPException(500, f"Error setting policy: {str(e)}")


# ===== Config Management =====


class DeviceConfigUpdate(BaseModel):
    """Request model for updating a single device's config."""
    id: str
    driver: str
    options: Dict[str, Any] = {}


class ConfigUpdateRequest(BaseModel):
    """Request model for updating the config file."""
    devices: List[Dict[str, Any]]
    influx: Optional[Dict[str, Any]] = None


@router.get("/config")
async def get_config():
    """
    Get current configuration.

    Returns:
        Dict with:
            - path: Path to current config file
            - config: Parsed config content (devices and influx)
            - raw: Raw YAML content as string

    Notes:
        - Config path determined by LABHUB_CONFIG env var or default
        - Useful for admin GUI to display and edit config
    """
    logger.debug("GET /api/v2/admin/config")

    config_path = get_config_path()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        parsed = yaml.safe_load(raw_content) or {}

        return {
            "path": config_path,
            "config": parsed,
            "raw": raw_content,
        }

    except FileNotFoundError:
        raise HTTPException(404, f"Config file not found: {config_path}")
    except Exception as e:
        logger.error(f"Failed to read config: {e}", exc_info=True)
        raise HTTPException(500, f"Error reading config: {str(e)}")


@router.put("/config")
async def update_config(req: ConfigUpdateRequest):
    """
    Update the configuration file.

    Writes the provided config to the current config file. Does NOT
    automatically reload devices - call /reload or /soft-reload after.

    Args:
        req: ConfigUpdateRequest with devices list and optional influx config

    Returns:
        Dict with:
            - status: "ok"
            - path: Path where config was saved

    Raises:
        HTTPException(500): Error writing config file

    Notes:
        - Atomic write (temp file + rename)
        - Preserves YAML formatting
        - Call /soft-reload to apply changes without full restart
    """
    logger.debug("PUT /api/v2/admin/config")

    config_path = get_config_path()

    try:
        # Build config dict
        config_data = {"devices": req.devices}
        if req.influx:
            config_data["influx"] = req.influx

        # Atomic write
        temp_path = config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)

        Path(temp_path).replace(config_path)

        logger.info(f"Config saved to {config_path}")
        return {"status": "ok", "path": config_path}

    except Exception as e:
        logger.error(f"Failed to write config: {e}", exc_info=True)
        raise HTTPException(500, f"Error writing config: {str(e)}")


@router.get("/config/device/{dev_id}")
async def get_device_config(dev_id: str):
    """
    Get configuration for a specific device.

    Args:
        dev_id: Device identifier

    Returns:
        Dict with device configuration from config.yaml

    Raises:
        HTTPException(404): Device not found in config
    """
    logger.debug(f"GET /api/v2/admin/config/device/{dev_id}")

    config_path = get_config_path()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f) or {}

        for device in parsed.get("devices", []):
            if device.get("id") == dev_id:
                return {"device": device}

        raise HTTPException(404, f"Device '{dev_id}' not found in config")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read device config: {e}", exc_info=True)
        raise HTTPException(500, f"Error reading config: {str(e)}")


@router.put("/config/device/{dev_id}")
async def update_device_config(dev_id: str, device_config: Dict[str, Any]):
    """
    Update configuration for a specific device.

    Updates or adds a device in the config file. Does NOT reload the device.

    Args:
        dev_id: Device identifier
        device_config: New device configuration (must include 'driver')

    Returns:
        Dict with:
            - status: "ok" or "created"
            - device: Updated device config

    Notes:
        - If device exists, updates it in place
        - If device doesn't exist, appends it
        - Call /reload/{dev_id} to apply changes
    """
    logger.debug(f"PUT /api/v2/admin/config/device/{dev_id}")

    config_path = get_config_path()

    if "driver" not in device_config:
        raise HTTPException(400, "Device config must include 'driver' field")

    # Ensure id matches
    device_config["id"] = dev_id

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f) or {}

        devices = parsed.get("devices", [])
        found = False
        for i, device in enumerate(devices):
            if device.get("id") == dev_id:
                devices[i] = device_config
                found = True
                break

        if not found:
            devices.append(device_config)

        parsed["devices"] = devices

        # Atomic write
        temp_path = config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(parsed, f, default_flow_style=False, sort_keys=False)

        Path(temp_path).replace(config_path)

        status = "ok" if found else "created"
        logger.info(f"Device config {status}: {dev_id}")
        return {"status": status, "device": device_config}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update device config: {e}", exc_info=True)
        raise HTTPException(500, f"Error updating config: {str(e)}")


@router.delete("/config/device/{dev_id}")
async def delete_device_config(dev_id: str):
    """
    Remove a device from configuration.

    Removes device from config file. Does NOT stop the running device.

    Args:
        dev_id: Device identifier to remove

    Returns:
        Dict with:
            - status: "ok"
            - removed: Device ID that was removed

    Raises:
        HTTPException(404): Device not found in config
    """
    logger.debug(f"DELETE /api/v2/admin/config/device/{dev_id}")

    config_path = get_config_path()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            parsed = yaml.safe_load(f) or {}

        devices = parsed.get("devices", [])
        original_len = len(devices)
        devices = [d for d in devices if d.get("id") != dev_id]

        if len(devices) == original_len:
            raise HTTPException(404, f"Device '{dev_id}' not found in config")

        parsed["devices"] = devices

        # Atomic write
        temp_path = config_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(parsed, f, default_flow_style=False, sort_keys=False)

        Path(temp_path).replace(config_path)

        logger.info(f"Device removed from config: {dev_id}")
        return {"status": "ok", "removed": dev_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete device config: {e}", exc_info=True)
        raise HTTPException(500, f"Error deleting from config: {str(e)}")


@router.get("/drivers")
async def list_drivers():
    """
    List all available drivers.

    Scans the drivers directory for vendor folders and driver modules.

    Returns:
        Dict with:
            - drivers: List of driver info dicts, each containing:
                - id: Full driver identifier (e.g., "pico_technology.ps5000a")
                - vendor: Vendor name
                - name: Driver/device name
                - path: File path

    Notes:
        - Drivers are Python files in drivers/<vendor>/<driver>.py
        - Excludes files starting with underscore
        - Does not validate that drivers are importable
    """
    logger.debug("GET /api/v2/admin/drivers")

    drivers_dir = Path(__file__).parent / "drivers"
    drivers_list = []

    try:
        for vendor_dir in drivers_dir.iterdir():
            if not vendor_dir.is_dir():
                continue
            if vendor_dir.name.startswith("_"):
                continue

            vendor = vendor_dir.name

            for driver_file in vendor_dir.glob("*.py"):
                if driver_file.name.startswith("_"):
                    continue

                driver_name = driver_file.stem
                driver_id = f"{vendor}.{driver_name}"

                drivers_list.append({
                    "id": driver_id,
                    "vendor": vendor,
                    "name": driver_name,
                    "path": str(driver_file),
                })

        # Sort by vendor, then name
        drivers_list.sort(key=lambda d: (d["vendor"], d["name"]))

        return {"drivers": drivers_list}

    except Exception as e:
        logger.error(f"Failed to list drivers: {e}", exc_info=True)
        raise HTTPException(500, f"Error listing drivers: {str(e)}")


@router.post("/soft-reload")
async def soft_reload(manager=Depends(get_manager)):
    """
    Intelligently reload devices based on config changes.

    Compares current running devices with config.yaml and:
    - Removes devices no longer in config
    - Adds new devices from config
    - Restarts devices whose config has changed
    - Keeps unchanged devices running (no interruption)

    Returns:
        Dict with:
            - status: "ok"
            - added: List of device IDs that were added
            - removed: List of device IDs that were removed
            - restarted: List of device IDs that were restarted
            - unchanged: List of device IDs that remained unchanged
            - devices: List of all device states after reload

    Notes:
        - Much faster than full /reload when few devices changed
        - Preserves device state for unchanged devices
        - WebSocket clients receive updates only for affected devices
    """
    logger.info("Soft-reloading devices from config...")

    try:
        cfg = load_config()

        # Build maps for comparison
        config_devices = {d.id: d for d in cfg.devices}
        running_devices = set(manager.devices.keys())
        config_ids = set(config_devices.keys())

        added = []
        removed = []
        restarted = []
        unchanged = []

        # Remove devices not in config
        to_remove = running_devices - config_ids
        for dev_id in to_remove:
            logger.info(f"Soft-reload: removing '{dev_id}' (not in config)")
            try:
                await manager.stop_polling_device(dev_id)
                await manager.remove_device(dev_id)
                removed.append(dev_id)
            except Exception as e:
                logger.error(f"Failed to remove device '{dev_id}': {e}")

        # Add new devices or restart changed ones
        for dev_id, dev_cfg in config_devices.items():
            if dev_id not in running_devices:
                # New device - add it
                logger.info(f"Soft-reload: adding '{dev_id}'")
                try:
                    await manager.add_device(dev_cfg.id, dev_cfg.driver, dev_cfg.options)
                    await manager.start_polling_device(dev_cfg.id)
                    added.append(dev_id)
                except Exception as e:
                    logger.error(f"Failed to add device '{dev_id}': {e}")
            else:
                # Existing device - check if config changed
                current_dev = manager.devices[dev_id]
                current_options = getattr(current_dev, "options", {})

                # Compare options (simple dict comparison)
                if current_options != dev_cfg.options:
                    logger.info(f"Soft-reload: restarting '{dev_id}' (config changed)")
                    try:
                        await manager.stop_polling_device(dev_id)
                        await manager.remove_device(dev_id)
                        await manager.add_device(dev_cfg.id, dev_cfg.driver, dev_cfg.options)
                        await manager.start_polling_device(dev_cfg.id)
                        restarted.append(dev_id)
                    except Exception as e:
                        logger.error(f"Failed to restart device '{dev_id}': {e}")
                else:
                    unchanged.append(dev_id)

        logger.info(
            f"Soft-reload complete: added={len(added)}, removed={len(removed)}, "
            f"restarted={len(restarted)}, unchanged={len(unchanged)}"
        )

        devices = [d.model_dump() for d in await manager.list_devices()]
        return {
            "status": "ok",
            "added": added,
            "removed": removed,
            "restarted": restarted,
            "unchanged": unchanged,
            "devices": devices,
        }

    except Exception as e:
        logger.error(f"Failed to soft-reload devices: {e}", exc_info=True)
        raise HTTPException(500, f"Error soft-reloading devices: {str(e)}")
