'''
Module to connect to Thorlabs PAX1000 polarimeter, take measurements
After installing software,
A list of API functions can be found under corresponding folder,
For example: file:///C:/Program%20Files%20(x86)/IVI%20Foundation/VISA/WinNT/TLPAX/Manual/TLPAX_files/Hierarchical%20Function%20Index.html

Author: Y. Chen
Date: 20th December 2021
'''

import ctypes
from ctypes import c_int, c_double, c_bool, c_char_p, c_ulong, c_ushort, byref
from multiprocessing.resource_sharer import stop
import threading
import time
import csv
import os
from ctypes import cdll
from typing import Any, Dict

# Try to load the DLL from the same directory as this script
current_dir = os.path.dirname(os.path.abspath(__file__))
dll_path = os.path.join(current_dir, "TLPAX_64.dll")

try:
    lib = cdll.LoadLibrary(dll_path)
except OSError as e:
    raise FileNotFoundError(f"Could not find TLPAX_64.dll at {dll_path}. Make sure the DLL file is in the same directory as this script.") from e

# Optional system DLL location used by alignment helpers.
_DLL_PATH = r"C:\Program Files\IVI Foundation\VISA\Win64\Lib_x64\msc"
_DLL_NAME = "TLPAX_64.dll"
_dll_cache = None


def _get_dll() -> ctypes.CDLL:
    """Load and configure the TLPAX DLL (cached after first call)."""
    global _dll_cache
    if _dll_cache is not None:
        return _dll_cache

    candidate_paths = [
        os.path.join(_DLL_PATH, _DLL_NAME),
        dll_path,
    ]

    last_error = None
    dll = None
    for candidate in candidate_paths:
        try:
            dll = ctypes.cdll.LoadLibrary(candidate)
            break
        except OSError as exc:
            last_error = exc

    if dll is None:
        # Fall back to the globally loaded library if available.
        dll = lib
        if dll is None:
            raise FileNotFoundError(
                f"Could not load {_DLL_NAME} from {candidate_paths}"
            ) from last_error

    dll.TLPAX_getMeasurementData.restype = ctypes.c_int32
    dll.TLPAX_getMeasurementData.argtypes = [
        ctypes.c_uint32,                      # instrumentHandle
        ctypes.POINTER(ctypes.c_double),      # optPower
        ctypes.POINTER(ctypes.c_double),      # phaseRetardation
        ctypes.POINTER(ctypes.c_double),      # normalizedS0
        ctypes.POINTER(ctypes.c_double),      # normalizedS1
        ctypes.POINTER(ctypes.c_double),      # normalizedS2
        ctypes.POINTER(ctypes.c_double),      # normalizedS3
        ctypes.POINTER(ctypes.c_double),      # DOP
        ctypes.POINTER(ctypes.c_double),      # azimuth
        ctypes.POINTER(ctypes.c_double),      # ellipticity
        ctypes.POINTER(ctypes.c_double),      # powerPolarized
        ctypes.POINTER(ctypes.c_double),      # powerUnpolarized
        ctypes.POINTER(ctypes.c_double),      # alignmentAid
    ]

    _dll_cache = dll
    return dll


def _normalize_handler(handler: Any) -> ctypes.c_uint32:
    """Normalize different handle container types to c_uint32."""
    if hasattr(handler, "value"):
        handler_value = int(handler.value)
    else:
        handler_value = int(handler)
    if handler_value < 0:
        raise ValueError("Instrument handle must be a non-negative integer")
    return ctypes.c_uint32(handler_value)


def get_alignment_reading(handler: Any) -> Dict[str, Any]:
    """Take one measurement and return values relevant to alignment."""
    dll = _get_dll()
    normalized_handler = _normalize_handler(handler)

    opt_power = ctypes.c_double(0.0)
    phase_ret = ctypes.c_double(0.0)
    s0 = ctypes.c_double(0.0)
    s1 = ctypes.c_double(0.0)
    s2 = ctypes.c_double(0.0)
    s3 = ctypes.c_double(0.0)
    dop = ctypes.c_double(0.0)
    azimuth = ctypes.c_double(0.0)
    ellipticity = ctypes.c_double(0.0)
    pwr_polarized = ctypes.c_double(0.0)
    pwr_unpolarized = ctypes.c_double(0.0)
    alignment_aid = ctypes.c_double(0.0)

    status = dll.TLPAX_getMeasurementData(
        normalized_handler,
        ctypes.byref(opt_power),
        ctypes.byref(phase_ret),
        ctypes.byref(s0),
        ctypes.byref(s1),
        ctypes.byref(s2),
        ctypes.byref(s3),
        ctypes.byref(dop),
        ctypes.byref(azimuth),
        ctypes.byref(ellipticity),
        ctypes.byref(pwr_polarized),
        ctypes.byref(pwr_unpolarized),
        ctypes.byref(alignment_aid),
    )

    if status != 0:
        raise RuntimeError(
            f"TLPAX_getMeasurementData failed (status {status:#010x}). "
            "Ensure the device is connected and in an active measurement mode."
        )

    aid_value = alignment_aid.value
    return {
        "opt_power": opt_power.value,
        "alignment_aid": aid_value,
        "is_aligned": aid_value >= 0.90,
    }


