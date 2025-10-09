import os, sys

from enum import Enum


from typing import Literal

class IO_MODE(Enum):
    SINGLE_BIT_2WIRE = 0b00
    SINGLE_BIT_3WIRE = 0b01
    SERIAL_MODE_2BIT = 0b10
    SERIAL_MODE_4BIT = 0b11

REF_CLK = 50_000_000

import time
from pyftdi.ftdi import Ftdi
Ftdi.show_devices()

INTERFACE = "ftdi://ftdi:232h:0:1/1"

from pyftdi.spi import SpiController
from pyftdi.gpio import GpioController

spi = SpiController()
spi.configure(INTERFACE)

# test SPI
port = spi.get_port(cs=0, freq=1e6, mode=0)

test_data = bytes([0xAA, 0x55, 0xFF, 0x00])
test_addr = 0x0A

port.exchange(bytes([test_addr & 0x7f]) + test_data, duplex=False)
time.sleep(2.0)

# test GPI
gpio = GpioController()
gpio.configure(INTERFACE, direction=0x30)

v = gpio.read()
# 01
gpio.write((v & ~0x30) | 0x10) # high
time.sleep(0.2)
#11
gpio.write((v & ~0x30) | 0x30) # high
time.sleep(0.6)
#10
gpio.write((v & ~0x30) | 0x20) # high
time.sleep(0.4)
#00
gpio.write((v & ~0x30) | 0x00) # high
time.sleep(0.2)





gpio.write()

v = gpio.read()
    print(f"gpi pre  read = {v:02x}")
    
    t = v | 0x30
    print(f"want to write = {t:02x}")
    gpio.write(t) # high
    v = gpio.read()
    print(f"gpi high read = {v:02x}")
    time.sleep(1)

    v = gpio.read()
    t = v & ~0x30
    print(f"want to write = {t:02x}")
    gpio.write(t) # low
    print(f"gpi post read = {v:02x}")





port.exchange(bytes([addr & 0x7f]) + data, duplex=False)



gpio = GpioController()
gpio.configure(INTERFACE, direction=0x10)

def io_update():
    v = gpio.read()
    gpio.write(v | 0x10) # high
    gpio.write(v & ~0x10) # low

def reg_write(addr, data:bytes):
    port.exchange(bytes([addr & 0x7f]) + data, duplex=False)
    io_update()

def reg_read(addr, length):
    port.exchange(bytes([0x80 | (addr & 0x7f)]), duplex=False)

    return port.exchange(b'\x00'*length, duplex=True)

def select_channel(channel: Literal[0,1,2,3], io_mode=IO_MODE.SINGLE_BIT_3WIRE):
    d = {0: 0x10, # Ch0
         1: 0x20, # Ch1
         2: 0x40, # Ch2
         3: 0x80} # Ch3
    csr_val = 0xF0 & d[channel]
    csr_val = (csr_val & ~0x06) | ((int(io_mode.value) & 0x3) << 1)
    #reg_write(0x00, bytes([csr_val]), latch=False)
    port.exchange(bytes([0x00 & 0x7f]) + bytes([csr_val]), duplex=False)
    readback = reg_read(0x00, 1)[0]
    print(f"CSR written=0x{csr_val:02X}, readback=0x{readback:02X}")

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
    reg_write(0x01, data)
    print(f"fr1 data = {fr1_val:02X}")
    print(f"System clock set to {sys_clk}")
    return sys_clk

def set_current_channel_freq(single_tone_freq, sys_clk):
    ftw = int(round(single_tone_freq * (1<<32) / sys_clk)) & 0xFFFFFFFF
    reg_write(0x04, ftw.to_bytes(4, 'big')) # 0x04 is cftw0 address
    freq = ftw * sys_clk / 2**32
    print(f"Channel set to single tone freq = {freq}")
    return freq

def set_current_channel_amp(scale_factor = 0.5): # scale factor between 0 and 1
    scale_factor_int = int(round(max(0, min(1023, float(scale_factor * 1024)))))

    acr_val = (1 << 12) | scale_factor_int # "1" at bit 12 enables manual writing
    data = acr_val.to_bytes(3, 'big')   

    reg_write(0x06, data)     

    amp = scale_factor_int / 1024    
    print(f"Channel set to single tone amp = {amp}")
    return amp


req_freq = 100_000

select_channel(3)
sys_clk = set_clock(500_000_000)

fr1_readback = reg_read(0x01, 3)
print(f"fr1 readback = {int.from_bytes(fr1_readback):02X}")

req_freq = 100_000
freq = set_current_channel_freq(req_freq, sys_clk=500000000)
amp = set_current_channel_amp(0.5)


def test5():
    gpio = GpioController()
    gpio.configure(INTERFACE, direction=0x30)

    v = gpio.read()
    print(f"gpi pre  read = {v:02x}")
    
    t = v | 0x30
    print(f"want to write = {t:02x}")
    gpio.write(t) # high
    v = gpio.read()
    print(f"gpi high read = {v:02x}")
    time.sleep(1)

    v = gpio.read()
    t = v & ~0x30
    print(f"want to write = {t:02x}")
    gpio.write(t) # low
    print(f"gpi post read = {v:02x}")


test5()

      
