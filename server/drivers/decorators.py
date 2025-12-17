from __future__ import annotations
from typing import (
    Any,
    Dict,
    Callable,
    List,
    Union,
    Optional,
    Set,
    Tuple,
    Mapping,
    Awaitable,
    get_type_hints,
    AsyncGenerator,
)
import inspect
import asyncio
import time
import weakref

from ._data_source import DataSource, Frame


ALIASES: Dict[str, Any] = {}


def api_device(api_name: str = None, doc: str = None):
    def decorator(cls: Any):
        cls._api_device_name = api_name or cls.__name__
        cls._api_device_meta = {"doc": doc or (cls.__doc__ or "").strip()}

        ALIASES[cls._api_device_name] = cls
        return cls

    return decorator


def api_command(api_name=None, *, doc=None):
    def decorator(method: Callable):
        # Validate type hints at class definition time
        try:
            hints = get_type_hints(method)
            sig = inspect.signature(method)

            # Check all parameters (except self) have type hints
            for param_name in sig.parameters.keys():
                if param_name == "self":
                    continue
                if param_name not in hints:
                    raise TypeError(
                        f"Command '{method.__name__}' parameter '{param_name}' is missing a type hint.\n"
                        f"Add type hint: def {method.__name__}(self, {param_name}: YourType):"
                    )

            # Warn if no return type specified (not all commands return values, so just warn)
            if "return" not in hints:
                import warnings
                warnings.warn(
                    f"Command '{method.__name__}' has no return type hint. "
                    f"Consider adding -> YourType or -> None",
                    RuntimeWarning
                )
        except NameError as e:
            # Forward references not resolved yet - warn but allow
            import warnings
            warnings.warn(
                f"Could not validate type hints for command '{method.__name__}': {e}. "
                f"Ensure forward references are properly quoted.",
                RuntimeWarning
            )

        method._api_command_name = api_name or method.__name__
        method._api_command_meta = {"doc": doc or (method.__doc__ or "").strip()}
        method._api_subcommands = {}  # event_name -> method name

        # generic event factory: @jog.event("release")(...)
        def event(event_name: str):
            def factory(
                sub_api_name: Optional[str] = None, *, doc: Optional[str] = None
            ):
                def sub_decorator(sub_method: Callable):
                    # sub_method._api_command_name = (
                    #    sub_api_name or f"{method._api_command_name}...{event_name}"
                    # )
                    sub_method._api_command_name = sub_api_name or sub_method.__name__
                    # sub_method._api_command_meta = {
                    #    "doc": (doc or (sub_method.__doc__ or "")).strip(),
                    #    "parent": method._api_command_name,
                    #    "event": event_name,
                    # }
                    # remember the subcommand on the parent (by function name for later binding)
                    method._api_subcommands[event_name] = sub_method.__name__
                    return sub_method

                return sub_decorator

            return factory

        # convenience aliases: @jog.release(), @jog.press()
        method.event = event
        # method.press = event("press")
        # TODO - document how this works!!!

        method.release = event("release")

        return method

    return decorator


def api_property(
    api_name=None, *, min=None, max=None, step=None, choices=None, doc=None, unit=None
):
    """
    Decorator for device properties - replaces @property decorator.

    IMPORTANT: Must be called with parentheses, even if no arguments.

    Usage:
        @api_property(min=0, max=100, unit="Hz")
        def frequency(self) -> float:
            return self._freq

        @frequency.setter
        def frequency(self, value: float):
            self._freq = value

        # Or with no arguments:
        @api_property()
        def status(self) -> str:
            return self._status

    Args:
        api_name: Optional API name (defaults to function name)
        min: Minimum value for numeric properties
        max: Maximum value for numeric properties
        step: Step size for UI controls
        choices: List of valid choices for enum properties
        doc: Documentation string (defaults to function docstring)
        unit: Physical unit (e.g., "Hz", "V", "A")

    Notes:
        - Replaces @property - do NOT use both
        - Metadata attached to function survives .setter() calls
        - Property defaults now handled by profile system
    """
    # Detect if used without calling (common mistake)
    if callable(api_name):
        raise TypeError(
            f"@api_property must be CALLED with parentheses.\n"
            f"Wrong:  @api_property\n"
            f"Right:  @api_property()\n"
            f"Right:  @api_property(min=0, max=100, unit='Hz')"
        )

    def decorator(fget):
        # Validate input
        if not callable(fget):
            raise TypeError(
                f"@api_property() must be applied to a function, "
                f"got {type(fget).__name__}"
            )

        # Validate type hint exists (fail fast at class definition time)
        from typing import get_type_hints
        try:
            hints = get_type_hints(fget)
            return_type = hints.get('return')
            if return_type is None:
                raise TypeError(
                    f"Property '{fget.__name__}' is missing a return type hint.\n"
                    f"Add type hint: def {fget.__name__}(self) -> YourType:"
                )
        except NameError as e:
            # get_type_hints can fail if forward references aren't resolved yet
            # This is OK during class definition - just warn
            import warnings
            warnings.warn(
                f"Could not validate type hint for '{fget.__name__}': {e}. "
                f"Ensure forward references are properly quoted.",
                RuntimeWarning
            )

        # Attach metadata to the getter function
        fget._api_property_name = api_name or fget.__name__
        fget._api_property_meta = {
            "min": min,
            "max": max,
            "step": step,
            "choices": choices,
            "unit": unit,
            "doc": doc or (fget.__doc__ or "").strip(),
        }

        # Create and return property object
        # The metadata is on fget, which property keeps as .fget attribute
        # When .setter() is called, it creates new property but preserves fget!
        return property(fget)

    return decorator


class api_data:
    def __init__(self, api_name: str | None = None, *, doc: str | None = None):

        self.generator: Optional[Callable] = None
        self._plot_fn: Optional[Callable] = None
        self._api_data_name: Optional[str] = api_name
        self._api_data_meta: Dict[str, Any] = {"doc": doc, "plots": []}

        self._owner: Optional[type] = None
        self._attr_name: Optional[str] = None

        self._instances: weakref.WeakKeyDictionary[object, DataSource] = (
            weakref.WeakKeyDictionary()
        )

    def __call__(self, method: AsyncGenerator):
        # Validate that method is actually an async generator function
        if not inspect.isasyncgenfunction(method):
            raise TypeError(
                f"@api_data must decorate an async generator function.\n"
                f"'{method.__name__}' is {type(method).__name__}.\n"
                f"Use: async def {method.__name__}(self) -> AsyncGenerator[Frame, None]:"
            )

        self.generator = method
        self._api_data_name = self._api_data_name or method.__name__
        self._api_data_meta["doc"] = (
            self._api_data_meta["doc"] or (method.__doc__ or "").strip()
        )
        return self

    def plot(self, api_name: str = None, *, doc: str = None):
        """Decorator for the plot-spec function (no params)."""

        def decorator(method: Callable):
            self._plot_fn = method
            # keep the plot docstring too (optional; handy for spec)
            self._api_data_meta["plots"].append(
                {
                    "name": api_name or method.__name__,
                    "doc": doc or (method.__doc__ or "").strip(),
                }
            )
            return method

        return decorator

    def __set_name__(self, owner: type, name: str):
        self._owner = owner
        self._attr_name = name
        # should not happen in typical usage
        if not self._api_data_name:
            self._api_data_name = (
                name  # default to attribute name if alias not provided
            )

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
            ds = DataSource(
                name=self._api_data_name,
                generator=bound_generator,
                plot_fn=bound_plot,
                doc=self._api_data_meta["doc"],
            )
            self._instances[obj] = ds
        return ds
