from __future__ import annotations
from typing import Any, Dict, Optional, List
import httpx
from urllib.parse import urlparse
import time
import json
import yaml
import urllib
from pathlib import Path
from datetime import datetime


# ------------------------- Formatting helpers -------------------------


def _fmt_param_line(p: Dict[str, Any], current: Any) -> str:
    #   .voltage: float = 15.5  # Voltage on the output pin
    name = p["name"]
    typ = p.get("type") or _infer_type_from_spec(p) or "Any"
    cur = repr(current)
    doc = p.get("doc") or ""
    return f"  .{name}: {typ} = {cur}" + (f"  # {doc}" if doc else "")


def _fmt_param_details(p: Dict[str, Any]) -> str:
    lines: List[str] = []
    name = p["name"]
    typ = p.get("type") or _infer_type_from_spec(p) or "Any"
    hdr = f"{name}: {typ}"
    if p.get("unit"):
        hdr += f" [{p['unit']}]"
    ro = "read-only" if p.get("read_only") else "read-write"
    lines.append(hdr + f"  ({ro})")
    rng = []
    if p.get("min") is not None:
        rng.append(f"min={p['min']}")
    if p.get("max") is not None:
        rng.append(f"max={p['max']}")
    if p.get("step") is not None:
        rng.append(f"step={p['step']}")
    if p.get("default") is not None:
        rng.append(f"default={p['default']!r}")
    if rng:
        lines.append("  " + "; ".join(rng))
    if p.get("choices"):
        lines.append(f"  choices: {p['choices']}")
    if p.get("fields"):
        lines.append("  fields:")
        if isinstance(p["fields"], dict):
            for fname, fspec in p["fields"].items():
                fline = f"    - {fname}"
                fd = fspec.get("doc")
                if fspec.get("unit"):
                    fline += f" [{fspec['unit']}]"
                if fd:
                    fline += f"  # {fd}"
                lines.append(fline)
        else:
            for fname in p["fields"]:
                lines.append(f"    - {fname}")
    if p.get("doc"):
        lines.append("")
        lines.append(p["doc"])
    return "\n".join(lines)


def _infer_type_from_spec(p: Dict[str, Any]) -> Optional[str]:
    if p.get("choices"):
        types = {type(x).__name__ for x in p["choices"]}
        if len(types) == 1:
            t = list(types)[0]
            return (
                f"Literal[{', '.join(repr(x) for x in p['choices'])}]"
                if t == "str"
                else t
            )
        return "Any"
    if p.get("min") is not None or p.get("max") is not None:
        return "float"
    return None


def _fmt_cmd_sig(cname: str, args_spec: Dict[str, Any]) -> str:
    parts = []
    for spec in args_spec:
        name = spec.get("name", "unknown")
        required = spec.get("required", True)
        default = spec.get("default")
        typ = spec.get("type", "Any")
        if required:
            parts.append(f"{name}: {typ}")
        else:
            parts.append(f"{name}: {typ} = {default!r}")
    return f"{cname}(" + ", ".join(parts) + ")"


# ------------------------- Rich callable wrapper -------------------------


class _RichCallable:
    """
    Wraps a callable so that typing its name in the REPL shows
    the signature and docstring instead of <function ...> or <bound method ...>.
    """

    def __init__(self, fn, sig: str = "", doc: str = ""):
        self._fn = fn
        self._sig = sig
        self._doc = doc
        self.__doc__ = fn.__doc__ or doc
        self.__name__ = getattr(fn, "__name__", "?")
        self.__qualname__ = getattr(fn, "__qualname__", self.__name__)

    def __call__(self, *args, **kwargs):
        return self._fn(*args, **kwargs)

    def __repr__(self) -> str:
        lines = [self._sig or f"{self.__name__}(...)"]
        if self._doc:
            for line in self._doc.strip().splitlines():
                lines.append(f"    {line}")
        return "\n".join(lines)

    __str__ = __repr__


# ------------------------- Proxies -------------------------


