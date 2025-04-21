#! /usr/bin/python

import sys
import time
from ctypes import *

##############################################################
# PARTIAL libMspRlink.so WRAPPERS
##############################################################
librlink = CDLL("/usr/local/lib/libMspRlink.so")

msp_rlink_DevicesConstruct = librlink.msp_rlink_DevicesConstruct
msp_rlink_DevicesConstruct.restype = POINTER(c_void_p)

msp_rlink_GetNumberOfDevices = librlink.msp_rlink_GetNumberOfDevices
msp_rlink_GetNumberOfDevices.argtype = [c_void_p, POINTER(c_size_t)]

msp_rlink_GetDevice =  librlink.msp_rlink_GetDevice
msp_rlink_GetDevice.argtype = [c_void_p, c_uint8, POINTER(c_void_p)]
msp_rlink_GetDevice.restype = c_int

msp_rlink_Construct = librlink.msp_rlink_Construct
msp_rlink_Construct.argtype = [c_void_p]
msp_rlink_Construct.restype = c_void_p

msp_rlink_Destruct = librlink.msp_rlink_Destruct
msp_rlink_Destruct.argtype = [c_void_p]

msp_rlink_Open = librlink.msp_rlink_Open
msp_rlink_Open.argtype = [c_void_p]
msp_rlink_Open.restype = c_int

msp_rlink_Close = librlink.msp_rlink_Close
msp_rlink_Close.argtype = [c_void_p]

msp_rlink_Heartbeat = librlink.msp_rlink_Heartbeat
msp_rlink_Heartbeat.argtype = [c_void_p]
msp_rlink_Heartbeat.restype = int

msp_rlink_SetXy = librlink.msp_rlink_SetXy
msp_rlink_SetXy.argtype = [c_void_p, c_int8, c_int8]
msp_rlink_SetXy.restype = int

MSP_OK = 0

##############################################################
# PRINT THE NUMBER OF CONNECTED RLINKS
##############################################################
devices = msp_rlink_DevicesConstruct()
nofDevices = c_size_t(0)
msp_rlink_GetNumberOfDevices(devices, byref(nofDevices))
print(f"Number of connected devices: {nofDevices.value}")
    
##############################################################
# PRINT THE NUMBER OF CONNECTED RLINKS
##############################################################
if nofDevices.value > 0:
    devinfo = c_void_p()
    devid = 0
    status = msp_rlink_GetDevice(devices, devid, byref(devinfo))

    if status == MSP_OK:
        print(f"OK")
        rlink = msp_rlink_Construct(devinfo)

        print("Opening rlink connection")
        status = msp_rlink_Open(rlink)

        if status == MSP_OK:
            print("Connected")
            idx = 0
            while idx < 100:
                idx = idx + 1
                msp_rlink_Heartbeat(rlink)

                if idx > 20:
                    msp_rlink_SetXy(rlink, 0, 100)
                elif idx == 20:
                    print("Driving")
                    msp_rlink_SetXy(rlink, 0, 0)
                else:
                    msp_rlink_SetXy(rlink, 0, 0)

                time.sleep(0.1)

            print("Closing down")
            msp_rlink_Close(rlink)

        msp_rlink_Destruct(rlink)
    else:
        print(f"Failed to get device with id {devid}")
else:
    print("No devices found!")

##############################################################
# END OF FILE
##############################################################
