"""
Thorlabs KIM101 K-Cube Inertial Motor Controller Driver

https://www.thorlabs.com/drawings/1babbca0d1da909e-CB0C236B-E3A6-8D8A-502F4365BA99A6F5/KIM101-KinesisManual.pdf
"""

from __future__ import annotations
import asyncio
import time
import logging
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING, Literal

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

        try:
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

            self._dev = device
            self.dev_settings = dev_settings

            self._dev.SetSettings(self.dev_settings, True, True)
            self._init_jog_state()

            return True
        except Exception as e:
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from device and clean up.

        Returns:
            True if disconnect successful, False otherwise
        """
        if not self._dev:
            return True

        try:
            self._dev.StopPolling()
            self._dev.Disconnect()
            return True
        except Exception as e:
            return False

    # --- API PROPERTIES ---
    @api_property()
    def channel_A(self) -> int:
        chan = self.InertialMotorStatus.MotorChannels.Channel1
        return self._dev.GetPosition(chan)

    @api_property()
    def channel_B(self) -> int:
        chan = self.InertialMotorStatus.MotorChannels.Channel2
        return self._dev.GetPosition(chan)

    @api_property()
    def channel_C(self) -> int:
        chan = self.InertialMotorStatus.MotorChannels.Channel3
        return self._dev.GetPosition(chan)

    @api_property()
    def channel_D(self) -> int:
        chan = self.InertialMotorStatus.MotorChannels.Channel4
        return self._dev.GetPosition(chan)

    def get_channel(self, channel):
        d = {
            "A": self.InertialMotorStatus.MotorChannels.Channel1,
            "B": self.InertialMotorStatus.MotorChannels.Channel2,
            "C": self.InertialMotorStatus.MotorChannels.Channel3,
            "D": self.InertialMotorStatus.MotorChannels.Channel4,
        }
        return d[channel]

    # --- API COMMANDS ---
    @api_command()  # TODO HIGH PRIO - ASYNC!!!
    def move_to(self, channel: Literal["A", "B", "C", "D"], position: int) -> None:
        """Moves channel to specified position"""
        ch = self.get_channel(channel)
        new_pos = (
            position  # try int???self.Decimal(position) # TODO OPEN VS CLOSED LOOP
        )
        self._dev.MoveTo(ch, new_pos, 60000)  # 60s timeout TODO - should be async!

    def _init_jog_state(self):
        # one hold flag per channel
        self._hold_flags = {
            self.InertialMotorStatus.MotorChannels.Channel1: threading.Event(),
            self.InertialMotorStatus.MotorChannels.Channel2: threading.Event(),
            self.InertialMotorStatus.MotorChannels.Channel3: threading.Event(),
            self.InertialMotorStatus.MotorChannels.Channel4: threading.Event(),
        }
        self._hold_tasks: Dict[int, asyncio.Task] = {}
        self._move_lock = asyncio.Lock()  # one motion at a time is safest on KIM

    @api_command()
    async def jog(
        self,
        channel: Literal["A", "B", "C", "D"],
        direction: Literal["increase", "decrease"],
    ) -> None:
        """Jogs the selected channel in given direction. Press-releae pattern"""

        ch = self.get_channel(channel)
        dir = (
            self.InertialMotorJogDirection.Increase
            if direction == "increase"
            else self.InertialMotorJogDirection.Decrease
        )

        jog_params = self._dev.GetJogParameters(ch)
        jog_mode = (
            (
                "step"
                if jog_params.JogMode == self.InertialMotorJogMode.Step
                else "continuous"
            ),
        )

        if jog_mode == "step":
            evt = self._hold_flags[ch]
            if evt.is_set():
                return  # already holding
            evt.set()

            async def _repeat_steps():
                # loop runs while key held; each call blocks until single step finishes or times out
                while evt.is_set():
                    # short timeout per step; if too small, bump it
                    await self._on_device(lambda: self._dev.Jog(ch, dir, 2000))
                    # tiny pause between repeats so Stop can catch up
                    await asyncio.sleep(0.01)

            t = asyncio.create_task(_repeat_steps())
            self._hold_tasks[ch] = (
                t  # TODO - SOME SEMI-AUTO MECHANISM TO CALL RELEASE??
            )

        else:  # continuous mode

            def _start():
                # simple no-op callback to complete the signature
                cb = KinesisDevice.Action[KinesisDevice.UInt64](lambda cmd_id: None)
                self._dev.Jog(ch, dir, cb)

            await self._on_device(_start)

        return

    @jog.release()
    async def jog_release(
        self,
        channel: Literal["A", "B", "C", "D"],
        direction: Literal["increase", "decrease"],
    ) -> None:  # same arguments as parent (or add **kwargs?) - TODO
        """Stops the current jog (if any)"""
        ch = self.get_channel(channel)
        # check mode
        jog_params = self._dev.GetJogParameters(ch)
        jog_mode = (
            (
                "step"
                if jog_params.JogMode == self.InertialMotorJogMode.Step
                else "continuous"
            ),
        )

        if jog_mode == "step":
            # stop the repeat loop
            evt = self._hold_flags[ch]
            evt.clear()
            # don't await the task here; it will exit after the current step
        else:
            # Continuous: send Stop
            await self._on_device(lambda: self._dev.Stop(ch))  # or StopImmediate(ch)

    @api_command()  # TODO - prime candidate for composite property...
    def set_jog_parameters(
        self,
        channel: Literal["A", "B", "C", "D"],
        mode: Literal["step", "continuous"] = "step",
        acc: int = 1000,
        rate: int = 500,
        step_fwd: int = 250,
        step_rev: int = 250,
    ) -> dict:
        """Sets common parameters for jogging on a channel"""
        ch = self.get_channel(channel)
        jog_params = self._dev.GetJogParameters(ch)

        if acc:
            jog_params.JogAcceleration = acc
        if mode:
            jog_params.JogMode = (
                self.InertialMotorJogMode.Step
                if mode == "step"
                else self.InertialMotorJogMode.Continuous
            )
        if rate:
            jog_params.JogRate = rate
        if step_fwd:
            jog_params.JogStepFwd = step_fwd
        if step_rev:
            jog_params.JogStepRev = step_rev

        self._dev.SetJogParameters(ch, jog_params)

        # turn back into dictionary
        r = {
            "channel": channel,
            "acc": int(jog_params.JogAcceleration),
            "mode": (
                "step"
                if jog_params.JogMode == self.InertialMotorJogMode.Step
                else "continuous"
            ),
            "rate": int(jog_params.JogRate),
            "step_fwd": int(jog_params.JogStepFwd),
            "step_rev": int(jog_params.JogStepRev),
        }
        return r

    @api_command()
    def set_drive_parameters(
        self,
        channel: Literal["A", "B", "C", "D"],
        max_voltage: int = 112,
        step_rate: int = 500,
        step_acc: int = 1000,
    ) -> dict:
        """Sets drive parameters for a channel"""
        ch = self.get_channel(channel)
        drive_params = self._dev.GetDriveParameters(ch)

        if max_voltage:
            drive_params.MaxVoltage = max_voltage
        if step_rate:
            drive_params.StepRate = step_rate
        if step_acc:
            drive_params.StepAcceleration = step_acc

        self._dev.SetDriveParameters(ch, drive_params)
        r = {
            "channel": channel,
            "max_voltage": drive_params.MaxVoltage,
            "step_rate": drive_params.StepRate,
            "step_acc": drive_params.StepAcceleration,
        }
        return r

    @api_command()
    def zero(
        self, channel: Literal["A", "B", "C", "D"]
    ) -> None:  # TODO HIGH PRIO - ASYNC!!!
        """SetPositionAs(channel, 0)"""
        self._dev.SetPositionAs(self.get_channel(channel), 0)

    @api_command()
    def identify(self) -> int:
        """Blinks display of the device a few times"""
        self._dev.IdentifyDevice()