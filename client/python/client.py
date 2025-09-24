from __future__ import annotations
from typing import Any, Dict, Optional, List
import httpx
from urllib.parse import urlparse
import time
import json
import urllib
import types 


# ------------------------- Formatting helpers -------------------------

def _fmt_param_line(p: Dict[str, Any], current: Any) -> str:
    #   .voltage: float = 15.5  # Voltage on the output pin
    name = p["name"]
    typ  = p.get("type") or _infer_type_from_spec(p) or "Any"
    cur  = repr(current)
    doc  = p.get("doc") or ""
    return f"  .{name}: {typ} = {cur}" + (f"  # {doc}" if doc else "")

def _fmt_param_details(p: Dict[str, Any]) -> str:
    # Detailed help block with ranges, choices, fields...
    lines: List[str] = []
    name = p["name"]
    typ  = p.get("type") or _infer_type_from_spec(p) or "Any"
    hdr  = f"{name}: {typ}"
    if p.get("unit"):
        hdr += f" [{p['unit']}]"
    ro = "read-only" if p.get("read_only") else "read-write"
    lines.append(hdr + f"  ({ro})")
    # constraints
    rng = []
    if p.get("min") is not None: rng.append(f"min={p['min']}")
    if p.get("max") is not None: rng.append(f"max={p['max']}")
    if p.get("step") is not None:    rng.append(f"step={p['step']}")
    if p.get("default") is not None: rng.append(f"default={p['default']!r}")
    if rng: lines.append("  " + "; ".join(rng))
    if p.get("choices"):
        lines.append(f"  choices: {p['choices']}")
    if p.get("fields"):  # composite param
        lines.append("  fields:")
        if isinstance(p["fields"], dict):
            for fname, fspec in p["fields"].items():
                fline = f"    - {fname}"
                fd = fspec.get("doc")
                if fspec.get("unit"): fline += f" [{fspec['unit']}]"
                if fd: fline += f"  # {fd}"
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
        # deduce common type within choices
        types = {type(x).__name__ for x in p["choices"]}
        if len(types) == 1:
            t = list(types)[0]
            return f"Literal[{', '.join(repr(x) for x in p['choices'])}]" if t == "str" else t
        return "Any"
    # fall back from min/max presence
    if p.get("min") is not None or p.get("max") is not None:
        return "float"
    return None

def _fmt_cmd_sig(cname: str, args_spec: Dict[str, Any]) -> str:
    parts = []
    #print("  - inside _fmt_cmd_sig")
    #print(cname)
    #print(args_spec)
    for spec in args_spec:
        name     = spec.get("name", "unknown")
        required = spec.get("required", True)
        default  = spec.get("default")
        typ      = spec.get("type", "Any")
        if required:
            parts.append(f"{name}: {typ}")
        else:
            parts.append(f"{name}: {typ} = {default!r}")
    return f"{cname}(" + ", ".join(parts) + ")"

# ------------------------- Proxies -------------------------

