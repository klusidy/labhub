

import ctypes
import numpy as np
#from picosdk.ps5000 import ps5000 as ps
import matplotlib.pyplot as plt
import numpy as np


from picosdk.discover import find_all_units
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc

# Ideally, construct whatever picoscope was found automatically

# scopes = find_all_units()

# for scope in scopes:
#     print(scope.info)
#     scope.close()

# scope = scopes[0] # for now, we have one picoscope connected

# ps = scope.driver # presumably from picosdk.ps5000a import ps5000a as ps

# for item in dir(ps):
#     print(item)


from picosdk.ps5000a import ps5000a as ps




# Create chandle and status ready for use
chandle = ctypes.c_int16()
status = {}

# Open 5000 series PicoScope
# Resolution set to 12 Bit
resolution =ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_12BIT"]
# Returns handle to chandle for use in future API functions
status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(chandle), None, resolution)

try:
    assert_pico_ok(status["openunit"])
except: # PicoNotOkError:

    powerStatus = status["openunit"]

    if powerStatus == 286:
        status["changePowerSource"] = ps.ps5000aChangePowerSource(chandle, powerStatus)
    elif powerStatus == 282:
        status["changePowerSource"] = ps.ps5000aChangePowerSource(chandle, powerStatus)
    else:
        raise

    assert_pico_ok(status["changePowerSource"])


# Set up channel A
# handle = chandle
channelA = ps.PS5000A_CHANNEL["PS5000A_CHANNEL_A"]
# enabled = 1
coupling_type = ps.PS5000A_COUPLING["PS5000A_DC"]
chARange = ps.PS5000A_RANGE["PS5000A_2V"]
# analogue offset = 0 V
status["setChA"] = ps.ps5000aSetChannel(chandle, channelA, 1, coupling_type, chARange, 0)
assert_pico_ok(status["setChA"])

###
# pp = ctypes.c_int16(0)
# complete = ctypes.c_int16(0)
# ps.ps5000aOpenUnitProgress(ctypes.byref(self.chandle), ctypes.byref(pp), ctypes.byref(complete))
# ###

# channel = "A"
# _info = 0# I guess - only one type of channel information available?? ps.PS5000A_CHANNEL_INFO["PS5000A_CI_RANGE_INFO"]
# _ranges = (ctypes.c_int16 * 4)()
# _length = ctypes.c_int32(0)
# _channel = ps.PS5000A_CHANNEL[f"PS5000A_CHANNEL_{channel}"]


# # query the length
# ps.ps5000aGetChannelInformation(chandle, _info, 0, None, ctypes.byref(_length), _channel)

# arr = (ctypes.c_int32 * _length.value)()
# ps.ps5000aGetChannelInformation(chandle, _info, 0, arr, ctypes.byref(_length), _channel)

# # # Convert to your enum / python ints
# ranges_vals = list(arr)  



# Set up channel B
# handle = chandle
channelB = ps.PS5000A_CHANNEL["PS5000A_CHANNEL_B"]
# enabled = 1
# coupling_type = ps.PS5000A_COUPLING["PS5000A_DC"]
chBRange = ps.PS5000A_RANGE["PS5000A_2V"]
# analogue offset = 0 V
status["setChB"] = ps.ps5000aSetChannel(chandle, channelB, 1, coupling_type, chBRange, 0)
assert_pico_ok(status["setChB"])


maxADC = ctypes.c_int16()
status["maximumValue"] = ps.ps5000aMaximumValue(chandle, ctypes.byref(maxADC))
assert_pico_ok(status["maximumValue"])




# Set up simple trigger
# handle = chandle
# enabled = 1
source = ps.PS5000A_CHANNEL["PS5000A_CHANNEL_A"]
threshold = int(mV2adc(100,chARange, maxADC))
# direction = PS5000A_RISING = 2
# delay = 0 s
# auto Trigger = 1000 ms
status["trigger"] = ps.ps5000aSetSimpleTrigger(chandle, 1, source, threshold, 2, 0, 1000)
assert_pico_ok(status["trigger"])

# Set number of pre and post trigger samples to be collected
preTriggerSamples = 2500
postTriggerSamples = 2500
maxSamples = preTriggerSamples + postTriggerSamples

