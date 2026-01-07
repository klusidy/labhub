"""
Thorlabs KIM101 K-Cube Inertial Motor Controller Driver

https://www.thorlabs.com/drawings/1babbca0d1da909e-CB0C236B-E3A6-8D8A-502F4365BA99A6F5/KIM101-KinesisManual.pdf
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
class kim101(KinesisDevice):
    """K-Cube Inertial Motor Controller (KIM101)"""

    _DLL_REQUIREMENTS = {
        "dlls": [
            "Thorlabs.MotionControl.GenericMotorCLI.dll",
            "ThorLabs.MotionControl.KCube.InertialMotorCLI.dll",
        ],
        "imports": {
            "GenericMotorCLI": "Thorlabs.MotionControl.GenericMotorCLI.GenericMotorCLI",
            "MotorDirection": "Thorlabs.MotionControl.GenericMotorCLI.MotorDirection",
            "KCubeInertialMotor": "Thorlabs.MotionControl.KCube.InertialMotorCLI.KCubeInertialMotor",
            "InertialMotorStatus": "Thorlabs.MotionControl.KCube.InertialMotorCLI.InertialMotorStatus",
            "ThorlabsInertialMotorSettings": "Thorlabs.MotionControl.KCube.InertialMotorCLI.ThorlabsInertialMotorSettings",
            "InertialMotorJogMode": "Thorlabs.MotionControl.KCube.InertialMotorCLI.InertialMotorJogMode",
            "InertialMotorJogDirection": "Thorlabs.MotionControl.KCube.InertialMotorCLI.InertialMotorJogDirection",
            "DriveParams": "Thorlabs.MotionControl.KCube.InertialMotorCLI.DriveParams",
        },
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize KIM101 driver.

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
        self._jog_state = None

        logger.debug(f"Initialized KIM101: serial={self.serial}, poll_ms={self.poll_ms}")

    def _init_jog_state(self):
        """Initialize jog state tracking (called after connect)"""
        self._jog_state = {
            "A": {"direction": None, "active": False},
            "B": {"direction": None, "active": False},
        }

    async def connect(self) -> bool:
        """
        Connect to KIM101 device.

        Returns:
            True if connection successful, False otherwise
        """
        await self._ensure_kinesis_loaded()

        def _connect():
            self.DeviceManagerCLI.BuildDeviceList()
            device = self.KCubeInertialMotor.CreateKCubeInertialMotor(self.serial)
            device.Connect(self.serial)
            device.WaitForSettingsInitialized(2000)
            device.StartPolling(self.poll_ms)
            time.sleep(max(0.25, self.poll_ms / 1000))
            device.EnableDevice()
            time.sleep(0.25)

            # Get device settings
            inertial_motor_config = device.GetInertialMotorConfiguration(self.serial)
            dev_settings = self.ThorlabsInertialMotorSettings.GetSettings(
                inertial_motor_config
            )
            return device, dev_settings

        try:
            self._dev, self.dev_settings = await self._run_blocking_in_thread(_connect)
            self._dev.SetSettings(self.dev_settings, True, True)
            self._init_jog_state()
            logger.info(f"{self.id}: Connected to KIM101 {self.serial}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to KIM101 {self.serial}: {e}")
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
            logger.info(f"{self.id}: Disconnected from KIM101 {self.serial}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- Properties ---

    @api_property()
    def channel_A(self) -> int:
        """Position of channel A (steps)"""
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        return self._dev.GetPosition(chan)

    @api_property()
    def channel_B(self) -> int:
        """Position of channel B (steps)"""
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        return self._dev.GetPosition(chan)

    @api_property()
    def channel_A_rate(self) -> int:
        """Step rate for channel A"""
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        return self.dev_settings.Drive.Channel(chan).StepRate

    @channel_A_rate.setter
    def channel_A_rate(self, value: int) -> None:
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        self.dev_settings.Drive.Channel(chan).StepRate = value
        self._dev.SetSettings(self.dev_settings, True, True)

    @api_property()
    def channel_B_rate(self) -> int:
        """Step rate for channel B"""
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        return self.dev_settings.Drive.Channel(chan).StepRate

    @channel_B_rate.setter
    def channel_B_rate(self, value: int) -> None:
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        self.dev_settings.Drive.Channel(chan).StepRate = value
        self._dev.SetSettings(self.dev_settings, True, True)

    # --- Commands ---

    @api_command()
    def identify(self) -> None:
        """Flash device LED to identify physically"""
        self._dev.IdentifyDevice()

    @api_command()
    def home_channel_A(self) -> None:
        """Home channel A (move to zero position)"""
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        self._dev.Home(chan)

    @api_command()
    def home_channel_B(self) -> None:
        """Home channel B (move to zero position)"""
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        self._dev.Home(chan)

    @api_command()
    def zero_channel_A(self) -> None:
        """Set current position of channel A as zero"""
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        self._dev.SetPositionAs(chan, 0)

    @api_command()
    def zero_channel_B(self) -> None:
        """Set current position of channel B as zero"""
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        self._dev.SetPositionAs(chan, 0)

    # TODO: Add jog commands if needed (press/release pattern with events)
