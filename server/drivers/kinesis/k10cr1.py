"""
Thorlabs K10CR1 Stepper Motor Rotation Mount Driver
"""

from __future__ import annotations
import time
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING, Literal

from ..base import api_device, api_command, api_property
from ._kinesis_device import KinesisDevice

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class k10cr1(KinesisDevice):
    """Stepper Motor Rotation Mount (K10CR1)"""

    config_template = {
        "serial": "55000001",
        "poll_ms": 200,
        "kinesis_path": "C:/Program Files/Thorlabs/Kinesis",
        "polling_interval": 1000,
    }

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
        value_decimal = self._to_decimal(value)
        self._dev.MoveTo(value_decimal, 60000)

    # --- Commands ---

    @api_command()
    def move_to(
        self, value: float
    ) -> None:  # todo when value is dict, update min/max/default etc
        conv = self._dev.UnitConverter
        value_decimal = self._to_decimal(value)
        self._dev.MoveTo(
            value_decimal, 60000
        )  # TODO - should be async? (properties are not async...)
        return value
    


    @api_command()
    def drive_up(self, velocity: float) -> None:
        fwd = self.MotorDirection.Forward  # todo add support for veocity!!
        self._dev.MoveContinuous(fwd)
        return

    @api_command()
    def drive_down(self, velocity: float) -> None:
        bck = self.MotorDirection.Backward
        self._dev.MoveContinuous(bck)
        return

    @drive_up.release()
    @drive_down.release()
    def drive_up_release(self, **kwargs) -> None:
        self._dev.StopImmediate()
        return
    

    @api_command()
    def home(self) -> None:
        self._dev.Home(60000)
        return
    

    @api_command()
    def set_jog_parameters(
        self,
        jog_mode: Literal["single_step", "continuous_held", "continuous_unheld"],
        step_size: float = 5,
        acceleration: float = 15,
        max_velocity: float = 15,
    ) -> dict:
        # min_velocity: float = 5)-> dict :#step_mode: str, max_velocity:int, acc:int) -> dict:
        logger.debug("inside set_jog_parameters")
        jog_params = self._dev.GetJogParams()
        if step_size:
            jog_params.StepSize = self._to_decimal(step_size)
        if acceleration:
            jog_params.VelocityParams.Acceleration = self._to_decimal(acceleration)
        if max_velocity:
            jog_params.VelocityParams.MaxVelocity = self._to_decimal(max_velocity)
        if jog_mode == "single_step":
            jog_params.JogMode = jog_params.JogModes.SingleStep
        elif jog_mode == "continuous_held":
            jog_params.JogMode = jog_params.JogModes.ContinuousHeld
        elif jog_mode == "continuous_unheld":
            jog_params.JogMode = jog_params.JogModes.ContinuousUnheld

        # self._dev.SetJogParams_DeviceUnit TODO - UNITS!!!
        self._dev.SetJogParams(jog_params)

        # if min_velocity:
        #    jog_params.VelocityParams.MinVelocity = self._to_decimal(min_velocity)

        r = {  # todo -read out from actual params
            "step_size": self.Decimal.ToDouble(jog_params.StepSize),
            "acceleration": self.Decimal.ToDouble(
                jog_params.VelocityParams.Acceleration
            ),
            "max_velocity": self.Decimal.ToDouble(
                jog_params.VelocityParams.MaxVelocity
            ),
            "jog_mode": (
                "single_step"
                if jog_params.JogMode == jog_params.JogModes.SingleStep
                else (
                    "continuous_held"
                    if jog_params.JogMode == jog_params.JogModes.ContinuousHeld
                    else (
                        "continuous_unheld"
                        if jog_params.JogMode == jog_params.JogModes.ContinuousUnheld
                        else "unknown"
                    )
                )
            ),
        }
        return r

