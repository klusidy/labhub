from __future__ import annotations
import asyncio, json, os, tempfile, hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, staticfiles, Body
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
    SaveMacroFileRequest,
)

from .device_manager import DeviceManager
from .events import EventBus
from .utils import init_logging
from .server_config import load_server_config, set_server_config, get_server_config
from .loader import load_config
from .monitor import ProfileMonitor
from .influx import InfluxWriter, InfluxStateMonitor
from .macros import MacroManager
from .repl_session import ReplSessionManager
from . import admin

# Load server config (from LABHUB_SERVER_CONFIG env var, ./server.yaml, or defaults)
server_cfg = load_server_config()
set_server_config(server_cfg)

# Initialize logging from server config
init_logging(level=server_cfg.logging.level, log_file=server_cfg.logging.file)
logger = logging.getLogger("labhub.main")


async def _background_device_startup() -> None:
    """Connect all devices, start polling, InfluxDB, and profile monitor.

    Runs as a background asyncio task so the HTTP server becomes reachable
    immediately after the lock is acquired.  Devices that take a long time
    to connect (or are unreachable) show as 'connecting'/'disconnected' in
    the GUI without blocking server startup.
    """
    global influx_writer, influx_monitor

    try:
        cfg = load_config(str(server_cfg.devices_path))
        await manager.initialize_devices(cfg)

        await manager.start_polling()
        logger.info("Device polling started")

        influx_cfg = server_cfg.to_influx_cfg()
        if influx_cfg.enabled:
            logger.info("Initializing InfluxDB integration...")
            try:
                influx_writer = InfluxWriter(influx_cfg)
                await influx_writer.start()
                manager.influx = influx_writer
                influx_monitor = InfluxStateMonitor(
                    influx_writer, manager, influx_cfg.snapshot_interval
                )
                await influx_monitor.start()
                logger.info("InfluxDB integration ready")
            except Exception as e:
                logger.warning(f"InfluxDB failed to initialize: {e} - continuing without telemetry")

        await asyncio.sleep(2.0)  # Allow polling to populate initial cache

        profile_path = str(server_cfg.profile_path)
        await profile_monitor.load_profile(profile_path)
        await profile_monitor.start()
        logger.info(f"Profile monitor started (path={profile_path})")

        logger.info("LabHub device startup complete")

    except asyncio.CancelledError:
        logger.info("Device startup cancelled (server shutting down)")
        raise
    except Exception as e:
        logger.error(f"Device startup failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    global lock, macro_manager, repl_manager

    # --- Startup ---
    logger.info("LabHub server starting...")

    # 1. Acquire lock keyed on server.yaml path (prevents multiple servers)
    server_config_path = str(server_cfg.config_file)
    digest = hashlib.sha256(server_config_path.encode("utf-8")).hexdigest()[:16]
    lock_path = os.path.join(tempfile.gettempdir(), f"labhub_{digest}.lock")
    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=0.1)
        logger.info(f"Acquired lock for: {server_config_path}")
    except Timeout:
        logger.error(
            f"Lock acquisition failed - another instance already running for: {server_config_path}"
        )
        raise RuntimeError(
            f"Another LabHub instance is already running for: {server_config_path}"
        )

    # 2. Wire profile monitor to admin endpoints (available immediately, before devices connect)
    admin.profile_monitor = profile_monitor

    # 3. Initialize macro manager (fast, no hardware)
    macros_path = server_cfg.macros_path
    if macros_path:
        macro_manager = MacroManager(macros_path)
        logger.info(f"Macro manager initialized (path={macros_path})")
    else:
        logger.info("Macro manager not configured")

    # 4. Initialize REPL session manager (fast, no hardware)
    project_root = Path(__file__).parent.parent
    repl_manager = ReplSessionManager(
        server_cfg.python_path, project_root, macros_path, server_cfg.startup_folder_path
    )
    logger.info(f"REPL session manager initialized (startup_folder={server_cfg.startup_folder_path})")

    # 5. Start device initialization as a background task.
    #    The HTTP server becomes reachable immediately; devices connect asynchronously
    #    and show a 'connecting' status while their connection is being established.
    _init_task = asyncio.create_task(_background_device_startup())

    logger.info("LabHub server ready (devices connecting in background)")

    yield  # Server is running

    # --- Shutdown ---
    logger.info("LabHub server shutting down...")

    # Cancel background device startup if still in progress
    if not _init_task.done():
        _init_task.cancel()
        try:
            await _init_task
        except (asyncio.CancelledError, Exception):
            pass

    # Stop all REPL sessions first
    if repl_manager:
        await repl_manager.close_all_sessions()
        logger.info("All REPL sessions closed")

    # Stop InfluxDB (flush pending writes before other cleanup)
    if influx_monitor:
        await influx_monitor.stop()
        logger.info("InfluxDB state monitor stopped")
    if influx_writer:
        await influx_writer.stop()
        logger.info("InfluxDB writer stopped")

    # Stop profile monitor (saves pending changes)
    await profile_monitor.stop()
    logger.info("Profile monitor stopped")

    await manager.stop_polling()
    logger.info("Device polling stopped")

    await manager.remove_all()
    logger.info("All devices disconnected")

    await manager.shutdown()
    logger.info("Device manager shutdown complete")

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
manager = DeviceManager(event_bus, max_workers=server_cfg.server.max_workers)
profile_monitor: ProfileMonitor | None = ProfileMonitor(
    event_bus, manager, save_interval=10.0
)  # Profile auto-save monitor
lock: FileLock | None = None  # Single-instance lock per CONFIG PATH

