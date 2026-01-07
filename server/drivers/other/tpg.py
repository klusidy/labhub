"""TPG Pressure Sensor Driver"""
from __future__ import annotations
import serial
import time
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..base import Device, api_device, api_command

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)

# Protocol constants
ACK = b"\x06"
NAK = b"\x15"
CR = b"\r"
LF = b"\n"
ENQ = b"\x05"


@api_device()
class tpg(Device):
    """TPG pressure sensor (vacuum gauge)"""

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize TPG driver.

        Config options:
            port: Serial port (e.g., "COM10" or "/dev/ttyUSB0")
            baud: Baud rate (default: 9600)
            timeout: Communication timeout in seconds (default: 1.0)
        """
        super().__init__(dev_id, options, manager)

        self.PORT = options.get("port", "COM10")
        self.BAUD = options.get("baud", 9600)
        self.timeout = options.get("timeout", 1.0)
        self.ser = None

    # --- Lifecycle ---

    def connect(self) -> bool:
        """
        Connect to TPG device.

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
                timeout=self.timeout,
                write_timeout=self.timeout,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            )
            time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to TPG on {self.PORT}: {e}")
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

    def expect_ack(self):
        # Read until CRLF; the device answers with ACK/NAK then CRLF
        line = self.ser.read_until(LF)
        if not line:
            raise TimeoutError("No ACK/NAK from TPG")
        if line.startswith(ACK):
            return True
        if line.startswith(NAK):
            raise RuntimeError("TPG reported NAK (invalid mnemonic or state)")
        raise RuntimeError(f"Unexpected reply: {line!r}")

    @api_command()
    def send_cmd(self, text: str) -> str:
        """Send command (3-letter mnemonics with optional params, terminated by CR)"""
        if not text.endswith("\r"):
            text += "\r"
        self.ser.reset_input_buffer()
        self.ser.write(text.encode("ascii"))
        self.expect_ack()
        return self.read_data_line()

    def read_data_line(self):
        # After ACK, send ENQ to fetch the data line, terminated by CRLF
        self.ser.write(ENQ)
        data = self.ser.read_until(LF).decode("ascii").strip("\r\n")
        if not data:
            raise TimeoutError("No data line after ENQ")
        return data

    def parse_pr_line(self, s):
        # Formats per manual (PR1):  x,sx.xxxxEsyy
        # (status, ',', value in exponential, status again?) Manual shows "x,sx.xxxxEsxx".
        # In practice, for PR1 you'll get like "0,5.20000E-02"
        parts = s.split(",")
        if len(parts) < 2:
            raise ValueError(f"Unexpected PR format: {s!r}")
        status = int(parts[0])
        value_str = parts[1]
        try:
            value = float(value_str)
        except ValueError:
            # Some firmware echoes a status suffix; keep only the numeric part before any non-number
            import re

            m = re.match(r"[+-]?\d+(\.\d+)?[eE][+-]?\d+", value_str)
            if not m:
                raise
            value = float(m.group(0))
        return status, value

    @api_command()
    def read_pressure_once(self, gauge: int = 1) -> dict:
        self.send_cmd(f"PR{gauge}")
        line = self.read_data_line()
        status, value = self.parse_pr_line(line)
        return {"status": status, "pressure": value, "raw": line}

    # @api_property(unit="Pa")
    # @property
    # def pressure_gauge_1(self): # TODO - periodic polling???
    #     """Pressure reading from gauge 1"""
    #     p = self.read_pressure_once(gauge=1)
    #     return p["pressure"]
