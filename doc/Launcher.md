# Launcher

The Launcher is a convenience GUI for operating the Labhub Server.
After starting the Launcher an icon will appear in the system tray and the server is started automatically. 

Green icon indicates that the server is up and running. If the server is stopped (or crashes) the icon will turn red.

![[img/server_tray.png]]

The following actions are available:
- **Start / Stop server**
- **Launch GUI** – shows the [basic GUI](GUI) in the browser (useful for browsing connected devices)
- **Open API docs** – shows the underlying FastAPI docs in the browser (useful for developing [custom clients](Clients))
- Config
- Profile

# Start
The Launcher can be started from the command line:
```cmd
python .\launcher\launcher.py [-h] [--config CONFIG] [--profile PROFILE] [--host HOST] [--port PORT]

Start LabHub Launcher

options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to config.yaml
  --profile PROFILE     Path to profile.yaml (optional)
  --host HOST           Host for the hub server, default is 127.0.0.1 (localhost)
  --port PORT           Port for the hub server, default is 8212
```
All aguments are optional, but for useful operation you should provide at least path to the device configuration file

## Device configuration (config.yaml)
This file stores a list of devices that LabHub server will connect to. Ideally, this file is only touched when adding/removing a device.

Each device must come with a unique identificator (a name) and a path to a [driver](Drivers). The default `config_default.yaml` looks like this:
```yaml
devices:
  - id: "foo"                  # <-- unique name for a device
    driver: "example_device"   # <-- driver (device type)
    serial_number: "EX123"     # <-- other parameters for successfull connection
  - id: "bar"                  # <-- different device of the same type
    driver: "example_device"
    serial_number: "EX456"
```
Each driver comes with a list of parameters which are required for successfull connection. Look for example configuration in the driver file, copy-paste it and edit correct specific values.
## User profile (profile.yaml)
While device configuration keeps track of connected devices, user profile keeps track of the state of each connected device. The profile.yaml stores values of all properties and is able to load them back to the server. 

When a profile is loaded (either on startup or later), the values are set up on the server. When a property value changes, the server will reflect this change in the current profile file. Therefore, the profile file **always keeps track of the current values**.

The intention is to avoid repeating steps when setting up an experiment. If you keep using the same profile file, it will always load the values from the last time. You can store a particular snapshot by manually copying current profile. 

TODO - example once it works

# VS Code
If you use VS code for LabHub, it is possible to set up so-called "tasks" for different configurations/profiles. To do so, create `.vscode/tasks.json` file that with something like this:

```json
{

  "version": "2.0.0",
  "tasks": [
    {
      "label": "Launch Labhub",
      "type": "shell",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": [
        "${workspaceFolder}/launcher/launcher.py",
        "--config",
        "<PATH-TO-YOUR-CONFIG-FILE>"
        "--profile",
        "<PATH-TO-YOUR-PROFILE-FILE>"
      ],
      "presentation": {
        "reveal": "always",
        "panel": "new"
      },
      "problemMatcher": []
    },
  ]
}
```
The task (which starts the Launcher which starts the Server) can be then run from 
`Command Palette (Ctrl+Shift+P) -> Tasks: Run Task --> Launch Labhub`