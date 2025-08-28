import client.python as lhc


# connect
lhc.connect("127.0.0.1", 8212)

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
