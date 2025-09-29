# 1. Open new window of VS Code in D:\labhub folder
# 2. Activate correct python: close existing terminal, then Terminal -> New Terminal. Green (.venv) should appear at the start of the command line
# (optional) open and modify config.yaml to set up default values for picoscope and other devices
# 3. Make sure that neither kinesis nor picoscope SW nor picoscope labview is running (there may be only to use the libraries)
# 4. Run `python .\hub\tray_app\tray.py` in the terminal. Labhub should -hopefully- start, the labhub icon should appear
# 5. Run or modify the following script for automated data acquisition 
# (6. If you stop the server (from the tray icon), you should be able to run the standard kinesis/picoscope SW)

import numpy as np
import matplotlib.pyplot as plt

import client.python as lhc

lhc.connect("127.0.0.1", 8212)
print(lhc) # prints docs

lhc.picoscope.set_channel(channel="A", enable=True, coupling_type="DC", range="1V")
lhc.picoscope.set_channel(channel="B", enable=True, coupling_type="DC", range="1V")

lhc.picoscope.sampling_frequency = 31_250_000 # Hz

### shorter acquisitions - via available data streams (lhc.picoscope.time_stream or lhc.picoscope.psd_stream)
# single frame - via .get_one_frame()
lhc.picoscope.post_trigger_samples = 10_000
frame = lhc.picoscope.time_stream.get_one_frame()
meta = lhc.picoscope.time_stream.get_plot_specs()

fig, ax = plt.subplots(figsize=(10,5))
ax.set_title(meta["title"])
ax.set_xlabel(meta["x-label"])
ax.set_ylabel(meta["y-label"])
for channel in ("A", "B"): 
    ax.plot(meta["x-values"], frame[channel], label=channel, alpha=0.8)
ax.grid()
ax.legend()
plt.show()

### multiple frames - via .stream() iterator
# limit - how many frames will be returned
# throttled to 10 Hz between server and client
psd_a_arr, psd_b_arr = [], []
for frame in lhc.picoscope.psd_stream.stream(limit=10):
    psd_a_arr.append(frame["A"])
    psd_b_arr.append(frame["B"])

psd_meta = lhc.picoscope.psd_stream.get_plot_specs()

fig, axs = plt.subplots(figsize=(10,8), nrows=2)
axs[0].set_title(psd_meta["title"])
axs[0].set_ylabel(psd_meta["y-label"])
axs[0].set_xlabel(psd_meta["x-label"])

axs[1].set_ylabel(psd_meta["y-label"])
axs[1].set_xlabel(psd_meta["x-label"])

for arr in psd_a_arr:
    axs[0].plot(psd_meta["x-values"], arr, color="black", alpha=0.10)
axs[0].plot(psd_meta["x-values"], np.array(psd_a_arr).mean(axis=0), color="tab:blue", label="A")
axs[0].grid()
axs[0].legend()

for arr in psd_b_arr:
    axs[1].plot(psd_meta["x-values"], arr, color="black", alpha=0.10)
axs[1].plot(psd_meta["x-values"], np.array(psd_a_arr).mean(axis=0), color="tab:orange", label="B")
axs[1].grid()
axs[1].legend()

# log/log for channel B just to show off
axs[1].set_xscale("log")
axs[1].set_yscale("log")

fig.show()

### longer acquisition -> save directly to file (no client-server overhead)
# only raw time series; saves to .wav; scaling to V may not be correct 
lhc.picoscope.acquire_to_file(folder="D:/tmp", filename="tst.wav", acquisition_duration_s=0.2) 

# If you want custom streams (hilbert transform or what not):
# in the file labhub/hub/hub_app/drivers/pico_technology/ps5000a.py
# copy-paste psd_stream and psd_stream_plot and rename
# modify the mapper() inner function 
#  - time series on input (1D numpy.array[N, ])
#  - must return a list (!!not numpy.array) - use the .tolist() just before return

# Known issues
# - sloppy conversion to V (not done consistently, especially when changing range on different channels)
# - resolution (bit depth) can only be changed on startup in config.yaml 
# - throttle other than 10 Hz not supported
# - active streaming may interfere with some commands (e.g. long acquisition) in unexpected ways