# InfluxDB integration (optional, initialized in lifespan if configured)
influx_writer: InfluxWriter | None = None
influx_monitor: InfluxStateMonitor | None = None

# Macro management (optional, initialized in lifespan if configured)
macro_manager: MacroManager | None = None

# REPL session management
repl_manager: ReplSessionManager | None = None

# Include admin router and set manager dependency
admin.manager = manager
app.include_router(admin.router)


# ---- Static files / GUI ----
_PROJECT_ROOT = Path(__file__).parent.parent

# Built-in GUIs (part of the product, always resolved relative to project root)
_BUILTIN_GUIS = [
    ("v1ui", "gui/basic/dist"),
    ("ui",   "gui/basic2/dist/spa"),
    ("devices", "gui/devices/dist/spa"),
    ("profile", "gui/profile/dist/spa"),
    ("macros",  "gui/macros/dist/spa"),
]

for _route, _rel in _BUILTIN_GUIS:
    _dist = _PROJECT_ROOT / _rel
    if _dist.exists():
        app.mount(
            f"/{_route}",
            staticfiles.StaticFiles(directory=str(_dist), html=True),
            name=_route,
        )

# Custom GUIs from server.yaml
for _gui in server_cfg.custom_guis:
    _dist = server_cfg.resolve_gui_dist(_gui)
    if _dist.exists():
        app.mount(
            _gui.route,
            staticfiles.StaticFiles(directory=str(_dist), html=True),
            name=_gui.device_id,
        )
        logger.info(f"Custom GUI mounted: {_gui.route} -> {_dist}")
    else:
        logger.warning(f"Custom GUI dist not found: {_dist} (route: {_gui.route})")



# ---- API helpers ----

def _resolve(path: str):
    """Navigate the device tree by slash-separated path and return the target device.

    The first segment is looked up in manager.devices (root devices).
    Subsequent segments traverse device.children.

    Examples:
        "red_pitaya"          → root device
        "red_pitaya/osc"      → osc child of red_pitaya
        "red_pitaya/osc/ch_a" → ch_a grandchild

    Raises:
        KeyError: if any segment is not found (caller converts to 404).
    """
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        raise KeyError("empty device path")
    dev = manager.devices[parts[0]]
    for part in parts[1:]:
        dev = dev.children[part]
    return dev


def _root_id(path: str) -> str:
    """Return the root device id from a slash-separated path."""
    return path.strip("/").split("/")[0]


# ---- API ----
@app.get("/api/v2/devices", response_model=list[DeviceInfo])
async def list_devices():
    """
    List all registered devices with their current state.

    Returns:
        List[DeviceInfo]: Array of device information objects, each containing:
            - id: Device identifier
            - kind: Device type (e.g., "piezo", "scope")
            - status: Connection status ("connected" or "disconnected")
            - state: Current property values

    Notes:
        - Returns empty list if no devices are configured
        - Includes disconnected devices with their last known state
    """
    logger.debug("GET /api/v2/devices - listing all devices")
    try:
        return await manager.list_devices()
    except Exception as e:
        logger.error(f"Failed to list devices: {e}", exc_info=True)
        raise HTTPException(500, f"Internal error while listing devices: {str(e)}")


