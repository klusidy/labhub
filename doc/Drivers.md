Labhub supports only a several devices (those that we use in our lab). Luckily, adding support for a new device was designed to be easy and convenient, even for inexperienced developers.

Each device requires a driver. These are organized in `server/drivers/<vendor>`.  Each driver is a python file `<device_type>.py` that must contain a class named `device_type`. For example if you had a portal gun, you would create the file `server/drivers/rick/portal_gun.py` with a `portal_gun` class that inherits from the universal `Device` class:

```python
# /server/drivers/rick/portal_gun.py
from ..base import Device

@api_device()
class: portal_gun(Device)
	pass
```

The decorator `@api_device()` tells labhub that this is a device that should be made public through the API. Later we use other decorators for properties, commands and data streams. The parent `Device` class ensures that the server can properly manage the device. The driver should contain only the device-specific parts; all the inner plumbing is handled by labhub.

> [!NOTE]  
> Usually, python projects use snake_case for file names and CamelCase for class names. In labhub, you can use eithre, but it must be the exact same string for class name and file name! 

Once such file is in place, you can add a device to your `config.yaml` with:
```yaml 
devices:
  - id: green_portal_gun    # unique name within your setup
    driver: rick.portal_gun # <vendor>.<device_type>
    serial_number: 1234     # whatever is needed to connect
```
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
```python
import RickControlLibrary   # whatever enables connecting device to python script
class portal_gun(Device):
	...
	def connect(self):
		try:
			self._lib = RickControlLibrary("connect", self.serial)
			return True
		except:
			return False
		
```

> [!NOTE]  
> Initialization should be fast in order not to block the server (just store what you need and leave). Connect is done in a separate thread for each device so any long synchronous calls should go there (connect may be an async method but at no real benefit - it is started in a separate thread for each device)

## Properties and commands

A labhub device is basically a set of properties and commands. A *property* is something with a numeric (or string or bool) value - for example voltage, pressure, position, etc. Properties are periodically polled and exposed to clients. A *command* is, well, a command; you tell the device what to do and it does it. Commands are typically for more complex or longer lasting actions.

> [!TIP]  
> Sometimes, it is not clear whether to use properties or commands for something. Use whatever feels more practical and readable. 
>

### Properties
A property works in a similar way to python's [property decorator](https://docs.python.org/3/library/functions.html#property). It requires a getter (a funcition to obtain a value) and optionally a setter (without a setter the property becomes read-only). The only difference is that instead of the `@property` decorator, you use `@api_property()` decorator. 

```python
class: portal_gun(Device)
	...
	@api_property(min=0.1, max=10, unit="m") 
	def diameter(self) -> float:
		"""Diameter of the portal to be created"""
		return self._lib("get_diameter")
		
	@diameter.setter
	def diameter(self, value:float):
		self._lib("set_diameter", value)
		return
```

Remember to use [type hints](https://docs.python.org/3/library/typing.html) and [doc strings](https://docs.python.org/3/glossary.html#term-docstring) – labhub exctract its information to properly build the API and validate input values. You can supply additional information throught the `api_property` parameters (min/max for bounds, choices to limit string options, unit for clarity on numeric values). Properties should be either `float`, `int`, `string` or `bool`; composite data types are not supported. 

### Commands
To publish a class method as a command to the API, simply decorate it with `@api_command()`.

``` python
class portal_gun(Device):
	...
	@api_command()
	def open(self, destination: string, fallback) -> dict:
		"""Attempts to find desired destination and opens portal there"""
		dst = self._lib("find_destination", destination)
		if dst:
			result = self._lib("open_portal", dst)
			return { success: True, 
			         danger_level: result["danger"],
			         fun_level: result["danger"]
			       }
		else:
			return { success: False,
					 message: "destination not found"
				   }
```

Both commands and property setters are run by labhub asynchronously in threads separate from the main one so that the server is not blocked by (potentially slow) execution.


## Data sources