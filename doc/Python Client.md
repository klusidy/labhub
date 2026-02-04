The main strenght of *Labhub* is the fact that it bundles together multiple devices from different vendors into a synchronized single point of truth for many different clients.

Besides various [[GUIs]], one such client is a python scripting client. It enables writing scripts that can modify values of properties, read the current state or invoke commands.

The client consist of two file (`client.py`and `__init__.py`) in the `/client/python` folder.

You just need to import the client (either by setting up an import path or by copy-pasting it to your project). You don't even have to use the same python interpreter that is bundled together with *Labhub*.

Connecting to Labhub is then fairly simple. The client also provides rich documentation on all connected devices

```python
>>> import client.python as lhc
>>> lhc.connect("127.0.0.1", 8212)
>>> print(lhc) # prints docs

trying to __init__ Hub with base_url http://127.0.0.1:8212
labhub (127.0.0.1:8212) has the following devices:
  .filtration_cavity  KCube Piezo Controller (KPZ101)
  .mirrors            K-Cube Inertial Motor Controller (KIM101)
  .chammber_pressure_gauge TPG pressure sensor (vacuum gauge)
  .AD_DDS             Analog Devices EVAL-AD9959 DDS evaluation board.

Uses subprocess bridge to communicate with 32-bit AD DLL from 64-bit Python.
Bridge communicates via stdin/stdout, serialized by base class _lock.
  .picoscope          PicoScope 5000a series driver.
This driver requires the PicoSDK to be installed.
  .half_plate         Stepper Motor Rotation Mount (K10CR1)
```

The documentation feature extends to devices and even individual commands/properties:
```python
>>> lhc.half_plate
half_plate  [?]
Stepper Motor Rotation Mount (K10CR1)

Parameters:
  .position: float = 0.0  # Position in real-world units (degrees)

Commands:
  .move_to(value: float)
  .drive_up(velocity: float)
  .drive_down(velocity: float)
  .home()
  .set_jog_parameters(jog_mode: str, step_size: float = 5, acceleration: float = 15, max_velocity: float = 15)

```
Reading out properties is also straightforward
```python
>>> lhc.half_plate.position                
position: float [deg]  (read-write)
  value=0.0

Position in real-world units (degrees)
```
As is invoking commands:
```python
>>>lhc.half_plate.move_to(value=5.0)
5.0
```
### Other clients
Similar clients for scripting in julia or MATLAB are, in principle, possible and are planned for the future