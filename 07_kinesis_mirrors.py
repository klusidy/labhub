from __future__ import annotations
import os, asyncio
from typing import Any, Dict, Optional
import time

kinesis_path = r"C:/Program Files/Thorlabs/Kinesis"  # optional if KINESIS_PAT

import clr  # type: ignore
from pathlib import Path
base = Path(kinesis_path)

clr.AddReference(str(base / "Thorlabs.MotionControl.DeviceManagerCLI.dll"))
clr.AddReference(str(base / "Thorlabs.MotionControl.GenericMotorCLI.dll"))
clr.AddReference(str(base / "ThorLabs.MotionControl.KCube.InertialMotorCLI.dll"))

# Imports after AddReference
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.GenericMotorCLI import GenericMotorCLI
from Thorlabs.MotionControl.KCube.InertialMotorCLI import KCubeInertialMotor, InertialMotorStatus, ThorlabsInertialMotorSettings, InertialMotorJogMode


DeviceManagerCLI.BuildDeviceList()

serial = "97101498"

device = KCubeInertialMotor.CreateKCubeInertialMotor(serial)
device.Connect(serial)

device_info = device.GetDeviceInfo()
print(device_info.Description)

inertial_motor_config = device.GetInertialMotorConfiguration(serial)
device_settings = ThorlabsInertialMotorSettings.GetSettings(inertial_motor_config)

chan1 = InertialMotorStatus.MotorChannels.Channel1  # enum chan ident
chan2 = InertialMotorStatus.MotorChannels.Channel2
chan3 = InertialMotorStatus.MotorChannels.Channel3
chan4 = InertialMotorStatus.MotorChannels.Channel4

device_settings.Drive.Channel(chan1).StepRate


from System import Action  # type: ignore


js = device.GetJogParameters(chan1)

# InertialMotorJogMode

# InertialMotorCLi
# ChannelStatus
# DeviceConfiguration
# DisableChannel
# DisableDevice
# EnableChannel
# GetConnectionState
# GetDevParams
# GetDeviceInfo
# GetDriveParameters
# GetHomeParameters
# GetInertialMotorConfiguration
# GetJogParameters ReguestJogParameters SetJogParameters
# GetSettings
# Jog(MotorChannels, InertialMotorJogDirection, action void Jog(MotorChannels, Direction, Int32))