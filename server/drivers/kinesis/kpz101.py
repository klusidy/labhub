"""
Thorlabs KPZ101 K-Cube Piezo Controller Driver

https://www.thorlabs.com/thorcat/ETN/ETN017657-D03.pdf
"""

from __future__ import annotations
import time
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..base import api_device, api_command, api_property
from ._kinesis_device import KinesisDevice

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class kpz101(KinesisDevice):
    """KCube Piezo Controller (KPZ101)"""

    # Declare DLL requirements for this device
    _DLL_REQUIREMENTS = {
        "dlls": [
            "Thorlabs.MotionControl.KCube.PiezoCLI.dll",
        ],
        "imports": {
            "KCubePiezo": "Thorlabs.MotionControl.KCube.PiezoCLI.KCubePiezo",
        },
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize KPZ101 driver.

        Config options:
            serial: Device serial number (required)
            poll_ms: Polling interval in milliseconds (default: 200)
            kinesis_path: Path to Kinesis DLLs (or set KINESIS_PATH env var)
        """
        super().__init__(dev_id, options, manager)

        # Extract connection parameters
        self.serial: str = options.get("serial", "")
        self.poll_ms: int = int(options.get("poll_ms", 200))

        if not self.serial:
            raise ValueError(f"Device '{dev_id}': serial number required")

        # Device handle (set during connect())
        self._dev = None
        self._voltage_input = 0

        logger.debug(f"Initialized KPZ101: serial={self.serial}, poll_ms={self.poll_ms}")

    async def connect(self) -> bool:
        """
        Connect to KPZ101 device.

        Returns:
            True if connection successful, False otherwise
        """
        # Ensure .NET DLLs are loaded
        await self._ensure_kinesis_loaded()

        # Connect to device on Kinesis thread
        try: 
            self.DeviceManagerCLI.BuildDeviceList()
            self._dev = self.KCubePiezo.CreateKCubePiezo(self.serial)
            self._dev.Connect(self.serial)
            self._dev.WaitForSettingsInitialized(2000)
            self._dev.StartPolling(self.poll_ms)
            time.sleep(max(0.25, self.poll_ms / 1000))
            self._dev.EnableDevice()
            time.sleep(0.25)

            # Initialize voltage settings
            max_voltage = self._dev.GetMaxOutputVoltage()
            self._dev.SetMaxOutputVoltage(max_voltage)
            logger.info(f"{self.id}: Connected to KPZ101 {self.serial}")
            return True
        except:
            logger.error(f"{self.id}: Failed to connect to KPZ101 {self.serial}: {e}")
            return False
        
            
    async def disconnect(self) -> bool:
        """
        Disconnect from device and clean up.

        Returns:
            True if disconnect successful, False otherwise
        """
        if not self._dev:
            return True

        try:
            await self._run_blocking_in_thread(self._dev.StopPolling)
            await self._run_blocking_in_thread(self._dev.DisableDevice)
            await self._run_blocking_in_thread(self._dev.Disconnect)
            logger.info(f"{self.id}: Disconnected from KPZ101 {self.serial}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- Properties ---

    @api_property(min=0.0, max=150.0, unit="V")
    def voltage_input(self) -> float:
        """Output voltage in volts"""
        return self._voltage_input

    @voltage_input.setter
    def voltage_input(self, value: float) -> None:
        voltage_decimal = self._to_decimal(value)
        self._dev.SetOutputVoltage(voltage_decimal)
        self._voltage_input = value



    @api_property(min=0.0, max=150.0, unit="V")
    def voltage(self) -> float:
        """Output voltage in volts"""
        voltage_decimal = self._dev.GetOutputVoltage()
        return self.Decimal.ToDouble(voltage_decimal)

    # @voltage.setter
    # def voltage(self, value: float) -> None:
    #     voltage_decimal = self._to_decimal(value)
    #     self._dev.SetOutputVoltage(voltage_decimal)

    # --- Commands ---

    @api_command()
    def identify(self) -> None:
        """Flash device LED to identify physically"""
        self._dev.IdentifyDevice()