class PropertyProxy:
    """
    A device parameter proxy. help(obj) prints detailed spec; str(obj) prints the current value.
    """

    def __init__(self, hub: "Hub", dev_id: str, name: str, spec: Dict[str, Any]):
        self._hub = hub
        self._id = dev_id
        self._name = name
        self._spec = spec
        self.__doc__ = _fmt_param_details(spec)

    def get(self) -> Any:
        return self._hub._get_param(self._id, self._name)

    def set(self, value: Any) -> None:
        if self._spec.get("read_only"):
            raise AttributeError(f"'{self._name}' is read-only")
        self._hub._patch(
            f"/api/v2/devices/{self._id}", json={"properties": {self._name: value}}
        )
        self._hub.refresh_device(self._id)

    def __str__(self) -> str:
        return str(self.get())

    def __repr__(self) -> str:
        p = self._spec
        name = p["name"]
        typ = p.get("type") or _infer_type_from_spec(p) or "Any"
        hdr = f"{name}: {typ}"
        if p.get("unit"):
            hdr += f" [{p['unit']}]"
        ro = "read-only" if p.get("read_only") else "read-write"
        bits = []
        if p.get("min") is not None:
            bits.append(f"min={p['min']}")
        if p.get("max") is not None:
            bits.append(f"max={p['max']}")
        if p.get("step") is not None:
            bits.append(f"step={p['step']}")
        if p.get("default") is not None:
            bits.append(f"default={p['default']!r}")
        if p.get("choices"):
            bits.append(f"choices={p['choices']}")
        constraints = ("  " + "; ".join(bits)) if bits else ""
        val = self.get()
        body = (p.get("doc") or "").strip()
        lines = [f"{hdr}  ({ro})", f"  value = {val!r}{constraints}"]
        if body:
            lines.append(f"  {body}")
        if not p.get("read_only"):
            lines.append(f"")
            lines.append(f"  Usage: device.{name} = <value>  or  device.{name}.set(<value>)")
        return "\n".join(lines)

    # conversions
    def __bool__(self):
        return bool(self.get())

    def __int__(self):
        return int(self.get())

    def __float__(self):
        return float(self.get())

    # arithmetic forwarders
    def _v(self):
        return self.get()

    def __add__(self, other):
        return self._v() + other

    def __radd__(self, other):
        return other + self._v()

    def __sub__(self, other):
        return self._v() - other

    def __rsub__(self, other):
        return other - self._v()

    def __mul__(self, other):
        return self._v() * other

    def __rmul__(self, other):
        return other * self._v()

    def __truediv__(self, other):
        return self._v() / other

    def __rtruediv__(self, other):
        return other / self._v()

    def __floordiv__(self, other):
        return self._v() // other

    def __rfloordiv__(self, other):
        return other // self._v()

    def __mod__(self, other):
        return self._v() % other

    def __rmod__(self, other):
        return other % self._v()

    def __pow__(self, other):
        return self._v() ** other

    def __rpow__(self, other):
        return other ** self._v()

    def __neg__(self):
        return -self._v()

    def __pos__(self):
        return +self._v()

    # comparisons
    def __eq__(self, other):
        return self._v() == (other.get() if isinstance(other, PropertyProxy) else other)

    def __lt__(self, other):
        return self._v() < (other.get() if isinstance(other, PropertyProxy) else other)

    def __le__(self, other):
        return self._v() <= (other.get() if isinstance(other, PropertyProxy) else other)

    def __gt__(self, other):
        return self._v() > (other.get() if isinstance(other, PropertyProxy) else other)

    def __ge__(self, other):
        return self._v() >= (other.get() if isinstance(other, PropertyProxy) else other)

    def __iter__(self):
        return iter(self.get())

    def __len__(self):
        return len(self.get())


