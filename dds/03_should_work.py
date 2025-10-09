
import time

from enum import Enum
from typing import Literal

class IO_MODE(Enum):
    SINGLE_BIT_2WIRE = 0b00
    SINGLE_BIT_3WIRE = 0b01
    SERIAL_MODE_2BIT = 0b10
    SERIAL_MODE_4BIT = 0b11


from pyftdi.ftdi import Ftdi
Ftdi.show_devices()

URL = "ftdi://ftdi:232h:0:1/1"

from pyftdi.spi import SpiController
from pyftdi.gpio import GpioController


spi = SpiController(cs_count=1)
spi.configure(URL)

port = spi.get_port(0, freq=1_000_000, mode=0)
gpio = spi.get_gpio()
gpio.set_direction(0x30, 0x30)
gpio.write(0x00) # initialize to low

def io_update():
    gpio.write(0x10) # toggle high -> low
    time.sleep(0.01)
    gpio.write(0x00)

def reset():
    gpio.write(0x20) # toggle high -> low
    time.sleep(0.01)
    gpio.write(0x00)

def reg_write(addr, data, do_io_update=True):
    port.exchange(bytes([addr & 0x7f]) + data, duplex=False)
    if do_io_update:
        io_update()

def reg_read(addr, length):
    return port.exchange(out=bytes([(addr & 0x1f) | 0x80]), 
                         readlen=length,
                         duplex=False)


def select_channel(channel: Literal[0,1,2,3], io_mode=IO_MODE.SINGLE_BIT_3WIRE):
    d = {0: 0x10, # Ch0
         1: 0x20, # Ch1
         2: 0x40, # Ch2
         3: 0x80} # Ch3
    csr_val = 0xF0 & d[channel]
    csr_val = (csr_val & ~0x06) | ((int(io_mode.value) & 0x3) << 1)
    #reg_write(0x00, bytes([csr_val]), latch=False)
    port.exchange(bytes([0x00,]) + bytes([csr_val,]), duplex=False)
    readback = reg_read(0x00, 1)[0] # return the 0th byte
    print(f"CSR written=0x{csr_val:02X}, readback=0x{readback:02X}")

REF_CLK = 50_000_000 # 50 MHz
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
    print(f"Setting FTW to {ftw}")
    reg_write(0x04, ftw.to_bytes(4, 'big')) # 0x04 is cftw0 address
    freq = ftw * sys_clk / 2**32
    print(f"Channel set to single tone freq = {freq}")
    return freq



reset()


io_update() # funguje!!!


req_freq = 100_000
select_channel(3)

sys_clk = set_clock(500_000_000)
fr1_readback = reg_read(0x01, 3)
print(f"fr1 readback = {int.from_bytes(fr1_readback):02X}")

req_freq = 100_000
freq = set_current_channel_freq(req_freq, sys_clk=500000000)