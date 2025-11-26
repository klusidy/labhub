from __future__ import annotations
import sys, types
from typing import Optional
from .client import Hub, connect as _connect

# We keep a process-global hub. The module proxies attribute access to it.
_HUB: Optional[Hub] = None

def connect(host="127.0.0.1", port=8212) -> Hub:
    """Connect to a running LabHub and update module-level help() output."""
    global _HUB
    _HUB = _connect(host, port)
    _update_module_surface()
    return _HUB

def _update_module_surface():
    """Expose devices by id on the module and refresh the module docstring."""
    mod = sys.modules[__name__]
    if _HUB is None:
        mod.__doc__ = "labhub: connect(host, port) to list devices."
        return
    # attach proxies as attributes by device id
    for name, proxy in _HUB.devices().items():
        setattr(mod, name, proxy)
    # update module doc so help(labhub) prints the listing
    mod.__doc__ = _HUB.describe()

def __getattr__(name: str):
    """Delegate attribute lookups to the connected Hub instance (by id only)."""
    if name == "_HUB":
        raise AttributeError
    if _HUB is None:
        raise AttributeError("Not connected. Call labhub.connect(...) first.")
    # Allow calling repr(help)-like string via labhub._describe if someone needs it
    if name == "_describe":
        return _HUB.describe
    # device by id?
    devs = _HUB.devices()
    if name in devs:
        return devs[name]
    if name == "snapshot":
        return _HUB.snapshot
    raise AttributeError(name)


class _LabHubClientModule(types.ModuleType):
    def __repr__(self):
        if _HUB is None:
            return "labhub (not connected; call connect(...))"
        return super().__repr__() + "\n" +  _HUB.describe()
    __str__ = __repr__

sys.modules[__name__].__class__ = _LabHubClientModule

# Make help(labhub) show device list (module docstring) even before connect()
__doc__ = "labhub: connect(host, port) to list devices."
