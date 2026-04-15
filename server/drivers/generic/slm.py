"""
Support for generic SLM device (external monitor)
"""

from __future__ import annotations
import asyncio
import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Dict, Any, Optional, TYPE_CHECKING

import numpy as np
import tkinter as tk
from PIL import Image, ImageTk

try:
    from screeninfo import get_monitors

    _HAS_SCREENINFO = True
except ImportError:
    _HAS_SCREENINFO = False

from ..base import Device, ChildDevice, api_device, api_command, api_property, api_data, Frame

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Child device: grating
# ---------------------------------------------------------------------------

@api_device()
class _grating(ChildDevice):
    """
    Grating sub-device — controls spacing and angle of a sinusoidal phase grating.

    Call show_grating() to generate and push the pattern to the SLM display.
    The circular mask (centre and radius) is taken from the sibling mask sub-device
    when use_mask=True.
    """

    def __init__(self, child_id: str, parent: Device):
        super().__init__(child_id, parent)
        self._spacing: float = 20.0  # defaults overridden in connect()
        self._angle: float = 0.0

    def connect(self) -> bool:
        opts = self._parent.options
        self._spacing = float(opts.get("grating_spacing", 20.0))
        self._angle = float(opts.get("grating_angle", 0.0))
        return True

    # --- Properties ---

    @api_property(min=1.0, max=4000.0, step=1.0, unit="px")
    def spacing(self) -> float:
        """Grating period in pixels (pixels per full 0–2π phase cycle)."""
        return self._spacing

    @spacing.setter
    def spacing(self, value: float) -> None:
        self._spacing = value

    @api_property(min=-180.0, max=180.0, step=0.5, unit="°")
    def angle(self) -> float:
        """
        Grating angle in degrees.
        0° → vertical fringes (phase varies along X).
        90° → horizontal fringes (phase varies along Y).
        """
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        self._angle = value

    # --- Commands ---

    @api_command()
    async def show_grating(self, use_mask: bool = True) -> None:
        """
        Generate and display a sinusoidal grating on the SLM.

        use_mask : if True, zero pixels outside the circular mask defined
                   by the sibling mask sub-device.  Set to False for a
                   full-frame grating regardless of mask settings.
        """
        root = self._parent  # slm root instance
        if root._monitor is None:
            raise RuntimeError("SLM not connected — cannot generate pattern")

        w = root._monitor["width"]
        h = root._monitor["height"]

        # Read mask parameters from sibling child, or disable mask
        mask_dev = root.children.get("mask")
        if use_mask and mask_dev is not None:
            cx, cy, r = mask_dev.cx, mask_dev.cy, mask_dev.r
        else:
            cx, cy, r = -1.0, -1.0, -1.0

        # Grating generation is CPU-bound: run on default thread pool
        loop = asyncio.get_running_loop()
        arr = await loop.run_in_executor(
            None, _generate_grating, w, h, self._spacing, self._angle, cx, cy, r
        )

        # Display must happen on the dedicated tkinter thread
        await root._run_blocking_in_thread(root._display, arr)


# ---------------------------------------------------------------------------
# Child device: mask
# ---------------------------------------------------------------------------