class DeviceProxy:
    """
    A device proxy. print(device) shows properties, commands, and data sources.
    """

    def __init__(self, hub: "Hub", dev_id: str, spec: Dict[str, Any]):
        self.__dict__["_hub"] = hub
        self.__dict__["_id"] = dev_id
        self.__dict__["_spec"] = spec

        # Build param proxies
        properties = {}
        for p in spec.get("properties", []):
            pr = PropertyProxy(hub, dev_id, p["name"], p)
            properties[p["name"]] = pr
            self.__dict__[p["name"]] = pr
        self.__dict__["_properties"] = properties

        # Build command callables
        cmds = {}
        for c in spec.get("commands", []):
            if isinstance(c, dict):
                cname = c["name"]
                cdoc = c.get("doc") or ""
                args_spec = c.get("args", {})
                returns = c.get("returns")
            else:
                cname, cdoc, args_spec, returns = c, "", {}, None

            def _make(cname=cname, args_spec=args_spec, cdoc=cdoc, returns=returns):
                def _cmd(*args, **kwargs):
                    # Map positional args to keyword args by position
                    for i, val in enumerate(args):
                        if i < len(args_spec):
                            kw_name = args_spec[i].get("name")
                            if kw_name:
                                kwargs[kw_name] = val
                    timeout = kwargs.pop("_timeout", None)
                    for aspec in args_spec:
                        name = aspec.get("name")
                        if aspec.get("required", True) and name not in kwargs:
                            raise TypeError(
                                f"Missing required arg '{name}' for {cname}()"
                            )
                    return self._hub._post(
                        f"/api/v2/devices/{dev_id}/commands",
                        json={"name": cname, "args": kwargs},
                        timeout=timeout,
                    ).json()

                sig = _fmt_cmd_sig(cname, args_spec)
                if returns:
                    sig += f" -> {returns}"
                _cmd.__doc__ = (sig + ("\n\n" + cdoc if cdoc else "")).strip()
                _cmd.__name__ = cname
                return _RichCallable(_cmd, sig=sig, doc=cdoc)

            cmds[cname] = _make()
        self.__dict__["_cmds"] = cmds

        # Data sources
        data_specs = spec.get("data_sources", []) or []
        data_map: Dict[str, DataSourceProxy] = {}
        for ds in data_specs:
            dsp = DataSourceProxy(hub, dev_id, ds)
            data_map[ds["name"]] = dsp
        self.__dict__["_data_sources"] = data_map

        # Build child device proxies
        for child_id, child_spec in (spec.get("children") or {}).items():
            child_path = f"{dev_id}/{child_id}"
            child_proxy = DeviceProxy(hub, child_path, child_spec)
            self.__dict__[child_id] = child_proxy

        self.__doc__ = self._build_doc()

    def _build_doc(self) -> str:
        driver = self._spec.get("driver", "?")
        root_id = self._id.split("/")[0]
        status = self._hub._devices.get(root_id, {}).get("status", "?")
        lines = [f"{self._id}  [{driver}]  status: {status}"]
        if self._spec.get("doc"):
            lines.append(self._spec["doc"])

        # properties with current values
        if self._spec.get("properties"):
            lines.append("")
            lines.append("Properties:")
            try:
                st = self._hub._ensure_state(self._id)
                state_dict = st.get("state", {}) or {}
            except Exception:
                state_dict = {}
            for p in self._spec.get("properties", []):
                current = state_dict.get(p["name"])
                lines.append(_fmt_param_line(p, current))

        # commands
        if self._spec.get("commands"):
            lines.append("")
            lines.append("Commands:")
            for name, fn in self._cmds.items():
                lines.append(f"  .{fn._sig}")
                if fn._doc:
                    lines.append(f"      {fn._doc.strip()}")

        # data sources
        if self._data_sources:
            lines.append("")
            lines.append("Data sources:")
            for name, ds in self._data_sources.items():
                plot_hint = "  (has plot)" if ds._spec.get("has_plot") else ""
                doc = (ds._spec.get("doc") or "").strip()
                lines.append(f"  .{name}{plot_hint}" + (f"  # {doc}" if doc else ""))

        # child devices
        children = self._spec.get("children") or {}
        if children:
            lines.append("")
            lines.append("Child devices:")
            for child_id, child_spec in children.items():
                child_doc = (child_spec.get("doc") or "").strip()
                lines.append(f"  .{child_id}" + (f"  # {child_doc}" if child_doc else ""))

        # usage hints
        lines.append("")
        lines.append("Tips:")
        lines.append("  device.property = value     # set a property")
        lines.append("  print(device.property)      # inspect a property in detail")
        lines.append("  device.command(args)        # run a command")

        return "\n".join(lines)

    def __getattr__(self, name: str):
        cmd = self.__dict__["_cmds"].get(name, None)
        if cmd:
            return cmd
        ds = self.__dict__["_data_sources"].get(name, None)
        if ds:
            return ds
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any):
        properties = self.__dict__.get("_properties", {})
        if name in properties:
            properties[name].set(value)
            self.__dict__["__doc__"] = self._build_doc()
            return
        self.__dict__[name] = value

    def __repr__(self) -> str:
        return self._build_doc()

    __str__ = __repr__

    def events(self, rate: float | int | None = None):
        """Yield state events for this device."""
        for ev in self._hub.events(ids=[self._id], rate=rate):
            yield ev

    def stream(
        self,
        rate: float | int | None = None,
        fmt: str = "msgpack",
        duration: float | None = None,
    ):
        """
        Yield data chunks {'t': [...], 'y': [...]} for this device via WebSocket.
        fmt: 'msgpack' (default) or 'json'. rate: server-side throttle in Hz.
        duration: stop after N seconds (optional).
        """
        try:
            import websocket
        except ImportError as e:
            raise RuntimeError(
                "Install 'websocket-client' to use DeviceProxy.stream()"
            ) from e

        url = self._hub._ws_url(
            f"/api/v2/streams/{self._id}",
            {"format": fmt, "rate": str(rate) if rate else None},
        )
        ws = websocket.create_connection(url)
        t0 = time.time()
        try:
            while True:
                frame = ws.recv()
                if not frame:
                    break
                if fmt.lower() == "json":
                    chunk = json.loads(frame)
                else:
                    try:
                        import msgpack
                    except ImportError as e:
                        ws.close()
                        raise RuntimeError("Install 'msgpack' or use fmt='json'") from e
                    chunk = msgpack.unpackb(frame, raw=False)
                if chunk:
                    yield chunk
                if duration is not None and (time.time() - t0) >= duration:
                    break
        finally:
            ws.close()

    def collect_stream(
        self, seconds: float, rate: float | int | None = None, fmt: str = "msgpack"
    ):
        """Collect and return concatenated (t, y) arrays over a time window."""
        T, Y = [], []
        for ch in self.stream(rate=rate, fmt=fmt, duration=seconds):
            if "t" in ch and "y" in ch:
                T.extend(ch["t"])
                Y.extend(ch["y"])
        return T, Y


