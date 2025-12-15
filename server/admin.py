"""
Admin API endpoints.

This module contains administrative endpoints for:
- Reloading devices from config
- Managing logging levels at runtime
- Applying property configurations
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
from typing import Dict, Any

from .schemas import ApplyPropertiesRequest
from .utils import set_level as set_logging_level, get_level as get_logging_level
from .loader import load_config

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
                await manager.start_polling_device(
                    d.id, 500
                )  # TODO: Configurable interval
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
