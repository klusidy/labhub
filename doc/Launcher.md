# Launcher

The Launcher is a convenience GUI for operating the Labhub Server.
After starting the Launcher an icon will appear in the system tray and the server is started automatically. 

Green icon indicates that the server is up and running. If the server is stopped (or crashes) the icon will turn red.
![[launcher_tray.png]]

The following actions are available:
- **Start / Stop server**
- **Configure** - shows a pop-up window where you can set up configuration files
- **Launch GUI** – shows the [basic GUI](GUIs.md) in the browser (useful for browsing connected devices)
- **More** – shows live device or profile configuration or the underlying FastAPI docs in the browser (useful for developing [custom clients](Python%20Client.md))
- **Quit** – stops the server and exits
# Start
When you click on **Start**, launcher starts the *Labhub* server. It passes to it all the paths to configuration files and some other parameters (like port where the server will be running).

When the server is running, you'll see a **Stop** option instead.
## Configure

The **Configure** option show this pop-up window. Bulk of Labhub configuration happens via .yaml files. The "Device configuration" specifies which devices will Labhub try to connect to, the "Profile" specifies a file which stores most recent snapshot of all the devices and which may be used to restore a previous session.

![[launcher_configure.png]]
There is a separate page about [[configuration]]

These files cannot be replaced by other at runtime – the only way  is to stop the server, pick a different file, then start the server again. It is possible, however, to change the contents of these files (see [[GUIs]]).
# How to start the Launcher

The most convenient way is by running the `run.bat` that was generated during installation. It does not provide any configuration by default – all options are persisted from last time. The script can be copy-pasted outside its original folder or modified in a text editor.

The `run.bat` script actually starts the launcher via this command:
```cmd
(.venv) python .\launcher\launcher.py [-h] [--config CONFIG] [--profile PROFILE] [--host HOST] [--port PORT]

Start LabHub Launcher

options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to config.yaml 
  --profile PROFILE     Path to profile.yaml 
  --host HOST           Host for the hub server 
  --port PORT           Port for the hub server 
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging level 
  --log-file LOG_FILE   Optional path to log file 
  --no-influx           Disable InfluxDB integration even if configured
  
options:
  -h, --help            show this help message and exit
  --config CONFIG       Path to config.yaml
  --profile PROFILE     Path to profile.yaml 
  --host HOST           Host for the hub server, default is 127.0.0.1 (localhost)
  --port PORT           Port for the hub server, default is 8212
```
All arguments are optional; specify them only when you wish to override settings from last time.

If you have several configuration files for some reason, it is recommended to always provide `--config` and `--profile` options to keep things tidy.

It is also possible to use this command in other IDEs like VS Code tasks:

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