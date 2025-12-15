"""
Properties file loader with recursive fallback support.

This module handles loading and resolving device properties from YAML files
with support for:
- Recursive fallback chains via "default" field
- $READOUT sentinel for reading values from devices
- Circular reference detection
- Maximum depth protection
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, Set, Tuple, List
import yaml

logger = logging.getLogger(__name__)

# Sentinel value for properties that should be read from device
READOUT_SENTINEL = "$READOUT"


class PropertyResolutionError(Exception):
    """Raised when property resolution fails due to circular references or max depth."""
    pass


def load_properties_file(path: Path) -> Dict[str, Any]:
    """
    Load properties.yaml file.

    Args:
        path: Path to properties YAML file

    Returns:
        Dict with device IDs as keys, values are property dicts
        Special key "default" can reference another device ID

    Example:
        {
            "picoscope": {"sampling_frequency": 31250000, "resolution": "$READOUT"},
            "laser_exp1": {"default": "laser_common", "pulse_width": 10},
            "laser_common": {"pulse_width": 5, "power": 100}
        }

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If file is not valid YAML
    """
    if not path.exists():
        raise FileNotFoundError(f"Properties file not found: {path}")

    with open(path, 'r') as f:
        properties = yaml.safe_load(f)

    if not isinstance(properties, dict):
        raise ValueError(f"Properties file must contain a YAML dict, got {type(properties)}")

    return properties


def resolve_properties_for_device(
    dev_id: str,
    all_properties: Dict[str, Any],
    max_depth: int = 10
) -> Tuple[Dict[str, Any], Set[str]]:
    """
    Resolve properties for a device following "default" chain.

    Args:
        dev_id: Device ID to resolve
        all_properties: Full properties dict from file
        max_depth: Maximum recursion depth

    Returns:
        (resolved_props, readout_props)
        - resolved_props: {prop_name: value} (excluding $READOUT)
        - readout_props: Set of prop names marked as $READOUT

    Resolution order:
        1. Follow "default" chain to bottom (depth-first)
        2. Build base dict from deepest default
        3. Apply each level up with dict.update() (later overrides earlier)
        4. Separate $READOUT props into readout set

    Raises:
        PropertyResolutionError: On circular reference or max depth exceeded

    Logging:
        - INFO: Fallback chain for each device
        - WARNING: Circular reference detected
        - WARNING: Max depth exceeded
    """
    # Track visited to detect cycles
    visited = []

    # Build chain by following "default" links
    chain = []
    current_id = dev_id

    while current_id:
        # Check for circular reference
        if current_id in visited:
            chain_str = ' -> '.join(visited + [current_id])
            logger.warning(f"Circular reference detected: {chain_str}")
            raise PropertyResolutionError(
                f"Circular reference in properties for '{dev_id}': {chain_str}"
            )

        # Check max depth
        if len(visited) >= max_depth:
            logger.warning(f"Max depth {max_depth} exceeded for '{dev_id}'")
            raise PropertyResolutionError(
                f"Max depth {max_depth} exceeded resolving properties for '{dev_id}'"
            )

        # Check if device exists in properties
        if current_id not in all_properties:
            if current_id != dev_id:
                # Intermediate default not found
                logger.warning(
                    f"Default '{current_id}' not found for '{dev_id}', stopping chain"
                )
            break

        visited.append(current_id)
        chain.append(current_id)

        # Get properties for this device
        props = all_properties[current_id]
        if not isinstance(props, dict):
            logger.warning(f"Properties for '{current_id}' must be a dict, got {type(props)}")
            break

        # Follow "default" link if it exists
        current_id = props.get("default")

    # If no properties found at all
    if not chain:
        return {}, set()

    # Log the resolution chain
    if len(chain) > 1:
        logger.info(f"Property chain for '{dev_id}': {' -> '.join(reversed(chain))}")
    else:
        logger.info(f"Properties for '{dev_id}': direct (no fallback)")

    # Build resolved dict (bottom-up, later overrides earlier)
    # Start from deepest (last in chain) and work back to original device
    resolved = {}
    for id in reversed(chain):
        props = all_properties[id].copy()
        props.pop("default", None)  # Remove special "default" key
        resolved.update(props)

    # Separate $READOUT props from regular props
    readout_props = {k for k, v in resolved.items() if v == READOUT_SENTINEL}
    regular_props = {k: v for k, v in resolved.items() if v != READOUT_SENTINEL}

    logger.debug(
        f"Resolved '{dev_id}': {len(regular_props)} props, {len(readout_props)} readout"
    )

    return regular_props, readout_props


def load_and_resolve_all(
    path: Path,
    device_ids: List[str],
    max_depth: int = 10
) -> Dict[str, Tuple[Dict[str, Any], Set[str]]]:
    """
    Load properties file and resolve for all device IDs.

    Args:
        path: Path to properties.yaml
        device_ids: List of device IDs to resolve
        max_depth: Maximum recursion depth

    Returns:
        Dict[dev_id] = (resolved_props, readout_props)
        - Devices not in file: empty entry ({}, set())
        - Devices with errors: empty entry ({}, set()) with WARNING logged

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If file is invalid YAML

    Behavior:
        - Logs INFO for each successful resolution
        - Logs WARNING for resolution errors (continues with others)
    """
    # Load the properties file
    all_properties = load_properties_file(path)

    results = {}

    for dev_id in device_ids:
        try:
            resolved_props, readout_props = resolve_properties_for_device(
                dev_id, all_properties, max_depth
            )
            results[dev_id] = (resolved_props, readout_props)

        except PropertyResolutionError as e:
            logger.warning(f"Failed to resolve properties for '{dev_id}': {e}")
            results[dev_id] = ({}, set())

        except Exception as e:
            logger.error(f"Unexpected error resolving properties for '{dev_id}': {e}", exc_info=True)
            results[dev_id] = ({}, set())

    return results