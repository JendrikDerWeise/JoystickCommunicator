import ctypes
import os
import platform
import sys
import enum # Nützlich für die Repräsentation der Enums in Python

# --- Konfiguration: Pfad zur Shared Library ---
# Da die Zielplattform Linux (RPi5) ist, suchen wir nach .so
# Passe diesen Pfad entsprechend an, wo deine kompilierte librlink.so liegt.
# Beispiel: Erwarte 'librlink.so' im selben Verzeichnis wie das Skript
LIB_FILENAME = '/lib/libMspRlink.so'
# Versuche, den Pfad relativ zum Skript zu finden
# Du kannst dies durch einen absoluten Pfad ersetzen, falls nötig:
# LIB_PATH = '/pfad/zu/deiner/librlink.so'
try:
    # __file__ ist nicht immer verfügbar (z.B. im interaktiven Modus),
    # also fügen wir einen Fallback hinzu
    script_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
    LIB_PATH = os.path.join(script_dir, LIB_FILENAME)
except NameError:
     LIB_PATH = LIB_FILENAME # Fallback, wenn __file__ nicht definiert ist

if not os.path.exists(LIB_PATH):
     # Versuche einen allgemeineren Systempfad, falls nicht lokal gefunden
     # (Dies erfordert, dass die Bibliothek im LD_LIBRARY_PATH ist)
     try:
         lib = ctypes.CDLL(LIB_FILENAME)
     except OSError:
          raise FileNotFoundError(
              f"Shared library '{LIB_FILENAME}' not found locally ('{LIB_PATH}') "
              "or in system library paths. Please check the path and LD_LIBRARY_PATH."
          )
else:
     # Lade die Shared Library vom spezifischen Pfad
     try:
         lib = ctypes.CDLL(LIB_PATH)
     except OSError as e:
         print(f"Error loading shared library from '{LIB_PATH}': {e}")
         sys.exit(1)

print(f"Successfully loaded shared library: {LIB_PATH if os.path.exists(LIB_PATH) else LIB_FILENAME}")

# --- C-Typ Definitionen für ctypes ---

# Grundlegende Typen (aus stdint.h, stdbool.h)
c_int8 = ctypes.c_int8
c_uint8 = ctypes.c_uint8
c_uint16 = ctypes.c_uint16
c_float = ctypes.c_float
c_bool = ctypes.c_bool
c_size_t = ctypes.c_size_t
c_char_p = ctypes.c_char_p
c_void_p = ctypes.c_void_p

# Definierte Typen basierend auf den Headern
msp_status_t = ctypes.c_int          # Aus msp_status.h (ist ein Enum)
msp_rlink_btn_t = ctypes.c_int       # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_light_t = ctypes.c_int     # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_mode_t = ctypes.c_int      # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_profile_t = ctypes.c_int   # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_status_t = ctypes.c_int    # Aus msp_rlinkdef.h (ist ein Enum) -> Geräte-Status
msp_rlink_axis_id_t = ctypes.c_int   # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_axis_dir_t = ctypes.c_int  # Aus msp_rlinkdef.h (ist ein Enum)
msp_rlink_err_t = ctypes.c_int       # Aus msp_rlinkdef.h (ist ein Enum) -> RLink Fehlercodes

# Opaque Pointer für die Strukturen (unverändert)
msp_rlink_devinfo_t_ptr = c_void_p
msp_rlink_devices_t_ptr = c_void_p
msp_rlink_t_ptr = c_void_p

# --- Konstanten (Enums und Macros) ---

# msp_status_t Enum Werte (aus msp_status.h)
MSP_OK = 0
MSP_FTD2XX = 1
MSP_TIMEOUT = 2
MSP_OVERFLOW = 3
MSP_UNDERFLOW = 4
MSP_INVALID_ARGS = 5
MSP_NOT_SUPPORTED = 6
MSP_OTHER_ERROR = 7
MSP_NO_MEMORY = 8
MSP_NULL_PTR = 9
MSP_INVALID_SIZE = 10
MSP_NOT_FOUND = 11
MSP_BUSY = 12
MSP_MSG_ERR = 13
MSP_CRC_ERR = 14
MSP_INVALID_LEN = 15

# Mapping von Status-Codes zu Namen für bessere Fehlermeldungen
MSP_STATUS_NAMES = {
    MSP_OK: "MSP_OK",
    MSP_FTD2XX: "MSP_FTD2XX",
    MSP_TIMEOUT: "MSP_TIMEOUT",
    MSP_OVERFLOW: "MSP_OVERFLOW",
    MSP_UNDERFLOW: "MSP_UNDERFLOW",
    MSP_INVALID_ARGS: "MSP_INVALID_ARGS",
    MSP_NOT_SUPPORTED: "MSP_NOT_SUPPORTED",
    MSP_OTHER_ERROR: "MSP_OTHER_ERROR",
    MSP_NO_MEMORY: "MSP_NO_MEMORY",
    MSP_NULL_PTR: "MSP_NULL_PTR",
    MSP_INVALID_SIZE: "MSP_INVALID_SIZE",
    MSP_NOT_FOUND: "MSP_NOT_FOUND",
    MSP_BUSY: "MSP_BUSY",
    MSP_MSG_ERR: "MSP_MSG_ERR",
    MSP_CRC_ERR: "MSP_CRC_ERR",
    MSP_INVALID_LEN: "MSP_INVALID_LEN",
}

