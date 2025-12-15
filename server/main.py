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
from .utils import init_logging
from .loader import get_config_path, load_config, get_profile_path
from .monitor import ProfileMonitor
from . import admin

# Initialize logging - reads LABHUB_LOG_LEVEL and LABHUB_LOG_FILE from environment
init_logging(log_file=os.environ.get("LABHUB_LOG_FILE"))
logger = logging.getLogger("labhub.main")  # Explicit name for proper hierarchy


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    global lock, profile_monitor

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
    await manager.start_polling()
    logger.info("Device polling started")

    # 4. Initialize profile monitor (for live state backup)
    await asyncio.sleep(2.0)  # Allow polling to populate initial states

    profile_path = get_profile_path()
    await profile_monitor.load_profile(profile_path)
    await profile_monitor.start()

    logger.info(f"Profile monitor started (path={profile_path})")

    # Set profile_monitor for admin endpoints
    admin.profile_monitor = profile_monitor

    logger.info("LabHub server ready")

    yield  # Server is running

    # --- Shutdown ---
    logger.info("LabHub server shutting down...")

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
manager = DeviceManager(event_bus)
profile_monitor: ProfileMonitor | None = ProfileMonitor(
    event_bus, manager, save_interval=10.0
)  # Profile auto-save monitor
lock: FileLock | None = None  # Single-instance lock per CONFIG PATH

# Include admin router and set manager dependency
admin.manager = manager
app.include_router(admin.router)

# ---- Static files / GUI ----
WEB_DIST = Path(__file__).parent.parent / "gui" / "basic" / "dist"
if WEB_DIST.exists():
    app.mount(
        "/ui", staticfiles.StaticFiles(directory=str(WEB_DIST), html=True), name="ui"
    )

