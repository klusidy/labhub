# hub_app/drivers/example_device.py
from __future__ import annotations
import asyncio, math, random
from typing import Any, Dict, Optional, List, AsyncIterator
import numpy as np
from ._base import Device, api_device, api_command, api_property, api_data, Frame

@api_device("example_device")
class ExampleDevice(Device):
    """
    Spec-driven toy device that generates a time-series from a configurable waveform.
    Properties control the waveform and streaming cadence; commands manage streaming.
    """

    kind = "example_device" # todo -keep this or replace with alias?
    #doc = "Example device that generates a time-series from a configurable waveform."

    # --- /spec metadata to make everything work -----------------------
    # PARAMS: Dict[str, Dict[str, Any]] = {
    #     "time_step": {
    #         "doc": "Sampling interval for generated data (seconds).",
    #         "type": "float", "unit": "s", "minimum": 1e-4, "maximum": 10.0, "default": 0.01, "step": 0.001,
    #     },
    #     "number_of_time_steps": {
    #         "doc": "How many samples to return from get_timestamps().",
    #         "type": "int", "minimum": 1, "maximum": 1_000_000, "default": 1000, "step": 1,
    #     },
    #     "wave": {
    #         "doc": "Composite waveform parameters.",
    #         "fields": {
    #             "frequency": {"doc": "Wave frequency (Hz).", "unit": "Hz", "minimum": 0.0, "maximum": 10_000.0, "default": 1.0},
    #             "amplitude": {"doc": "Wave amplitude.", "minimum": 0.0, "maximum": 1e6, "default": 1.0},
    #             "phase":     {"doc": "Phase offset (radians).", "unit": "rad", "minimum": 0.0, "maximum": 2*math.pi, "default": 0.0},
    #         },
    #     },
    #     "add_noise": {
    #         "doc": "Add small uniform noise (~±5% of amplitude).",
    #         "type": "bool", "default": False,
    #     },
    #     "wave_type": {
    #         "doc": "Waveform type.",
    #         "type": "str", "choices": ["sin", "square"], "default": "sin",
    #     },
    #     # todo -add status flags like "streaming" to PARAMS as read-only param
    # }

    # COMMANDS: Dict[str, Dict[str, Any]] = {
    #     "get_timestamps": {
    #         "doc": "Return x-axis timestamps based on number_of_time_steps and time_step.",
    #         "args": {}, "returns": "List[float]",
    #         "method": "get_timestamps",  # method name to call
    #     },
    #     "start": {
    #         "doc": "Start streaming y-values at time_step Hz. Stops automatically after duration (s) if >0.",
    #         "args": {"duration_in_seconds": {"type": "int", "required": True, "default": 0}},
    #         "returns": "None",
    #     },
    #     "stop": {
    #         "doc": "Stop streaming.",
    #         "args": {}, "returns": "None",
    #     },
    #}

    # -------------------------------------------------------------------------

    def __init__(self, dev_id: str, default_values: Dict[str, Any]):
        super().__init__(dev_id, default_values)
        


    # --- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop()
        self._connected = False

    # -- API PROPERTIES 

    @api_property(min=1e-4, max=10.0, default=0.01, step=0.001) # TODO - ADD UNITS
    @property
    def time_step(self) -> float:
        """Sampling interval for generated data (seconds)"""
        return self._time_step
    
    @time_step.setter
    def time_step(self, value:float): # todo when value is dict, update min/max/default etc
        self._time_step = value

    @api_property(min=1, max=1_000_000, default=1000, step=10)
    @property
    def number_of_time_steps(self) -> int:
        """How many samples to return from get_timestamps() (default = 1000)"""
        return self._number_of_time_steps
    
    @number_of_time_steps.setter
    def number_of_time_steps(self, value:int):
        self._number_of_time_steps = value

    
    @api_property(default=False)
    @property
    def noise(self) -> bool:
        """Add small uniform noise (~±5% of amplitude)."""
        return self._noise
    
    @noise.setter
    def noise(self, value: bool):
        self._noise = value

    @api_property(choices=["sin", "square"], default="sin")
    @property
    def wave_type(self) -> str:
        """Waveform type"""
        return self._wave_type
    
    @wave_type.setter
    def wave_type(self, value: str): # validation is done automatically from choices
        self._wave_type = value
            

    # PARAMS: Dict[str, Dict[str, Any]] = {

    #         "wave": {
    #             "doc": "Composite waveform parameters.",
    #             "fields": {
    #                 "frequency": {"doc": "Wave frequency (Hz).", "unit": "Hz", "minimum": 0.0, "maximum": 10_000.0, "default": 1.0},
    #                 "amplitude": {"doc": "Wave amplitude.", "minimum": 0.0, "maximum": 1e6, "default": 1.0},
    #                 "phase":     {"doc": "Phase offset (radians).", "unit": "rad", "minimum": 0.0, "maximum": 2*math.pi, "default": 0.0},
    #             },
    #         },

        
    #         # todo -add status flags like "streaming" to PARAMS as read-only param
    #     }

    # @api_property()
    # @property
    # def wave(self):
    #     # vendor-specific HW logic for value readout
    #     return {
    #         "frequency": self._freq,
    #         "amplitude": self._amp,
    #         "phase": self._phase    
    #     }
    
    # @wave.setter
    # def wave(self, value: Dict[str, Any]):
    #     # vendor-specific HW logic for value setting
    #     self._freq = float(value.get("frequency", 1.0))
    #     self._amp = float(value.get("amplitude", 1.0))
    #     self._phase = float(value.get("phase", 0.0))

    # --- API COMMANDS ---

    @api_command()
    def get_timestamps(self) -> List[float]:
        """Return x-axis timestamps based on number_of_time_steps and time_step."""
        dt = self.time_step
        self._ts = np.arange(self.number_of_time_steps) * dt
        return self._ts.tolist() # todo - find faster way to serialize numpy

    # --- API DATA/PLOTS ---

    # @api_data()
    # def demo_wave(self) -> Frame:
    #     """Simple wave generator for demo purposes"""
    #     wave = np.sin(self.get_timestamps())
    #     if self.wave_type == "square":
    #         wave = np.sign(wave)
    #     if self.noise:
    #         wave += np.random.rand(self.number_of_time_steps)
    #     return {"series": [{"name":"Test waveform", "data": wave.tolist()},]}
    @api_data()
    async def demo_wave(self) -> AsyncIterator[Frame]:
        """Simple wave generator for demo purposes"""
        try:
            # setup
            wave = np.sin(self.get_timestamps())
            if self.wave_type == "square":
                wave = np.sign(wave)
            
            # repeated action
            while True:
                ret_wave = wave + (np.random.rand(self.number_of_time_steps) * 0.5) if self.noise else wave.copy()
                yield {"series": [{"name":"Test waveform", "data": ret_wave.tolist()},]}
                await asyncio.sleep(0.05) # 

        finally:
            print("demo_wave generator exiting") # teardown

    
    # simple payload: { data: [...] }
    # object-of-arrays: { "PSD": [...], "Channel 1": [...], meta: {...} }
    # explicit series list: { series: [ { name: "PSD", data: [...] }, { name: "Ch 1", data: [...] } ], "x-values": [...] }
    
    @demo_wave.plot()
    def demo_plot(self) -> Dict[str, Any]:
        """ Simple line plot for demo purposes """
        return {"title": "Demo plot", 
                "x-label": "s", 
                "y-label": "V", 
                "x-values": self.get_timestamps()}



    
    # --- implement methods for COMMANDS ----------------------------
    # def get_timestamps(self) -> List[float]:
       
    
    # async def start(self, duration_in_seconds: int = 0) -> None:
    #     #todo - do not ignore duration in seconds
    #     ts = np.array(self.get_timestamps())

    #     # WHAT IF self._stream_queue is not there??
    #     async def _runner():
    #         try:
    #             while self._stream_running:
    #                 x = np.sin(2 * np.pi * self._freq * ts + self._phase) * self._amp
    #                 if self.add_noise and self._amp > 0:
    #                     x += (np.random.random(len(x)) * 2.0 - 1.0) * 0.05 * self._amp
    #                 if self._stream_queue.full():
    #                     try:
    #                         _ = self._q.get_nowait()
    #                     except asyncio.QueueEmpty:
    #                         pass

    #                     try:
    #                         self._q.put_nowait(x)
    #                     except asyncio.QueueFull:
    #                         pass
    #                     await asyncio.sleep(self.time_step)
    #         finally:
    #             self._stream_running = False

    #     self._stream_task = asyncio.create_task(_runner(), name=f"{self.id}-stream")


        

    # async def start(self, duration_in_seconds: int) -> None:
    #     # Stop previous stream if any
    #     await self.stop()

    #     loop = asyncio.get_running_loop()
    #     self._t0 = loop.time()
    #     self._stream_running = True
    #     self._stream_end = (self._t0 + float(duration_in_seconds)) if duration_in_seconds and duration_in_seconds > 0 else None
    #     self._q = asyncio.Queue(maxsize=4096)

    #     async def _runner():
    #         try:
    #             while self._stream_running:
    #                 now = loop.time()
    #                 if self._stream_end is not None and now >= self._stream_end:
    #                     break
    #                 t = now - self._t0
    #                 y = self._sample(t)
    #                 # If full, drop oldest to keep stream moving
    #                 if self._q.full():
    #                     try:
    #                         _ = self._q.get_nowait()
    #                     except asyncio.QueueEmpty:
    #                         pass
    #                 try:
    #                     self._q.put_nowait((t, y))
    #                 except asyncio.QueueFull:
    #                     pass
    #                 await asyncio.sleep(self.time_step)
    #         finally:
    #             self._stream_running = False

    #     self._stream_task = asyncio.create_task(_runner(), name=f"{self.id}-stream")

    # async def stop(self) -> None:
    #     self._stream_running = False
    #     if self._stream_task and not self._stream_task.done():
    #         self._stream_task.cancel()
    #         try:
    #             await self._stream_task
    #         except asyncio.CancelledError:
    #             pass
    #     self._stream_task = None


    # --- any helper methods go here ---------------------------------------------
    # def _sample(self, t: float) -> float:
    #     """Generate one sample at time t (seconds since stream start)."""
    #     ωt = 2.0 * math.pi * self._freq * t + self._phase
    #     if self.wave_type == "square":
    #         base = self._amp * (1.0 if math.sin(ωt) >= 0.0 else -1.0)
    #     else:
    #         base = self._amp * math.sin(ωt)
    #     if self.add_noise and self._amp > 0:
    #         base += (random.random() * 2.0 - 1.0) * 0.05 * self._amp  # ±5% noise
    #     return base



