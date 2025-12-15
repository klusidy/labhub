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
import logging

from .schemas import (
    DeviceInfo,
    PatchRequest,
    DeviceSpec,
    CommandRequest,
    ApplyPropertiesRequest,
)

from .device_manager import DeviceManager
from .events import EventBus
from .utils import (
    init_logging,
    set_level as set_logging_level,
    get_level as get_logging_level,
)
from .loader import get_config_path, load_config

# Initialize logging - reads LABHUB_LOG_LEVEL and LABHUB_LOG_FILE from environment
init_logging(log_file=os.environ.get("LABHUB_LOG_FILE"))
logger = logging.getLogger(__name__)  # Uses module path automatically


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    global lock

    # --- Startup ---
    logger.info("LabHub server starting...")

    # 1. Acquire config file lock (prevents multiple servers for same config)
    config_path = os.path.abspath(get_config_path())
    digest = hashlib.sha256(config_path.encode("utf-8")).hexdigest()[:16]
    lock_path = os.path.join(tempfile.gettempdir(), f"labhub_{digest}.lock")
    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=0.1)
        logger.info(f"Acquired lock for config: {config_path}")
    except Timeout:
        logger.error(
            f"Lock acquisition failed - another instance already running for config: {config_path}"
        )
        raise RuntimeError(
            f"Another LabHub instance is already running for config: {config_path}"
        )

    # 2. Initialize devices from config
    cfg = load_config()
    await manager.initialize_devices(cfg)

    # 3. Start property polling
    await manager.start_polling(500)
    logger.info("Device polling started")

    # TODO: 4. Initialize profile monitor (for live state backup)
    # await init_profile_monitor(profile_path)

    logger.info("LabHub server ready")

    yield  # Server is running

    # --- Shutdown ---
    logger.info("LabHub server shutting down...")

    # TODO: Stop profile monitor
    # await stop_profile_monitor()

    await manager.stop_polling()
    logger.info("Device polling stopped")

    await manager.remove_all()
    logger.info("All devices disconnected")

    # Release lock
    try:
        if lock is not None:
            lock.release()
            logger.info("Config lock released")
    except Exception as e:
        logger.warning(f"Failed to release lock: {e}")

    logger.info("LabHub server stopped")


# ======= APP =========
app = FastAPI(title="LabHub", version="0.2.0", lifespan=lifespan)
event_bus = EventBus()
manager = DeviceManager(event_bus)
lock: FileLock | None = None  # Single-instance lock per CONFIG PATH

# ---- Static files / GUI ----
WEB_DIST = Path(__file__).parent.parent / "gui" / "basic" / "dist"
if WEB_DIST.exists():
    app.mount(
        "/ui", staticfiles.StaticFiles(directory=str(WEB_DIST), html=True), name="ui"
    )

# todo - gui for picoscope should not be specified separately - not extensible
GUI_PICOSCOPE_DIST = (
    Path(__file__).parent.parent.parent / "gui" / "picoscope_gui" / "dist" / "spa"
)
if GUI_PICOSCOPE_DIST.exists():
    app.mount(
        "/picoscope",
        staticfiles.StaticFiles(directory=str(GUI_PICOSCOPE_DIST), html=True),
        name="picoscope",
    )


# ---- API ----
@app.get("/api/v2/devices", response_model=list[DeviceInfo])
async def list_devices():
    return await manager.list_devices()


@app.get("/api/v2/devices/{dev_id}", response_model=DeviceInfo)
async def get_device(dev_id: str):
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await manager.get_device_state(dev_id)


@app.patch("/api/v2/devices/{dev_id}", response_model=DeviceInfo)
async def patch_device(dev_id: str, req: PatchRequest):
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    # t0=time.perf_counter();
    res = await manager.apply_properties(dev_id, req.properties)
    # print(f"PATCH total={(time.perf_counter()-t0)*1000:.1f}ms")
    return res
    # return await manager.apply_properties(dev_id, req.properties)


@app.get("/api/v2/devices/{dev_id}/spec", response_model=DeviceSpec)
async def get_device_spec(dev_id: str):
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await manager.get_device_spec(dev_id)


@app.post("/api/v2/devices/{dev_id}/commands")
async def run_command(dev_id: str, req: CommandRequest):
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    res = await manager.run_command(dev_id, req.name, req.args)
    return res


@app.post("/api/v2/admin/reload")
async def reload_all():
    """
    Reload all devices from config.yaml without restarting the process.

    This:
    1. Stops polling
    2. Disconnects all devices
    3. Reloads config
    4. Reconnects all devices
    5. Restarts polling
    """
    logger.info("Reloading all devices from config...")
    await manager.stop_polling()
    await manager.remove_all()

    # Reinitialize devices from config
    await manager.initialize_devices()

    await manager.start_polling(
        500
    )  # TODO: Make polling interval per-device configurable
    logger.info("Reload complete")

    devices = [d.model_dump() for d in await manager.list_devices()]
    return {"ok": True, "devices": devices}


