
from __future__ import annotations
import asyncio, json, os, tempfile, hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, staticfiles
from typing import Dict, List, Any
from filelock import FileLock, Timeout
import yaml
import time
from dataclasses import dataclass
from pathlib import Path
import msgpack
import pdb # for live debugging



from .schemas import DeviceInfo, PatchRequest, DeviceSpec, CommandRequest
from .device_manager import DeviceManager
from .events import EventBus
from ._logging import init_logging
import logging
from ._logging import set_level as set_logging_level, get_level as get_logging_level




# ---- Logging ----
init_logging()
logger = logging.getLogger("labhub.main")

# ---- Config helpers ----
def get_config_path() -> str:
    # Priority: app.state.config_path (set by factory/CLI) -> LABHUB_CONFIG env -> hub/config.yaml (default)
    cp = getattr(app.state, "config_path", None) if "app" in globals() else None
    if cp and str(cp).strip():
        return str(cp)
    env_cp = os.environ.get("LABHUB_CONFIG")
    if env_cp and str(env_cp).strip():
        return env_cp
    return str(Path(__file__).resolve().parents[1] / "config.yaml")

@dataclass
class DeviceCfg:
    id: str
    driver: str
    options: Dict[str, Any] #full dict from config.yaml for that device (incl. id and driver)

@dataclass
class HubCfg:
    devices: List[DeviceCfg]



def load_config() -> HubCfg:
    config_path = get_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    devices: List[DeviceCfg] = []
    for d in raw.get("devices", []):
        # TODO: what if "id" or "driver" is missing?
        devices.append(DeviceCfg(id=d["id"], driver=d["driver"], options=d))
    return HubCfg(devices=devices)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _lock
    cfg_path = os.path.abspath(get_config_path())
    digest = hashlib.sha256(cfg_path.encode("utf-8")).hexdigest()[:16]
    lock_path = os.path.join(tempfile.gettempdir(), f"labhub_{digest}.lock")
    _lock = FileLock(lock_path)
    try:
        _lock.acquire(timeout=0.1)
    except Timeout:
        raise RuntimeError(f"Another LabHub instance is already running for config: {cfg_path}")

    cfg = load_config()

    add_tasks = [asyncio.create_task(_manager.add_device(d.id, d.driver, d.options)) for d in cfg.devices]
    results = await asyncio.gather(*add_tasks, return_exceptions=True)

    for d, res in zip(cfg.devices, results):
        if isinstance(res, Exception):
            logger.error("Device '%s' failed to add: %r", d.id, res)
            raise res


    #for d in cfg.devices:
    #    logger.debug("-------- adding device based on config ---------------")
    #    await _manager.add_device(d.id, d.driver, d.options)
    #for d in cfg.devices:
    #    asyncio.create_task(_manager.add_device(d.id, d.driver, d.options))

    await _manager.start_polling(500)
    yield
    # shutdown
    # Clean up the ML models and release the resources
    await _manager.stop_polling()
    await _manager.remove_all()
    try:
        if _lock is not None:
            _lock.release()
    except Exception:
        pass

# ---- App ----
app = FastAPI(title="LabHub", version="0.1.3", lifespan=lifespan)
_event_bus = EventBus()
_manager = DeviceManager(_event_bus)

# Single-instance lock per CONFIG PATH
_lock: FileLock | None = None

WEB_DIST = Path(__file__).parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/ui", staticfiles.StaticFiles(directory=str(WEB_DIST), html=True), name="ui")

# ---- API ----
@app.get("/api/v1/devices", response_model=list[DeviceInfo])
async def list_devices():
    return await _manager.list_devices()

@app.get("/api/v1/devices/{dev_id}", response_model=DeviceInfo)
async def get_device(dev_id: str):
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await _manager.get_device_state(dev_id)

