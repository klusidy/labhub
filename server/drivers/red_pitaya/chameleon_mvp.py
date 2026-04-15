"""
Chameleon MVP — STEMlab 125-14 FPGA driver for labhub.

Manages the full board lifecycle:
  1. SSH → upload server binary + bitfile
  2. Program FPGA via /dev/xdevcfg
  3. Start TCP register-access server
  4. Discover modules via fingerprint ROM

Device hierarchy::

    chameleon_mvp           ← root Device (handles connection)
    ├── router              ← 16×16 AXI-Stream crossbar
    ├── adc_input           ← ADC input + equalization filter
    ├── asg                 ← Arbitrary Signal Generator
    ├── dac_out             ← Analog output enable
    ├── scope               ← 4-channel oscilloscope (16 k samples)
    └── sum_block           ← Weighted sum/diff of two signals

Configuration (config.yaml)::

    - id: chameleon_01
      driver: red_pitaya.chameleon_mvp
      hostname: 169.254.2.8
      fpga_dir_src: C:/path/to/fpga_bitfiles   # optional, defaults to chameleon2/fpga_bitfiles
      server_dir_src: null                       # optional, defaults to chameleon2/server
      overwrite_server: false
      should_connect: true

Source/destination index constants (for router sel_* properties)::

    Sources (what to put in sel_*):
        0 = ADC A,  1 = ADC B,  2 = ASG,  3 = SUM,  4 = DIFF

    Destinations correspond to properties:
        sel_dac_a, sel_dac_b, sel_scope_a/b/c/d, sel_sum_a/b
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Dict, Any, List, Optional, TYPE_CHECKING

from ..base import (
    Device,
    ChildDevice,
    api_device,
    api_command,
    api_property,
    api_data,
    Frame,
)

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


@api_device()
class chameleon_mvp(Device):
    """
    Chameleon FPGA board on a STEMlab 125-14.

    Connects via SSH, programs the FPGA, starts the register-access server,
    and exposes all discovered modules as child devices.
    """

    config_template = {
        "hostname": "169.254.10.10",
        "username": "root",
        "password": "root",
        "server_port": 2222,
        "fpga_filename": "chameleon_latest.bit",
        "fpga_dir_src": None,  # local directory containing the bitfile
        "server_dir_src": None,  # local directory containing the server binary
        "overwrite_server": False,
        "polling_interval": 2000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)
        self._chameleon_manager = None
        self._dev = None  # ChameleonDevice instance after connect

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def connect(self) -> bool:
        """SSH into board, program FPGA, start server, discover modules.

        Runs in a thread (blocking) — may take 10–30 seconds on first call
        due to FPGA programming.
        """
        # Import here to keep the import optional at module level
        from chameleon.manager import ChameleonManager

        try:
            opt = self.options
            mgr_kwargs = dict(
                hostname=opt.get("hostname", "169.254.10.10"),
                username=opt.get("username", "root"),
                password=opt.get("password", "root"),
                server_port=opt.get("server_port", 2222),
                fpga_filename=opt.get("fpga_filename", "chameleon_latest.bit"),
                overwrite_server=opt.get("overwrite_server", False),
            )
            if opt.get("fpga_dir_src"):
                mgr_kwargs["fpga_dir_src"] = opt["fpga_dir_src"]
            if opt.get("server_dir_src"):
                mgr_kwargs["server_dir_src"] = opt["server_dir_src"]

            self._chameleon_manager = ChameleonManager(**mgr_kwargs)
            self._dev = self._chameleon_manager.setup()
            logger.info(
                "%s: connected to %s — %d module(s) discovered",
                self.id,
                mgr_kwargs["hostname"],
                len(self._dev.modules),
            )
            return True
        except Exception as exc:
            logger.error("%s: connect() failed: %s", self.id, exc)
            self._chameleon_manager = None
            self._dev = None
            return False

    async def disconnect(self) -> bool:
        if self._chameleon_manager is not None:
            try:
                await self._run_blocking_in_thread(self._chameleon_manager.close)
            except Exception as exc:
                logger.warning("%s: disconnect error: %s", self.id, exc)
            finally:
                self._chameleon_manager = None
                self._dev = None
        return True

    # -----------------------------------------------------------------------
    # Root-level properties
    # -----------------------------------------------------------------------

    @api_property(doc="Board hostname / IP address")
    def hostname(self) -> str:
        return self.options.get("hostname", "?")

    @api_property(doc="Number of FPGA modules discovered via fingerprint ROM")
    def n_modules(self) -> int:
        return len(self._dev.modules) if self._dev else 0

    # -----------------------------------------------------------------------
    # Children
    # -----------------------------------------------------------------------

    @api_device()
    class router(ChildDevice):
        """16×16 AXI-Stream crossbar — configure signal routing between modules.

        Available sources (choose in sel_* properties):
            ADC_A, ADC_B   — analog inputs after the equalization filter
            ASG            — arbitrary signal generator (digital, pre-DAC)
            SUM            — sum_block weighted sum output
            DIFF           — sum_block weighted difference output
        """

        # Human-readable source names; index = hardware slot number.
        _SRC_NAMES: List[str] = [
            "ADC_A", "ADC_B", "ASG", "SUM", "DIFF",
            "src5", "src6", "src7", "src8", "src9",
            "src10", "src11", "src12", "src13", "src14", "src15",
        ]
        _SRC_CHOICES = _SRC_NAMES  # alias for decorator

        def connect(self) -> bool:
            from chameleon.modules.router import Router as _Router
            self._hw: _Router = self._parent._dev.router
            return True

        def _src_to_idx(self, name: str) -> int:
            try:
                return self._SRC_NAMES.index(name)
            except ValueError:
                return 0

        def _idx_to_src(self, idx: int) -> str:
            return self._SRC_NAMES[idx] if 0 <= idx < len(self._SRC_NAMES) else "ADC_A"

        # --- Destination slots exposed as string-choice properties ---

        @api_property(choices=_SRC_CHOICES, doc="Signal source for DAC A output")
        def sel_dac_a(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_DAC_A])

        @sel_dac_a.setter
        def sel_dac_a(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_DAC_A] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for DAC B output")
        def sel_dac_b(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_DAC_B])

        @sel_dac_b.setter
        def sel_dac_b(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_DAC_B] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for Scope channel A")
        def sel_scope_a(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SCOPE_A])

        @sel_scope_a.setter
        def sel_scope_a(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SCOPE_A] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for Scope channel B")
        def sel_scope_b(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SCOPE_B])

        @sel_scope_b.setter
        def sel_scope_b(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SCOPE_B] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for Scope channel C")
        def sel_scope_c(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SCOPE_C])

        @sel_scope_c.setter
        def sel_scope_c(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SCOPE_C] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for Scope channel D")
        def sel_scope_d(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SCOPE_D])

        @sel_scope_d.setter
        def sel_scope_d(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SCOPE_D] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for SumBlock input A")
        def sel_sum_a(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SUM_A])

        @sel_sum_a.setter
        def sel_sum_a(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SUM_A] = self._src_to_idx(v)

        @api_property(choices=_SRC_CHOICES, doc="Signal source for SumBlock input B")
        def sel_sum_b(self) -> str:
            from chameleon.modules.router import Router as _R
            return self._idx_to_src(self._hw.sel[_R.DST_SUM_B])

        @sel_sum_b.setter
        def sel_sum_b(self, v: str) -> None:
            from chameleon.modules.router import Router as _R
            self._hw.sel[_R.DST_SUM_B] = self._src_to_idx(v)

        @api_command(
            doc="Read all 16 routing slots. Returns list where index=destination, value=source name."
        )
        def read_routing(self) -> Dict[str, str]:
            raw = self._hw.sel.read_all()
            dst_names = [
                "DAC_A", "DAC_B", "SCOPE_A", "SCOPE_B", "SCOPE_C", "SCOPE_D",
                "SUM_A", "SUM_B", "dst8", "dst9", "dst10", "dst11",
                "dst12", "dst13", "dst14", "dst15",
            ]
            return {dst_names[i]: self._idx_to_src(raw[i]) for i in range(16)}

        @api_command(
            doc="Restore default routing: ADC A/B → DAC A/B, Scope A-D, SumBlock A/B"
        )
        def reset_to_defaults(self) -> str:
            self._hw.reset_to_defaults()
            return "routing restored to defaults"

    # -----------------------------------------------------------------------

    @api_device()
    class adc_input(ChildDevice):
        """ADC input — equalization filter bypass and live sample readout."""

        def connect(self) -> bool:
            self._hw = self._parent._dev.adc_input
            return True

        @api_property(doc="Latest channel A sample (16-bit signed ADC counts)")
        def sample_a(self) -> int:
            return int(self._hw.sample_a)

        @api_property(doc="Latest channel B sample (16-bit signed ADC counts)")
        def sample_b(self) -> int:
            return int(self._hw.sample_b)

        @api_property(
            doc="Bypass equalization filter on channel A (True = bypass, default)"
        )
        def bypass_a(self) -> bool:
            return self._hw.bypass_a

        @bypass_a.setter
        def bypass_a(self, v: bool) -> None:
            self._hw.bypass_a = v

        @api_property(
            doc="Bypass equalization filter on channel B (True = bypass, default)"
        )
        def bypass_b(self) -> bool:
            return self._hw.bypass_b

        @bypass_b.setter
        def bypass_b(self, v: bool) -> None:
            self._hw.bypass_b = v

    # -----------------------------------------------------------------------

    @api_device()
    class asg(ChildDevice):
        """Arbitrary Signal Generator — configurable waveform on the DAC path."""

        # Class-level defaults (overwritten in connect)
        _frequency_hz: float = 1000.0
        _amplitude: float = 0.5
        _waveform: str = "off"

        def connect(self) -> bool:
            self._hw = self._parent._dev.asg
            # Instance variables — safe to set here, connect() is called once
            self._frequency_hz = 1000.0
            self._amplitude = 0.5
            self._waveform = "off"
            return True

        @api_property(min=1.0, max=62.5e6, unit="Hz", doc="Output frequency")
        def frequency(self) -> float:
            try:
                return self._hw.frequency
            except Exception:
                return self._frequency_hz

        @frequency.setter
        def frequency(self, v: float) -> None:
            self._frequency_hz = v
            if self._waveform not in ("off", "dc"):
                self._apply_waveform()

        @api_property(
            min=0.0, max=1.0, doc="Output amplitude as fraction of full scale (0–1)"
        )
        def amplitude(self) -> float:
            return self._amplitude

        @amplitude.setter
        def amplitude(self, v: float) -> None:
            self._amplitude = v
            self._apply_waveform()

        @api_property(choices=["sine", "ramp", "dc", "off"], doc="Waveform type")
        def waveform(self) -> str:
            return self._waveform

        @waveform.setter
        def waveform(self, v: str) -> None:
            self._waveform = v
            self._apply_waveform()

        @api_property(doc="True if ASG is currently running")
        def is_running(self) -> bool:
            return self._hw.is_running

        def _apply_waveform(self) -> None:
            if self._waveform == "sine":
                self._hw.load_sine(self._frequency_hz, self._amplitude)
            elif self._waveform == "ramp":
                self._hw.load_ramp(self._frequency_hz, self._amplitude)
            elif self._waveform == "dc":
                self._hw.load_dc(self._amplitude)
            else:
                self._hw.stop()

        @api_command(doc="Start continuous sine output. frequency: Hz, amplitude: 0–1")
        def start_sine(self, frequency: float = 1000.0, amplitude: float = 0.5) -> str:
            self._frequency_hz = frequency
            self._amplitude = amplitude
            self._waveform = "sine"
            self._hw.load_sine(frequency, amplitude)
            return f"sine {frequency:.1f} Hz  amp={amplitude:.3f}"

        @api_command(doc="Start continuous ramp output. frequency: Hz, amplitude: 0–1")
        def start_ramp(self, frequency: float = 1000.0, amplitude: float = 0.5) -> str:
            self._frequency_hz = frequency
            self._amplitude = amplitude
            self._waveform = "ramp"
            self._hw.load_ramp(frequency, amplitude)
            return f"ramp {frequency:.1f} Hz  amp={amplitude:.3f}"

        @api_command(doc="Output a constant DC level. level: −1.0 to +1.0")
        def start_dc(self, level: float = 0.0) -> str:
            self._amplitude = level
            self._waveform = "dc"
            self._hw.load_dc(level)
            return f"DC level={level:.4f}"

        @api_command(doc="Stop ASG output")
        def stop(self) -> str:
            self._waveform = "off"
            self._hw.stop()
            return "ASG stopped"

    # -----------------------------------------------------------------------

    @api_device()
    class dac_out(ChildDevice):
        """DAC output — enable/disable the analog output stage."""

        def connect(self) -> bool:
            self._hw = self._parent._dev.dac_out
            return True

        @api_property(doc="Enable analog DAC output (False = muted at mid-scale / 0 V)")
        def output_enable(self) -> bool:
            return bool(self._hw.output_enable)

        @output_enable.setter
        def output_enable(self, v: bool) -> None:
            self._hw.output_enable = v

    # -----------------------------------------------------------------------

    @api_device()
    class scope(ChildDevice):
        """4-channel BRAM oscilloscope with configurable trigger and decimation.

        Trigger source string → integer mapping:
            'off'=0  'sw'=1
            'ch0_rise'=2  'ch0_fall'=3
            'ch1_rise'=4  'ch1_fall'=5
            'ch2_rise'=6  'ch2_fall'=7
            'ch3_rise'=8  'ch3_fall'=9
            'ext_rise'=10 'ext_fall'=11
        """

        _TRIG_NAMES = [
            "off",
            "sw",
            "ch0_rise",
            "ch0_fall",
            "ch1_rise",
            "ch1_fall",
            "ch2_rise",
            "ch2_fall",
            "ch3_rise",
            "ch3_fall",
            "ext_rise",
            "ext_fall",
        ]

        def connect(self) -> bool:
            from chameleon.modules.scope import Scope as _Scope

            self._hw: _Scope = self._parent._dev.scope
            self._Scope = _Scope
            return True

        @api_property(
            min=1, max=131071, doc="Decimation factor (1 = 125 MSa/s full rate)"
        )
        def decimation(self) -> int:
            return int(self._hw.decimation)

        @decimation.setter
        def decimation(self, v: int) -> None:
            self._hw.decimation = max(1, int(v))

        @api_property(unit="Hz", doc="Effective sample rate = 125 MHz / decimation")
        def sample_rate_hz(self) -> float:
            return self._hw.sample_rate_hz

        @api_property(
            choices=[
                "off",
                "sw",
                "ch0_rise",
                "ch0_fall",
                "ch1_rise",
                "ch1_fall",
                "ch2_rise",
                "ch2_fall",
                "ch3_rise",
                "ch3_fall",
                "ext_rise",
                "ext_fall",
            ],
            doc="Trigger source",
        )
        def trig_source(self) -> str:
            raw = int(self._hw.trig_source)
            if 0 <= raw < len(self._TRIG_NAMES):
                return self._TRIG_NAMES[raw]
            return "off"

        @trig_source.setter
        def trig_source(self, v: str) -> None:
            try:
                self._hw.trig_source = self._TRIG_NAMES.index(v)
            except ValueError:
                self._hw.trig_source = 0

        @api_property(
            min=-32768, max=32767, doc="Trigger threshold (16-bit signed ADC counts)"
        )
        def trig_level(self) -> int:
            return int(self._hw.trig_level)

        @trig_level.setter
        def trig_level(self, v: int) -> None:
            self._hw.trig_level = int(v)

        @api_property(
            min=0, max=65535, doc="Trigger hysteresis band (ADC counts, unsigned)"
        )
        def trig_hyst(self) -> int:
            return int(self._hw.trig_hyst)

        @trig_hyst.setter
        def trig_hyst(self, v: int) -> None:
            self._hw.trig_hyst = int(v)

        @api_property(
            min=1, max=16383, doc="Number of pre-trigger samples (post = 16384 − pre)"
        )
        def pre_trig_len(self) -> int:
            return int(self._hw.pre_trig_len)

        @pre_trig_len.setter
        def pre_trig_len(self, v: int) -> None:
            from chameleon.modules.scope import BUF_DEPTH as _BD

            v = max(1, min(int(v), _BD - 1))
            self._hw.pre_trig_len = v
            self._hw.post_trig_len = _BD - v

        def _apply_trig_config(self) -> None:
            """Write current trigger properties to hardware.

            Called before every arm to guarantee hardware matches the displayed
            GUI state, even after an FPGA reprogram (which resets all registers
            to defaults: trig_source=0/off, trig_level=0, trig_hyst=20).
            """
            hw = self._hw
            # Read from Python cache (populated by polling).  Fall back to
            # safe defaults so capture() always works on a freshly programmed board.
            ts_str = self._cache.get("trig_source", "sw")
            try:
                ts_idx = self._TRIG_NAMES.index(ts_str)
            except ValueError:
                ts_idx = 1  # sw = immediate trigger
            hw.trig_source = ts_idx
            hw.trig_level  = int(self._cache.get("trig_level", 0))
            hw.trig_hyst   = int(self._cache.get("trig_hyst", 20))
            hw.decimation  = max(1, int(self._cache.get("decimation", 1)))

        @api_command(
            doc="Arm scope and wait for capture. Returns time-ordered 4-channel data "
                "(keys: t, ch0–ch3, sample_rate_hz). timeout_s: max wait in seconds."
        )
        def capture(self, timeout_s: float = 5.0) -> Dict[str, Any]:
            """Re-applies current trig settings then arms and waits for capture."""
            self._apply_trig_config()
            data = self._hw.capture(timeout=timeout_s)
            t, channels = self._Scope.unroll(data)
            return {
                "t": t.tolist(),
                "ch0": channels[0].tolist(),
                "ch1": channels[1].tolist(),
                "ch2": channels[2].tolist(),
                "ch3": channels[3].tolist(),
                "sample_rate_hz": self._hw.sample_rate_hz,
            }

        @api_data(doc="Continuous 4-channel scope stream (repeating captures)")
        async def wave(self) -> AsyncIterator[Frame]:
            """Repeatedly capture and stream scope data as time-ordered frames.

            Recovery policy:
            - Trigger timeout (trigger never fires): retries indefinitely,
              re-applying trig config each time so fixing the setting in the
              GUI immediately resumes the stream.
            - Protocol/hardware errors (header mismatch, ACK mismatch,
              unimplemented register type, etc.): up to MAX_PROTO_RETRIES
              retries with trig config re-apply between attempts.
            - Connection loss (OSError, NoneType.sendall, etc.): up to
              MAX_RECONNECTS full parent reconnects before giving up.
            All error counters reset on each successful capture.
            """
            _MAX_PROTO_RETRIES = 5
            _MAX_RECONNECTS = 3

            proto_errors = 0
            reconnect_count = 0
            timeout_count = 0

            # Apply trigger config once — ensures a fresh-programmed board can stream
            try:
                await self._run_blocking_in_thread(self._apply_trig_config)
            except Exception as exc:
                logger.warning("%s.scope: initial trig config failed: %s", self._parent.id, exc)

            try:
                while True:
                    try:
                        data = await self._run_blocking_in_thread(self._hw.capture, 5.0)
                        t, channels = self._Scope.unroll(data)
                        # Successful capture — reset all error counters
                        proto_errors = 0
                        reconnect_count = 0
                        timeout_count = 0
                        yield {
                            "series": [
                                {"name": "Ch A", "data": channels[0].tolist()},
                                {"name": "Ch B", "data": channels[1].tolist()},
                                {"name": "Ch C", "data": channels[2].tolist()},
                                {"name": "Ch D", "data": channels[3].tolist()},
                            ]
                        }

                    except asyncio.CancelledError:
                        raise

                    except (AttributeError, OSError) as exc:
                        # Connection-loss errors: NoneType.sendall, WinError 10038, etc.
                        reconnect_count += 1
                        logger.warning(
                            "%s.scope: connection lost in wave (reconnect %d/%d): %s",
                            self._parent.id, reconnect_count, _MAX_RECONNECTS, exc,
                        )
                        if reconnect_count > _MAX_RECONNECTS:
                            raise RuntimeError(
                                f"wave: too many reconnect attempts ({_MAX_RECONNECTS}), giving up"
                            ) from exc
                        await asyncio.sleep(3.0)
                        try:
                            await self._parent.disconnect()
                            await self._run_blocking_in_thread(self._parent.connect)
                            self._hw = self._parent._dev.scope
                            await self._run_blocking_in_thread(self._apply_trig_config)
                            logger.info(
                                "%s.scope: reconnected, resuming wave stream", self._parent.id
                            )
                            proto_errors = 0
                            timeout_count = 0
                        except Exception as reconnect_exc:
                            logger.error(
                                "%s.scope: reconnect failed: %s", self._parent.id, reconnect_exc
                            )

                    except Exception as exc:
                        msg = str(exc).lower()
                        if "timed out" in msg or "timeout" in msg:
                            # Trigger timeout — retry indefinitely; user may have set a
                            # trigger condition that hasn't fired yet.  Re-applying trig
                            # config picks up any setting changes made in the GUI.
                            timeout_count += 1
                            if timeout_count == 1 or timeout_count % 10 == 0:
                                logger.warning(
                                    "%s.scope: capture timeout #%d (trig_source=%r) — "
                                    "retrying; change trig_source to 'sw' for free-running",
                                    self._parent.id,
                                    timeout_count,
                                    self._cache.get("trig_source", "?"),
                                )
                            await asyncio.sleep(0.2)
                            try:
                                await self._run_blocking_in_thread(self._apply_trig_config)
                            except Exception:
                                pass
                        else:
                            # Protocol/hardware error: header mismatch, ACK mismatch,
                            # unhandled register type, etc.
                            proto_errors += 1
                            logger.warning(
                                "%s.scope: protocol/hardware error (%d/%d): %s",
                                self._parent.id, proto_errors, _MAX_PROTO_RETRIES, exc,
                            )
                            if proto_errors >= _MAX_PROTO_RETRIES:
                                raise RuntimeError(
                                    f"wave: too many consecutive protocol errors "
                                    f"({_MAX_PROTO_RETRIES}), giving up"
                                ) from exc
                            await asyncio.sleep(0.5)
                            try:
                                await self._run_blocking_in_thread(self._apply_trig_config)
                            except Exception:
                                pass

            finally:
                logger.debug("%s.scope: wave stream stopped", self._parent.id)

        @wave.plot()
        def wave_plot(self) -> Dict[str, Any]:
            from chameleon.modules.scope import BUF_DEPTH as _BD, CLOCK_FREQ as _CLK

            dec = int(self._hw.decimation)
            pre = int(self._hw.pre_trig_len)
            dt_us = dec / _CLK * 1e6
            t_us = [(i - pre) * dt_us for i in range(_BD)]
            return {
                "title": "Scope",
                "x-label": "Time relative to trigger (µs)",
                "y-label": "ADC counts",
                "x-values": t_us,
            }

    # -----------------------------------------------------------------------

    @api_device()
    class sum_block(ChildDevice):
        """Weighted sum and difference of two router-connected signals.

        Computes (in FPGA):
            out_sum  = sat16( (gain_a × A + gain_b × B) / 2^14 )
            out_diff = sat16( (gain_a × A − gain_b × B) / 2^14 )

        Gains are Q1.14 float: range −2.0 to +1.9999.
        Preset: gain_a = gain_b = 0.5  →  sum = (A+B)/2, no saturation.
        """

        def connect(self) -> bool:
            self._hw = self._parent._dev.sum_block
            return True

        @api_property(
            min=-2.0, max=1.9999, doc="Gain applied to input A (Q1.14, +1.0 = unity)"
        )
        def gain_a(self) -> float:
            return self._hw.gain_a

        @gain_a.setter
        def gain_a(self, v: float) -> None:
            self._hw.gain_a = float(v)

        @api_property(
            min=-2.0, max=1.9999, doc="Gain applied to input B (Q1.14, +1.0 = unity)"
        )
        def gain_b(self) -> float:
            return self._hw.gain_b

        @gain_b.setter
        def gain_b(self, v: float) -> None:
            self._hw.gain_b = float(v)

        @api_command(doc="Set gain_a = gain_b = 0.5 for non-clipping (A+B)/2 sum")
        def preset_half_sum(self) -> str:
            self._hw.gain_a = 0.5
            self._hw.gain_b = 0.5
            return "gain_a=0.5, gain_b=0.5"

        @api_command(doc="Set gain_a = gain_b = 1.0 for full unity-gain sum (may clip)")
        def preset_unity_sum(self) -> str:
            self._hw.gain_a = 1.0
            self._hw.gain_b = 1.0
            return "gain_a=1.0, gain_b=1.0"