# NOTE: routes with path suffixes (/spec, /commands, /data/…) MUST be
# registered before the bare {path:path} GET/PATCH catch-alls, otherwise
# FastAPI's greedy path parameter would consume the suffix.

@app.get("/api/v2/devices/{path:path}/spec", response_model=DeviceSpec)
async def get_device_spec(path: str):
    """Get device (or sub-device) specification.

    Path examples:
        /api/v2/devices/red_pitaya/spec          → root device spec
        /api/v2/devices/red_pitaya/osc/spec      → osc module spec
    """
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")
    try:
        return dev.build_spec(path)
    except Exception as e:
        logger.error(f"Failed to build spec for '{path}': {e}", exc_info=True)
        raise HTTPException(500, f"Error reading device specification: {str(e)}")


@app.get("/api/v2/devices/{path:path}/data/{source}/plot")
async def get_plot_spec(path: str, source: str):
    """Get plot specification for a data source on any device in the tree."""
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")
    try:
        ds = dev.get_datasource(source)
        return ds.plot()
    except KeyError:
        raise HTTPException(404, f"Unknown data source '{source}'")
    except Exception as e:
        raise HTTPException(500, f"Error reading plot spec: {str(e)}")


@app.get("/api/v2/devices/{path:path}/data/{source}/frame")
async def get_one_frame(path: str, source: str):
    """Get a single data frame from a source on any device in the tree."""
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")
    try:
        ds = dev.get_datasource(source)
        return await ds.once()
    except KeyError:
        raise HTTPException(404, f"Unknown data source '{source}'")
    except Exception as e:
        raise HTTPException(500, f"Error acquiring frame: {str(e)}")


@app.get("/api/v2/devices/{path:path}/data")
async def get_data_catalog(path: str):
    """List available data sources for a device at any depth in the tree."""
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")
    try:
        return {"device": path, "sources": dev.list_data_sources()}
    except Exception as e:
        raise HTTPException(500, f"Error reading data catalog: {str(e)}")


@app.post("/api/v2/devices/{path:path}/commands")
async def run_command(path: str, req: CommandRequest):
    """Execute a command on a device at any depth in the tree.

    After the command completes the root device's full state is published
    to the event bus so all WebSocket clients stay in sync.
    """
    root_id = _root_id(path)
    if root_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{root_id}'")
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")

    try:
        res = await dev.run_command(req.name, req.args)
    except ValueError as e:
        raise HTTPException(400, f"Invalid command: {str(e)}")
    except Exception as e:
        logger.error(f"Command '{req.name}' failed on '{path}': {e}", exc_info=True)
        raise HTTPException(500, f"Command execution failed: {str(e)}")

    # Publish full root state so WS clients stay in sync
    root_dev = manager.devices[root_id]
    st = await root_dev.read_state()
    await event_bus.publish({"type": "device.state", "id": root_id, "state": st})
    return res


# --- State read / property write (bare path — registered LAST among GETs) ---

@app.get("/api/v2/devices/{path:path}", response_model=DeviceInfo)
async def get_device(path: str):
    """Get current state for a device at any depth in the tree.

    Args:
        path: Slash-separated device path (e.g. "red_pitaya/osc/ch_a")

    Returns:
        DeviceInfo: Device information including:
            - id: Device identifier
            - kind: Device type
            - status: Connection status
            - state: Current property values (nested for composite devices)

    Raises:
        HTTPException(404): Device not found in configuration
        HTTPException(500): Error reading device state
    """
    logger.debug(f"GET /api/v2/devices/{path}")
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")
    try:
        st = await dev.read_state()
        return DeviceInfo(
            id=path,
            driver=dev._api_driver,
            status=dev._status,
            state=st,
        )
    except Exception as e:
        logger.error(f"Failed to get state for '{path}': {e}", exc_info=True)
        raise HTTPException(500, f"Error reading device state: {str(e)}")