def get_alignment_percent(handler: Any) -> float:
    """Return beam alignment as a percentage (0.0 - 100.0)."""
    reading = get_alignment_reading(handler)
    return float(reading["alignment_aid"]) * 100.0

from httpx import delete
import pyvisa

cwd = os.getcwd()
os.chdir(r"C:\Program Files\IVI Foundation\VISA\Win64\Bin")

class Polarimeter:
    """
        Class for dealing with connecting to PAX1000 polarimeter
    """
    def __init__(self, resource=None, measureMode=9, wavelength=0.000000532):
        '''
        Constructor
        :type resource: string with utf-8 coded, see here: https://stackoverflow.com/questions/6269765/what-does-the-b-character-do-in-front-of-a-string-literal;
          measureMode: int;
          wavelength: double
        :param resource: resource identifier to the polarimeter, i.e. b'USB0::0x1313::0x8031::M00766101::INSTR';
           measureMode: the measure mode from 0-9;
           wavelength: wavelength of your laser
        '''
        self.handler = c_ulong()
        self.deviceCount = c_int()
        self.modelName = c_char_p(b"")
        self.serialNumber = c_char_p(b"")
        self.manufacturer = c_char_p(b"")
        self.deviceAvailable = c_bool()

        self.resource = resource
        self.IDQuery = True
        self.resetDevice = False
        self.measureMode = measureMode
        self.wavelength = wavelength

    def getResourceID(self):
        rm = pyvisa.ResourceManager()
        print("Devices found:")
        print(rm.list_resources())
    
    def getNumOfDev(self):
        lib.TLPAX_findRsrc(self.handler, byref(self.deviceCount))
        print("Number of available devices: {}".format(self.deviceCount.value))

    def getDevModel(self):
        lib.TLPAX_getRsrcInfo(0, 0, self.modelName, 0, 0, byref(self.deviceAvailable))
        lib.TLPAX_getRsrcInfo(0, 0, 0, 0, self.manufacturer, byref(self.deviceAvailable))
        lib.TLPAX_getRsrcInfo(0, 0, 0, self.serialNumber, 0, byref(self.deviceAvailable))
        print("The device's availability: {}, model: {}, manufacturer: {}, serial number: {}"\
                .format(self.deviceAvailable.value, self.modelName.value, self.manufacturer.value, self.serialNumber.value))

    def initDev(self):
        if not self.resource:
            print("Error, resource ID cannot be empty! UsegetResourceID to check legal device id before initializing the device")
            return
        ret = lib.TLPAX_init(self.resource, self.IDQuery, self.resetDevice, byref(self.handler))
        if ret == 0:
            print("Device initialization succeed!")
        else:
            print("Error when initializing the device!")

    def setMeasureMode(self,measureMode):
        lib.TLPAX_setMeasurementMode(self.handler, measureMode)
        time.sleep(1) # 1 second is necessary for waiting the device
        mode = c_int()
        lib.TLPAX_getMeasurementMode(self.handler, byref(mode))
        print("The measureMode is set to be: {}".format(mode.value))

    def setWavelength(self, _wavelength):
        lib.TLPAX_setWavelength(self.handler, c_double(_wavelength) )
        time.sleep(1) # 1 second is necessary for waiting the device
        wavelength = c_double()
        lib.TLPAX_getWavelength(self.handler, byref(wavelength))
        print("The wavelength is set to be: {} m".format(wavelength.value))

    def hasExternalPowerSupply(self):
        """Return True when the external power supply is connected."""
        connected = c_ushort()
        lib.TLPAX_hasExternalPowerSupply(self.handler, byref(connected))
        return bool(connected.value)

    def connectDevice(self):
        self.getNumOfDev()
        if int(self.deviceCount.value) == 0:
            print("Cannot find available devices, exiting.")
            return
        self.getDevModel()
        if self.deviceAvailable.value == False:
            raise RuntimeError("Error, the device is not available! Probably another process is using it. Considering close that process.")
            return
        self.initDev()
        self.setMeasureMode(self.measureMode)
        self.setWavelength(self.wavelength)


    def closeDevice(self):
        if self.handler.value:
            lib.TLPAX_close(self.handler)
        self.handler = c_ulong()


