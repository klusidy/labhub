# kinesis_runtime.py
from __future__ import annotations
import asyncio, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any, Dict
from .._base import Device



# async def run(fn):
#     """Run callable on the single Kinesis thread."""
#     loop = asyncio.get_running_loop()
#     return await loop.run_in_executor(_EXEC, fn)

# def run_sync(fn):
#     """Synchronous variant (avoid in async paths)."""
#     return _EXEC.submit(fn).result()


# def shutdown():
#     _EXEC.shutdown(wait=True)



class KinesisDevice(Device):

    # CLASS VARIABLES shared by all KinesisDevice instances
    # All kinesis calls must be done on a single thread due to .NET limitations.
    _LOADED = False
    _THREAD_ID: int | None = None
    _EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kinesis")

    DeviceManagerCLI = None
    KCubePiezo = None
    Decimal = None

    @staticmethod
    def _load_dotnet_sync(kinesis_path: str):
        if KinesisDevice._LOADED:
            return

        import clr  # type: ignore
        base = Path(kinesis_path)
        dm = base / "Thorlabs.MotionControl.DeviceManagerCLI.dll"
        pz = base / "Thorlabs.MotionControl.KCube.PiezoCLI.dll"
        if not (dm.exists() and pz.exists()):
            raise RuntimeError(f"Kinesis DLLs not found under {base}")

        clr.AddReference(str(dm))
        clr.AddReference(str(pz))

        # Imports MUST happen after AddReference and on the same thread.
        from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI as _DMCLI  # type: ignore
        from Thorlabs.MotionControl.KCube.PiezoCLI import KCubePiezo as _KCubePiezo    # type: ignore
        from System import Decimal as _Decimal  # type: ignore

        KinesisDevice.DeviceManagerCLI = _DMCLI
        KinesisDevice.KCubePiezo = _KCubePiezo
        KinesisDevice.Decimal = _Decimal

        KinesisDevice._THREAD_ID = threading.get_ident()
        KinesisDevice._LOADED = True

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        conn = options.get("conn", {})
        self.kinesis_path: str = conn.get("kinesis_path") or os.environ.get("KINESIS_PATH") or ""
        if not self.kinesis_path:
            raise RuntimeError("Provide conn.kinesis_path or set KINESIS_PATH")
        self._Decimal = None  # filled in after ensure_loaded()
        super().__init__(dev_id, options)

    async def _on_device(self, fn): # TODO - THIS MAY BE STATICMETHOD
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(KinesisDevice._EXEC, fn)

    async def property_get_async(self, name: str):
        return await self._on_device(lambda: self.property_get(name))

    async def property_set_async(self, name: str, value):
        return await self._on_device(lambda: self.property_set(name, value))

    async def _ensure_kinesis_loaded(self):
        return await self._on_device(lambda: self._load_dotnet_sync(self.kinesis_path))
       

