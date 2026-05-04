"""
Support for generic SLM device (external monitor)
"""

from __future__ import annotations
import asyncio
import base64
import io
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Dict, Any, Optional, TYPE_CHECKING

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QLabel

try:
    from screeninfo import get_monitors

    _HAS_SCREENINFO = True
except ImportError:
    _HAS_SCREENINFO = False

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


class _SlmWindow(QLabel):
    """Borderless top-level label used to present the SLM pattern."""

    def __init__(self, on_escape=None):
        super().__init__(None)
        self._on_escape = on_escape
        self.setWindowTitle("SLM")
        self.setStyleSheet("background-color: black;")
        self.setAlignment(Qt.AlignCenter)
        self.setScaledContents(True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            if self._on_escape is not None:
                self._on_escape()
            event.accept()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Child device: trap
# ---------------------------------------------------------------------------


@api_device()
class _trap(ChildDevice):
    """
    Trap sub-device — computes and displays the phase pattern for a single optical trap.

    Coordinate system: the pattern rectangle (width × height) is centred at
    (SLM_centre + offset_h, SLM_centre + offset_v).  If the rectangle extends
    beyond the SLM edges it is silently cropped.

    x, y, z are Fourier-plane parameters; the phase is computed over the full
    width × height grid regardless of the aperture size.  The circular aperture
    mask may extend beyond the rectangle — pixels outside it are set to phase_offset.

    max_phase and phase_offset are read from the parent SLM device (config).

    An optional overlay (full SLM resolution, 0–255 → −π…+π phase delta,
    128 = no change) is combined with the embedded frame before display.

    With auto_update=True (default) every property change immediately triggers
    a recompute.  Set auto_update=False and call update() explicitly for
    batch changes.
    """

    def __init__(self, child_id: str, parent: Device):
        super().__init__(child_id, parent)
        self._x: float = 0.0
        self._y: float = 0.0
        self._z: float = 0.0
        self._beam_type: str = "gauss"
        self._aperture_diameter: int = -1  # -1 → min(width, height)
        self._bessel_inner_fraction: float = 0.9
        self._offset_h: int = 0  # horizontal centre offset from SLM centre (px)
        self._offset_v: int = 0  # vertical centre offset from SLM centre (px)
        self._auto_update: bool = True
        self._trap_pattern_arr: np.ndarray | None = None
        self._overlay_arr: np.ndarray | None = None

    async def _run_blocking_in_thread(self, fn):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._parent._QT_EXEC, fn)

    def connect(self) -> bool:
        opts = self._parent.options
        self._x = float(opts.get("trap_x", 0.0))
        self._y = float(opts.get("trap_y", 0.0))
        self._z = float(opts.get("trap_z", 0.0))
        self._beam_type = str(opts.get("beam_type", "gauss"))
        self._aperture_diameter = int(opts.get("aperture_diameter", -1))
        self._bessel_inner_fraction = float(opts.get("bessel_inner_fraction", 0.9))
        self._offset_h = int(opts.get("offset_h", 0))
        self._offset_v = int(opts.get("offset_v", 0))
        self._auto_update = bool(opts.get("auto_update", True))
        return True

    # --- Properties ---

    @api_property(min=-0.5, max=0.5, step=0.001)
    def x(self) -> float:
        """Fourier-plane x coordinate (range −0.5 … 0.5). Maps linearly to lateral trap position."""
        return self._x

    @x.setter
    def x(self, value: float) -> None:
        self._x = value
        if self._auto_update:
            self._do_update()

    @api_property(min=-0.5, max=0.5, step=0.001)
    def y(self) -> float:
        """Fourier-plane y coordinate (range −0.5 … 0.5). Maps linearly to lateral trap position."""
        return self._y

    @y.setter
    def y(self, value: float) -> None:
        self._y = value
        if self._auto_update:
            self._do_update()

    @api_property(min=-1e-2, max=1e-2, step=1e-5)
    def z(self) -> float:
        """Axial offset coefficient (quadratic phase). Typical range ±1×10⁻³; shifts focus along optical axis."""
        return self._z

    @z.setter
    def z(self, value: float) -> None:
        self._z = value
        if self._auto_update:
            self._do_update()

    @api_property(choices=["gauss", "bessel"])
    def beam_type(self) -> str:
        """Beam profile shape: 'gauss' (filled disk aperture) or 'bessel' (annular ring aperture)."""
        return self._beam_type

    @beam_type.setter
    def beam_type(self, value: str) -> None:
        self._beam_type = value
        if self._auto_update:
            self._do_update()

    @api_property(min=-1, step=1, unit="px")
    def aperture_diameter(self) -> int:
        """
        Circular aperture diameter in pixels. −1 → min(width, height).
        May be larger than the pattern region — the mask is simply cropped at the boundary.
        """
        return self._aperture_diameter

    @aperture_diameter.setter
    def aperture_diameter(self, value: int) -> None:
        self._aperture_diameter = int(value)
        if self._auto_update:
            self._do_update()

    @api_property(min=0.5, max=0.99, step=0.01)
    def bessel_inner_fraction(self) -> float:
        """
        Inner-to-outer radius ratio of the Bessel annulus (only used when beam_type='bessel').
        0.9 → thin ring; the inner hole covers 90 % of the aperture radius.
        """
        return self._bessel_inner_fraction

    @bessel_inner_fraction.setter
    def bessel_inner_fraction(self, value: float) -> None:
        self._bessel_inner_fraction = value
        if self._auto_update:
            self._do_update()

    @api_property(step=1, unit="px")
    def offset_h(self) -> int:
        """
        Horizontal offset of the pattern centre from the SLM monitor centre in pixels.
        Positive → shifts right.  The pattern is cropped silently if it extends beyond the SLM.
        """
        return self._offset_h

    @offset_h.setter
    def offset_h(self, value: int) -> None:
        self._offset_h = int(value)
        if self._auto_update:
            self._do_update()

    @api_property(step=1, unit="px")
    def offset_v(self) -> int:
        """
        Vertical offset of the pattern centre from the SLM monitor centre in pixels.
        Positive → shifts down.  The pattern is cropped silently if it extends beyond the SLM.
        """
        return self._offset_v

    @offset_v.setter
    def offset_v(self, value: int) -> None:
        self._offset_v = int(value)
        if self._auto_update:
            self._do_update()

    @api_property()
    def auto_update(self) -> bool:
        """When True, every property change immediately triggers a recompute and display update."""
        return self._auto_update

    @auto_update.setter
    def auto_update(self, value: bool) -> None:
        self._auto_update = value

    # --- Commands ---

    @api_command()
    def update(self) -> None:
        """Recompute and display the trap pattern from current parameters (ignores auto_update)."""
        self._do_update()

    @api_command()
    def add_overlay(self, pattern: list) -> None:
        """
        Set an overlay pattern and combine it with the trap pattern on the SLM.

        pattern : nested list (rows × cols) of uint8 values 0–255, must match the SLM monitor
                  resolution [height × width].

        Overlay encoding — the full 0–255 range maps to a phase delta of −π … +π:
            128  →  0 (no change, mid-gray)
              0  →  −π
            255  →  +π

        This encoding is independent of max_phase / phase_offset and is directly
        visualisable: a flat mid-gray overlay has no effect on the trap pattern.
        """
        arr = np.asarray(pattern, dtype=float)
        arr = _validate_pattern(arr)
        root = self._parent
        if root._monitor is not None:
            w, h = root._monitor["width"], root._monitor["height"]
            if arr.shape != (h, w):
                raise ValueError(
                    f"Overlay shape {arr.shape} does not match SLM monitor frame ({h}×{w}). "
                    "Overlay must cover the full monitor."
                )
        self._overlay_arr = arr
        self._do_update()

    @api_command()
    def remove_overlay(self) -> None:
        """Remove the overlay and redisplay the pure trap pattern."""
        self._overlay_arr = None
        self._do_update()

    # --- Data sources ---

    @api_data("trap_img", kind="image")
    async def trap_img(self) -> AsyncIterator[Frame]:
        """Stream the computed trap phase pattern (without overlay, without mask) as a PNG image."""
        loop = asyncio.get_running_loop()
        while True:
            if self._trap_pattern_arr is not None:
                arr = self._trap_pattern_arr.copy()
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}
            else:
                yield {"image_b64": None}
            await asyncio.sleep(0.1)

    @api_data("overlay_img", kind="image")
    async def overlay_img(self) -> AsyncIterator[Frame]:
        """Stream the current overlay pattern (128 = no change). Yields nothing when no overlay is set."""
        loop = asyncio.get_running_loop()
        while True:
            if self._overlay_arr is not None:
                arr = self._overlay_arr.copy()
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}
            else:
                yield {"image_b64": None}
            await asyncio.sleep(0.1)

    # --- Internal helpers ---

    def _do_update(self) -> None:
        root = self._parent
        if root._monitor is None:
            return
        slm_w, slm_h = root._monitor["width"], root._monitor["height"]

        pat_w = slm_w
        pat_h = slm_h
        aperture = (
            self._aperture_diameter
            if self._aperture_diameter > 0
            else min(pat_w, pat_h)
        )

        pat = _compute_trap_pattern(
            pat_w,
            pat_h,
            self._x,
            self._y,
            self._z,
            self._beam_type,
            aperture,
            self._bessel_inner_fraction,
            root._max_phase,
            root._phase_offset,
        )
        self._trap_pattern_arr = pat

        # Centre of the pattern rectangle on the SLM
        cx = slm_w // 2 + self._offset_h
        cy = slm_h // 2 + self._offset_v
        x0 = cx - pat_w // 2
        y0 = cy - pat_h // 2

        # Build the full-frame array, then paste the pattern (clipped to monitor bounds)
        frame = np.full((slm_h, slm_w), root._phase_offset, dtype=np.uint8)
        src_x0 = max(0, -x0)
        dst_x0 = max(0, x0)
        src_y0 = max(0, -y0)
        dst_y0 = max(0, y0)
        src_x1 = min(pat_w, slm_w - x0)
        src_y1 = min(pat_h, slm_h - y0)
        if src_x1 > src_x0 and src_y1 > src_y0:
            frame[
                dst_y0 : dst_y0 + (src_y1 - src_y0), dst_x0 : dst_x0 + (src_x1 - src_x0)
            ] = pat[src_y0:src_y1, src_x0:src_x1]

        if self._overlay_arr is not None:
            frame = _combine_patterns(
                frame, self._overlay_arr, root._max_phase, root._phase_offset
            )

        root._display(frame)


