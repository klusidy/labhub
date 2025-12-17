"""
Driver Loading System

Dynamically imports device drivers based on config.yaml driver identifiers.

Architecture:
- Driver identifier format: "vendor_name.device_name" (e.g., "example.example_device")
- Maps to file: drivers/vendor_name/device_name.py
- Class name must match filename EXACTLY (e.g., device_name.py → class device_name)
- Class must be decorated with @api_device()

Usage:
    # In config.yaml:
    devices:
      - id: my_device
        driver: vendor_name.device_name

    # Driver loader automatically imports:
    from drivers.vendor_name.device_name import device_name
"""

from __future__ import annotations
import importlib
import logging
from typing import Type

from .base import Device

logger = logging.getLogger("labhub.device_manager.drivers")


# Track already loaded drivers to avoid redundant imports
ALREADY_LOADED = dict()


def load_driver_class(driver_identifier: str) -> Type[Device]:
    """
    Dynamically load driver class from identifier.

    Args:
        driver_identifier: Driver path (e.g., "example.example_device")

    Returns:
        Device class ready for instantiation

    Raises:
        ValueError: Invalid driver identifier format
        ImportError: Module not found or failed to import
        KeyError: Class not found in module (wrong class name or missing @api_device?)

    Examples:
        >>> cls = load_driver_class("example.example_device")
        >>> device = await cls.create("my_dev", {...})

    Notes:
        - Triggers module import on first call (registers class in ALIASES)
        - Subsequent calls return cached class from ALIASES
        - Class name must match filename exactly (no case conversion)
    """
    # Parse driver identifier
    parts = driver_identifier.split(".")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid driver identifier '{driver_identifier}'. "
            f"Expected format: 'vendor.device' (e.g., 'example.example_device')"
        )

    vendor, device_name = parts
    module_path = f"server.drivers.{vendor}.{device_name}"
    expected_class_name = device_name  # Shall match filename exactly

    # Check if already loaded
    if module_path in ALREADY_LOADED:
        logger.debug(f"Driver '{driver_identifier}' already loaded from cache")
        return ALREADY_LOADED[module_path]

    # Dynamic import (triggers @api_device decorator which registers class in ALIASES)
    if module_path not in ALREADY_LOADED:
        logger.info(f"Loading driver '{driver_identifier}' from {module_path}")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, expected_class_name)
            ALREADY_LOADED[module_path] = cls
        except ImportError as e:
            raise ImportError(
                f"Failed to import driver module '{module_path}': {e}\n"
                f"Expected file: server/drivers/{vendor}/{device_name}.py"
            ) from e

    # # Find class in ALREADY_LOADED (should be registered by @api_device decorator)
    # # this was formerly using ALIASES
    # if expected_class_name not in ALREADY_LOADED:
    #     available = ", ".join(sorted(ALREADY_LOADED.keys()))
    #     raise KeyError(
    #         f"Driver class '{expected_class_name}' not found in module '{module_path}'.\n"
    #         f"Ensure:\n"
    #         f"  1. Class is decorated with @api_device()\n"
    #         f"  2. Class name matches filename exactly: class {expected_class_name}(Device)\n"
    #         f"  3. File path: drivers/{vendor}/{device_name}.py\n"
    #         f"Available classes: {available or '(none loaded yet)'}"
    #     )

    logger.debug(f"Loaded driver '{driver_identifier}' -> {expected_class_name}")
    return ALREADY_LOADED[module_path]


def get(driver_identifier: str) -> Type[Device]:
    """
    Get driver class by identifier.

    This is the main entry point used by DeviceManager.

    Args:
        driver_identifier: Driver path (e.g., "example.example_device")

    Returns:
        Device class

    Raises:
        ValueError: Invalid driver identifier format
        ImportError: Driver module not found
        KeyError: Driver class not found in module
    """
    return load_driver_class(driver_identifier)


# For backwards compatibility and direct access
__all__ = ["Device", "get", "load_driver_class"]
