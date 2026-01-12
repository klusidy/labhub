# Install pico SDK
# follow this getting started page:
# https://github.com/picotech/picosdk-python-wrappers

from __future__ import annotations
import asyncio, math, random, logging
from typing import Any, Dict, Optional, List, Literal, AsyncIterator, TYPE_CHECKING

import numpy as np
from collections import deque
from scipy.signal import get_window, detrend as sp_detrend

from ..base import Device, api_device, api_command, api_property, api_data, Frame
from ..data_source import DataSource

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

import ctypes
import os
import wave
from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc

import numpy as np
import matplotlib.pyplot as plt
import time

logger = logging.getLogger(__name__)
logger = logging.getLogger("labhub.device_manager.pico_technologies.ps5000a")

# Sentinel object to signal stream start/restart to subscribers
FIRST_FRAME = object()

RANGE_VALUES = {
    "10MV": 0.01,
    "20MV": 0.02,
    "50MV": 0.05,
    "100MV": 0.1,
    "200MV": 0.2,
    "500MV": 0.5,
    "1V": 1.0,
    "2V": 2.0,
    "5V": 5.0,
    "10V": 10.0,
    "20V": 20.0,
    "50V": 50.0,
    "MAX_RANGE": 50.0,
}


class PicoRawSource(DataSource):
    """Class that handles reading out time series data from Picoscope
    other data sources may subscribe to it, do its transformation and yield it to client
    so that all transformations are done on the same data"""

    def __init__(self, driver):
        self.driver = driver
        self.loop: asyncio.AbstractEventLoop | None = None
        self.interval = 0.1  # todo figure out how to update this mid-acquisition
        self._needs_restart = False  # Dirty flag for parameter changes
        super().__init__("pico raw source")

    async def stop(self):
        await super().stop()
        try:
            self.driver.status["stop"] = ps.ps5000aStop(self.driver.chandle)
        except Exception:
            pass

    async def start(self, force_restart=False):

        # S
        # tash loop to enable restarting when some param changes
        self._needs_restart = False # dont need restart at start, like ever
        self.loop = asyncio.get_running_loop()
        if self.running() and not force_restart:
            return

        # For restart, stop the poller task, dont lose subscribers and create a new one
        if force_restart:
            await self.stop()

        # Prepare block acquisition
        pre_trigger_samples = self.driver._pre_trigger_samples
        post_trigger_samples = self.driver._post_trigger_samples
        total_samples = pre_trigger_samples + post_trigger_samples
        buffer_len = total_samples

        self.driver.sampling_frequency = (
            self.driver._sampling_frequency
        )  # seting property with cached value will reset timebase internally # TODO - add restart when something important changes
        timebase = self.driver._timebase

        # prepare buffers for active channels
        channels_active = []
        for ch in ("A", "B", "C", "D"):
            if getattr(self.driver, f"channel_{ch}", {}).get("enable", 0):
                channels_active.append(ch)

        if not channels_active:
            return

        buffers_raw = {}
        for ch in channels_active:
            buffers_raw[ch] = np.zeros(buffer_len, dtype=np.int16)
            source = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{ch}"]

            self.driver.status[f"setDataBuffers{ch}"] = ps.ps5000aSetDataBuffers(
                self.driver.chandle,
                source,
                buffers_raw[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                None,  # min buffer not used
                buffer_len,
                0,  # segment index
                ps.PS5000A_RATIO_MODE["PS5000A_RATIO_MODE_NONE"],
            )

        # Prepare the poller task
        check = ctypes.c_int16(0)
        overflow = ctypes.c_int16()

        async def poller():
            while True:
                # Check if we have subscribers (DataSource lock)
                async with self._lock:
                    if len(self._subscribers) == 0:
                        break

                # Acquire Device lock for hardware access
                async with self.driver._lock:
                    # Check if parameters changed - restart if needed
                    if self._needs_restart:
                        #logger.debug(">>>>> I do need restart")
                        raise asyncio.CancelledError("Restart requested")

                    ready = ctypes.c_int16(0)
                    cmaxSamples = ctypes.c_int32(buffer_len)

                    # All hardware operations protected by Device lock
                    self.driver.status["runBlock"] = ps.ps5000aRunBlock(
                        self.driver.chandle,
                        pre_trigger_samples,
                        post_trigger_samples,
                        timebase,
                        None,
                        0,
                        None,
                        None,
                    )

                    while ready.value == check.value:
                        self.driver.status["isReady"] = ps.ps5000aIsReady(
                            self.driver.chandle, ctypes.byref(ready)
                        )
                        await asyncio.sleep(0.001)  # Yield event loop, keep lock

                    self.driver.status["getValues"] = ps.ps5000aGetValues(
                        self.driver.chandle,
                        0,
                        ctypes.byref(cmaxSamples),
                        0,
                        0,
                        0,
                        ctypes.byref(overflow),
                    )

                    # Construct frame while holding lock
                    frame = {}
                    for ch, buffer in buffers_raw.items():
                        frame[ch] = np.frombuffer(buffer, dtype=np.int16)

                # Fan-out outside Device lock (don't hold HW during distribution)
                await self._fan_out(frame)
                await asyncio.sleep(self.interval)

            self.driver.status["stop"] = ps.ps5000aStop(self.driver.chandle)

        # Signal stream start/restart to subscribers (triggers plot metadata refresh)
        await self._fan_out(FIRST_FRAME)

        self._needs_restart = False # do not restart at start of a task
        self._task = asyncio.create_task(poller(), name=f"PicoscopeRawStream")

        # def on_done(t: asyncio.Task):
        #     try:
        #         e = t.exception()
        #         if e and not isinstance(e, asyncio.CancelledError):
        #             logger.exception("Picoscope raw stream crashed")
        #     except asyncio.CancelledError:
        #         pass

        def on_done(t: asyncio.Task):
            try:
                e = t.exception()
                if e is not None:
                    if isinstance(e, asyncio.CancelledError):
                        logger.info("Task was cancelled.")
                    else:
                        logger.exception("Picoscope raw stream crashed")
            finally:
                # Check if a restart was requested, and start a new task
                if self._needs_restart:
                    logger.debug("Restarting task due to parameter change.")
                    asyncio.create_task(self.start(force_restart=True)) 

        self._task.add_done_callback(on_done)


@api_device()
class ps5000a(Device):
    """PicoScope 5000a series driver.
    This driver requires the PicoSDK to be installed."""

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        self.chandle = ctypes.c_int16()
        self.status = {}

        # TODO - UNIFY HOW PARAMS ARE STORED (CACHE OR _ATTR?)
        self.requested_resolution = options.get(
            "resolution", 12
        )  # TODO - make resolution into a selectable parameter
        if self.requested_resolution not in [8, 12, 14, 15, 16]:
            raise ValueError("resolution must be one of [8, 12, 14, 15, 16]")
        self.resolution = ps.PS5000A_DEVICE_RESOLUTION[
            f"PS5000A_DR_{self.requested_resolution}BIT"
        ]

        self._timebase = 10  # todo set default timebase in config.yaml
        self._max_samples = 134217472  # TODO  - this should be initialized!!!
        self._time_interval_ns = 32.0
        self._sampling_frequency = 1e9 / 32

        self._pre_trigger_samples = 0
        self._post_trigger_samples = 5000
        self._trigger = {}

        self._downsample_window = 10

        self._pico_raw_source = PicoRawSource(driver=self)

        super().__init__(dev_id, options, manager)

    # --- lifecycle -----------------------------------------------------------
    async def connect(self) -> None:
        """Connect to the device."""
        # TODO - fail gracefully if something goes wrong

        def sync_connect():
            self.started = ctypes.c_int16(0)  # <-- status*, not handle
            self.status["openunit"] = ps.ps5000aOpenUnitAsync(
                ctypes.byref(self.started), None, self.resolution
            )
            if self.status["openunit"] != 0 or self.started.value == 0:
                raise RuntimeError(
                    f"OpenUnitAsync failed/blocked: {self.status}, started={self.started.value}"
                )

            progress = ctypes.c_int16(0)
            complete = ctypes.c_int16(0)

            while True:
                self.status["openunit_progress"] = ps.ps5000aOpenUnitProgress(
                    ctypes.byref(self.chandle),
                    ctypes.byref(progress),
                    ctypes.byref(complete),
                )

                if complete.value == 1:
                    break
                time.sleep(0.1)

            if self.status["openunit_progress"] != 0:  # expect PICO_OK==0
                raise RuntimeError(f"OpenUnitProgress failed: {self.status}")

            try:
                assert_pico_ok(self.status["openunit"])
            except:  # PicoNotOkError:
                powerStatus = self.status["openunit"]
                if powerStatus == 286:
                    self.status["changePowerSource"] = ps.ps5000aChangePowerSource(
                        self.chandle, powerStatus
                    )
                elif powerStatus == 282:
                    self.status["changePowerSource"] = ps.ps5000aChangePowerSource(
                        self.chandle, powerStatus
                    )
                else:
                    raise

                assert_pico_ok(self.status["changePowerSource"])

            return True

        res = await self._on_device(
            sync_connect
        )  # TODO - keep track of single thread like kinesis?
        # TODO - sync_connect mechanism is in base, but what to do with the channel defaults?
        # TODO - NO CHANNEL DEFAULTS IN CONFIG.YAML!!!
        if not res:
            return False

        for channel_defaults in self.options.get("channels", []):
            if "id" not in channel_defaults:
                raise ValueError("channel config must include 'id' (A, B, C, or D)")
            _coupling = channel_defaults.get("coupling", "DC")
            _range = channel_defaults.get("range", "1V")
            _enable = channel_defaults.get("enable", True)
            await self.set_channel(channel_defaults["id"], _enable, _coupling, _range)
        return True

    async def disconnect(self) -> None:
        """Disconnect from the device."""

        def _disconnect():
            # Stop the scope
            self.status["stop"] = ps.ps5000aStop(self.chandle)
            assert_pico_ok(self.status["stop"])

            # Close unit Disconnect the scope
            self.status["close"] = ps.ps5000aCloseUnit(self.chandle)
            assert_pico_ok(self.status["close"])

        await self._on_device(_disconnect)

    def estimate_timebase(self, frequency_hz):
        """Convert frequency to a 'timebase'
        https://www.picotech.com/download/manuals/picoscope-5000-series-a-api-programmers-guide.pdf
        """

        sampling_interval_s = 1 / frequency_hz
        sampling_interval_ns = sampling_interval_s * 1e9

        if self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_8BIT"]:
            if sampling_interval_ns >= 8:
                timebase = int(125000000 * sampling_interval_s) + 2
            elif sampling_interval_ns >= 4:
                timebase = 2
            elif sampling_interval_ns >= 2:
                timebase = 1
            else:  # fastest possible
                timebase = 0

        elif self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_12BIT"]:
            if sampling_interval_ns >= 16:
                timebase = int(62500000 * sampling_interval_s) + 3
            elif sampling_interval_ns >= 8:
                timebase = 3
            elif sampling_interval_ns >= 4:
                timebase = 2
            else:
                timebase = 1

        elif (
            self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_14BIT"]
            or self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_15BIT"]
        ):
            if sampling_interval_ns >= 16:
                timebase = int(125000000 * sampling_interval_s) + 2
            else:
                timebase = 3

        elif self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_16BIT"]:
            if sampling_interval_ns >= 32:
                timebase = int(62500000 * sampling_interval_s) + 3
            else:
                timebase = 4
            pass
        else:
            raise ValueError("Unsupported resolution")

        return timebase

    @api_property(unit="Hz")
    def sampling_frequency(self) -> float:
        """Current sampling frequency in Hz."""

        return self._sampling_frequency

    @sampling_frequency.setter
    def sampling_frequency(self, value: float) -> None:
        timeIntervalns = ctypes.c_float()
        returnedMaxSamples = ctypes.c_int32()

        self._timebase = self.estimate_timebase(value)
        # check that timebase is achievable given actual device settings
        for timebase_candidate in range(self._timebase, self._timebase + 5):
            self.status["getTimebase2"] = ps.ps5000aGetTimebase2(
                self.chandle,
                timebase_candidate,
                1,
                ctypes.byref(timeIntervalns),
                ctypes.byref(returnedMaxSamples),
                0,
            )
            if self.status["getTimebase2"] == 0:
                break
        else:  # if not break
            raise RuntimeError(
                f"Could not set timebase for requested frequency {value}Hz"
            )
            print(f"Could not set timebase for requested frequency {value}Hz")
            return

        self._timebase = timebase_candidate
        self._max_samples = returnedMaxSamples.value
        self._time_interval_ns = timeIntervalns.value
        actual_frequency = 1e9 / timeIntervalns.value
        self._sampling_frequency = actual_frequency

        # Signal data source to restart with new parameters
        self._pico_raw_source._needs_restart = True

        return actual_frequency

    # read-only properties (slave of sampling_frequency)
    @api_property()
    def sampling_time_ns(self) -> float:
        return self._time_interval_ns

    @api_property()
    def max_data_samples(self) -> int:
        """Maximum number of samples that can be captured in one acquisition."""
        return self._max_samples

    @api_property(unit="s")
    def max_data_seconds(self) -> float:
        """Maximum number of samples that can be captured in one acquisition."""
        return self._max_samples * self._time_interval_ns * 1e-9

    @api_property()
    def pre_trigger_samples(self) -> int:
        """Number of pre-trigger samples in the current acquisition."""
        return self._pre_trigger_samples

    @pre_trigger_samples.setter
    def pre_trigger_samples(self, value: int) -> None:
        if not (0 <= value <= self._max_samples):
            raise ValueError(
                f"pre_trigger_samples must be between 0 and {self._max_samples}"
            )
        self._pre_trigger_samples = value
        # Signal data source to restart with new parameters
        self._pico_raw_source._needs_restart = True
        return value

    @api_property()
    def post_trigger_samples(self) -> int:
        """Number of post-trigger samples in the current acquisition."""
        return self._post_trigger_samples

    @post_trigger_samples.setter
    def post_trigger_samples(self, value: int) -> None:
        if not (0 <= value <= self._max_samples):
            raise ValueError(
                f"post_trigger_samples must be between 0 and {self._max_samples}"
            )
        self._post_trigger_samples = value
        # Signal data source to restart with new parameters
        self._pico_raw_source._needs_restart = True
        return value

    @api_property(unit="s")
    def post_trigger_samples_seconds(
        self,
    ) -> float:  # TODO link different units to the same property
        """Number of post-trigger samples in the current acquisition."""
        return self._post_trigger_samples * self._time_interval_ns * 1e-9

    @api_property()
    def pre_trigger_samples(self) -> int:
        """Number of pre-trigger samples in the current acquisition."""
        return self._pre_trigger_samples

    @pre_trigger_samples.setter
    def pre_trigger_samples(self, value: int) -> None:
        if not (0 <= value <= self._max_samples):
            raise ValueError(
                f"pre_trigger_samples must be between 0 and {self._max_samples}"
            )
        self._pre_trigger_samples = value
        # Signal data source to restart with new parameters
        self._pico_raw_source._needs_restart = True
        return value

    @api_property()
    def downsample_window(self) -> int:
        """Number of samples to average over in downsampled PSD"""
        return self._downsample_window

    @downsample_window.setter
    def downsample_window(self, value: int) -> None:
        self._downsample_window = value
        return value

    @api_command()
    async def set_channel(
        self,
        channel: Literal["A", "B", "C", "D"],
        enable: bool,
        coupling_type: Literal["AC", "DC"],
        range: Literal[
            "10MV",
            "20MV",
            "50MV",
            "100MV",
            "200MV",
            "500MV",
            "1V",
            "2V",
            "5V",
            "10V",
            "20V",
            "50V",
            "MAX_RANGES",
        ],
    ) -> dict:

        _channel = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]
        _enable = 1 if enable else 0
        _coupling_type = ps.PS5000A_COUPLING[f"PS5000A_{coupling_type}"]
        _range = ps.PS5000A_RANGE[f"PS5000A_{range}"]
        multiplier = (
            RANGE_VALUES[range] / 2**15
        )  # at least I think its always 16bits...

        self.status[f"setCh{channel}"] = ps.ps5000aSetChannel(
            self.chandle, _channel, _enable, _coupling_type, _range, 0
        )
        assert_pico_ok(self.status[f"setCh{channel}"])

        ret = {
            "status": self.status[f"setCh{channel}"],
            "channel": _channel,
            "enable": _enable,
            "coupling_type": _coupling_type,
            "range": _range,
            "multiplier": multiplier,
            "range_str": range,
            "coupling_type_str": coupling_type,
        }
        setattr(self, f"channel_{channel}", ret)

        # Signal data source to restart with new channel configuration
        self._pico_raw_source._needs_restart = True

        return ret

    # Add channels settings to state to support the display in the UI
    async def read_state(self) -> Dict[str, Any]:  # override
        state = await super().read_state()
        state["_channel_settings"] = {
            ch: getattr(self, f"channel_{ch}", {}) for ch in ("A", "B", "C", "D")
        }
        state["_trigger_settings"] = (
            self._trigger
        )  # dict of last values for set_simple_trigger
        return state

    async def _post_apply_properties(self, properties: dict) -> None:
        """Restore channel and trigger settings from profile."""
        # Restore channel settings if present in profile
        if "_channel_settings" in properties:
            channel_settings = properties["_channel_settings"]
            for ch, settings in channel_settings.items():
                if settings:  # Only restore if channel was configured
                    try:
                        await self.set_channel(
                            channel=ch,
                            enable=bool(settings.get("enable", 0)),
                            coupling_type=settings.get("coupling_type_str", "DC"),
                            range=settings.get("range_str", "1V"),
                        )
                    except Exception as e:
                        logger.warning(f"{self.id}: Failed to restore channel {ch} settings: {e}")

        # Restore trigger settings if present in profile
        if "_trigger_settings" in properties:
            trigger = properties["_trigger_settings"]
            if trigger:  # Only restore if trigger was configured
                try:
                    await self.set_simple_trigger(
                        enable=bool(trigger.get("enable", 0)),
                        source=trigger.get("source_str", "A"),
                        threshold_mV=trigger.get("threshold_mV", 0.0),
                        direction=trigger.get("direction_str", "RISING"),
                        delay=trigger.get("delay", 0),
                        auto_trigger_ms=trigger.get("auto_trigger_ms", 1000),
                    )
                except Exception as e:
                    logger.warning(f"{self.id}: Failed to restore trigger settings: {e}")

    @api_command()
    async def set_simple_trigger(
        self,
        enable: bool,
        source: Literal["A", "B", "C", "D"],
        threshold_mV: float,
        direction: Literal["RISING", "FALLING", "RISING_OR_FALLING"],
        delay: int = 0,
        auto_trigger_ms: int = 1000,
    ) -> dict:

        _enable = 1 if enable else 0
        _source = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{source}"]

        maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps5000aMaximumValue(
            self.chandle, ctypes.byref(maxADC)
        )

        _channel_range = getattr(self, f"channel_{source}", {}).get(
            "range", ps.PS5000A_RANGE["PS5000A_1V"]
        )
        _threshold = int(mV2adc(threshold_mV, _channel_range, maxADC))
        _direction = ps.PS5000A_THRESHOLD_DIRECTION[f"PS5000A_{direction}"]
        _delay = delay
        _auto_trigger_ms = auto_trigger_ms

        self.status["trigger"] = ps.ps5000aSetSimpleTrigger(
            self.chandle,
            _enable,
            _source,
            _threshold,
            _direction,
            _delay,
            _auto_trigger_ms,
        )
        assert_pico_ok(self.status["trigger"])

        ret = {
            "status": self.status["trigger"],
            "enable": _enable,
            "source": _source,
            "source_str": source,
            "threshold": _threshold,
            "threshold_mV": threshold_mV,
            "direction": _direction,
            "direction_str": direction,
            "delay": _delay,
            "auto_trigger_ms": _auto_trigger_ms,
        }

        self._trigger = ret

        # Signal data source to restart with new trigger configuration
        self._pico_raw_source._needs_restart = True

        return ret

    @api_command()
    async def acquire_to_file(
        self, folder: str, filename: str, acquisition_duration_s: Optional[float] = None
    ) -> dict:

        sampling_frequency_hz = self._sampling_frequency

        if acquisition_duration_s is None:
            acquisition_duration_s = (
                self._pre_trigger_samples + self._post_trigger_samples
            ) / float(sampling_frequency_hz)

        # apply (this should set _timebase/_time_interval_ns in your driver)
        acquisition_samples = min(
            self.max_data_samples,
            int(round(float(acquisition_duration_s) * sampling_frequency_hz)),
        )

        # ---- enabled channels & host buffers (int16) ----
        channels_active = [
            ch
            for ch in ("A", "B", "C", "D")
            if getattr(self, f"channel_{ch}", {}).get("enable", 0)
        ]
        if not channels_active:
            return {"ok": False, "error": "No channels enabled"}

        # allocate numpy buffers that the driver fills in-place
        raw = {
            ch: np.empty(acquisition_samples, dtype=np.int16) for ch in channels_active
        }

        # set buffers (singular API for no-aggregation)
        for ch in channels_active:
            src = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{ch}"]
            ptr = raw[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
            # ps5000aSetDataBuffer(handle, channel, bufferPtr, length, segmentIndex, ratioMode)
            self.status[f"setDataBuffer{ch}"] = ps.ps5000aSetDataBuffer(
                self.chandle,
                src,
                ptr,
                acquisition_samples,
                0,
                ps.PS5000A_RATIO_MODE["PS5000A_RATIO_MODE_NONE"],
            )

        # ---- run block acquisition ----
        loop = asyncio.get_running_loop()
        done_evt = asyncio.Event()

        # pre = 0, post = acquisition_samples
        time_indisposed_ms = None
        segment_index = 0

        self.status["runBlock"] = ps.ps5000aRunBlock(
            self.chandle,
            0,  # pre-trigger
            acquisition_samples,  # post-trigger
            self._timebase,  # computed from sampling_frequency
            None,
            0,
            None,
            None,
        )

        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        while ready.value == check.value:  # TODO - callback instead of polling
            self.status["isReady"] = ps.ps5000aIsReady(
                self.chandle, ctypes.byref(ready)
            )
            await asyncio.sleep(0.01)

        # wait for the device to finish acquisition
        # await done_evt.wait()

        # ---- pull the data out of the device into our numpy buffers ----
        start_index = 0
        c_no_of_samples = ctypes.c_int32(acquisition_samples)
        downsample_ratio = 1
        ratio_mode = ps.PS5000A_RATIO_MODE["PS5000A_RATIO_MODE_NONE"]
        overflow = ctypes.c_int16(0)

        # For ps5000a, GetValues is per device (not per channel). Since we already
        # set per-channel buffers with SetDataBuffer above, this single call fills all.
        self.status["getValues"] = ps.ps5000aGetValues(
            self.chandle,
            start_index,
            ctypes.byref(c_no_of_samples),
            downsample_ratio,
            ratio_mode,
            segment_index,
            ctypes.byref(overflow),
        )

        ns = int(c_no_of_samples.value)  # actual samples retrieved
        if ns <= 0:
            return {"ok": False, "error": "No samples returned"}

        # ---- write WAV (16-bit PCM, interleaved if multi-channel) ----
        os.makedirs(folder, exist_ok=True)
        if not filename.lower().endswith(".wav"):
            filename += ".wav"
        path = os.path.join(folder, filename)

        nch = len(channels_active)
        # stack to shape (ns, nch) and interleave
        data16 = np.stack([raw[ch][:ns] for ch in channels_active], axis=1)  # int16
        # Ensure little-endian bytes for WAV
        if data16.dtype.byteorder not in ("<", "="):
            data16 = data16.astype("<i2", copy=False)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(nch)
            wf.setsampwidth(2)  # int16
            wf.setframerate(int(round(sampling_frequency_hz)))
            wf.writeframes(data16.ravel(order="C").tobytes())

        # optional: surface overflow/clipping info
        clipped = bool(overflow.value)

        self._pico_raw_source._needs_restart = True
        return {
            "ok": True,
            "file": path,
            "duration_s": acquisition_duration_s,
            "channels": channels_active,
            "samples": ns,
            "fs_hz": sampling_frequency_hz,
            "clipped": clipped,
        }

    @api_data()
    async def time_stream(self) -> AsyncIterator[Frame]:
        """Simple time series stream. To add a new stream, copy-paste this method and modify the mapper function
        The mapper function should take time series np.array on input and produce a list (so that data can be send over to clients)
        """

        def mapper(x):
            return x.tolist()

        q = await self._pico_raw_source.subscribe()
        await self._pico_raw_source.start()  # ensure background poller is running

        try:
            while True:
                frame = await q.get()

                # Check for stream start/restart signal
                if frame is FIRST_FRAME:
                    # Yield plot metadata to inform subscribers of new x-axis
                    yield {
                        "type": "plot_metadata",
                        "plot": self.time_stream_plot(),
                    }
                else:
                    # Regular data frame
                    yield {ch: mapper(data) for ch, data in frame.items()}
        finally:
            await self._pico_raw_source.unsubscribe(q)

    @time_stream.plot()
    def time_stream_plot(self) -> Dict[str, Any]:
        """Time series plot"""

        pre_trigger_samples = self._pre_trigger_samples
        post_trigger_samples = self._post_trigger_samples
        total_samples = pre_trigger_samples + post_trigger_samples

        return {
            "title": "Time series plot",
            "x-label": "us",
            "y-label": "V",
            "x-values": (
                np.arange(total_samples) * self._time_interval_ns * 1e-3
            ).tolist(),
            "channel_settings": {
                ch: getattr(self, f"channel_{ch}", {}) for ch in ("A", "B", "C", "D")
            },
        }

    @api_data()
    async def psd_stream(self) -> AsyncIterator[Frame]:
        """Returns PSD of the time series"""

        def mapper(x):
            N = x.size
            dt = self.sampling_time_ns * 1e-9
            fs = 1 / dt

            fft = np.fft.rfft(x)
            Pxx = (np.abs(fft[1:]) ** 2) / (
                fs * N
            )  # normalize to density [unit^2 / Hz]
            return Pxx.tolist()

        q = await self._pico_raw_source.subscribe()
        await self._pico_raw_source.start()

        try:
            while True:
                frame = await q.get()

                # Check for stream start/restart signal
                if frame is FIRST_FRAME:
                    # Yield plot metadata to inform subscribers of new frequency axis
                    yield {
                        "type": "plot_metadata",
                        "plot": self.psd_stream_plot(),
                    }
                else:
                    # Regular data frame
                    yield {ch: mapper(data) for ch, data in frame.items()}
        finally:
            await self._pico_raw_source.unsubscribe(q)

    @psd_stream.plot()
    def psd_stream_plot(self) -> Dict[str, Any]:
        """PSD plot (function doc)"""

        pre_trigger_samples = self._pre_trigger_samples
        post_trigger_samples = self._post_trigger_samples
        total_samples = pre_trigger_samples + post_trigger_samples

        dt = (
            self.sampling_time_ns * 1e-9
        )  # created at runtime - self can be fixed in definition time
        fs = 1 / dt

        freqs = np.fft.rfftfreq(total_samples, d=dt)[1:]

        return {
            "title": "PSD",  # self.psd_stream_plot.__doc__,
            "x-label": "Frequency (Hz)",
            "y-label": "PSD [V^2 / Hz]",
            "x-values": freqs.tolist(),
        }

    @api_data()
    async def psd_stream_downsample(self) -> AsyncIterator[Frame]:
        """Returns PSD of the time series"""

        def downsample_average(data: np.ndarray, window_size: int) -> np.ndarray:
            n = data.size
            num_windows = n // window_size
            if num_windows == 0:
                return np.empty(0, dtype=data.dtype)
            return (
                data[: num_windows * window_size]
                .reshape(num_windows, window_size)
                .mean(axis=1)
            )

        def mapper(x):
            N = x.size
            dt = self.sampling_time_ns * 1e-9
            fs = 1 / dt

            fft = np.fft.rfft(x)
            Pxx = (np.abs(fft[1:]) ** 2) / (
                fs * N
            )  # normalize to density [unit^2 / Hz]

            # Apply frequency downsample averaging
            window_size = self._downsample_window
            if window_size > 1:
                Pxx = downsample_average(Pxx, window_size)

            return Pxx.tolist()

        q = await self._pico_raw_source.subscribe()
        await self._pico_raw_source.start()

        try:
            while True:
                frame = await q.get()

                # Check for stream start/restart signal
                if frame is FIRST_FRAME:
                    # Yield plot metadata to inform subscribers of new frequency axis
                    yield {
                        "type": "plot_metadata",
                        "plot": self.psd_stream_downsample_plot(),
                    }
                else:
                    # Regular data frame
                    yield {ch: mapper(data) for ch, data in frame.items()}
        finally:
            await self._pico_raw_source.unsubscribe(q)

    @psd_stream_downsample.plot()
    def psd_stream_downsample_plot(self) -> Dict[str, Any]:
        """PSD plot (function doc)"""

        pre_trigger_samples = self._pre_trigger_samples
        post_trigger_samples = self._post_trigger_samples
        total_samples = pre_trigger_samples + post_trigger_samples
        window_size = self._downsample_window

        dt = (
            self.sampling_time_ns * 1e-9
        )  # created at runtime - self can be fixed in definition time
        fs = 1 / dt

        freqs = np.fft.rfftfreq(total_samples, d=dt)[1:]

        # Apply downsample averaging for X axis
        if window_size > 1:
            n = freqs.size
            num_windows = n // window_size
            freqs = (
                freqs[: num_windows * window_size]
                .reshape(num_windows, window_size)
                .mean(axis=1)
            )

        return {
            "title": "PSD (downsampled)",  # self.psd_stream_downsample_plot.__doc__,
            "x-label": "Frequency (Hz)",
            "y-label": "PSD [V^2 / Hz]",
            "x-values": freqs.tolist(),
        }