# Event Masks (aus msp_rlink.h)
MSP_RLINK_EV_DISCONNECTED = 0x01
MSP_RLINK_EV_ERROR = 0x02
MSP_RLINK_EV_DATA_READY = 0x04

# msp_rlink_btn_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_BTN_YT = 0
MSP_RLINK_BTN_YR = 1
MSP_RLINK_BTN_RR = 2
MSP_RLINK_BTN_NOF = 3

# msp_rlink_light_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_LIGHT_BRAKE = 0
MSP_RLINK_LIGHT_DIP = 1
MSP_RLINK_LIGHT_HAZARD = 2
MSP_RLINK_LIGHT_LEFT = 3
MSP_RLINK_LIGHT_RIGHT = 4
MSP_RLINK_LIGHT_NOF = 5

# msp_rlink_mode_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_MODE_1 = 0
MSP_RLINK_MODE_2 = 1
MSP_RLINK_MODE_3 = 2
MSP_RLINK_MODE_4 = 3
MSP_RLINK_MODE_5 = 4
MSP_RLINK_MODE_6 = 5
MSP_RLINK_MODE_7 = 6
MSP_RLINK_MODE_8 = 7
MSP_RLINK_MODE_NOF = 8

# msp_rlink_profile_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_PROFILE_1 = 0
MSP_RLINK_PROFILE_2 = 1
MSP_RLINK_PROFILE_3 = 2
MSP_RLINK_PROFILE_4 = 3
MSP_RLINK_PROFILE_5 = 4
MSP_RLINK_PROFILE_6 = 5
MSP_RLINK_PROFILE_7 = 6
MSP_RLINK_PROFILE_8 = 7
MSP_RLINK_PROFILE_NOF = 8

# msp_rlink_status_t Enum Werte (aus msp_rlinkdef.h) -> Geräte-Status
MSP_RLINK_STATUS_CONFIGURING = 0
MSP_RLINK_STATUS_ERROR = 1
MSP_RLINK_STATUS_POWER_CYCLE = 2
MSP_RLINK_STATUS_SHUTDOWN = 3
MSP_RLINK_STATUS_OUT_OF_FOCUS = 4
MSP_RLINK_STATUS_FOCUS = 5
MSP_RLINK_STATUS_NOF = 6

# msp_rlink_axis_id_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_AXIS_ID_0 = 0
# ... (alle anderen bis 31)
MSP_RLINK_AXIS_ID_31 = 31
MSP_RLINK_AXIS_ID_NOF = 32

# msp_rlink_axis_dir_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_AXIS_DIR_NONE = 0
MSP_RLINK_AXIS_DIR_UP = 1
MSP_RLINK_AXIS_DIR_DOWN = 2
MSP_RLINK_AXIS_DIR_NOF = 3

# msp_rlink_err_t Enum Werte (aus msp_rlinkdef.h) -> RLink Fehlercodes
MSP_RLINK_ERR_NONE = 0
MSP_RLINK_ERR_TIMEOUT = 1
MSP_RLINK_ERR_OUT_OF_MEMORY = 2
MSP_RLINK_ERR_MDEV_ERROR = 3

# Mapping für RLink Fehlercodes zu Namen
MSP_RLINK_ERR_NAMES = {
    MSP_RLINK_ERR_NONE: "MSP_RLINK_ERR_NONE",
    MSP_RLINK_ERR_TIMEOUT: "MSP_RLINK_ERR_TIMEOUT",
    MSP_RLINK_ERR_OUT_OF_MEMORY: "MSP_RLINK_ERR_OUT_OF_MEMORY",
    MSP_RLINK_ERR_MDEV_ERROR: "MSP_RLINK_ERR_MDEV_ERROR",
}


# --- Definition der Funktionssignaturen (unverändert zur vorherigen Version) ---
# (Hier wird jetzt intern auf die präziseren Typ-Aliase verwiesen)

# msp_rlink_Construct
lib.msp_rlink_Construct.argtypes = [msp_rlink_devinfo_t_ptr]
lib.msp_rlink_Construct.restype = msp_rlink_t_ptr

# msp_rlink_Destruct
lib.msp_rlink_Destruct.argtypes = [msp_rlink_t_ptr]
lib.msp_rlink_Destruct.restype = None # void

# msp_rlink_Open
lib.msp_rlink_Open.argtypes = [msp_rlink_t_ptr]
lib.msp_rlink_Open.restype = msp_status_t

