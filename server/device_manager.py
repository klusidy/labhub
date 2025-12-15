from __future__ import annotations
import asyncio
from typing import Dict, List, Type, Any, get_args
import time
from .schemas import DeviceInfo, PropertySpec, CommandSpec, DeviceSpec, DataSourceSpec, ArgSpec   # <-- add these
from .events import EventBus

from .drivers._base import Device
# from .drivers.sim_piezo import SimPiezo
# try:
#     from .drivers.thorlabs_kcube_piezo import ThorlabsKCubePiezo
# except Exception:  # pythonnet missing or non-Windows
#     ThorlabsKCubePiezo = None  # type: ignore


# DRIVER_REGISTRY = {
#     "sim_piezo": SimPiezo,
#     "kcube_piezo": ThorlabsKCubePiezo,
# }


from . import drivers
import logging
logger = logging.getLogger("labhub.device_manager")


class DeviceManager:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.devices: Dict[str, drivers.Device] = {}
        self._poll_tasks: Dict[str, asyncio.Task] = {}
        self._stop_evt = asyncio.Event()
        

    async def add_device(self, dev_id: str, driver: str, options: dict) -> None:
        cls = drivers.get(driver)
        if cls is None:
            raise RuntimeError(f"Unknown driver '{driver}' or not available on this platform")
        

        logger.info("Adding device: %s", driver)
        #logger.debug("Class: %r, dev_id: %r, options: %r", cls, dev_id, options)
        

        try:
            dev: drivers.Device = await cls.create(dev_id, options)
            # TODO: dev.connect() and defaults are handled in .create, but it may be here...?
            self.devices[dev_id] = dev
        except Exception as e:
            logger.exception("Failed to connect to device with dev_id=%r", dev_id)

    async def remove_device(self, dev_id: str) -> None:        # <-- add (useful for reloads, tests)
        dev = self.devices.pop(dev_id, None)
        if dev:
            try:
                await dev.disconnect()
            except Exception:
                pass

    async def remove_all(self) -> None:
        for dev in list(self.devices.values()):
            try:
                await dev.disconnect()
            except Exception:
                pass
        self.devices.clear()

    async def start_polling_device(self, dev_id:str, state_ms: int = 200, data_ms: int = 50) -> None:
        
        async def polling_task(dev_id: str, dev: Device) -> None:
            keys = list(getattr(dev, "PROPERTIES", {}).keys())
            state = {}
            try:
                while not self._stop_evt.is_set():
                    for k in keys:
                        _ = await dev.poll_property(k) # read actual values to cache
                    st = await dev.read_state() # read cached values (incl. extra info)
                    await self.event_bus.publish({"type":"device.state","id":dev_id,"state":st})
                    
                    await asyncio.sleep(dev.polling_interval / 1000)
            except asyncio.CancelledError:
                pass
        
        self._poll_tasks[dev_id] = asyncio.create_task(polling_task(dev_id, self.devices[dev_id]))
        return 
    
    async def start_polling(self, state_ms: int = 200, data_ms: int = 50) -> None:
        for dev_id, dev in self.devices.items():
            await self.start_polling_device(dev_id, state_ms, data_ms)

    async def stop_polling_device(self, dev_id: str) -> None:
        if dev_id not in self._poll_tasks:
            return 
        task = self._poll_tasks.pop(dev_id)
        if task:
            task.cancel()
    

    async def stop_polling(self) -> None:
        self._stop_evt.set()
        for dev_id, t in self._poll_tasks.items(): t.cancel()
        await asyncio.gather(*self._poll_tasks.values(), return_exceptions=True)
        self._poll_tasks.clear()
        self._stop_evt = asyncio.Event()  # allow restart

    # API helpers
    async def list_devices(self) -> List[DeviceInfo]:
        out: List[DeviceInfo] = []
        for dev_id, dev in self.devices.items():
            st = await dev.read_state()
            out.append(DeviceInfo(
                id=dev_id,
                kind=getattr(dev, "kind", "device"),
                status=("connected" if dev.is_connected else "disconnected"),
                state=st
            ))
        return out

    async def get_device_state(self, dev_id: str) -> DeviceInfo:
        dev = self.devices[dev_id]
        st = await dev.read_state()
        return DeviceInfo(
            id=dev_id,
            kind=getattr(dev, "kind", "device"),
            status=("connected" if dev.is_connected else "disconnected"),
            state=st
        )

    async def apply_properties(self, dev_id: str, properties: dict) -> DeviceInfo:
        dev = self.devices[dev_id]
        #t0=time.perf_counter();
        st = await dev.apply_properties(properties) # should not read back state - use read_state explicitely TODO 
        #t1=time.perf_counter();
        await self.event_bus.publish({"type": "device.state", "id": dev_id, "state": st})
        #t2=time.perf_counter(); print(f"set={(t1-t0)*1000:.1f}ms publish={(t2-t1)*1000:.1f}ms")
        #return await self.get_device_state(dev_id)
        return DeviceInfo(
            id=dev_id,
            kind=getattr(dev, "kind", "device"),
            status=("connected" if dev.is_connected else "disconnected"),
            state=st
        )

    async def run_command(self, dev_id: str, name: str, args: dict):     # <-- keep/add
        dev = self.devices[dev_id]
        if not hasattr(dev, "run_command"):
            raise RuntimeError("Commands not supported")
        res = await dev.run_command(name, args)
        # push latest state so GUIs reflect the action
        st = await dev.read_state()
        await self.event_bus.publish({"type":"device.state","id":dev_id,"state":st})
        return res
    
    # thin wrappers for data source - are they necessary? TODO 
    async def get_data_catalog(self, dev_id: str) -> Dict[str, Any]:
        dev = self.devices[dev_id]
        return {"device": dev_id, "sources": dev.list_data_sources()}
    
    async def get_plot_spec(self, dev_id: str, source: str) -> Dict[str, Any]:
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return ds.plot()  # {} if not provided
    
    async def get_one_frame(self, dev_id: str, source: str) -> Dict[str, Any]:
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return await ds.once()
    
    async def subscribe_stream(self, dev_id: str, source: str, *, maxsize: int = 4):
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return await ds.subscribe(maxsize=maxsize)

    async def start_stream(self, dev_id: str, source: str, *, interval: float | None):
        dev = self.devices[dev_id]
        await dev.get_datasource(source).start(interval=interval)

    async def stop_stream(self, dev_id: str, source: str):
        dev = self.devices[dev_id]
        await dev.get_datasource(source).stop()
    


    async def get_device_spec(self, dev_id: str) -> DeviceSpec:               # <-- new
        """Build a SpecResponse from driver-declared PROPERTIES/COMMANDS."""
        dev = self.devices[dev_id]
        # PROPERTIES: expect a dict meta; tolerate missing keys
        properties: List[PropertySpec] = []
        for name, meta in getattr(dev, "PROPERTIES", {}).items():
            if meta.get("type", 'Any') == 'Any':
                logger.warning(f"Property {dev.options["driver"]}.{name} has not return type specified! Add type hint to the property getter")
                continue
            properties.append(PropertySpec(
                name=name,
                read_only=bool(meta.get("read_only", False)),
                unit=meta.get("unit"),
                type=meta.get("type", object).__qualname__,  # str, int, float, bool # todo - for complex types, this does not work
                min=meta.get("min"),
                max=meta.get("max"),
                choices=meta.get("choices"),
                fields=meta.get("fields"),     # list[str] or dict – matches your schemas.py
                doc=meta.get("doc"),           # <-- add doc field
                default=meta.get("default"),   # <-- add default field
                # doc/default/step if you add them later
                # TODO - ADD STEP/DEFAULT AND DOCS FIELDS
            ))
        # COMMANDS: list[str] or list of {name, args}
        cmds: List[CommandSpec] = []
        cmd_meta = getattr(dev, "COMMANDS", [])
        if isinstance(cmd_meta, dict):
            for cname, cinfo in cmd_meta.items():
                args=[] # process args to match argspec format
                raw_args = cinfo.get("args", [])
                #print(f"  !!!!!!!!! --- command {cname} raw args = {raw_args}")
                for a in raw_args:
                    a_type = a.get("type", object)
                    if a_type is None:
                        print(f"!! Command {cname} is missing type hint for argument {a}. Add proper type hint for correct API.")
                        continue
                    qualname = a_type.__qualname__
                    if qualname == "Literal":
                        choices = get_args(a["type"])
                        type_str = type(choices[0]).__qualname__
                    else:
                        choices = None
                        type_str = qualname

                    args.append(ArgSpec(   
                        name=a.get("name"),
                        type= type_str, #_type_name(a.get("type", Any)), <-- for more complex args, this will be necessary
                        default=a.get("default"),
                        required=a.get("default", None) is None,
                        choices=choices
                    ))
                    logger.debug("type_str = %s, choices = %s", type_str, args[-1].choices)
                #print(f"  !!!!!!!!! --- command {cname} args = {args}")
                events = cinfo.get("events", {})
                cmds.append(CommandSpec(name=cname, args=args, doc=cinfo.get("doc", ""), events=events))
        else:
            for cname in cmd_meta: #COMMANDS SHOULD BE DICTIONARY, THIS SHOULD NOT HAPPEN
                cmds.append(CommandSpec(name=cname, args={}))


        # DATA SOURCES
        dss: List[DataSourceSpec] = []
        ds_meta = getattr(dev, "DATA_SOURCES")
        if isinstance(ds_meta, dict):
            for dsname, dsinfo in ds_meta.items():
                dss.append(DataSourceSpec(name=dsname, has_plot=dsinfo.get("has_plot", False), doc=dsinfo.get("doc", "")))

        dev_meta = getattr(dev, "_api_device_meta")#["doc"]
        #print("  --- inside Device Spec constructor ---")
        #print(f"dev = {dev}, dev_id = {dev_id}, dev_meta = {dev_meta}")
        return DeviceSpec(
            id=dev_id,
            kind=getattr(dev, "kind", "device"),
            doc=dev_meta.get("doc", "No docstring found in driver class"),  # <-- add doc field
            properties=properties,
            commands=cmds,
            data_sources=dss
        )

    async def apply_properties_from_file(self, properties_path) -> Dict[str, str]:
        """
        Load properties file and apply to all devices.

        Args:
            properties_path: Path to properties.yaml (Path or str)

        Returns:
            Dict[dev_id] = "success" | "skipped" | "error: <message>"

        Behavior:
            - Log and skip devices not in file
            - Log and skip devices with resolution errors
            - Continue applying to other devices on error
        """
        from .properties_loader import load_and_resolve_all, PropertyResolutionError
        from pathlib import Path

        properties_path = Path(properties_path)
        logger.info(f"Loading properties from {properties_path}")

        device_ids = list(self.devices.keys())

        try:
            resolved_all = load_and_resolve_all(properties_path, device_ids)
        except Exception as e:
            logger.error(f"Failed to load properties file: {e}")
            return {dev_id: f"error: file load failed" for dev_id in device_ids}

        results = {}

        for dev_id, device in self.devices.items():
            if dev_id not in resolved_all:
                logger.info(f"No properties for {dev_id}, skipping")
                results[dev_id] = "skipped"
                continue

            resolved_props, readout_props = resolved_all[dev_id]

            if not resolved_props and not readout_props:
                logger.info(f"No properties to apply for {dev_id}")
                results[dev_id] = "skipped"
                continue

            try:
                await device.apply_properties_from_spec(resolved_props, readout_props)
                results[dev_id] = "success"

                # Publish updated state
                state = await device.read_state()
                await self.event_bus.publish({
                    "type": "device.state",
                    "id": dev_id,
                    "state": state
                })

            except Exception as e:
                logger.error(f"Failed to apply properties to {dev_id}: {e}", exc_info=True)
                results[dev_id] = f"error: {str(e)}"

        return results

    async def apply_properties_from_dict(
        self,
        properties: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Apply properties from dict (for API endpoint).

        Args:
            properties: {dev_id: {prop_name: value | "$READOUT", ...}, ...}
                       Can include "default" key for fallback

        Returns:
            Dict[dev_id] = "success" | "skipped" | "error: <message>"
        """
        from .properties_loader import resolve_properties_for_device, PropertyResolutionError

        results = {}

        for dev_id, device in self.devices.items():
            if dev_id not in properties:
                results[dev_id] = "skipped"
                continue

            try:
                resolved_props, readout_props = resolve_properties_for_device(
                    dev_id, properties
                )

                await device.apply_properties_from_spec(resolved_props, readout_props)
                results[dev_id] = "success"

                # Publish updated state
                state = await device.read_state()
                await self.event_bus.publish({
                    "type": "device.state",
                    "id": dev_id,
                    "state": state
                })

            except PropertyResolutionError as e:
                logger.error(f"Property resolution failed for {dev_id}: {e}")
                results[dev_id] = f"error: {str(e)}"
            except Exception as e:
                logger.error(f"Failed to apply properties to {dev_id}: {e}", exc_info=True)
                results[dev_id] = f"error: {str(e)}"

        return results


