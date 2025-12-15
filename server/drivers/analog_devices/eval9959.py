# hub_app/drivers/example_device.py
from __future__ import annotations
import asyncio, math, random
from typing import Any, Dict, Optional, List, AsyncIterator
import numpy as np
import serial
import time
from pathlib import Path

from .._base import Device, api_device, api_command, api_property, api_data, Frame
from .adi_bridge import AdiClockEvalBridge

BRIDGE_EXE = str(Path(__file__).with_name("adiclockeval_spi_bridge.exe"))

CHANNELS = {0: 0x10, 1: 0x20, 2: 0x40, 3: 0x80}

#   - id: "AnalogDevices_DDS"
#     driver: "eval9959"
#     vid: 0x0456
#     pid: 0xee25
#     ref_clk_hz: 50_000_000
#     dll_folder: "C:/Program Files (x86)/Analog Devices/AD9958_59 Evaluation Software"


@api_device("eval9959")
class EVAL9959(Device):
    """
    Analog devices 9959 evaluation board
    """

    kind = "eval9959"

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        self.dll_folder = options.get("dll_folder", r"C:\Program Files (x86)\Analog Devices\AD9958_59 Evaluation Software") # <-- change to your COM port (e.g., "/dev/ttyACM0" on Linux)
        self.vid = options.get("vid", 0x0456) # CDC ignores baud, but pyserial wants a value
        self.pid = options.get("pid", 0xee25)
        self._ref_clk_hz = 40_000_000  #options.get("ref_clk_hz", 50_000_000)
        self._sys_clk_hz = 400_000_000 #options.get("sys_clk_hz", 500_000_000)
        self._channel0_frequency = 0
        self._channel1_frequency = 0
        self._channel2_frequency = 0
        self._channel3_frequency = 0

        self._channel0_amplitude = 0
        self._channel1_amplitude = 0
        self._channel2_amplitude = 0
        self._channel3_amplitude = 0
        self.dev_id = 0 # for now, support only one device TODO
        self.bridge = None
        super().__init__(dev_id, options)

    async def connect(self) -> None:

        def _connect():
            bridge = AdiClockEvalBridge(BRIDGE_EXE, self.dll_folder, timeout=10.0)
            time.sleep(0.1)
            bridge.start()
            return bridge

        self.bridge = await self._on_device(_connect) 
        self.bridge.find_hardware(1, [(self.vid, self.pid), ]) # TODO CHECK IF its connected
        if self.bridge.get_vendor_id() != self.vid or self.bridge.get_product_id() != self.pid:
            raise Exception(f"Failed to connect to AD device with vid={hex(self.vid)} and pid={hex(self.pid)}")
        
        self._connected = True # indicate successful connection
        return  

    async def disconnect(self) -> None:
        def _disconnect():
            self.bridge.close()

        await self._on_device(_disconnect)
        self._connected = False

    def io_update(self):
        command = 3    # maps to opcode 0x0C
        self.bridge.set_port_value(self.dev_id, command, 0x10)
        self.bridge.set_port_value(self.dev_id, command, 0x00)

    @api_property(default=50_000_000, step=1, unit="Hz") # TODO - review min/max
    @property
    def ref_clk(self) -> int:
        """Reference clock [Hz] (input to eval board from external source)"""
        return self._ref_clk_hz
    
    @ref_clk.setter
    def ref_clk(self, value :int):
        self._ref_clk_hz = value # update reference clock // TODO - checks?
        self.sys_clk = self._sys_clk_hz # call the setter = keep old value of system clock on new ref clock


    @api_property(default=500_000_000, step=1, unit="Hz") # TODO - review min/max
    @property
    def sys_clk(self) -> int:
        """System clock [Hz] of the internal DDS
        (reference clock × integer multiplier)"""
        return self._sys_clk_hz
    
    @sys_clk.setter
    def sys_clk(self, value: int=500_000_000):
        multiplier = int(round(value / self._ref_clk_hz))
        self._sys_clk_hz = self._ref_clk_hz * multiplier
        if 255_000_000 <= self._sys_clk_hz <= 500_000_000:
            vco_flag = True
        elif 100_000_000 <= self._sys_clk_hz <= 255_000_000:
            vco_flag = False
        else:
            print(f" For sys_clk = {self._sys_clk_hz} Hz, there is not guarantee of operation (choose either 100-160 MHz or 255-500 MHz")
            return # TODO - some sort of error into GUI??
        
        fr1_val = 0
        if vco_flag:
            fr1_val |= 1 << 23
        fr1_val |= (multiplier & 0x1F) << 18
        data = fr1_val.to_bytes(3, 'big')
        self.bridge.spi_write_addr_payload(self.dev_id, 0x01, data) # TODO - wait for confirmation
        self.io_update()

    def select_channel(self, channel_mask):
        self.bridge.spi_write_addr_payload(self.dev_id, 0x00,  [channel_mask, ]) 

    @api_command()
    def set_channel_frequency(self, channel_mask:int, frequency:int) -> float:
        """Sets frequency (in Hz) to one or more channels according to channel mask
           ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80"""
        self.select_channel(channel_mask)
        ftw = int(round(frequency * (1<<32) / self._sys_clk_hz)) & 0xFFFFFFFF
        self.bridge.spi_write_addr_payload(self.dev_id, 0x04, ftw.to_bytes(4, 'big')) # 0x04 is cftw0 address
        freq = ftw * self._sys_clk_hz / 2**32
        self.io_update()
        return freq
    
    
    @api_command()
    def set_channel_amplitude(self, channel_mask:int, amplitude:float) -> float:
        """Sets relative amplitude (range 0..1) to one or more channels according to channel mask
           ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80"""
        self.select_channel(channel_mask)
        amplitude_int = int(round(max(0, min(1023, float(amplitude * 1024)))))

        acr_val = (1 << 12) | amplitude_int # "1" at bit 12 enables manual writing
        data = acr_val.to_bytes(3, 'big')   

        self.bridge.spi_write_addr_payload(self.dev_id, 0x06, data)     

        amp = amplitude_int / 1024    
        #print(f"Channel set to single tone amp = {amp}")
        self.io_update()
        return amp

    @api_property(unit="Hz")
    @property
    def channel0_frequency(self) -> float:
        """Frequency [Hz] of single tone signal on channel 0"""
        return self._channel0_frequency
    
    @channel0_frequency.setter
    def channel0_frequency(self, value:float):
        self._channel0_frequency = self.set_channel_frequency(0x10, value)

    @api_property()
    @property
    def channel0_amplitude(self) -> float:
        """Amplitude (0–1) of single tone signal on channel 0"""
        return self._channel0_amplitude
    
    @channel0_amplitude.setter
    def channel0_amplitude(self, value:float):
        self._channel0_amplitude = self.set_channel_amplitude(0x10, value)



    @api_property(unit="Hz")
    @property
    def channel1_frequency(self) -> float:
        """Frequency [Hz] of single tone signal on channel 1"""
        return self._channel1_frequency
    
    @channel1_frequency.setter
    def channel1_frequency(self, value:float):
        self._channel1_frequency = self.set_channel_frequency(0x20, value)

    @api_property()
    @property
    def channel1_amplitude(self) -> float:
        """Amplitude (0–1) of single tone signal on channel 1"""
        return self._channel1_amplitude
    
    @channel1_amplitude.setter
    def channel1_amplitude(self, value:float):
        self._channel1_amplitude = self.set_channel_amplitude(0x20, value)



    @api_property(unit="Hz")
    @property
    def channel2_frequency(self) -> float:
        """Frequency [Hz] of single tone signal on channel 2"""
        return self._channel2_frequency
    
    @channel2_frequency.setter
    def channel2_frequency(self, value:float):
        self._channel2_frequency = self.set_channel_frequency(0x40, value)

    @api_property()
    @property
    def channel2_amplitude(self) -> float:
        """Amplitude (0–1) of single tone signal on channel 2"""
        return self._channel2_amplitude
    
    @channel2_amplitude.setter
    def channel2_amplitude(self, value:float):
        self._channel2_amplitude = self.set_channel_amplitude(0x40, value)



    @api_property(unit="Hz")
    @property
    def channel3_frequency(self) -> float:
        """Frequency [Hz] of single tone signal on channel 3"""
        return self._channel3_frequency
    
    @channel3_frequency.setter
    def channel3_frequency(self, value:float):
        self._channel3_frequency = self.set_channel_frequency(0x80, value)

    @api_property()
    @property
    def channel3_amplitude(self) -> float:
        """Amplitude (0–1) of single tone signal on channel 3"""
        return self._channel3_amplitude
    
    @channel3_amplitude.setter
    def channel3_amplitude(self, value:float):
        self._channel3_amplitude = self.set_channel_amplitude(0x80, value)

    


 





