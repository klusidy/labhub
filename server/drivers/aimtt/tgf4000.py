"""Aim-TTi TGF4000 Series Function Generator Driver"""
from __future__ import annotations
import serial
import time
import logging
from typing import Any, Dict, Optional, List, TYPE_CHECKING

from ..base import Device, api_device, api_command

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class tgf4000(Device):
    """Aim-TTi TGF4000 series function generator"""

    config_template = {
        "port": "COM8",
        "baud": 115200,
        "polling_interval": 1000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize TGF4000 driver.

        Config options:
            port: Serial port (e.g., "COM8" or "/dev/ttyUSB0")
            baud: Baud rate (default: 115200)
        """
        super().__init__(dev_id, options, manager)

        self.PORT = options.get("port", "COM8")
        self.BAUD = options.get("baud", 115200)
        self.ser = None

    # --- Lifecycle ---

    def connect(self) -> bool:
        """
        Connect to TGF4000 device.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.ser = serial.Serial(
                port=self.PORT,
                baudrate=self.BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
                write_timeout=1.0,
            )
            time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to TGF4000 on {self.PORT}: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from device.

        Returns:
            True if disconnect successful, False otherwise
        """
        if not self.ser:
            return True

        try:
            self.ser.close()
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

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