class PropertyProxy:
    """
    A device parameter proxy. help(obj) prints detailed spec; str(obj) prints the current value.
    """
    def __init__(self, hub: "Hub", dev_id: str, name: str, spec: Dict[str, Any]):
        self._hub   = hub
        self._id    = dev_id
        self._name  = name
        self._spec  = spec
        # Detailed doc for help(...)
        self.__doc__ = _fmt_param_details(spec)

    # user-facing value helpers
    def get(self) -> Any:
        return self._hub._get_param(self._id, self._name)

    def set(self, value: Any) -> None:
        if self._spec.get("read_only"):
            raise AttributeError(f"'{self._name}' is read-only")
        self._hub._patch(f"/api/v1/devices/{self._id}", json={"properties": {self._name: value}})
        self._hub.refresh_device(self._id)

    # make assignment work: device.param = x (DeviceProxy.__setattr__ calls set())
    # pretty-printing
    def __str__(self) -> str:
        # value-only for printing/formatting
        return str(self.get())

    def __repr__(self) -> str:
        # spec + current value on top line
        p = self._spec
        name = p["name"]
        typ  = p.get("type") or _infer_type_from_spec(p) or "Any"
        hdr  = f"{name}: {typ}"
        if p.get("unit"): hdr += f" [{p['unit']}]"
        ro = "read-only" if p.get("read_only") else "read-write"
        # constraints
        bits = []
        if p.get("min") is not None: bits.append(f"min={p['min']}")
        if p.get("max") is not None: bits.append(f"max={p['max']}")
        if p.get("step") is not None:    bits.append(f"step={p['step']}")
        if p.get("default") is not None: bits.append(f"default={p['default']!r}")
        if p.get("choices"):             bits.append(f"choices={p['choices']}")
        constraints = ("  " + "; ".join(bits)) if bits else ""
        val = self.get()
        body = (p.get("doc") or "").strip()
        return f"{hdr}  ({ro})\n  value={val!r}{constraints}\n\n{body}".rstrip()
    
    # conversions
    def __bool__(self):  return bool(self.get())
    def __int__(self):   return int(self.get())
    def __float__(self): return float(self.get())

    # arithmetic forwarders (return plain Python numbers/strings, not a proxy)
    def _v(self): return self.get()
    def __add__(self, other):      return self._v() + other
    def __radd__(self, other):     return other + self._v()
    def __sub__(self, other):      return self._v() - other
    def __rsub__(self, other):     return other - self._v()
    def __mul__(self, other):      return self._v() * other
    def __rmul__(self, other):     return other * self._v()
    def __truediv__(self, other):  return self._v() / other
    def __rtruediv__(self, other): return other / self._v()
    def __floordiv__(self, other): return self._v() // other
    def __rfloordiv__(self, other):return other // self._v()
    def __mod__(self, other):      return self._v() % other
    def __rmod__(self, other):     return other % self._v()
    def __pow__(self, other):      return self._v() ** other
    def __rpow__(self, other):     return other ** self._v()
    def __neg__(self):             return -self._v()
    def __pos__(self):             return +self._v()
    # comparisons
    def __eq__(self, other):       return self._v() == (other.get() if isinstance(other, PropertyProxy) else other)
    def __lt__(self, other):       return self._v() <  (other.get() if isinstance(other, PropertyProxy) else other)
    def __le__(self, other):       return self._v() <= (other.get() if isinstance(other, PropertyProxy) else other)
    def __gt__(self, other):       return self._v() >  (other.get() if isinstance(other, PropertyProxy) else other)
    def __ge__(self, other):       return self._v() >= (other.get() if isinstance(other, PropertyProxy) else other)

    # ------------------------- DeviceSpec and CommandSpec -------------------------    
    def __iter__(self): return iter(self.get())
    def __len__(self):  return len(self.get())