class PolarimeterLTM:
    """ 
        Class for PAX1000 taking a long term measurement
    """

    def __init__(self, handler, sampleStage, rotateAngle=0, measureTime=20, interval=0.05):
        """ Constructor
        :type  handler: c_ulong;
               sampleStage: ?;
               rotateAngle: int;
               measureTime: int;
               interval: int;
        :param handler: handler to the polarimeter;
               sampleStage: stage instance for the sample;
               rotateAngle: degree the sampleStage will be rotated;
               measureTime: polarimeter's measure time;
               interval: measurement interval, in seconds
        """
        self.handler = handler
        self.sampleStage = sampleStage
        self.rotateAngle = rotateAngle
        self.measureTime = measureTime
        self.interval = interval

        self.runFlag = True
        self.lastestScanID = 255
        self.startTime = 0
        self.endTime = 0
        self.diff = 0

        self.stageMinVelocity = 0
        self.stageAcceleration = 0
        self.stageMaxVelocity = 0
        self.stop = False

        self.sync() # sync the time between timeStamp and Polarimeter time
        self.clearMemory() # clear memory first
        if self.sampleStage:
            self.getStageVelocity() # get stage velocity parameters
            self.sampleStage.set_position_reference() # set reference point for the stage

    def sync(self):
        timeStamp = round(time.time() * 1000)
        self.takeOneMeasurement()
        upTime = c_int()
        timePola = lib.TLPAX_getTimeStamp(self.handler, self.lastestScanID, byref(upTime))
        self.diff = timeStamp - int(upTime.value)

    
    def getStageVelocity(self):
        params = self.sampleStage.get_velocity_parameters()
        self.stageMinVelocity = params.min_velocity
        self.stageAcceleration = params.acceleration
        self.stageMaxVelocity = params.max_velocity

    def rotateStage(self):
        time.sleep(0.5)
        self.startTime = int(time.time() * 1000)
        self.sampleStage.move_by(self.rotateAngle) # rotate the stage
        self.sampleStage.wait_move() # wait for stage to finish
        self.endTime = int(time.time() * 1000)

    def run(self, fname):
        '''
        polarimeter taking data, when rotating the sample stage, then write data to csv file fname
        '''
        self.setStageDefaultVelocity() # set default velocity
        self.clearMemory() # clear memory

        '''
        thread = threading.Thread(target=self.measure, args=())
        #thread.daemon = True
        self.runFlag = True
        thread.start() # start measuring
        time.sleep(0.1)
        self.startTime = int(time.time() * 1000)
        self.sampleStage.move_by(self.rotateAngle) # rotate the stage
        self.sampleStage.wait_move() # wait for stage to finish
        self.endTime = int(time.time() * 1000)
        time.sleep(0.1)
        self.runFlag = False # stop the measurement
        time.sleep(1)
        '''
        
        thread = threading.Thread(target=self.rotateStage, args=())
        thread.start() # start thread, rotate the stage (delayed 0.5 s)
        self.measure() # make sure the measure time is larger than the rotation time!!! (1-2s longer is optimal)
        
        # now reset the sample stage, and write the polarimeter data
        self.writeData(self.lastestScanID, '{}.csv'.format(fname)) # write data
        self.setStageHighVelocity()
        self.sampleStage.move_to(0) # reset stage
        self.sampleStage.wait_move() # wait for the stage
        
        # clean
        self.setStageDefaultVelocity()
        self.clearMemory()

    def writeData(self, scanID, fname):
        """ Method to retrieve data from scanID, and write to CSV file """
        print("will now write to file...")
        #fields = ['Polarimeter Time', 'S1', 'S2', 'S3', 'Power', 'DOP','azimuthal','ellipticity','startTime','endTime']
        fields = ['Polarimeter Time', 'Power', 'DOP','azimuthal','ellipticity','startTime','endTime']
        startTime = self.startTime - self.diff
        endTime = self.endTime - self.diff
        with open(fname, 'w', newline="") as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(fields)
            for i in range(int(scanID), 255, -1):
                data = self.readFromScanID(i)
                lib.TLPAX_releaseScan(self.handler, c_int(i))
                csvwriter.writerow( data + [int(startTime), int(endTime)] )
        print("CSV file saved to {}".format(fname))

    def readFromScanID(self, _id):
        """ Method to read data from specific scanID, return a list """
        polaTime = c_int()
        lib.TLPAX_getTimeStamp(self.handler, c_int(_id), byref(polaTime))
        #s1 = c_double()
        #s2 = c_double()
        #s3 = c_double()
        #lib.TLPAX_getStokes(self.handler, c_int(_id), byref(s1), byref(s2), byref(s3))
        power = c_double()
        powerPolarized = c_double()
        powerUnpolarized = c_double()
        lib.TLPAX_getPower(self.handler, c_int(_id), byref(power), byref(powerPolarized), byref(powerUnpolarized))
        dop = c_double()
        dolp = c_double()
        docp = c_double()
        lib.TLPAX_getDOP(self.handler, c_int(_id), byref(dop), byref(dolp), byref(docp))
        azimuthal = c_double()
        ellipticity = c_double()
        lib.TLPAX_getPolarization(self.handler, c_int(_id), byref(azimuthal), byref(ellipticity))
        
        #return [int(polaTime.value), float(s1.value), float(s2.value), float(s3.value),float(power.value), float(dop.value),float(azimuthal.value), float(ellipticity.value) ]
        return [int(polaTime.value),float(power.value), float(dop.value),float(azimuthal.value), float(ellipticity.value) ]

    def setStageHighVelocity(self):
        #print("Resetting stage...")
        self.sampleStage.setup_velocity(min_velocity = self.stageMinVelocity, acceleration=self.stageAcceleration*1, max_velocity = self.stageMaxVelocity*8)
        #self.sampleStage.move_to(0)

    def setStageDefaultVelocity(self):
        self.sampleStage.setup_velocity(min_velocity = self.stageMinVelocity, acceleration=self.stageAcceleration, max_velocity = self.stageMaxVelocity)

    def measure(self):
        """ Method that take continuous measurments with the period interval for measureTime seconds """
        print("Measure start...")
        #while self.runFlag:
        start = time.time()
        while (time.time()-start)<self.measureTime:
            # Do something
            self.takeOneMeasurement()
            time.sleep(self.interval)
        print("Measure stopped.")

    def get_alignment_measurement(self) -> Dict[str, Any]:
        """Take a fresh measurement and return values relevant to alignment.

        Prefers the dedicated DLL alignment aid value when available.
        Falls back to a newly captured scan and uses DOP as a proxy.
        """
        try:
            reading = get_alignment_reading(self.handler)
            reading["source"] = "alignment_aid"
            return reading
        except Exception:
            scan_id = self.takeOneMeasurement()
            measurement = self.readFromScanID(scan_id)
            dop = 0.0
            power = 0.0
            if isinstance(measurement, (list, tuple)):
                if len(measurement) >= 3:
                    try:
                        dop = float(measurement[2])
                    except (TypeError, ValueError):
                        dop = 0.0
                if len(measurement) >= 2:
                    try:
                        power = float(measurement[1])
                    except (TypeError, ValueError):
                        power = 0.0
            return {
                "opt_power": power,
                "alignment_aid": dop,
                "is_aligned": dop >= 0.90,
                "source": "dop_fallback",
            }

    def alignment_assistance(self, measurement: Any = None) -> float:
        """Return an alignment score in the range 0.0-1.0.

        If `measurement` is not provided, this method acquires all required data
        by taking a fresh measurement.
        """
        if measurement is None:
            reading = self.get_alignment_measurement()
            try:
                return float(reading.get("alignment_aid", 0.0))
            except (TypeError, ValueError):
                return 0.0

        if isinstance(measurement, dict) and "alignment_aid" in measurement:
            try:
                return float(measurement["alignment_aid"])
            except (TypeError, ValueError):
                return 0.0

        if isinstance(measurement, (list, tuple)) and len(measurement) >= 3:
            try:
                return float(measurement[2])
            except (TypeError, ValueError):
                return 0.0

        return 0.0

    def alignment_assist(self) -> float:
        """Take a fresh measurement and return alignment in percent (0-100)."""
        return round(self.alignment_assistance() * 100, 2)

    def alighment_assist(self, measurement: Any = None):
        """Backward-compatible misspelling.

        If `measurement` is None, takes a fresh measurement and returns percent.
        """
        if measurement is None:
            return self.alignment_assist()
        return round(self.alignment_assistance(measurement) * 100, 2)

    def measure_until_stopped(self, measure_interval=0.05, delete: bool = False):
        """Take measurements until self.stop is changed to True."""
        print("Infinite measure start...")
        self.stop = False
        while not self.stop:
            self.takeOneMeasurement()
            time.sleep(measure_interval)
            if delete:
                self.delete_last_scan() 
        print("Infinite measure stopped.")

    def takeOneMeasurement(self):
        """ Take one measurement, return its scanID """
        scanID = c_int()
        lib.TLPAX_getLatestScan(self.handler, byref(scanID))
        self.lastestScanID = int(scanID.value)
        #print(int(scanID.value))
        return(self.lastestScanID)

    def clearMemory(self):
        """ Clear memory of the polarimeter """
        for i in range(int(self.lastestScanID), 255, -1):
            lib.TLPAX_releaseScan(self.handler, c_int(i))
        self.lastestScanID = 255
    
    def delete_last_scan(self):
        """ Delete the most recent scan from the polarimeter's memory. """
        last_scan_id = self.lastestScanID
        lib.TLPAX_releaseScan(self.handler, c_int(last_scan_id))
        self.lastestScanID -= 1