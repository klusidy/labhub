# hub_app/drivers/example_device.py
from __future__ import annotations
import asyncio, math, random
from typing import Any, Dict, Optional, List, AsyncIterator
import numpy as np
import serial
import time
from ..base import Device, api_device, api_command, api_property, api_data, Frame


@api_device("tgf4000")
class TGF4000(Device):
    """
    TGF4000 signal generator
    """

    kind = "tgf4000"  # todo -keep this or replace with alias?

    # -------------------------------------------------------------------------

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        self.PORT = options.get(
            "port", "COM8"
        )  # <-- change to your COM port (e.g., "/dev/ttyACM0" on Linux)
        self.BAUD = options.get(
            "baud", 115200
        )  # CDC ignores baud, but pyserial wants a value
        self.ser = None
        super().__init__(dev_id, options)

    # --- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:

        def _connect():
            ser = serial.Serial(
                port=self.PORT,
                baudrate=self.BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,  # seconds
                write_timeout=1.0,
            )
            time.sleep(0.1)
            return ser

        self.ser = await self._on_device(_connect)

    async def disconnect(self) -> None:
        def _disconnect():
            self.ser.close()

        await self._on_device(_disconnect)

    # -- API PROPERTIES

    # @api_property(min=1e-4, max=10.0, default=0.01, step=0.001) # TODO - ADD UNITS
    # @property
    # def frequency(self) -> float:
    #     """Sampling interval for generated data (seconds)"""
    #     return self._freq

    # @frequency.setter
    # def frequency(self, value:float): # todo when value is dict, update min/max/default etc
    #     self._freq = value

    @api_command()
    def write_cmd(self, command: str) -> bool:
        """Sends command to the device write_cmd(ser, "CHN1")
        write_cmd(ser, "WAVE SINE")
        write_cmd(ser, "FREQ 8000000")
        write_cmd(ser, "AMPL 0.5")
        write_cmd(ser, "DCOFFS 0")
        write_cmd(ser, "OUTPUT OFF")"""
        if not self.ser:
            return False
        if not command.endswith("\n"):
            command += "\n"
        self.ser.write(command.encode("ascii"))
        return True

    @api_command()
    def query(self, command: str) -> Any:
        """Send a command and wait for response"""
        if not self.ser:
            return ""
        self.write_cmd(command)
        resp = self.ser.read_until(b"\n").decode("ascii").rstrip("\r\n")
        return resp

    @api_command()
    def check_errors(self) -> List[str]:
        # Standard events and error registers (see manual’s Status reporting)
        esr = self.query("*ESR?")
        # Execution / Query error registers (implementation described in manual)
        # These commands are 'EER?' and 'QER?' in the status model section.
        try:
            eer = self.query("EER?")
        except Exception:
            eer = "?"
        try:
            qer = self.query("QER?")
        except Exception:
            qer = "?"
        return [esr, eer, qer]
