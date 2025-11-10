from __future__ import annotations
from typing import Any, Dict
from .._base import Device, api_device, api_command, api_property
from nkt_tools import NKTP_DLL
import logging
logger = logging.getLogger(__name__)

@api_device("nkt_laser_X15")
class X15(Device):
    """
    NKT Photonics laser X15
    """

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        super().__init__(dev_id, options)
        self.port = options.get("PORT", "COM4")
        self.autoMode = options.get("autoMode", 0)
        self.liveMode = options.get("liveMode", 0)

    # --- lifecycle ---
    async def connect(self) -> None:
        def _connect():
            openResult = NKTP_DLL.openPorts(self.port, self.autoMode, self.liveMode)
            if openResult != 0:
                raise Exception (f"NKTP port not connected: {NKTP_DLL.PortResultTypes(openResult)}")
            rdResult, self.wvg_standard = NKTP_DLL.registerReadU32(self.port, 0x01, 0x32, -1)
            logger.info(f"NKTP Read standard wavelength result: {NKTP_DLL.RegisterResultTypes(rdResult)}")

        await self._on_device(_connect) 

    async def disconnect(self) -> None:
        def _disconnect():
            closeResult = NKTP_DLL.closePorts(self.port)

        await self._on_device(_disconnect)

    # --- API PROPERTIES ---


    @api_property()
    @property
    def emission(self) -> bool:
        rdResult, value = NKTP_DLL.registerReadU8(self.port, 0x01, 0x30, -1)
        """Emission on/off"""
        if rdResult != 0:
            logger.info(f"NKTP Read result: {NKTP_DLL.RegisterResultTypes(rdResult)}")
        return bool(value)
    
    @emission.setter
    def emission(self, value: bool) -> None:
        value_int = int(value)
        wrResult = NKTP_DLL.registerWriteS16(self.port, 0x01, 0x2A, value_int, -1)


    @api_property()
    @property
    def wvg_actual(self) -> float:
        rdResult, wvg_actual_int = NKTP_DLL.registerReadS32(self.port, 0x01, 0x72, -1)
        """Wavelength setpoint in nm. Minimal step 0.0001."""
        if rdResult != 0:
            logger.info(f"NKTP Read result: {NKTP_DLL.RegisterResultTypes(rdResult)}")
        wvg_actual = (wvg_actual_int + self.wvg_standard)/10000
        return wvg_actual    



    @api_property(min=1546.0, max=1554.0, step=0.0001)
    @property
    def wvg_setpoint(self) -> float:
        rdResult, wvg_setpoint_int = NKTP_DLL.registerReadS16(self.port, 0x01, 0x2A, -1)
        """Wavelength setpoint in nm. Minimal step 0.0001."""
        if rdResult != 0:
            logger.info(f"NKTP Read result: {NKTP_DLL.RegisterResultTypes(rdResult)}")
        wvg_setpoint = (wvg_setpoint_int + self.wvg_standard)/10000
        return wvg_setpoint
    
    @wvg_setpoint.setter
    def wvg_setpoint(self, value: float) -> None:
        value_int = int(round(value-self.wvg_standard))
        wrResult = NKTP_DLL.registerWriteS16(self.port, 0x01, 0x2A, value_int, -1)



    @api_property()
    @property
    def power(self) -> float:
        rdResult, power = NKTP_DLL.registerReadU16(self.port, 0x01, 0x17, -1)
        """Output power in mW"""
        if rdResult != 0:
            logger.info(f"NKTP Read result: {NKTP_DLL.RegisterResultTypes(rdResult)}")
        return power/100


    # --- API COMMANDS ---
    #@api_command()
    #def bar(self, port: str) -> int:
        #"""Demo command; increments an internal counter and return its value"""
        #self._bar_count +=1
        #return self._bar_count
