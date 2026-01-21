import sys

from ctypes import WinDLL, CDLL, create_string_buffer, c_int, c_void_p, POINTER, c_uint32, c_uint8
import ctypes


from enum import Enum

import time
from typing import Literal

class IO_MODE(Enum):
    SINGLE_BIT_2WIRE = 0b00
    SINGLE_BIT_3WIRE = 0b01
    SERIAL_MODE_2BIT = 0b10
    SERIAL_MODE_4BIT = 0b11

REF_CLK = 50_000_000



#dll_path_usb = "C:\\Program Files (x86)\\Analog Devices\\AD9958_59 Evaluation Software\\ADI_CYUSB_USB4.dll"
dll_path_adi = "C:\\Program Files (x86)\\Analog Devices\\AD9958_59 Evaluation Software\\adiclockeval.dll"

dll = ctypes.WinDLL(dll_path_adi)

dll.FindHardware.argtypes = (POINTER(c_uint32), POINTER(c_uint32), c_int)
dll.FindHardware.restype = None

dll.GetVendorID.argtypes = (c_int,)
dll.GetVendorID.restype = c_uint32

dll.GetProductID.argtypes = (c_int,)
dll.GetProductID.restype = c_uint32

dll.SpiWrite.argtypes = (c_int, c_void_p, c_int)
dll.SpiWrite.restype = c_int

dll.SetPortValue.argtypes = (c_int, c_uint32, c_uint32)
dll.SetPortValue.restype  = c_int

VID = 0x0456
PID = 0xee25

vendor_arr = (c_uint32 * 1)(VID)
product_arr = (c_uint32 * 1)(PID)

dll.FindHardware(vendor_arr, product_arr, 1)

v = dll.GetVendorID(0)
p = dll.GetProductID(0)

print(hex(v), hex(p))



## test SpiRead

# params SpiRead(dev_id , reg_value, reg_len, ptr_out, len_readback, param_6)

# dll.SpiWrite.argtypes = (c_int, c_void_p, c_int)
# dll.SpiWrite.restype = c_int

# dll.SpiRead.argtypes = (c_int, c_void_p, c_int, POINTER(c_uint8), c_int, c_uint8)
# dll.SpiRead.restype  = c_int

dev_id = 0

# dll.SpiWrite(dev_id, ctypes.cast(buf, c_void_p), len(payload), ptr_out, len_readback, random_byte)


dll.SpiRead.argtypes = (
    c_int,            # dev_id
    POINTER(c_uint8), # reg_value (bytes to write on SPI)
    c_int,            # reg_len
    POINTER(c_uint8), # out buffer
    c_int,            # len_readback (bytes)
    c_uint8,          # bit_shift=0
)
dll.SpiRead.restype = c_int

def spi_read(reg_addr, nbytes, dev_id=0, bit_shift=0):
    # build the 1-byte SPI "read register" command (your protocol)
    cmd = (0x80 | (reg_addr & 0x7F))  # MSB=1 means read, per you
    reg_buf = (c_uint8 * 1)(cmd)
    out_buf = (c_uint8 * nbytes)()
    rc = dll.SpiRead(dev_id, reg_buf, 1, out_buf, nbytes, c_uint8(bit_shift))
    return bytes(reversed(out_buf))

what_channel = 0x10 # 0x80 = ch3
spi_write(0x00,  [what_channel, ]) 

r = spi_read(0x4, 4, dev_id=0, bit_shift=0)



def spi_write_works(addr, payload, dev_id=0, dll=dll):
    payload = bytes(reversed([addr,] + payload))
    buf = (c_uint8 * len(payload)).from_buffer_copy(payload)
    rc = dll.SpiWrite(dev_id, ctypes.cast(buf, c_void_p), len(payload))
    return rc

import ctypes
from ctypes import c_uint8, c_void_p

def spi_write(addr, payload, dev_id=0, dll=dll):
    """Normalize payload, prepend addr, reverse bytes, and call dll.SpiWrite.
    payload may be: bytes, bytearray, int, list/tuple of ints.
    addr must be an int 0..255.
    """
    # normalize payload -> bytes
    if isinstance(payload, int):
        # convert integer to minimal big-endian bytes (at least 1 byte)
        nb = (payload.bit_length() + 7) // 8 or 1
        payload_bytes = payload.to_bytes(nb, 'big')
    elif isinstance(payload, (bytes, bytearray)):
        payload_bytes = bytes(payload)
    elif isinstance(payload, (list, tuple)):
        payload_bytes = bytes(payload)
    else:
        raise TypeError("payload must be int/bytes/bytearray/list/tuple")
    
    if not (0 <= addr <= 0xFF):
        raise ValueError("addr must be 0..255")
    
    src = bytes([addr]) + payload_bytes          # e.g. b'\x04' + b'\x12\x34\x56'
    src_reversed = src[::-1]                     # reverse byte order
    
    buf = (c_uint8 * len(src_reversed)).from_buffer_copy(src_reversed)
    rc = dll.SpiWrite(int(dev_id), ctypes.cast(buf, c_void_p), len(src_reversed))
    return rc


