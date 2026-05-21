"""
Basler camera driver for LabHub using pypylon (Basler pylon SDK).

Supports USB3 Vision and GigE Vision cameras. Selects by serial number or
falls back to the first available device.

Device hierarchy::

    camera              ← root Device
    (no children)

Configuration (config.yaml)::

    - id: basler_01
      driver: basler.camera
      serial_number: null       # null = first available camera
      polling_interval: 2000

Requires pypylon::

    pip install pypylon

Notes on SFNC compatibility:
  - ExposureTime / Gain / AcquisitionFrameRate require SFNC ≥ 2.x (USB3, newer GigE).
  - Very old GigE cameras (SFNC 1.x) use ExposureTimeAbs / GainRaw — override
    the relevant property getters/setters for those models if needed.
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


def _array_to_b64png(arr: np.ndarray) -> str:
    """Encode a uint8 numpy array (H×W or H×W×3) as a base64-encoded PNG string."""
    if arr.ndim == 2:
        img = Image.fromarray(arr, mode="L")
    else:
        img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


@api_device()
class camera(Device):
    """
    Basler camera (pypylon / Basler pylon SDK).

    Properties cover the most useful acquisition parameters (exposure, gain,
    ROI, trigger, frame rate).  The ``live`` data source streams JPEG/PNG
    frames suitable for display in the GUI.  The ``snap`` command returns
    raw pixel data as a nested list for scripting.
    """

    config_template = {
        "serial_number": None,   # null → first available camera
        "polling_interval": 2000,
    }

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)
        self._camera = None
        self._converter = None   # pylon.ImageFormatConverter → Mono8

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        from pypylon import pylon

        try:
            factory = pylon.TlFactory.GetInstance()
            serial = self.options.get("serial_number")

            if serial:
                di = pylon.DeviceInfo()
                di.SetSerialNumber(str(serial))
                device = factory.CreateDevice(di)
            else:
                device = factory.CreateFirstDevice()

            self._camera = pylon.InstantCamera(device)
            self._camera.Open()

            # Converter: outputs Mono8 regardless of native pixel format.
            # Handles Bayer, 10-/12-bit packed, etc. transparently.
            self._converter = pylon.ImageFormatConverter()
            self._converter.OutputPixelFormat = pylon.PixelType_Mono8
            self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            info = self._camera.GetDeviceInfo()
            logger.info(
                "%s: connected to %s (S/N %s)",
                self.id,
                info.GetModelName(),
                info.GetSerialNumber(),
            )
            return True

        except Exception as exc:
            logger.error("%s: connect() failed: %s", self.id, exc)
            self._camera = None
            self._converter = None
            return False

    def disconnect(self) -> bool:
        if self._camera is not None:
            try:
                if self._camera.IsGrabbing():
                    self._camera.StopGrabbing()
                self._camera.Close()
            except Exception as exc:
                logger.warning("%s: disconnect error: %s", self.id, exc)
            finally:
                self._camera = None
                self._converter = None
        return True

    # ------------------------------------------------------------------
    # Read-only identification
    # ------------------------------------------------------------------

    @api_property(doc="Camera model name")
    def model(self) -> str:
        return self._camera.GetDeviceInfo().GetModelName()

    @api_property(doc="Camera serial number")
    def serial_number(self) -> str:
        return self._camera.GetDeviceInfo().GetSerialNumber()

    @api_property(unit="°C", doc="Device temperature (not available on all models)")
    def temperature(self) -> float:
        try:
            return float(self._camera.DeviceTemperature.Value)
        except Exception:
            return float("nan")

    # ------------------------------------------------------------------
    # Acquisition parameters
    # ------------------------------------------------------------------

    @api_property(min=10.0, max=10_000_000.0, unit="µs", doc="Exposure time")
    def exposure_time(self) -> float:
        return float(self._camera.ExposureTime.Value)

    @exposure_time.setter
    def exposure_time(self, v: float) -> None:
        self._camera.ExposureTime.Value = float(v)

    @api_property(min=0.0, max=48.0, unit="dB", doc="Analog gain (SFNC ≥ 2.x; max depends on camera)")
    def gain(self) -> float:
        return float(self._camera.Gain.Value)

    @gain.setter
    def gain(self, v: float) -> None:
        self._camera.Gain.Value = float(v)

    @api_property(
        choices=["Mono8", "Mono12", "Mono16", "BayerRG8", "BayerRG12", "RGB8Packed"],
        doc="Pixel format (sensor output; available choices depend on camera model)",
    )
    def pixel_format(self) -> str:
        return str(self._camera.PixelFormat.Value)

    @pixel_format.setter
    def pixel_format(self, v: str) -> None:
        self._camera.PixelFormat.Value = v

    # ------------------------------------------------------------------
    # Region of interest
    # ------------------------------------------------------------------

    @api_property(min=1, doc="ROI width in pixels")
    def width(self) -> int:
        return int(self._camera.Width.Value)

    @api_property(min=1, doc="ROI height in pixels")
    def height(self) -> int:
        return int(self._camera.Height.Value)

    @api_property(min=0, doc="ROI horizontal offset from sensor origin")
    def offset_x(self) -> int:
        return int(self._camera.OffsetX.Value)

    @api_property(min=0, doc="ROI vertical offset from sensor origin")
    def offset_y(self) -> int:
        return int(self._camera.OffsetY.Value)

    # ------------------------------------------------------------------
    # Frame rate
    # ------------------------------------------------------------------

    @api_property(doc="Enable explicit acquisition frame rate limit")
    def frame_rate_enable(self) -> bool:
        return bool(self._camera.AcquisitionFrameRateEnable.Value)

    @frame_rate_enable.setter
    def frame_rate_enable(self, v: bool) -> None:
        self._camera.AcquisitionFrameRateEnable.Value = v

    @api_property(min=0.1, max=2000.0, unit="Hz", doc="Target frame rate (active when frame_rate_enable=True)")
    def frame_rate(self) -> float:
        return float(self._camera.AcquisitionFrameRate.Value)

    @frame_rate.setter
    def frame_rate(self, v: float) -> None:
        self._camera.AcquisitionFrameRate.Value = float(v)

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------

    @api_property(
        choices=["Off", "On"],
        doc="Trigger mode — Off: free-run; On: wait for trigger_source",
    )
    def trigger_mode(self) -> str:
        return str(self._camera.TriggerMode.Value)

    @trigger_mode.setter
    def trigger_mode(self, v: str) -> None:
        self._camera.TriggerMode.Value = v

    @api_property(
        choices=["Software", "Line1", "Line2", "Line3", "Line4"],
        doc="Active trigger source (only relevant when trigger_mode=On)",
    )
    def trigger_source(self) -> str:
        return str(self._camera.TriggerSource.Value)

    @trigger_source.setter
    def trigger_source(self, v: str) -> None:
        self._camera.TriggerSource.Value = v

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @api_command(
        doc="Grab a single frame and return pixel data as a 2D list (rows × cols, uint8). "
            "Works while the live stream is active. Large images are slow over JSON — "
            "use the live stream for display."
    )
    def snap(self) -> List[List[int]]:
        from pypylon import pylon

        if self._camera.IsGrabbing():
            # Live stream is running — retrieve the latest buffered frame
            grab = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        else:
            grab = self._camera.GrabOne(5000, pylon.TimeoutHandling_ThrowException)

        try:
            if not grab.GrabSucceeded():
                raise RuntimeError(
                    f"Grab failed: {grab.ErrorCode} {grab.ErrorDescription}"
                )
            converted = self._converter.Convert(grab)
            return converted.Array.copy().tolist()
        finally:
            grab.Release()

    @api_command(
        doc="Send a software trigger pulse. Requires trigger_mode=On and trigger_source=Software."
    )
    def execute_software_trigger(self) -> str:
        self._camera.TriggerSoftware.Execute()
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
        cam = self._camera
        # Align to hardware increments
        x_inc = int(cam.OffsetX.Inc)
        y_inc = int(cam.OffsetY.Inc)
        w_inc = int(cam.Width.Inc)
        h_inc = int(cam.Height.Inc)
        w = max(int(cam.Width.Min), (width // w_inc) * w_inc)
        h = max(int(cam.Height.Min), (height // h_inc) * h_inc)
        x = (x // x_inc) * x_inc
        y = (y // y_inc) * y_inc
        # Reset offsets before resizing (avoids out-of-bounds intermediate states)
        cam.OffsetX.Value = 0
        cam.OffsetY.Value = 0
        cam.Width.Value = w
        cam.Height.Value = h
        cam.OffsetX.Value = min(x, int(cam.OffsetX.Max))
        cam.OffsetY.Value = min(y, int(cam.OffsetY.Max))
        return (
            f"ROI: x={cam.OffsetX.Value} y={cam.OffsetY.Value} "
            f"w={cam.Width.Value} h={cam.Height.Value}"
        )

    @api_command(doc="Reset ROI to full sensor resolution.")
    def reset_roi(self) -> str:
        cam = self._camera
        cam.OffsetX.Value = 0
        cam.OffsetY.Value = 0
        cam.Width.Value = cam.Width.Max
        cam.Height.Value = cam.Height.Max
        return f"ROI reset to full sensor: {cam.Width.Value}×{cam.Height.Value}"

    @api_command(
        doc="Run one-shot automatic exposure and return the resulting exposure time (µs). "
            "Blocks until the camera reports convergence (≤ 5 s)."
    )
    def auto_expose_once(self) -> float:
        cam = self._camera
        cam.ExposureAuto.Value = "Once"
        deadline = time.monotonic() + 5.0
        while cam.ExposureAuto.Value != "Off" and time.monotonic() < deadline:
            time.sleep(0.05)
        return float(cam.ExposureTime.Value)

    @api_command(
        doc="Run one-shot automatic gain and return the resulting gain (dB). "
            "Blocks until the camera reports convergence (≤ 5 s)."
    )
    def auto_gain_once(self) -> float:
        cam = self._camera
        cam.GainAuto.Value = "Once"
        deadline = time.monotonic() + 5.0
        while cam.GainAuto.Value != "Off" and time.monotonic() < deadline:
            time.sleep(0.05)
        return float(cam.Gain.Value)

    # ------------------------------------------------------------------
    # Helpers (internal)
    # ------------------------------------------------------------------

    def _grab_one_mono8(self) -> np.ndarray:
        """Retrieve the next available frame and return a Mono8 ndarray. Blocking."""
        from pypylon import pylon

        grab = self._camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        try:
            if not grab.GrabSucceeded():
                raise RuntimeError(
                    f"Grab failed: {grab.ErrorCode} {grab.ErrorDescription}"
                )
            converted = self._converter.Convert(grab)
            return converted.Array.copy()
        finally:
            grab.Release()

    # ------------------------------------------------------------------
    # Data source: live image stream
    # ------------------------------------------------------------------

    @api_data("live", kind="image", doc="Continuous live image stream (Mono8, base64-PNG frames)")
    async def live(self) -> AsyncIterator[Frame]:
        """Continuously grab frames and yield them as base64-encoded PNG images.

        Uses GrabStrategy_LatestImageOnly so slow consumers never accumulate a
        queue of stale frames — each yield delivers the most recent image.

        Stops automatically when all subscribers disconnect.
        """
        from pypylon import pylon

        loop = asyncio.get_running_loop()
        await self._run_blocking_in_thread(
            self._camera.StartGrabbing, pylon.GrabStrategy_LatestImageOnly
        )
        logger.debug("%s: live stream started", self.id)
        try:
            while True:
                arr = await self._run_blocking_in_thread(self._grab_one_mono8)
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}
        finally:
            try:
                self._camera.StopGrabbing()
            except Exception:
                pass
            logger.debug("%s: live stream stopped", self.id)