# Get timebase information
# Warning: When using this example it may not be possible to access all Timebases as all channels are enabled by default when opening the scope.  
# To access these Timebases, set any unused analogue channels to off.
# handle = chandle
timebase = 10
# noSamples = maxSamples
# pointer to timeIntervalNanoseconds = ctypes.byref(timeIntervalns)
# pointer to maxSamples = ctypes.byref(returnedMaxSamples)
# segment index = 0
timeIntervalns = ctypes.c_float()
returnedMaxSamples = ctypes.c_int32()
status["getTimebase2"] = ps.ps5000aGetTimebase2(chandle, timebase, 1, ctypes.byref(timeIntervalns), ctypes.byref(returnedMaxSamples), 0)
assert_pico_ok(status["getTimebase2"])
print(f"timeintervale = {timeIntervalns} ns, maxSamples = {returnedMaxSamples.value}")



# Run block capture
# handle = chandle
# number of pre-trigger samples = preTriggerSamples
# number of post-trigger samples = PostTriggerSamples
# timebase = 8 = 80 ns (see Programmer's guide for mre information on timebases)
# time indisposed ms = None (not needed in the example)
# segment index = 0
# lpReady = None (using ps5000aIsReady rather than ps5000aBlockReady)
# pParameter = None
status["runBlock"] = ps.ps5000aRunBlock(chandle, preTriggerSamples, postTriggerSamples, timebase, None, 0, None, None)
assert_pico_ok(status["runBlock"])

# Check for data collection to finish using ps5000aIsReady
ready = ctypes.c_int16(0)
check = ctypes.c_int16(0)
while ready.value == check.value:
    status["isReady"] = ps.ps5000aIsReady(chandle, ctypes.byref(ready))


# Create buffers ready for assigning pointers for data collection
bufferAMax = (ctypes.c_int16 * maxSamples)()
bufferAMin = (ctypes.c_int16 * maxSamples)() # used for downsampling which isn't in the scope of this example
bufferBMax = (ctypes.c_int16 * maxSamples)()
bufferBMin = (ctypes.c_int16 * maxSamples)() # used for downsampling which isn't in the scope of this example


source = ps.PS5000A_CHANNEL["PS5000A_CHANNEL_A"]
# pointer to buffer max = ctypes.byref(bufferAMax)
# pointer to buffer min = ctypes.byref(bufferAMin)
# buffer length = maxSamples
# segment index = 0
# ratio mode = PS5000A_RATIO_MODE_NONE = 0
status["setDataBuffersA"] = ps.ps5000aSetDataBuffers(chandle, source, ctypes.byref(bufferAMax), ctypes.byref(bufferAMin), maxSamples, 0, 0)
assert_pico_ok(status["setDataBuffersA"])

# Set data buffer location for data collection from channel B
# handle = chandle
source = ps.PS5000A_CHANNEL["PS5000A_CHANNEL_B"]
# pointer to buffer max = ctypes.byref(bufferBMax)
# pointer to buffer min = ctypes.byref(bufferBMin)
# buffer length = maxSamples
# segment index = 0
# ratio mode = PS5000A_RATIO_MODE_NONE = 0
status["setDataBuffersB"] = ps.ps5000aSetDataBuffers(chandle, source, ctypes.byref(bufferBMax), ctypes.byref(bufferBMin), maxSamples, 0, 0)
assert_pico_ok(status["setDataBuffersB"])


# create overflow loaction
overflow = ctypes.c_int16()
# create converted type maxSamples
cmaxSamples = ctypes.c_int32(maxSamples)


# Retried data from scope to buffers assigned above
# handle = chandle
# start index = 0
# pointer to number of samples = ctypes.byref(cmaxSamples)
# downsample ratio = 0
# downsample ratio mode = PS5000A_RATIO_MODE_NONE
# segment index
# pointer to overflow = ctypes.byref(overflow))
status["getValues"] = ps.ps5000aGetValues(chandle, 0, ctypes.byref(cmaxSamples), 0, 0, 0, ctypes.byref(overflow))
assert_pico_ok(status["getValues"])

adc2mVChAMax =  adc2mV(bufferAMax, chARange, maxADC)
adc2mVChBMax =  adc2mV(bufferBMax, chBRange, maxADC)

time = np.linspace(0, (cmaxSamples.value - 1) * timeIntervalns.value, cmaxSamples.value)

# plot data from channel A and B
fig, ax = plt.subplots(figsize=(10,6))
ax.plot(time, adc2mVChAMax[:])
plt.plot(time, adc2mVChBMax[:])
ax.set_xlabel('Time (ns)')
ax.set_ylabel('Voltage (mV)')
plt.show()





ps.ps5000aMinimumValue

ps._python_get_unit_info

ps.ps5000aGetUnitInfo.argtypes

# Create chandle and status ready for use
chandle = ctypes.c_int16()
status = {}




# Open 5000 series PicoScope
# Returns handle to chandle for use in future API functions
status["openunit"] = ps.ps5000OpenUnit(ctypes.byref(chandle))
assert_pico_ok(status["openunit"])
