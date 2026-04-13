# Frequently Asked Questions (FAQ)

## Configuration & Setup

### Q: What's the difference between config.yaml, profile.yaml, and server.yaml?

- **server.yaml** - Server-wide settings (host/port, logging, InfluxDB, scripting paths, custom GUIs). Configured once via launcher's Configure dialog.
- **config.yaml** - Device list and connection parameters (which devices to connect to and how). Edited via `/devices` GUI when adding/removing devices.
- **profile.yaml** - Current state of all devices (property values, read/write policies). Auto-updated as properties change, loaded on startup to restore session.

**In short**: server.yaml = launcher settings, config.yaml = what devices, profile.yaml = device state.

### Q: Can I have multiple configurations for different experiments?

Yes! You can:
1. Create multiple `server_*.yaml` files in `launcher/` directory
2. Launch with `python launcher/launcher.py --server-config launcher/server_experiment_A.yaml`
3. Each server.yaml can point to different config.yaml and profile.yaml files

Or keep one server.yaml and switch config/profile via the launcher's Configure dialog.

### Q: How do I add a new device while the server is running?

1. Go to `http://127.0.0.1:8212/devices` (adjust port if needed)
2. Click "Add Device" button
3. Select driver from the list
4. Fill in connection parameters (ID, serial number, COM port, etc.)
5. Click "Connect" to test, then save

The device is immediately available - no server restart needed.

### Q: Why isn't my device connecting?

Check these in order:
1. **Device admin GUI** (`/devices`) - does it show "Connected"?
2. **Logs** - check launcher window or log file for error messages
3. **Connection params** - verify serial number, COM port, IP address, etc.
4. **Driver requirements** - some drivers need specific DLLs or .NET runtimes
5. **Permissions** - COM ports may need admin rights on Windows
6. **Physical connection** - cable, power, USB connection

### Q: How do I change the server port or host address?

Via launcher's Configure dialog (General tab):
1. Right-click tray icon → Configure
2. Change Host/Port fields
3. Click "(Re)Start Server"

Or via command line:
```bash
python launcher/launcher.py --port 9000 --host 0.0.0.0
```

## Properties, Commands, and Data Sources

### Q: When should I use a command vs a property?

**Properties** - Use for stateful values that:
- Have a current value that can be read
- Change occasionally (not rapidly streaming data)
- Should be cached and polled by the server
- Need to be saved/restored in profile.yaml

Examples: laser power, frequency, enable/disable flags, temperature setpoint

**Commands** - Use for actions that:
- Perform an operation with side effects
- Return a result (may be complex data)
- Should NOT be cached
- Trigger something to happen

Examples: "start acquisition", "calibrate", "reset", "take snapshot"

**Data Sources** - Use for streaming data:
- High-frequency measurements
- Time-series data
- Continuous acquisition

Examples: oscilloscope traces, sensor readings, video frames

### Q: What's the difference between read and write policy in profile.yaml?

- **`policy: write`** (default) - Value is restored from profile on server startup if it differs from current value
- **`policy: read`** - Value is tracked in profile but NEVER written back to device on startup

Use `read` policy when:
- Another program controls the device and you don't want to override it
- The device is in a locked state and writing could cause issues
- You want to observe current values without changing them

Change policies via the profile GUI at `http://127.0.0.1:8212/profile`.

### Q: Why did my property value reset after restart?

Check profile.yaml:
1. Is the property listed? (If not, it wasn't saved)
2. What's the policy? (If `read`, it won't be restored)
3. Is profile path correct in server.yaml?

The profile is auto-saved when properties change, so if it reset, likely the wrong profile was loaded.

### Q: Can I create a custom data source or do I always use @api_data?

**Use `@api_data` decorator** when:
- Wrapping simple transformations
- Combining existing properties/data sources
- No complex acquisition logic needed

**Create custom `DataSource` subclass** when:
- Complex hardware acquisition (buffers, callbacks, state machines)
- Need fine control over threading/async
- Managing external resources (file handles, DLLs, etc.)

See `drivers/pico_technology/ps5000a.py` for a complex example (PicoScope with streaming buffers).

### Q: How do I handle multi-channel devices (e.g., 4-channel DDS)?