# msp_rlink_Close
lib.msp_rlink_Close.argtypes = [msp_rlink_t_ptr]
lib.msp_rlink_Close.restype = msp_status_t

# msp_rlink_SetXy
lib.msp_rlink_SetXy.argtypes = [msp_rlink_t_ptr, c_int8, c_int8]
lib.msp_rlink_SetXy.restype = msp_status_t

# msp_rlink_SetAxis
lib.msp_rlink_SetAxis.argtypes = [msp_rlink_t_ptr, msp_rlink_axis_id_t, msp_rlink_axis_dir_t]
lib.msp_rlink_SetAxis.restype = msp_status_t

# msp_rlink_SetBtn
lib.msp_rlink_SetBtn.argtypes = [msp_rlink_t_ptr, msp_rlink_btn_t, c_bool]
lib.msp_rlink_SetBtn.restype = msp_status_t

# msp_rlink_SetHorn
lib.msp_rlink_SetHorn.argtypes = [msp_rlink_t_ptr, c_bool]
lib.msp_rlink_SetHorn.restype = msp_status_t

# msp_rlink_SetLight
lib.msp_rlink_SetLight.argtypes = [msp_rlink_t_ptr, msp_rlink_light_t, c_bool]
lib.msp_rlink_SetLight.restype = msp_status_t

# msp_rlink_SetError
lib.msp_rlink_SetError.argtypes = [msp_rlink_t_ptr, c_uint8]
lib.msp_rlink_SetError.restype = msp_status_t

# msp_rlink_GetMode
lib.msp_rlink_GetMode.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_mode_t)]
lib.msp_rlink_GetMode.restype = msp_status_t

# msp_rlink_GetProfile
lib.msp_rlink_GetProfile.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_profile_t)]
lib.msp_rlink_GetProfile.restype = msp_status_t

# msp_rlink_GetHorn
lib.msp_rlink_GetHorn.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_bool)]
lib.msp_rlink_GetHorn.restype = msp_status_t

# msp_rlink_GetBatteryInfo
lib.msp_rlink_GetBatteryInfo.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_bool),    # low
    ctypes.POINTER(c_uint8),   # gauge
    ctypes.POINTER(c_float)    # current
]
lib.msp_rlink_GetBatteryInfo.restype = msp_status_t

# msp_rlink_GetVelocity
lib.msp_rlink_GetVelocity.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_float),   # m1vel
    ctypes.POINTER(c_float),   # m2vel
    ctypes.POINTER(c_float)    # turnVel
]
lib.msp_rlink_GetVelocity.restype = msp_status_t

# msp_rlink_GetSpeed
lib.msp_rlink_GetSpeed.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_uint8),   # speed
    ctypes.POINTER(c_float),   # trueSpeed
    ctypes.POINTER(c_uint8)    # speedLimitApplied
]
lib.msp_rlink_GetSpeed.restype = msp_status_t

# msp_rlink_GetLight
lib.msp_rlink_GetLight.argtypes = [
    msp_rlink_t_ptr,
    msp_rlink_light_t,
    ctypes.POINTER(c_bool),    # active
    ctypes.POINTER(c_bool)     # lit
]
lib.msp_rlink_GetLight.restype = msp_status_t

# msp_rlink_GetError
lib.msp_rlink_GetError.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_uint16),  # ecInterface
    ctypes.POINTER(c_uint16)   # ecRnet
]
lib.msp_rlink_GetError.restype = msp_status_t

# msp_rlink_GetDevStatus
lib.msp_rlink_GetDevStatus.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_bool),           # oon
    ctypes.POINTER(msp_rlink_status_t),# status (Geräte-Status Enum)
    ctypes.POINTER(c_uint8)           # warning
]
lib.msp_rlink_GetDevStatus.restype = msp_status_t

# msp_rlink_GetHms
lib.msp_rlink_GetHms.argtypes = [
    msp_rlink_t_ptr,
    ctypes.POINTER(c_uint16),  # inputProcess
    ctypes.POINTER(c_uint16),  # interProcess
    ctypes.POINTER(c_uint16),  # outputProcess
    ctypes.POINTER(c_bool),    # selInput
    ctypes.POINTER(c_bool),    # selInter
    ctypes.POINTER(c_bool)     # selOutput
]
lib.msp_rlink_GetHms.restype = msp_status_t

# msp_rlink_Heartbeat
lib.msp_rlink_Heartbeat.argtypes = [msp_rlink_t_ptr]
lib.msp_rlink_Heartbeat.restype = msp_status_t

# msp_rlink_GetLatestError
lib.msp_rlink_GetLatestError.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_err_t)]
lib.msp_rlink_GetLatestError.restype = msp_status_t

# msp_rlink_SetEventNotification
lib.msp_rlink_SetEventNotification.argtypes = [
    msp_rlink_t_ptr,
    ctypes.c_uint, # mask
    c_void_p,      # cvar
    c_void_p       # mutex
]
lib.msp_rlink_SetEventNotification.restype = msp_status_t

