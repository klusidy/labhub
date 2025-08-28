from __future__ import annotations
import asyncio
from typing import Any, Dict, Callable, Optional, Mapping, get_type_hints
import inspect
from ._decorators import api_device, api_command, api_property, ALIASES, api_data, Frame


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
                
                properties[fget._api_property_name] = prop

            if isinstance(attr, api_data):
                data_source_meta = command_meta = getattr(attr, "_api_data_meta", {})
                data_source = {}
                data_source["doc"] = data_source_meta.get("doc", "No doc provided. Fill in doc string of decorated property in device driver.")
                data_source["has_plot"] = attr._plot_fn is not None
                data_source["method"] = name # attribute name - is this necessary?? todo (should be the same as name anyway, why double it?)
                data_sources[attr._api_data_name] = data_source

        cls.COMMANDS = commands
        cls.PROPERTIES = properties
        cls.DATA_SOURCES = data_sources

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        """Initialize device with ID and options from config.yaml."""
        self.id = dev_id
        self.options = options
        #self._state: Dict[str, Any] = {}
        #self._state_lock = asyncio.Lock() # todo - maybe add later when multiple clients are connected to the same device?
        self._connected = False

        # enforce dafaults from PROPERTIES
        for property_name, metadata in getattr(self, "PROPERTIES", {}).items():
            if "fields" in metadata:  # composite default dict
                fields = metadata["fields"] if isinstance(metadata["fields"], dict) else {k:{} for k in metadata["fields"]}
                default = {k: v.get("default") for k, v in fields.items() if "default" in v}
                self.property_set(property_name, default)
               
            if "default" in metadata:
                self.property_set(property_name, metadata["default"])
        # enforce defaults from config.yaml
        for config_props in (options.get("properties", {}), options):
            for k, v in config_props.items():
                if k in self.PROPERTIES:  # ignore non-property keys (e.g., driver-specific)
                    self.property_set(k, v)
            


    # --- lifecycle ---
    async def connect(self) -> None:  # override
        self._connected = True

    async def disconnect(self) -> None:  # override
        self._connected = False

    # --- core ops ---
    async def read_state(self) -> Dict[str, Any]:  # override
        return {k: self.property_get(k) for k in getattr(self, "PROPERTIES", {})}    
    
    def property_get(self, name: str) -> Any:
        if hasattr(self, name):
            return getattr(self, name)  
        raise RuntimeError(f"API Property '{name}' has no @property counterpart in class")

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

    def property_set(self, name: str, value: Any) -> None:
        setattr(self, name, self._coerce_clamp(getattr(self, "PROPERTIES", {}).get(name, {}), value))
        
    async def apply_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in properties.items():
            self.property_set(k, v)
        # default: return a dict with all PROPERTIES reflected #todo - is this desired behavior?
        state: Dict[str, Any] = {}
        for k in getattr(self, "PROPERTIES", {}).keys():
            state[k] = self.property_get(k)
        state["connected"] = True
        return state

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