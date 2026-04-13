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

import numpy as np

from ..base import Device, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()  # No arguments - metadata inferred from class
class chameleon(Device):  # Class name MUST match filename exactly
    """
    Example device that generates configurable waveforms for testing.
    This is a simulated device - it doesn't connect to real hardware.
    For real device examples, see other files in drivers/<vendor> folders.
    """

    # Config template: options that appear in config.yaml when this device is added.
    # The example device needs no connection options.
    config_template = {
        "polling_interval": 1000,
        "bitfile": "chameleon.bit",
        "IP": "192.168.1.101",
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
        )  # Do include this base class initialization!

        # Initialize whatever internal variables are needed
        # Here, we simulate HW state with them
        self.hw_time_step = 0.01  # Would be read from device in real driver
        self.hw_number_of_time_steps = 1000
        self.hw_noise = False
        self.hw_wave_type = "sin"

    # --- Lifecycle Methods ---------------------------------------------------
    # Override these to manage hardware connections

    def connect(self) -> None:
        """Either sync or async method to establish connection to HW.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        return True  # For real hardware, implement connection logic here¨

    async def disconnect(self) -> None:
        """
        Either sync or async method to safely terminate connection to HW.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        return True

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
    @api_property(min=1e-4, max=10.0, step=0.001, unit="s")
    def time_step(self) -> float:
        """
        Sampling interval for generated data.

        Getter returns cached value (fast, no hardware access).
        For real devices, this would return the last value read from hardware.
        """
        return self.hw_time_step

    @time_step.setter
    def time_step(self, value: float):
        """
        Set sampling interval.

        For real hardware, this would:
        1. Call SDK function to configure device
        2. Update private cache variable

        Example (from ps5000a.py):
            ps.ps5000aSetTimebase(self.chandle, timebase, ...)
            self._time_interval = value  # Update cache

        Note: Base class handles validation (min/max/choices from decorator)
        """
        self.hw_time_step = value

    @api_property(min=1, max=1_000_000, step=10)
    def number_of_time_steps(self) -> int:
        """Number of samples to generate"""
        return self.hw_number_of_time_steps

    @number_of_time_steps.setter
    def number_of_time_steps(self, value: int):
        self.hw_number_of_time_steps = value

    @api_property()
    def noise(self) -> bool:
        """Add random noise to waveform"""
        return self.hw_noise

    @noise.setter
    def noise(self, value: bool):
        self.hw_noise = value

    @api_property(choices=["sin", "square"])
    def wave_type(self) -> str:
        """Waveform type"""
        return self.hw_wave_type

    @wave_type.setter
    def wave_type(self, value: str):
        self.hw_wave_type = value

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
    def get_timestamps(self) -> List[float]:
        """
        Generate timestamp array for current configuration.

        This is a sync command - it will automatically run in a thread pool,
        so it's safe to make blocking SDK calls directly here.

        For async commands, you must wrap blocking calls:
            async def my_async_command(self, arg: int) -> str:
                result = await self._run_blocking_in_thread(sdk_function, arg)
                return result
        """
        dt = self.time_step
        ts = np.arange(self.number_of_time_steps) * dt
        return ts.tolist()

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

    # --- Data Sources --------------------------------------------------------
    # Data sources are async generators that yield Frame dicts for streaming.
    # They run in background tasks managed by the DataSource class.

    @api_data()
    async def demo_wave(self) -> AsyncIterator[Frame]:
        """
        Generate continuous waveform stream.

        Yields Frame dicts with structure:
            {
                "series": [
                    {"name": "Channel A", "data": [y1, y2, ...]},
                    {"name": "Channel B", "data": [y1, y2, ...]},
                ]
            }

        Important:
        - Use await asyncio.sleep() to control emission rate
        - Clean up hardware resources in finally block
        - Use self._run_blocking_in_thread() for SDK calls
        """
        try:
            logger.debug(f"{self.id}: demo_wave starting")

            while True:
                # Generate waveform
                ts = np.arange(self.number_of_time_steps) * self.time_step
                wave = np.sin(2 * np.pi * ts)

                if self.wave_type == "square":
                    wave = np.sign(wave)

                if self.noise:
                    wave = wave + (np.random.rand(len(wave)) - 0.5) * 0.1

                # Yield frame to all subscribers
                yield {
                    "series": [
                        {"name": "Waveform", "data": wave.tolist()},
                    ]
                }

                # Control emission rate
                await asyncio.sleep(0.05)

        finally:
            logger.debug(f"{self.id}: demo_wave stopped")
            # For real hardware: stop acquisition, release buffers

    @demo_wave.plot()
    def demo_plot(self) -> Dict[str, Any]:
        """
        Define plot specification for demo_wave.

        Called once when client requests plot config.
        Returns dict with title, axis labels, and x-values.
        """
        return {
            "title": "Example Waveform",
            "x-label": "Time (s)",
            "y-label": "Amplitude (V)",
            "x-values": self.get_timestamps(),
        }


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