@app.patch("/api/v2/devices/{path:path}", response_model=DeviceInfo)
async def patch_device(path: str, req: PatchRequest):
    """Update properties on a device at any depth in the tree.

    The full nested state of the ROOT device is published to the event bus
    after applying so all WebSocket clients stay in sync.
    """
    root_id = _root_id(path)
    if root_id not in manager.devices:
        raise HTTPException(404, f"Unknown device '{root_id}'")
    try:
        dev = _resolve(path)
    except KeyError:
        raise HTTPException(404, f"Unknown device path '{path}'")

    try:
        st = await dev.apply_properties(req.properties)
    except ValueError as e:
        raise HTTPException(400, f"Invalid property: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to apply properties to '{path}': {e}", exc_info=True)
        raise HTTPException(500, f"Error applying properties: {str(e)}")

    # Publish full root state (nested) so WS clients see the complete picture
    root_dev = manager.devices[root_id]
    root_state = await root_dev.read_state()
    await event_bus.publish({"type": "device.state", "id": root_id, "state": root_state})

    return DeviceInfo(id=path, driver=dev._api_driver, status=dev._status, state=st)


from time import monotonic


@app.websocket("/api/v2/events")
async def ws_events(ws: WebSocket):
    """
    WebSocket endpoint for real-time device state updates.

    Clients receive:
    1. Initial snapshot of all (or filtered) device states
    2. Real-time state updates as properties change

    Query Parameters:
        ids: Optional comma-separated device IDs to filter (e.g., "piezo1,scope")
        rate: Optional max update rate in Hz (e.g., 10 for 10 updates/sec)

    Message Format:
        Snapshot: {"type": "snapshot", "devices": [DeviceInfo, ...]}
        Update: {"type": "device.state", "id": dev_id, "state": {...}}

    Notes:
        - Rate limiting is client-side (server may send faster than requested)
        - Connection closed on client disconnect
        - Subscribe to event bus on connect, unsubscribe on disconnect
    """
    await ws.accept()
    qp = dict(ws.query_params)
    want_ids = set(qp["ids"].split(",")) if qp.get("ids") else None
    rate_hz = float(qp.get("rate", 0) or 0)
    min_period = (1.0 / rate_hz) if rate_hz > 0 else 0.0
    last_sent = 0.0

    logger.debug(
        f"WS /api/v2/events - client connected (filters: ids={want_ids}, rate={rate_hz}Hz)"
    )

    q = await event_bus.subscribe()
    try:
        # Send initial snapshot (respect ids filter)
        snap = [d.model_dump() for d in await manager.list_devices()]
        if want_ids:
            snap = [d for d in snap if d["id"] in want_ids]
        await ws.send_text(json.dumps({"type": "snapshot", "devices": snap}))
        logger.debug(f"WS /api/v2/events - sent snapshot ({len(snap)} devices)")

        # Stream state updates
        while True:
            ev = await q.get()
            if ev.get("type") != "device.state":
                continue  # Only device state updates on this endpoint
            if want_ids and ev.get("id") not in want_ids:
                continue  # Filter by device ID
            if min_period > 0:
                now = monotonic()
                if (now - last_sent) < min_period:
                    continue  # Rate limiting
                last_sent = now
            await ws.send_text(json.dumps(ev))

    except WebSocketDisconnect:
        logger.debug("WS /api/v2/events - client disconnected")
    except Exception as e:
        logger.error(f"WS /api/v2/events - error: {e}", exc_info=True)
    finally:
        await event_bus.unsubscribe(q)



@app.websocket("/api/v2/streams/{full_path:path}")
async def ws_stream(ws: WebSocket, full_path: str):
    """WebSocket endpoint for streaming data from any device in the tree.

    Path format:  /api/v2/streams/{device_path}/{source}
    The LAST path segment is the data source name; everything before it is the
    device path navigated via _resolve().

    Examples:
        /api/v2/streams/picoscope/time_stream        → root device source
        /api/v2/streams/red_pitaya/osc/scope_stream  → child device source

    Query Parameters:
        rate: Acquisition rate in Hz (default 12.5)
    """
    await ws.accept()

    # Split last segment as source name
    parts = [p for p in full_path.strip("/").split("/") if p]
    if len(parts) < 2:
        logger.warning(f"WS stream: invalid path '{full_path}' (need device/source)")
        await ws.close(code=4404)
        return

    source = parts[-1]
    device_path = "/".join(parts[:-1])

    qps = dict(ws.query_params)
    prod_hz = float(qps.get("rate", 12.5))
    prod_interval = (1.0 / prod_hz) if prod_hz > 0 else 0.08

    logger.debug(f"WS /api/v2/streams/{full_path} - client connected (rate={prod_hz}Hz)")

    # Resolve device
    try:
        dev = _resolve(device_path)
    except KeyError:
        logger.warning(f"WS stream: device not found at '{device_path}'")
        await ws.close(code=4404)
        return

    # Subscribe to data source
    try:
        ds = dev.get_datasource(source)
        q = await ds.subscribe(maxsize=64)
    except KeyError:
        logger.warning(f"WS stream: source '{source}' not found on '{device_path}'")
        await ws.close(code=4404)
        return
    except Exception as e:
        logger.error(f"WS stream: subscribe failed for '{full_path}': {e}", exc_info=True)
        await ws.close(code=1011)
        return

    # Start acquisition
    try:
        await ds.start(interval=prod_interval)
    except Exception as e:
        logger.error(f"WS stream: start failed for '{full_path}': {e}", exc_info=True)
        await ws.close(code=1011)
        return

    # Stream frames
    frame_count = 0
    try:
        while True:
            frame = await q.get()
            await ws.send_json(frame)
            frame_count += 1
    except WebSocketDisconnect:
        logger.debug(f"WS stream: client disconnected from '{full_path}' ({frame_count} frames)")
    except Exception as e:
        logger.error(f"WS stream: error on '{full_path}': {e}", exc_info=True)
    finally:
        try:
            await ds.unsubscribe(q)
        except Exception as e:
            logger.warning(f"WS stream: cleanup failed for '{full_path}': {e}")


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


