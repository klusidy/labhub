*Labhub* is configured via a pair of configuration files. They use the human-readable .yaml format that can be open in any text editor. They specify what devices will *Labhub* (try to) connect to and what to do with them upon startup.
## Device configuration (config.yaml)
This file stores a list of devices that LabHub server will connect to. This file is only touched when adding/removing a device.

Each device must come with a unique identificator (a name) and a path to a [driver](Drivers). The default `config_default.yaml` looks like this:
```yaml
devices:
  - id: "foo"                          # <-- unique name for a device
    driver: "example.example_device"   # <-- driver (device type)
    serial_number: "EX123"             # <-- other parameters for successfull connection
  - id: "bar"                          # <-- different device of the same type
    driver: "example.example_device"
    serial_number: "EX456"
```
Each driver comes with a list of parameters which are required for successfull connection. Look for example configuration in the driver file, copy-paste it and edit correct specific values.

## Device GUI

Path to a configuration file cannot be changed during runtime, but its contents may.
There is a device admin interface at `http://127.0.0.1:8212/devices`.

![[device_gui.png]]
This interface basically shows the contents of the configuration file, together with options to add new device (from available drivers) or to modify its connection options. It is also possible to re-connect to a device to test whether it is configured properly.
## User profile (profile.yaml)
While device configuration keeps track of connected devices, user profile keeps track of the state of each connected device. The profile.yaml stores values of all properties and is able to load them back to the server. 

When a profile is loaded (either on startup or later), the values are set up on the server. When a property value changes, the server will reflect this change in the current profile file. Therefore, the profile file **always keeps track of the current values**.

The intention is to avoid repeating steps when setting up an experiment. If you keep using the same profile file, it will always load the values from the last time. You can store a particular snapshot by manually copying current profile. 
### Read/Write policy
Sometimes, it may be useful NOT to write a new value when loading up a server. Maybe the value was updated from a different program, maybe writing a value may interfere with a locked system.

For this, each property comes with a profile "policy":
- `policy: read` means that this value from a profile file is never loaded. Current values are still tracked in the profile file, but its never used for anythin
- `policy: write` means that this value from a profile is loaded only if it differs from value already on the server. This prevents re-writing to the same value (which may cause hiccups in time-sensitive experiments, e.g. locking frequencies)

### Profile GUI
Changing policies manually in a file may be a bit tedious, so there is a profile interface to do exactly that at `http://127.0.0.1:8212/profile.

![[profile_gui.png]]