# ---------------------------------------------------------------------------
# Child device: mask
# ---------------------------------------------------------------------------


@api_device()
class _mask(ChildDevice):
    """
    Mask sub-device — restricts what region of the SLM frame is shown.

    Independently enables a vertical stripe (columns) and a horizontal stripe (rows).
    Each enabled stripe keeps the underlying pattern + overlay in that band and zeros
    the rest.  When both stripes are enabled their union is shown.
    When neither is enabled the full pattern passes through unchanged.

    The mask is applied in root._display() after overlay combination, so it
    affects everything that reaches the SLM, including raw show() calls.
    """

    def __init__(self, child_id: str, parent: Device):
        super().__init__(child_id, parent)
        self._vertical_show: bool = False
        self._vertical_idx: int = 0
        self._vertical_size: int = 0
        self._horizontal_show: bool = False
        self._horizontal_idx: int = 0
        self._horizontal_size: int = 0

    async def _run_blocking_in_thread(self, fn):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._parent._QT_EXEC, fn)

    def connect(self) -> bool:
        opts = self._parent.options
        self._vertical_show = bool(opts.get("vertical_show", False))
        self._vertical_idx = int(opts.get("vertical_idx", 0))
        self._vertical_size = int(opts.get("vertical_size", 0))
        self._horizontal_show = bool(opts.get("horizontal_show", False))
        self._horizontal_idx = int(opts.get("horizontal_idx", 0))
        self._horizontal_size = int(opts.get("horizontal_size", 0))
        return True

    # --- Properties ---

    @api_property()
    def vertical_show(self) -> bool:
        """Enable the vertical stripe mask (keeps columns vertical_idx … vertical_idx+vertical_size)."""
        return self._vertical_show

    @vertical_show.setter
    def vertical_show(self, value: bool) -> None:
        self._vertical_show = value
        self._parent._redisplay()

    @api_property(min=0, step=1, unit="px")
    def vertical_idx(self) -> int:
        """Start column of the vertical stripe (0 = left edge of SLM)."""
        return self._vertical_idx

    @vertical_idx.setter
    def vertical_idx(self, value: int) -> None:
        self._vertical_idx = int(value)
        self._parent._redisplay()

    @api_property(min=0, step=1, unit="px")
    def vertical_size(self) -> int:
        """Width of the vertical stripe in pixels."""
        return self._vertical_size

    @vertical_size.setter
    def vertical_size(self, value: int) -> None:
        self._vertical_size = int(value)
        self._parent._redisplay()

    @api_property()
    def horizontal_show(self) -> bool:
        """Enable the horizontal stripe mask (keeps rows horizontal_idx … horizontal_idx+horizontal_size)."""
        return self._horizontal_show

    @horizontal_show.setter
    def horizontal_show(self, value: bool) -> None:
        self._horizontal_show = value
        self._parent._redisplay()

    @api_property(min=0, step=1, unit="px")
    def horizontal_idx(self) -> int:
        """Start row of the horizontal stripe (0 = top edge of SLM)."""
        return self._horizontal_idx

    @horizontal_idx.setter
    def horizontal_idx(self, value: int) -> None:
        self._horizontal_idx = int(value)
        self._parent._redisplay()

    @api_property(min=0, step=1, unit="px")
    def horizontal_size(self) -> int:
        """Height of the horizontal stripe in pixels."""
        return self._horizontal_size

    @horizontal_size.setter
    def horizontal_size(self, value: int) -> None:
        self._horizontal_size = int(value)
        self._parent._redisplay()

    @api_data("mask_img", kind="image")
    async def mask_img(self) -> AsyncIterator[Frame]:
        """Stream the computed trap phase pattern (without overlay, without mask) as a PNG image."""
        loop = asyncio.get_running_loop()
        while True:
            arr = (
                np.ones(
                    (self._parent._monitor["height"], self._parent._monitor["width"]),
                    dtype=np.uint8,
                )
                * 255
            )
            masked = self.apply(arr)
            b64 = await loop.run_in_executor(None, _array_to_b64png, masked)
            yield {"image_b64": b64}
            await asyncio.sleep(0.1)

    # --- Internal ---

    def apply(self, pattern: np.ndarray) -> np.ndarray:
        """Return a copy of pattern with everything outside the enabled stripe(s) zeroed."""
        if not self._vertical_show and not self._horizontal_show:
            return pattern
        result = np.zeros_like(pattern)
        if self._vertical_show and self._vertical_size > 0:
            v0 = self._vertical_idx
            v1 = v0 + self._vertical_size
            result[:, v0:v1] = pattern[:, v0:v1]
        if self._horizontal_show and self._horizontal_size > 0:
            h0 = self._horizontal_idx
            h1 = h0 + self._horizontal_size
            result[h0:h1, :] = pattern[h0:h1, :]
        return result


