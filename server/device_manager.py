"""
Device Manager - Central coordinator for device lifecycle and operations.

Manages device initialization, polling, state tracking, and API operations.
"""

from __future__ import annotations
import asyncio
from typing import Dict, List, Type, Any
from concurrent.futures import ThreadPoolExecutor

from .schemas import DeviceInfo, DeviceSpec
from .events import EventBus
from .drivers.base import Device
from . import drivers
import logging

logger = logging.getLogger("labhub.device_manager")


class DeviceManager:
    """
    Central coordinator for device lifecycle and operations.

    Responsibilities:
    - Device initialization and cleanup
    - Periodic state polling and event broadcasting
    - API operation routing (get state, apply properties, run commands)
    - Data source management (catalogs, frames, streaming)

    Architecture:
    - Single instance per server process
    - Thread pool executor for blocking device operations
    - Async polling tasks for each device
    - Event bus integration for real-time state updates
    """

    def __init__(self, event_bus: EventBus, max_workers: int = 8):
        """
        Initialize device manager.

        Args:
            event_bus: Event bus for publishing device state changes
            max_workers: Thread pool size for blocking device operations
        """
        self.event_bus = event_bus
        self.devices: Dict[str, drivers.Device] = {}
        self._poll_tasks: Dict[str, asyncio.Task] = {}
        self._stop_evt = asyncio.Event()

        # Shared thread pool executor for all devices
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="device_worker"
        )
        logger.debug(f"Initialized device manager with {max_workers} worker threads")

    async def initialize_devices(self, cfg) -> None:
        """
        Initialize all devices from config.

        Loads config.yaml, creates devices in parallel, and handles errors gracefully.
        """

        logger.info(f"Initializing {len(cfg.devices)} device(s)...")

        # Create all devices in parallel
        tasks = []
        for d in cfg.devices:
            tasks.append(self.add_device(d.id, d.driver, d.options))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log results
        successes = sum(1 for r in results if r is None)
        failures = sum(1 for r in results if isinstance(r, Exception))

        logger.info(
            f"Device initialization complete: {successes} succeeded, {failures} failed"
        )

        if failures > 0:
            logger.warning("Some devices failed to initialize - check logs for details")

    async def add_device(self, dev_id: str, driver: str, options: dict) -> None:
        """
        Add a device to the manager.

        Creates device instance, connects to hardware, and registers with manager.
        Does NOT apply default property values - defaults should be loaded from
        profile in main.py after initialization.

        Args:
            dev_id: Unique device identifier
            driver: Driver name (e.g., "sim_piezo", "kinesis")
            options: Driver-specific configuration options

        Raises:
            RuntimeError: Unknown driver or driver not available on platform
            Exception: Device connection or initialization failed

        Notes:
            - Device connection handled by driver's .create() method
            - Failures are logged but not re-raised (allows partial initialization)
            - Device passed the manager's executor for blocking operations
        """
        try:
            cls = drivers.get(driver)
        except KeyError as ke:
            cls = None
            logger.error(
                f"Driver class not found in module: {driver}: {ke}", exc_info=True
            )
        except ValueError as ve:
            cls = None
            logger.error(f"Error loading driver '{driver}': {ve}", exc_info=True)
        except ImportError as ie:
            cls = None
            logger.error(
                f"Failed to import driver module for '{driver}': \n" f"{ie}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to import driver module for '{driver}': \n" f"{ie}"
            ) from ie

        if cls is None:
            logger.error(f"Unknown driver '{driver}' or not available on this platform")
            raise RuntimeError(
                f"Unknown driver '{driver}' or not available on this platform"
            )

        logger.info(f"  - Adding device '{dev_id}' with driver '{driver}'")
        logger.debug(f"Device options: {options}")

        try:
            # Create device instance and connect to hardware
            # Pass manager reference for executor access
            # Note: options already contains "driver" field from load_config()
            dev: drivers.Device = await cls.create(dev_id, options, manager=self)
            self.devices[dev_id] = dev
            logger.info(
                f"\033[32m  - Device '{dev_id}' added successfully\033[0m"
            )  # TODO BETTER COLOR MANAGEMENT
        except Exception as e:
            logger.error(
                f"Failed to add device '{dev_id}' (driver={driver}): {e}",
                exc_info=True,
            )
            raise

    async def remove_device(self, dev_id: str) -> None:
        """
        Remove a device from the manager.

        Disconnects device and removes from registry. Used for device reload
        and cleanup operations.

        Args:
            dev_id: Device identifier to remove

        Notes:
            - Silently succeeds if device not found
            - Disconnect errors are logged but not raised
            - Does not stop polling (call stop_polling_device first)
        """
        dev = self.devices.pop(dev_id, None)
        if dev:
            logger.debug(f"Removing device '{dev_id}'")
            try:
                await dev.disconnect()
                logger.debug(f"Device '{dev_id}' disconnected successfully")
            except Exception as e:
                logger.warning(f"Error disconnecting device '{dev_id}': {e}")
        else:
            logger.debug(f"Device '{dev_id}' not found, nothing to remove")

    async def remove_all(self) -> None:
        """
        Remove all devices from the manager.

        Disconnects all devices and clears registry. Used for server shutdown
        and full reload operations.

        Notes:
            - Disconnect errors are logged but not raised
            - Does not stop polling (call stop_polling first)
        """
        logger.debug(f"Removing all devices ({len(self.devices)} total)")
        for dev_id, dev in list(self.devices.items()):
            try:
                await dev.disconnect()
                logger.debug(f"Device '{dev_id}' disconnected")
            except Exception as e:
                logger.warning(f"Error disconnecting device '{dev_id}': {e}")
        self.devices.clear()
        logger.debug("All devices removed")

    async def start_polling_device(
        self,
        dev_id: str,
    ) -> None:
        """
        Start periodic state polling for a device.

        Creates async task that polls all device properties at the device's
        configured polling interval and broadcasts state to event bus.

        Args:
            dev_id: Device identifier

        Notes:
            - Polling interval is device-specific (dev.polling_interval)
            - Broadcasts full state every poll cycle
            - TODO: Optimize to send full state infrequently + immediate updates
                    after property changes to reduce event bus traffic
            - Task automatically stops on CancelledError
        """
        if dev_id not in self.devices:
            logger.warning(f"Cannot start polling: device '{dev_id}' not found")
            return

        async def polling_task(dev_id: str, dev: Device) -> None:
            """Inner polling loop for a single device."""
            keys = list(getattr(dev, "_api_properties", {}).keys())
            logger.debug(
                f"Polling task started for '{dev_id}' ({len(keys)} properties, interval={dev.polling_interval}ms)"
            )

            try:
                while not self._stop_evt.is_set():
                    # Poll all properties to update cache
                    for k in keys:
                        _ = await dev.poll_property(k)

                    # Read cached state and broadcast
                    st = await dev.read_state()
                    await self.event_bus.publish(
                        {"type": "device.state", "id": dev_id, "state": st}
                    )

                    # Wait for next poll cycle
                    await asyncio.sleep(dev.polling_interval / 1000)

            except asyncio.CancelledError:
                logger.debug(f"Polling task cancelled for '{dev_id}'")
            except Exception as e:
                logger.error(f"Polling task error for '{dev_id}': {e}", exc_info=True)

        self._poll_tasks[dev_id] = asyncio.create_task(
            polling_task(dev_id, self.devices[dev_id])
        )
        logger.debug(f"Started polling for device '{dev_id}'")

    async def start_polling(self) -> None:
        """
        Start polling for all registered devices.

        Notes:
            - Creates one async task per device
            - Each device uses its own polling interval
        """
        logger.info(f"Starting polling for {len(self.devices)} device(s)")
        for dev_id, dev in self.devices.items():
            await self.start_polling_device(dev_id)
        logger.info("Polling started for all devices")

    async def stop_polling_device(self, dev_id: str) -> None:
        """
        Stop polling for a single device.

        Args:
            dev_id: Device identifier

        Notes:
            - Silently succeeds if device not being polled
            - Cancels async polling task
        """
        if dev_id not in self._poll_tasks:
            logger.debug(f"No polling task for '{dev_id}' to stop")
            return

        task = self._poll_tasks.pop(dev_id)
        if task:
            task.cancel()
            logger.debug(f"Stopped polling for device '{dev_id}'")

    async def stop_polling(self) -> None:
        """
        Stop polling for all devices.

        Cancels all polling tasks and resets stop event. Called during
        server shutdown or full device reload.

        Notes:
            - Waits for all tasks to complete
            - Errors during task cancellation are ignored
            - Resets stop event to allow restart
        """
        logger.info(f"Stopping polling for {len(self._poll_tasks)} device(s)")
        self._stop_evt.set()

        for dev_id, t in self._poll_tasks.items():
            t.cancel()

        await asyncio.gather(*self._poll_tasks.values(), return_exceptions=True)
        self._poll_tasks.clear()
        self._stop_evt = asyncio.Event()  # Allow restart
        logger.info("Polling stopped for all devices")

    # ======= API Helper Methods =======

    async def list_devices(self) -> List[DeviceInfo]:
        """
        List all registered devices with their current state.

        Returns:
            List of DeviceInfo objects containing id, kind, status, and state

        Notes:
            - Reads fresh state from each device
            - Includes disconnected devices with cached state
            - Returns empty list if no devices registered
        """
        logger.debug(f"Listing {len(self.devices)} device(s)")
        out: List[DeviceInfo] = []

        for dev_id, dev in self.devices.items():
            try:
                st = await dev.read_state()
                out.append(
                    DeviceInfo(
                        id=dev_id,
                        driver=dev._api_driver,
                        status=("connected" if dev.is_connected else "disconnected"),
                        state=st,
                    )
                )
            except Exception as e:
                logger.error(f"Error reading state for device '{dev_id}': {e}")
                # Include device in list with error indicator
                out.append(
                    DeviceInfo(
                        id=dev_id,
                        driver=dev._api_driver,
                        status="error",
                        state={"error": str(e)},
                    )
                )

        return out

    async def get_device_state(self, dev_id: str) -> DeviceInfo:
        """
        Get current state for a specific device.

        Args:
            dev_id: Device identifier

        Returns:
            DeviceInfo with current state

        Raises:
            KeyError: Device not found (should be caught by endpoint)
            Exception: Error reading device state
        """
        logger.debug(f"Getting state for device '{dev_id}'")
        dev = self.devices[dev_id]  # Raises KeyError if not found
        st = await dev.read_state()

        return DeviceInfo(
            id=dev_id,
            driver=dev._api_driver,
            status=("connected" if dev.is_connected else "disconnected"),
            state=st,
        )

    async def apply_properties(self, dev_id: str, properties: dict) -> DeviceInfo:
        """
        Apply property updates to a device.

        Updates device properties and broadcasts new state to event bus.

        Args:
            dev_id: Device identifier
            properties: Dict of property name-value pairs to update

        Returns:
            DeviceInfo with updated state

        Raises:
            KeyError: Device not found
            ValueError: Invalid property name or value (driver-specific)
            Exception: Error applying properties

        Notes:
            - Only specified properties are updated
            - Updated state immediately published to event bus
            - Property changes may trigger hardware operations
        """
        logger.debug(f"Applying {len(properties)} propert(ies) to '{dev_id}'")
        dev = self.devices[dev_id]

        st = await dev.apply_properties(properties)

        # Broadcast updated state
        await self.event_bus.publish(
            {"type": "device.state", "id": dev_id, "state": st}
        )

        return DeviceInfo(
            id=dev_id,
            driver=dev._api_driver,
            status=("connected" if dev.is_connected else "disconnected"),
            state=st,
        )

    async def run_command(self, dev_id: str, name: str, args: dict):
        """
        Execute a device command.

        Runs device-specific command and broadcasts updated state.

        Args:
            dev_id: Device identifier
            name: Command name (from device's @api_command)
            args: Command arguments dict

        Returns:
            Command-specific result (varies by command)

        Raises:
            KeyError: Device not found
            RuntimeError: Device doesn't support commands
            ValueError: Invalid command name or arguments
            Exception: Command execution failed

        Notes:
            - Command availability defined in driver's COMMANDS metadata
            - State update broadcast after command completes
            - Some commands return file paths or structured data
        """
        logger.debug(f"Running command '{name}' on device '{dev_id}' with args: {args}")
        dev = self.devices[dev_id]

        if not hasattr(dev, "run_command"):
            logger.error(f"Device '{dev_id}' does not support commands")
            raise RuntimeError("Commands not supported")

        res = await dev.run_command(name, args)
        logger.debug(f"Command '{name}' completed for '{dev_id}'")

        # Broadcast updated state so clients see changes
        st = await dev.read_state()
        await self.event_bus.publish(
            {"type": "device.state", "id": dev_id, "state": st}
        )

        return res

    # ======= Data Source Methods =======

    async def get_data_catalog(self, dev_id: str) -> Dict[str, Any]:
        """
        Get catalog of available data sources for a device.

        Args:
            dev_id: Device identifier

        Returns:
            Dict with 'device' and 'sources' keys

        Raises:
            KeyError: Device not found

        Notes:
            - Data sources provide streaming/plotting capabilities
            - Source list defined in driver's DATA_SOURCES metadata
        """
        logger.debug(f"Getting data catalog for '{dev_id}'")
        dev = self.devices[dev_id]
        return {"device": dev_id, "sources": dev.list_data_sources()}

    async def get_plot_spec(self, dev_id: str, source: str) -> Dict[str, Any]:
        """
        Get plot specification for a data source.

        Args:
            dev_id: Device identifier
            source: Data source name

        Returns:
            Dict with plot metadata (labels, units, etc.)

        Raises:
            KeyError: Device or source not found

        Notes:
            - Returns empty dict if source doesn't provide plot spec
            - Used by clients to configure visualization
        """
        logger.debug(f"Getting plot spec for '{dev_id}/{source}'")
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return ds.plot()

    async def get_one_frame(self, dev_id: str, source: str) -> Dict[str, Any]:
        """
        Get a single data frame from a source.

        Args:
            dev_id: Device identifier
            source: Data source name

        Returns:
            Dict with frame data (format varies by source)

        Raises:
            KeyError: Device or source not found
            Exception: Frame acquisition failed

        Notes:
            - May trigger hardware acquisition
            - For continuous data, use streaming instead
        """
        logger.debug(f"Getting one frame from '{dev_id}/{source}'")
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return await ds.once()

    async def subscribe_stream(self, dev_id: str, source: str, *, maxsize: int = 4):
        """
        Subscribe to data stream from a source.

        Args:
            dev_id: Device identifier
            source: Data source name
            maxsize: Queue size (older frames dropped when full)

        Returns:
            asyncio.Queue for receiving frames

        Raises:
            KeyError: Device or source not found

        Notes:
            - Must call start_stream to begin frame production
            - Client responsible for consuming frames to avoid queue overflow
        """
        logger.debug(f"Subscribing to stream '{dev_id}/{source}' (maxsize={maxsize})")
        dev = self.devices[dev_id]
        ds = dev.get_datasource(source)
        return await ds.subscribe(maxsize=maxsize)

    async def start_stream(self, dev_id: str, source: str, *, interval: float | None):
        """
        Start data acquisition for a stream.

        Args:
            dev_id: Device identifier
            source: Data source name
            interval: Acquisition interval in seconds

        Raises:
            KeyError: Device or source not found
            Exception: Failed to start acquisition

        Notes:
            - Begins producing frames to subscribed queues
            - Multiple subscribers can receive same frames
        """
        logger.debug(f"Starting stream '{dev_id}/{source}' (interval={interval}s)")
        dev = self.devices[dev_id]
        await dev.get_datasource(source).start(interval=interval)

    async def stop_stream(self, dev_id: str, source: str):
        """
        Stop data acquisition for a stream.

        Args:
            dev_id: Device identifier
            source: Data source name

        Raises:
            KeyError: Device or source not found

        Notes:
            - Stops frame production
            - Subscribed queues remain valid but receive no new frames
        """
        logger.debug(f"Stopping stream '{dev_id}/{source}'")
        dev = self.devices[dev_id]
        await dev.get_datasource(source).stop()

    async def get_device_spec(self, dev_id: str) -> DeviceSpec:
        """
        Build device specification from driver metadata.

        Wrapper that delegates to device's build_spec() method.

        Args:
            dev_id: Device identifier

        Returns:
            DeviceSpec with properties, commands, and data sources

        Raises:
            KeyError: Device not found
        """
        logger.debug(f"Building device spec for '{dev_id}'")
        dev = self.devices[dev_id]
        return dev.build_spec(dev_id)

    async def shutdown(self) -> None:
        """
        Cleanup manager resources.

        Shuts down thread pool executor. Called during server shutdown.

        Notes:
            - Should be called after stop_polling() and remove_all()
            - Waits for running tasks to complete
        """
        logger.info("Shutting down device manager")
        self.executor.shutdown(wait=True)
        logger.info("Device manager shutdown complete")

    # ======= Orphaned Profile Functions (TODO: Remove or refactor) =======

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
                await self.event_bus.publish(
                    {"type": "device.state", "id": dev_id, "state": state}
                )

            except Exception as e:
                logger.error(
                    f"Failed to apply properties to {dev_id}: {e}", exc_info=True
                )
                results[dev_id] = f"error: {str(e)}"

        return results

    async def apply_properties_from_dict(
        self, properties: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Apply properties from dict (for API endpoint).

        Args:
            properties: {dev_id: {prop_name: value | "$READOUT", ...}, ...}
                       Can include "default" key for fallback

        Returns:
            Dict[dev_id] = "success" | "skipped" | "error: <message>"
        """
        from .properties_loader import (
            resolve_properties_for_device,
            PropertyResolutionError,
        )

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
                await self.event_bus.publish(
                    {"type": "device.state", "id": dev_id, "state": state}
                )

            except PropertyResolutionError as e:
                logger.error(f"Property resolution failed for {dev_id}: {e}")
                results[dev_id] = f"error: {str(e)}"
            except Exception as e:
                logger.error(
                    f"Failed to apply properties to {dev_id}: {e}", exc_info=True
                )
                results[dev_id] = f"error: {str(e)}"

        return results
