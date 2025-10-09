
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

time.sleep(0.5)
# CS0 on D3, SCLK=D0, MOSI=D1, MISO=D2
port = spi.get_port(0, freq=1_000_000, mode=0)
time.sleep(0.5)
# optional: use GPIO D4..D7 via the same controller
gpio = spi.get_gpio()
time.sleep(0.5)
gpio.set_direction(0x30, 0x30)   # D4,D5 outputs; D6,D7 inputs (example)
time.sleep(1.0)

gpio.write(0x10)                 # toggle D4 high
time.sleep(0.1)
gpio.write(0x20)
time.sleep(0.2)
gpio.write(0x30)
time.sleep(0.3)
gpio.write(0x00)
time.sleep(0.4)

# loopback test: connect D1↔D2
tx = bytes([0xAA, 0x55, 0xFF, 0x00]) # 1010 1010 0101 0101 1111 1111 0000 0000
rx = port.exchange(tx, duplex=False)

time.sleep(0.5)
spi.close()