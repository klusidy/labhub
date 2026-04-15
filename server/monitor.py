"""
Profile Monitor - Automatic state persistence to profile file.

Periodically saves device states to profile file, preserving user-defined policies.
"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Iterable, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .device_manager import DeviceManager

from .events import EventBus
from .loader import (
    HubProfile,
    DeviceProfile,
    PropertyProfile,
    save_profile,
    load_profile,
)

logger = logging.getLogger(__name__)


class ProfileMonitor:
    """
    Periodically saves device states to profile file.

    Architecture:
    - Saves full state every N seconds
    - Preserves user-defined policies from existing profile
    - Default policy: "write" for writable properties, "read" for read-only
    - TODO: Add event-based change detection when granular events available
    """

    def __init__(
        self,
        event_bus: EventBus,
        manager: DeviceManager,
        profile_path: None | str | Path = None,
        save_interval: float = 10.0,
    ):
        """
        Initialize profile monitor.

        Args:
            event_bus: Event bus (reserved for future event-based monitoring)
            manager: DeviceManager instance
            profile_path: Path to profile file
            save_interval: Save interval in seconds (default 10s)
        """
        self.event_bus = event_bus
        self.manager = manager

        self.profile_path = (
            Path(profile_path) if profile_path else None
        )  # TODO make this more similar to device manager - it also does not need path to cfg straightway
        self.save_interval = save_interval

        # Policy storage: {dev_id: {prop_name: policy}}
        self._policies: Dict[str, Dict[str, str]] = {}

        self._running = False
        self._save_task: Optional[asyncio.Task] = None

        logger.debug(
            f"Profile monitor initialized (path={self.profile_path}, interval={save_interval}s)"
        )

    async def start(self, initial_delay: float = 2.0) -> None:
        """
        Start periodic profile saves.

        Loads existing profile to preserve policies, waits for initial polling
        to populate device CACHE, then starts save loop.

        Args:
            initial_delay: Seconds to wait before starting saves (default 2.0).
                          Allows polling to populate CACHE, preventing unnecessary
                          writes when loading profiles on startup.
        """
        if self._running:
            logger.warning("Profile monitor already running")
            return

        self._running = True

        # Load existing profile to preserve policies
        self._load_policies()

        # Wait for initial polling to populate CACHE TODO - SHOULD BE ELSEWHERE? ORDER OF OPERATIONS DURING STARTUP REVIEW!!
        # This prevents unnecessary property writes on startup when CACHE is empty
        # if initial_delay > 0:
        #     logger.debug(
        #         f"Waiting {initial_delay}s for initial device polling to populate CACHE..."
        #     )
        #     await asyncio.sleep(initial_delay)
        #     logger.debug("Initial delay complete, CACHE should be populated")

        # Start periodic save loop
        self._save_task = asyncio.create_task(self._periodic_save_loop())

        logger.info(
            f"Profile monitor started (saving to {self.profile_path} every {self.save_interval}s)"
        )

    async def stop(self) -> None:
        """
        Stop monitoring and perform final save.
        """
        if not self._running:
            logger.debug("Profile monitor not running, nothing to stop")
            return

        logger.info("Stopping profile monitor...")
        self._running = False

        # Cancel save task
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass

        # Final save
        logger.info("Performing final profile save before shutdown")
        await self._save_profile()

        logger.info("Profile monitor stopped")

    def _load_policies(self) -> None:
        """
        Load policies from existing profile file.

        Preserves user-defined policies. If profile doesn't exist, starts fresh.
        """
        try:
            profile = load_profile(self.profile_path)
            self._policies.clear()

            for dev_profile in profile.devices:
                dev_policies = {}
                for prop_name, prop_profile in dev_profile.properties.items():
                    dev_policies[prop_name] = prop_profile.policy
                self._policies[dev_profile.id] = dev_policies

            logger.info(
                f"Loaded policies from existing profile ({len(profile.devices)} devices)"
            )

        except FileNotFoundError:
            logger.info("No existing profile found, will create new one")
            self._policies.clear()
        except Exception as e:
            logger.warning(f"Failed to load profile policies: {e}")
            self._policies.clear()

    async def _periodic_save_loop(self) -> None:
        """
        Background task: save profile every N seconds.
        """
        logger.debug("Periodic save loop started")
        try:
            while self._running:
                await asyncio.sleep(self.save_interval)
                await self._save_profile()

        except asyncio.CancelledError:
            logger.debug("Periodic save loop cancelled")
        except Exception as e:
            logger.error(f"Periodic save loop error: {e}", exc_info=True)

    async def _save_profile(self) -> None:
        """
        Save current device states to profile file.

        Uses manager.list_devices() for state, preserves existing policies.
        """
        try:
            device_profiles = []

            # Iterate every device and child device in the tree.
            # Each gets its own profile entry keyed by its full path.
            for path, dev in self._iter_device_tree():
                if path not in self._policies:
                    self._policies[path] = {}

                properties = {}
                for prop_name in dev._api_properties:
                    value = dev.get_cached(prop_name)

                    if prop_name in self._policies[path]:
                        policy = self._policies[path][prop_name]
                    else:
                        prop_meta = dev._api_properties.get(prop_name, {})
                        policy = "read" if prop_meta.get("read_only") else "write"
                        self._policies[path][prop_name] = policy

                    properties[prop_name] = PropertyProfile(value=value, policy=policy)

                device_profiles.append(DeviceProfile(id=path, properties=properties))

            # Write to file atomically
            profile = HubProfile(devices=device_profiles)
            save_profile(profile, self.profile_path)
            logger.info(
                f"Profile saved successfully ({len(device_profiles)} device(s), {self.profile_path})"
            )

        except Exception as e:
            logger.error(
                f"Failed to save profile to {self.profile_path}: {e}", exc_info=True
            )

    async def load_profile(
        self, new_path: str | Path, switch_path: bool = True
    ) -> None:
        """
        Load profile from file and apply write-policy properties.

        Loads properties and policies from a profile file, applies properties with
        "write" policy to devices, and optionally switches to using this profile
        for future saves.

        Args:
            new_path: Profile file path to load from
            switch_path: If True, use this path for future saves (default: True)

        Raises:
            FileNotFoundError: Profile file not found

        Notes:
            - Loads new_path BEFORE changing self.profile_path (avoids race condition)
            - Applies only "write" policy properties
            - Value comparison done in apply_properties (checks CACHE)
            - Does not delete old profile file
            - Performs immediate save to new location if switch_path=True
        """
        new_path = Path(new_path)
        old_path = self.profile_path

        logger.info(
            f"Loading profile from {new_path}"
            + (f" (will switch from {old_path})" if switch_path else "")
        )

        # Load new profile (don't change self.profile_path yet - race condition!)
        try:
            new_profile = load_profile(new_path)
            new_policies = {}

            # Process each device (or child device) in profile
            for dev_profile in new_profile.devices:
                dev_path = dev_profile.id
                dev = self._resolve_device(dev_path)

                if not dev:
                    logger.warning(
                        f"Device '{dev_path}' in profile not found in manager, skipping"
                    )
                    continue

                # Extract policies and filter write-policy properties
                dev_policies = {}
                write_properties = {}

                for prop_name, prop_profile in dev_profile.properties.items():
                    dev_policies[prop_name] = prop_profile.policy
                    if prop_profile.policy == "write":
                        write_properties[prop_name] = prop_profile.value

                new_policies[dev_path] = dev_policies

                # Apply write-policy properties directly to the resolved device
                if write_properties:
                    try:
                        await dev.apply_properties(write_properties)
                        logger.info(
                            f"Applied {len(write_properties)} write-policy properties to '{dev_path}'"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to apply properties to '{dev_path}': {e}",
                            exc_info=True,
                        )

            # Update policies AFTER successful load and apply
            self._policies = new_policies

            # Switch to new profile path if requested
            if switch_path:
                self.profile_path = new_path
                logger.info(f"Profile path switched: {old_path} -> {new_path}")

                # Immediate save to new location
                await self._save_profile()
            else:
                logger.info(
                    f"Profile loaded (path not switched, still using {old_path})"
                )

        except FileNotFoundError:
            logger.error(f"Profile file not found: {new_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to load profile from {new_path}: {e}", exc_info=True)
            raise

    async def set_policy(self, dev_id: str, prop_name: str, policy: str) -> None:
        """
        Change policy for a specific device property.

        Args:
            dev_id: Device identifier
            prop_name: Property name
            policy: New policy ("read" or "write")

        Raises:
            ValueError: Invalid policy or read-only property with "write" policy

        Notes:
            - Policy is persisted in next save
            - Cannot set "write" policy on read-only property
        """
        if policy not in ("read", "write"):
            raise ValueError(f"Invalid policy: {policy}. Must be 'read' or 'write'")

        # Validate: cannot set "write" on read-only property
        dev = self._resolve_device(dev_id)
        if dev:
            prop_meta = dev._api_properties.get(prop_name, {})
            if prop_meta.get("read_only") and policy == "write":
                raise ValueError(
                    f"Cannot set 'write' policy on read-only property '{prop_name}'"
                )

        # Update policy
        if dev_id not in self._policies:
            self._policies[dev_id] = {}

        self._policies[dev_id][prop_name] = policy
        logger.info(f"Policy changed: {dev_id}.{prop_name} -> {policy}")

        # Force immediate save to persist change
        await self._save_profile()

    async def apply_profile_to_device(self, dev_id: str) -> None:
        """
        Apply profile (write-policy properties) to a device and all its children.

        Used when a device is connected mid-session to restore its
        last-known property values from the profile.

        Args:
            dev_id: Root device identifier
        """
        if not self.manager.devices.get(dev_id):
            logger.warning(f"Cannot apply profile: device '{dev_id}' not in manager")
            return

        # Load current profile from file for fresh values
        try:
            profile = load_profile(self.profile_path)
        except Exception as e:
            logger.warning(f"Failed to load profile for device '{dev_id}': {e}")
            return

        # Apply all profile entries that belong to this root device
        # (both the root entry "dev_id" and child entries "dev_id/ch_a" etc.)
        applied = 0
        for dev_profile in profile.devices:
            path = dev_profile.id
            if path != dev_id and not path.startswith(dev_id + "/"):
                continue

            dev = self._resolve_device(path)
            if not dev:
                continue

            write_properties = {
                k: v.value
                for k, v in dev_profile.properties.items()
                if v.policy == "write"
            }

            if write_properties:
                try:
                    await dev.apply_properties(write_properties)
                    applied += len(write_properties)
                except Exception as e:
                    logger.error(
                        f"Failed to apply profile properties to '{path}': {e}",
                        exc_info=True,
                    )

            # Restore policies
            self._policies[path] = {k: v.policy for k, v in dev_profile.properties.items()}

        if applied:
            logger.info(f"Applied {applied} write-policy properties to '{dev_id}' subtree")

    # ------------------------------------------------------------------
    # Device-tree helpers
    # ------------------------------------------------------------------

    def _resolve_device(self, path: str):
        """Return the Device at *path* (e.g. ``'ps5000a/ch_a'``), or None."""
        parts = path.split("/")
        dev = self.manager.devices.get(parts[0])
        for part in parts[1:]:
            if dev is None:
                return None
            dev = dev.children.get(part)
        return dev

    def _iter_device_tree(self) -> Iterable[Tuple[str, object]]:
        """Yield ``(path, Device)`` for every device and child, depth-first."""
        def _recurse(path: str, dev):
            yield path, dev
            for child_id, child in dev.children.items():
                yield from _recurse(f"{path}/{child_id}", child)

        for dev_id, dev in self.manager.devices.items():
            yield from _recurse(dev_id, dev)

    async def force_save(self) -> None:
        """
        Force immediate profile save.

        Useful for manual save operations or admin endpoints.
        """
        logger.debug("Force save requested")
        await self._save_profile()
