from __future__ import annotations
import asyncio, math, time
from typing import Any, Dict
from ._base import Device, api_device, api_command, api_property

@api_device("sim_piezo")
class SimPiezo(Device):
    kind = "sim_piezo"

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        super().__init__(dev_id, options)
        self._voltage = float(options.get("voltage", 0.0))
        #self._t0 = time.perf_counter()

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    # async def read_state(self) -> Dict[str, Any]:
    #     # Simulate a tiny ripple just for visuals
    #     #t = time.perf_counter() - self._t0
    #     t = 0.42
    #     return {"voltage": self._voltage + 0.01 * math.sin(2 * math.pi * t), "connected": True}

    # async def apply_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
    #     if "voltage" in params:
    #         self._voltage = float(params["voltage"])
    #     return await self.read_state()