# Architecture

This page is a more technical deep-dive into how *Labhub* works under the hood. For a gentler introduction, check out [[Introduction]].

## System Overview

*Labhub* follows a classic client-server architecture. The **server** connects to hardware devices and exposes their capabilities through a unified API. Various **clients** (web GUIs, Python scripts, Julia notebooks) communicate with the server over HTTP and WebSockets.

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENTS                              │
│  ┌──────────┐  ┌────────────────┐  ┌──────────────┐     │
│  │ Web GUIs │  │ Python Client  │  │ Julia Client │     │
│  └──────────┘  └────────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────┘
                    ↕ HTTP + WebSocket
┌─────────────────────────────────────────────────────────┐
│                  LABHUB SERVER                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Device Manager                       │  │
│  │    ┌─────────┐ ┌─────────┐ ┌─────────┐            │  │
│  │    │ Device  │ │ Device  │ │ Device  │  ...       │  │
│  │    │ Driver  │ │ Driver  │ │ Driver  │            │  │
│  │    └─────────┘ └─────────┘ └─────────┘            │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                    ↕ Vendor APIs
┌─────────────────────────────────────────────────────────┐
│                    HARDWARE                             │
│     Thorlabs   ·   NKT   ·   PicoScope   ·   etc.       │
└─────────────────────────────────────────────────────────┘
```

This separation provides several benefits:
- **Multiple clients** can access devices simultaneously
- **Different languages** can be used for scripting (Python, Julia, MATLAB)
- **Hardware isolation** - device crashes don't affect the server
- **Remote access** - connect from other machines on the network

## Server Components

The server (`server/main.py`) is built on [FastAPI](https://fastapi.tiangolo.com/), a modern Python web framework. It has several key subsystems:

### Device Manager

The heart of *Labhub*. It handles device lifecycle:
1. **Initialization** - creates device instances from [[Configuration]]
2. **Connection** - connects to hardware (in parallel for speed)
3. **Polling** - periodically reads device state (~2Hz by default)
4. **State routing** - forwards API calls to appropriate devices
5. **Cleanup** - safely disconnects devices on shutdown

### Event Bus

A simple publish-subscribe system for real-time updates. When a device property changes, the event bus notifies all connected WebSocket clients. This is how the [[GUIs]] stay synchronized.

### Profile Monitor

Periodically saves device state to `profile.yaml`. This enables restoring device settings between sessions. See [[Configuration#User profile (profile.yaml)]] for details.

### InfluxDB Writer (optional)

If you need long-term logging of device values, *Labhub* can push data to [InfluxDB](https://www.influxdata.com/). Great for tracking experiments over time. See [[Logging (InfluxDB integration)]] for setup.

## API Endpoints

The server exposes a REST API for querying and controlling devices. Full documentation is always available at `http://127.0.0.1:8212/docs` (assuming default port).

Here are the key endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/devices` | GET | List all devices with current state |
| `/api/v2/devices/{id}` | GET | Get single device state |
| `/api/v2/devices/{id}` | PATCH | Update device properties |
| `/api/v2/devices/{id}/spec` | GET | Get device capabilities |
| `/api/v2/devices/{id}/commands` | POST | Execute a command |

### WebSocket Endpoints

For real-time updates, the server provides WebSocket endpoints:

- `/api/v2/events` - broadcasts device state changes to connected clients
- `/api/v2/streams/{id}/{source}` - streams data from data sources (e.g., oscilloscope traces)

> [!TIP]
> If you're building a custom client, start with the REST API for simplicity. Add WebSocket subscriptions later when you need real-time updates.

## Driver System

Each device type needs a *driver* - a Python class that knows how to talk to that specific hardware. Drivers live in `server/drivers/<vendor>/<device_type>.py`.

The driver system uses Python decorators to expose device capabilities:

```python
from ..base import Device, api_device, api_property, api_command

