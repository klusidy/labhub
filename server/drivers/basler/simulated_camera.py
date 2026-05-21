"""
Simulated Basler camera driver for LabHub.

Identical API to basler.camera but requires no physical camera.
Frames are rendered from a static reference image with physics-based modelling
of brightness and noise as a function of exposure_time and gain.

Brightness model
----------------
  signal = reference_pixel * (exposure_time / reference_exposure)
                           * 10^((gain - reference_gain) / 20)

Noise model
-----------
  shot_noise ~ Normal(0, sqrt(signal))      — Poisson approximation
  read_noise ~ Normal(0, READ_NOISE_STD)    — sensor floor
  output = clip(signal + shot_noise + read_noise, 0, 255)

Configuration (config.yaml)::

    - id: basler_sim
      driver: basler.simulated_camera
      reference_image: path/to/reference.png  # omit → synthetic gradient
      reference_exposure: 10000.0             # µs at which reference was taken
      reference_gain: 0.0                     # dB at which reference was taken
      read_noise_std: 2.0                     # ADU, sensor read noise floor
      polling_interval: 2000
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import AsyncIterator, Dict, Any, List, Optional, TYPE_CHECKING

import numpy as np
from PIL import Image

from ..base import Device, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)

_DEFAULT_SENSOR_W = 640
_DEFAULT_SENSOR_H = 480
_DEFAULT_FPS = 25.0
_TARGET_MEAN_FRACTION = 0.6  # auto-expose targets 60 % of full scale


def _array_to_b64png(arr: np.ndarray) -> str:
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@api_device()
class simulated_camera(Device):
    """
    Simulated Basler camera.

    Renders frames from a static reference image with physics-based brightness
    and noise modelling.  Drop-in replacement for basler.camera — same API,
    no hardware required.
    """

    config_template = {
        "reference_image": None,  # path to PNG/TIFF; null → synthetic gradient
        "reference_exposure": 10000.0,  # µs
        "reference_gain": 0.0,  # dB
        "read_noise_std": 2.0,  # ADU
        "polling_interval": 2000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)
        self._ref_image: Optional[np.ndarray] = None  # float32 H×W

        # Mutable camera state (mirrors hardware registers)
        self._exposure_time: float = 10000.0
        self._gain: float = 0.0
        self._pixel_format: str = "Mono8"
        self._sensor_w: int = _DEFAULT_SENSOR_W
        self._sensor_h: int = _DEFAULT_SENSOR_H
        self._width: int = _DEFAULT_SENSOR_W
        self._height: int = _DEFAULT_SENSOR_H
        self._offset_x: int = 0
        self._offset_y: int = 0
        self._frame_rate_enable: bool = False
        self._frame_rate: float = _DEFAULT_FPS
        self._trigger_mode: str = "Off"
        self._trigger_source: str = "Software"
        self._is_grabbing: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        ref_path = self.options.get("reference_image")
        if ref_path:
            try:
                img = Image.open(ref_path).convert("L")
                self._ref_image = np.asarray(img, dtype=np.float32)
                logger.info(
                    "%s: loaded reference image %s (%dx%d)",
                    self.id,
                    ref_path,
                    self._ref_image.shape[1],
                    self._ref_image.shape[0],
                )
            except Exception as exc:
                logger.warning(
                    "%s: could not load reference image '%s': %s — using synthetic",
                    self.id,
                    ref_path,
                    exc,
                )
                self._ref_image = self._make_synthetic_image(
                    _DEFAULT_SENSOR_H, _DEFAULT_SENSOR_W
                )
        else:
            self._ref_image = self._make_synthetic_image(
                _DEFAULT_SENSOR_H, _DEFAULT_SENSOR_W
            )
            logger.info(
                "%s: no reference image configured — using synthetic gradient", self.id
            )

        self._sensor_h, self._sensor_w = self._ref_image.shape
        self._width = self._sensor_w
        self._height = self._sensor_h
        return True

    def disconnect(self) -> bool:
        self._is_grabbing = False
        return True

    # ------------------------------------------------------------------
    # Read-only identification
    # ------------------------------------------------------------------

    @api_property(doc="Camera model name")
    def model(self) -> str:
        return "Simulated Basler acA2440-20gm"

    @api_property(doc="Camera serial number")
    def serial_number(self) -> str:
        return "SIM-000000"

    @api_property(unit="°C", doc="Device temperature (not available on all models)")
    def temperature(self) -> float:
        return None

    # ------------------------------------------------------------------
    # Acquisition parameters
    # ------------------------------------------------------------------

    @api_property(min=10.0, max=10_000_000.0, unit="µs", doc="Exposure time")
    def exposure_time(self) -> float:
        return self._exposure_time

    @exposure_time.setter
    def exposure_time(self, v: float) -> None:
        self._exposure_time = float(v)

    @api_property(
        min=0.0,
        max=48.0,
        unit="dB",
        doc="Analog gain (SFNC ≥ 2.x; max depends on camera)",
    )
    def gain(self) -> float:
        return self._gain

    @gain.setter
    def gain(self, v: float) -> None:
        self._gain = float(v)

    @api_property(
        choices=["Mono8", "Mono12", "Mono16", "BayerRG8", "BayerRG12", "RGB8Packed"],
        doc="Pixel format (sensor output; available choices depend on camera model)",
    )
    def pixel_format(self) -> str:
        return self._pixel_format

    @pixel_format.setter
    def pixel_format(self, v: str) -> None:
        self._pixel_format = v

    # ------------------------------------------------------------------
    # Region of interest
    # ------------------------------------------------------------------

    @api_property(min=1, doc="ROI width in pixels")
    def width(self) -> int:
        return self._width

    @api_property(min=1, doc="ROI height in pixels")
    def height(self) -> int:
        return self._height

    @api_property(min=0, doc="ROI horizontal offset from sensor origin")
    def offset_x(self) -> int:
        return self._offset_x

    @api_property(min=0, doc="ROI vertical offset from sensor origin")
    def offset_y(self) -> int:
        return self._offset_y

    # ------------------------------------------------------------------
    # Frame rate
    # ------------------------------------------------------------------

    @api_property(doc="Enable explicit acquisition frame rate limit")
    def frame_rate_enable(self) -> bool:
        return self._frame_rate_enable

    @frame_rate_enable.setter
    def frame_rate_enable(self, v: bool) -> None:
        self._frame_rate_enable = bool(v)

    @api_property(
        min=0.1,
        max=2000.0,
        unit="Hz",
        doc="Target frame rate (active when frame_rate_enable=True)",
    )
    def frame_rate(self) -> float:
        return self._frame_rate

    @frame_rate.setter
    def frame_rate(self, v: float) -> None:
        self._frame_rate = float(v)

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------

    @api_property(
        choices=["Off", "On"],
        doc="Trigger mode — Off: free-run; On: wait for trigger_source",
    )
    def trigger_mode(self) -> str:
        return self._trigger_mode

    @trigger_mode.setter
    def trigger_mode(self, v: str) -> None:
        self._trigger_mode = v

    @api_property(
        choices=["Software", "Line1", "Line2", "Line3", "Line4"],
        doc="Active trigger source (only relevant when trigger_mode=On)",
    )
    def trigger_source(self) -> str:
        return self._trigger_source

    @trigger_source.setter
    def trigger_source(self, v: str) -> None:
        self._trigger_source = v

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @api_command(
        doc="Grab a single frame and return pixel data as a 2D list (rows × cols, uint8). "
        "Works while the live stream is active. Large images are slow over JSON — "
        "use the live stream for display."
    )
    def snap(self) -> List[List[int]]:
        return self._render_frame().tolist()

    @api_command(
        doc="Send a software trigger pulse. Requires trigger_mode=On and trigger_source=Software."
    )
    def execute_software_trigger(self) -> str:
        return "software trigger sent"

    @api_command(
        doc="Set region of interest. Values are clamped to sensor bounds and "
        "alignment increments automatically."
    )
    def set_roi(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 640,
        height: int = 480,
    ) -> str:
        self._offset_x = max(0, min(x, self._sensor_w - 1))
        self._offset_y = max(0, min(y, self._sensor_h - 1))
        self._width = max(1, min(width, self._sensor_w - self._offset_x))
        self._height = max(1, min(height, self._sensor_h - self._offset_y))
        return (
            f"ROI: x={self._offset_x} y={self._offset_y} "
            f"w={self._width} h={self._height}"
        )

    @api_command(doc="Reset ROI to full sensor resolution.")
    def reset_roi(self) -> str:
        self._offset_x = 0
        self._offset_y = 0
        self._width = self._sensor_w
        self._height = self._sensor_h
        return f"ROI reset to full sensor: {self._width}×{self._height}"

    @api_command(
        doc="Run one-shot automatic exposure and return the resulting exposure time (µs). "
        "Blocks until the camera reports convergence (≤ 5 s)."
    )
    def auto_expose_once(self) -> float:
        ref_exp = float(self.options.get("reference_exposure", 10000.0))
        ref_gain = float(self.options.get("reference_gain", 0.0))
        gain_linear = 10 ** ((self._gain - ref_gain) / 20.0)
        ref_mean = float(np.mean(self._roi_from_reference()))
        if ref_mean < 1.0:
            ref_mean = 1.0
        target = _TARGET_MEAN_FRACTION * 255.0
        optimal_exp = ref_exp * (target / ref_mean) / gain_linear
        self._exposure_time = float(np.clip(optimal_exp, 10.0, 10_000_000.0))
        time.sleep(0.1)  # simulate convergence delay
        return self._exposure_time

    @api_command(
        doc="Run one-shot automatic gain and return the resulting gain (dB). "
        "Blocks until the camera reports convergence (≤ 5 s)."
    )
    def auto_gain_once(self) -> float:
        ref_exp = float(self.options.get("reference_exposure", 10000.0))
        ref_gain = float(self.options.get("reference_gain", 0.0))
        ref_mean = float(np.mean(self._roi_from_reference()))
        if ref_mean < 1.0:
            ref_mean = 1.0
        target = _TARGET_MEAN_FRACTION * 255.0
        exposure_scale = self._exposure_time / ref_exp
        needed_gain_linear = (target / ref_mean) / exposure_scale
        # convert to dB: gain_dB = 20 * log10(linear)
        optimal_gain_dB = 20.0 * np.log10(max(needed_gain_linear, 1e-6)) + ref_gain
        self._gain = float(np.clip(optimal_gain_dB, 0.0, 48.0))
        time.sleep(0.1)
        return self._gain

    # ------------------------------------------------------------------
    # Data source: live image stream
    # ------------------------------------------------------------------

    @api_data(
        "live",
        kind="image",
        doc="Continuous live image stream (Mono8, base64-PNG frames)",
    )
    async def live(self) -> AsyncIterator[Frame]:
        """Continuously render and yield simulated frames as base64-encoded PNG images."""
        loop = asyncio.get_running_loop()
        self._is_grabbing = True
        logger.debug("%s: simulated live stream started", self.id)
        try:
            while True:
                fps = self._frame_rate if self._frame_rate_enable else _DEFAULT_FPS
                frame_interval = 1.0 / max(fps, 0.1)

                arr = await loop.run_in_executor(None, self._render_frame)
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}

                await asyncio.sleep(frame_interval)
        finally:
            self._is_grabbing = False
            logger.debug("%s: simulated live stream stopped", self.id)

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _render_frame(self) -> np.ndarray:
        """Render one Mono8 frame with brightness and noise modelling."""
        ref_exp = float(self.options.get("reference_exposure", 10000.0))
        ref_gain = float(self.options.get("reference_gain", 0.0))
        read_noise_std = float(self.options.get("read_noise_std", 2.0))

        exposure_scale = self._exposure_time / ref_exp
        gain_linear = 10 ** ((self._gain - ref_gain) / 20.0)
        scale = exposure_scale * gain_linear

        roi = self._roi_from_reference()
        scaled = roi * scale

        shot_noise = np.sqrt(np.maximum(scaled, 0.0)) * np.random.standard_normal(
            scaled.shape
        )
        read_noise = read_noise_std * np.random.standard_normal(scaled.shape)

        return np.clip(scaled + shot_noise + read_noise, 0, 255).astype(np.uint8)

    def _roi_from_reference(self) -> np.ndarray:
        """Return a float32 crop of the reference image matching the current ROI.

        Pads with mid-grey if the ROI extends beyond the reference image bounds.
        """
        ref = self._ref_image
        ref_h, ref_w = ref.shape
        x0, y0 = self._offset_x, self._offset_y
        x1, y1 = x0 + self._width, y0 + self._height

        x0c, y0c = min(x0, ref_w), min(y0, ref_h)
        x1c, y1c = min(x1, ref_w), min(y1, ref_h)

        crop = ref[y0c:y1c, x0c:x1c]

        out_h = y1 - y0
        out_w = x1 - x0
        if crop.shape == (out_h, out_w):
            return crop

        padded = np.full((out_h, out_w), 127.0, dtype=np.float32)
        padded[: crop.shape[0], : crop.shape[1]] = crop
        return padded

    @staticmethod
    def _make_synthetic_image(h: int, w: int) -> np.ndarray:
        """Smooth radial gradient as a fallback reference when no image is provided."""
        cy, cx = h / 2.0, w / 2.0
        y = np.linspace(0, h - 1, h, dtype=np.float32)
        x = np.linspace(0, w - 1, w, dtype=np.float32)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        r_max = np.sqrt(cx**2 + cy**2)
        img = (1.0 - r / r_max) * 200.0 + 20.0
        return img.astype(np.float32)