# msp_rlink_GetStatus
lib.msp_rlink_GetStatus.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(ctypes.c_uint)]
lib.msp_rlink_GetStatus.restype = msp_status_t

# msp_rlink_Logging
lib.msp_rlink_Logging.argtypes = [msp_rlink_t_ptr, c_bool]
lib.msp_rlink_Logging.restype = None # void

# msp_rlink_SetLogFile
lib.msp_rlink_SetLogFile.argtypes = [msp_rlink_t_ptr, c_char_p]
lib.msp_rlink_SetLogFile.restype = c_bool

# msp_rlink_DevicesConstruct
lib.msp_rlink_DevicesConstruct.argtypes = []
lib.msp_rlink_DevicesConstruct.restype = msp_rlink_devices_t_ptr

# msp_rlink_DevicesDestruct
lib.msp_rlink_DevicesDestruct.argtypes = [msp_rlink_devices_t_ptr]
lib.msp_rlink_DevicesDestruct.restype = None # void

# msp_rlink_GetNumberOfDevices
lib.msp_rlink_GetNumberOfDevices.argtypes = [msp_rlink_devices_t_ptr, ctypes.POINTER(c_size_t)]
lib.msp_rlink_GetNumberOfDevices.restype = msp_status_t

# msp_rlink_GetDeviceSerialnumber
lib.msp_rlink_GetDeviceSerialnumber.argtypes = [
    msp_rlink_devices_t_ptr,
    c_size_t,
    ctypes.POINTER(c_char_p)
]
lib.msp_rlink_GetDeviceSerialnumber.restype = msp_status_t

# msp_rlink_GetDeviceDescription
lib.msp_rlink_GetDeviceDescription.argtypes = [
    msp_rlink_devices_t_ptr,
    c_size_t,
    ctypes.POINTER(c_char_p)
]
lib.msp_rlink_GetDeviceDescription.restype = msp_status_t

# msp_rlink_GetDevice
lib.msp_rlink_GetDevice.argtypes = [
    msp_rlink_devices_t_ptr,
    c_size_t,
    ctypes.POINTER(msp_rlink_devinfo_t_ptr)
]
lib.msp_rlink_GetDevice.restype = msp_status_t


# --- Python Klassen als Wrapper ---

class RLinkError(Exception):
    """Custom exception for RLink errors."""
    def __init__(self, message, status_code=None, rlink_err_code=None):
        super().__init__(message)
        self.status_code = status_code
        self.rlink_err_code = rlink_err_code

    def __str__(self):
        base_msg = super().__str__()
        details = []
        if self.status_code is not None:
            status_name = MSP_STATUS_NAMES.get(self.status_code, "UNKNOWN_STATUS")
            details.append(f"Status={status_name}({self.status_code})")
        if self.rlink_err_code is not None:
            err_name = MSP_RLINK_ERR_NAMES.get(self.rlink_err_code, "UNKNOWN_RLINK_ERROR")
            details.append(f"RLinkError={err_name}({self.rlink_err_code})")
        if details:
            return f"{base_msg} [{', '.join(details)}]"
        else:
            return base_msg

class RLinkDevice:
    """Represents information about a detected RLink device."""
    def __init__(self, index, serial, description, dev_info_ptr):
        self.index = index
        self.serial = serial
        self.description = description
        self._dev_info_ptr = dev_info_ptr # Store the pointer

    def __repr__(self):
        return f"RLinkDevice(index={self.index}, serial='{self.serial}', description='{self.description}')"

# Optional: Python Enums für bessere Typsicherheit und Lesbarkeit im Python-Code
# Diese spiegeln die C-Enums wider
class MspStatus(enum.IntEnum):
    OK = MSP_OK
    FTD2XX = MSP_FTD2XX
    TIMEOUT = MSP_TIMEOUT
    OVERFLOW = MSP_OVERFLOW
    UNDERFLOW = MSP_UNDERFLOW
    INVALID_ARGS = MSP_INVALID_ARGS
    NOT_SUPPORTED = MSP_NOT_SUPPORTED
    OTHER_ERROR = MSP_OTHER_ERROR
    NO_MEMORY = MSP_NO_MEMORY
    NULL_PTR = MSP_NULL_PTR
    INVALID_SIZE = MSP_INVALID_SIZE
    NOT_FOUND = MSP_NOT_FOUND
    BUSY = MSP_BUSY
    MSG_ERR = MSP_MSG_ERR
    CRC_ERR = MSP_CRC_ERR
    INVALID_LEN = MSP_INVALID_LEN

class RLinkButton(enum.IntEnum):
    YELLOW_TIP = MSP_RLINK_BTN_YT
    YELLOW_RING = MSP_RLINK_BTN_YR
    RED_RING = MSP_RLINK_BTN_RR
    # NOF nicht einschließen, da es kein gültiger Button ist