Create properties with channel-specific names:
```python
@api_property(min=0, max=100e6, unit="Hz")
async def ch1_frequency(self) -> float:
    return await self._run_blocking_in_thread(self._dev.get_frequency, channel=1)

@ch1_frequency.setter
async def ch1_frequency(self, value: float):
    await self._run_blocking_in_thread(self._dev.set_frequency, channel=1, freq=value)
```

Or use indexed pattern:
```python
@api_command
async def set_channel_freq(self, channel: int, frequency: float):
    await self._run_blocking_in_thread(self._dev.set_frequency, channel, frequency)
```

See `drivers/analog_devices/eval9959.py` for a multi-channel example.

## InfluxDB Integration

### Q: How do I enable InfluxDB telemetry?

1. Install InfluxDB (download from influxdata.com or use existing instance)
2. Create a bucket and get an API token from InfluxDB UI
3. In launcher: Configure → InfluxDB tab → Enable + fill in connection details
4. Restart server

All property changes and periodic snapshots will be logged.

### Q: What's the difference between batch size, flush interval, and snapshot interval?

- **Flush interval** (ms) - How often queued data points are sent to InfluxDB (default: 1000 = once per second)
- **Batch size** - Max data points sent per flush (default: 5000)
- **Snapshot interval** (s) - How often to capture full device state (default: 5.0 seconds)

**Example**: With 10 devices, 5 properties each, changing frequently:
- Snapshot every 5s = 50 data points queued
- Flush every 1s sends whatever is queued (up to batch_size limit)
- Batch size of 5000 is plenty for most use cases

Lower flush interval = more real-time, higher network/CPU usage.

### Q: Can I query InfluxDB data from my scripts?

Yes! Use InfluxDB's Python client or Flux queries:
```python
from influxdb_client import InfluxDBClient

client = InfluxDBClient(url="http://localhost:8086", token="YOUR_TOKEN", org="labhub")
query_api = client.query_api()

query = '''
from(bucket: "labhub")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "device_property")
  |> filter(fn: (r) => r.device_id == "picoscope")
  |> filter(fn: (r) => r.property == "sampling_frequency")
'''

tables = query_api.query(query)
for table in tables:
    for record in table.records:
        print(f"{record.get_time()}: {record.get_value()}")
```

## Custom GUIs

### Q: How do I add a custom GUI?

1. Build your web app (React/Vue/Svelte/anything) that talks to LabHub API
2. Build for production → get a `dist/` folder
3. In launcher: Configure → Custom GUIs tab → Add
4. Fill in:
   - **Device ID**: Unique name (e.g., "my_device_gui")
   - **Route**: URL path (e.g., "/mydevice")
   - **Dist Path**: Full path to dist folder
5. Restart server
6. Access at `http://127.0.0.1:8212/mydevice`

The GUI will appear in the launcher's tray menu automatically.

### Q: Can my custom GUI control multiple devices?

Yes! The `device_id` in server.yaml is just a label for the GUI, not the device it controls.

Your GUI can:
```javascript
// Control multiple devices
const devices = await fetch('/api/v2/devices').then(r => r.json());
await fetch('/api/v2/devices/picoscope/properties/sampling_frequency', {
    method: 'POST',
    body: JSON.stringify({value: 31250000})
});
await fetch('/api/v2/devices/laser/properties/power', {
    method: 'POST',
    body: JSON.stringify({value: 50})
});
```

However, note that the current picoscope GUI is hardcoded to one device - see tech-debt #32 for improving this.

### Q: Does my custom GUI need to be in the labhub repository?

No! The `dist` path in server.yaml can point anywhere:
- Inside repo: `gui/custom/my_gui/dist`
- External: `C:/projects/my_separate_gui/dist`
- Network share: `//server/share/guis/my_gui/dist`

Only the built dist folder needs to be accessible to the server.

## Client Libraries

### Q: Python vs Julia client - which should I use?

**Python** (`client/python/labhub.py`):
- ✅ Complete, tested
- ✅ Full type hints
- ✅ Supports properties, commands, data sources, events
- ✅ Stream data with async iteration

**Julia** (`client/julia/`):
- ⚠️ In progress, incomplete
- Use if you need Julia ecosystem (DifferentialEquations.jl, Plots.jl, etc.)

For new projects, use Python unless you specifically need Julia.

### Q: How do I stream data in the Python client?

