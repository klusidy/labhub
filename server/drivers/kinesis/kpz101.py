from __future__ import annotations
import os, asyncio, time
from typing import Any, Dict, Optional
from .._base import Device, api_device, api_command, api_property
from ._kinesis_device import KinesisDevice


import logging

logger = logging.getLogger(__name__)


@api_device("kpz101")
class KPZ101(KinesisDevice):
    """
    KCube piezo driver
    https://www.thorlabs.com/thorcat/ETN/ETN017657-D03.pdf
    """

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        conn = options.get("conn")

        self.serial: str = conn.get("serial")
        self.poll_ms: int = int(conn.get("poll_ms", 200))
        self.simulate: bool = bool(conn.get("simulate", False))
        self._dev = None
        logger.debug("init of KPZ101 dev_id=%s options=%s", dev_id, options)
        super().__init__(dev_id, options, manager)

    # --- internal ---

    async def _call(
        self, fn, *args, **kw
    ):  # to keep it fresh, run everything in a "kinesis" executor thread
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._exec, lambda: fn(*args, **kw))

    def _to_decimal(self, value: float):
        return self.Decimal(value) if self.Decimal else float(value)

    # --- lifecycle ---
    async def connect(self) -> None:
        """Connect to the device (or simulate connection)."""
        if self.simulate:
            self._connected = True
            logger.info(f"[SIM] Connected to simulated KCubePiezo {self.serial}")
            return

        await self._ensure_kinesis_loaded()

        # Build device list and connect (run in thread to avoid blocking loop)
        def _connect():
            self.DeviceManagerCLI.BuildDeviceList()  # DeviceManagerCLI is static for all KinesisDevice instances
            dev = self.KCubePiezo.CreateKCubePiezo(self.serial)
            dev.Connect(self.serial)
            dev.WaitForSettingsInitialized(2000)
            dev.StartPolling(self.poll_ms)
            time.sleep(max(0.25, self.poll_ms / 1000))
            dev.EnableDevice()
            time.sleep(0.25)

            max_voltage = dev.GetMaxOutputVoltage()  # This is stored as a .NET decimal
            dev.SetMaxOutputVoltage(max_voltage)
            return dev

        self._dev = await self._on_device(
            _connect
        )  # TODO: better naming than _on_device

        # def _initialize():
        #     # without this, settingg voltage fails ?! wtf
        #     max_voltage = self._dev.GetMaxOutputVoltage()  # This is stored as a .NET decimal
        #     self._dev.SetMaxOutputVoltage(max_voltage)

        # self._dev = await self._on_device(_initialize)

        self._connected = True

    async def disconnect(self) -> None:
        if self.simulate or not self._dev:
            self._connected = False
            return
        await self._on_device(self._dev.StopPolling)
        await self._on_device(self._dev.DisableDevice)
        await self._on_device(self._dev.Disconnect)
        self._connected = False

    # --- API PROPERTIES ---
    @api_property()
    @property
    def voltage(self) -> float:
        voltage_decimal = self._dev.GetOutputVoltage()
        return self.Decimal.ToDouble(voltage_decimal)

    @voltage.setter
    def voltage(self, value: float) -> None:
        voltage_decimal = self._to_decimal(value)
        self._dev.SetOutputVoltage(voltage_decimal)
        r = self._dev.GetOutputVoltage()

    # --- API COMMANDS ---
    @api_command()
    def identify(self) -> int:
        """Demo command; increments an internal counter and return its value"""
        self._dev.IdentifyDevice()
