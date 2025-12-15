include("client/julia/client.jl")
using .LabHubClient

println("first test of the scripting capability")


hub = LabHubClient.connect(foo=42)
hub

# Connect to your hub (same host/port you used in Python)
hub = LabHubClient.connect(host="127.0.0.1", port=8212)

# Pick your devices (by id)
#dev_dummy  = hub.devices.dummy_01             # mirrors: lhc.dummy_01
dev_dummy = hub.devices["dummy_01"]
#dev_ex     = hub.devices.example_device_01    # mirrors: lhc.example_device_01

# Call commands (same semantics as Python)
xs = get_timestamps(dev_ex)                   # mirrors: xs = lhc.example_device_01.get_timestamps()
a  = start(dev_ex; duration_in_seconds=10)    # mirrors: a = lhc.example_device_01.start(duration_in_seconds=10)

# Optional: print a friendly summary
println(dev_ex)