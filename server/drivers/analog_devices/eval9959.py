"""Analog Devices EVAL-AD9959 DDS Evaluation Board Driver"""

from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from ..base import Device, api_device, api_command, api_property
from .adi_bridge import AdiClockEvalBridge

if TYPE_CHECKING:
    from ...device_manager import DeviceManager

logger = logging.getLogger(__name__)

# Path to 32-bit bridge executable for DLL interop
BRIDGE_EXE = str(Path(__file__).with_name("adiclockeval_spi_bridge.exe"))

# Channel selection masks
CHANNELS = {0: 0x10, 1: 0x20, 2: 0x40, 3: 0x80}


@api_device()
class eval9959(Device):
    """
    Analog Devices EVAL-AD9959 DDS evaluation board.

    Uses subprocess bridge to communicate with 32-bit AD DLL from 64-bit Python.
    Bridge communicates via stdin/stdout, serialized by base class _lock.
    """

    def __init__(
        self,
        dev_id: str,
        options: Dict[str, Any],
        manager: Optional[DeviceManager] = None,
    ):
        """
        Initialize EVAL-AD9959 driver.

        Config options:
            dll_folder: Path to AD evaluation software DLLs
            vid: USB vendor ID (default: 0x0456)
            pid: USB product ID (default: 0xEE25)
            ref_clk_hz: Reference clock frequency (default: 40 MHz)
            sys_clk_hz: System clock frequency (default: 400 MHz)
        """
        super().__init__(dev_id, options, manager)

        self.dll_folder = options.get(
            "dll_folder",
            r"C:\Program Files (x86)\Analog Devices\AD9958_59 Evaluation Software",
        )
        self.vid = options.get("vid", 0x0456)
        self.pid = options.get("pid", 0xEE25)
        self._ref_clk_hz = options.get("ref_clk_hz", 40_000_000)

        self.device_index = 0  # Support only first device for now
        self.bridge = None

    # --- Lifecycle ---

    def connect(self) -> bool:
        """
        Connect to EVAL-AD9959 device.

        Starts bridge subprocess and searches for USB device.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Initialize bridge subprocess
            self.bridge = AdiClockEvalBridge(BRIDGE_EXE, self.dll_folder, timeout=10.0)
            time.sleep(0.1)
            self.bridge.start()

            # Search for hardware
            self.bridge.find_hardware(1, [(self.vid, self.pid)])

            # Verify correct device is connected
            if (
                self.bridge.get_vendor_id() != self.vid
                or self.bridge.get_product_id() != self.pid
            ):
                logger.error(
                    f"{self.id}: Device not found or wrong VID/PID. "
                    f"Expected {hex(self.vid)}:{hex(self.pid)}, "
                    f"got {hex(self.bridge.get_vendor_id())}:{hex(self.bridge.get_product_id())}"
                )
                return False

            logger.info(
                f"{self.id}: Connected to EVAL-AD9959 "
                f"(VID:{hex(self.vid)} PID:{hex(self.pid)})"
            )
            return True
        except Exception as e:
            logger.error(f"{self.id}: Failed to connect to EVAL-AD9959: {e}")
            return False

    def disconnect(self) -> bool:
        """
        Disconnect from device.

        Closes bridge subprocess.

        Returns:
            True if disconnect successful, False otherwise
        """
        if not self.bridge:
            return True

        try:
            self.bridge.close()
            return True
        except Exception as e:
            logger.error(f"{self.id}: Error during disconnect: {e}")
            return False

    # --- Low-level helpers ---

    def io_update(self):
        """Trigger I/O update to apply pending register changes"""
        command = 3  # Maps to opcode 0x0C
        self.bridge.set_port_value(self.device_index, command, 0x10)
        self.bridge.set_port_value(self.device_index, command, 0x00)

    def select_channel(self, channel_mask: int):
        """Select channel(s) for subsequent operations via channel mask"""
        self.bridge.spi_write_addr_payload(self.device_index, 0x00, [channel_mask])

    def read_register(self, reg_addr: int, num_bytes: int) -> bytes:
        """
        Read from a register.

        Args:
            reg_addr: Register address (0x00-0x7F)
            num_bytes: Number of bytes to read

        Returns:
            Bytes read from the register
        """
        data = self.bridge.spi_read_addr(self.device_index, reg_addr, num_bytes)
        return data

    # --- Properties ---

    @api_property(step=1, unit="Hz")
    def ref_clk(self) -> int:
        """Reference clock [Hz] (input to eval board from external source)"""
        return self._ref_clk_hz

    @ref_clk.setter
    def ref_clk(self, value: int):
        # option 1: when changing ref clock, try to keep sys clock the same
        prev_sys_clk = self.sys_clk
        self._ref_clk_hz = value
        self.sys_clk = prev_sys_clk

        # option 2: when changing ref clock, keep multiplier the same
        # self._ref_clk_hz = value
        # sys_clk readout will reflect new ref clock with same multiplier

    @api_property(step=1, unit="Hz")
    def sys_clk(self) -> int:
        """System clock [Hz] of internal DDS (reference clock × integer multiplier)"""

        # use read_register
        data = self.read_register(0x01, 3)
        fr1_val = int.from_bytes(data, "big")
        multiplier = (fr1_val >> 18) & 0x1F

        return self._ref_clk_hz * multiplier

    @sys_clk.setter
    def sys_clk(self, value: int):
        """
        Set system clock frequency.

        The DDS requires an integer multiplier of the reference clock.
        Valid ranges: 100-255 MHz or 255-500 MHz.
        """
        multiplier = min(max(int(round(value / self._ref_clk_hz)), 1), 31)
        value_clipped = self._ref_clk_hz * multiplier

        # Determine VCO range
        if 255_000_000 <= value_clipped <= 500_000_000:
            vco_flag = True
        elif 100_000_000 <= value_clipped <= 255_000_000:
            vco_flag = False
        else:
            logger.warning(
                f"{self.id}: System clock {value_clipped} Hz is out of "
                f"guaranteed operation range (100-255 MHz or 255-500 MHz)"
            )
            return

        # Configure FR1 register: VCO flag + multiplier
        fr1_val = 0
        if vco_flag:
            fr1_val |= 1 << 23
        fr1_val |= (multiplier & 0x1F) << 18
        data = fr1_val.to_bytes(3, "big")

        self.bridge.spi_write_addr_payload(self.device_index, 0x01, data)
        self.io_update()

    # --- Commands ---

    @api_command()
    def get_channel_frequency(self, channel_mask: int) -> float:
        """
        Get frequency (Hz) for one or more channels.

        Args:
            channel_mask: Channel selection (ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80)
        Returns:
            Frequency in Hz
        """

        self.select_channel(channel_mask)
        data = self.bridge.spi_read_addr(self.device_index, 0x04, 4)
        ftw = int.from_bytes(data, "big")

        frequency = ftw * self.sys_clk / (1 << 32)
        return frequency

    @api_command()
    def set_channel_frequency(self, channel_mask: int, frequency: float) -> float:
        """
        Set frequency (Hz) for one or more channels.

        Args:
            channel_mask: Channel selection (ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80)
            frequency: Desired frequency in Hz

        Returns:
            Actual frequency set (quantized to DDS resolution)
        """
        self.select_channel(channel_mask)

        # Calculate frequency tuning word (32-bit)
        ftw = int(round(frequency * (1 << 32) / self.sys_clk)) & 0xFFFFFFFF

        # Write to CFTW0 register (address 0x04)
        self.bridge.spi_write_addr_payload(
            self.device_index, 0x04, ftw.to_bytes(4, "big")
        )

        # Calculate actual frequency
        actual_freq = ftw * self.sys_clk / (1 << 32)
        self.io_update()
        return actual_freq

    @api_command()
    def get_channel_amplitude(self, channel_mask: int) -> float:
        """
        Get amplitude for one or more channels.

        Args:
            channel_mask: Channel selection (ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80)
        Returns:
            Amplitude (0.0-1.0)
        """
        self.select_channel(channel_mask)
        data = self.bridge.spi_read_addr(self.device_index, 0x06, 3)
        acr_val = int.from_bytes(data, "big")

        amplitude_int = acr_val & 0x3FF  # Lower 10 bits
        amplitude = amplitude_int / 1024
        return amplitude

    @api_command()
    def set_channel_amplitude(self, channel_mask: int, amplitude: float) -> float:
        """
        Set amplitude for one or more channels.

        Args:
            channel_mask: Channel selection (ch0: 0x10, ch1: 0x20, ch2: 0x40, ch3: 0x80)
            amplitude: Amplitude 0.0-1.0 (relative to full scale)

        Returns:
            Actual amplitude set (quantized to 10-bit resolution)
        """
        self.select_channel(channel_mask)

        # Clamp and quantize to 10-bit (0-1023)
        amplitude_int = int(round(max(0, min(1023, amplitude * 1024))))

        # ACR register: bit 12 enables manual amplitude control
        acr_val = (1 << 12) | amplitude_int
        data = acr_val.to_bytes(3, "big")

        # Write to ACR register (address 0x06)
        self.bridge.spi_write_addr_payload(self.device_index, 0x06, data)

        actual_amp = amplitude_int / 1024
        self.io_update()
        return actual_amp

    # --- Channel Properties ---
    # Note: No hardware readback support; these return cached values

    @api_property(unit="Hz")
    def channel0_frequency(self) -> float:
        """Frequency [Hz] of channel 0"""
        return self.get_channel_frequency(0x10)
        # return self._channel0_frequency

    @channel0_frequency.setter
    def channel0_frequency(self, value: float):
        self.set_channel_frequency(0x10, value)

    @api_property()
    def channel0_amplitude(self) -> float:
        """Amplitude (0.0-1.0) of channel 0"""
        return self.get_channel_amplitude(0x10)

    @channel0_amplitude.setter
    def channel0_amplitude(self, value: float):
        self.set_channel_amplitude(0x10, value)

    @api_property(unit="Hz")
    def channel1_frequency(self) -> float:
        """Frequency [Hz] of channel 1"""
        return self.get_channel_frequency(0x20)

    @channel1_frequency.setter
    def channel1_frequency(self, value: float):
        self.set_channel_frequency(0x20, value)

    @api_property()
    def channel1_amplitude(self) -> float:
        """Amplitude (0.0-1.0) of channel 1"""
        return self.get_channel_amplitude(0x20)

    @channel1_amplitude.setter
    def channel1_amplitude(self, value: float):
        self.set_channel_amplitude(0x20, value)

    @api_property(unit="Hz")
    def channel2_frequency(self) -> float:
        """Frequency [Hz] of channel 2"""
        return self.get_channel_frequency(0x40)

    @channel2_frequency.setter
    def channel2_frequency(self, value: float):
        self.set_channel_frequency(0x40, value)

    @api_property()
    def channel2_amplitude(self) -> float:
        """Amplitude (0.0-1.0) of channel 2"""
        return self.get_channel_amplitude(0x40)

    @channel2_amplitude.setter
    def channel2_amplitude(self, value: float):
        self.set_channel_amplitude(0x40, value)

    @api_property(unit="Hz")
    def channel3_frequency(self) -> float:
        """Frequency [Hz] of channel 3"""
        return self.get_channel_frequency(0x80)

    @channel3_frequency.setter
    def channel3_frequency(self, value: float):
        self.set_channel_frequency(0x80, value)

    @api_property()
    def channel3_amplitude(self) -> float:
        """Amplitude (0.0-1.0) of channel 3"""
        return self.get_channel_amplitude(0x80)

    @channel3_amplitude.setter
    def channel3_amplitude(self, value: float):
        self.set_channel_amplitude(0x80, value)

    @api_command()
    def read_register_bytes(self, reg_addr: int, num_bytes: int = 1) -> str:
        """
        Read bytes from a register and return as hex string.

        Args:
            reg_addr: Register address (0x00-0x7F)
            num_bytes: Number of bytes to read (default: 1)

        Returns:
            Hex string of read data (e.g., 'A3F012')
        """
        data = self.read_register(reg_addr, num_bytes)
        return data.hex().upper()
