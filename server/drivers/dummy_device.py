from __future__ import annotations
from typing import Any, Dict
from ._base import Device, api_device, api_command, api_property


@api_device("dummy")
class DummyDevice(Device):
    """
    Minimal example driver.
    Exposes one RW property 'foo' and one command 'bar()'.
    """

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options)
        properties = options.get("properties", {})

        # initialize inner state of the class
        self._foo = float(properties.get("foo", self.PROPERTIES["foo"]["default"]))
        self._bar_count = 0

    # --- lifecycle ---
    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    # --- API PROPERTIES ---
    @api_property(min=0, max=1.0, default=0.5, step=0.01)
    @property
    def foo(self) -> float:
        """Demo numeric property for testing"""
        return self._foo

    @foo.setter
    def foo(self, value: float) -> None:
        self._foo = value

    # --- API COMMANDS ---
    @api_command()
    def bar(self) -> int:
        """Demo command; increments an internal counter and return its value"""
        self._bar_count += 1
        return self._bar_count

    # # --- setters ---
    # async def apply_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
    #     #print(" -- DummyDevice.apply_params \n", params)
    #     if "foo" in params:

    #         v = float(params["foo"]) # todo make sure what structure you are getting
    #         # clamp to instance limits
    #         v = max(self._min, min(self._max, v))
    #         self._foo = v
    #     return await self.read_state()

    # # --- commands ---
    # async def run_command(self, name: str, args: Dict[str, Any] | None = None):
    #     args = args or {}
    #     if name == "bar":
    #         self._bar_count += 1
    #         # return something useful for testing
    #         return {"ok": True, "bar_count": self._bar_count, "foo": self._foo}
    #     raise RuntimeError(f"Unknown command '{name}'")
