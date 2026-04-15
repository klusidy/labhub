"""
Multi-Device (Composite Device) Example
========================================

Demonstrates the three-level device hierarchy:

    multi_device          ← root Device (manages "connection")
    ├── channel_a         ← ChildDevice (via as_child() shorthand)
    ├── channel_b         ← ChildDevice (via as_child() shorthand)
    └── subsystem         ← ChildDevice (declared as nested class)
          ├── ch_x        ← ChildDevice grandchild (nested inside subsystem)
          └── ch_y        ← ChildDevice grandchild

All devices are simulated — no real hardware required.

Key patterns shown
------------------
* @api_device() on nested classes → auto-discovered children
* ChildDevice.as_child(**attrs) → compact declaration of N identical children
* connect() on child classes → called automatically after parent connects,
  self._parent is already set so hardware handles are accessible
* Properties, commands and data sources work identically on every level
* State is returned as a nested dict matching the hierarchy
* PATCH and commands work on any node via path routing
  e.g.  PATCH /api/v2/devices/multi_device/subsystem/ch_x
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import AsyncIterator, Dict, Any, Optional, TYPE_CHECKING

from ..base import Device, ChildDevice, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reusable channel type (defined OUTSIDE the parent hierarchy)
# ---------------------------------------------------------------------------

@api_device()
class sim_channel(ChildDevice):
    """Simulated signal channel — reusable base for individual channels.

    Demonstrates:
    - Properties with min/max/unit
    - A command
    - connect() that accesses self._parent hardware

    Used via as_child() inside multi_device and subsystem.
    """

    # Class-level attribute overridden by as_child() to differentiate channels.
    # The root device stores a simple shared "hardware" dict and this index
    # selects which slot to read/write.
    _hw_index: int = 0

    def connect(self) -> bool:
        """Grab a reference to our slice of the parent's simulated hardware."""
        # Walk up to the root to find shared hw state.
        # In a real driver this would be something like:
        #   self._hw_ch = self._parent._hw.channels[self._hw_index]
        root = self
        while hasattr(root, "_parent"):
            root = root._parent
        self._root = root   # keep a shortcut for property access
        logger.debug(f"{self.id}: sim_channel connected (hw_index={self._hw_index})")
        return True

    # --- Properties ---

    @api_property(min=0.0, max=10.0, unit="V", doc="Output amplitude")
    def amplitude(self) -> float:
        """Simulated amplitude stored in root's hw_state."""
        return self._root._hw_state["channels"][self._hw_index]["amplitude"]

    @amplitude.setter
    def amplitude(self, value: float) -> None:
        self._root._hw_state["channels"][self._hw_index]["amplitude"] = value

    @api_property(choices=["DC", "AC", "GND"], doc="Input coupling mode")
    def coupling(self) -> str:
        return self._root._hw_state["channels"][self._hw_index]["coupling"]

    @coupling.setter
    def coupling(self, value: str) -> None:
        self._root._hw_state["channels"][self._hw_index]["coupling"] = value

    # --- Commands ---

    @api_command(doc="Zero the channel offset")
    def zero(self) -> None:
        """Reset amplitude to 0."""
        self.amplitude = 0.0

    # --- Data sources ---

    @api_data(doc="Continuous sine-wave stream for this channel")
    async def wave(self) -> AsyncIterator[Frame]:
        """Yield a sine-wave frame every 50 ms."""
        try:
            while True:
                t = time.monotonic()
                amp = self.amplitude
                n = 64
                samples = [amp * math.sin(2 * math.pi * (i / n) + t) for i in range(n)]
                yield {"series": [{"name": self.id, "data": samples}]}
                await asyncio.sleep(0.05)
        finally:
            logger.debug(f"{self.id}: wave stream stopped")

    @wave.plot()
    def wave_plot(self) -> Dict[str, Any]:
        return {
            "title": f"Channel {self.id}",
            "x-label": "Sample",
            "y-label": "Voltage (V)",
            "x-values": list(range(64)),
        }


# ---------------------------------------------------------------------------
# Sub-system: a ChildDevice that itself owns children
# ---------------------------------------------------------------------------

@api_device()
class sim_subsystem(ChildDevice):
    """A sub-system owning two grandchild channels.

    Demonstrates a three-level hierarchy:
        root → subsystem → ch_x / ch_y

    The grandchildren are declared with as_child() using different hw_index
    values so they read/write different slots in the shared hardware table.
    """

    # Grandchildren declared at class level — discovered automatically.
    # hw_index 4 and 5 so they don't overlap with root-level ch_a (0) / ch_b (1).
    ch_x = sim_channel.as_child(_hw_index=4)
    ch_y = sim_channel.as_child(_hw_index=5)

    def connect(self) -> bool:
        logger.debug(f"{self.id}: subsystem connected")
        return True

    @api_property(choices=["idle", "running", "error"], doc="Subsystem operating mode")
    def mode(self) -> str:
        return self._parent._hw_state["subsystem_mode"]

    @mode.setter
    def mode(self, value: str) -> None:
        self._parent._hw_state["subsystem_mode"] = value

    @api_command(doc="Reset the subsystem to idle mode")
    def reset(self) -> None:
        """Set mode back to idle."""
        self.mode = "idle"


# ---------------------------------------------------------------------------
# Root composite device
# ---------------------------------------------------------------------------

@api_device()
class multi_device(Device):
    """Simulated multi-level composite device.

    Tree structure::

        multi_device
        ├── channel_a   (sim_channel, hw_index=0)
        ├── channel_b   (sim_channel, hw_index=1)
        └── subsystem   (sim_subsystem)
              ├── ch_x  (sim_channel, hw_index=4)
              └── ch_y  (sim_channel, hw_index=5)

    State is returned as a nested dict, e.g.::

        {
            "status_msg": "ok",
            "channel_a": {"amplitude": 1.0, "coupling": "DC"},
            "channel_b": {"amplitude": 2.0, "coupling": "AC"},
            "subsystem": {
                "mode": "idle",
                "ch_x": {"amplitude": 0.0, "coupling": "DC"},
                "ch_y": {"amplitude": 0.0, "coupling": "DC"},
            },
        }
    """

    config_template = {
        "polling_interval": 500,
    }

    # --- Children declared at class level ---
    # Two top-level channels via as_child():
    channel_a = sim_channel.as_child(_hw_index=0)
    channel_b = sim_channel.as_child(_hw_index=1)

    # A sub-system (itself has children ch_x, ch_y):
    @api_device()
    class subsystem(sim_subsystem):
        """Subsystem override — no extra properties, just registers as child."""
        pass

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)

        # Shared simulated hardware state — in a real driver this would be
        # the SDK handle / network connection / shared memory.
        self._hw_state: Dict[str, Any] = {
            "channels": [
                {"amplitude": float(i), "coupling": "DC"}
                for i in range(8)
            ],
            "subsystem_mode": "idle",
        }

    def connect(self) -> bool:
        """Simulate connecting to hardware."""
        logger.info(f"{self.id}: multi_device connected (simulated)")
        return True

    async def disconnect(self) -> bool:
        logger.info(f"{self.id}: multi_device disconnected")
        return True

    # --- Root-level properties ---

    @api_property(doc="Human-readable status message from the device")
    def status_msg(self) -> str:
        """Always 'ok' for this simulation."""
        return "ok"

    # --- Root-level commands ---

    @api_command(doc="Zero all channels simultaneously")
    def zero_all(self) -> str:
        """Set every channel's amplitude to 0.0."""
        for ch in self._hw_state["channels"]:
            ch["amplitude"] = 0.0
        return "all channels zeroed"
