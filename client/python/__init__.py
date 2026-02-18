from __future__ import annotations
import sys, types
from typing import Optional
from .labhub import Hub, Devices, Server, connect as _connect

_HUB: Optional[Hub] = None
devices: Optional[Devices] = None
server: Optional[Server] = None


def connect(host="127.0.0.1", port=8212) -> bool:
    """
    Connect to a LabHub server.

    After calling this, use:
      labhub.devices   - access and control devices
      labhub.server    - server administration

    Returns True on success.
    """
    global _HUB, devices, server
    hub, devs, srv = _connect(host, port)
    _HUB = hub
    mod = sys.modules[__name__]
    mod.devices = devs
    mod.server = srv
    return True


class _LabHubModule(types.ModuleType):
    def __repr__(self):
        if _HUB is None:
            lines = [
                "labhub (not connected)",
                "",
                "Usage:",
                "  import client.python as labhub",
                "  labhub.connect(host, port)",
                "  print(labhub)                  # show this overview",
                "  print(labhub.devices)          # list connected devices",
                "  print(labhub.server)           # list server operations",
            ]
            return "\n".join(lines)

        host = _HUB._host_port()
        n = len(devices) if devices else 0
        lines = [f"labhub @ {host}  ({n} device{'s' if n != 1 else ''} connected)"]
        lines.append("")

        if devices and len(devices) > 0:
            lines.append("Devices:")
            for dev_id, proxy in devices:
                kind = proxy._spec.get("kind", "")
                doc = (proxy._spec.get("doc") or "").strip()
                label = f".devices.{dev_id}"
                info = f"[{kind}]" if kind else ""
                desc = f"  {doc}" if doc else ""
                lines.append(f"  {label.ljust(32)} {info}{desc}")
            lines.append("")

        lines.append("Server admin:  print(labhub.server) for full list")
        lines.append("")
        lines.append("Quick start:")
        lines.append("  d = labhub.devices.DEVICE_ID   # get a device")
        lines.append("  print(d)                        # see its properties & commands")
        lines.append("  d.property = value              # set a property")
        lines.append("  d.command(args)                 # run a command")
        return "\n".join(lines)

    __str__ = __repr__


sys.modules[__name__].__class__ = _LabHubModule

__doc__ = "labhub: call connect(host, port) to get started."
