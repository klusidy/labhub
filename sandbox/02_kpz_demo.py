serial = "29251095"         # <- your device serial

from __future__ import annotations
import os, asyncio
from typing import Any, Dict, Optional
import time


#serial = "28591066"

kinesis_path = r"C:/Program Files/Thorlabs/Kinesis"  # optional if KINESIS_PAT


import clr  # type: ignore
from pathlib import Path
base = Path(kinesis_path)

dm = base / "Thorlabs.MotionControl.DeviceManagerCLI.dll"
pz = base / "Thorlabs.MotionControl.KCube.PiezoCLI.dll"

if not (dm.exists() and pz.exists()):
    raise RuntimeError(f"Kinesis DLLs not found under {base}")

clr.AddReference(str(dm))
clr.AddReference(str(pz))
# Imports after AddReference
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
from Thorlabs.MotionControl.KCube.PiezoCLI import KCubePiezo  # type: ignore
from System import Decimal  # type: ignore


DeviceManagerCLI.BuildDeviceList()

device = KCubePiezo.CreateKCubePiezo(serial)

device.Connect(serial)

# Get Device Information and display description
#device_info = device.GetDeviceInfo()
#print(device_info.Description)

# Start polling and enable
device.StartPolling(250)  #250ms polling rate
time.sleep(0.25)
device.EnableDevice()
time.sleep(0.25)  # Wait for device to enable

if not device.IsSettingsInitialized():
    device.WaitForSettingsInitialized(2000)  # 10 second timeout
    assert device.IsSettingsInitialized() is True

# Load the device configuration
#device_config = device.GetPiezoConfiguration(serial)

# This shows how to obtain the device settings
#device_settings = device.PiezoDeviceSettings

# Set the Zero point of the device
#print("Setting Zero Point")
#device.SetZero()

#Get the maximum voltage output of the KPZ
max_voltage = device.GetMaxOutputVoltage()  # This is stored as a .NET decimal
print(f'Max voltage {max_voltage}')
device.SetMaxOutputVoltage(max_voltage)

# Go to a voltage
dev_voltage = Decimal(0.29)
print(f'Going to voltage {dev_voltage}')
device.SetOutputVoltage(dev_voltage)


if dev_voltage != Decimal(0) and dev_voltage <= max_voltage:
    timeout = time.time() + 30
    device.SetOutputVoltage(dev_voltage)
    while (device.IsSetOutputVoltageActive()):
        time.sleep(30)
        if time.time() < timeout:
            raise Exception("Timeout Exceeded")
    print(f'Moved to Voltage {device.GetOutputVoltage()}')
else:
    print(f'Voltage must be between 0 and {max_voltage}')

# Stop Polling and Disconnect
device.StopPolling()
device.Disconnect()