@api_device()
class my_device(Device):

    @api_property(unit="V", min=0, max=10)
    def voltage(self) -> float:
        """Output voltage"""
        return self._read_voltage()

    @voltage.setter
    def voltage(self, value: float):
        self._write_voltage(value)

    @api_command()
    def reset(self) -> dict:
        """Reset device to factory defaults"""
        self._do_reset()
        return {"success": True}
```

The decorators automatically:
- Generate API endpoints
- Create documentation
- Validate input values (type, range, choices)
- Handle threading (blocking calls run in a thread pool)

For more details on writing drivers, see [[Drivers]].

## Data Flow Examples

### Reading a Property

```
1. Client:   GET /api/v2/devices/laser1
2. Server:   device_manager.get_device_state("laser1")
3. Driver:   Returns cached property values
4. Server:   Responds with JSON { "power": 0.5, "enabled": true, ... }
5. Client:   Displays values in UI
```

### Writing a Property

```
1. Client:   PATCH /api/v2/devices/laser1 { "power": 0.8 }
2. Server:   device_manager.apply_properties("laser1", {"power": 0.8})
3. Driver:   Sets hardware value, updates cache
4. EventBus: Broadcasts state change to all WebSocket clients
5. Monitor:  Saves new value to profile.yaml
6. Server:   Responds with updated state
7. Other clients: Receive WebSocket notification, update their UIs
```

### Executing a Command

```
1. Client:   POST /api/v2/devices/stage1/commands { "name": "home" }
2. Server:   device_manager.run_command("stage1", "home", {})
3. Driver:   Executes homing routine (may take seconds/minutes)
4. Server:   Responds with command result
5. EventBus: Broadcasts state change (position updated)
```

## Thread Model

*Labhub* uses an async-first design with careful threading:

- **Main thread** - runs the FastAPI event loop, handles HTTP/WebSocket
- **Polling tasks** - async tasks that periodically read device state
- **Thread pool** - executes blocking hardware calls (property setters, commands)

> [!NOTE]
> Device drivers don't need to worry about threading. The server handles it automatically - just write synchronous code and *Labhub* will run it in the right context.

## Startup Sequence

When you start *Labhub* (via [[Launcher]] or command line):

1. **Lock acquisition** - prevents multiple servers on same config
2. **Config loading** - reads `config.yaml`, validates device definitions
3. **Device creation** - creates all device instances in parallel
4. **Connection** - each device connects to its hardware
5. **Polling starts** - begins periodic state reads
6. **Profile loading** - restores previous device settings from `profile.yaml`
7. **InfluxDB init** - starts telemetry writer (if enabled)
8. **Server ready** - API is now accessible

Shutdown is the reverse - disconnect devices, save profile, release lock.

## File Organization

```
labhub/
├── server/
│   ├── main.py          # FastAPI app, API endpoints
│   ├── device_manager.py # Device lifecycle management
│   ├── events.py        # Pub-sub event bus
│   ├── monitor.py       # Profile auto-save
│   ├── influx.py        # InfluxDB integration
│   ├── loader.py        # Config/profile YAML parsing
│   ├── schemas.py       # Pydantic models
│   └── drivers/         # Device drivers
│       ├── base.py      # Base class and decorators
│       ├── kinesis/     # Thorlabs Kinesis devices
│       ├── nkt/         # NKT Photonics lasers
│       └── ...
├── launcher/
│   ├── launcher.py      # System tray application
│   └── config_*.yaml    # Configuration files
├── client/
│   ├── python/          # Python scripting client
│   └── julia/           # Julia scripting client
└── gui/
    ├── basic2/          # Main web GUI (Vue/TypeScript)
    ├── devices/         # Device admin GUI
    └── profile/         # Profile admin GUI
```

## Single Instance Lock

*Labhub* prevents running multiple servers with the same configuration. This avoids conflicts when two processes try to control the same hardware.

The lock is a simple file lock on the config path. If you see an error about the config being locked, check for other running instances.

## See Also

- [[Introduction]] - high-level overview for users
- [[Configuration]] - setting up config and profile files
- [[Drivers]] - writing custom device drivers
- [[Python Client]] - scripting with the Python client
- [[GUIs]] - using the web interfaces
