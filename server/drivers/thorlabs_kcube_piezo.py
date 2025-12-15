from __future__ import annotations
import os, asyncio
from typing import Any, Dict, Optional
from ._base import Device, api_device, api_command, api_property
from . import alias

import logging
logger = logging.getLogger(__name__)

@api_device("kcube_piezo")
class ThorlabsKCubePiezo(Device):
    """
    Kinesis KCube Piezo driver via pythonnet. Tested on Windows x64 only.

    Implements:
      - Commands: identify(), enable(), disable(), zero()
      - Properties: voltage (get/set), maximum_voltage (get/set)

    Options expected in config:
      serial: str  (device serial number, e.g., '29250001')
      kinesis_path: str (optional; defaults to env KINESIS_PATH)
      poll_ms: int (optional; default 200)
      simulate: bool (optional; if True, no hardware is used)
    """

    kind = "kcube_piezo"

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        super().__init__(dev_id, options)
        self.serial: str = options.get("serial")
        self.kinesis_path: Optional[str] = options.get("kinesis_path") or os.environ.get("KINESIS_PATH")
        self.poll_ms: int = int(options.get("poll_ms", 200))
        self.simulate: bool = bool(options.get("simulate", False))
        self._dev = None  # .NET device instance
        self._voltage_cache: float = float(options.get("voltage", 0.0))
        self._max_voltage_cache: float = float(options.get("maximum_voltage", 75.0))
        self._min_voltage_cache: float = 0.0
        self._Decimal = None  # bound to System.Decimal after _load_dotnet()
        self._dotnet_loaded = False

    # --- internal: .NET bootstrap ---
    def _load_dotnet(self) -> None:
        if self._dotnet_loaded:
            return
        import clr  # type: ignore
        from pathlib import Path
        if not self.kinesis_path:
            raise RuntimeError("Set KINESIS_PATH or provide options.kinesis_path for Kinesis install directory")
        base = Path(self.kinesis_path)
        dm = base / "Thorlabs.MotionControl.DeviceManagerCLI.dll"
        pz = base / "Thorlabs.MotionControl.KCube.PiezoCLI.dll"
        if not (dm.exists() and pz.exists()):
            raise RuntimeError(f"Kinesis DLLs not found under {base}")
        clr.AddReference(str(dm))
        clr.AddReference(str(pz))
        # Imports after AddReference
        global DeviceManagerCLI, KCubePiezo
        from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
        from Thorlabs.MotionControl.KCube.PiezoCLI import KCubePiezo  # type: ignore
        try:
            from System import Decimal  # type: ignore
            self._Decimal = Decimal
        except Exception:
            self._Decimal = float
        self._dotnet_loaded = True
        logger.info("Kinesis .NET libraries loaded.")

    def _to_decimal(self, value: float):
        return self._Decimal(value) if self._Decimal else float(value)

    async def connect(self) -> None:
        """Connect to the device (or simulate connection)."""
        if self.simulate:
            self._connected = True
            logger.info(f"[SIM] Connected to simulated KCubePiezo {self.serial}")
            return
        self._load_dotnet()
        # Build device list and connect (run in thread to avoid blocking loop)
        def _connect():
            DeviceManagerCLI.BuildDeviceList()
            dev = KCubePiezo.CreateKCubePiezo(self.serial)
            dev.Connect(self.serial)
            dev.WaitForSettingsInitialized(5000)
            dev.StartPolling(self.poll_ms)
            dev.EnableDevice()
            return dev

        loop = asyncio.get_running_loop()
        self._dev = await loop.run_in_executor(None, _connect)
        logger.info(f"Connected to KCubePiezo {self.serial}")
        # Initialize caches from device
        try:
            st = await self.read_state()
            self._voltage_cache = float(st.get("voltage", self._voltage_cache))
            self._max_voltage_cache = float(st.get("maximum_voltage", self._max_voltage_cache))
        except Exception as e:
            logger.warning(f"Failed to read initial state: {e}")
        # Try to read min voltage if supported
        try:
            def _get_min():
                return float(getattr(self._dev, "GetMinOutputVoltage")())
            self._min_voltage_cache = await loop.run_in_executor(None, _get_min)
        except Exception:
            self._min_voltage_cache = 0.0
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from the device (or simulate disconnect)."""
        if self.simulate:
            self._connected = False
            logger.info(f"[SIM] Disconnected from simulated KCubePiezo {self.serial}")
            return
        if not self._dev:
            return
        def _disc():
            try:
                self._dev.StopPolling()
            except Exception:
                pass
            try:
                self._dev.DisableDevice()
            except Exception:
                pass
            try:
                self._dev.Disconnect()
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _disc)
        self._connected = False
        logger.info(f"Disconnected from KCubePiezo {self.serial}")

    async def read_state(self) -> Dict[str, Any]:
        """Read current device state."""
        if self.simulate:
            return {
                "voltage": self._voltage_cache,
                "maximum_voltage": self._max_voltage_cache,
                "connected": True,
            }
        if not self._dev:
            return {"connected": False}

        def _read():
            get_v = getattr(self._dev, "GetOutputVoltage", None)
            get_vmax = getattr(self._dev, "GetMaxOutputVoltage", None)
            v = float(get_v()) if get_v else self._voltage_cache
            vmax = float(get_vmax()) if get_vmax else self._max_voltage_cache
            return {"voltage": v, "maximum_voltage": vmax, "connected": True}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _read)

    async def apply_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Apply parameters (voltage, maximum_voltage) to the device."""
        if self.simulate:
            if "maximum_voltage" in params:
                self._max_voltage_cache = float(params["maximum_voltage"])
            if "voltage" in params:
                v = float(params["voltage"])
                lo, hi = self._min_voltage_cache, self._max_voltage_cache
                self._voltage_cache = max(lo, min(hi, v))
            return await self.read_state()

        if not self._dev:
            raise RuntimeError("Device not connected")

        def _apply():
            # Update max first so subsequent voltage clamp uses new range
            if "maximum_voltage" in params:
                vmax = float(params["maximum_voltage"])
                setter = getattr(self._dev, "SetMaxOutputVoltage", None)
                if not setter:
                    raise RuntimeError("SetMaxOutputVoltage not found")
                setter(self._to_decimal(vmax))
                self._max_voltage_cache = vmax
            # Query current limits
            get_min = getattr(self._dev, "GetMinOutputVoltage", None)
            lo = float(get_min()) if get_min else self._min_voltage_cache
            get_max = getattr(self._dev, "GetMaxOutputVoltage", None)
            hi = float(get_max()) if get_max else self._max_voltage_cache
            # Set voltage with clamping
            if "voltage" in params:
                v = float(params["voltage"])
                v = max(lo, min(hi, v))
                setter = getattr(self._dev, "SetOutputVoltage", None)
                if not setter:
                    raise RuntimeError("SetOutputVoltage not found; verify API method name")
                setter(self._to_decimal(v))
            # Return fresh state
            get_v = getattr(self._dev, "GetOutputVoltage", None)
            cur_v = float(get_v()) if get_v else 0.0
            get_vmax = getattr(self._dev, "GetMaxOutputVoltage", None)
            cur_vmax = float(get_vmax()) if get_vmax else self._max_voltage_cache
            return {"voltage": cur_v, "maximum_voltage": cur_vmax, "connected": True}

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _apply)

    # --- imperative commands (actions) ---
    async def run_command(self, name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        """
        Run a device command (identify, enable, disable, zero).
        Extend this method to add more commands.
        """
        args = args or {}
        if self.simulate:
            if name == "identify":
                logger.info(f"[SIM] identify called")
                return {"ok": True}
            if name == "enable":
                logger.info(f"[SIM] enable called")
                return {"ok": True}
            if name == "disable":
                logger.info(f"[SIM] disable called")
                return {"ok": True}
            if name == "zero":
                logger.info(f"[SIM] zero called")
                self._voltage_cache = 0.0
                return {"ok": True}
            raise RuntimeError(f"Unknown command {name}")

        if not self._dev:
            raise RuntimeError("Device not connected")

        COMMANDS = {
            "identify": "IdentifyDevice",
            "enable": "EnableDevice",
            "disable": "DisableDevice",
            "zero": "SetZero",
            # Add more commands here as needed
        }
        if name not in COMMANDS:
            raise RuntimeError(f"Unknown command {name}")

        def _run():
            meth = getattr(self._dev, COMMANDS[name], None)
            if not meth:
                raise RuntimeError(f"Method {COMMANDS[name]} not found on device")
            return meth()

        loop = asyncio.get_running_loop()
        logger.info(f"Running command {name} on KCubePiezo {self.serial}")
        return await loop.run_in_executor(None, _run)

    # --- helper for future expansion ---
    # def get_supported_commands(self) -> list[str]:
    #     return list(COMMANDS.keys())

"""
# must-haves
kcube.zero() # SetZero
kcube.identify()
kcube.enable()
kcube.disable()

kcube.voltage = 15.0 # GetOutputVoltage/SetOutputVoltage - in System.Decimal 
kcube.maximum_voltage = 75  # in volts (or 100 or 150) GetMaxOutputVoltage/SetMaxOutputVoltage



# nice-to-have
kcube.step_down()
kcube.step_up()

kcube.control.loop_mode = "open_loop" # or "closed_loop"
kcube.control.proportional_gain = 100
kcube.control.integral_gain = 20

kcube.control.voltage_step_size = 0.1  # in volts
kcube.control.percentage_step_size = 0.1  # in percent

kcube.drive_input = "external_SMA_signal" # or channel_1 or channel_2
kcube.wheel_mode = "adjust_voltage" # or "jog_voltage" or "set_voltage"
kcube.wheel_direction = "forward" # or "reverse"
kcube.voltage_adjust_rate = "low" # or "medium" or "high"

kcube.display_intensity_percent = 0.5
kcube.display_dim_on_inactivity = True
kcube.display_timeout_minutes = 60  # in minutes
kcube.display_dimmed_intensity_percent = 0.2

kcube.input = "sw+wheel" # sw or "sw+external"
kcube.io_mode_1 = "disabled" # or "digital_input" or "trigger_input_jog_up" or "trigger_input_jog_down" or "digital_output" 
kcube.io_polarity_1 = "active_high" # or "active_low"
kcube.io_mode_2 = "disabled"
kcube.io_polarity_2 = "active_high"
"""