def io_update(dev_id=0):
    command = 3    # maps to opcode 0x0C
    rc = dll.SetPortValue(dev_id, command, 0x10)
    rc = dll.SetPortValue(dev_id, command, 0x00)
    return rc


REF_CLK = 50_000_000
def set_clock(system_clock_request=500_000_000):
    multiplier = int(round(system_clock_request / REF_CLK))
    sys_clk = REF_CLK * multiplier
    if 255_000_000 <= sys_clk <= 500_000_000:
        vco_flag = True
    elif 100_000_000 <= sys_clk <= 255_000_000:
        vco_flag = False
    else:
        print(f" For sys_clk = {sys_clk} Hz, there is not guarantee of operation (choose either 100-160 MHz or 255-500 MHz")
        return
    
    fr1_val = 0
    if vco_flag:
        fr1_val |= 1 << 23
    fr1_val |= (multiplier & 0x1F) << 18
    data = fr1_val.to_bytes(3, 'big')
    spi_write(0x01, data)
    print(f"fr1 data = {fr1_val:02X}")
    print(f"System clock set to {sys_clk}")
    return sys_clk



def set_current_channel_freq(single_tone_freq, sys_clk):
    ftw = int(round(single_tone_freq * (1<<32) / sys_clk)) & 0xFFFFFFFF
    spi_write(0x04, ftw.to_bytes(4, 'big')) # 0x04 is cftw0 address
    freq = ftw * sys_clk / 2**32
    print(f"Channel set to single tone freq = {freq}")
    return freq

def set_current_channel_amp(scale_factor = 0.5): # scale factor between 0 and 1
    scale_factor_int = int(round(max(0, min(1023, float(scale_factor * 1024)))))
    acr_val = (1 << 12) | scale_factor_int # "1" at bit 12 enables manual writing
    data = acr_val.to_bytes(3, 'big')   
    spi_write(0x06, data)     
    amp = scale_factor_int / 1024    
    print(f"Channel set to single tone amp = {amp}")
    return amp


what_channel = 0x80 # 0x80 = ch3
spi_write(0x00,  [what_channel, ]) 

set_clock(500_000_000)
freq = set_current_channel_freq(100_000, sys_clk=500_000_000)
amp = set_current_channel_amp(0.85)
io_update()

# select channel 3
# 00 00 00 00 00 00 00 00   01 00 00 00 00 00 00 00  0x00 0x80


# set amp to 0.85:
# 00 00 00 00 00 01 01 00   00 00 00 00 00 00 00 00  0x06 0x00
# 00 00 00 01 00 00 01 01   00 01 01 00 00 01 01 00  0x13 0x66

# from bridge via cli
# select channel 3
# 00 00 00 00 00 00 00 00   01 00 00 00 00 00 00 00 0x00 0x80

#set amp to 0x85 SPI_WRITE_HEX 0 0X06001366
# 00 00 00 00 00 01 01 00  00 00 00 00 00 00 00 00  0x06 0x00
# 00 00 00 01 00 00 01 01  00 01 01 00 00 01 01 00  0x13 0x66




#& ".\adiclockeval_spi_bridge.exe" "C:/Program Files (x86)/Analog Devices/AD9958_59 Evaluation Software"

PING
FIND_HARDWARE 1 0X0456 0XEE25
GET_VENDOR_ID
GET_PRODUCT_ID


SPI_WRITE_HEX 0 0X0080
SPI_WRITE_HEX 0 0X01 0XA9 0X00 0X00 
# 0X01 0XA8 0X00 0X00 # set system clock to 500 MHz
SPI_WRITE_HEX 0 0X06001200 
# set amp to 0.5
#SPI_WRITE_HEX 0 0X8000
SPI_WRITE_HEX 0 0X040f1b71
SET_PORT_VALUE 0 3 0x10
SET_PORT_VALUE 0 3 0x00