from __future__ import annotations
from typing import Dict, List, Type, Any
from ._base import Device, ALIASES

def get(name: str):
    """Lookup by exact class name (e.g. 'SimPiezo') or by alias below."""
    # Optional alias map so you can use lowercase keys in config:
    cls = ALIASES.get(name) or ALIASES.get(name.lower()) or globals().get(name)
    if cls is None:
        available = ", ".join(sorted(ALIASES.keys()))
        raise RuntimeError(f"Unknown/unavailable driver '{name}'. Available: {available}")
    return cls

# Export driver classes into the package namespace
from .sim_piezo import SimPiezo
from .dummy_device import DummyDevice
from .example_device import ExampleDevice
#todo - if you dont import device that you then try to use, server will crash but report correct loading

try:
    from .kinesis.kpz101 import KPZ101
    from .kinesis.kim101 import KIM101
    from .kinesis.k10cr1 import K10CR1
except Exception as e:  # pythonnet missing or non-Windows
    KPZ101 = None  
    KIM101 = None
    K10CR1 = None

try:
    from .pico_technology.ps5000a import PicoScope5000a
except Exception as e:
    PicoScope5000a = None
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("Could not import PicoScope5000a driver: %s", e)

try:
    from .aimtt.tgf4000 import TGF4000
except Exception as e:
    TGF4000 = None
    logger.warning("Could not import TGF4000 driver: %s", e)