# todo - gui for picoscope should not be specified separately - not extensible
GUI_PICOSCOPE_DIST = (
    Path(__file__).parent.parent.parent
    / "gui"
    / "devices"
    / "picoscope"
    / "dist"
    / "spa"
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


@app.get("/api/v2/devices/{dev_id}", response_model=DeviceInfo)
async def get_device(dev_id: str):
    """
    Get current state for a specific device.

    Args:
        dev_id: Device identifier (e.g., "piezo1", "scope_main")

    Returns:
        DeviceInfo: Device information including:
            - id: Device identifier
            - kind: Device type
            - status: Connection status
            - state: Current property values

    Raises:
        HTTPException(404): Device not found in configuration
        HTTPException(500): Error reading device state
    """
    logger.debug(f"GET /api/v2/devices/{dev_id} - fetching device state")

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.get_device_state(dev_id)
    except Exception as e:
        logger.error(f"Failed to get state for device '{dev_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Error reading device state: {str(e)}")


@app.patch("/api/v2/devices/{dev_id}", response_model=DeviceInfo)
async def patch_device(dev_id: str, req: PatchRequest):
    """
    Update device properties.

    Args:
        dev_id: Device identifier
        req: PatchRequest containing properties to update
            - properties: Dict[str, Any] - Property name-value pairs

    Returns:
        DeviceInfo: Updated device state after applying properties

    Raises:
        HTTPException(404): Device not found
        HTTPException(400): Invalid property name or value
        HTTPException(500): Error applying properties to device

    Notes:
        - Only provided properties are updated; others remain unchanged
        - Property changes are published to event bus for real-time updates
        - Read-only properties cannot be modified
    """
    logger.debug(
        f"PATCH /api/v2/devices/{dev_id} - updating properties: {list(req.properties.keys())}"
    )

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.apply_properties(dev_id, req.properties)
    except ValueError as e:
        # Invalid property name or value
        logger.warning(f"Invalid property update for '{dev_id}': {e}")
        raise HTTPException(400, f"Invalid property: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to apply properties to '{dev_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Error applying properties: {str(e)}")


@app.get("/api/v2/devices/{dev_id}/spec", response_model=DeviceSpec)
async def get_device_spec(dev_id: str):
    """
    Get device specification (capabilities and metadata).

    Returns the device's complete API specification including available
    properties, commands, and data sources. Used by clients to understand
    device capabilities and build dynamic UIs.

    Args:
        dev_id: Device identifier

    Returns:
        DeviceSpec: Device specification containing:
            - id: Device identifier
            - kind: Device type
            - doc: Device documentation/description
            - properties: List of property definitions (name, type, range, etc.)
            - commands: List of available commands with arguments
            - data_sources: List of data sources for streaming/plotting

    Raises:
        HTTPException(404): Device not found
        HTTPException(500): Error reading device specification

    Notes:
        - Spec is derived from driver class metadata (PROPERTIES, COMMANDS, DATA_SOURCES)
        - Includes type information, constraints, and documentation
        - Used for API discovery and client-side validation
    """
    logger.debug(f"GET /api/v2/devices/{dev_id}/spec - fetching device specification")

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.get_device_spec(dev_id)
    except Exception as e:
        logger.error(
            f"Failed to get specification for device '{dev_id}': {e}", exc_info=True
        )
        raise HTTPException(500, f"Error reading device specification: {str(e)}")


@app.post("/api/v2/devices/{dev_id}/commands")
async def run_command(dev_id: str, req: CommandRequest):
    """
    Execute a device command.

    Commands are device-specific actions selected from the driver methods
    by a @api_method() decorator. Examples: "home" for motion devices,
    "trigger" for scopes, etc.

    Args:
        dev_id: Device identifier
        req: CommandRequest containing:
            - name: Command name
            - args: Dict of command arguments

    Returns:
        Command-specific result (varies by command)

    Raises:
        HTTPException(404): Device not found
        HTTPException(400): Invalid command name or arguments
        HTTPException(500): Command execution failed

    Notes:
        - Available commands listed in device spec (/api/v2/devices/{dev_id}/spec)
        - Device state is published to event bus after command completes
        - Some commands may return file paths or structured data
    """
    logger.debug(
        f"POST /api/v2/devices/{dev_id}/commands - running command: {req.name}"
    )

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        res = await manager.run_command(dev_id, req.name, req.args)
        logger.debug(f"Command '{req.name}' completed successfully for '{dev_id}'")
        return res
    except ValueError as e:
        logger.warning(f"Invalid command for '{dev_id}': {e}")
        raise HTTPException(400, f"Invalid command: {str(e)}")
    except Exception as e:
        logger.error(f"Command '{req.name}' failed for '{dev_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Command execution failed: {str(e)}")


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


@app.get("/api/v2/devices/{dev_id}/data")
async def get_data_catalog(dev_id: str) -> Dict[str, Any]:
    """
    Get catalog of available data sources for a device.

    Data sources provide streaming data, plots, or single-shot acquisitions.
    Examples: oscilloscope traces, sensor readings, camera frames.

    Args:
        dev_id: Device identifier

    Returns:
        Dict with:
            - device: Device ID
            - sources: List of data source names

    Raises:
        HTTPException(404): Device not found
        HTTPException(500): Error reading data catalog

    Notes:
        - Each source can be queried for plot specs (/plot) or frames (/frame)
        - Sources can be streamed via WebSocket (/api/v2/streams/{dev_id}/{source})
    """
    logger.debug(f"GET /api/v2/devices/{dev_id}/data - fetching data catalog")

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.get_data_catalog(dev_id)
    except Exception as e:
        logger.error(f"Failed to get data catalog for '{dev_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Error reading data catalog: {str(e)}")


@app.get("/api/v2/devices/{dev_id}/data/{source}/plot")
async def get_plot_spec(dev_id: str, source: str) -> Dict[str, Any]:
    """
    Get plot specification for a data source.

    Plot specs describe how to visualize data from this source, including
    axis labels, units, data ranges, and trace configurations.

    Args:
        dev_id: Device identifier
        source: Data source name

    Returns:
        Dict with plot configuration:
            - x-label, y-label: Axis labels
            - x-unit, y-unit: Physical units
            - x-values: Optional fixed x-axis values
            - Additional source-specific fields

    Raises:
        HTTPException(404): Device or source not found
        HTTPException(500): Error reading plot spec

    Notes:
        - Not all sources provide plot specs (check device spec)
        - Spec format varies by source type (line plot, 2D image, etc.)
    """
    logger.debug(
        f"GET /api/v2/devices/{dev_id}/data/{source}/plot - fetching plot spec"
    )

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.get_plot_spec(dev_id, source)
    except KeyError as e:
        logger.warning(f"Data source '{source}' not found on '{dev_id}'")
        raise HTTPException(404, f"Unknown data source '{source}': {str(e)}")
    except Exception as e:
        logger.error(
            f"Failed to get plot spec for '{dev_id}/{source}': {e}", exc_info=True
        )
        raise HTTPException(500, f"Error reading plot spec: {str(e)}")


@app.get("/api/v2/devices/{dev_id}/data/{source}/frame")
async def get_one_frame(dev_id: str, source: str) -> Dict[str, Any]:
    """
    Get a single data frame from a source.

    Performs a one-shot read of the data source. For continuous streaming,
    use the WebSocket endpoint instead.

    Args:
        dev_id: Device identifier
        source: Data source name

    Returns:
        Dict with frame data (format varies by source):
            - Common fields: timestamp, data
            - Source-specific fields vary

    Raises:
        HTTPException(404): Device or source not found
        HTTPException(500): Error acquiring frame

    Notes:
        - May trigger hardware acquisition (e.g., oscilloscope capture)
        - Use WebSocket streaming for high-rate continuous data
        - Frame format defined by data source implementation
    """
    logger.debug(f"GET /api/v2/devices/{dev_id}/data/{source}/frame - fetching frame")

    if dev_id not in manager.devices:
        logger.warning(f"Device not found: {dev_id}")
        raise HTTPException(404, f"Unknown device '{dev_id}'")

    try:
        return await manager.get_one_frame(dev_id, source)
    except KeyError as e:
        logger.warning(f"Data source '{source}' not found on '{dev_id}'")
        raise HTTPException(404, f"Unknown data source '{source}': {str(e)}")
    except Exception as e:
        logger.error(
            f"Failed to get frame from '{dev_id}/{source}': {e}", exc_info=True
        )
        raise HTTPException(500, f"Error acquiring frame: {str(e)}")


@app.websocket("/api/v2/streams/{dev_id}/{source}")
async def ws_stream(ws: WebSocket, dev_id: str, source: str):
    """
    WebSocket endpoint for streaming data from a device source.

    Provides high-rate continuous data streaming from data sources like
    oscilloscope traces, sensor readings, or camera frames.

    Path Parameters:
        dev_id: Device identifier
        source: Data source name (from device's DATA_SOURCES)

    Query Parameters:
        rate: Optional acquisition/streaming rate in Hz (default: 12.5 Hz)

    Message Format:
        JSON frames with source-specific structure (e.g., {"data": [...], "timestamp": ...})

    Notes:
        - Automatically starts data source acquisition on connect
        - Queue size limited to 64 frames (older frames dropped if not consumed)
        - Connection closed with code 4404 if device/source not found
        - Unsubscribes and stops streaming on disconnect
    """
    await ws.accept()

    qps = dict(ws.query_params)
    prod_hz = float(qps.get("rate", 12.5))
    prod_interval = (1.0 / prod_hz) if prod_hz > 0 else 0.08

    logger.debug(
        f"WS /api/v2/streams/{dev_id}/{source} - client connected (rate={prod_hz}Hz)"
    )

    # Check device exists
    if dev_id not in manager.devices:
        logger.warning(f"WS stream: device not found: {dev_id}")
        await ws.close(code=4404)
        return

    # Subscribe to data source
    try:
        q = await manager.subscribe_stream(dev_id, source, maxsize=64)
    except KeyError as e:
        logger.warning(f"WS stream: data source '{source}' not found on '{dev_id}'")
        await ws.close(code=4404)
        return
    except Exception as e:
        logger.error(
            f"WS stream: failed to subscribe to '{dev_id}/{source}': {e}",
            exc_info=True,
        )
        await ws.close(code=1011)
        return

    # Start data acquisition
    try:
        await manager.start_stream(dev_id, source, interval=prod_interval)
        logger.debug(f"WS stream: started acquisition for '{dev_id}/{source}'")
    except Exception as e:
        logger.error(
            f"WS stream: failed to start '{dev_id}/{source}': {e}", exc_info=True
        )
        await ws.close(code=1011)
        return

    # Stream frames to client
    try:
        frame_count = 0
        while True:
            frame = await q.get()
            await ws.send_json(frame)
            frame_count += 1

    except WebSocketDisconnect:
        logger.debug(
            f"WS stream: client disconnected from '{dev_id}/{source}' ({frame_count} frames sent)"
        )
    except Exception as e:
        logger.error(
            f"WS stream: error streaming '{dev_id}/{source}': {e}", exc_info=True
        )
    finally:
        # Clean up subscription
        try:
            dev = manager.devices.get(dev_id)
            if dev:
                await dev.get_datasource(source).unsubscribe(q)
                logger.debug(f"WS stream: unsubscribed from '{dev_id}/{source}'")
        except Exception as e:
            logger.warning(f"WS stream: cleanup failed for '{dev_id}/{source}': {e}")


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
