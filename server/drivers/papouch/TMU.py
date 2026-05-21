"""Papouch TMU USB thermometer driver"""
from __future__ import annotations
import logging
import threading
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

import serial
from serial.tools import list_ports

from ..base import Device, api_device, api_property

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)

_TMU_VID = 0x0403
_TMU_PID = 0x6001


def _find_tmu_port() -> Optional[str]:
    for info in list_ports.comports():
        if info.vid == _TMU_VID and info.pid == _TMU_PID:
            return info.device
    return None


def _parse_tmu_line(raw: bytes) -> Optional[float]:
    # Format: *B1E1+021.8\r  — fields: prefix(*) format(B) address(1) code(E1) temperature
    line = raw.decode("ascii", errors="replace").strip()
    if not line.startswith("*B") or len(line) < 6:
        return None
    temp_str = line[5:].strip()
    if temp_str == "Err":
        raise ValueError("Sensor reports Err - probe may be disconnected")
    return float(temp_str)


@api_device()
class TMU(Device):
    """Papouch TMU USB thermometer.

    The device transmits a temperature reading every ~10 s autonomously.
    Port is auto-discovered by USB VID/PID (0403:6001); set 'port' in config
    to override (e.g. 'COM3' or '/dev/ttyUSB0').
    """

    config_template = {
        "port": "",           # leave empty for auto-discovery by VID/PID
        "polling_interval": 15000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)
        self._port: Optional[str] = options.get("port") or None
        self._ser: Optional[serial.Serial] = None
        self._last_temperature: Optional[float] = None
        self._stop_event = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None

    # --- Lifecycle ---

    def connect(self) -> bool:
        port = self._port or _find_tmu_port()
        if port is None:
            logger.error(
                f"{self.id}: TMU not found (VID={_TMU_VID:#06x}, PID={_TMU_PID:#06x})."
                " Set 'port' in config or check USB connection."
            )
            return False

        try:
            self._ser = serial.Serial(
                port=port, baudrate=9600, bytesize=8, parity="N", stopbits=1, timeout=15
            )
        except Exception as e:
            logger.error(f"{self.id}: Failed to open {port}: {e}")
            return False

        logger.info(f"{self.id}: Opened TMU on {port}")
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name=f"tmu-reader-{self.id}"
        )
        self._reader_thread.start()

        # Wait for first reading (device sends every ~10 s; timeout 15 s)
        deadline = time.monotonic() + 15
        while self._last_temperature is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if self._last_temperature is None:
            logger.warning(f"{self.id}: No reading received within 15 s, proceeding anyway")

        return True

    def disconnect(self) -> bool:
        self._stop_event.set()
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self._reader_thread:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None
        return True

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                raw = self._ser.read_until(b"\r")
                if not raw:
                    continue
                temp = _parse_tmu_line(raw)
                if temp is not None:
                    self._last_temperature = temp
                    logger.debug(f"{self.id}: temperature = {temp} °C")
            except ValueError as e:
                logger.warning(f"{self.id}: {e}")
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"{self.id}: Serial read error: {e}")
                break

    # --- Properties ---

    @api_property(unit="°C")
    def temperature(self) -> float:
        """Current temperature from the TMU probe."""
        if self._last_temperature is None:
            raise RuntimeError("No temperature reading available yet")
        return self._last_temperature