class RLinkLight(enum.IntEnum):
    BRAKE = MSP_RLINK_LIGHT_BRAKE
    DIP = MSP_RLINK_LIGHT_DIP
    HAZARD = MSP_RLINK_LIGHT_HAZARD
    LEFT = MSP_RLINK_LIGHT_LEFT
    RIGHT = MSP_RLINK_LIGHT_RIGHT

class RLinkMode(enum.IntEnum):
    MODE_1 = MSP_RLINK_MODE_1
    MODE_2 = MSP_RLINK_MODE_2
    MODE_3 = MSP_RLINK_MODE_3
    MODE_4 = MSP_RLINK_MODE_4
    MODE_5 = MSP_RLINK_MODE_5
    MODE_6 = MSP_RLINK_MODE_6
    MODE_7 = MSP_RLINK_MODE_7
    MODE_8 = MSP_RLINK_MODE_8

class RLinkProfile(enum.IntEnum):
    PROFILE_1 = MSP_RLINK_PROFILE_1
    PROFILE_2 = MSP_RLINK_PROFILE_2
    PROFILE_3 = MSP_RLINK_PROFILE_3
    PROFILE_4 = MSP_RLINK_PROFILE_4
    PROFILE_5 = MSP_RLINK_PROFILE_5
    PROFILE_6 = MSP_RLINK_PROFILE_6
    PROFILE_7 = MSP_RLINK_PROFILE_7
    PROFILE_8 = MSP_RLINK_PROFILE_8

class RLinkDevStatus(enum.IntEnum): # Renamed from RLinkStatus to avoid conflict
    CONFIGURING = MSP_RLINK_STATUS_CONFIGURING
    ERROR = MSP_RLINK_STATUS_ERROR
    POWER_CYCLE = MSP_RLINK_STATUS_POWER_CYCLE
    SHUTDOWN = MSP_RLINK_STATUS_SHUTDOWN
    OUT_OF_FOCUS = MSP_RLINK_STATUS_OUT_OF_FOCUS
    FOCUS = MSP_RLINK_STATUS_FOCUS

class RLinkAxisId(enum.IntEnum):
    ID_0 = MSP_RLINK_AXIS_ID_0
    # ... Add all other IDs if needed ...
    ID_31 = MSP_RLINK_AXIS_ID_31

class RLinkAxisDir(enum.IntEnum):
    NONE = MSP_RLINK_AXIS_DIR_NONE
    UP = MSP_RLINK_AXIS_DIR_UP
    DOWN = MSP_RLINK_AXIS_DIR_DOWN

class RLinkErrorType(enum.IntEnum):
    NONE = MSP_RLINK_ERR_NONE
    TIMEOUT = MSP_RLINK_ERR_TIMEOUT
    OUT_OF_MEMORY = MSP_RLINK_ERR_OUT_OF_MEMORY
    MDEV_ERROR = MSP_RLINK_ERR_MDEV_ERROR


