from __future__ import annotations
from typing import Any, Dict
from ..base import Device, api_device, api_command, api_property
import serial, time, threading


@api_device("boostik")
class Boostik(Device):
    """
    NKT Boostik fiber amplifier
    """

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        self.PORT = options.get(
            "port", "COM5"
        )  # <-- change to your COM port (e.g., "/dev/ttyACM0" on Linux)
        self.BAUD = options.get(
            "baud", 9600
        )  # CDC ignores baud, but pyserial wants a value
        self.timeout = options.get("timeout", 1.0)
        self._ser = None
        self._lock = threading.Lock()
        self._last_tx = 0.0
        self._min_gap = 0.02  # 20 ms between commands
        super().__init__(dev_id, options, manager)

    async def connect(self) -> None:

        def _connect():
            _ser = serial.Serial(
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
            _ser.reset_input_buffer()
            time.sleep(0.1)
            return _ser

        self._ser = await self._on_device(_connect)

    async def disconnect(self) -> None:
        def _disconnect():
            self._ser.close()

        await self._on_device(_disconnect)

    # --- low-level helpers ---
    def _send(self, cmd: str) -> str:
        # print(f"Sent command: {cmd}")
        self._ser.write((cmd + "\r").encode("ascii"))
        self._ser.flush()
        return self._ser.readline().decode("ascii", errors="ignore").strip()

    def query(self, cmd: str) -> str:
        payload = (cmd + "\r").encode("ascii")
        with self._lock:
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

    # --- properties ---

    @api_property()
    @property
    def enabled(self) -> bool:
        """Emission on/off"""
        r = self.query("CDO")
        # print("CDO return: " + r)
        return r == "1"

    @enabled.setter
    def enabled(self, on: bool) -> None:
        self.query(f"CDO {1 if on else 0}")

    @api_property()
    @property
    def current_setpoint(self) -> float:
        """Current setpoint [A]"""
        r = self.query("ACC")
        # print("ACC return: " + r)
        try:
            return float(r)
        except ValueError:
            return -100.0

    @current_setpoint.setter
    def current_setpoint(self, amps: float) -> None:
        self.query(f"ACC {amps}")

    @api_property()
    @property
    def actual_current(self) -> float:
        """Actual current [A]"""
        r = self.query("AMC")
        # print("AMC return: " + r)
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property()
    @property
    def diode_temp(self) -> float:
        """Temperature of diode booster [°C]"""
        r = self.query("AMT 1")
        # print("AMT 1 return: " + r)
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property()
    @property
    def ambient_temp(self) -> float:
        """Ambient temperature [°C]"""
        r = self.query("CMA")
        # print("CMA return: " + r)
        try:
            return float(r)
        except ValueError:
            return -100.0

    @api_property()
    @property
    def input_power(self) -> float:
        """Input optical power [mW]"""
        r = self.query("CMP 1")
        # print("CMP 1 return: " + r)
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