class DeviceProxy:
    """
    A device proxy. help(obj) / repr(obj) prints parameters with current values and command signatures.
    """
    def __init__(self, hub: "Hub", dev_id: str, spec: Dict[str, Any]):
        self.__dict__["_hub"]  = hub
        self.__dict__["_id"]   = dev_id
        self.__dict__["_spec"] = spec

        # Build param proxies and attach as attributes by id-only
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
                cdoc  = c.get("doc") or ""
                args_spec = c.get("args", {})
                returns = c.get("returns")  # optional, if your /spec provides it
            else:
                cname, cdoc, args_spec, returns = c, "", {}, None

            def _make(cname=cname, args_spec=args_spec, cdoc=cdoc, returns=returns):
                def _cmd(**kwargs):
                    # simple arg presence check
                    for aspec in args_spec:
                        name = aspec.get("name")
                        if aspec.get("required", True) and name not in kwargs:
                            raise TypeError(f"Missing required arg '{name}' for {cname}()")
                    return self._hub._post(
                        f"/api/v1/devices/{dev_id}/commands",
                        json={"name": cname, "args": kwargs},
                    ).json()
                sig = _fmt_cmd_sig(cname, args_spec)
                if returns: sig += f" -> {returns}"
                _cmd.__doc__ = (sig + ("\n\n" + cdoc if cdoc else "")).strip()
                _cmd.__name__ = cname
                return _cmd

            cmds[cname] = _make()
        self.__dict__["_cmds"] = cmds

        # --- Data sources ---
        data_specs = spec.get("data_sources", []) or []
        #data_ns = types.SimpleNamespace()
        data_map: Dict[str, DataSourceProxy] = {}
        for ds in data_specs:
            dsp = DataSourceProxy(hub, dev_id, ds)
            #setattr(data_ns, ds["name"], dsp)
            data_map[ds["name"]] = dsp
        #self.__dict__["data_sources"] = data_ns
        self.__dict__["_data_sources"] = data_map

        # --- Plots (only for data with has_plot=True) ---
        #plots_ns = types.SimpleNamespace()
        #plots_map: Dict[str, PlotProxy] = {}
        #for name, dsp in data_map.items():
        #    if dsp._spec.get("has_plot"):
        #        pp = PlotProxy(dsp)
        #        #setattr(plots_ns, name, pp)
        #        plots_map[name] = pp
        #self.__dict__["plots"] = plots_ns
        #self.__dict__["_plots"] = plots_map


        # Device-level doc for help(...)
        self.__doc__ = self._build_doc()

    def _build_doc(self) -> str:
        lines = [f"{self._id}  [{self._spec.get('kind','?')}]"]
        if self._spec.get("doc"):
            lines.append(self._spec["doc"])

        # parameters with current values
        lines.append("\nParameters:")
        state = self._hub._ensure_state(self._id)
        for p in self._spec.get("properties", []):
            current = state["state"].get(p["name"])
            lines.append(_fmt_param_line(p, current))

        # commands with annotated properties
        if self._spec.get("commands"):
            lines.append("\nCommands:")
            for name, fn in self._cmds.items():
                lines.append(f"  .{fn.__doc__.splitlines()[0]}")  # first line: signature
                doc = fn.__doc__.split("\n", 1)
                if len(doc) > 1 and doc[1].strip():
                    lines.append("    " + doc[1].strip())

        # data sources
        if getattr(self, "_data_sources", None):
            lines.append("")
            lines.append("Data Sources:")
            for name, ds in self._data_sources.items():
                plot_hint = "  (plot)" if ds._spec.get("has_plot") else ""
                doc = ds.__doc__.strip()
                lines.append(f"  .{name} {plot_hint}")
                lines.append("    " + doc)

        # --- Plots ---
        # if getattr(self, "_plots", None):
        #     lines.append("")
        #     lines.append("Plots:")
        #     for name, pp in self._plots.items():
        #         lines.append(f"  .{name}(**kwargs) -> dict")


        return "\n".join(lines)

    # resolve commands as attributes
    def __getattr__(self, name: str): # getattr is used only when the attribute does not exist
        cmd = self.__dict__["_cmds"].get(name, None)
        if cmd: return cmd

        ds = self.__dict__["_data_sources"].get(name, None)
        if ds: return ds
        raise AttributeError(name)

    # route assignments to parameter proxies
    def __setattr__(self, name: str, value: Any):
        properties = self.__dict__.get("_properties", {})
        if name in properties:
            properties[name].set(value)
            # refresh doc (current values may change)
            self.__dict__["__doc__"] = self._build_doc()
            return
        self.__dict__[name] = value

    def __repr__(self) -> str:
        # Same as help()
        return self._build_doc()

    __str__ = __repr__

    
    # NEW: device-scoped events (state only, from /api/v1/events)
    def events(self, rate: float | int | None = None): #todo - add duration limit
        """Yield state events for this device."""
        for ev in self._hub.events(ids=[self._id], rate=rate):
            yield ev

    # NEW: binary data stream (from /api/v1/streams/{id})
    def stream(self, rate: float | int | None = None, fmt: str = "msgpack", duration: float | None = None):
        """
        Yield data chunks {'t': [...], 'y': [...]} for this device via WebSocket.
        fmt: 'msgpack' (default) or 'json'. rate: server-side throttle in Hz.
        duration: stop after N seconds (optional).
        """
        try:
            import websocket  # pip install websocket-client
        except ImportError as e:
            raise RuntimeError("Install 'websocket-client' to use DeviceProxy.stream()") from e

        url = self._hub._ws_url(f"/api/v1/streams/{self._id}", {"format": fmt, "rate": str(rate) if rate else None})
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

    # this may not be necessary - collecting can be done differently by user script
    def collect_stream(self, seconds: float, rate: float | int | None = None, fmt: str = "msgpack"):
        """Collect and return concatenated (t, y) arrays over a time window."""
        T, Y = [], []
        for ch in self.stream(rate=rate, fmt=fmt, duration=seconds):
            if "t" in ch and "y" in ch:
                T.extend(ch["t"]); Y.extend(ch["y"])
        return T, Y


# ------------------------- Data & Plot proxies -------------------------

