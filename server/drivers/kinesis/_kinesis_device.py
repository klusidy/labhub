"""
Kinesis Device Base Class

Provides common infrastructure for all Thorlabs Kinesis devices:
- Single-threaded executor for .NET DLL access (required by pythonnet)
- Lazy loading of .NET assemblies
- Declarative DLL requirements system

Architecture:
- All Kinesis operations run on dedicated single thread (_EXEC)
- DLL loaded once per process, shared by all device instances
- Each device subclass declares its DLL requirements via _DLL_REQUIREMENTS

Usage:
    class kpz101(KinesisDevice):
        _DLL_REQUIREMENTS = {
            'dlls': ['Thorlabs.MotionControl.KCube.PiezoCLI.dll'],
            'imports': {
                'KCubePiezo': 'Thorlabs.MotionControl.KCube.PiezoCLI.KCubePiezo',
            }
        }
"""

from __future__ import annotations
import asyncio
import threading
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..base import Device

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


class KinesisDevice(Device):
    """
    Base class for all Thorlabs Kinesis devices.

    Handles .NET CLR interop via pythonnet with single-threaded execution.
    All subclasses share the same thread and DLL imports.
    """

    # Shared class variables for all Kinesis devices
    _LOADED_TYPES: set = set()  # Track which device types have loaded their DLLs
    _THREAD_ID: int | None = None  # ID of the Kinesis thread
    _EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kinesis")
    _LOADED_CLASSES: Dict[str, Any] = {}  # Cache of loaded .NET classes

    # Common DLL requirements for all Kinesis devices
    _COMMON_DLL_REQUIREMENTS = {
        "dlls": [
            "Thorlabs.MotionControl.DeviceManagerCLI.dll",
        ],
        "imports": {
            # Common imports needed by all devices
            "DeviceManagerCLI": "Thorlabs.MotionControl.DeviceManagerCLI.DeviceManagerCLI",
            "Decimal": "System.Decimal",
            "Action": "System.Action",
            "UInt64": "System.UInt64",
        },
    }

    # Device-specific requirements - override in subclasses
    _DLL_REQUIREMENTS: Dict[str, Any] = {"dlls": [], "imports": {}}

    @classmethod
    def _load_dotnet_sync(cls, kinesis_path: str) -> None:
        """
        Load .NET DLLs and import required classes.

        Called once per process on the Kinesis thread. Loads DLLs and classes
        declared in _COMMON_DLL_REQUIREMENTS and all subclass _DLL_REQUIREMENTS.

        Args:
            kinesis_path: Directory containing Kinesis DLLs

        Raises:
            RuntimeError: If DLL files not found or import fails
        """
        # Check if this specific device type has already loaded its DLLs
        device_type = cls.__name__
        if device_type in cls._LOADED_TYPES:
            return

        try:
            import clr  # type: ignore
        except ImportError:
            raise RuntimeError(
                "pythonnet not installed. Install with: pip install pythonnet"
            )

        base = Path(kinesis_path)
        logger.info(f"Loading Kinesis DLLs from {base}")

        # Collect DLL requirements from common + this specific device class
        all_dlls = set(cls._COMMON_DLL_REQUIREMENTS["dlls"])
        all_imports = dict(cls._COMMON_DLL_REQUIREMENTS["imports"])

        # Add this device's specific requirements
        if hasattr(cls, "_DLL_REQUIREMENTS"):
            reqs = cls._DLL_REQUIREMENTS
            all_dlls.update(reqs.get("dlls", []))
            all_imports.update(reqs.get("imports", {}))

        # Load DLL files
        logger.debug(f"Loading {len(all_dlls)} DLL(s)")
        for dll_name in sorted(all_dlls):
            dll_path = base / dll_name
            if not dll_path.exists():
                raise RuntimeError(f"Kinesis DLL not found: {dll_path}")
            clr.AddReference(str(dll_path))
            logger.debug(f"  Loaded: {dll_name}")

        # Import .NET classes dynamically
        logger.debug(f"Importing {len(all_imports)} .NET class(es)")
        for name, dotnet_path in sorted(all_imports.items()):
            try:
                # Parse module.ClassName format
                parts = dotnet_path.rsplit(".", 1)
                if len(parts) == 2:
                    module_name, class_name = parts
                else:
                    module_name, class_name = "", dotnet_path

                # Import the .NET module
                if module_name:
                    module = __import__(module_name, fromlist=[class_name])
                    cls._LOADED_CLASSES[name] = getattr(module, class_name)
                else:
                    # Top-level import
                    cls._LOADED_CLASSES[name] = __import__(class_name)

                logger.debug(f"  Imported: {name} <- {dotnet_path}")
            except Exception as e:
                raise RuntimeError(
                    f"Failed to import .NET class '{dotnet_path}' as '{name}': {e}"
                ) from e

        cls._THREAD_ID = threading.get_ident()
        cls._LOADED_TYPES.add(device_type)
        logger.info(
            f"Kinesis {device_type} loaded (thread={cls._THREAD_ID}, "
            f"{len(all_dlls)} DLLs, {len(all_imports)} classes)"
        )

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize Kinesis device.

        Args:
            dev_id: Device identifier
            options: Must contain kinesis_path or KINESIS_PATH env var must be set
            manager: Device manager reference
        """
        super().__init__(dev_id, options, manager)

        # Extract kinesis_path from options (legacy: conn.kinesis_path)
        conn = options.get("conn", {})
        self.kinesis_path: str = (
            options.get("kinesis_path")
            or conn.get("kinesis_path")
            or os.environ.get("KINESIS_PATH")
            or ""
        )
        if not self.kinesis_path:
            raise RuntimeError(
                f"Device '{dev_id}': kinesis_path not specified. "
                "Set in config.yaml or KINESIS_PATH environment variable"
            )

    def __getattr__(self, name: str) -> Any:
        """
        Provide access to loaded .NET classes via attribute access.

        Allows: self.DeviceManagerCLI instead of KinesisDevice._LOADED_CLASSES['DeviceManagerCLI']
        """
        if name in self._LOADED_CLASSES:
            return self._LOADED_CLASSES[name]
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    async def _ensure_kinesis_loaded(self) -> None:
        """
        Ensure .NET DLLs are loaded (called from connect()).

        Runs _load_dotnet_sync on the Kinesis thread if not already loaded.
        """
        device_type = self.__class__.__name__
        if device_type not in self._LOADED_TYPES:
            await self._run_blocking_in_thread(
                lambda: self.__class__._load_dotnet_sync(self.kinesis_path)
            )

    async def _run_blocking_in_thread(self, fn):
        """
        Execute function on the dedicated Kinesis thread.

        Override base class to use Kinesis-specific single-threaded executor.
        All .NET interop must go through this method to avoid threading issues.

        Args:
            fn: Callable to execute (can be lambda or bound method)

        Returns:
            Result of fn()
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._EXEC, fn)

    def _to_decimal(self, value: float):
        """
        Convert Python float to .NET Decimal.

        Helper for interop with Kinesis SDK methods that require System.Decimal.
        """
        Decimal = self._LOADED_CLASSES.get("Decimal")
        return Decimal(value) if Decimal else float(value)

    # Note: Subclasses override connect() and disconnect()
    # See example_device.py for the pattern