class MspRlink:
    """Python wrapper for the msp_rlink C library."""

    def __init__(self, dev_info_ptr):
        """
        Initializes the RLink instance using device info.
        Use MspRlink.enumerate_devices() to get dev_info_ptr.
        """
        if not dev_info_ptr:
            raise ValueError("dev_info_ptr cannot be None")

        self.handle = lib.msp_rlink_Construct(dev_info_ptr)
        if not self.handle:
            # Versuche, mehr Details zu bekommen (obwohl Construct selten Fehlercodes zurückgibt)
            raise RLinkError("Failed to construct RLink instance (msp_rlink_Construct returned NULL)")
        self._opened = False
        self._lib = lib # Halte eine Referenz zur Bibliothek

    def __del__(self):
        """Destructor to ensure resources are released."""
        if hasattr(self, 'handle') and self.handle:
            if self._opened:
                try:
                    self.close()
                except RLinkError as e:
                    # Use sys.stderr for warnings/errors during cleanup
                    print(f"Warning: Error closing device in destructor: {e}", file=sys.stderr)
            # Ensure lib reference still exists during destruction
            if hasattr(self, '_lib') and self._lib:
                 self._lib.msp_rlink_Destruct(self.handle)
            self.handle = None # Prevent double destruction

    def __enter__(self):
        """Context manager entry: opens the device."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: closes the device."""
        self.close()

    def _check_status(self, status: int, func_name: str):
        """Checks the msp_status_t code and raises RLinkError on failure."""
        if status != MSP_OK:
            status_name = MSP_STATUS_NAMES.get(status, "UNKNOWN_STATUS")
            # Attempt to get more specific RLink error info if status suggests it
            rlink_err_code = None
            if status == MSP_OTHER_ERROR or status == MSP_TIMEOUT: # Example conditions
                 try:
                      rlink_err_code = self.get_latest_error()
                 except RLinkError: # If get_latest_error itself fails
                      pass
            raise RLinkError(f"Error in {func_name}",
                             status_code=status,
                             rlink_err_code=rlink_err_code)

    @staticmethod
    def enumerate_devices():
        """Enumerates connected RLink devices."""
        # Use the globally loaded library instance 'lib'
        devices_handle = lib.msp_rlink_DevicesConstruct()
        if not devices_handle:
            raise RLinkError("Failed to construct devices list (msp_rlink_DevicesConstruct returned NULL)")

        devices_list = []
        try:
            num_devices = c_size_t()
            status = lib.msp_rlink_GetNumberOfDevices(devices_handle, ctypes.byref(num_devices))
            # Static check function needed here as 'self' is not available
            if status != MSP_OK:
                 status_name = MSP_STATUS_NAMES.get(status, "UNKNOWN_STATUS")
                 raise RLinkError(f"Error in msp_rlink_GetNumberOfDevices", status_code=status)


            for i in range(num_devices.value):
                sn_ptr = c_char_p()
                descr_ptr = c_char_p()
                dev_info_ptr = msp_rlink_devinfo_t_ptr() # Should be c_void_p initially

                status_sn = lib.msp_rlink_GetDeviceSerialnumber(devices_handle, i, ctypes.byref(sn_ptr))
                if status_sn != MSP_OK:
                    status_name = MSP_STATUS_NAMES.get(status_sn, "UNKNOWN_STATUS")
                    raise RLinkError(f"Error getting serial for index {i}", status_code=status_sn)
                serial = sn_ptr.value.decode('utf-8', errors='replace') if sn_ptr.value else "N/A"

                status_descr = lib.msp_rlink_GetDeviceDescription(devices_handle, i, ctypes.byref(descr_ptr))
                if status_descr != MSP_OK:
                    status_name = MSP_STATUS_NAMES.get(status_descr, "UNKNOWN_STATUS")
                    raise RLinkError(f"Error getting description for index {i}", status_code=status_descr)
                description = descr_ptr.value.decode('utf-8', errors='replace') if descr_ptr.value else "N/A"

                # Get the actual pointer value for the device info
                dev_info_out_ptr = msp_rlink_devinfo_t_ptr()
                status_dev = lib.msp_rlink_GetDevice(devices_handle, i, ctypes.byref(dev_info_out_ptr))
                if status_dev != MSP_OK:
                    status_name = MSP_STATUS_NAMES.get(status_dev, "UNKNOWN_STATUS")
                    raise RLinkError(f"Error getting device info for index {i}", status_code=status_dev)

                # Store the pointer value itself
                devices_list.append(RLinkDevice(i, serial, description, dev_info_out_ptr))

        finally:
            lib.msp_rlink_DevicesDestruct(devices_handle)

        return devices_list

    # --- Wrapped C Functions ---

    def open(self):
        """Opens the connection to the RLink device."""
        status = self._lib.msp_rlink_Open(self.handle)
        self._check_status(status, "msp_rlink_Open")
        self._opened = True
        print("RLink device opened successfully.")

    def close(self):
        """Closes the connection to the RLink device."""
        if self._opened and hasattr(self, 'handle') and self.handle:
            status = self._lib.msp_rlink_Close(self.handle)
            self._opened = False # Set false even if close fails to prevent recursive calls in __del__
            self._check_status(status, "msp_rlink_Close")
            print("RLink device closed.")
        elif not self._opened and hasattr(self, 'handle') and self.handle:
             print("RLink device already closed or not opened.")


    def set_xy(self, x: int, y: int):
        """Sets the XY value."""
        status = self._lib.msp_rlink_SetXy(self.handle, c_int8(x), c_int8(y))
        self._check_status(status, "msp_rlink_SetXy")

    def set_axis(self, axis_id: RLinkAxisId, direction: RLinkAxisDir):
        """Sets the axis value using Python Enums."""
        status = self._lib.msp_rlink_SetAxis(self.handle, msp_rlink_axis_id_t(axis_id), msp_rlink_axis_dir_t(direction))
        self._check_status(status, "msp_rlink_SetAxis")

    def set_button(self, btn: RLinkButton, pressed: bool):
        """Sets the button state using Python Enums."""
        status = self._lib.msp_rlink_SetBtn(self.handle, msp_rlink_btn_t(btn), c_bool(pressed))
        self._check_status(status, "msp_rlink_SetBtn")

    def set_horn(self, enable: bool):
        """Enables or disables the horn."""
        status = self._lib.msp_rlink_SetHorn(self.handle, c_bool(enable))
        self._check_status(status, "msp_rlink_SetHorn")

    def set_light(self, light: RLinkLight, enable: bool):
        """Sets the state of a light using Python Enums."""
        status = self._lib.msp_rlink_SetLight(self.handle, msp_rlink_light_t(light), c_bool(enable))
        self._check_status(status, "msp_rlink_SetLight")

    def set_error(self, error_code: int):
        """Sets the error code (0 means no error)."""
        status = self._lib.msp_rlink_SetError(self.handle, c_uint8(error_code))
        self._check_status(status, "msp_rlink_SetError")

    def get_mode(self) -> RLinkMode:
        """Gets the current mode as a Python Enum."""
        mode = msp_rlink_mode_t()
        status = self._lib.msp_rlink_GetMode(self.handle, ctypes.byref(mode))
        self._check_status(status, "msp_rlink_GetMode")
        return RLinkMode(mode.value)

    def get_profile(self) -> RLinkProfile:
        """Gets the current profile as a Python Enum."""
        profile = msp_rlink_profile_t()
        status = self._lib.msp_rlink_GetProfile(self.handle, ctypes.byref(profile))
        self._check_status(status, "msp_rlink_GetProfile")
        return RLinkProfile(profile.value)

    def get_horn(self) -> bool:
        """Gets the current horn status."""
        horn_status = c_bool()
        status = self._lib.msp_rlink_GetHorn(self.handle, ctypes.byref(horn_status))
        self._check_status(status, "msp_rlink_GetHorn")
        return horn_status.value

    def get_battery_info(self) -> tuple[bool, int, float]:
        """Gets battery information: (is_low, gauge_percent, current_amps)."""
        low = c_bool()
        gauge = c_uint8()
        current = c_float()
        status = self._lib.msp_rlink_GetBatteryInfo(self.handle, ctypes.byref(low), ctypes.byref(gauge), ctypes.byref(current))
        self._check_status(status, "msp_rlink_GetBatteryInfo")
        return low.value, gauge.value, current.value

    def get_velocity(self) -> tuple[float, float, float]:
        """Gets velocity variables: (motor1_vel, motor2_vel, turn_vel)."""
        m1vel = c_float()
        m2vel = c_float()
        turnVel = c_float()
        status = self._lib.msp_rlink_GetVelocity(self.handle, ctypes.byref(m1vel), ctypes.byref(m2vel), ctypes.byref(turnVel))
        self._check_status(status, "msp_rlink_GetVelocity")
        return m1vel.value, m2vel.value, turnVel.value

    def get_speed(self) -> tuple[int, float, int]:
        """Gets speed values: (speed_setting, true_speed, speed_limit_applied)."""
        speed = c_uint8()
        true_speed = c_float()
        speed_limit_applied = c_uint8() # Assuming 0 or 1, or specific limit ID
        status = self._lib.msp_rlink_GetSpeed(self.handle, ctypes.byref(speed), ctypes.byref(true_speed), ctypes.byref(speed_limit_applied))
        self._check_status(status, "msp_rlink_GetSpeed")
        return speed.value, true_speed.value, speed_limit_applied.value

    def get_light(self, light: RLinkLight) -> tuple[bool, bool]:
        """Gets the status of a specific light: (is_active, is_lit)."""
        active = c_bool()
        lit = c_bool()
        status = self._lib.msp_rlink_GetLight(self.handle, msp_rlink_light_t(light), ctypes.byref(active), ctypes.byref(lit))
        self._check_status(status, "msp_rlink_GetLight")
        return active.value, lit.value

    def get_error_codes(self) -> tuple[int, int]:
        """Gets interface and RNet error codes."""
        ec_interface = c_uint16()
        ec_rnet = c_uint16()
        status = self._lib.msp_rlink_GetError(self.handle, ctypes.byref(ec_interface), ctypes.byref(ec_rnet))
        self._check_status(status, "msp_rlink_GetError")
        return ec_interface.value, ec_rnet.value

    def get_device_status(self) -> tuple[bool, RLinkDevStatus, int]:
        """Gets device status: (is_out_of_neutral, rlink_status_enum, warning_code)."""
        oon = c_bool()
        rlink_c_status = msp_rlink_status_t() # C enum type
        warning = c_uint8()
        status = self._lib.msp_rlink_GetDevStatus(self.handle, ctypes.byref(oon), ctypes.byref(rlink_c_status), ctypes.byref(warning))
        self._check_status(status, "msp_rlink_GetDevStatus")
        return oon.value, RLinkDevStatus(rlink_c_status.value), warning.value

    def get_hms(self) -> tuple[int, int, int, bool, bool, bool]:
        """Gets HMS status."""
        input_process = c_uint16()
        inter_process = c_uint16()
        output_process = c_uint16()
        sel_input = c_bool()
        sel_inter = c_bool()
        sel_output = c_bool()
        status = self._lib.msp_rlink_GetHms(self.handle, ctypes.byref(input_process), ctypes.byref(inter_process),
                                      ctypes.byref(output_process), ctypes.byref(sel_input),
                                      ctypes.byref(sel_inter), ctypes.byref(sel_output))
        self._check_status(status, "msp_rlink_GetHms")
        return (input_process.value, inter_process.value, output_process.value,
                sel_input.value, sel_inter.value, sel_output.value)

    def heartbeat(self):
        """Resets the communication timeout timer."""
        status = self._lib.msp_rlink_Heartbeat(self.handle)
        self._check_status(status, "msp_rlink_Heartbeat")

    def get_latest_error(self) -> RLinkErrorType:
        """Gets the latest RLink-specific error code as Python Enum."""
        err = msp_rlink_err_t()
        # Don't use _check_status here, as this function *retrieves* an error
        status = self._lib.msp_rlink_GetLatestError(self.handle, ctypes.byref(err))
        if status != MSP_OK:
             # Handle the unlikely case that GetLatestError itself fails
             status_name = MSP_STATUS_NAMES.get(status, "UNKNOWN_STATUS")
             # Raise an error here as we cannot fulfill the request
             raise RLinkError(f"msp_rlink_GetLatestError failed itself", status_code=status)
        return RLinkErrorType(err.value)

    def set_event_notification(self, mask: int, cvar_ptr=None, mutex_ptr=None):
        """
        Subscribes to event notifications.
        NOTE: Passing actual condition variables/mutexes requires advanced ctypes usage.
              Passing None (default) likely disables callback/notification mechanism.
        """
        # Ensure mask is uint
        status = self._lib.msp_rlink_SetEventNotification(self.handle, ctypes.c_uint(mask), cvar_ptr, mutex_ptr)
        self._check_status(status, "msp_rlink_SetEventNotification")

    def get_status_flags(self) -> int:
        """Gets the event flags that have been set (returns raw mask)."""
        flags = ctypes.c_uint()
        status = self._lib.msp_rlink_GetStatus(self.handle, ctypes.byref(flags))
        self._check_status(status, "msp_rlink_GetStatus")
        return flags.value

    def set_logging(self, enable: bool):
        """Enables or disables logging."""
        self._lib.msp_rlink_Logging(self.handle, c_bool(enable)) # No return status

    def set_log_file(self, filename: str) -> bool:
        """Sets the filename for logging."""
        # Ensure the filename is encoded correctly for the C function
        filename_bytes = filename.encode('utf-8')
        result = self._lib.msp_rlink_SetLogFile(self.handle, c_char_p(filename_bytes))
        return result