class DataSourceProxy:
    """
    A data source proxy bound to a concrete device + source name.

    Methods:
      - get_one_frame() -> dict         # GET /devices/{id}/data/{source}/frame
      - get_plot_specs() -> dict        # GET /devices/{id}/data/{source}/plot
      - stream(limit=None, interval=None, rate=None, fmt='json') -> iterator of frames
                                        # WS  /api/v1/streams/{id}/{source}
    """
    def __init__(self, hub: "Hub", dev_id: str, spec: Dict[str, Any]):
        self._hub = hub
        self._id = dev_id
        self._name = spec.get("name") or spec.get("id") or "data"
        self._spec = spec or {}
        self.__doc__ = (self._spec.get("doc") or "").strip() or f"{self._id}.{self._name} data source"

    # --- simple pulls ---------------------------------------------------------
    def get_one_frame(self, **kwargs) -> Dict[str, Any]:
        """Fetch a single frame (JSON->Python)."""
        return self._hub._get_data_frame(self._id, self._name, kwargs)

    def get_plot_specs(self, **kwargs) -> Dict[str, Any]:
        """Fetch plotting metadata/specs (JSON->Python)."""
        return self._hub._get_plot_specs(self._id, self._name, kwargs)

    # --- streaming (synchronous iterator) ------------------------------------
    def stream(
        self,
        *,
        limit: Optional[int] = None,
        #interval: Optional[float] = None,
        rate: Optional[float | int] = None,
        fmt: str = "json",
    ):
        """
        Yield frames from WS /api/v1/streams/{device_id}/{source}?format=&rate=.

        Args:
          limit: stop after yielding this many frames (None = infinite)
          interval: client-side sleep between yields (seconds)
          rate: server throttle Hz (maps to ?rate=)
          fmt: 'json' or 'msgpack'
        """
        try:
            import websocket  # websocket-client
        except ImportError as e:
            raise RuntimeError("Install 'websocket-client' to use DataSourceProxy.stream()") from e

        url = self._hub._ws_url(
            f"/api/v1/streams/{self._id}/{self._name}",
            {"format": fmt, "rate": str(rate) if rate else None},
        )
        ws = websocket.create_connection(url)
        # If msgpack, we’ll unpack bytes; else json text
        unpack_msgpack = None
        if fmt.lower() != "json":
            try:
                import msgpack  # type: ignore
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
                chunk = json.loads(frame) if unpack_msgpack is None else unpack_msgpack(frame, raw=False)
                if chunk:
                    yield chunk
                    n += 1
                if limit is not None and n >= limit:
                    break
                #if interval:
                #    time.sleep(interval)
        finally:
            ws.close()

    def __repr__(self) -> str:
        lines = []
        lines.append(f"{self._name}: data source  {self.__doc__}")
        lines.append(f"  .get_one_frame()  returns single data frame")
        lines.append(f"  .stream(limit, rate=0.01) returns iterator that will provide up to limit frames" )
        if self._spec.get("has_plot"):
            lines.append(f"  .get_plot_specs() returns plot metadata")
        return "\n".join(lines)
    
    __str__ = __repr__




class PlotProxy:
    """
    Thin alias around a data source's .plot(**kwargs) to make plots discoverable
    as dev.plots.<name>(**kwargs).
    """
    def __init__(self, data_proxy: DataSourceProxy):
        if not data_proxy._spec.get("has_plot"):
            raise ValueError("Cannot create PlotProxy for a data source without a plot.")
        self._data = data_proxy
        self._id = data_proxy._id
        self._name = data_proxy._name
        doc = (data_proxy._spec.get("doc") or "").strip()
        self.__doc__ = f"{self._name}: plot for data source '{self._name}'\n\n{doc}"

    def __call__(self, **kwargs) -> Any:
        """Fetch the plot payload (JSON → Python)."""
        return self._data.plot(**kwargs)

    def __repr__(self) -> str:
        return f"<Plot {self._id}.{self._name}: plot(**kwargs)>"

    __str__ = __repr__



# ------------------------- Hub -------------------------