# ------------------------- Data & Plot proxies -------------------------


class DataSourceProxy:
    """
    A data source proxy bound to a concrete device + source name.
    """

    def __init__(self, hub: "Hub", dev_id: str, spec: Dict[str, Any]):
        self._hub = hub
        self._id = dev_id
        self._name = spec.get("name") or spec.get("id") or "data"
        self._spec = spec or {}
        self.__doc__ = (
            self._spec.get("doc") or ""
        ).strip() or f"{self._id}.{self._name} data source"

    def get_one_frame(self, **kwargs) -> Dict[str, Any]:
        """Fetch a single frame (JSON->Python)."""
        return self._hub._get_data_frame(self._id, self._name, kwargs)

    def get_plot_specs(self, **kwargs) -> Dict[str, Any]:
        """Fetch plotting metadata/specs (JSON->Python)."""
        return self._hub._get_plot_specs(self._id, self._name, kwargs)

    def stream(
        self,
        *,
        limit: Optional[int] = None,
        rate: Optional[float | int] = None,
        fmt: str = "json",
    ):
        """
        Yield frames from WS /api/v2/streams/{device_id}/{source}.

        Args:
          limit: stop after yielding this many frames (None = infinite)
          rate: server throttle Hz
          fmt: 'json' or 'msgpack'
        """
        try:
            import websocket
        except ImportError as e:
            raise RuntimeError(
                "Install 'websocket-client' to use DataSourceProxy.stream()"
            ) from e

        url = self._hub._ws_url(
            f"/api/v2/streams/{self._id}/{self._name}",
            {"format": fmt, "rate": str(rate) if rate else None},
        )
        ws = websocket.create_connection(url)
        unpack_msgpack = None
        if fmt.lower() != "json":
            try:
                import msgpack
                unpack_msgpack = msgpack.unpackb
            except ImportError as e:
                ws.close()
                raise RuntimeError("Install 'msgpack' or use stream(fmt='json')") from e

        try:
            n = 0
            while True:
                frame = ws.recv()
                if not frame:
                    break
                chunk = (
                    json.loads(frame)
                    if unpack_msgpack is None
                    else unpack_msgpack(frame, raw=False)
                )
                if chunk:
                    yield chunk
                    n += 1
                if limit is not None and n >= limit:
                    break
        finally:
            ws.close()

    def __repr__(self) -> str:
        lines = [f"{self._name}: data source"]
        doc = (self._spec.get("doc") or "").strip()
        if doc:
            lines.append(f"  {doc}")
        lines.append(f"")
        lines.append(f"  .get_one_frame()             fetch single data frame")
        lines.append(f"  .stream(limit, rate=10)      iterate over data frames")
        if self._spec.get("has_plot"):
            lines.append(f"  .get_plot_specs()            fetch plot metadata")
        return "\n".join(lines)

    __str__ = __repr__


