# adi_bridge.py
import subprocess
import threading
import queue
import os
import sys
from typing import List, Tuple, Optional, Iterable, Union

__all__ = ["BridgeError", "AdiClockEvalBridge"]

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

class BridgeError(RuntimeError):
    pass

class AdiClockEvalBridge:
    """
    Wrapper around the 32-bit adiclockeval_spi_bridge.exe.
    Protocol: line-based, synchronous request/response.
    """
    def __init__(
        self,
        exe_path: str,
        dll_folder: str,
        timeout: float = 5.0,
        creationflags: int = CREATE_NO_WINDOW,
    ) -> None:
        self.exe_path = exe_path
        self.dll_folder = dll_folder
        self.timeout = timeout
        self._p: Optional[subprocess.Popen] = None
        self._out_q: "queue.Queue[str]" = queue.Queue()
        self._err_q: "queue.Queue[str]" = queue.Queue()
        self._reader_t: Optional[threading.Thread] = None
        self._err_t: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ---------- process management ----------
    def start(self) -> None:
        if self._p is not None:
            return
        if not os.path.isfile(self.exe_path):
            raise BridgeError(f"Bridge executable not found: {self.exe_path}")
        if not os.path.isdir(self.dll_folder):
            raise BridgeError(f"DLL folder not found: {self.dll_folder}")

        self._p = subprocess.Popen(
            [self.exe_path, self.dll_folder],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,                # line mode
            encoding="utf-8",
            #newline="\n",             # normalize to \n
            bufsize=1,                # line-buffered
            creationflags=CREATE_NO_WINDOW,
        )

        # reader threads
        self._reader_t = threading.Thread(target=self._reader, daemon=True)
        self._reader_t.start()
        self._err_t = threading.Thread(target=self._err_reader, daemon=True)
        self._err_t.start()

        # quick health check
        pong = self.ping()
        if pong != "PONG":
            raise BridgeError(f"Unexpected PING response: {pong}")

    def _reader(self) -> None:
        assert self._p and self._p.stdout
        for line in self._p.stdout:
            #print(f" .. read back: {line}")
            self._out_q.put(line.rstrip("\r\n"))

    def _err_reader(self) -> None:
        assert self._p and self._p.stderr
        for line in self._p.stderr:
            self._err_q.put(line.rstrip("\r\n"))

    def close(self) -> None:
        if self._p:
            try:
                self._send_line("QUIT", expect_reply=True, swallow_errors=True)
            except Exception:
                pass
            try:
                self._p.terminate()
            except Exception:
                pass
            self._p = None

    # def __enter__(self):
    #     self.start()
    #     return self

    # def __exit__(self, *exc):
    #     self.close()

    # ---------- low-level I/O ----------
    def _drain_err_tail(self, n=10):
        lines = []
        try:
            while True:
                lines.append(self._err_q.get_nowait())
        except queue.Empty:
            pass
        return " | ".join(lines[-n:]) if lines else "<no stderr>"

    def _send_line(self, line: str, expect_reply: bool = True, swallow_errors: bool = False):
        #print(f" -- sending line to bridge: {line}")
        if not self._p or not self._p.stdin:
            raise BridgeError("Bridge is not running")
        if self._p.poll() is not None:
            raise BridgeError(f"Bridge exited (code {self._p.returncode}). Stderr: {self._drain_err_tail()}")

        with self._lock:
            try:
                # IMPORTANT: do not mix manual stdout reads elsewhere while using the queue reader
                self._p.stdin.write(line + "\n")
                self._p.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                raise BridgeError(f"Write failed: {e}. Stderr: {self._drain_err_tail()}") from e

            if not expect_reply:
                return None

            try:
                resp = self._out_q.get(timeout=self.timeout)
            except queue.Empty:
                state = f"dead(code={self._p.returncode})" if self._p.poll() is not None else "alive"
                msg = f"Timeout waiting for reply to '{line}' (proc {state}). Stderr: {self._drain_err_tail()}"
                if swallow_errors:
                    return None
                raise BridgeError(msg)
            return resp


    def _ok_payload(self, resp: str) -> str:
        if not resp.startswith("OK"):
            raise BridgeError(f"Bridge error: {resp}")
        return resp[2:].strip()

    # ---------- public API (matches server commands) ----------
    def ping(self) -> str:
        resp = self._send_line("PING")
        return self._ok_payload(resp)  # "PONG"

    def find_hardware(self, count: int, vid_pid: Optional[List[Tuple[int, int]]] = None) -> List[Tuple[int, int]]:
        if count <= 0:
            raise ValueError("count must be > 0")
        parts = ["FIND_HARDWARE", str(count)]
        if vid_pid:
            for v, p in vid_pid[:count]:
                parts.append(str(v))
                parts.append(str(p))
        resp = self._send_line(" ".join(parts))
        payload = self._ok_payload(resp)
        toks = payload.split()
        if len(toks) != count * 2:
            raise BridgeError(f"Unexpected FIND_HARDWARE payload: {payload}")
        out = []
        for i in range(0, len(toks), 2):
            out.append((int(toks[i]), int(toks[i + 1])))
        return out

    def get_vendor_id(self, dev_id: int = 0) -> int:
        resp = self._send_line(f"GET_VENDOR_ID {dev_id}")
        return int(self._ok_payload(resp))

    def get_product_id(self, dev_id: int = 0) -> int:
        resp = self._send_line(f"GET_PRODUCT_ID {dev_id}")
        return int(self._ok_payload(resp))

    def set_port_value(self, dev_id: int, command: int, value: int) -> int:
        resp = self._send_line(f"SET_PORT_VALUE {dev_id} {command} {value}")
        return int(self._ok_payload(resp))

    def spi_write_hex(self, dev_id: int, hexdata: str) -> int:
        """
        hexdata may be continuous '010203', or '01 02 03', or '0x01,0x02', etc.
        The server infers length.
        """
        resp = self._send_line(f"SPI_WRITE_HEX {dev_id} {hexdata}")
        return int(self._ok_payload(resp))

    # ---------- convenience helpers (optional) ----------
    @staticmethod
    def _bytes_to_hex_blob(data: bytes) -> str:
        # compact, no separators (server accepts separators too)
        return data.hex()

    def spi_write_bytes(self, dev_id: int, data: Union[bytes, bytearray, Iterable[int]]) -> int:
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(int(b) & 0xFF for b in data)
        return self.spi_write_hex(dev_id, self._bytes_to_hex_blob(data))

    def spi_write_addr_payload(self, dev_id: int, addr: int, payload: Union[int, bytes, bytearray, Iterable[int]]) -> int:
        """
        Your higher-level convenience: normalize payload, prepend addr, NOT! reverse bytes.
        Mirrors your working Python logic.
        """
        if not (0 <= addr <= 0xFF):
            raise ValueError("addr must be 0..255")
        if isinstance(payload, int):
            nb = (payload.bit_length() + 7) // 8 or 1
            pbytes = payload.to_bytes(nb, "big")
        elif isinstance(payload, (bytes, bytearray)):
            pbytes = bytes(payload)
        else:
            pbytes = bytes(int(b) & 0xFF for b in payload)
        src = bytes([addr]) + pbytes
        #print(f" -- constructed payload: {src}")
        return self.spi_write_bytes(dev_id, src)

    def spi_read_hex(self, dev_id: int, write_hex: str, read_len: int, bit_shift: int = 0) -> tuple[bytes]:
        """
        Send hex data and read back bytes via SPI.

        Args:
            dev_id: Device index
            write_hex: Hex string to write (e.g., '80' for read command)
            read_len: Number of bytes to read back
            bit_shift: Optional bit shift parameter (default 0)

        Returns:
            Tuple of (return_code, read_bytes)
        """
        resp = self._send_line(f"SPI_READ_HEX {dev_id} 0X{write_hex} {read_len} {bit_shift}")
        payload = self._ok_payload(resp)
        #toks = payload.split()

        if len(payload) < 1:
            raise BridgeError(f"Unexpected SPI_READ_HEX payload: {payload}")
        
        hex_bytes = bytes.fromhex(payload)
        
        return hex_bytes

    def spi_read_bytes(self, dev_id: int, write_data: Union[bytes, bytearray, Iterable[int]], read_len: int, bit_shift: int = 0) -> tuple[int, bytes]:
        """
        Convenience method to send bytes and read back bytes via SPI.

        Args:
            dev_id: Device index
            write_data: Bytes to write
            read_len: Number of bytes to read back
            bit_shift: Optional bit shift parameter (default 0)

        Returns:
            Tuple of (return_code, read_bytes)
        """
        if not isinstance(write_data, (bytes, bytearray)):
            write_data = bytes(int(b) & 0xFF for b in write_data)
        write_hex = self._bytes_to_hex_blob(write_data)
        return self.spi_read_hex(dev_id, write_hex, read_len, bit_shift)

    def spi_read_addr(self, dev_id: int, addr: int, read_len: int, bit_shift: int = 0) -> tuple[int, bytes]:
        """
        High-level convenience: read from a register address.

        Constructs read command (0x80 | addr) and reads back data.
        Matches the pattern from your ctypes example.

        Args:
            dev_id: Device index
            addr: Register address (0-127)
            read_len: Number of bytes to read back
            bit_shift: Optional bit shift parameter (default 0)

        Returns:
            Tuple of (return_code, read_bytes)
        """
        if not (0 <= addr <= 0x7F):
            raise ValueError("addr must be 0..127 for read command")

        # Construct read command: MSB=1 means read
        read_cmd = 0x80 | (addr & 0x7F)
        return self.spi_read_bytes(dev_id, bytes([read_cmd]), read_len, bit_shift)