# --- Beispielverwendung ---
if __name__ == "__main__":
    import time # Für sleep

    try:
        print("Enumerating RLink devices...")
        devices = MspRlink.enumerate_devices()

        if not devices:
            print("No RLink devices found.")
            sys.exit(0)

        print(f"Found {len(devices)} device(s):")
        for dev in devices:
            print(f"  - {dev}")

        # Wähle das erste gefundene Gerät aus
        selected_device_info = devices[0]._dev_info_ptr
        print(f"\nConnecting to device with SN: {devices[0].serial}...")

        # Instanz erstellen und Verbindung öffnen (mit Context Manager)
        with MspRlink(selected_device_info) as rlink:
            print("Connection successful.")

            # Logging aktivieren (optional)
            log_filename = "rlink_log.txt"
            if rlink.set_log_file(log_filename):
                print(f"Enabled logging to {log_filename}")
                rlink.set_logging(True)
            else:
                print(f"Failed to set log file {log_filename}")

            # Beispiel: Lese einige Werte und verwende Python Enums
            mode = rlink.get_mode()
            profile = rlink.get_profile()
            print(f"Current Mode: {mode.name} ({mode.value}), Profile: {profile.name} ({profile.value})")

            batt_low, batt_gauge, batt_current = rlink.get_battery_info()
            print(f"Battery Info: Low={batt_low}, Gauge={batt_gauge}%, Current={batt_current:.2f}A")

            is_oon, dev_status, warning = rlink.get_device_status()
            print(f"Device Status: OON={is_oon}, Status={dev_status.name}, WarningCode={warning}")

            # Beispiel: Setze einen Wert (Vorsicht bei echten Geräten!)
            print("Toggling Yellow Tip button state (example)...")
            rlink.set_button(RLinkButton.YELLOW_TIP, True)
            time.sleep(0.2)
            rlink.set_button(RLinkButton.YELLOW_TIP, False)
            time.sleep(0.2)

            # Beispiel: Heartbeat senden
            rlink.heartbeat()
            print("Heartbeat sent.")

            # Beispiel: Statusflags lesen (relevant mit Event Notifications)
            flags = rlink.get_status_flags()
            print(f"Status Flags: {flags:#04x}")
            if flags & MSP_RLINK_EV_DISCONNECTED: print("  - Disconnected event flag set")
            if flags & MSP_RLINK_EV_ERROR: print("  - Error event flag set")
            if flags & MSP_RLINK_EV_DATA_READY: print("  - Data Ready event flag set")

            # Letzten RLink-spezifischen Fehler abrufen
            latest_err = rlink.get_latest_error()
            print(f"Latest RLink Error Code: {latest_err.name} ({latest_err.value})")


        print("\nDevice closed automatically by context manager.")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Please ensure the shared library is compiled and LIB_PATH/LD_LIBRARY_PATH is set correctly.", file=sys.stderr)
    except RLinkError as e:
        print(f"RLink Error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()