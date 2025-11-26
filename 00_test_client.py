print("foo")
import client.python as lhc

lhc.connect("127.0.0.1", 8212)

lhc.dummy_01.foo

lhc.example_device_01

xs = lhc.example_device_01.get_timestamps()
a = lhc.example_device_01.start(duration_in_seconds=10)

s = lhc.snapshot(folder=r"C:\Users\jankl\Documents\pracovni\upt\labglue\tmp")
help(lhc.snapshot)


