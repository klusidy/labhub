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
        if KinesisDevice._LOADED: # here I import only once- but its not good design to have to have all dlls for all devices here...
            return

        import clr  # type: ignore
        base = Path(kinesis_path)

        dlls = ["Thorlabs.MotionControl.DeviceManagerCLI.dll",
                "Thorlabs.MotionControl.KCube.PiezoCLI.dll", # kcube kpz101
                "Thorlabs.MotionControl.GenericMotorCLI.dll", # inertial motor (generic)
                "ThorLabs.MotionControl.KCube.InertialMotorCLI.dll", # kim101
                "ThorLabs.MotionControl.IntegratedStepperMotorsCLI.dll", # k10cr1
                ]

        for dll_name in dlls:
            p = base / dll_name
            if not (p.exists):
                raise RuntimeError(f"Kinesis DLL {dll_name} not found in {base}")
            clr.AddReference(str(p))

        # Imports MUST happen after AddReference and on the same thread.
        from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI as _DMCLI  # type: ignore
        from System import (Decimal as _Decimal, # type: ignore
                            Action as Action,
                            UInt64 as UInt64)  

        from Thorlabs.MotionControl.KCube.PiezoCLI import KCubePiezo as _KCubePiezo    # type: ignore

        from Thorlabs.MotionControl.GenericMotorCLI import GenericMotorCLI as _GenericMotorCLI # type: ignore
        from Thorlabs.MotionControl.KCube.InertialMotorCLI import (   # type:ignore
            KCubeInertialMotor as _KCubeInertialMotor, 
            InertialMotorStatus as _InertialMotorStatus, 
            ThorlabsInertialMotorSettings as _ThorlabsInertialMotorSettings,
            InertialMotorJogMode as _InertialMotorJogMode,
            InertialMotorJogDirection as _InertialMotorJogDirection,
            DriveParams as _DriveParams)
        
        import Thorlabs.MotionControl.IntegratedStepperMotorsCLI as _IntegratedStepperMotorsCLI
        
        # common
        KinesisDevice.Decimal = _Decimal
        KinesisDevice.Action = Action
        KinesisDevice.UInt64 = UInt64
        KinesisDevice.DeviceManagerCLI = _DMCLI
        
        # KPZ
        KinesisDevice.KCubePiezo = _KCubePiezo

        #KIM #TODO - REFACTOR AND KEEP THE CLI ONLY
        KinesisDevice.GenericMotorCLI = _GenericMotorCLI
        KinesisDevice.KCubeInertialMotor = _KCubeInertialMotor
        KinesisDevice.InertialMotorStatus = _InertialMotorStatus
        KinesisDevice.ThorlabsInertialMotorSettings = _ThorlabsInertialMotorSettings
        KinesisDevice.InertialMotorJogMode = _InertialMotorJogMode
        KinesisDevice.InertialMotorJogDirection = _InertialMotorJogDirection
        KinesisDevice.DriveParams = _DriveParams

        #k10cr1
        KinesisDevice.IntegratedStepperMotorsCLI = _IntegratedStepperMotorsCLI # store the whole package, not one-by-one

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
       

