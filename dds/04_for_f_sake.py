
import time
from pyftdi.ftdi import Ftdi
Ftdi.show_devices()

URL = "ftdi://ftdi:232h:0:1/1"
URL = "ftdi://ftdi:232h:0:2/1"
URL = 'ftdi://ftdi:232h/1'  # keep it simple

from pyftdi.spi import SpiController
from pyftdi.gpio import GpioController


spi = SpiController(cs_count=1)
spi.configure(URL)
port = spi.get_port(0, freq=500_000, mode=0)
gpio = spi.get_gpio()
gpio.set_direction(0x70, 0x70)   # D4,D5 outputs; D6,D7 inputs (example)
gpio.write(0x00)                 # initialize to low
gpio.write(0x60)                 # do reset (and keep it??)

tx = bytes([0x00, 0x82]) # 4 bits - channel select, 4 bits 3: 0, 2:1 : io_mode (I want 01), 0: lsb
rx = port.exchange(tx, duplex=False)

time.sleep(0.001)
resp = port.exchange(bytes([0x80]), 1, duplex=False)
print(f"resp = {resp[0]:02x}")  

time.sleep(0.1)


#tx = bytes([0x01, 0xa8, 0x80, 0x00]) # 1010 1010 0101 0101 1111 1111 0000 0000
#rx = port.exchange(tx, duplex=False)

#gpio.write(0x10)
#gpio.write(0x00)  
#resp = port.exchange(bytes([0x81]), 3, duplex=False)
#print(f"resp = {resp[0]:02x}  {resp[1]:02x}  {resp[2]:02x}")  

spi.close()

