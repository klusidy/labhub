from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Callable, Optional, Mapping, get_type_hints, TYPE_CHECKING
import inspect
from concurrent.futures import ThreadPoolExecutor
from .decorators import api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ..device_manager import DeviceManager
    from ..schemas import DeviceSpec

# Global fallback executor (used if device created without manager)
_fallback_executor = ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="fallback_worker"
)

logger = logging.getLogger("labhub.drivers._base")


# --- base class for a device driver --------------------------------
class Device:
    """Abstract async device interface."""

    _api_driver: str = "device"
    _api_properties: Dict[str, Dict[str, Any]] = {}   # per subclass
    _api_commands: Dict[str, Dict[str, Any]] = {}     # per subclass
    _api_data_sources: Dict[str, Dict[str, Any]] = {} # per subclass
    _api_children: Dict[str, type] = {}               # per subclass — child Device classes
    _config_template: Dict[str, Any] = {}             # per subclass

    def __init_subclass__(cls, api_alias: Optional[str] = None):
        """Called when a subclass is defined (not initialized).

        Scans for @api_command, @api_property, @api_data and nested @api_device
        child classes.  Merges parent metadata first so empty subclasses and
        as_child() copies inherit everything from their base class.
        """
        super().__init_subclass__()

        # --- Merge parent metadata through MRO so subclasses inherit API ---
        # reversed() so most-derived class wins on name collision.
        # _api_children is also merged so that subclassing a ChildDevice
        # (e.g. `class subsystem(sim_subsystem): pass`) keeps grandchildren.
        inherited_properties: Dict[str, Any] = {}
        inherited_commands: Dict[str, Any] = {}
        inherited_data_sources: Dict[str, Any] = {}
        inherited_children: Dict[str, type] = {}
        for base in reversed(cls.__mro__[1:]):          # skip cls itself
            if "_api_properties" in base.__dict__:
                inherited_properties.update(base.__dict__["_api_properties"])
            if "_api_commands" in base.__dict__:
                inherited_commands.update(base.__dict__["_api_commands"])
            if "_api_data_sources" in base.__dict__:
                inherited_data_sources.update(base.__dict__["_api_data_sources"])
            if "_api_children" in base.__dict__:
                inherited_children.update(base.__dict__["_api_children"])

        # Start with inherited, then overlay with this class's own declarations
        commands = dict(inherited_commands)
        properties = dict(inherited_properties)
        data_sources = dict(inherited_data_sources)
        child_classes: Dict[str, type] = dict(inherited_children)

        for name, attr in cls.__dict__.items():
            # --- @api_command decorated methods ---
            if callable(attr) and hasattr(attr, "_api_command_meta"):
                command_meta = getattr(attr, "_api_command_meta", {})
                signature = inspect.signature(attr)
                type_hints = get_type_hints(attr)

                command: Dict[str, Any] = {}
                command["doc"] = command_meta.get(
                    "doc",
                    "No doc provided. Fill in doc string of decorated method in device driver.",
                )
                command["returns"] = (
                    type_hints.get("return", "Any").__name__
                    if "return" in type_hints
                    else "Any"
                )
                command["method"] = name
                command["args"] = [
                    {
                        "name": p.name,
                        "type": type_hints.get(p.name),
                        "default": (
                            p.default
                            if p.default is not inspect.Parameter.empty
                            else None
                        ),
                    }
                    for p in signature.parameters.values()
                    if p.name != "self"
                ]
                event_commands = getattr(attr, "_api_subcommands", {})
                command["events"] = {
                    event_name: sub_name
                    for event_name, sub_name in event_commands.items()
                }
                commands[attr._api_command_name] = command

            # --- @api_property decorated properties ---
            if isinstance(attr, property) and hasattr(attr.fget, "_api_property_meta"):
                fget, fset = attr.fget, attr.fset
                get_hint = get_type_hints(fget).get("return", "Any")
                prop_meta = getattr(fget, "_api_property_meta", {})

                prop: Dict[str, Any] = {}
                prop["doc"] = prop_meta.get(
                    "doc",
                    "No doc provided. Fill in doc string of decorated property in device driver.",
                )
                prop["type"] = get_hint
                prop["read_only"] = fset is None
                prop["min"] = prop_meta.get("min", None)
                prop["max"] = prop_meta.get("max", None)
                prop["step"] = prop_meta.get("step", None)
                prop["choices"] = prop_meta.get("choices", None)
                prop["unit"] = prop_meta.get("unit", None)
                properties[fget._api_property_name] = prop

            # --- @api_data descriptors ---
            if isinstance(attr, api_data):
                data_source_meta = getattr(attr, "_api_data_meta", {})
                data_source: Dict[str, Any] = {}
                data_source["doc"] = data_source_meta.get(
                    "doc",
                    "No doc provided. Fill in doc string of decorated property in device driver.",
                )
                data_source["has_plot"] = attr._plot_fn is not None
                data_source["kind"] = data_source_meta.get("kind", "timeseries")
                data_sources[attr._api_data_name] = data_source

            # --- Nested Device subclasses decorated with @api_device() ---
            # These become child devices instantiated automatically after connect().
            if (
                isinstance(attr, type)
                and issubclass(attr, Device)
                and attr is not Device
                and hasattr(attr, "_api_device_meta")
            ):
                child_classes[name] = attr

        cls._api_commands = commands
        cls._api_properties = properties
        cls._api_data_sources = data_sources
        cls._api_children = child_classes          # own-only, NOT inherited
        cls._config_template = cls.__dict__.get("config_template", {})

    # ------------------------------------------------------------------
    # Factory / root-device lifecycle
    # ------------------------------------------------------------------

    @classmethod
    async def create(
        cls,
        dev_id: str,
        options: dict[str, object],
        manager: Optional[DeviceManager] = None,
    ):
        """Create and initialize a root device instance.

        Args:
            dev_id:   Device identifier
            options:  Configuration options from config.yaml
            manager:  DeviceManager instance (provides executor)

        Notes:
            - Connects to hardware, then auto-inits declared child devices.
            - Property defaults are loaded from the profile (monitor.py).
        """
        self = cls(dev_id, options, manager)
        await self._connect()
        if self._status != "connected":
            logger.warning(
                f"Device '{dev_id}' failed to connect (status: {self._status})"
            )
        return self

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """Initialise a root device.

        Args:
            dev_id:   Unique device identifier from config.yaml
            options:  Full device config dict (includes "driver" key)
            manager:  Reference to DeviceManager (executor, event bus)
        """
        self.id = dev_id
        self.options = options
        self._api_driver = options.get("driver", "unknown")
        self._manager = manager
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Any] = {}
        self.polling_interval = options.get("polling_interval", 1000)  # ms
        self._status = "disconnected"
        self._poll_error_count = 0
        self.children: Dict[str, Device] = {}   # populated by _init_children()

    # ------------------------------------------------------------------
    # Child-device helpers (used by ChildDevice and _init_children)
    # ------------------------------------------------------------------

    def _init_as_child(self, child_id: str, parent: Device) -> None:
        """Set up this instance as a child device owned by *parent*.

        Shares the parent's lock so all operations on the same physical
        hardware bus are mutually exclusive.  Call from ChildDevice.__init__
        instead of super().__init__().
        """
        self.id = child_id
        self._parent = parent
        self._manager = parent._manager
        self._lock = parent._lock           # shared up to the root device
        self._cache: Dict[str, Any] = {}
        self._status = "connected"          # updated by _connect() → connect()
        self._poll_error_count = 0
        self.polling_interval = parent.polling_interval
        self.options = {}
        self.children: Dict[str, Device] = {}
        self._api_driver = self.__class__.__name__

    async def _init_children(self) -> None:
        """Instantiate and connect every child class declared in _api_children.

        Called automatically by _connect() after the device (or child) connects
        successfully.  Recurses: each child's _connect() will call its own
        _init_children(), giving arbitrary-depth trees.
        """
        for child_id, child_cls in self._api_children.items():
            try:
                child = child_cls(child_id, self)
                self.children[child_id] = child
                await child._connect()
                logger.debug(
                    f"{self.id}: child '{child_id}' ready (status={child._status})"
                )
            except Exception as e:
                logger.error(
                    f"{self.id}: failed to init child '{child_id}': {e}",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """Internal connect: calls connect(), sets status, inits children."""
        if asyncio.iscoroutinefunction(self.connect):
            success = await self.connect()
        else:
            success = await self._run_blocking_in_thread(self.connect)

        if success:
            self._status = "connected"
            self._poll_error_count = 0
            await self._init_children()     # auto-create declared child devices
        else:
            self._status = "disconnected"

    def connect(self) -> bool:
        """Override (sync or async) to establish the hardware connection.

        Returns:
            True if successful, False otherwise.
        """
        return True

    async def _disconnect(self) -> None:
        """Internal disconnect: calls disconnect(), sets status."""
        if asyncio.iscoroutinefunction(self.disconnect):
            success = await self.disconnect()
        else:
            success = await self._run_blocking_in_thread(self.disconnect)

        if success:
            self._status = "disconnected"
        else:
            logger.warning(f"{self.id}: disconnect reported failure")
            self._status = "unhealthy"

    def disconnect(self) -> bool:
        """Override (sync or async) to close the hardware connection.

        Returns:
            True if successful, False otherwise.
        """
        return True

    def check_status(self) -> str:
        """Return current health status string.

        Override in subclasses that can actively detect disconnection.
        """
        return self._status

    # ------------------------------------------------------------------
    # Threading
    # ------------------------------------------------------------------

    async def _run_blocking_in_thread(self, func, *args, **kwargs):
        """Run a blocking function in the shared thread-pool executor."""
        loop = asyncio.get_running_loop()
        executor = self._manager.executor if self._manager else _fallback_executor
        return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

    async def _on_device(self, func, *args, **kwargs):
        """Legacy alias for _run_blocking_in_thread (backwards compat)."""
        return await self._run_blocking_in_thread(func, *args, **kwargs)

    # ------------------------------------------------------------------
    # Property I/O
    # ------------------------------------------------------------------

    async def poll_property(self, name: str) -> Any:
        """Read one property from device hardware and update cache.

        Tracks consecutive failures; marks device unhealthy after 3.
        """
        async with self._lock:
            try:
                value = await self._run_blocking_in_thread(lambda: getattr(self, name))
                self._cache[name] = value

                if self._poll_error_count > 0:
                    logger.info(f"{self.id}: poll recovered (property '{name}')")
                    self._poll_error_count = 0
                    if self._status == "unhealthy":
                        self._status = "connected"
                        logger.info(f"{self.id}: status recovered: unhealthy → connected")

                return value

            except Exception as e:
                self._poll_error_count += 1
                logger.warning(
                    f"{self.id}: failed to poll '{name}' "
                    f"(error #{self._poll_error_count}): {e}"
                )
                if self._poll_error_count >= 3 and self._status == "connected":
                    self._status = "unhealthy"
                    logger.error(
                        f"{self.id}: marked unhealthy after "
                        f"{self._poll_error_count} consecutive polling failures"
                    )
                raise

    async def set_property(self, name: str, value: Any) -> None:
        """Set one property on the device hardware and update cache."""
        meta = getattr(self, "_api_properties", {}).get(name, {})
        clamped_value = self._coerce_clamp(meta, value)
        async with self._lock:
            await self._run_blocking_in_thread(
                lambda: setattr(self, name, clamped_value)
            )
            self._cache[name] = clamped_value

    def get_cached(self, name: str) -> Any:
        """Return the last-polled value for *name* (None if not yet polled)."""
        return self._cache.get(name, None)

    async def read_state(self) -> Dict[str, Any]:
        """Return a nested dict of all cached property values.

        Own properties are at the top level; each child device's state is
        nested under its id key::

            {
                "voltage": 3.3,       # own property
                "osc": {              # child device
                    "sampling_freq": 1e8,
                    "ch_a": {"coupling": "DC"},
                },
            }
        """
        state: Dict[str, Any] = {k: self.get_cached(k) for k in self._api_properties}
        for child_id, child in self.children.items():
            state[child_id] = await child.read_state()
        return state

    async def apply_properties(self, properties: dict) -> dict:
        """Apply a (possibly nested) properties dict.

        Top-level keys that match a child device id are routed to that child
        (value must be a dict).  All other keys are treated as own properties.
        """
        for k, v in properties.items():
            if k in self.children:
                if isinstance(v, dict):
                    await self.children[k].apply_properties(v)
                else:
                    logger.warning(
                        f"{self.id}: ignoring non-dict value for child '{k}'"
                    )
            elif k in self._api_properties:
                if self.get_cached(k) != v:
                    await self.set_property(k, v)

        await self._post_apply_properties(properties)
        return await self.read_state()

    async def _post_apply_properties(self, properties: dict) -> None:
        """Hook called after apply_properties completes.

        Override to handle composite/derived properties that cannot be mapped
        1:1 onto individual api_property setters.
        """
        pass

    def _coerce_clamp(self, spec: Dict[str, Any], value: Any) -> Any:
        """Best-effort type coercion + bounds/choices enforcement."""
        t = spec.get("type") or Any
        try:
            if t == int:
                value = int(value)
            elif t == float:
                value = float(value)
            elif t == bool:
                value = bool(value)
            elif t == str:
                value = str(value)
        except Exception:
            pass
        if "min" in spec and spec["min"] is not None and isinstance(value, (int, float)):
            value = max(spec["min"], value)
        if "max" in spec and spec["max"] is not None and isinstance(value, (int, float)):
            value = min(spec["max"], value)
        if "choices" in spec and spec["choices"]:
            if value not in spec["choices"]:
                value = spec["choices"][0]
        return value

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def run_command(self, name: str, args: Dict[str, Any] | None = None):
        """Execute a device command by name.

        Sync commands run in the thread pool; async commands run directly.
        Both acquire the exclusive lock to prevent collision with property I/O.
        """
        args = args or {}
        if hasattr(self, name) and callable(fn := getattr(self, name)):
            async with self._lock:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(**args)
                else:
                    return await self._run_blocking_in_thread(lambda: fn(**args))
        raise RuntimeError(
            f"Method '{name}' specified in _api_commands not found in the class"
        )

    # ------------------------------------------------------------------
    # Data source accessors
    # ------------------------------------------------------------------

    def list_data_sources(self) -> Dict[str, Dict[str, Any]]:
        """Return the per-class data-source registry (name → spec)."""
        return dict(self.__class__._api_data_sources)

    def get_datasource(self, name: str):
        """Return the DataSource instance for *name*."""
        spec = self.__class__._api_data_sources.get(name)
        if not spec:
            raise KeyError(
                f"Unknown data source '{name}' for {self.__class__.__name__}"
            )
        return getattr(self, name)

    # ------------------------------------------------------------------
    # Spec building
    # ------------------------------------------------------------------

    @classmethod
    def _build_spec_from_class(cls, dev_id: str, driver: str = None) -> "DeviceSpec":
        """Build a DeviceSpec from class-level metadata only (no instance needed).

        Works for disconnected devices and for child classes declared via
        nested class or as_child().  Recurses into _api_children.

        Args:
            dev_id: The id to embed in the returned spec.
            driver: Override for the driver field (defaults to class name).
        """
        from typing import get_args
        from ..schemas import (
            DeviceSpec,
            PropertySpec,
            CommandSpec,
            DataSourceSpec,
            ArgSpec,
        )

        # --- Properties ---
        properties = []
        for name, meta in cls._api_properties.items():
            if meta.get("type", "Any") == "Any":
                logger.debug(
                    f"Property {cls.__name__}.{name} has type 'Any' — skipping spec"
                )
                continue
            properties.append(
                PropertySpec(
                    name=name,
                    read_only=bool(meta.get("read_only", False)),
                    unit=meta.get("unit"),
                    type=meta.get("type", object).__qualname__,
                    min=meta.get("min"),
                    max=meta.get("max"),
                    choices=meta.get("choices"),
                    fields=meta.get("fields"),
                    doc=meta.get("doc"),
                )
            )

        # --- Commands ---
        cmds = []
        for cname, cinfo in cls._api_commands.items():
            args = []
            for a in cinfo.get("args", []):
                a_type = a.get("type", object)
                if a_type is None:
                    logger.warning(
                        f"Command {cname} missing type hint for arg {a}."
                    )
                    continue
                qualname = a_type.__qualname__
                if qualname == "Literal":
                    choices = get_args(a["type"])
                    type_str = type(choices[0]).__qualname__
                else:
                    choices = None
                    type_str = qualname
                args.append(
                    ArgSpec(
                        name=a.get("name"),
                        type=type_str,
                        default=a.get("default"),
                        required=a.get("default", None) is None,
                        choices=choices,
                    )
                )
            cmds.append(
                CommandSpec(
                    name=cname,
                    args=args,
                    doc=cinfo.get("doc", ""),
                    events=cinfo.get("events", {}),
                )
            )

        # --- Data sources ---
        dss = []
        for dsname, dsinfo in cls._api_data_sources.items():
            dss.append(
                DataSourceSpec(
                    name=dsname,
                    has_plot=dsinfo.get("has_plot", False),
                    doc=dsinfo.get("doc", ""),
                    kind=dsinfo.get("kind", "timeseries"),
                )
            )

        # --- Children (recursive) ---
        children = {
            child_id: child_cls._build_spec_from_class(child_id)
            for child_id, child_cls in cls._api_children.items()
        }

        dev_meta = cls.__dict__.get("_api_device_meta") or {}
        logger.debug(
            f"Spec built for '{dev_id}' ({cls.__name__}): "
            f"{len(properties)} props, {len(cmds)} cmds, "
            f"{len(dss)} sources, {len(children)} children"
        )

        return DeviceSpec(
            id=dev_id,
            driver=driver or cls.__name__,
            doc=dev_meta.get("doc", ""),
            properties=properties,
            commands=cmds,
            data_sources=dss,
            children=children,
        )

    def build_spec(self, dev_id: str) -> "DeviceSpec":
        """Build DeviceSpec for this device instance.

        Delegates to the classmethod so the spec is consistent whether the
        device is connected or not.
        """
        return type(self)._build_spec_from_class(dev_id, driver=self._api_driver)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True if status is 'connected' (backwards compatibility)."""
        return self._status == "connected"

    # ------------------------------------------------------------------
    # Profile helpers (apply_properties_from_spec used by monitor/loader)
    # ------------------------------------------------------------------

    async def apply_properties_from_spec(
        self, resolved_props: dict, readout_props: dict
    ) -> None:
        """Apply resolved + readout properties from profile loader.

        resolved_props: {name: value}  — write to hardware
        readout_props:  {name: ...}    — read current value from hardware into cache
        """
        for name, value in resolved_props.items():
            try:
                await self.set_property(name, value)
            except Exception as e:
                logger.warning(f"{self.id}: failed to set '{name}' = {value}: {e}")

        for name in readout_props:
            try:
                await self.poll_property(name)
            except Exception as e:
                logger.warning(f"{self.id}: failed to readout '{name}': {e}")


# ---------------------------------------------------------------------------
# ChildDevice — base class for sub-devices owned by a parent device
# ---------------------------------------------------------------------------

class ChildDevice(Device):
    """Base class for child/sub-devices that are owned by a parent device.

    Child devices share the parent's hardware connection and lock.  They are
    declared as nested classes decorated with ``@api_device()`` and are
    automatically instantiated when the parent (or ancestor) connects::

        @api_device()
        class red_pitaya(Device):

            @api_device()
            class osc(ChildDevice):
                \"\"\"Oscilloscope module\"\"\"

                @api_device()
                class ch_a(osc_channel):   # osc_channel defined elsewhere
                    _hw_channel = 0

                @api_property(unit="Hz")
                def sampling_freq(self) -> float:
                    return self._parent._hw.osc.get_decimation()

    For identical sub-devices that only differ by a class-level attribute, use
    the ``as_child()`` shorthand instead of writing empty subclasses::

        ch_a = osc_channel.as_child(_hw_channel=0)
        ch_b = osc_channel.as_child(_hw_channel=1)

    Child devices access the parent via ``self._parent``.  Hardware handles
    should be stored in ``connect()`` which is called after the parent is ready.
    Children never call ``super().__init__()`` from Device — they call
    ``self._init_as_child(child_id, parent)`` instead (or just inherit this
    class and rely on its ``__init__``).

    Options
    -------
    Child devices receive no ``options`` dict (no config.yaml entry).  If
    hardware-specific config is needed it should be a class-level attribute
    (set per subclass) or accessed via ``self._parent.options``.
    """

    def __init__(self, child_id: str, parent: Device):
        """Initialise as a child device.

        Args:
            child_id: Name within the parent (e.g. ``"ch_a"``, ``"osc"``).
            parent:   The owning device (may itself be a child).
        """
        self._init_as_child(child_id, parent)

    @classmethod
    def as_child(cls, **class_attrs) -> type:
        """Create a subclass copy with class-level attribute overrides.

        Useful for declaring N identical children without writing N empty
        subclass bodies::

            class scope_channel(ChildDevice):
                _hw_index: int = 0

                def connect(self) -> bool:
                    self._hw = self._parent._hw.channels[self._hw_index]
                    return True

            @api_device()
            class picoscope(Device):
                ch_a = scope_channel.as_child(_hw_index=0)
                ch_b = scope_channel.as_child(_hw_index=1)
                ch_c = scope_channel.as_child(_hw_index=2)
                ch_d = scope_channel.as_child(_hw_index=3)

        The attribute name in the parent class body (``ch_a``, etc.) becomes
        the child's runtime ``id``.

        Args:
            **class_attrs: Class-level attributes to set on the new type
                           (e.g. ``_hw_index=0``).
        """
        meta = dict(
            getattr(cls, "_api_device_meta", None)
            or {"doc": (cls.__doc__ or "").strip()}
        )
        new_cls = type(
            cls.__name__,
            (cls,),
            {
                "_api_device_meta": meta,
                "_api_device_name": cls.__name__,
                **class_attrs,
            },
        )
        return new_cls