# ---- Macro API ----
@app.get("/api/v2/macros")
async def list_macros() -> List[Dict[str, Any]]:
    """
    List all macro files with their function signatures.

    Returns:
        List of macro files with functions:
            - filename: Name of the .py file
            - functions: List of function definitions
                - name: Function name
                - args: List of argument definitions
                - doc: Docstring (if present)
            - error: Parse error (if any)

    Raises:
        HTTPException(503): Macros not configured
    """
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug("GET /api/v2/macros - listing macro files")
    try:
        return macro_manager.list_files()
    except Exception as e:
        logger.error(f"Failed to list macros: {e}", exc_info=True)
        raise HTTPException(500, f"Error listing macros: {str(e)}")


@app.post("/api/v2/macros/refresh")
async def refresh_macros() -> Dict[str, Any]:
    """
    Refresh the macro file list by rescanning the macros folder.

    Returns:
        Status message with count of files loaded.

    Raises:
        HTTPException(503): Macros not configured
    """
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug("POST /api/v2/macros/refresh - refreshing macro list")
    try:
        macro_manager.refresh()
        files = macro_manager.list_files()
        return {"status": "ok", "files_loaded": len(files)}
    except Exception as e:
        logger.error(f"Failed to refresh macros: {e}", exc_info=True)
        raise HTTPException(500, f"Error refreshing macros: {str(e)}")


@app.get("/api/v2/macros/files/{filename}")
async def get_macro_file(filename: str) -> Dict[str, Any]:
    """
    Get the source code of a macro file.

    Args:
        filename: Name of the macro file (e.g., "my_macros.py")

    Returns:
        Dict with:
            - filename: Name of the file
            - content: Source code as string

    Raises:
        HTTPException(503): Macros not configured
        HTTPException(404): File not found
    """
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug(f"GET /api/v2/macros/files/{filename}")

    content = macro_manager.get_file_content(filename)
    if content is None:
        raise HTTPException(404, f"Macro file not found: {filename}")

    return {"filename": filename, "content": content}


@app.post("/api/v2/macros/files/{filename}")
async def save_macro_file(filename: str, req: SaveMacroFileRequest) -> Dict[str, Any]:
    """
    Save the source code of a macro file.

    Args:
        filename: Name of the macro file (e.g., "my_macros.py")
        req: Request body with content field

    Returns:
        Status message.

    Raises:
        HTTPException(503): Macros not configured
        HTTPException(400): Invalid filename or save failed
    """
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug(f"POST /api/v2/macros/files/{filename}")

    success = macro_manager.save_file_content(filename, req.content)
    if not success:
        raise HTTPException(400, f"Failed to save macro file: {filename}")

    return {"status": "ok", "filename": filename}


@app.put("/api/v2/macros/files/{filename}")
async def create_macro_file(filename: str) -> Dict[str, Any]:
    """Create a new empty macro file."""
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug(f"PUT /api/v2/macros/files/{filename}")

    success = macro_manager.create_file(filename)
    if not success:
        raise HTTPException(400, f"Failed to create macro file: {filename}")

    return {"status": "ok", "filename": filename}


