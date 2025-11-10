from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, Callable, Optional, Mapping, get_type_hints
import inspect
from concurrent.futures import ThreadPoolExecutor
from ._decorators import api_device, api_command, api_property, ALIASES, api_data, Frame

executor = ThreadPoolExecutor(max_workers=8) # todo - get this from above somehow? also make this configurable

logger = logging.getLogger(__name__)

# --- base class for a device driver --------------------------------
class Device:
    """Abstract async device interface."""

    kind: str = "device"

    PROPERTIES: Dict[str, Dict[str, Any]] = {}   # per subclass
    COMMANDS: Dict[str, Dict[str, Any]] = {}     # per subclass
    DATA_SOURCES: Dict[str, Dict[str, Any]] = {} # per subclass

    def __init_subclass__(cls, api_alias: Optional[str] = None):
        """ Called when a subclass is defined (not initialized).
            Scans for @api_command and @api_property decorators to auto-populate COMMANDS and PROPERTIES."""
        super().__init_subclass__() # there is not superclass, but its good practice
        commands, properties, data_sources = {}, {}, {}

        for name, attr in cls.__dict__.items(): # go thrgouh all class attributes
            if callable(attr) and hasattr(attr, "_api_command_meta"):
                command_meta = getattr(attr, "_api_command_meta", {})
                signature = inspect.signature(attr)
                type_hints = get_type_hints(attr)
                
                command = {}
                command["doc"] = command_meta.get("doc", "No doc provided. Fill in doc string of decorated method in device driver.")
                command["returns"] = type_hints.get("return", "Any").__name__ if "return" in type_hints else "Any"
                command["method"] = name
                command["args"] = [
                    {
                        "name": p.name,
                        "type": type_hints.get(p.name),
                        "default": p.default if p.default is not inspect.Parameter.empty else None,
                    }
                    for p in signature.parameters.values() if p.name != "self"
                    ]
                
                event_commands = getattr(attr, "_api_subcommands", {})
                command["events"] = {event_name: sub_name for event_name, sub_name in event_commands.items()}

                commands[attr._api_command_name] = command
        
            if isinstance(attr, property) and hasattr(attr.fget, "_api_property_meta"):
                fget, fset = attr.fget, attr.fset
                get_hint = get_type_hints(fget).get("return", "Any")
                prop_meta = getattr(fget, "_api_property_meta", {})
                
                # hits for set are not used - assume same as get (todo: raise exception if not)
                set_hint = get_type_hints(fset).get("value", "Any") if fset else None
                set_params = list(inspect.signature(fset).parameters.values())[1:] if fset else []

                prop = {}
                prop["doc"] = prop_meta.get("doc", "No doc provided. Fill in doc string of decorated property in device driver.")
                prop["type"] = get_hint
                prop["read_only"] = fset is None
                prop["default"] = prop_meta.get("default", None)
                prop["min"] = prop_meta.get("min", None)
                prop["max"] = prop_meta.get("max", None)
                prop["step"] = prop_meta.get("step", None)
                prop["choices"] = prop_meta.get("choices", None)
                prop["unit"] = prop_meta.get("unit", None)
                
                properties[fget._api_property_name] = prop

            if isinstance(attr, api_data):
                data_source_meta = getattr(attr, "_api_data_meta", {})
                data_source = {}
                data_source["doc"] = data_source_meta.get("doc", "No doc provided. Fill in doc string of decorated property in device driver.")
                data_source["has_plot"] = attr._plot_fn is not None
                data_source["method"] = name # attribute name - is this necessary?? todo (should be the same as name anyway, why double it?)
                data_sources[attr._api_data_name] = data_source

        cls.COMMANDS = commands
        cls.PROPERTIES = properties
        cls.DATA_SOURCES = data_sources

    @classmethod
    async def create(cls, dev_id: str, options: dict[str, object]):
        self = cls(dev_id, options) # just create the object
        await self.connect()
        if self._connected:
            await self._apply_driver_defaults()
            await self._apply_config_defaults()
        else:
            pass # TODO report that device was not connected??
        return self

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        """Initialize device with ID and options from config.yaml."""
        self.id = dev_id
        self.options = options # whatever was in config.yaml
        self.LOCK = asyncio.Lock()
        self.CACHE: Dict[str, Any] = {}  # cached property values
        self.polling_interval = options.get("polling_interval", 1000)  # ms
        self._connected = False


    async def _apply_driver_defaults(self):
        for property_name, metadata in getattr(self, "PROPERTIES", {}).items():
            if "default" in metadata and metadata["default"] is not None: 
                logger.debug("- base init, prop_name=%s, metadata=%s", property_name, metadata)
                await self.set_property(property_name, metadata["default"])


    async def _apply_config_defaults(self):
        for k, v in self.options.get("defaults", {}).items():
            if k in getattr(self, "PROPERTIES", {}):
                await self.set_property(k, v)


    # --- lifecycle ---
    async def connect(self) -> None:  # override
        self._connected = True

    async def disconnect(self) -> None:  # override
        self._connected = False

    # --- core ops v2 ---
    async def _run_blocking_in_thread(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, lambda: func(*args, **kwargs))
    
    async def poll_property(self, name: str) -> Any:
        """Read one property from device and update cache."""
        async with self.LOCK:
            value = await self._run_blocking_in_thread(lambda: getattr(self, name))
            self.CACHE[name] = value #CachedValue(value=value, updated_at=asyncio.get_event_loop().time())
            return value

    async def set_property(self, name: str, value: Any) -> None:
        """Set one property on device and update cache."""
        meta = getattr(self, "PROPERTIES", {}).get(name, {})
        clamped_value = self._coerce_clamp(meta, value)
        async with self.LOCK:
            await self._run_blocking_in_thread(lambda: setattr(self, name, clamped_value))
            self.CACHE[name] = value 
            # read-back (optional) - TODO decide if needed (probably not? - just trust it)
            #new_value = await self._run_blocking_in_thread(lambda: self.property_get(name))
            #self.cache[name] = new_value 

    def get_cached(self, name: str) -> Any:
        """Get cached property value."""
        return self.CACHE.get(name, None)


    async def read_state(self) -> Dict[str, Any]:
        """ Reads all properties from cache."""
        state = {}
        for k in getattr(self, "PROPERTIES", {}).keys():
            state[k] = self.get_cached(k)
        return state
    
    async def apply_properties(self, properties: dict) -> dict:
        for k, v in properties.items():
            if self.get_cached(k) == v:
                continue
            await self.set_property(k, v) 

        # read back concurrently (optional)
        return await self.read_state()
        

    # --- core ops ---
    # async def read_state(self) -> Dict[str, Any]:  
    #     keys = list(getattr(self, "PROPERTIES", {}).keys())
    #     vals = await asyncio.gather(*(self.property_get_async(k) for k in keys))
    #     state = dict(zip(keys, vals))
    #     return state
    
    # async def read_state_sequential(self) -> Dict[str, Any]:  
    #     keys = list(getattr(self, "PROPERTIES", {}).keys())
    #     state = {}
    #     for k in keys:
    #         state[k] = await self.property_get_async(k)
    #     return state
    
    

    # def property_get(self, name: str) -> Any:
    #     return getattr(self, name)  
    
    # async def property_get_async(self, name: str):
    #     return await self._on_device(lambda: self.property_get(name))
    


    # async def apply_properties(self, properties: dict) -> dict:
    #     for k, v in properties.items():
    #         await self.property_set_async(k, v)

    #     # read back concurrently (optional)
    #     return await self.read_state()


    # def property_set(self, name: str, value):
    #     meta = getattr(self, "PROPERTIES", {}).get(name, {})
    #     setattr(self, name, self._coerce_clamp(meta, value))

    # async def property_set_async(self, name: str, value):
    #     return await self._on_device(lambda: self.property_set(name, value))
    
    def _coerce_clamp(self, spec: Dict[str, Any], value: Any) -> Any:
        # best-effort type + bounds + choices enforcement
        t = spec.get("type") or Any
        try:
            if t == int: value = int(value)
            elif t == float: value = float(value)
            elif t == bool:  value = bool(value)
            elif t == str:   value = str(value)
        except Exception:
            # todo - should I catch it here?
            pass
        if "min" in spec and spec["min"] is not None and isinstance(value, (int, float)):
            value = max(spec["min"], value)
        if "max" in spec and spec["max"] is not None and isinstance(value, (int, float)):
            value = min(spec["max"], value)
        if "choices" in spec and spec["choices"]:
            if value not in spec["choices"]:
                # pick closest/default if out of set
                value = spec.get("default", spec["choices"][0])
        return value
    
    # Default marshaller: just offload to a thread so we don't block the loop.
    # Drivers that need strict thread affinity will override this (see KPZ).
    # async def _on_device(self, fn):
    #     loop = asyncio.get_running_loop()
    #     return await loop.run_in_executor(None, fn)

    



    # ---- generic command runner -------------------------------------------
    async def run_command(self, name: str, args: Dict[str, Any] | None = None):
        args = args or {}
        if hasattr(self, name) and callable(fn := getattr(self, name)):
            return await fn(**args) if asyncio.iscoroutinefunction(fn) else fn(**args)
        raise RuntimeError(f"Method {name} specified in COMMANDS not found in the class")


    # Convenience accessors
    def list_data_sources(self) -> Dict[str, Dict[str, Any]]:
        """Return the per-class registry (name -> spec)."""
        return dict(self.__class__.DATA_SOURCES)

    def get_datasource(self, name: str):
        """Return the DataSource instance (the descriptor’s __get__ gives you one)."""
        spec = self.__class__.DATA_SOURCES.get(name)
        if not spec:
            raise KeyError(f"Unknown data source '{name}' for {self.__class__.__name__}")
        return getattr(self, spec["method"])
       

    # --- helpers ---
    @property
    def is_connected(self) -> bool:
        return self._connected