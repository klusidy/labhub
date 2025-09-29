from __future__ import annotations
import os, asyncio, time
from typing import Any, Dict, Optional
from .._base import Device, api_device, api_command, api_property
from ._kinesis_device import KinesisDevice


import logging
logger = logging.getLogger(__name__)

@api_device("k10cr1")
class K10CR1(KinesisDevice):
    """
    Stepper Motor Rotation Mount
    """
    pass
    
    def __init__(self, dev_id: str, options: Dict[str, Any]):
        conn = options.get("conn")

        self.serial: str = conn.get("serial")
        self.poll_ms: int = int(conn.get("poll_ms", 200))
        self.simulate: bool = bool(conn.get("simulate", False))
        self._dev = None  
        #print(f" -- init of halfplate, dev_id = {dev_id}, options = {options}")
        super().__init__(dev_id, options)

    async def _call(self, fn, *args, **kw): # to keep it fresh, run everything in a "kinesis" executor thread
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._exec, lambda: fn(*args, **kw))

    
    def _to_decimal(self, value: float):
        return self.Decimal(value) if self.Decimal else float(value)
    
    async def connect(self) -> None:
        if self.simulate:
            self._connected = True
            logger.info(f"[SIM] Connected to simulated KCubePiezo {self.serial}")
            return
        
        await self._ensure_kinesis_loaded() # TODO - DIFFERENT DLLS FOR EACH DEVICE
        
        def _connect():
            self.DeviceManagerCLI.BuildDeviceList()
            device = self.IntegratedStepperMotorsCLI.CageRotator.CreateCageRotator(self.serial)
            device.Connect(self.serial)
            device.WaitForSettingsInitialized(2000)

            device.StartPolling(self.poll_ms); time.sleep(max(0.25, self.poll_ms/1000))
            device.EnableDevice();             time.sleep(0.25)

            
            return device
        
        self._dev = await self._on_device(_connect)

        self.dev_settings = self._dev.LoadMotorConfiguration(self.serial)
        currentDeviceSettings = self._dev.MotorDeviceSettings # why this? (https://github.com/Thorlabs/Motion_Control_Examples/blob/main/Matlab/Intergrated/K10CR2/K10CR2.m)
        self.dev_settings.UpdateCurrentConfiguration()
        
        self._connected = True

    async def disconnect(self) -> None:
        if self.simulate and not self._dev:
            self._connected = False
            return
        
        await self._on_device(self._dev.StopPolling)
        await self._on_device(self._dev.Disconnect)
        self._connected = False

    @api_property()
    @property
    def position(self)-> float:
        conv = self._dev.UnitConverter
        pos = self._dev.GetPositionCounter()
        pos_dec = self._to_decimal(pos)
        #print(f"position is {pos}")
        #print(f"position is {pos_dec}")
        real = conv.DeviceUnitToReal(pos_dec, conv.UnitType.Length)
        return float(self.Decimal.ToDouble(real))
