"""
Example Device Driver Template

This file serves as a template for creating new device drivers.

To create a new driver:
1. Copy this file to drivers/vendor_name/your_device_name.py
2. Rename class to match filename EXACTLY: class your_device_name(Device)
3. Update docstrings and implement device-specific hardware interaction
4. Add entry to config.yaml: driver: vendor_name.your_device_name

Key patterns demonstrated:
- @api_device() decorator (no arguments) registers the driver
- @api_property() creates properties with metadata (min/max/unit/choices)
- @api_command() creates callable commands with type-checked arguments
- @api_data() creates streaming data sources with optional plot specs
- Class name MUST match filename exactly (e.g., example_device.py → class example_device)
"""

from __future__ import annotations
import asyncio
import logging
from typing import List, AsyncIterator, Dict, Any, Optional, TYPE_CHECKING
from .PAX1000LTM import *
import numpy as np
import pyvisa

from ..base import Device, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()  # No arguments - metadata inferred from class
class pax(Device):  # Class name MUST match filename exactly
    """
    Example device that generates configurable waveforms for testing.
    This is a simulated device - it doesn't connect to real hardware.
    For real device examples, see other files in drivers/<vendor> folders.
    """

    # Config template: options that appear in config.yaml when this device is added.
    # The example device needs no connection options.
    config_template = {
        "polling_interval": 1000,
        "serial": "asdf"
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize device instance.

        Args:
            dev_id: Unique device identifier from config.yaml
            options: Full device config dict from config.yaml (includes "driver" key)
            manager: Reference to DeviceManager (provides executor, event bus)

        Notes:
            - Base class stores options, manager, creates _cache, _lock
            - Don't connect to hardware here - use async connect() method
            - Initialize private variables that cache hardware state here
        """
        super().__init__(
            dev_id, options, manager
        )   
        self.polarimeter = None
        self.interval = 0.05
        self.hw_number_of_time_steps = 1000
        # Cached metadata filled on successful connect.
        self.hw_resource = ""
        self.hw_model = ""
        self.hw_serial_number = ""
        self.hw_firmware_version = ""
        # Do include this base class initialization!


    # --- Lifecycle Methods ---------------------------------------------------
    # Override these to manage hardware connections

    def connect(self) -> bool:
        """Either sync or async method to establish connection to HW.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        resource_list = pyvisa.ResourceManager().list_resources()
        if not resource_list:
            print("No devices found!")
            return False
        # Extract the first resource as a bytes string
        resource = (
            resource_list[0].encode("utf-8")
            if isinstance(resource_list[0], str)
            else resource_list[0]
        )

        self.polarimeter = Polarimeter(resource, 9, 0.000000532)  # measureMode:9, wavelength: 532nm
        self.polarimeter.connectDevice()
        if not self.polarimeter.handler.value:
            self.polarimeter = None
            return False

        self.hw_resource = resource.decode("utf-8") if isinstance(resource, bytes) else str(resource)
        self.hw_model = (
            self.polarimeter.modelName.value.decode("utf-8", errors="ignore")
            if self.polarimeter.modelName and self.polarimeter.modelName.value
            else ""
        )
        self.hw_serial_number = (
            self.polarimeter.serialNumber.value.decode("utf-8", errors="ignore")
            if self.polarimeter.serialNumber and self.polarimeter.serialNumber.value
            else ""
        )
        return True

    async def disconnect(self) -> bool:
        if self.polarimeter:
            self.polarimeter.closeDevice()
            self.polarimeter = None
            return True
        return False

    # --- Properties ----------------------------------------------------------
    # Properties represent device state that can be read (and optionally written).
    #
    # Instead of python @property, use @api_property() decorator to signify that
    # a property should be polled and exposed through the API
    # The decorator accepts metadata arguments:
    # - min, max: Numeric bounds for validation
    # - step: Increment step for numeric properties
    # - unit: Unit string (e.g., "V", "s", "Hz")
    # - choices: List of valid string options
    #
    # Under the hood:
    # - polling thread calls the getter periodically
    # - value is cached in self._cache
    # - clients read cached values via API
    # - setters update hardware and cache when called
    # - locking (exclusive access) is handled automatically
    @api_property()
    def polarimeter_resource(self) -> str:
        """Resource (id for connection) of the polarimeter"""
        return self.hw_resource

    @api_property()
    def polarimeter_model(self) -> str:
        """Model of the polarimeter"""
        return self.hw_model

    @api_property()
    def polarimeter_serial_number(self) -> str:
        """Serial number of the polarimeter"""
        return self.hw_serial_number

    @api_property()
    def polarimeter_firmware_version(self) -> str:
        """Version of firmware on the polarimeter"""
        return self.hw_firmware_version
    
    @api_property()
    def polarimeter_wavelength(self) -> float:
        """wavelenght of the polarimeter"""
        if not self.polarimeter:
            return 0.0
        wavelength = c_double()
        lib.TLPAX_getWavelength(self.polarimeter.handler, byref(wavelength))
        return wavelength.value
    
    @polarimeter_wavelength.setter
    def polarimeter_wavelength(self, value: float):
        if not self.polarimeter:
            raise RuntimeError("Polarimeter is not connected")
        self.polarimeter.setWavelength(value)
    
    @api_property(min = 1, max = 9, step= 1)
    def polarimeter_measure_mode(self) -> int:
        if not self.polarimeter:
            return 0
        measure_mode = c_int()
        lib.TLPAX_getMeasurementMode(self.polarimeter.handler, byref(measure_mode))
        return measure_mode.value
    
    @polarimeter_measure_mode.setter
    def polarimeter_measure_mode(self, value: int):
        if not self.polarimeter:
            raise RuntimeError("Polarimeter is not connected")
        self.polarimeter.setMeasureMode(value)
    
    @api_property(min=0.01, max=1.0, step=0.01, unit="s")
    def polarimeter_measurement_interval(self) -> float:
        return self.interval
    
    @polarimeter_measurement_interval.setter
    def polarimeter_measurement_interval(self, value: float) -> None:
        self.interval = value


    @api_property(min=1, max=1_000_000, step=1)
    def number_of_steps(self) -> int:
        """Number of samples to generate"""
        return self.hw_number_of_time_steps

    @number_of_steps.setter
    def number_of_steps(self, value: int):
        self.hw_number_of_time_steps = value


    # --- Commands ------------------------------------------------------------
    # Commands are actions that execute on demand (not polled/cached).
    # Use for operations like: start acquisition, save data, reset device.
    # Use @api_command() decorator to publish commands to API
    # Dont forget to type-annotate arguments and return type!
    #
    # Threading behavior:
    # - Sync commands (def): Automatically run in thread pool, safe for blocking calls
    # - Async commands (async def): Run directly in event loop, must use
    #   await self._run_blocking_in_thread() for any blocking/thread-specific calls
    #
    # Locking: Commands acquire exclusive lock automatically (no collision with properties)
    @api_command()
    def is_connected(self) -> bool:
        """Example command that checks if the device is connected."""
        return self.polarimeter is not None       

    @api_command()
    def hello_world(self, name: str = "World", times: int = 1) -> str:
        """Example command that takes an argument and returns a string."""
        return f"Hello, {name}! This is {self.id}. (Called {times} times)"

    @api_command()
    def long_running_operation(self, duration_s: float) -> str:
        """Example of a long-running command that simulates blocking behavior."""
        import time

        time.sleep(duration_s)  # Simulate blocking SDK call
        return f"Completed long operation of {duration_s} seconds."



# === Additional Notes ========================================================
#
# Threading for Blocking SDK Calls:
# ----------------------------------
# Many hardware SDKs use blocking C functions. To prevent blocking the async
# event loop, wrap these calls:
#
#     value = await self._run_blocking_in_thread(sdk_func, arg1, arg2)
#
# This runs the function in the thread pool executor.
#
# Property vs Command Decision:
# -----------------------------
# - Property: Represents device state (frequency, voltage, mode)
#            Cached value, polled periodically, supports min/max/choices
#            Use when: value can be read back from device
#
# - Command: Triggers an action (start_scan, save_file, reset)
#           Not cached, executes on demand, can return result
#           Use when: operation has side effects or doesn't represent state
#
# Read-Only Properties:
# ---------------------
# Omit .setter decorator to make property read-only.
# Useful for: device serial number, firmware version, capabilities
#
# Device Status and Health:
# -------------------------
# - Base class tracks self._status: "connected", "disconnected", "unhealthy"
# - Override check_status() if device SDK can actively detect disconnection
# - Polling failures automatically mark device unhealthy after 3 errors
#
# Configuration Access:
# ---------------------
# All config.yaml parameters available via self.options dict:
#     serial_num = self.options.get("serial_number")
#     ip = self.options.get("ip_address", "192.168.1.1")
#
# The "driver" field is automatically included in options.