```python
from client.python.labhub import Hub

hub = Hub("http://127.0.0.1:8212")
picoscope = hub.device("picoscope")

# Start a data source
stream_id = picoscope.start_data("trace", interval=0.1)

# Stream data (blocks until stopped)
for chunk in picoscope.stream_data(stream_id):
    print(f"Got {len(chunk)} samples")
    # Process chunk...

# Or async version
import asyncio

async def stream_async():
    async for chunk in hub.device("picoscope").stream_data_async(stream_id):
        print(f"Got {len(chunk)} samples")

asyncio.run(stream_async())
```

### Q: Can I use the API directly without a client library?

Yes! LabHub is a standard REST/WebSocket API:

```python
import httpx

# Read property
r = httpx.get("http://127.0.0.1:8212/api/v2/devices/picoscope/properties/sampling_frequency")
value = r.json()["value"]

# Write property
httpx.post("http://127.0.0.1:8212/api/v2/devices/picoscope/properties/sampling_frequency",
           json={"value": 31250000})

# Call command
result = httpx.post("http://127.0.0.1:8212/api/v2/devices/picoscope/commands/reset").json()

# List devices
devices = httpx.get("http://127.0.0.1:8212/api/v2/devices").json()
```

See auto-generated docs at `http://127.0.0.1:8212/docs` for full API reference.

## Development & Troubleshooting

### Q: How do I add a new driver?

See [Drivers.md](Drivers.md) for complete guide. Quick version:

1. Create `server/drivers/manufacturer/my_device.py`
2. Subclass `Device` with `api_alias` (optional, for short names)
3. Implement `__init__`, `connect()`, `disconnect()`
4. Add properties with `@api_property`, commands with `@api_command`, data sources with `@api_data`
5. Register in `server/drivers/__init__.py`

The driver will auto-appear in the "Add Device" dropdown in `/devices` GUI.

### Q: Where are log files stored?

By default, logs go to console only. To enable file logging:
1. Launcher → Configure → General tab → Log File
2. Pick a path (e.g., `C:/labhub/logs/labhub.log`)
3. Restart server

Or via CLI:
```bash
python launcher/launcher.py --log-file labhub.log --log-level DEBUG
```

### Q: How do I debug WebSocket events?

```javascript
const ws = new WebSocket('ws://127.0.0.1:8212/api/v2/events');
ws.onmessage = (event) => {
    console.log('Event:', JSON.parse(event.data));
};
```

Events include:
- `device_connected` / `device_disconnected`
- `property_changed`
- `command_started` / `command_completed` / `command_failed`
- `data_chunk`

Full state snapshot sent on WebSocket connect.

### Q: Can I run multiple LabHub servers on the same machine?

Yes, but they need different:
- Ports (e.g., 8212, 8213, 8214...)
- server.yaml files (each with different port configured)

Launch each with its own server.yaml:
```bash
python launcher/launcher.py --server-config launcher/server_setup1.yaml
python launcher/launcher.py --server-config launcher/server_setup2.yaml
```

Each launcher will run independently with its own tray icon (keyed by server.yaml path hash).

### Q: What does "locked_by" mean in device status?

Currently not implemented (#35 in tech-debt). The field exists but isn't enforced - multiple clients can control devices simultaneously. Coordination is manual.

## Platform & Installation

### Q: Does LabHub work on Linux/Mac?

**Partial support**:
- ✅ Core server runs on Linux/Mac
- ❌ Some drivers are Windows-only (Kinesis via pythonnet)
- ⚠️ No installer script yet (manual venv setup required)

See tech-debt #26/27 for progress on packaging.

### Q: Do I need to rebuild GUIs after updates?

**Built-in GUIs** (ui, devices, profile, macros): No - dist folders tracked in git

**Custom GUIs**: Yes - run `npm run build` in your GUI folder after changes, then restart server

### Q: How much Python knowledge do I need?

**To use LabHub**: None - interact via GUI or copy/paste client examples

**To write control scripts**: Basic Python (variables, functions, loops)

**To write drivers**: Intermediate Python (async/await, decorators, classes)

## Still Have Questions?

1. Check the full documentation in `/doc` folder
2. Look at example drivers in `server/drivers/example/`
3. Explore auto-generated API docs at `http://127.0.0.1:8212/docs`
4. Check source code - most modules have detailed docstrings
