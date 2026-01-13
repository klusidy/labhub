Labhub supports only a couple of devices (those that we use in our lab). Luckily, adding support for a new device was designed to be easy and convenient, even for inexperienced developers.

Each device requires a driver. These are organized in `server/drivers/<vendor>`.  Each driver is a python file `<device_type>.py` that must contain a class named `device_type`. For example if you have a portal gun, you would create the file `server/drivers/rick/portal_gun.py` with a `portal_gun` class that inherits from the universal `Device` class.

```python
from ..base import Device

@api_device()
class: portal_gun(Device)
	pass
```

> [!NOTE]  
> Usually, python projects use snake_case for file names and CamelCase for class names. In labhub, you must use the exact same string for class name and file name! 

Once such file is in place, you can add a device to your `config.yaml` with something like:
```yaml 
devices:
  - id: green_portal_gun    # unique name within your setup
    driver: rick.portal_gun # <vendor>.<device_type>
    serial_number: 1234            # whatever is needed to connect
```

The decorator `@api_device()` tells labhub that this is a device that should be made public through the API. Later we use other decorators for properties, commands and data streams. The parent `Device` class ensures that the server can properly manage the device. The driver should contain only the device-specific parts; all the inner plumbing is handled by labhub.

## Initialization and connection
For a device to properly function, its class must implement three core methods:
- `__init__()` for initializing and storing info form `config.yaml`
- `connect()` for establishing connection on startup
- `disconnect()` for safely closing the connection

For initialization, you must always initialize the base class so that it properly registers. Anything from the `config.yaml` is stored in the `options` dictionary. If anything goes wrong, simply raise an exception, it will be properly hanled by labhub (you will get an error message and other devices will connect normally).
```python
class: portal_gun(Device)
	def __init__(self, dev_id, options, manager):
		super().__init__(dev_id, options, manager) # always initialize base class
		# your code goes here ↓↓↓
		if "serial_number" in options:
			self.serial = options["serial_number"]
		else:
			raise KeyError("serial_number needed for portal gun")
```
For connecting, you should do whatever is needed for extablishing a connection - vendors usually provide an example script so you can copy-paste that. Remember to store whatever reference you need later into `self`. You must return `True` if the connection was successful (or `False` if it was not) so that labhub can operate the device properly. 

> [!NOTE]  
> Initialization should be fast in order not to block the server (just store what you need and leave). Connect is done in a separate thread for each device so any long synchronous calls should go there (connect may be an async method but at no real benefit)

## Properties and commands
Each labhub device is basically a set of properties and commands. Property is something with a numeric (or string or bool) value - for example voltage, pressure, position, etc. Properties are periodically polled and exposed to clients. A command is, well, a command; you tell the device what to do and it does it. 




## Data sources