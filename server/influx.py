"""
InfluxDB 2.x integration for LabHub telemetry.

Provides non-blocking writes to InfluxDB with batching, retry logic,
and graceful degradation when InfluxDB is unavailable.

Measurements:
- device_state: Periodic snapshots of all device properties
- property_set: Event log of property changes (via API)
- command_exec: Event log of command executions
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .loader import InfluxCfg
    from .device_manager import DeviceManager

logger = logging.getLogger("labhub.influx")


class InfluxWriter:
    """
    Async InfluxDB writer with batching and error resilience.

    Architecture:
    - Internal asyncio.Queue for buffering points
    - Background task flushes batches to InfluxDB
    - Non-blocking writes - callers never wait for InfluxDB
    - Graceful degradation - logs errors but doesn't fail device operations

    Thread Safety:
    - All public methods are async and use the event loop's queue
    - No explicit locks needed - asyncio.Queue is coroutine-safe
    - Background flush task runs in same event loop as callers
    """

    def __init__(self, config: InfluxCfg):
        self.config = config

        # State
        self._running = False
        self._client = None
        self._write_api = None
        self._queue: Optional[asyncio.Queue] = None
        self._flush_task: Optional[asyncio.Task] = None

        # Metrics
        self._points_written = 0
        self._points_dropped = 0
        self._write_errors = 0
        self._last_error: Optional[str] = None
        self._last_successful_write: Optional[float] = None

        logger.debug(f"InfluxWriter initialized (enabled={config.enabled})")

    async def start(self) -> None:
        """
        Start the writer and connect to InfluxDB.

        Called during server lifespan startup. Failures here are logged
        but don't prevent server from starting.
        """
        if not self.config.enabled:
            logger.info("InfluxDB integration disabled")
            return

        if self._running:
            logger.warning("InfluxWriter already running")
            return

        try:
            # Import here to make influxdb-client optional
            from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

            self._client = InfluxDBClientAsync(
                url=self.config.url,
                token=self.config.token,
                org=self.config.org,
            )

            # Test connection
            health = await self._client.ping()
            if not health:
                logger.warning("InfluxDB ping failed - server may be starting up")
            else:
                logger.info(f"Connected to InfluxDB at {self.config.url}")

            self._write_api = self._client.write_api()
            self._queue = asyncio.Queue(maxsize=10000)
            self._running = True

            # Start background flush task
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("InfluxWriter started")

        except ImportError:
            logger.error(
                "influxdb-client-python not installed. "
                "Install with: pip install influxdb-client[async]"
            )
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self._last_error = str(e)

    async def stop(self) -> None:
        """
        Stop the writer and flush remaining points.

        Called during server shutdown. Attempts to write buffered
        points before closing connection.
        """
        if not self._running:
            return

        logger.info("Stopping InfluxWriter...")
        self._running = False

        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush of remaining points
        await self._flush_batch(final=True)

        # Close client
        if self._client:
            await self._client.close()
            self._client = None

        logger.info(
            f"InfluxWriter stopped. Stats: {self._points_written} written, "
            f"{self._points_dropped} dropped, {self._write_errors} errors"
        )

    # ---- Public write methods ----

    async def write_device_state(
        self,
        device_id: str,
        driver: str,
        state: Dict[str, Any],
        connected: bool = True,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write periodic device state snapshot.

        Measurement: device_state
        Tags: device_id, driver
        Fields: All property values (flattened) + _connected
        """
        if not self._running:
            return

        fields = self._flatten_state(state)
        fields["_connected"] = connected

        point = {
            "measurement": "device_state",
            "tags": {"device_id": device_id, "driver": driver},
            "fields": fields,
            "time": timestamp or datetime.now(timezone.utc),
        }
        await self._enqueue(point)

    async def write_property_set(
        self,
        device_id: str,
        driver: str,
        property_name: str,
        old_value: Any,
        new_value: Any,
        source: str = "api",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write property change event.

        Measurement: property_set
        Tags: device_id, driver, source
        Fields: {property_name}_old, {property_name}_new (typed per property)
        """
        if not self._running:
            return

        # Use property name as field prefix so each property has its own typed fields
        point = {
            "measurement": "property_set",
            "tags": {
                "device_id": device_id,
                "driver": driver,
                "property": property_name,
                "source": source,
            },
            "fields": {
                f"{property_name}_old": self._serialize_value(old_value),
                f"{property_name}_new": self._serialize_value(new_value),
            },
            "time": timestamp or datetime.now(timezone.utc),
        }
        await self._enqueue(point)

    async def write_command_exec(
        self,
        device_id: str,
        driver: str,
        command_name: str,
        args: Optional[Dict[str, Any]],
        result: Any,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Write command execution event.

        Measurement: command_exec
        Tags: device_id, driver, command, success
        Fields: args (json), result (json), duration_ms, error
        """
        if not self._running:
            return

        fields: Dict[str, Any] = {
            "args": json.dumps(args) if args else "{}",
            "result": json.dumps(result) if result is not None else "null",
            "duration_ms": duration_ms,
            "success": success,
        }
        if error:
            fields["error"] = error

        point = {
            "measurement": "command_exec",
            "tags": {
                "device_id": device_id,
                "driver": driver,
                "command": command_name,
            },
            "fields": fields,
            "time": timestamp or datetime.now(timezone.utc),
        }
        await self._enqueue(point)

    # ---- Internal methods ----

    async def _enqueue(self, point: Dict) -> None:
        """Add point to write queue (non-blocking)."""
        if self._queue is None:
            return

        try:
            self._queue.put_nowait(point)
        except asyncio.QueueFull:
            # Drop oldest point to make room
            try:
                _ = self._queue.get_nowait()
                self._points_dropped += 1
                self._queue.put_nowait(point)
            except asyncio.QueueEmpty:
                pass

    async def _flush_loop(self) -> None:
        """Background task: periodically flush batched points."""
        flush_interval = self.config.flush_interval_ms / 1000

        try:
            while self._running:
                await asyncio.sleep(flush_interval)
                await self._flush_batch()
        except asyncio.CancelledError:
            logger.debug("Flush loop cancelled")

    async def _flush_batch(self, final: bool = False) -> None:
        """Flush queued points to InfluxDB."""
        if not self._write_api or self._queue is None:
            return

        # Collect batch
        batch = []
        batch_limit = self.config.batch_size if not final else self._queue.qsize()

        while len(batch) < batch_limit:
            try:
                point = self._queue.get_nowait()
                batch.append(point)
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        # Convert to line protocol format
        from influxdb_client import Point

        points = []
        for p in batch:
            pt = Point(p["measurement"])
            for tag_key, tag_val in p.get("tags", {}).items():
                pt = pt.tag(tag_key, tag_val)
            for field_key, field_val in p.get("fields", {}).items():
                pt = pt.field(field_key, field_val)
            if p.get("time"):
                pt = pt.time(p["time"])
            points.append(pt)

        # Write with retry
        retry_delay = self.config.flush_interval_ms / 1000
        for attempt in range(self.config.max_retries):
            try:
                await self._write_api.write(
                    bucket=self.config.bucket,
                    record=points,
                )
                self._points_written += len(batch)
                self._last_successful_write = time.monotonic()

                if attempt > 0:
                    logger.info(f"InfluxDB write succeeded after {attempt} retries")
                return

            except Exception as e:
                self._write_errors += 1
                self._last_error = str(e)

                if attempt < self.config.max_retries - 1:
                    logger.warning(
                        f"InfluxDB write failed (attempt {attempt + 1}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(
                        f"InfluxDB write failed after {self.config.max_retries} attempts, "
                        f"dropping {len(batch)} points: {e}"
                    )
                    self._points_dropped += len(batch)

    def _flatten_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten nested state dict for InfluxDB fields."""
        flat: Dict[str, Any] = {}
        for key, value in state.items():
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    flat[f"{key}_{subkey}"] = self._serialize_value(subval)
            else:
                flat[key] = self._serialize_value(value)
        return flat

    def _serialize_value(self, value: Any) -> Any:
        """Convert value to InfluxDB-compatible type.

        Note: All numeric values are converted to float to avoid type conflicts.
        InfluxDB enforces strict field typing - once a field is written as float,
        all subsequent writes must also be float.
        """
        if value is None:
            return "null"
        if isinstance(value, bool):
            # Must check bool before int, since bool is subclass of int
            return value
        if isinstance(value, (int, float)):
            # Always use float for numeric values to ensure type consistency
            return float(value)
        if isinstance(value, str):
            # Try to convert numeric-looking strings to float to avoid type conflicts
            # (clients sometimes send numbers as strings in JSON)
            try:
                return float(value)
            except ValueError:
                return value
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value)

    def _to_string(self, value: Any) -> str:
        """Convert any value to string for fields that may have mixed types."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (list, dict)):
            return json.dumps(value)
        return str(value)

    # ---- Status/metrics ----

    def get_status(self) -> Dict[str, Any]:
        """Get writer status for admin endpoints."""
        return {
            "enabled": self.config.enabled,
            "running": self._running,
            "url": self.config.url,
            "bucket": self.config.bucket,
            "org": self.config.org,
            "queue_size": self._queue.qsize() if self._queue else 0,
            "points_written": self._points_written,
            "points_dropped": self._points_dropped,
            "write_errors": self._write_errors,
            "last_error": self._last_error,
            "last_successful_write": self._last_successful_write,
        }


class InfluxStateMonitor:
    """
    Periodically writes device state snapshots to InfluxDB.

    Similar architecture to ProfileMonitor but writes to InfluxDB
    instead of YAML file.
    """

    def __init__(
        self,
        writer: InfluxWriter,
        manager: DeviceManager,
        interval: float = 10.0,
    ):
        self.writer = writer
        self.manager = manager
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start periodic state snapshots."""
        if self._running or not self.writer.config.enabled:
            return

        self._running = True
        self._task = asyncio.create_task(self._snapshot_loop())
        logger.info(f"InfluxStateMonitor started (interval={self.interval}s)")

    async def stop(self) -> None:
        """Stop periodic snapshots."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("InfluxStateMonitor stopped")

    async def _snapshot_loop(self) -> None:
        """Background task: write state snapshots periodically."""
        try:
            while self._running:
                await asyncio.sleep(self.interval)
                await self._write_snapshots()
        except asyncio.CancelledError:
            pass

    async def _write_snapshots(self) -> None:
        """Write current state of all devices."""
        for dev_id, dev in self.manager.devices.items():
            try:
                state = await dev.read_state()
                await self.writer.write_device_state(
                    device_id=dev_id,
                    driver=getattr(dev, "_api_driver", "unknown"),
                    state=state,
                    connected=dev.is_connected,
                )
            except Exception as e:
                logger.warning(f"Failed to snapshot '{dev_id}': {e}")
