from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Callable, Optional, Mapping, get_type_hints, TYPE_CHECKING
import inspect
from concurrent.futures import ThreadPoolExecutor
from .decorators import api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ..device_manager import DeviceManager

# Global fallback executor (used if device created without manager)
_fallback_executor = ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="fallback_worker"
)

logger = logging.getLogger("labhub.drivers._base")


# --- base class for a device driver --------------------------------
class Device:
    """Abstract async device interface."""

    _api_driver: str = "device"
    _api_properties: Dict[str, Dict[str, Any]] = {}  # per subclass
    _api_commands: Dict[str, Dict[str, Any]] = {}  # per subclass
    _api_data_sources: Dict[str, Dict[str, Any]] = {}  # per subclass

    def __init_subclass__(cls, api_alias: Optional[str] = None):
        """Called when a subclass is defined (not initialized).
        Scans for @api_command and @api_property decorators to auto-populate registries.
        """
        super().__init_subclass__()  # there is not superclass, but its good practice
        commands, properties, data_sources = {}, {}, {}

        for name, attr in cls.__dict__.items():  # go thrgouh all class attributes
            if callable(attr) and hasattr(attr, "_api_command_meta"):
                command_meta = getattr(attr, "_api_command_meta", {})
                signature = inspect.signature(attr)
                type_hints = get_type_hints(attr)

                command = {}
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

            if isinstance(attr, property) and hasattr(attr.fget, "_api_property_meta"):
                fget, fset = attr.fget, attr.fset
                get_hint = get_type_hints(fget).get("return", "Any")
                prop_meta = getattr(fget, "_api_property_meta", {})

                # hits for set are not used - assume same as get (todo: raise exception if not)
                set_hint = get_type_hints(fset).get("value", "Any") if fset else None
                set_params = (
                    list(inspect.signature(fset).parameters.values())[1:]
                    if fset
                    else []
                )

                prop = {}
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

            if isinstance(attr, api_data):
                data_source_meta = getattr(attr, "_api_data_meta", {})
                data_source = {}
                data_source["doc"] = data_source_meta.get(
                    "doc",
                    "No doc provided. Fill in doc string of decorated property in device driver.",
                )
                data_source["has_plot"] = attr._plot_fn is not None
                data_sources[attr._api_data_name] = data_source

        cls._api_commands = commands
        cls._api_properties = properties
        cls._api_data_sources = data_sources

    @classmethod
    async def create(
        cls,
        dev_id: str,
        options: dict[str, object],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Create and initialize device instance.

        Args:
            dev_id: Device identifier
            options: Configuration options from config.yaml
            manager: DeviceManager instance (provides executor for blocking ops)

        Returns:
            Initialized device instance

        Notes:
            - Connects to hardware
            - Property defaults applied from profile (monitor.py)
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
        """
        Initialize device with ID and options from config.yaml.

        Args:
            dev_id: Device identifier
            options: Configuration from config.yaml
            manager: DeviceManager instance (for executor access)
        """
        self.id = dev_id
        self.options = options
        self._api_driver = options.get("driver", "unknown")
        self._manager = (
            manager  # Reference to device manager (for executor, event bus, etc.)
        )
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Any] = {}  # Cached property values
        self.polling_interval = options.get("polling_interval", 1000)  # ms
        self._status = "disconnected"  # "disconnected", "connected", "unhealthy"
        self._poll_error_count = 0  # Track consecutive polling failures

    # --- lifecycle ---
    async def _connect(self) -> None:  # override
        """Internal connect method called by create()."""
        # check if sync or async connect is implemented
        if asyncio.iscoroutinefunction(self.connect):
            success = await self.connect()
        else:
            success = await self._run_blocking_in_thread(self.connect)

        if success:
            self._status = "connected"
            self._poll_error_count = 0
        else:
            self._status = "disconnected"

    def connect(self) -> bool:
        """Either sync or async method to be overwritten by subclasses.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        return True

    async def _disconnect(self) -> None:  # override
        """Internal disconnect method."""
        if asyncio.iscoroutinefunction(self.disconnect):
            success = await self.disconnect()
        else:
            success = await self._run_blocking_in_thread(self.disconnect)

        if success:
            self._status = "disconnected"
        else:
            logger.warning(f"{self.id}: Disconnect reported failure")
            self._status = "unhealthy"

    def disconnect(self) -> bool:
        """Either sync or async method to be overwritten by subclasses.

        Returns:
            bool: True if disconnect was successful, False otherwise.
        """
        return True

    def check_status(self) -> str:
        """
        Check device health status.

        Returns:
            Status string: "connected", "disconnected", or "unhealthy"

        Notes:
            Override in subclasses that can actively detect disconnection
            (e.g., by querying device status). Base implementation returns
            current status based on connection state and polling failures.
        """
        return self._status

    # --- core ops v2 ---
    async def _run_blocking_in_thread(self, func, *args, **kwargs):
        """
        Run blocking function in thread pool executor.

        Uses device manager's executor if available, otherwise fallback executor.

        Args:
            func: Blocking function to run
            *args, **kwargs: Arguments to pass to func

        Returns:
            Result from func
        """
        loop = asyncio.get_running_loop()
        executor = self._manager.executor if self._manager else _fallback_executor
        return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))

    async def _on_device(self, func, *args, **kwargs):
        """
        Legacy alias for _run_blocking_in_thread.

        Deprecated: Use _run_blocking_in_thread instead. Kept for backwards
        compatibility with existing drivers.

        Args:
            func: Blocking function to run
            *args, **kwargs: Arguments to pass to func

        Returns:
            Result from func
        """
        return await self._run_blocking_in_thread(func, *args, **kwargs)

    async def poll_property(self, name: str) -> Any:
        """
        Read one property from device and update cache.

        Handles polling failures by tracking consecutive errors. After 3
        consecutive failures, marks device as "unhealthy".

        Args:
            name: Property name to poll

        Returns:
            Property value

        Raises:
            Exception: If polling fails (after logging and updating status)
        """
        async with self._lock:
            try:
                value = await self._run_blocking_in_thread(lambda: getattr(self, name))
                self._cache[name] = value

                # Reset error count on successful poll
                if self._poll_error_count > 0:
                    logger.info(f"{self.id}: Poll recovered (property '{name}')")
                    self._poll_error_count = 0
                    if self._status == "unhealthy":
                        self._status = "connected"
                        logger.info(
                            f"{self.id}: Device status recovered: unhealthy -> connected"
                        )

                return value

            except Exception as e:
                self._poll_error_count += 1
                logger.warning(
                    f"{self.id}: Failed to poll property '{name}'"
                    f"(error #{self._poll_error_count}): {e}"
                )

                # Mark as unhealthy after 3 consecutive failures
                if self._poll_error_count >= 3 and self._status == "connected":
                    self._status = "unhealthy"
                    logger.error(
                        f"{self.id}: Device marked as unhealthy after {self._poll_error_count} "
                        f"consecutive polling failures"
                    )

                raise

    async def set_property(self, name: str, value: Any) -> None:
        """Set one property on device and update cache."""
        meta = getattr(self, "_api_properties", {}).get(name, {})
        clamped_value = self._coerce_clamp(meta, value)
        async with self._lock:
            await self._run_blocking_in_thread(
                lambda: setattr(self, name, clamped_value)
            )
            self._cache[name] = clamped_value  # Cache the clamped value, not original

    def get_cached(self, name: str) -> Any:
        """Get cached property value."""
        return self._cache.get(name, None)

    async def read_state(self) -> Dict[str, Any]:
        """Reads all properties from cache."""
        state = {}
        for k in getattr(self, "_api_properties", {}).keys():
            state[k] = self.get_cached(k)
        return state

    async def apply_properties(self, properties: dict) -> dict:
        for k, v in properties.items():
            if self.get_cached(k) == v:
                continue
            await self.set_property(k, v)

        # Call post-apply hook for drivers with composite/derived properties
        await self._post_apply_properties(properties)

        # read back concurrently (optional)
        return await self.read_state()

    async def _post_apply_properties(self, properties: dict) -> None:
        """
        Hook for drivers to handle special cases after profile properties are applied.

        Override this in subclasses to restore composite properties (like channel
        settings) that are published in read_state() but not actual api_properties.

        Args:
            properties: The properties dict that was just applied
        """
        pass

    def _coerce_clamp(self, spec: Dict[str, Any], value: Any) -> Any:
        # best-effort type + bounds + choices enforcement
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
            # todo - should I catch it here?
            pass
        if (
            "min" in spec
            and spec["min"] is not None
            and isinstance(value, (int, float))
        ):
            value = max(spec["min"], value)
        if (
            "max" in spec
            and spec["max"] is not None
            and isinstance(value, (int, float))
        ):
            value = min(spec["max"], value)
        if "choices" in spec and spec["choices"]:
            if value not in spec["choices"]:
                # pick first choice if value not in valid set
                value = spec["choices"][0]
        return value

    # ---- generic command runner -------------------------------------------
    async def run_command(self, name: str, args: Dict[str, Any] | None = None):
        """
        Execute a command on the device.

        Commands are executed with exclusive lock to prevent collision with
        property access. Sync commands run in thread pool to avoid blocking.

        Args:
            name: Command method name
            args: Command arguments

        Returns:
            Command result

        Notes:
            - Sync commands: Wrapped in _run_blocking_in_thread
            - Async commands: Awaited directly (must handle threading internally)
        """
        args = args or {}
        if hasattr(self, name) and callable(fn := getattr(self, name)):
            async with self._lock:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(**args)
                else:
                    return await self._run_blocking_in_thread(lambda: fn(**args))
        raise RuntimeError(
            f"Method {name} specified in _api_commands not found in the class"
        )

    # Convenience accessors
    def list_data_sources(self) -> Dict[str, Dict[str, Any]]:
        """Return the per-class registry (name -> spec)."""
        return dict(self.__class__._api_data_sources)

    def get_datasource(self, name: str):
        """Return the DataSource instance (the descriptor's __get__ gives you one)."""
        spec = self.__class__._api_data_sources.get(name)
        if not spec:
            raise KeyError(
                f"Unknown data source '{name}' for {self.__class__.__name__}"
            )
        return getattr(self, name)

    # --- helpers ---
    @property
    def is_connected(self) -> bool:
        """Check if device is connected (backwards compatibility)."""
        return self._status == "connected"

    def build_spec(self, dev_id: str):
        """
        Build device specification from driver metadata.

        Constructs comprehensive API specification from driver's _api_properties,
        _api_commands, and _api_data_sources metadata.

        Args:
            dev_id: Device identifier

        Returns:
            DeviceSpec with properties, commands, and data sources

        Notes:
            - Used by clients for API discovery and UI generation
            - Property types extracted from Python type hints
            - Command arguments include type and constraint info
        """
        from typing import get_args
        from ..schemas import (
            DeviceSpec,
            PropertySpec,
            CommandSpec,
            DataSourceSpec,
            ArgSpec,
        )

        # Parse _api_properties metadata
        properties = []
        for name, meta in self._api_properties.items():
            # Type validation now done in decorator - this is a safety net for edge cases
            if meta.get("type", "Any") == "Any":
                logger.debug(
                    f"Property {self.options['driver']}.{name} has type 'Any' (decorator should have caught this)"
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

        # Parse _api_commands metadata
        cmds = []
        cmd_meta = self._api_commands
        if isinstance(cmd_meta, dict):
            for cname, cinfo in cmd_meta.items():
                args = []
                raw_args = cinfo.get("args", [])
                for a in raw_args:
                    a_type = a.get("type", object)
                    if a_type is None:
                        logger.warning(
                            f"Command {cname} is missing type hint for argument {a}. Add proper type hint for correct API."
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
                    logger.debug(
                        "type_str = %s, choices = %s", type_str, args[-1].choices
                    )

                events = cinfo.get("events", {})
                cmds.append(
                    CommandSpec(
                        name=cname, args=args, doc=cinfo.get("doc", ""), events=events
                    )
                )
        else:
            # Fallback for legacy format
            for cname in cmd_meta:
                cmds.append(CommandSpec(name=cname, args=[]))

        # Parse _api_data_sources metadata
        dss = []
        ds_meta = self._api_data_sources
        if isinstance(ds_meta, dict):
            for dsname, dsinfo in ds_meta.items():
                dss.append(
                    DataSourceSpec(
                        name=dsname,
                        has_plot=dsinfo.get("has_plot", False),
                        doc=dsinfo.get("doc", ""),
                    )
                )

        dev_meta = getattr(self, "_api_device_meta", {})
        logger.debug(
            f"Device spec built for '{dev_id}': {len(properties)} properties, {len(cmds)} commands, {len(dss)} data sources"
        )

        return DeviceSpec(
            id=dev_id,
            driver=self._api_driver,
            doc=dev_meta.get("doc", "No docstring found in driver class"),
            properties=properties,
            commands=cmds,
            data_sources=dss,
        )