@app.delete("/api/v2/macros/files/{filename}")
async def delete_macro_file(filename: str) -> Dict[str, Any]:
    """Delete a macro file."""
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    logger.debug(f"DELETE /api/v2/macros/files/{filename}")

    success = macro_manager.delete_file(filename)
    if not success:
        raise HTTPException(400, f"Failed to delete macro file: {filename}")

    return {"status": "ok", "filename": filename}


@app.post("/api/v2/macros/files/{filename}/rename")
async def rename_macro_file(
    filename: str, req: Dict[str, str] = Body(...)
) -> Dict[str, Any]:
    """Rename a macro file."""
    if macro_manager is None:
        raise HTTPException(503, "Macros not configured")

    new_name = req.get("new_name", "")
    if not new_name:
        raise HTTPException(400, "new_name is required")

    logger.debug(f"POST /api/v2/macros/files/{filename}/rename -> {new_name}")

    success = macro_manager.rename_file(filename, new_name)
    if not success:
        raise HTTPException(400, f"Failed to rename macro file: {filename}")

    return {"status": "ok", "old_name": filename, "new_name": new_name}


# ======= REPL ENDPOINTS =======


@app.post("/api/v2/repl/session/start")
async def start_repl_session(client_id: str = Body(..., embed=True)) -> Dict[str, Any]:
    """
    Start a new REPL session or reconnect to existing one.

    Args:
        client_id: Unique identifier for the client (GUI instance)

    Returns:
        Session information including session_id and status

    Raises:
        HTTPException(500): Failed to create session
    """
    if repl_manager is None:
        raise HTTPException(500, "REPL manager not initialized")

    logger.info(f"POST /api/v2/repl/session/start (client_id={client_id})")

    try:
        session = await repl_manager.get_or_create_session(client_id)
        return {
            "session_id": session.session_id,
            "status": "ready",
            "created_at": session.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to start REPL session: {e}")
        raise HTTPException(500, f"Failed to start REPL session: {str(e)}")


@app.delete("/api/v2/repl/session/{session_id}")
async def close_repl_session(session_id: str) -> Dict[str, Any]:
    """
    Close a REPL session.

    Args:
        session_id: Session identifier

    Returns:
        Success status

    Raises:
        HTTPException(404): Session not found
    """
    if repl_manager is None:
        raise HTTPException(500, "REPL manager not initialized")

    logger.info(f"DELETE /api/v2/repl/session/{session_id}")

    session = repl_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    await repl_manager.close_session(session_id)
    return {"success": True}


@app.websocket("/api/v2/repl/session/{session_id}/ws")
async def repl_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for REPL communication.

    Handles bidirectional communication with REPL session:
    - Receives commands from client
    - Streams stdout/stderr output to client
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for REPL session {session_id}")

    if repl_manager is None:
        await websocket.send_json({"type": "error", "message": "REPL manager not initialized"})
        await websocket.close()
        return

    session = repl_manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": f"Session {session_id} not found"})
        await websocket.close()
        return

    # Send buffered output history for reconnection.
    # Client passes ?offset=N (# of messages already displayed) so we skip those.
    try:
        offset = int(websocket.query_params.get("offset", 0))
    except (ValueError, TypeError):
        offset = 0
    for item in session.output_buffer[offset:]:
        await websocket.send_json({"type": "output", **item})

    # Subscribe to future output from the session's background reader tasks.
    # This avoids reading directly from process.stdout/stderr (which can only
    # be consumed by one reader at a time) and enables clean reconnections.
    output_queue = session.subscribe()

    async def forward_output():
        """Forward queued output items to the WebSocket."""
        try:
            while True:
                item = await output_queue.get()
                await websocket.send_json({"type": "output", **item})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error forwarding output for session {session_id}: {e}")

    async def handle_client_messages():
        """Handle incoming messages from client"""
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "execute":
                code = data.get("code", "")
                await repl_manager.execute_code(session_id, code)

            elif msg_type == "interrupt":
                await repl_manager.send_interrupt(session_id)
                await websocket.send_json({
                    "type": "output",
                    "stream": "stdout",
                    "data": "^C\n",
                })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    forward_task = asyncio.create_task(forward_output())
    try:
        await handle_client_messages()
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from REPL session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        forward_task.cancel()
        await asyncio.gather(forward_task, return_exceptions=True)
        session.unsubscribe(output_queue)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"WebSocket closed for REPL session {session_id}")