class PlotProxy:
    """
    Thin alias around a data source's plot to make plots discoverable.
    """

    def __init__(self, data_proxy: DataSourceProxy):
        if not data_proxy._spec.get("has_plot"):
            raise ValueError(
                "Cannot create PlotProxy for a data source without a plot."
            )
        self._data = data_proxy
        self._id = data_proxy._id
        self._name = data_proxy._name
        doc = (data_proxy._spec.get("doc") or "").strip()
        self.__doc__ = f"{self._name}: plot for data source '{self._name}'\n\n{doc}"

    def __call__(self, **kwargs) -> Any:
        """Fetch the plot payload (JSON -> Python)."""
        return self._data.plot(**kwargs)

    def __repr__(self) -> str:
        return f"<Plot {self._id}.{self._name}: plot(**kwargs)>"

    __str__ = __repr__


# ------------------------- Devices collection -------------------------


class Devices:
    """
    Collection of connected device proxies.

    Access devices as attributes:  devices.my_device
    Iterate over devices:          for name, dev in devices
    """

    def __init__(self, hub: "Hub"):
        self.__dict__["_hub"] = hub
        self.__dict__["_proxies"] = {}

    def _rebuild(self):
        self.__dict__["_proxies"] = dict(self._hub._proxies)

    def refresh(self) -> "Devices":
        """Re-fetch device list and specs from the server."""
        self._hub.refresh()
        self._rebuild()
        return self

    def __getattr__(self, name: str):
        proxies = self.__dict__["_proxies"]
        if name in proxies:
            return proxies[name]
        raise AttributeError(
            f"No device '{name}'. Available: {', '.join(proxies.keys()) or '(none)'}"
        )

    def __setattr__(self, name: str, value: Any):
        # prevent accidentally overwriting device proxies
        if name in self.__dict__.get("_proxies", {}):
            raise AttributeError(
                f"Cannot replace device '{name}'. Use device.property = value instead."
            )
        self.__dict__[name] = value

    def __iter__(self):
        return iter(self._proxies.items())

    def __len__(self):
        return len(self._proxies)

    def __contains__(self, name: str):
        return name in self._proxies

    def keys(self):
        return self._proxies.keys()

    def values(self):
        return self._proxies.values()

    def items(self):
        return self._proxies.items()

    def __getitem__(self, name: str):
        if name in self._proxies:
            return self._proxies[name]
        raise KeyError(name)

    def events(self, ids: list[str] | str | None = None, rate: float | int | None = None):
        """
        Yield real-time state events for devices.

        Args:
          ids:  device id or list of ids to filter (None = all devices)
          rate: max events/sec from server
        """
        yield from self._hub.events(ids=ids, rate=rate)

    def __repr__(self) -> str:
        proxies = self._proxies
        n = len(proxies)
        host = self._hub._host_port()
        if not proxies:
            return f"Devices ({host}): (none connected)\n\n  Call labhub.devices.refresh() after connecting devices."

        lines = [f"Devices ({host}): {n} connected"]
        lines.append("")
        for dev_id, proxy in proxies.items():
            kind = proxy._spec.get("kind", "")
            status = self._hub._devices.get(dev_id, {}).get("status", "?")
            doc = (proxy._spec.get("doc") or "").strip()
            label = f".{dev_id}"
            info = f"[{kind}]" if kind else ""
            if status != "connected":
                info += f" ({status})"
            desc = f"  {doc}" if doc else ""
            lines.append(f"  {label.ljust(24)} {info}{desc}")

        lines.append("")
        lines.append("Usage:")
        lines.append("  d = labhub.devices.DEVICE_ID")
        lines.append("  print(d)                      # show properties, commands")
        lines.append("  d.property = value             # set a property")
        lines.append("  d.command(args)                # run a command")
        return "\n".join(lines)

    __str__ = __repr__


# ------------------------- Server / admin -------------------------


