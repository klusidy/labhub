# Install pico SDK
# follow this getting started page:
# https://github.com/picotech/picosdk-python-wrappers

from __future__ import annotations
import asyncio, math, random
from typing import Any, Dict, Optional, List, Literal, AsyncIterator
import numpy as np
from collections import deque
from scipy.signal import get_window, detrend as sp_detrend

from .._base import Device, api_device, api_command, api_property, api_data, Frame
from .._data_source import DataSource


import ctypes
from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc

import numpy as np
import matplotlib.pyplot as plt
import time

class PicoRawSource(DataSource):
    def __init__(self, driver):
        self.driver = driver
        self.loop: asyncio.AbstractEventLoop | None = None
        super().__init__("pico raw source")
    
    async def stop(self):
        await super().stop()
        try:
            self.driver.status["stop"] = ps.ps5000aStop(self.driver.chandle)
        except Exception:
            pass #TODO HANDLE STOP EXCEPTION

    async def start(self, force_restart=False):
        # setup picoscope stuff
        self.loop = asyncio.get_running_loop()   # <── store it here
        if self.running() and not force_restart:
            return # 
        
        if force_restart:
            await self.stop() # stop but keep the queue intact
        
        ################ setup picoscope stuff #####################
        
        post_trigger_samples = self.driver._cache.get("post_trigger_samples", 5000)
        buffer_len = 2**15 # 32768  #post_trigger_samples 
        sample_interval = self.driver.sampling_time_ns
        sample_units_key = "PS5000A_NS"
        downsample_ratio = 1
        frame_len = post_trigger_samples

        channels_active = []
        for ch in ("A", "B", "C", "D"):
            if self.driver._cache.get(f"channel_{ch}", {}).get("enable", 0):
                channels_active.append(ch)

        if not channels_active: # nothing enabled # raise?
            return
        
        buffers_raw = {}
        for ch in channels_active:
            buffers_raw[ch] = np.zeros(buffer_len, dtype=np.int16)
            source = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{ch}"]

            self.driver.status[f"setDataBuffers{ch}"] = ps.ps5000aSetDataBuffers(self.driver.chandle,
                                                                source,
                                                                buffers_raw[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                                                                None,  # min buffer not used
                                                                buffer_len,
                                                                0,  # segment index
                                                                ps.PS5000A_RATIO_MODE["PS5000A_RATIO_MODE_NONE"],
                                                            )

        c_sample_interval = ctypes.c_int32(int(sample_interval))
        sample_units = ps.PS5000A_TIME_UNITS[sample_units_key]

        max_pre_trigger_samples, auto_stop_on, total_samples = 0,0,0

        self.driver.status["runStreaming"] = ps.ps5000aRunStreaming(self.driver.chandle,
                                                                ctypes.byref(c_sample_interval),
                                                                sample_units,
                                                                max_pre_trigger_samples,
                                                                total_samples,
                                                                auto_stop_on,
                                                                int(downsample_ratio),
                                                                ps.PS5000A_RATIO_MODE["PS5000A_RATIO_MODE_NONE"],
                                                                buffer_len,
                                                            )
        
        self.driver._time_interval_ns = c_sample_interval.value # already in ns
        self.driver._sampling_frequency = 1e9/self.driver._time_interval_ns
        #self.driver._sample
        #actual_sample_interval_ns = actual_sample_interval * 1000

        print("Capturing at sample interval %s ns" % self.driver._time_interval_ns)

        # variables accessed by _callback
        frame_buffer = {ch: np.empty(frame_len, dtype=np.int16) for ch in channels_active}
        frames_ready = deque(maxlen=5)
        was_called_back = False
        write_idx = 0


        ################ add the callback ##########################
        def _callback(handle, number_of_samples, start_index, overflow, trigger_at, triggered, auto_stop, param):
            nonlocal was_called_back, write_idx
            was_called_back = True
            if number_of_samples <= 0:
                return
            
            remaining = frame_len - write_idx
            take = min(number_of_samples, remaining)
            print(f" in callback {number_of_samples}, {start_index}")

            if take > 0:
                for ch in channels_active:
                    end = start_index + take
                    if end <= buffer_len:    
                        frame_buffer[ch][write_idx:write_idx+take] = buffers_raw[ch][start_index:start_index+take]
                    else:
                        frame_buffer[ch][write_idx:write_idx+take] = np.concatenate((buffers_raw[ch][start_index:],
                                                                                     buffers_raw[ch][:take - (buffer_len-start_index)]
                                                                                    ))
                write_idx += take
                if write_idx >= frame_len:
                    #frame = {c: mapper(frame_buffer[c]) for c in channels_active}
                    frame = {c: frame_buffer[c].copy() for c in channels_active} # dict channel: np.array
                    frames_ready.append(frame) # skip frames_ready and put it directly into all queues?
                    write_idx = 0
        
        func_ptr_callback = ps.StreamingReadyType(_callback)

        ############## create poller task for continuous readout ##########

        async def poller():
            should_run = True
            while should_run:
                was_called_back = False
                self.driver.status["getStreamingLatestValues"] = ps.ps5000aGetStreamingLatestValues(self.driver.chandle, 
                                                                                          func_ptr_callback, 
                                                                                          None)
                while frames_ready:
                    await self._fan_out(frames_ready.popleft())

                async with self._lock:
                    if (len(self._subscribers) == 0):
                        should_run = False
                        break
                # sleep only if not was_called_back?? TODO
                # or sleep every time to allow context switch?
                await asyncio.sleep(0.001) # minimal time to allow context switch? (can it be too long? should I just yield or something?)
            
            self.driver.status["stop"] = ps.ps5000aStop(self.driver.chandle)

        self._task = asyncio.create_task(poller(), name=f"PicoscopeRawStream")

        def on_done(t: asyncio.Task):
            try:
                e = t.exception()
                if e and not isinstance(e, asyncio.CancelledError):
                    print(f"Picoscope raw stream crashed \n {e}")
            except asyncio.CancelledError:
                pass

        self._task.add_done_callback(on_done)
            
        

    async def once(self):
        # TODO - what to do here?
        # when doing Once, I start the actual generator (which starts this data source) and only when it reads out single frame, it finishes
        # so probably dont implement once() at all here
        # should keep it empty, because I dont have self.generator, so calling once() of parent0 DataSource class would fail
        pass
    



    # overwrite runner with stuff with callback and so on
    pass

@api_device("ps5000a")
class PicoScope5000a(Device):
    """PicoScope 5000a series driver.
    This driver requires the PicoSDK to be installed."""

    def __init__(self, dev_id: str, options: Dict[str, Any]):
        self.chandle = ctypes.c_int16()
        self.status = {}

        self.requested_resolution = options.get("resolution", 12)
        if self.requested_resolution not in [8, 12, 14, 15, 16]:
            raise ValueError("resolution must be one of [8, 12, 14, 15, 16]")
        self.resolution = ps.PS5000A_DEVICE_RESOLUTION[f"PS5000A_DR_{self.requested_resolution}BIT"]

        self._cache = {"pre_trigger_samples": 0,
                       "post_trigger_samples": 5000,} 
        self._timebase = 10 # todo seT default timebase in config.yaml
        self._max_samples = 0
        self._time_interval_ns = 32.0
        self._sampling_frequency = 1e9/32

        self._pico_raw_source = PicoRawSource(driver=self)

        super().__init__(dev_id, options)
        
    
    # --- lifecycle -----------------------------------------------------------
    async def connect(self) -> None: # TODO - fail gracefully if something goes wrong while connecting one of the devices
        """Connect to the device."""

        def _connect():
            self.started  = ctypes.c_int16(0)   # <-- status*, not handle
            self.status["openunit"] = ps.ps5000aOpenUnitAsync(ctypes.byref(self.started), None, self.resolution) #TODO - async opening may not be finished!!
            if self.status["openunit"] != 0 or self.started.value == 0:
                raise RuntimeError(f"OpenUnitAsync failed/blocked: {self.status}, started={self.started.value}")


            progress = ctypes.c_int16(0)
            complete = ctypes.c_int16(0)

            while True:
                self.status["openunit_progress"] = ps.ps5000aOpenUnitProgress(
                    ctypes.byref(self.chandle), ctypes.byref(progress), ctypes.byref(complete)
                )

                print("::: pico connect progress = {}% ... {}".format(progress.value, self.status))

                if complete.value == 1:
                    break
                time.sleep(0.01)
            
            if self.status["openunit_progress"] != 0:  # expect PICO_OK==0
                raise RuntimeError(f"OpenUnitProgress failed: {self.status}")


            print(f"::: pico connect status = {self.status}")
            try:
                assert_pico_ok(self.status["openunit"])
            except: # PicoNotOkError:

                powerStatus = self.status["openunit"]

                if powerStatus == 286:
                    self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, powerStatus)
                elif powerStatus == 282:
                    self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, powerStatus)
                else:
                    raise

                assert_pico_ok(self.status["changePowerSource"])
            
            return True

        await self._on_device(_connect) # TODO - keep track of single thread like kinesis?

        for channel_defaults in self.options.get("channels", []):
            if "id" not in channel_defaults:
                raise ValueError("channel config must include 'id' (A, B, C, or D)")
            _coupling = channel_defaults.get("coupling", "DC")
            _range = channel_defaults.get("range", "1V")
            _enable = channel_defaults.get("enable", True)
            await self.set_channel(channel_defaults["id"], _enable, _coupling, _range)

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        def _disconnect():

            # Stop the scope
            # handle = chandle
            self.status["stop"] = ps.ps5000aStop(self.chandle)
            assert_pico_ok(self.status["stop"])

            # Close unit Disconnect the scope
            # handle = chandle
            self.status["close"]=ps.ps5000aCloseUnit(self.chandle)
            assert_pico_ok(self.status["close"])
            pass 

        await self._on_device(_disconnect)

    
    def estimate_timebase(self, frequency_hz):
        """Convert frequency to a 'timebase'
        https://www.picotech.com/download/manuals/picoscope-5000-series-a-api-programmers-guide.pdf"""
        
        sampling_interval_s = 1 / frequency_hz
        sampling_interval_ns = sampling_interval_s * 1e9

        if self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_8BIT"]:    
            if sampling_interval_ns >= 8:
                timebase = int(125000000*sampling_interval_s) + 2
            elif sampling_interval_ns >= 4:
                timebase = 2
            elif sampling_interval_ns >= 2:
                timebase = 1
            else: # fastest possible
                timebase = 0 
            
        elif self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_12BIT"]:
            if sampling_interval_ns >= 16:
                timebase = int(62500000*sampling_interval_s) + 3
            elif sampling_interval_ns >= 8:
                timebase = 3
            elif sampling_interval_ns >= 4:
                timebase = 2
            else:
                timebase = 1

        elif self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_14BIT"] \
          or self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_15BIT"]:
            if sampling_interval_ns>= 16:
                timebase = int(125000000*sampling_interval_s) + 2
            else:
                timebase = 3

        elif self.resolution == ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_16BIT"]:
            if sampling_interval_ns>= 32:
                timebase = int(62500000*sampling_interval_s) + 3
            else:
                timebase = 4
            pass
        else:
            raise ValueError("Unsupported resolution")
        
        return timebase


    #channels may be good case-study for composite properties - but with no getter, its a command I guess...
    @api_property()
    @property
    def sampling_frequency(self) -> float:
        """Current sampling frequency in Hz."""

        return self._sampling_frequency

        if self._pico_raw_source.running():
            return self._sampling_frequency
        #print(" >>> inside sampling_frequency getter")

        timeIntervalns = ctypes.c_float()
        returnedMaxSamples = ctypes.c_int32()

        # todo check

        self.status["getTimebase2"] = ps.ps5000aGetTimebase2(self.chandle, 
                                                             self._timebase, 
                                                             1, 
                                                             ctypes.byref(timeIntervalns), 
                                                             ctypes.byref(returnedMaxSamples), 0)
        
        #print(f" >>> inside sampling_frequency getter: timeIntervalns = {timeIntervalns.value} ns, returnedMaxSamples = {returnedMaxSamples.value}")
               
        print(f" --- sampling interval.value = {timeIntervalns.value}, status = {self.status["getTimebase2"]}")

        if timeIntervalns.value > 0:
            return 1e9 / timeIntervalns.value
        else:
            print(f" --- ^^^ tis weird edge case")
        return 8 # just put something in there? TODO - how to handle this edge case?
    # @api_property()
    # @property
    # def sampling_frequency(self) -> float:
    #     return self._sampling_frequency
    
    # @sampling_frequency.setter
    # def sampling_frequency(self, value: float) -> None:
    #     self._sampling_frequency = value

    
    # todo - should getter & setter be async???
    @sampling_frequency.setter
    def sampling_frequency(self, value: float) -> None:

        if self._pico_raw_source.running():
            self._sampling_frequency = value
            self._time_interval_ns = 1e9 / value # pico raw source will get restarted with these values
            #await self._pico_raw_source.start(force_restart=True)
            # try:
            #     loop = asyncio.get_event_loop()
            # except:
            #     loop = asyncio.new_event_loop()
            #     asyncio.set_event_loop(loop)
            # loop.run_until_complete(self._pico_raw_source.start(force_restart=True))
            
            self._pico_raw_source.loop.call_soon_threadsafe(asyncio.create_task,self._pico_raw_source.start(force_restart=True))       
        
            return self._sampling_frequency # restart may modify requested values, return the true one...


        # normal block acquisition
            
        timeIntervalns = ctypes.c_float()
        returnedMaxSamples = ctypes.c_int32()

        self._timebase = self.estimate_timebase(value)
        # check that timebase is achievable given actual device settings
        for timebase_candidate in range(self._timebase, self._timebase + 5):
            self.status["getTimebase2"] = ps.ps5000aGetTimebase2(self.chandle, 
                                                                timebase_candidate, 
                                                                1, 
                                                                ctypes.byref(timeIntervalns), 
                                                                ctypes.byref(returnedMaxSamples), 0)
            if self.status["getTimebase2"] == 0:
                break
        else:   # if not break
            raise RuntimeError(f"Could not set timebase for requested frequency {value}Hz")
        
        self._timebase = timebase_candidate
        self._max_samples = returnedMaxSamples.value
        self._time_interval_ns = timeIntervalns.value
        actual_frequency = 1e9 / timeIntervalns.value
        self._sampling_frequency = actual_frequency
        return actual_frequency
    
    # read-only properties (slave of sampling_frequency)
    @api_property()
    @property   
    def sampling_time_ns(self) -> float:
        return self._time_interval_ns
         
    @api_property()
    @property
    def max_data_samples(self) -> int:
        """Maximum number of samples that can be captured in one acquisition."""
        return self._max_samples
    
    @api_property()
    @property
    def max_data_seconds(self) -> float:
        """Maximum number of samples that can be captured in one acquisition."""
        return self._max_samples * self._time_interval_ns * 1e-9
    
    @api_property()
    @property
    def pre_trigger_samples(self) -> int:
        """Number of pre-trigger samples in the current acquisition."""
        return self._cache.get("pre_trigger_samples", 0)
    
    @pre_trigger_samples.setter
    def pre_trigger_samples(self, value: int) -> None:
        if not (0 <= value <= self._max_samples):
            raise ValueError(f"pre_trigger_samples must be between 0 and {self._max_samples}")
        self._cache["pre_trigger_samples"] = value
        return value
    
    @api_property()
    @property
    def post_trigger_samples(self) -> int:  
        """Number of post-trigger samples in the current acquisition."""
        return self._cache.get("post_trigger_samples", 0)
    
    @post_trigger_samples.setter
    def post_trigger_samples(self, value: int) -> None:
        if not (0 <= value <= self._max_samples):
            raise ValueError(f"post_trigger_samples must be between 0 and {self._max_samples}")
        self._cache["post_trigger_samples"] = value
        return value
    



    @api_command()
    async def set_channel(self,
                          channel: Literal["A", "B", "C", "D"], 
                          enable: bool,
                          coupling_type: Literal["AC", "DC"], 
                          range: Literal['10MV', '20MV', '50MV', '100MV', '200MV', '500MV', '1V', '2V', '5V', '10V', '20V', '50V', 'MAX_RANGES']) -> dict:
        print("--- INSIDE set_channel", channel, enable, coupling_type, range)
        _channel = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]
        _enable = 1 if enable else 0
        _coupling_type = ps.PS5000A_COUPLING[f"PS5000A_{coupling_type}"]
        _range = ps.PS5000A_RANGE[f"PS5000A_{range}"]

        self.status[f"setCh{channel}"] = ps.ps5000aSetChannel(self.chandle, _channel, _enable, _coupling_type, _range, 0)
        assert_pico_ok(self.status[f"setCh{channel}"])

        ret = {"status": self.status[f"setCh{channel}"],
                "channel": _channel,
                "enable": _enable,
                "coupling_type": _coupling_type,
                "range": _range}
        self._cache[f"channel_{channel}"] = ret # this is extremeely stupid but there is no option to get the range once its set...
        return ret
    # async def get_channel_info(self, 
    #                            channel: Literal["A", "B", "C", "D"]) -> dict:
        
    #     _info = 0# I guess - only one type of channel information available?? ps.PS5000A_CHANNEL_INFO["PS5000A_CI_RANGE_INFO"]
    #     _ranges = (ctypes.c_int16 * 4)()
    #     _length = ctypes.c_int16(4)
    #     _channel = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]

    #     ps.ps5000aGetChannelInformation(self.chandle, _info, 0, _ranges, _length, _channel)
    
    @api_command()
    async def set_simple_trigger(self,
                                 enable: bool,
                                 source: Literal["A", "B", "C", "D"],
                                 threshold_mV: float,
                                 direction: Literal["RISING", "FALLING", "RISING_OR_FALLING"],
                                 delay: int = 0,
                                 auto_trigger_ms: int = 1000) -> dict:
        
        print("--- INSIDE set_simple_trigger", enable, source, threshold_mV, direction, delay, auto_trigger_ms)
        _enable = 1 if enable else 0
        _source = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{source}"]

        maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps5000aMaximumValue(self.chandle, ctypes.byref(maxADC))
        
        _channel_range = self._cache.get(f"channel_{source}", {}).get("range", ps.PS5000A_RANGE["PS5000A_1V"]) # assume default if it was not set previously...
        _threshold = int(mV2adc(threshold_mV,_channel_range, maxADC))
        _direction = ps.PS5000A_THRESHOLD_DIRECTION[f"PS5000A_{direction}"]
        _delay = delay
        _auto_trigger_ms = auto_trigger_ms
        
        self.status["trigger"] = ps.ps5000aSetSimpleTrigger(self.chandle, _enable, _source, _threshold, _direction, _delay, _auto_trigger_ms)
        assert_pico_ok(self.status["trigger"])

        ret = {"status": self.status["trigger"],
                "enable": _enable,
                "source": _source,
                "threshold": _threshold,
                "direction": _direction,
                "delay": _delay,
                "auto_trigger_ms": _auto_trigger_ms}
        
        self._cache["trigger"] = ret
        return ret
        

    @api_command() #MUST RETURN SOMETHING!!!
    def demo_wave(self) -> Frame:
        """Simple block acquisition"""
        

        # Start block acquisition
        pre_trigger_samples = self._cache.get("pre_trigger_samples", 0)
        post_trigger_samples = self._cache.get("post_trigger_samples", 5000)
        total_samples = pre_trigger_samples + post_trigger_samples
        timebase = self._timebase
        
        self.status["runBlock"] = ps.ps5000aRunBlock(self.chandle, 
                                                     pre_trigger_samples, 
                                                     post_trigger_samples, 
                                                     timebase, 
                                                     None, 
                                                     0, 
                                                     None, 
                                                     None)
        
        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        while ready.value == check.value:
            self.status["isReady"] = ps.ps5000aIsReady(self.chandle, ctypes.byref(ready))

        
        print(" >>>>>> Acquisition complete")

        # Set up data buffers for each enabled channel
        buffers_raw, buffers_mv = {}, {}
        for channel in ["A", "B", "C", "D"]:
            ch = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]
            enabled = self._cache.get(f"channel_{channel}", {}).get("enable", 0)
            if not enabled:
                pass #do I need to set up buffer for all channels?
                #continue

            buffer_max = (ctypes.c_int16 * total_samples)()
            buffer_min = (ctypes.c_int16 * total_samples)() # used for downsampling which isn't in the scope of this example

            source = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]
            self.status[f"setDataBuffers{channel}"] = ps.ps5000aSetDataBuffers(self.chandle, source, ctypes.byref(buffer_max), ctypes.byref(buffer_min), total_samples, 0, 0)

            buffers_raw[channel] = buffer_max

        print(" >>>>>> buffer setup complete")

        
        # get data from all buffers with one call
        overflow = ctypes.c_int16() # overflow location
        cmaxSamples = ctypes.c_int32(pre_trigger_samples + post_trigger_samples) # converted type maxSamples (wtf is this) # this ought to be set from before somehow??
        self.status["getValues"] = ps.ps5000aGetValues(self.chandle, 0, ctypes.byref(cmaxSamples), 0, 0, 0, ctypes.byref(overflow))
        assert_pico_ok(self.status["getValues"])

        # convert raw data to mV
        maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps5000aMaximumValue(self.chandle, ctypes.byref(maxADC))

        return_series = []
        for channel, raw_data in buffers_raw.items():
            data_decoded = np.frombuffer(raw_data, dtype=np.int16)
            break
           
        #return { "series": return_series }
        return {"data": data_decoded.tolist()}
        #return {"data": np.random.rand(pre_trigger_samples + post_trigger_samples).tolist() }

   
    @api_data()
    async def time_stream(self) -> AsyncIterator[Frame]:

        def mapper(x):
            return x.tolist()

        q = await self._pico_raw_source.subscribe()
        await self._pico_raw_source.start() # ensure background poller is running todo - what interval?? - none interval, there is a minimal one so that data can be read out all the time

        try:
            while True:
                frame = await q.get() # read out data from the queue, frame is {channel: np.array}
                yield {ch: mapper(data) for ch, data in frame.items()}
                # no need to sleep here, Im sleeping in the outer loop (async for time_stream())
                #asyncio.sleep(0.001) # to allow context change (is it necessary?)
        finally:
            await self._pico_raw_source.unsubscribe(q)
            

    # @api_data()
    # async def psd_stream(self) -> AsyncIterator[Frame]:
    #     """Returns PSD of the time series"""
    #     print(">>>> creating async def psd stream")

    #     def mapper(x):
    #         N = x.size
    #         dt = self.sampling_time_ns * 1e-9 #created at runtime - self can be fixed in definition time
    #         fs = 1/dt

    #         fft = np.fft.rfft(x)
    #         Pxx = 1 +(np.abs(fft[1:])**2) / (fs*N) # normalize to density [unit^2 / Hz]
    #         return Pxx.tolist()
        
    #     async for frame in self._stream(mapper):
    #         yield frame
        
    
    # @api_data()
    # async def time_stream(self) -> AsyncIterator[Frame]:
    #     def mapper(x):
    #         return x.tolist()
        
    #     async for frame in self._stream(mapper):
    #         yield frame

       
    
    @time_stream.plot()
    def time_stream_plot(self) -> Dict[str, Any]:
        """ Time series plot """

        pre_trigger_samples = self._cache.get("pre_trigger_samples", 0)
        post_trigger_samples = self._cache.get("post_trigger_samples", 5000)
        total_samples = pre_trigger_samples + post_trigger_samples

        return {"title": "Time series plot", 
                "x-label": "us", 
                "y-label": "V", 
                "x-values": (np.arange(total_samples)*self._time_interval_ns*1e-3).tolist()}
        
    

    # @psd_stream.plot()
    # def psd_stream_plot(self) -> Dict[str, Any]:
    #     """PSD plot (function doc)"""

    #     pre_trigger_samples = self._cache.get("pre_trigger_samples", 0)
    #     post_trigger_samples = self._cache.get("post_trigger_samples", 5000)
    #     total_samples = pre_trigger_samples + post_trigger_samples

    #     dt = self.sampling_time_ns * 1e-9 #created at runtime - self can be fixed in definition time
    #     fs = 1/dt

    #     freqs = np.fft.rfftfreq(total_samples, d=dt)[1:]

    #     return {
    #         "title":   self.psd_stream_plot.__doc__,
    #         "x-label": "Frequency (Hz)",
    #         # If you convert ADC->volts upstream, change to "Voltage (V)"
    #         "y-label": "PSD [V^2 / Hz]",
    #         "x-values": freqs.tolist(),
    #     }
