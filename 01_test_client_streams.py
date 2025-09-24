import client.python as lhc
import matplotlib.pyplot as plt
import numpy as np


# connect
lhc.connect("127.0.0.1", 8212)

lhc.example_device_01

ds = lhc.example_device_01.demo_wave

f = ds.get_one_frame()

s = f["series"][0]

fig, ax = plt.subplots(figsize=(10,5))
ax.plot(s["data"])
plt.show()

frames = [f["series"][0]["data"] for f in ds.stream(limit=10)]

fig, ax = plt.subplots(figsize=(10,5))
for frame in frames:
    ax.plot(frame, color="black", alpha=0.10)
ax.plot(np.array(frames).mean(axis=0), color="red")
plt.show()

lhc.example_device_01.demo_wave # demo_wave is instance of DataSourceProxy

# when called, return an iterator:
frames = []
for frame in lhc.example_device_01.demo_wave.stream(limit=5, interval=0.001):
    frames.append(frame)

# special method for single frame:
single_frame = lhc.example_device_01.demo_wave.get_one_frame()

# special method for plot specs
plot_specs = lhc.example_device_01.demo_wave.get_plot_specs()

# start a run
lhc.example_device_01.start(duration_in_seconds=5)

# 1) Read state changes (e.g., streaming flag) at ~2 Hz
for ev in lhc.example_device_01.events(rate=2):
    print("STATE:", ev)
    # stop after first couple of updates
    break

# 2) Stream binary data for 5 s at ~20 Hz and collect it
lhc.example_device_01.start(duration_in_seconds=5)
t, y = lhc.example_device_01.collect_stream(seconds=2, rate=20, fmt="msgpack")
print(len(t), "samples")

# stop explicitly (it will also auto-stop after duration)
lhc.example_device_01.stop()