class Server:
    """
    Server administration interface.

    Provides operations for managing the LabHub server: configuration,
    device lifecycle, profiles, logging, and monitoring.
    """

    # Methods that should be wrapped with _RichCallable for REPL display
    _public_methods = {
        "snapshot", "reload", "soft_reload", "reload_device",
        "connect_device", "disconnect_device", "config", "device_config",
        "update_device_config", "drivers", "profile", "profile_save",
        "profile_load", "loglevel", "set_loglevel", "apply_properties",
        "influx_status",
    }

    def __init__(self, hub: "Hub"):
        self._hub = hub

    def __getattr__(self, name: str):
        # Let normal attribute lookup happen first (this is only called on miss)
        raise AttributeError(name)

    def __getattribute__(self, name: str):
        val = super().__getattribute__(name)
        # Wrap public methods so REPL shows signature + docstring
        if name in Server._public_methods and callable(val):
            import inspect
            try:
                sig = str(inspect.signature(val))
            except (ValueError, TypeError):
                sig = "(...)"
            return _RichCallable(val, sig=f"{name}{sig}", doc=val.__doc__ or "")
        return val

    # ---- Snapshot ----

    def snapshot(
        self,
        folder: str = None,
        name: str = "snapshot_{now:%y%m%d_%H%M%S}",
        filetype: str = "yaml",
        content: str = "properties",
    ):
        """
        Fetch a snapshot of all device states. Optionally save to file.

        Args:
          folder:   directory to save file (None = return data only)
          name:     filename template, use {now} for timestamp
          filetype: 'yaml' or 'json'
          content:  'properties' (id -> state) or 'devices' (full info)

        Returns: dict (properties) or list (devices)
        """
        devs = self._hub._http.get("/api/v2/devices").json()

        if content == "properties":
            data = {dev["id"]: dev["state"] for dev in devs}
        elif content == "devices":
            data = devs
        else:
            raise ValueError(
                f"Invalid content format '{content}', must be 'properties' or 'devices'"
            )

        now = datetime.now()
        filename = f"{name.format(now=now)}.{filetype.lower()}"

        if folder:
            path = Path(folder)
            if path.is_dir():
                full = path / filename
                if filetype == "json":
                    with open(full, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                if filetype in ("yaml", "yml"):
                    with open(full, "w", encoding="utf-8") as f:
                        yaml.safe_dump(data, f, sort_keys=False)

        return data

    # ---- Reload ----

    def reload(self) -> Dict[str, Any]:
        """Reload all devices from config (full restart)."""
        r = self._hub._http.post("/api/v2/admin/reload")
        r.raise_for_status()
        return r.json()

    def soft_reload(self) -> Dict[str, Any]:
        """Smart reload: only restart devices whose config changed."""
        r = self._hub._http.post("/api/v2/admin/soft-reload")
        r.raise_for_status()
        return r.json()

    def reload_device(self, dev_id: str) -> Dict[str, Any]:
        """Reload a single device from config."""
        r = self._hub._http.post(f"/api/v2/admin/reload/{dev_id}")
        r.raise_for_status()
        return r.json()

    # ---- Device connect/disconnect ----

    def connect_device(self, dev_id: str) -> Dict[str, Any]:
        """Connect (enable) a device."""
        r = self._hub._http.post(f"/api/v2/admin/device/{dev_id}/connect")
        r.raise_for_status()
        return r.json()

    def disconnect_device(self, dev_id: str) -> Dict[str, Any]:
        """Disconnect (disable) a device."""
        r = self._hub._http.post(f"/api/v2/admin/device/{dev_id}/disconnect")
        r.raise_for_status()
        return r.json()

    # ---- Configuration ----

    def config(self) -> Dict[str, Any]:
        """Get current device configuration (config.yaml content)."""
        r = self._hub._http.get("/api/v2/admin/config")
        r.raise_for_status()
        return r.json()

    def device_config(self, dev_id: str) -> Dict[str, Any]:
        """Get configuration for a single device."""
        r = self._hub._http.get(f"/api/v2/admin/config/device/{dev_id}")
        r.raise_for_status()
        return r.json()

    def update_device_config(self, dev_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update configuration for a single device."""
        r = self._hub._http.put(f"/api/v2/admin/config/device/{dev_id}", json=config)
        r.raise_for_status()
        return r.json()

    def drivers(self) -> List[Dict[str, Any]]:
        """List all available device drivers."""
        r = self._hub._http.get("/api/v2/admin/drivers")
        r.raise_for_status()
        return r.json()

    # ---- Profile ----

    def profile(self) -> Dict[str, Any]:
        """Get current profile info (path, policies, raw content)."""
        r = self._hub._http.get("/api/v2/admin/profile")
        r.raise_for_status()
        return r.json()

    def profile_save(self) -> Dict[str, Any]:
        """Force an immediate profile save."""
        r = self._hub._http.post("/api/v2/admin/profile/save")
        r.raise_for_status()
        return r.json()

    def profile_load(self, file_path: str, switch_path: bool = True) -> Dict[str, Any]:
        """
        Load a profile from file and apply saved property values.

        Args:
          file_path:    path to profile YAML file
          switch_path:  if True, future saves go to this file (default True)
        """
        r = self._hub._http.post(
            "/api/v2/admin/profile/load",
            params={"file_path": file_path, "switch_path": switch_path},
        )
        r.raise_for_status()
        return r.json()

    # ---- Logging ----

    def loglevel(self, logger_name: str = None) -> str:
        """Get current log level. Optionally specify a logger name."""
        params = {}
        if logger_name:
            params["logger_name"] = logger_name
        r = self._hub._http.get("/api/v2/admin/loglevel", params=params or None)
        r.raise_for_status()
        return r.json()

    def set_loglevel(self, level: str, logger_name: str = None) -> Dict[str, Any]:
        """
        Set log level at runtime.

        Args:
          level:       DEBUG, INFO, WARNING, or ERROR
          logger_name: optional, e.g. 'labhub.drivers' (default: root)
        """
        params = {"level": level}
        if logger_name:
            params["logger_name"] = logger_name
        r = self._hub._http.post("/api/v2/admin/loglevel", params=params)
        r.raise_for_status()
        return r.json()

    # ---- Bulk property application ----

    def apply_properties(
        self, properties: Dict[str, Dict[str, Any]] = None, file_path: str = None
    ) -> Dict[str, Any]:
        """
        Bulk-apply properties to multiple devices.

        Args:
          properties: dict of {device_id: {prop: value, ...}, ...}
          file_path:  path to a YAML/JSON file with properties to apply
        """
        body = {}
        if properties:
            body["properties"] = properties
        if file_path:
            body["file_path"] = file_path
        r = self._hub._http.post("/api/v2/admin/apply_properties", json=body)
        r.raise_for_status()
        return r.json()

    # ---- InfluxDB ----

    def influx_status(self) -> Dict[str, Any]:
        """Get InfluxDB integration status and metrics."""
        r = self._hub._http.get("/api/v2/admin/influx/status")
        r.raise_for_status()
        return r.json()

    # ---- Presentation ----

    def __repr__(self) -> str:
        host = self._hub._host_port()
        lines = [f"LabHub server @ {host}"]
        lines.append("")
        lines.append("Snapshots & profiles:")
        lines.append("  .snapshot(folder, name, filetype)           Save device state snapshot")
        lines.append("  .profile()                                  Get current profile info")
        lines.append("  .profile_save()                             Force immediate profile save")
        lines.append("  .profile_load(file_path)                    Load profile from file")
        lines.append("  .apply_properties(properties)               Bulk-set properties on devices")
        lines.append("")
        lines.append("Device lifecycle:")
        lines.append("  .reload()                                   Reload all devices from config")
        lines.append("  .soft_reload()                              Smart reload (changed only)")
        lines.append("  .reload_device(dev_id)                      Reload a single device")
        lines.append("  .connect_device(dev_id)                     Connect a device")
        lines.append("  .disconnect_device(dev_id)                  Disconnect a device")
        lines.append("")
        lines.append("Configuration:")
        lines.append("  .config()                                   Get device configuration")
        lines.append("  .device_config(dev_id)                      Get single device config")
        lines.append("  .update_device_config(dev_id, config)       Update device config")
        lines.append("  .drivers()                                  List available drivers")
        lines.append("")
        lines.append("Monitoring:")
        lines.append("  .loglevel()                                 Get current log level")
        lines.append("  .set_loglevel('DEBUG'|'INFO'|'WARNING')     Set log level at runtime")
        lines.append("  .influx_status()                            Get InfluxDB status")
        return "\n".join(lines)

    __str__ = __repr__


# ------------------------- Hub (internal) -------------------------


class Hub:
    """Internal connection manager. Not exposed directly to the user."""

    def __init__(self, base_url: str):
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base,
            timeout=httpx.Timeout(5.0, read=300.0),
        )
        self._devices: Dict[str, Dict[str, Any]] = {}  # id -> DeviceInfo
        self._specs: Dict[str, Dict[str, Any]] = {}    # id -> DeviceSpec
        self._proxies: Dict[str, DeviceProxy] = {}     # id -> DeviceProxy

    @property
    def base(self) -> str:
        return self._base

    def refresh(self) -> "Hub":
        devs = self._http.get("/api/v2/devices").json()
        if not isinstance(devs, list):
            raise RuntimeError("Unexpected /devices response")
        self._devices = {d["id"]: d for d in devs}
        self._specs.clear()
        self._proxies.clear()

        for d in devs:
            dev_id = d["id"]
            spec = self._http.get(f"/api/v2/devices/{dev_id}/spec").json()
            self._specs[dev_id] = spec
            self._proxies[dev_id] = DeviceProxy(self, dev_id, spec)
        return self

    def refresh_device(self, dev_id: str) -> Dict[str, Any]:
        """Fetch latest DeviceInfo and update local cache."""
        st = self._http.get(f"/api/v2/devices/{dev_id}").json()
        self._devices[dev_id] = st
        return st

    # ---- used by proxies ----

    def _ensure_state(self, dev_id: str) -> Dict[str, Any]:
        st = self._http.get(f"/api/v2/devices/{dev_id}").json()
        self._devices[dev_id] = st
        return st

    def _get_param(self, dev_id: str, name: str):
        st = self._ensure_state(dev_id)
        return (st.get("state") or {}).get(name)

    def _patch(self, path: str, json: Dict[str, Any]):
        return self._http.patch(path, json=json)

    def _post(self, path: str, json: Dict[str, Any], timeout: float = None):
        kw = {"json": json}
        if timeout is not None:
            kw["timeout"] = timeout
        return self._http.post(path, **kw)

    def _host_port(self) -> str:
        u = urlparse(self._base)
        return f"{u.hostname}:{u.port or 80}"

    # ---- events (websocket) ----

    def events(
        self, ids: list[str] | str | None = None, rate: float | int | None = None
    ):
        """Yield server-pushed state events as dicts."""
        try:
            import websocket
        except ImportError as e:
            raise RuntimeError("Install 'websocket-client' to use events()") from e

        params = {}
        if ids:
            params["ids"] = (
                ",".join(ids) if isinstance(ids, (list, tuple, set)) else str(ids)
            )
        if rate:
            params["rate"] = str(rate)
        url = self._ws_url("/api/v2/events", params)
        ws = websocket.create_connection(url)
        try:
            while True:
                msg = ws.recv()
                if not msg:
                    break
                yield json.loads(msg)
        finally:
            ws.close()

    # ---- data helpers ----

    def _ws_url(self, path: str, params: Dict[str, Any] | None = None) -> str:
        base = self._base.replace("http://", "ws://").replace("https://", "wss://")
        url = base + path
        if params:
            qp = {k: v for k, v in params.items() if v is not None}
            if qp:
                url += "?" + urllib.parse.urlencode(qp)
        return url

    def _get_data_frame(
        self, dev_id: str, source: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        qp = ("?" + urllib.parse.urlencode(params)) if params else ""
        r = self._http.get(f"/api/v2/devices/{dev_id}/data/{source}/frame{qp}")
        r.raise_for_status()
        return r.json()

    def _get_plot_specs(
        self, dev_id: str, source: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        qp = ("?" + urllib.parse.urlencode(params)) if params else ""
        r = self._http.get(f"/api/v2/devices/{dev_id}/data/{source}/plot{qp}")
        r.raise_for_status()
        return r.json()


# ------------------------- Top-level connect helper -------------------------


def connect(host="127.0.0.1", port=8212) -> bool:
    """
    Connect to a LabHub server and return (devices, server) tuple.

    Returns True on success. After connecting, use the module-level
    labhub.devices and labhub.server objects.
    """
    base = f"http://{host}:{port}"
    try:
        hub = Hub(base).refresh()
    except Exception as e:
        raise ConnectionError(
            f"Cannot connect to LabHub at {base}. Is the server running?\n{e}"
        )

    devices = Devices(hub)
    devices._rebuild()
    server = Server(hub)
    return hub, devices, server