# ---------------------------------------------------------------------------
# Root device
# ---------------------------------------------------------------------------


@api_device()
class slm(Device):
    """
    Driver for a generic SLM device that looks like an external monitor to the OS.
    The SLM appears as a secondary display; patterns are sent by rendering a
    full-screen borderless window on that monitor.

    Sub-devices
    -----------
    trap : phase pattern (position, beam type, aperture, overlay)
    mask : stripe-region visibility mask applied on top of everything
    """

    # Single-threaded executor kept for potential future async use.
    _QT_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slm_qt")

    config_template = {
        "polling_interval": 1000,
        "monitor_index": None,  # None → auto-select first non-primary monitor
        "max_phase": 220,  # uint8 gray value that produces exactly 2π phase shift
        "phase_offset": 0,  # uint8 gray value at zero phase
        "aperture_limit": -1,  # max allowed aperture_diameter in px; -1 → no limit
        # trap defaults
        "trap_x": 0.0,
        "trap_y": 0.0,
        "trap_z": 0.0,
        "beam_type": "gauss",
        "aperture_diameter": -1,
        "bessel_inner_fraction": 0.9,
        "offset_h": 0,
        "offset_v": 0,
        "auto_update": True,
        # mask defaults
        "vertical_show": False,
        "vertical_idx": 0,
        "vertical_size": 0,
        "horizontal_show": False,
        "horizontal_idx": 0,
        "horizontal_size": 0,
    }

    trap = _trap.as_child()
    mask = _mask.as_child()

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)

        self._monitor_index: int | None = options.get("monitor_index", None)
        self._max_phase: int = int(options.get("max_phase", 220))
        self._phase_offset: int = int(options.get("phase_offset", 0))

        # Qt state
        self._monitor: dict | None = None
        self._app: QApplication | None = None
        self._window: _SlmWindow | None = None
        self._pixmap: QPixmap | None = None

        # _raw_pattern: pre-mask frame; _current_pattern: post-mask (streamed to GUI)
        self._raw_pattern: np.ndarray | None = None
        self._current_pattern: np.ndarray | None = None

    async def _run_blocking_in_thread(self, fn):
        """Run fn on the dedicated Qt thread (single-threaded executor ensures Qt thread affinity)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._QT_EXEC, fn)

    # --- Lifecycle ---

    def connect(self) -> bool:
        try:
            self._monitor = _pick_slm_monitor(self._monitor_index)
        except RuntimeError as e:
            logger.error(f"SLM '{self.id}': {e}")
            return False
        logger.info(
            f"SLM '{self.id}': monitor [{self._monitor['index']}] "
            f"'{self._monitor['name']}' "
            f"{self._monitor['width']}×{self._monitor['height']} "
            f"at offset ({self._monitor['x']}, {self._monitor['y']})"
        )
        return True

    def disconnect(self) -> bool:
        self._QT_EXEC.submit(self._close_window).result()
        return True

    # --- Read-only properties ---

    @api_property()
    def monitor_name(self) -> str:
        """Name of the SLM monitor as reported by the OS."""
        return self._monitor["name"] if self._monitor else ""

    @api_property()
    def monitor_resolution(self) -> list:
        """[width, height] of the SLM monitor in pixels."""
        if self._monitor is None:
            return [0, 0]
        return [self._monitor["width"], self._monitor["height"]]

    @api_property()
    def is_displaying(self) -> bool:
        """True when the SLM display window is currently open."""
        return self._window is not None

    @is_displaying.setter
    def is_displaying(self, value: bool) -> None:
        if value:
            self._redisplay()
        else:
            self._close_window()

    @api_property()
    def max_phase(self) -> int:
        """uint8 gray value that maps to 2π phase shift on this SLM (set in config)."""
        return self._max_phase

    @api_property()
    def phase_offset(self) -> int:
        """uint8 gray value that maps to 0 phase on this SLM (set in config)."""
        return self._phase_offset

    # --- Commands ---

    @api_command()
    def show(self, pattern: list) -> None:
        """
        Display a raw grayscale pattern on the SLM (bypasses trap computation).
        The mask child is still applied.

        pattern : nested list (rows × cols) of numeric values 0–255.
        """
        arr = np.asarray(pattern, dtype=float)
        arr = _validate_pattern(arr)
        self._display(arr)

    # --- Data source: live pattern preview ---

    @api_data("current_img", kind="image")
    async def current_img(self) -> AsyncIterator[Frame]:
        """Stream the pattern currently shown on the SLM (after overlay and mask) as PNG."""
        loop = asyncio.get_running_loop()
        while True:
            if self._current_pattern is not None:
                arr = self._current_pattern.copy()
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}
            else:
                yield {"image_b64": None}
            await asyncio.sleep(0.1)

    # --- Internal helpers ---

    def _ensure_app(self) -> QApplication:
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
        self._app = app
        return app

    def _process_qt_events(self) -> None:
        self._ensure_app().processEvents()

    def _display(self, arr: np.ndarray) -> None:
        """Store pre-mask frame, apply mask child, push to Qt window."""
        self._raw_pattern = arr
        mask_dev = self.children.get("mask")
        displayed = mask_dev.apply(arr) if mask_dev is not None else arr
        self._current_pattern = displayed
        img = self._to_pil(displayed)
        if self._window is None:
            self._open_window(img)
        else:
            self._update_image(img)

    def _redisplay(self) -> None:
        """Re-apply the mask to the last computed frame (called when mask params change)."""
        if self._raw_pattern is not None:
            self._display(self._raw_pattern)

    def _to_pil(self, pattern: np.ndarray) -> Image.Image:
        m = self._monitor
        img = Image.fromarray(pattern, mode="L")
        if img.size != (m["width"], m["height"]):
            img = img.resize((m["width"], m["height"]), Image.LANCZOS)
        return img.convert("RGB")

    def _pil_to_qpixmap(self, img: Image.Image) -> QPixmap:
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    def _close_window(self) -> None:
        if self._window is not None:
            import threading
            from PySide6.QtCore import QThread
            caller = threading.current_thread().name
            same = QThread.currentThread() is self._window.thread()
            logger.info(f"_close_window: caller={caller}, same Qt thread={same}")
            self._window.hide()
            self._window.deleteLater()
            self._window = None
            self._pixmap = None
            self._process_qt_events()

    def _open_window(self, img: Image.Image) -> None:
        self._ensure_app()
        m = self._monitor
        self._window = _SlmWindow(on_escape=self._close_window)
        self._window.setGeometry(m["x"], m["y"], m["width"], m["height"])
        self._window.setFocusPolicy(Qt.StrongFocus)
        self._pixmap = self._pil_to_qpixmap(img)
        self._window.setPixmap(self._pixmap)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._window.setFocus()
        self._process_qt_events()

    def _update_image(self, img: Image.Image) -> None:
        self._pixmap = self._pil_to_qpixmap(img)
        self._window.setPixmap(self._pixmap)
        self._window.repaint()
        self._process_qt_events()


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _validate_pattern(pattern: np.ndarray) -> np.ndarray:
    if pattern.ndim != 2:
        raise ValueError(f"Pattern must be 2D, got shape {pattern.shape}")
    if pattern.dtype != np.uint8:
        pattern = np.clip(pattern, 0, 255).astype(np.uint8)
    return pattern


def _compute_trap_pattern(
    width: int,
    height: int,
    x: float,
    y: float,
    z: float,
    beam_type: str,
    aperture_diameter: int,
    bessel_inner_fraction: float,
    max_phase: int,
    phase_offset: int,
) -> np.ndarray:
    """
    Return a uint8 phase pattern (shape: height × width) for a single optical trap.

    Coordinate origin is the rectangle centre.  The circular aperture is centred there too
    and may extend beyond the rectangle — pixels outside the mask are set to phase_offset.
    """
    x_coords = np.arange(width, dtype=float) - width // 2
    y_coords = np.arange(height, dtype=float) - height // 2
    X, Y = np.meshgrid(x_coords, y_coords)
    Z = X**2 + Y**2
    R = np.sqrt(Z)

    mask = _create_mask(R, aperture_diameter, beam_type, bessel_inner_fraction)
    phase = _calc_phase(x, y, z, X, Y, Z)
    return _phase_to_grayscale(mask * phase, max_phase, phase_offset)


def _calc_phase(
    x: float,
    y: float,
    z: float,
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
) -> np.ndarray:
    """Phase mask for a single trap at Fourier-plane coords (x, y) and axial offset z."""
    return np.angle(np.exp(1j * (2 * math.pi * (x * X + y * Y + z * Z))))


def _create_mask(
    R: np.ndarray,
    aperture_diameter: int,
    beam_type: str,
    bessel_inner_fraction: float,
) -> np.ndarray:
    """Circular aperture mask: solid disk for 'gauss', thin annulus for 'bessel'."""
    outer_r = aperture_diameter / 2.0
    mask = np.zeros(R.shape)
    if beam_type == "bessel":
        inner_r = outer_r * bessel_inner_fraction
        mask[(R <= outer_r) & (R >= inner_r)] = 1.0
    else:
        mask[R <= outer_r] = 1.0
    return mask


def _phase_to_grayscale(
    phase: np.ndarray, max_phase: int, phase_offset: int
) -> np.ndarray:
    """Convert a phase array (radians, any range) to uint8 gray levels."""
    p = phase % (2 * math.pi)
    p = p / (2 * math.pi) * max_phase + phase_offset
    return np.clip(p, 0, 255).astype(np.uint8)


def _combine_patterns(
    trap: np.ndarray,
    overlay: np.ndarray,
    max_phase: int,
    phase_offset: int,
) -> np.ndarray:
    """
    Add trap and overlay in phase space and re-encode as uint8.

    Trap is decoded from SLM encoding (max_phase / phase_offset).
    Overlay uses a fixed 0–255 → −π … +π mapping (128 = no change).
    """
    trap_phase = (trap.astype(np.float64) - phase_offset) * (2 * math.pi / max_phase)
    overlay_phase = (overlay.astype(np.float64) / 255.0 * 2 - 1) * math.pi
    return _phase_to_grayscale(trap_phase + overlay_phase, max_phase, phase_offset)


def _array_to_b64png(arr: np.ndarray) -> str:
    """Encode a uint8 2D numpy array as a base64-encoded PNG string."""
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Monitor helpers
# ---------------------------------------------------------------------------


def list_monitors() -> list[dict]:
    """
    Return a list of connected monitors with their geometry.

    Each entry: {"index": int, "x": int, "y": int,
                 "width": int, "height": int, "name": str, "is_primary": bool}
    """
    if not _HAS_SCREENINFO:
        raise RuntimeError("screeninfo is not installed. Run: pip install screeninfo")
    monitors = []
    for i, m in enumerate(get_monitors()):
        monitors.append(
            {
                "index": i,
                "x": m.x,
                "y": m.y,
                "width": m.width,
                "height": m.height,
                "name": getattr(m, "name", f"monitor_{i}"),
                "is_primary": getattr(m, "is_primary", i == 0),
            }
        )
    return monitors


def print_monitors() -> None:
    """Print all detected monitors — useful for finding which index is the SLM."""
    for m in list_monitors():
        tag = " [PRIMARY]" if m["is_primary"] else ""
        print(
            f"  [{m['index']}] {m['name']}{tag}  "
            f"{m['width']}×{m['height']}  offset ({m['x']}, {m['y']})"
        )


def _pick_slm_monitor(monitor_index: int | None) -> dict:
    monitors = list_monitors()
    if monitor_index is not None:
        matches = [m for m in monitors if m["index"] == monitor_index]
        if not matches:
            raise RuntimeError(
                f"Monitor index {monitor_index} not found. "
                f"Available indices: {[m['index'] for m in monitors]}"
            )
        return matches[0]
    non_primary = [m for m in monitors if not m["is_primary"]]
    if non_primary:
        return non_primary[0]
    raise RuntimeError(
        "No non-primary monitor found for the SLM. "
        "Connect the SLM and check with slm.print_monitors(), "
        "then set monitor_index explicitly in config.yaml."
    )
