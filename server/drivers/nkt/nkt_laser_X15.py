"""NKT Photonics X15 Laser Driver"""
from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, TYPE_CHECKING

from nkt_tools import NKTP_DLL

from ..base import Device, api_device, api_property

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class nkt_laser_x15(Device):
    """
    NKT Photonics X15 tunable laser.

    Uses single-threaded executor for NKT DLL access (similar to Kinesis pattern).
    All NKT DLL calls must go through this thread to avoid threading issues.
    """

    # Shared single-threaded executor for all X15 instances (NKT DLL thread affinity)
    _EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nkt_x15")

    config_template = {
        "PORT": "COM4",
        "autoMode": 0,
        "liveMode": 0,
        "polling_interval": 1000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize X15 driver.

        Config options:
            PORT: Serial port (e.g., "COM4")
            autoMode: Auto mode setting (default: 0)
            liveMode: Live mode setting (default: 0)
        """
        super().__init__(dev_id, options, manager)

        self.port = options.get("PORT", "COM4")
        self.autoMode = options.get("autoMode", 0)
        self.liveMode = options.get("liveMode", 0)
        self._wvg_standard = 0  # Initialized during connect

    async def _run_blocking_in_thread(self, fn):
        """
        Execute function on dedicated NKT thread.

        Override base class to use NKT-specific single-threaded executor.
        All NKT DLL calls must go through this method to avoid threading issues.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._EXEC, fn)

    # --- Lifecycle ---

    def connect(self) -> bool:
        """
        Connect to X15 laser.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            openResult = NKTP_DLL.openPorts(self.port, self.autoMode, self.liveMode)
            if openResult != 0:
                logger.error(
                    f"{self.id}: Failed to open NKT port {self.port}: "
                    f"{NKTP_DLL.PortResultTypes(openResult)}"
                )
                return False

            # Read standard wavelength configuration
            rdResult, self._wvg_standard = NKTP_DLL.registerReadU32(
                self.port, 0x01, 0x32, -1
            )
            if rdResult != 0:
                logger.warning(
                    f"{self.id}: Failed to read standard wavelength: "
                    f"{NKTP_DLL.RegisterResultTypes(rdResult)}"
                )

            logger.info(f"{self.id}: Connected to NKT X15 on {self.port}")
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to NKT X15: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from laser.

        Returns:
            True if disconnect successful, False otherwise
        """
        try:
            closeResult = NKTP_DLL.closePorts(self.port)
            if closeResult != 0:
                logger.warning(
                    f"{self.id}: Close ports returned: "
                    f"{NKTP_DLL.PortResultTypes(closeResult)}"
                )
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- Properties ---

    @api_property()
    def emission(self) -> bool:
        """Emission on/off"""
        rdResult, value = NKTP_DLL.registerReadU8(self.port, 0x01, 0x30, -1)
        if rdResult != 0:
            logger.warning(
                f"{self.id}: Failed to read emission: {NKTP_DLL.RegisterResultTypes(rdResult)}"
            )
        return bool(value)

    @emission.setter
    def emission(self, value: bool) -> None:
        value_int = int(value)
        wrResult = NKTP_DLL.registerWriteS16(self.port, 0x01, 0x30, value_int, -1)
        if wrResult != 0:
            logger.warning(
                f"{self.id}: Failed to write emission: {NKTP_DLL.RegisterResultTypes(wrResult)}"
            )

    @api_property(unit="nm")
    def wvg_standard(self) -> float:
        """Standard wavelength - setpoint can be adjusted ±0.5nm around this"""
        return self._wvg_standard / 10000

    @api_property(unit="nm")
    def wvg_actual(self) -> float:
        """Actual wavelength in nm"""
        rdResult, wvg_actual_int = NKTP_DLL.registerReadS32(self.port, 0x01, 0x72, -1)
        if rdResult != 0:
            logger.warning(
                f"{self.id}: Failed to read actual wavelength: {NKTP_DLL.RegisterResultTypes(rdResult)}"
            )
        wvg_actual = (wvg_actual_int + self._wvg_standard) / 10000
        return wvg_actual

    @api_property(min=1546.0, max=1554.0, step=0.0001, unit="nm")
    def wvg_setpoint(self) -> float:
        """Wavelength setpoint in nm (0.0001 nm resolution)"""
        rdResult, wvg_setpoint_int = NKTP_DLL.registerReadS16(self.port, 0x01, 0x2A, -1)
        if rdResult != 0:
            logger.warning(
                f"{self.id}: Failed to read wavelength setpoint: {NKTP_DLL.RegisterResultTypes(rdResult)}"
            )
        wvg_setpoint = (wvg_setpoint_int + self._wvg_standard) / 10000
        return wvg_setpoint

    @wvg_setpoint.setter
    def wvg_setpoint(self, value_nm: float) -> None:
        value_int = int(round(value_nm * 10000 - self._wvg_standard))
        wrResult = NKTP_DLL.registerWriteS16(self.port, 0x01, 0x2A, value_int, -1)
        if wrResult != 0:
            logger.warning(
                f"{self.id}: Failed to write wavelength setpoint: {NKTP_DLL.RegisterResultTypes(wrResult)}"
            )

    @api_property(unit="mW")
    def power(self) -> float:
        """Output power in mW"""
        rdResult, power = NKTP_DLL.registerReadU16(self.port, 0x01, 0x17, -1)
        if rdResult != 0:
            logger.warning(
                f"{self.id}: Failed to read power: {NKTP_DLL.RegisterResultTypes(rdResult)}"
            )
        return power / 100

    # --- API COMMANDS ---
    # @api_command()
    # def bar(self, port: str) -> int:
    # """Demo command; increments an internal counter and return its value"""
    # self._bar_count +=1
    # return self._bar_count