@app.patch("/api/v1/devices/{dev_id}", response_model=DeviceInfo)
async def patch_device(dev_id: str, req: PatchRequest):
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    #t0=time.perf_counter(); 
    res = await _manager.apply_properties(dev_id, req.properties)
    #print(f"PATCH total={(time.perf_counter()-t0)*1000:.1f}ms")
    return res
    #return await _manager.apply_properties(dev_id, req.properties)

@app.get("/api/v1/devices/{dev_id}/spec", response_model=DeviceSpec)
async def get_device_spec(dev_id: str):
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await _manager.get_device_spec(dev_id)

@app.post("/api/v1/devices/{dev_id}/commands")
async def run_command(dev_id: str, req: CommandRequest):
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    res = await _manager.run_command(dev_id, req.name, req.args)
    return res

@app.post("/api/v1/admin/reload")
async def reload_all():
    """Reload config.yaml without restarting the process."""
    await _manager.stop_polling()
    await _manager.remove_all()
    cfg = load_config()
    for d in cfg.devices: # TODO - CHANGE TO ASYNC GATHER
        await _manager.add_device(d.id, d.driver, d.options)
    await _manager.start_polling(500) #TODO - make param of each device
    devices = [d.model_dump() for d in await _manager.list_devices()]
    return {"ok": True, "devices": devices}

@app.post("/api/v1/admin/reload/{dev_id}")
async def reload_device(dev_id: str):
    """Remove and add a (presumably) faulty device"""
    if dev_id in _manager.devices:
        await _manager.stop_polling_device(dev_id)
        await _manager.remove_device(dev_id)
    
    cfg = load_config()
    for d in cfg.devices: # TODO - CHANGE TO ASYNC GATHER
        if d.id == dev_id:
            await _manager.add_device(d.id, d.driver, d.options)
            await _manager.start_polling_device(d.id, 500)
    devices = [d.model_dump() for d in await _manager.list_devices()]
    return {"ok": True, "devices": devices}


@app.get("/api/v1/admin/loglevel")
async def admin_get_loglevel():
    """Get current root logging level."""
    return {"level": get_logging_level()}


@app.post("/api/v1/admin/loglevel")
async def admin_set_loglevel(level: str):
    """Set root logging level. Accepts names like DEBUG, INFO or numeric values."""
    try:
        res = set_logging_level(level)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return res

from time import monotonic

