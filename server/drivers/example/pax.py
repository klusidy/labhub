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
import logging
import threading
import time
from typing import Dict, Any, Optional, TYPE_CHECKING
from .PAX1000LTM import *
import pyvisa
import os

from ..base import Device, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)

DEFAULT_SAVE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "pax")
)


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
        self.polarimeterLTM: Optional[PolarimeterLTM] = None
        self.interval = 0.05
        self.hw_number_of_time_steps = 1000
        self._continuous_measurement_thread = None
        # Cached metadata filled on successful connect.
        self.hw_resource = ""
        self.hw_model = ""
        self.hw_serial_number = ""
        self.alighnment_assistance_active = False
        # Do include this base class initialization!


    # --- Lifecycle Methods ---------------------------------------------------
    # Override these to manage hardware connections

    def connect(self) -> bool:
        """Method to establish connection to the polarimeter.
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
        polarimeter = self.polarimeter
        try:      
            self.polarimeter.connectDevice()
            if not self.polarimeter.handler.value:
                self.polarimeter = None
                return False
        except Exception as exc:
            logger.error(f"Failed to connect to polarimeter: {exc}")
            self.polarimeter = None
            return False

        self.hw_resource = resource.decode("utf-8") if isinstance(resource, bytes) else str(resource)
        self.hw_model = (
            self.polarimeter.modelName.value.decode("utf-8", errors="ignore") # type: ignore
            if self.polarimeter.modelName and self.polarimeter.modelName.value # type: ignore
            else ""
        )

        # PolarimeterLTM expects (handler, sampleStage, ...). We do not use a stage here.
        self.polarimeterLTM = PolarimeterLTM(
            self.polarimeter.handler, # type: ignore
            None,
            0,
            20,
            self.interval,
        )
        return True

    async def disconnect(self) -> bool:
        if self.polarimeter:
            if self.polarimeterLTM:
                self.polarimeterLTM.stop = True
            if self._continuous_measurement_thread and self._continuous_measurement_thread.is_alive():
                self._continuous_measurement_thread.join(timeout=1.0)
            self._continuous_measurement_thread = None
            self.polarimeter.closeDevice()
            self.polarimeter = None
            self.polarimeterLTM = None
            return True
        return False

    async def apply_properties(self, properties: dict) -> dict:
        filtered_properties = {
            name: value
            for name, value in properties.items()
            if name != "polarimeter_measure_time"
        }
        if not filtered_properties:
            return await self.read_state()
        return await super().apply_properties(filtered_properties)

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
    def polarimeter_external_power_connected(self) -> bool:
        """Whether the external power supply is connected."""
        if not self.polarimeter:
            return False
        return self.polarimeter.hasExternalPowerSupply()

    @api_property()
    def last_scan_id(self) -> str:
        """ID of the last scan taken by the polarimeter."""
        if not self.polarimeterLTM:
            return "-1"
        if self.polarimeterLTM.lastestScanID < 256:
            return "No measurements taken yet"
        return str(self.polarimeterLTM.lastestScanID)
    
    @api_property()
    def number_of_measurements_stored(self) -> str:
        """Number of measurements currently stored in the polarimeter's memory."""
        if not self.polarimeterLTM:
            return "-1"
        if self.polarimeterLTM.lastestScanID < 256:
            return "No measurements stored yet"
        return str(self.polarimeterLTM.lastestScanID - 255)
    
    @api_property()
    def latest_measurement(self) -> str:
        """Data of the latest measurement taken by the polarimeter."""
        if not self.polarimeterLTM:
            return "No measurements - device not connected"
        if self.polarimeterLTM.lastestScanID < 256:
            return "No measurements to view"
        return str(self.polarimeterLTM.readFromScanID(int(self.polarimeterLTM.lastestScanID)))
    
    

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
    def run_alignment_assistance(
        self,
        interval: float = 0.1,
        aceptable_alighment: float = 98.0,
        num_of_consecutive_aceptable_values: int = 5,
    ) -> str:
        if not self.polarimeterLTM:
            return "Polarimeter is not connected"

        aceptable_values = 0
        list_of_alighment_values = []
        while aceptable_values < num_of_consecutive_aceptable_values:
            measurementid = self.polarimeterLTM.takeOneMeasurement()
            measurement = self.polarimeterLTM.readFromScanID(measurementid)
            alighment_value = measurement[2] * 100
            if alighment_value >= aceptable_alighment:
                aceptable_values += 1
                list_of_alighment_values.append(round(alighment_value, 2))
            else:
                aceptable_values = 0
                list_of_alighment_values = []
            time.sleep(interval)

        return f"Alignment assistance completed. List of the last {num_of_consecutive_aceptable_values} alignment values: {list_of_alighment_values}"

    @api_command()
    def save_by_measurement_id(
        self,
        overwrite_existing_files: bool = False,
        start_scan_id: int = 255,
        end_scan_id: int = 255,
        filename: str = "measurements.csv",
        filepath: Optional[str] = None,
    ) -> str:
        if not self.polarimeterLTM:
            return "Polarimeter is not connected"
        try:
            normalized_start_scan_id = int(start_scan_id)
            normalized_end_scan_id = int(end_scan_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("start_scan_id and end_scan_id must be integers >= 255") from exc

        if normalized_start_scan_id < 255 or normalized_end_scan_id < 255:
            raise ValueError("start_scan_id and end_scan_id must be >= 255")
        if normalized_start_scan_id > normalized_end_scan_id:
            raise ValueError("start_scan_id must be less than or equal to end_scan_id")

        measurements = []
        for scan_id in range(normalized_start_scan_id, normalized_end_scan_id + 1):
            measurement = self.polarimeterLTM.readFromScanID(scan_id)
            if measurement is not None:
                measurements.append((scan_id, measurement))
        if not measurements:
            return f"No measurements found between scan ID {normalized_start_scan_id} and {normalized_end_scan_id}"

        save_dir = os.path.abspath(filepath) if filepath else DEFAULT_SAVE_DIR
        os.makedirs(save_dir, exist_ok=True)
        if overwrite_existing_files:
            full_path = os.path.join(save_dir, filename)
            overwrite_warning = "file {filename} already existed and was be overwritten. " if overwrite_existing_files else ""
        
        elif not overwrite_existing_files and os.path.exists(os.path.join(save_dir, filename)):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(save_dir, f"{base}_{counter}{ext}")):
                counter += 1
            filename = f"{base}_{counter}{ext}"
            full_path = os.path.join(save_dir, filename)
            overwrite_warning = f"file {filename} already exists. Saving as {filename} instead. "
        
        if os.path.exists(full_path):
            overwrite_warning = f"Warning: existing file was overwritten at {full_path}. "
            logger.warning(overwrite_warning.strip())

        with open(full_path, "w") as f:
            f.write("scan_id,measurement\n")
            for scan_id, measurement in measurements:
                f.write(f"{scan_id},{measurement}\n")

        return (
            f"{overwrite_warning}"
            f"Measurements from scan ID {normalized_start_scan_id} to {normalized_end_scan_id} "
            f"saved to {full_path}"
        )
    @api_command()
    def take_one_measurement(self) -> str:
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"
        measurementid = self.polarimeterLTM.takeOneMeasurement()
        measurement = self.polarimeterLTM.readFromScanID(measurementid)
        return (f"Measurement with id {measurementid} taken. these are the results: {measurement}")
    
    @api_command()
    def long_scan_by_time(
        self,
        measure_time: Optional[float] = None, interval_s: Optional[float] = None, clear_memory: bool = True) -> str:
        error_value: int = 0
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"

        normalized_measure_time: Optional[int] = None
        normalized_interval_s: Optional[float] = None

        if measure_time is not None:
            try:
                normalized_measure_time = int(measure_time)
            except (TypeError, ValueError) as exc:
                raise ValueError("measure_time must be an integer > 0") from exc

        if interval_s is not None:
            try:
                normalized_interval_s = float(interval_s)
            except (TypeError, ValueError) as exc:
                raise ValueError("interval_s must be a number > 0") from exc

        if normalized_measure_time is not None and normalized_measure_time <= error_value:
            raise ValueError("measure_time must be > 0")
        if normalized_interval_s is not None and normalized_interval_s <= error_value:
            raise ValueError("interval_s must be > 0")

        if isinstance(clear_memory, str):
            clear_memory = clear_memory.strip().lower() not in {"0", "false", "no", "off"}

        if normalized_measure_time is not None:
            self.polarimeterLTM.measureTime = normalized_measure_time
        if normalized_interval_s is not None:
            self.interval = normalized_interval_s
            self.polarimeterLTM.interval = normalized_interval_s
        else:
            # Keep PolarimeterLTM and device property in sync when command is called.
            self.polarimeterLTM.interval = float(self.interval)

        if clear_memory:
            self.polarimeterLTM.clearMemory()

        started_at = time.perf_counter()
        self.polarimeterLTM.measure()
        elapsed = time.perf_counter() - started_at

        latest_scan_id = self.polarimeterLTM.lastestScanID
        latest_measurement = self.polarimeterLTM.readFromScanID(latest_scan_id)

        return (
            "Long scan completed. "
            f"measure_time={self.polarimeterLTM.measureTime:.3f}s, "
            f"interval={self.polarimeterLTM.interval:.3f}s, "
            f"elapsed={elapsed:.3f}s, "
            f"latest_scan_id={latest_scan_id}, "
            f"latest_measurement={latest_measurement}"
        )
    
    @api_command()
    def long_scan_by_steps(self, num_of_steps: int, measurement_interval : float, clear_memory: bool = True) -> str:
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"
        try:
            normalized_num_of_steps = int(num_of_steps)
        except (TypeError, ValueError) as exc:
            raise ValueError("num_of_steps must be an integer > 0") from exc

        try:
            normalized_measurement_interval = float(measurement_interval)
        except (TypeError, ValueError) as exc:
            raise ValueError("measurement_interval must be a number > 0") from exc

        if normalized_num_of_steps <= 0:
            raise ValueError("num_of_steps must be > 0")
        if normalized_measurement_interval <= 0:
            raise ValueError("measurement_interval must be > 0")

        total_measure_time = normalized_num_of_steps * normalized_measurement_interval

        self.hw_number_of_time_steps = normalized_num_of_steps
        self.interval = normalized_measurement_interval
        self.polarimeterLTM.interval = self.interval

        if clear_memory:
            self.polarimeterLTM.clearMemory()

        previous_scan_id = self.polarimeterLTM.lastestScanID
        acquired_steps = 0
        poll_delay = min(self.interval / 10, 0.01)
        step_timeout = max(self.interval * 3, 0.2)

        started_at = time.perf_counter()
        next_step_at = started_at
        while acquired_steps < normalized_num_of_steps:
            deadline = time.perf_counter() + step_timeout
            while time.perf_counter() < deadline:
                current_scan_id = self.polarimeterLTM.takeOneMeasurement()
                if current_scan_id > previous_scan_id:
                    previous_scan_id = current_scan_id
                    acquired_steps += 1
                    break
                time.sleep(poll_delay)
            else:
                elapsed = time.perf_counter() - started_at
                return (
                    "Long scan timed out before collecting all requested measurements. "
                    f"requested_steps={normalized_num_of_steps}, "
                    f"acquired_steps={acquired_steps}, "
                    f"interval={self.interval:.3f}s, "
                    f"elapsed={elapsed:.3f}s"
                )

            # Keep effective acquisition cadence close to requested interval.
            next_step_at += normalized_measurement_interval
            remaining = next_step_at - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)

        elapsed = time.perf_counter() - started_at

        latest_scan_id = self.polarimeterLTM.lastestScanID
        latest_measurement = self.polarimeterLTM.readFromScanID(latest_scan_id)

        return (
            "Long scan completed. "
            f"num_of_steps={normalized_num_of_steps}, "
            f"acquired_steps={acquired_steps}, "
            f"measure_time={total_measure_time:.3f}s, "
            f"interval={self.interval:.3f}s, "
            f"elapsed={elapsed:.3f}s, "
            f"latest_scan_id={latest_scan_id}, "
            f"latest_measurement={latest_measurement}"
        )
        

    @api_command()
    def read_measurement_by_id(self, scan_id: int) -> str:
        """Read a specific measurement from the polarimeter's memory by scan ID."""
        if not self.polarimeterLTM:
            return "Polarimeter is not connected"
        try:
            normalized_scan_id = int(scan_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("scan_id must be an integer >= 255") from exc

        if normalized_scan_id < 255:
            raise ValueError("scan_id must be >= 255")

        measurement = self.polarimeterLTM.readFromScanID(normalized_scan_id)
        if measurement is None:
            return f"No measurement found with scan ID {normalized_scan_id}"
        return f"Measurement for scan ID {normalized_scan_id}: {measurement}"
    
    @api_command()
    def erase_all_measurements(self) -> str:
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"
        self.polarimeterLTM.clearMemory()
        return "All measurements erased from the device."
    
    @api_command()
    def start_continuous_measurement(self, interval: float = 0.1) -> str:
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"

        if self._continuous_measurement_thread and self._continuous_measurement_thread.is_alive():
            return "Continuous measurement is already running"

        self.polarimeterLTM.stop = False
        self._continuous_measurement_thread = threading.Thread(
            target=self.polarimeterLTM.measure_until_stopped,
            args=(interval,),
            daemon=True,
        )
        self._continuous_measurement_thread.start()
        return "Continuous measurement started."
    
    @api_command()
    def stop_continuous_measurement(self) -> str:
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"

        if not self._continuous_measurement_thread or not self._continuous_measurement_thread.is_alive():
            return "Continuous measurement is not running"

        self.polarimeterLTM.stop = True
        self._continuous_measurement_thread.join(timeout=max(self.interval * 2, 1.0))
        if self._continuous_measurement_thread.is_alive():
            return "Stop requested, but continuous measurement is still shutting down"

        self._continuous_measurement_thread = None
        return "Continuous measurement stopped."
    
    @api_command()
    def delete_last_scan(self) -> str:
        """ Delete the most recent scan from the polarimeter's memory. """
        if not self.polarimeter or not self.polarimeterLTM:
            return "Polarimeter is not connected"
        if self.polarimeterLTM.lastestScanID < 256:
            return "No measurements to delete"
        self.polarimeterLTM.delete_last_scan()
        deleted_scan_id = self.polarimeterLTM.lastestScanID + 1
        return f"Deleted scan with ID {deleted_scan_id} from memory."


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
