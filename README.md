# Labhub

A convenient, easy-to-use, robust and extensible tool for lab automation. Connect multiple instruments from different vendors to a single server, then control them from web GUIs or scripts in Python, Julia, or MATLAB.

## Why Labhub?

You work in a lab with instruments from various vendors - Thorlabs, National Instruments, PicoScope, custom Arduino setups. Each has its own software, its own API, its own quirks. Your colleague prefers Julia, your supervisor uses MATLAB, and you're comfortable with Python.

**Labhub** solves this by providing:
- **Unified API** - one interface for all your devices
- **Multiple clients** - Python, Julia, web GUI, all connected simultaneously
- **Real-time sync** - changes from one client appear in all others instantly
- **Session persistence** - restore your setup from last time with one click

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://svn.isibrno.cz/levifot/labhub.git
   cd labhub
   ```

2. Run the installer:
   ```bash
   ./install.bat
   ```

3. Start Labhub:
   ```bash
   ./run.bat
   ```

4. Open the web GUI at `http://127.0.0.1:8212/ui`

## Documentation

| Document | Description |
|----------|-------------|
| [Introduction](doc/Introduction.md) | High-level overview and motivation |
| [Installation](doc/Installation.md) | Step-by-step setup guide |
| [Configuration](doc/Configuration.md) | Setting up devices and profiles |
| [Launcher](doc/Launcher.md) | Using the system tray application |
| [GUIs](doc/GUIs.md) | Web-based user interfaces |
| [Python Client](doc/Python%20Client.md) | Scripting with Python |
| [Drivers](doc/Drivers.md) | Writing custom device drivers |
| [Architecture](doc/Architecture.md) | Technical deep-dive |

## Example Usage

```python
import client.python as lhc

lhc.connect("127.0.0.1", 8212)

# Read a property
print(lhc.laser.power)  # 0.5

# Set a property
lhc.laser.power = 0.8

# Execute a command
lhc.stage.home()
```

## Supported Devices

Labhub currently supports devices from:
- Thorlabs (Kinesis motion controllers)
- NKT Photonics (lasers)
- PicoScope (oscilloscopes)
- Analog Devices (DDS boards)
- Custom/Arduino devices

Adding support for new devices is straightforward - see the [Drivers](doc/Drivers.md) documentation.

## Contributing

Contributions are welcome! The more devices we support, the more useful Labhub becomes. See the contribution section in [Introduction](doc/Introduction.md) for details.

## Contact

Labhub is developed by the levitation photonics group at the [Institute of Scientific Instruments](https://isibrno.cz) of the Czech Academy of Sciences.

Contact: klusacek@isibrno.cz