@app.websocket("/api/v1/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    qp = dict(ws.query_params)
    want_ids = set(qp["ids"].split(",")) if qp.get("ids") else None
    rate_hz = float(qp.get("rate", 0) or 0)
    min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0
    last_sent = 0.0

    q = await _event_bus.subscribe()
    try:
        # initial snapshot (respect ids filter)
        snap = [d.model_dump() for d in await _manager.list_devices()]
        if want_ids:
            snap = [d for d in snap if d["id"] in want_ids]
        await ws.send_text(json.dumps({"type": "snapshot", "devices": snap}))

        while True:
            ev = await q.get()
            if ev.get("type") != "device.state":
                continue  # state only on this WS
            if want_ids and ev.get("id") not in want_ids:
                continue
            if min_period > 0:
                now = monotonic()
                if (now - last_sent) < min_period:
                    continue
                last_sent = now
            await ws.send_text(json.dumps(ev))
    except WebSocketDisconnect:
        pass
    finally:
        await _event_bus.unsubscribe(q)

# todo - review if this api structure is extensible for new plots
@app.get("/api/v1/devices/{dev_id}/data")
async def get_data_catalog(dev_id: str) -> Dict[str, Any]:
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await _manager.get_data_catalog(dev_id)

@app.get("/api/v1/devices/{dev_id}/data/{source}/plot") # todo - change to lineplot?
async def get_plot_spec(dev_id: str, source: str) -> Dict[str, Any]:
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    # 404 if unknown source
    try:
        return await _manager.get_plot_spec(dev_id, source)
    except KeyError as e:
        raise HTTPException(404, str(e))

@app.get("/api/v1/devices/{dev_id}/data/{source}/frame")
async def get_one_frame(dev_id: str, source: str) -> Dict[str, Any]:
    if dev_id not in _manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    try:
        return await _manager.get_one_frame(dev_id, source)
    except KeyError as e:
        raise HTTPException(404, str(e))

@app.websocket("/api/v1/streams/{dev_id}/{source}")
async def ws_stream(ws: WebSocket, dev_id: str, source: str):
    await ws.accept()

    # Optional rate limiting: ?rate=10  -> interval=0.1s
    qps = dict(ws.query_params)
    # interval = None
    # if qps:
    #     try:
    #         hz = float(qps)
    #         interval = (1.0 / hz) if hz > 0 else None
    #     except Exception:
    #         interval = None

    #send_hz = float(qps.get("rate", 10))
    #send_period = (1.0 / send_hz) if send_hz > 0 else 0.1 # todo - use this somehow

    prod_hz = float(qps.get("rate", 12.5)) # producer should be slighlty faster I guess
    prod_interval = (1.0 / prod_hz) if prod_hz > 0 else 0.08

    # Subscribe
    if dev_id not in _manager.devices:
        await ws.close(code=4404)
        return
    try:
        q = await _manager.subscribe_stream(dev_id, source, maxsize=64)
    except KeyError:
        await ws.close(code=4404)
        return

    # If caller provided a rate, start (hot) producer for this source
    if prod_interval is not None:
        await _manager.start_stream(dev_id, source, interval=prod_interval)

    try:
        while True:
            frame = await q.get()
            # Send as JSON; if you add msgpack later, branch on ?format=
            # TODO THROTTLE SENDING STUFF
            await ws.send_json(frame)
    except WebSocketDisconnect:
        pass
    finally:
        # best-effort cleanup
        try:
            dev = _manager.devices[dev_id]
            await dev.get_datasource(source).unsubscribe(q)
        except Exception:
            pass

# @app.websocket("/api/v1/streams/{dev_id}")
# async def ws_stream(ws: WebSocket, dev_id: str, rate : int=10, format: str = "json"):
#     await ws.accept()
#     format = ws.query_params.get("format", "msgpack").lower()
#     rate_hz = float(ws.query_params.get("rate", 0) or 0)
#     min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0

#     dev = _manager.devices.get(dev_id, None)
#     if dev is None or not hasattr(dev, "subscribe_stream"):
#         await ws.close(code=1008)
#         return
    
#     q = dev.subscribe_stream()
#     try:
#         while True:
#             stream_frame = await q.get() # read whatever was pushed to the queue by the device
#             if format == "json":
#                 await ws.send_text(json.dumps(stream_frame))
#             else:
#                 await ws.send_bytes(msgpack.packb(stream_frame, use_bint_type=True))
#             await asyncio.sleep(min_period)
#     except WebSocketDisconnect:
#         pass
#     finally:
#         dev.unsubscribe_stream(q)

# @app.websocket("/api/v1/streams/{dev_id}")
# async def ws_stream(ws: WebSocket, dev_id: str):
#     await ws.accept()
#     fmt = ws.query_params.get("format", "msgpack").lower()  # "msgpack" (default) or "json"
#     rate_hz = float(ws.query_params.get("rate", 0) or 0)
#     min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0
#     last_sent = 0.0

#     if dev_id not in _manager.devices:
#         await ws.close(code=1008)
#         return

#     q = await _event_bus.subscribe()
#     try:
#         while True:
#             ev = await q.get()
#             if ev.get("type") != "device.data" or ev.get("id") != dev_id:
#                 continue
#             chunk = ev.get("stream")
#             if not chunk:
#                 continue
#             if min_period > 0:
#                 now = monotonic()
#                 if (now - last_sent) < min_period:
#                     continue
#                 last_sent = now
#             if fmt == "json":
#                 await ws.send_text(json.dumps(chunk))
#             else:
#                 import msgpack
#                 await ws.send_bytes(msgpack.packb(chunk, use_bin_type=True))
#     except WebSocketDisconnect:
#         pass
#     finally:
#         await _event_bus.unsubscribe(q)