@app.post("/api/v2/admin/reload/{dev_id}")
async def reload_device(dev_id: str):
    """
    Reload a single device from config.yaml.

    Useful for:
    - Recovering from device errors
    - Applying config changes to one device
    - Reconnecting after hardware issues
    """
    logger.info(f"Reloading device: {dev_id}")

    # Remove existing device if present
    if dev_id in manager.devices:
        await manager.stop_polling_device(dev_id)
        await manager.remove_device(dev_id)

    # Find device in config and re-add
    cfg = load_config()
    device_found = False
    for d in cfg.devices:
        if d.id == dev_id:
            await manager.add_device(d.id, d.driver, d.options)
            await manager.start_polling_device(d.id, 500)  # TODO: Configurable interval
            device_found = True
            logger.info(f"Device '{dev_id}' reloaded successfully")
            break

    if not device_found:
        logger.warning(f"Device '{dev_id}' not found in config")
        raise HTTPException(404, f"Device '{dev_id}' not found in config")

    devices = [d.model_dump() for d in await manager.list_devices()]
    return {"ok": True, "devices": devices}


@app.get("/api/v2/admin/loglevel")
async def admin_get_loglevel(logger_name: str | None = None):
    """
    Get current logging level.

    Args:
        logger_name: Optional specific logger (e.g., 'labhub.drivers'). If None, returns root 'labhub' logger.
    """
    return {"logger": logger_name or "labhub", "level": get_logging_level(logger_name)}


@app.post("/api/v2/admin/loglevel")
async def admin_set_loglevel(level: str, logger_name: str | None = None):
    """
    Set logging level at runtime.

    Args:
        level: Level name (DEBUG, INFO, WARNING, ERROR) or numeric value
        logger_name: Optional specific logger (e.g., 'labhub.drivers', 'labhub.drivers.kinesis').
                    If None, sets root 'labhub' logger.

    Examples:
        POST /api/v2/admin/loglevel?level=DEBUG
        POST /api/v2/admin/loglevel?level=WARNING&logger_name=labhub.drivers
    """
    try:
        res = set_logging_level(level, logger_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return res


@app.post("/api/v2/admin/apply_properties")
async def apply_properties_endpoint(req: ApplyPropertiesRequest):
    """Apply properties from file or inline dict. Does NOT restart devices."""
    if req.file_path:
        path = Path(req.file_path)
        if not path.exists():
            raise HTTPException(404, f"Properties file not found: {path}")
        results = await manager.apply_properties_from_file(path)
    elif req.properties:
        results = await manager.apply_properties_from_dict(req.properties)
    else:
        raise HTTPException(400, "Must provide file_path or properties")

    return {"status": "ok", "results": results}


from time import monotonic


@app.websocket("/api/v2/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    qp = dict(ws.query_params)
    want_ids = set(qp["ids"].split(",")) if qp.get("ids") else None
    rate_hz = float(qp.get("rate", 0) or 0)
    min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0
    last_sent = 0.0

    q = await event_bus.subscribe()
    try:
        # initial snapshot (respect ids filter)
        snap = [d.model_dump() for d in await manager.list_devices()]
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
        await event_bus.unsubscribe(q)


# todo - review if this api structure is extensible for new plots
@app.get("/api/v2/devices/{dev_id}/data")
async def get_data_catalog(dev_id: str) -> Dict[str, Any]:
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    return await manager.get_data_catalog(dev_id)


@app.get("/api/v2/devices/{dev_id}/data/{source}/plot")  # todo - change to lineplot?
async def get_plot_spec(dev_id: str, source: str) -> Dict[str, Any]:
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    # 404 if unknown source
    try:
        return await manager.get_plot_spec(dev_id, source)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/v2/devices/{dev_id}/data/{source}/frame")
async def get_one_frame(dev_id: str, source: str) -> Dict[str, Any]:
    if dev_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{dev_id}'")
    try:
        return await manager.get_one_frame(dev_id, source)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.websocket("/api/v2/streams/{dev_id}/{source}")
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

    # send_hz = float(qps.get("rate", 10))
    # send_period = (1.0 / send_hz) if send_hz > 0 else 0.1 # todo - use this somehow

    prod_hz = float(qps.get("rate", 12.5))  # producer should be slighlty faster I guess
    prod_interval = (1.0 / prod_hz) if prod_hz > 0 else 0.08

    # Subscribe
    if dev_id not in manager.devices:
        await ws.close(code=4404)
        return
    try:
        q = await manager.subscribe_stream(dev_id, source, maxsize=64)
    except KeyError:
        await ws.close(code=4404)
        return

    # If caller provided a rate, start (hot) producer for this source
    if prod_interval is not None:
        await manager.start_stream(dev_id, source, interval=prod_interval)

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
            dev = manager.devices[dev_id]
            await dev.get_datasource(source).unsubscribe(q)
        except Exception:
            pass


# @app.websocket("/api/v2/streams/{dev_id}")
# async def ws_stream(ws: WebSocket, dev_id: str, rate : int=10, format: str = "json"):
#     await ws.accept()
#     format = ws.query_params.get("format", "msgpack").lower()
#     rate_hz = float(ws.query_params.get("rate", 0) or 0)
#     min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0

#     dev = manager.devices.get(dev_id, None)
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

# @app.websocket("/api/v2/streams/{dev_id}")
# async def ws_stream(ws: WebSocket, dev_id: str):
#     await ws.accept()
#     fmt = ws.query_params.get("format", "msgpack").lower()  # "msgpack" (default) or "json"
#     rate_hz = float(ws.query_params.get("rate", 0) or 0)
#     min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0
#     last_sent = 0.0

#     if dev_id not in manager.devices:
#         await ws.close(code=1008)
#         return

#     q = await event_bus.subscribe()
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
#         await event_bus.unsubscribe(q)