@api_device()
class _mask(ChildDevice):
    """
    Mask sub-device — defines a circular aperture applied by show_grating().

    Set r = -1 to disable masking (full frame).
    Set cx = -1 or cy = -1 to use the monitor centre for that coordinate.
    """

    def __init__(self, child_id: str, parent: Device):
        super().__init__(child_id, parent)
        self._cx: float = -1.0  # defaults overridden in connect()
        self._cy: float = -1.0
        self._r: float = -1.0

    def connect(self) -> bool:
        opts = self._parent.options
        self._cx = float(opts.get("mask_cx", -1.0))
        self._cy = float(opts.get("mask_cy", -1.0))
        self._r = float(opts.get("mask_r", -1.0))
        return True

    # --- Properties ---

    @api_property(min=-1.0, unit="px")
    def cx(self) -> float:
        """Mask centre X in pixels.  -1 → use monitor centre."""
        return self._cx

    @cx.setter
    def cx(self, value: float) -> None:
        self._cx = value

    @api_property(min=-1.0, unit="px")
    def cy(self) -> float:
        """Mask centre Y in pixels.  -1 → use monitor centre."""
        return self._cy

    @cy.setter
    def cy(self, value: float) -> None:
        self._cy = value

    @api_property(min=-1.0, unit="px")
    def r(self) -> float:
        """Mask radius in pixels.  -1 → no mask, full frame used."""
        return self._r

    @r.setter
    def r(self, value: float) -> None:
        self._r = value


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
    grating : spacing + angle + show_grating command
    mask    : circular aperture (cx, cy, r) applied by show_grating
    """

    # Single-threaded executor: all tkinter calls must originate from one OS thread.
    # Class-level because tkinter is process-wide — only one Tk() per process.
    _TK_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slm_tk")

    config_template = {
        "polling_interval": 1000,
        "monitor_index": None,      # None → auto-select first non-primary monitor
        "grating_spacing": 20.0,
        "grating_angle": 0.0,
        "mask_cx": -1.0,
        "mask_cy": -1.0,
        "mask_r": -1.0,
    }

    # Declare child devices — auto-discovered and instantiated after connect()
    grating = _grating.as_child()
    mask = _mask.as_child()

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        super().__init__(dev_id, options, manager)

        self._monitor_index: int | None = options.get("monitor_index", None)

        # Tkinter state (all access must go through _TK_EXEC)
        self._monitor: dict | None = None
        self._root: tk.Tk | None = None
        self._label: tk.Label | None = None
        self._tk_image: ImageTk.PhotoImage | None = None

        # Last pattern sent — polled by the current_pattern data source
        self._current_pattern: np.ndarray | None = None

    # --- Thread routing ------------------------------------------------------
    # Route every blocking call through the dedicated single-threaded executor.
    # This guarantees that Tk(), update(), destroy() etc. always execute on the
    # same OS thread.  Property polls and sync commands all go through here.

    async def _run_blocking_in_thread(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._TK_EXEC, lambda: fn(*args, **kwargs))

    # --- Lifecycle -----------------------------------------------------------

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
        """Sync so the base class routes it through _run_blocking_in_thread → tk thread."""
        self.close()
        return True

    # --- Properties: monitor info --------------------------------------------

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
        return self._root is not None

    # --- Commands ------------------------------------------------------------

    @api_command()
    def show(self, pattern: list) -> None:
        """
        Display a grayscale pattern on the SLM.

        pattern : nested list (rows × cols) of numeric values 0–255.
                  Clipped to uint8 and resized to the monitor resolution if needed.
        """
        arr = np.asarray(pattern, dtype=float)
        arr = _validate_pattern(arr)
        self._display(arr)

    @api_command()
    def close(self) -> None:
        """Close the SLM display window."""
        if self._root is not None:
            self._root.destroy()
            self._root = None
            self._label = None
            self._tk_image = None

    # --- Data source: live pattern preview -----------------------------------

    @api_data("current_pattern", kind="image")
    async def current_pattern(self) -> AsyncIterator[Frame]:
        """
        Stream the current SLM pattern as a base64-encoded PNG image.

        Yields one frame per poll cycle whenever a pattern has been loaded.
        Rate is controlled by the caller (rate slider in the GUI).
        Press 'Once' to grab a snapshot; press 'Start' to stream continuously.
        """
        loop = asyncio.get_running_loop()
        while True:
            if self._current_pattern is not None:
                arr = self._current_pattern.copy()  # snapshot before encoding
                b64 = await loop.run_in_executor(None, _array_to_b64png, arr)
                yield {"image_b64": b64}
            # Brief pause before next check; DataSource runner adds its own rate-limiting.
            await asyncio.sleep(0.1)

    # --- Internal helpers ----------------------------------------------------

    def _display(self, arr: np.ndarray) -> None:
        """Store pattern and push to tkinter window (create or update)."""
        self._current_pattern = arr
        img = self._to_pil(arr)
        if self._root is None:
            self._open_window(img)
        else:
            self._update_image(img)

    def _to_pil(self, pattern: np.ndarray) -> Image.Image:
        """Convert uint8 numpy array to a PIL RGB image sized to the monitor."""
        m = self._monitor
        img = Image.fromarray(pattern, mode="L")
        if img.size != (m["width"], m["height"]):
            img = img.resize((m["width"], m["height"]), Image.LANCZOS)
        return img.convert("RGB")  # tkinter PhotoImage requires RGB

    def _open_window(self, img: Image.Image) -> None:
        m = self._monitor
        self._root = tk.Tk()
        self._root.title("SLM")
        self._root.configure(bg="black")
        self._root.overrideredirect(True)   # no title bar / decorations
        self._root.geometry(f"{m['width']}x{m['height']}+{m['x']}+{m['y']}")
        self._root.attributes("-topmost", True)
        self._root.bind("<Escape>", lambda _: self.close())

        self._tk_image = ImageTk.PhotoImage(img, master=self._root)
        self._label = tk.Label(self._root, image=self._tk_image, bg="black", bd=0)
        self._label.image = self._tk_image  # explicit ref — prevents GC blanking
        self._label.pack()
        self._root.update()

    def _update_image(self, img: Image.Image) -> None:
        self._tk_image = ImageTk.PhotoImage(img, master=self._root)
        self._label.configure(image=self._tk_image)
        self._label.image = self._tk_image  # explicit ref — prevents GC blanking
        self._root.update()


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _validate_pattern(pattern: np.ndarray) -> np.ndarray:
    if pattern.ndim != 2:
        raise ValueError(f"Pattern must be 2D, got shape {pattern.shape}")
    if pattern.dtype != np.uint8:
        pattern = np.clip(pattern, 0, 255).astype(np.uint8)
    return pattern


def _generate_grating(
    width: int,
    height: int,
    spacing: float,
    angle_deg: float,
    mask_cx: float,
    mask_cy: float,
    mask_r: float,
) -> np.ndarray:
    """
    Return a uint8 sinusoidal phase grating (shape: height × width).

    Values 0–255 represent phase 0–2π.
    Pixels outside the circular mask (when mask_r > 0) are set to 0.
    mask_cx / mask_cy < 0 → centred on the frame.
    """
    angle_rad = np.deg2rad(angle_deg)
    xs = np.arange(width, dtype=float)
    ys = np.arange(height, dtype=float)
    X, Y = np.meshgrid(xs, ys)

    proj = X * np.cos(angle_rad) + Y * np.sin(angle_rad)
    pattern = (128 + 127 * np.sin(2 * np.pi * proj / spacing)).astype(np.uint8)

    if mask_r > 0:
        cx = mask_cx if mask_cx >= 0 else width / 2.0
        cy = mask_cy if mask_cy >= 0 else height / 2.0
        outside = (X - cx) ** 2 + (Y - cy) ** 2 > mask_r ** 2
        pattern[outside] = 0

    return pattern


def _array_to_b64png(arr: np.ndarray) -> str:
    """Encode a uint8 2D numpy array as a base64-encoded PNG string."""
    img = Image.fromarray(arr, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Monitor helpers (useful from CLI / debug)
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
    """
    Return the monitor dict to use for the SLM.

    If monitor_index is None, auto-selects the first non-primary monitor.
    Raises RuntimeError if no suitable monitor is found.
    """
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
