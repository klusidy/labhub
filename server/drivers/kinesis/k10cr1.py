"""
Thorlabs K10CR1 Stepper Motor Rotation Mount Driver
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
class k10cr1(KinesisDevice):
    """Stepper Motor Rotation Mount (K10CR1)"""

    _DLL_REQUIREMENTS = {
        "dlls": [
            "Thorlabs.MotionControl.GenericMotorCLI.dll",
            "ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll",
        ],
        "imports": {
            "IntegratedStepperMotorsCLI": "Thorlabs.MotionControl.IntegratedStepperMotorsCLI",
            "MotorDirection": "Thorlabs.MotionControl.GenericMotorCLI.MotorDirection",
        },
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize K10CR1 driver.

        Config options:
            serial: Device serial number (required)
            poll_ms: Polling interval in milliseconds (default: 200)
            kinesis_path: Path to Kinesis DLLs (or set KINESIS_PATH env var)
        """
        super().__init__(dev_id, options, manager)

        self.serial: str = options.get("serial", "")
        self.poll_ms: int = int(options.get("poll_ms", 200))

        if not self.serial:
            raise ValueError(f"Device '{dev_id}': serial number required")

        self._dev = None
        self.dev_settings = None

        logger.debug(f"Initialized K10CR1: serial={self.serial}, poll_ms={self.poll_ms}")

    async def connect(self) -> bool:
        """
        Connect to K10CR1 device.

        Returns:
            True if connection successful, False otherwise
        """
        await self._ensure_kinesis_loaded()

        def _connect():
            self.DeviceManagerCLI.BuildDeviceList()
            device = self.IntegratedStepperMotorsCLI.CageRotator.CreateCageRotator(
                self.serial
            )
            device.Connect(self.serial)
            device.WaitForSettingsInitialized(2000)
            device.StartPolling(self.poll_ms)
            time.sleep(max(0.25, self.poll_ms / 1000))
            device.EnableDevice()
            time.sleep(0.25)
            return device

        try:
            self._dev = await self._run_blocking_in_thread(_connect)

            # Load motor configuration
            self.dev_settings = self._dev.LoadMotorConfiguration(self.serial)
            # Access current device settings (from Thorlabs examples)
            _ = self._dev.MotorDeviceSettings
            self.dev_settings.UpdateCurrentConfiguration()

            logger.info(f"{self.id}: Connected to K10CR1 {self.serial}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to K10CR1 {self.serial}: {e}")
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
            await self._run_blocking_in_thread(self._dev.Disconnect)
            logger.info(f"{self.id}: Disconnected from K10CR1 {self.serial}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- Properties ---

    @api_property(unit="deg")
    def position(self) -> float:
        """Position in real-world units (degrees)"""
        conv = self._dev.UnitConverter
        pos = self._dev.GetPositionCounter()
        pos_dec = self._to_decimal(pos)
        real = conv.DeviceUnitToReal(pos_dec, conv.UnitType.Length)
        return float(self.Decimal.ToDouble(real))

    @position.setter
    def position(self, value: float) -> None:
        conv = self._dev.UnitConverter
        value_dec = self._to_decimal(value)
        device_unit = conv.RealToDeviceUnit(value_dec, conv.UnitType.Length)
        self._dev.SetMoveAbsolutePosition(device_unit)
        self._dev.MoveAbsolute(5000)  # 5 second timeout

    # --- Commands ---

    @api_command()
    def identify(self) -> None:
        """Flash device LED to identify physically"""
        self._dev.IdentifyDevice()

    @api_command()
    def home(self) -> None:
        """Home the device (move to zero position)"""
        self._dev.Home(5000)  # 5 second timeout

    @api_command()
    def zero(self) -> None:
        """Set current position as zero"""
        self._dev.SetPositionAs(0)

    @api_command()
    def move_relative(self, distance: float) -> None:
        """
        Move relative to current position.

        Args:
            distance: Distance to move in degrees
        """
        conv = self._dev.UnitConverter
        distance_dec = self._to_decimal(distance)
        device_unit = conv.RealToDeviceUnit(distance_dec, conv.UnitType.Length)
        self._dev.SetMoveRelativeDistance(device_unit)
        self._dev.MoveRelative(5000)  # 5 second timeout

    @api_command()
    def stop(self) -> None:
        """Stop any ongoing motion"""
        self._dev.Stop(500)  # 500ms timeout
