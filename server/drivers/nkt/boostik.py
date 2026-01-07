"""NKT Photonics Boostik Fiber Amplifier Driver"""
from __future__ import annotations
import serial
import time
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..base import Device, api_device, api_command, api_property

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class boostik(Device):
    """NKT Photonics Boostik fiber amplifier"""

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize Boostik driver.

        Config options:
            port: Serial port (e.g., "COM5" or "/dev/ttyUSB0")
            baud: Baud rate (default: 9600)
            timeout: Communication timeout in seconds (default: 1.0)
        """
        super().__init__(dev_id, options, manager)

        self.PORT = options.get("port", "COM5")
        self.BAUD = options.get("baud", 9600)
        self.timeout = options.get("timeout", 1.0)
        self._ser = None
        self._last_tx = 0.0
        self._min_gap = 0.02  # 20 ms minimum gap between commands

    # --- Lifecycle ---

    def connect(self) -> bool:
        """
        Connect to Boostik device.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._ser = serial.Serial(
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
            self._ser.reset_input_buffer()
            time.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to Boostik on {self.PORT}: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from device.

        Returns:
            True if disconnect successful, False otherwise
        """
        if not self._ser:
            return True

        try:
            self._ser.close()
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- low-level helpers ---
    def _send(self, cmd: str) -> str:
        # print(f"Sent command: {cmd}")
        self._ser.write((cmd + "\r").encode("ascii"))
        self._ser.flush()
        return self._ser.readline().decode("ascii", errors="ignore").strip()

    def query(self, cmd: str) -> str:
        """
        Send command and read response with rate limiting.

        Note: Rate limiting is safe without additional locking because
        base class ensures exclusive access (async lock in poll_property/run_command).
        """
        payload = (cmd + "\r").encode("ascii")
        dt = time.monotonic() - self._last_tx
        if dt < self._min_gap:
            time.sleep(self._min_gap - dt)
        self._ser.write(payload)
        self._ser.flush()
        self._last_tx = time.monotonic()
        return self._readline()

    def _readline(self) -> str:
        # read one line terminated by CR/LF; return "" on timeout
        buf = bytearray()
        t0 = time.monotonic()
        to = self._ser.timeout or 0
        while True:
            b = self._ser.read(1)
            if not b:
                if time.monotonic() - t0 >= to:
                    return ""
                continue
            if b in (b"\r", b"\n"):
                # optional: swallow paired \n after \r
                if b == b"\r" and self._ser.in_waiting:
                    nxt = self._ser.read(1)
                    if nxt != b"\n":
                        buf.extend(nxt or b"")
                return buf.decode("ascii", errors="ignore").strip()
            buf.extend(b)

    # --- Properties ---

    @api_property()
    def enabled(self) -> bool:
        """Emission on/off"""
        r = self.query("CDO")
        return r == "1"

    @enabled.setter
    def enabled(self, on: bool) -> None:
        self.query(f"CDO {1 if on else 0}")

    @api_property(unit="A")
    def current_setpoint(self) -> float:
        """Current setpoint [A]"""
        r = self.query("ACC")
        try:
            return float(r)
        except ValueError:
            return -100.0

    @current_setpoint.setter
    def current_setpoint(self, amps: float) -> None:
        self.query(f"ACC {amps}")

    @api_property(unit="A")
    def actual_current(self) -> float:
        """Measured current [A]"""
        r = self.query("AMC")
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property(unit="°C")
    def diode_temp(self) -> float:
        """Temperature of diode booster [°C]"""
        r = self.query("AMT 1")
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property(unit="°C")
    def ambient_temp(self) -> float:
        """Ambient temperature [°C]"""
        r = self.query("CMA")
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property(unit="mW")
    def input_power(self) -> float:
        """Input optical power [mW]"""
        r = self.query("CMP 1")
        try:
            return float(r) / 10
        except ValueError:
            return -100.0

    # @property
    # def device_info(self) -> str:
    #    """CDI (string) read-only"""
    #    return self._send("CDI")


# --- example usage ---
# with Boostik("COM5") as b:
#     print(b.enabled)              # bool
#     b.enabled = True              # turn ON
#     b.current_setpoint = 4.0      # set 4 A
#     print(b.actual_current)       # float
#     print(b.input_power)          # float
#     print(b.diode_temp, b.ambient_temp)
#     print(b.device_info)
