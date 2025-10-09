import sys

from ctypes import WinDLL, CDLL, create_string_buffer, c_int, c_void_p
import ctypes


def expand_bits(payload = bytes[0x00, 0xf0], msb_first=True, one=0x01, zero=0x00):
    out = []
    for b in payload:
        rng = range(7, -1, -1) if msb_first else range(8)
        for i in rng:
            out.append(one if (b >> i) & 1 else zero)
    return out  # list of bytes (0x00/0x01), LSB holds the bit


dll_path_usb = "C:\\Program Files (x86)\\Analog Devices\\AD9958_59 Evaluation Software\\ADI_CYUSB_USB4.dll"
#dll_path_adi = "C:\\Program Files (x86)\\Analog Devices\\AD9958_59 Evaluation Software\\adiclockeval.dll"


dll_usb = ctypes.WinDLL(dll_path_usb)
#dll_adi = ctypes.WinDLL(dll_path_adi)

#dll_usb = ctypes.CDLL(dll_path_usb)
#dll_adi = ctypes.CDLL(dll_path_adi)

cy = ctypes.WinDLL(r"C:\Program Files (x86)\Analog Devices\AD9958_59 Evaluation Software\ADI_CYUSB_USB4.dll")

# int Connect(int vid, int pid, unsigned char index, void** out_handle)
cy.Connect.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_void_p)]
cy.Connect.restype  = ctypes.c_int

# int Bulk_Transfer(void* handle, unsigned char pipe, unsigned int* length, void* buffer)
cy.Bulk_Transfer.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p]
cy.Bulk_Transfer.restype  = ctypes.c_int

# int Disconnect(void* handle)
cy.Disconnect.argtypes = [ctypes.c_void_p]
cy.Disconnect.restype  = ctypes.c_int

VID, PID = 0x0456, 0xEE25   # example – use your board’s
handle = ctypes.c_void_p()

def connect_any_index(vid, pid):
    for idx in range(8):
        h = ctypes.c_void_p(handle.value or 0)
        rc = cy.Connect(vid, pid, idx, ctypes.byref(h))
        if rc == 0 and h.value:
            print(idx)
            return h
    raise OSError("Connect failed for all indices 0..7")

handle = connect_any_index(VID, PID) # so far so good...?

payload = expand_bits(bytes([0x00, 0x80])) # activate channel 3, 2 wire mode
buf = (ctypes.c_ubyte * len(payload))(*payload)
n   = ctypes.c_uint(len(payload))

PIPE_OUT = 0x02        # common on FX2: EP2 OUT = 0x02 (verify for your board)
rc = cy.Bulk_Transfer(handle, PIPE_OUT, ctypes.byref(n), buf)
if rc != 0:
    raise OSError(f"Bulk OUT failed rc={rc}")

payload = expand_bits(bytes([0x04, 0xf0, 0xcc, 0xaa, 0x69])) # write test phase control work (do I need to read back??) TODO - analyze the usb logs from before
buf = (ctypes.c_ubyte * len(payload))(*payload)
n   = ctypes.c_uint(len(payload))

PIPE_OUT = 0x02        # common on FX2: EP2 OUT = 0x02 (verify for your board)
rc = cy.Bulk_Transfer(handle, PIPE_OUT, ctypes.byref(n), buf)
if rc != 0:
    raise OSError(f"Bulk OUT failed rc={rc}")



cy.Disconnect(handle)

