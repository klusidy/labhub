from __future__ import annotations
import os, asyncio, time
from typing import Any, Dict, Optional, Literal
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
        """ Position in real-world units, presumably degrees (?)"""""
        conv = self._dev.UnitConverter
        pos = self._dev.GetPositionCounter()
        pos_dec = self._to_decimal(pos)
        #print(f"position is {pos}")
        #print(f"position is {pos_dec}")
        real = conv.DeviceUnitToReal(pos_dec, conv.UnitType.Length)
        return float(self.Decimal.ToDouble(real))
    

    @position.setter
    def position(self, value:float) -> None: # todo when value is dict, update min/max/default etc
        conv = self._dev.UnitConverter
        value_decimal = self._to_decimal(value)
        self._dev.MoveTo(value_decimal, 60000) # TODO - should be async? (properties are not async...)
        return value  

    #@api_property()
    #@property
    #def units(self) -> str:
        # cound not find any enum of available units...
        # self._dev.MotorDeviceSettings.Physical.RealUnits = "°" # can set like this, but can change to anythinng...
        # return "°"
    
    # @units.setter
    # def units(self, units: str) -> None: # self._dev.SetJogParams_DeviceUnit
    #     return
    

    
    @api_command()
    def drive_up(self, velocity: float) -> None:
        fwd = self.MotorDirection.Forward # todo add support for veocity!!
        self._dev.MoveContinuous(fwd)
        return
    
    @api_command()
    def drive_down(self, velocity: float) -> None:
        bck = self.MotorDirection.Backward
        self._dev.MoveContinuous(bck)
        return
    
    @drive_up.release()
    @drive_down.release()
    def drive_up_release(self, **kwargs) -> None:
        self._dev.StopImmediate()
        return
    
    @api_command()
    def home(self) -> None:
        self._dev.Home(60000)
        return
    
    
    # @api_command()
    # def jog_up(self) -> None:
    #     return
    
    
    # @api_command()
    # def jog_down(self) -> None:
    #     return
    
    # @jog_up.release()
    # @jog_down.release()
    # def jog_down_release(self) -> None:
    #     return
    
    @api_command()
    def set_jog_parameters(self, 
                           jog_mode: Literal["single_step", "continuous_held", "continuous_unheld"],
                           step_size: float = 5,
                           acceleration: float = 15,
                           max_velocity: float = 15)-> dict:
                           #min_velocity: float = 5)-> dict :#step_mode: str, max_velocity:int, acc:int) -> dict:
        print("iinsde step parameters")
        jog_params = self._dev.GetJogParams()
        if step_size:
            jog_params.StepSize = self._to_decimal(step_size)
        if acceleration:
            jog_params.VelocityParams.Acceleration = self._to_decimal(acceleration)
        if max_velocity:
            jog_params.VelocityParams.MaxVelocity = self._to_decimal(max_velocity)
        if jog_mode == "single_step":
            jog_params.JogMode = jog_params.JogModes.SingleStep
        elif jog_mode == "continuous_held":
            jog_params.JogMode = jog_params.JogModes.ContinuousHeld
        elif jog_mode == "continuous_unheld":
            jog_params.JogMode = jog_params.JogModes.ContinuousUnheld

        #self._dev.SetJogParams_DeviceUnit TODO - UNITS!!!
        self._dev.SetJogParams(jog_params)
        
        #if min_velocity:
        #    jog_params.VelocityParams.MinVelocity = self._to_decimal(min_velocity)
        
        r = { # todo -read out from actual params
            "step_size": self.Decimal.ToDouble(jog_params.StepSize),
            "acceleration": self.Decimal.ToDouble(jog_params.VelocityParams.Acceleration),
            "max_velocity": self.Decimal.ToDouble(jog_params.VelocityParams.MaxVelocity),
            "jog_mode": "single_step" if jog_params.JogMode == jog_params.JogModes.SingleStep else \
                         "continuous_held" if jog_params.JogMode == jog_params.JogModes.ContinuousHeld else \
                         "continuous_unheld" if jog_params.JogMode == jog_params.JogModes.ContinuousUnheld else "unknown"
            }
        return r
    

    
    # @api_command()
    # def stop(self) -> None:
    #     return
    
    # @api_command()
    # def identify(self) -> None:
    #     return
    

    