class Hub:
    def __init__(self, base_url: str):
        print(f"trying to __init__ Hub with base_url {base_url}")
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(base_url=self._base, timeout=3.0)
        self._devices: Dict[str, Dict[str, Any]] = {}   # id -> DeviceInfo
        self._specs:   Dict[str, Dict[str, Any]] = {}   # id -> DeviceSpec
        self._proxies: Dict[str, DeviceProxy]     = {}  # id -> DeviceProxy

    @property
    def base(self) -> str:
        return self._base

    def refresh(self) -> "Hub":
        #print(" - inside refresh")
        devs = self._http.get("/api/v1/devices").json()
        if not isinstance(devs, list):
            raise RuntimeError("Unexpected /devices response")
        self._devices = {d["id"]: d for d in devs}
        self._specs.clear(); self._proxies.clear()

        for d in devs:
            dev_id = d["id"]
            spec = self._http.get(f"/api/v1/devices/{dev_id}/spec").json()
            self._specs[dev_id] = spec
            self._proxies[dev_id] = DeviceProxy(self, dev_id, spec)
        return self
    
    def refresh_device(self, dev_id: str) -> Dict[str, Any]:
        """Fetch latest DeviceInfo and update local cache."""
        st = self._http.get(f"/api/v1/devices/{dev_id}").json()
        self._devices[dev_id] = st
        return st

    # ---- accessors for proxies ----
    def devices(self) -> Dict[str, DeviceProxy]:
        return dict(self._proxies)

    # ---- used by proxies ----
    def _ensure_state(self, dev_id: str) -> Dict[str, Any]:
        # st = self._devices.get(dev_id)
        # if not st:
        #     st = self._http.get(f"/api/v1/devices/{dev_id}").json()
        #     self._devices[dev_id] = st
        
        # ugly hack to always get fresh state (should be subscibed to event bus instead TODO) 
        st = self._http.get(f"/api/v1/devices/{dev_id}").json()
        self._devices[dev_id] = st

        return st

    def _get_param(self, dev_id: str, name: str):
        st = self._ensure_state(dev_id)
        return st["state"].get(name)

    def _patch(self, path: str, json: Dict[str, Any]):
        return self._http.patch(path, json=json)

    def _post(self, path: str, json: Dict[str, Any]):
        return self._http.post(path, json=json)

    def _get_data_once(self, dev_id: str, name: str, params: Dict[str, Any]) -> Any:
        url = f"/api/v1/devices/{dev_id}/data/{name}"
        resp = self._http.get(url, params=params or None)
        resp.raise_for_status()
        return resp.json()

    def _get_plot(self, dev_id: str, name: str, params: Dict[str, Any]) -> Any:
        url = f"/api/v1/devices/{dev_id}/plots/{name}"
        resp = self._http.get(url, params=params or None)
        resp.raise_for_status()
        return resp.json()


    # ---- presentation ----
    def _host_port(self) -> str:
        u = urlparse(self._base)
        return f"{u.hostname}:{u.port or 80}"
    
    # NEW: hub-wide events (state only)
    def events(self, ids: list[str] | str | None = None, rate: float | int | None = None):
        """
        Yield server-pushed state events as dicts.
        ids: device id or list; rate: max events/sec from server.
        """
        try:
            import websocket  # pip install websocket-client
        except ImportError as e:
            raise RuntimeError("Install 'websocket-client' to use Hub.events()") from e

        params = {}
        if ids:
            params["ids"] = ",".join(ids) if isinstance(ids, (list, tuple, set)) else str(ids)
        if rate:
            params["rate"] = str(rate)
        url = self._ws_url("/api/v1/events", params)
        ws = websocket.create_connection(url)
        try:
            while True:
                msg = ws.recv()
                if not msg:
                    break
                yield json.loads(msg)
        finally:
            ws.close()

    # data source helpers
    def _ws_url(self, path: str, params: Dict[str, Any] | None = None) -> str:
        base = self._base.replace("http://", "ws://").replace("https://", "wss://")
        url = base + path
        if params:
            qp = {k: v for k, v in params.items() if v is not None}
            if qp:
                url += "?" + urllib.parse.urlencode(qp)
        return url
    
    def _get_data_frame(self, dev_id: str, source: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        qp = ("?" + urllib.parse.urlencode(params)) if params else ""
        r = self._http.get(f"/api/v1/devices/{dev_id}/data/{source}/frame{qp}")
        r.raise_for_status()
        return r.json()

    def _get_plot_specs(self, dev_id: str, source: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        qp = ("?" + urllib.parse.urlencode(params)) if params else ""
        r = self._http.get(f"/api/v1/devices/{dev_id}/data/{source}/plot{qp}")
        r.raise_for_status()
        return r.json()

    def describe(self) -> str:
        lines = [f"labhub ({self._host_port()}) has the following devices:"]
        for dev_id, proxy in self._proxies.items():
            doc = proxy._spec.get("doc", "")
            doc = doc.strip() if doc is not None else "-"
            lines.append(f"  .{dev_id.ljust(18)} {doc}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.describe()

    __str__ = __repr__


# ------------------------- Top-level connect helper -------------------------

def connect(host="127.0.0.1", port=8000) -> Hub:
    base = f"http://{host}:{port}"
    try:
        hub = Hub(base).refresh()
    except Exception as e:
        raise ConnectionError(
            f"Cannot connect to LabHub at {base}. Is the tray/server running?\n{e}"
        )
    return hub


