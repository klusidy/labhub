from __future__ import annotations
from typing import Any, Dict, Callable, List, Union, Optional, Set, Tuple, Mapping, Awaitable, get_type_hints, AsyncGenerator
import inspect
import asyncio
import time
import weakref

from ._data_source import DataSource, Frame


ALIASES: Dict[str, Any] = {}

def api_device(api_name: str = None, doc: str=None):
    def decorator(cls: Any):
        cls._api_device_name = api_name or cls.__name__
        cls._api_device_meta = {"doc": doc or (cls.__doc__ or "").strip()}

        ALIASES[cls._api_device_name] = cls
        return cls
    return decorator

def api_command(api_name=None, *, doc=None):
    def decorator(method: Callable):
        method._api_command_name = api_name or method.__name__
        method._api_command_meta = {"doc" : doc or (method.__doc__ or "").strip() }
        return method
    return decorator

def api_property(api_name=None, *, min=None, max=None, default=None, step=None, choices=None, doc=None):
    def decorator(property_obj):  # put this ABOVE @property todo - replace @property??
        fget = property_obj.fget
        fget._api_property_name = api_name or fget.__name__
        fget._api_property_meta = {"min": min, 
                                "max": max, 
                                "default": default,
                                "step": step,
                                "choices": choices,
                                "doc": doc or fget.__doc__}
        return property_obj
    return decorator

class api_data:
    def __init__(self, api_name:str | None=None, *, doc:str | None = None):

        self.generator: Optional[Callable] = None
        self._plot_fn: Optional[Callable] = None
        self._api_data_name: Optional[str] = api_name
        self._api_data_meta: Dict[str, Any] = {"doc": doc, "plots": []}

        self._owner: Optional[type] = None
        self._attr_name: Optional[str] = None

        self._instances: weakref.WeakKeyDictionary[object, DataSource] = weakref.WeakKeyDictionary()

    def __call__(self, method: AsyncGenerator):
        self.generator = method
        self._api_data_name = self._api_data_name or method.__name__
        self._api_data_meta["doc"] =  self._api_data_meta["doc"] or (method.__doc__ or "").strip()
        return self
    
    def plot(self, api_name: str = None, *, doc: str=None):
        """Decorator for the plot-spec function (no params)."""
        def decorator(method: Callable):
            self._plot_fn = method
            # keep the plot docstring too (optional; handy for spec)
            self._api_data_meta["plots"].append({
                "name": api_name or method.__name__,
                "doc": doc or (method.__doc__ or "").strip()
            })
            return method
        return decorator
    
    def __set_name__(self, owner: type, name: str):
        self._owner = owner
        self._attr_name = name
        # should not happen in typical usage
        if not self._api_data_name: 
            self._api_data_name = name # default to attribute name if alias not provided 

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.generator is None:
            raise AttributeError(f"Async generator '{self._attr_name}' is not defined.")

        ds = self._instances.get(obj, None)
        if ds is None:
            # bind methods to instance
            bound_generator = self.generator.__get__(obj, objtype)
            bound_plot = self._plot_fn.__get__(obj, objtype) if self._plot_fn else None
            ds = DataSource(name=self._api_data_name, generator=bound_generator, plot_fn=bound_plot, doc=self._api_data_meta["doc"])
            self._instances[obj] = ds
        return ds  


