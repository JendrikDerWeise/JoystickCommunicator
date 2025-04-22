# full_rlink_wrapper.py
import ctypes
import os
import platform
import sys
import enum
import time # Für eventuelle Delays

# --- Fehlerklasse ---
class RLinkError(Exception):
    """Custom exception for RLink errors."""
    def __init__(self, message, status_code=None, rlink_err_code=None):
        super().__init__(message)
        self.status_code = status_code
        self.rlink_err_code = rlink_err_code # Für Fehler von GetLatestError

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

# --- Pfad zur Bibliothek ---
# PASSE DIESEN PFAD GGF. AN! Er muss auf deine libMspRlink.so zeigen.
LIB_PATH = "/usr/local/lib/libMspRlink.so"
# Versuche, andere übliche Orte oder relative Pfade zu finden
try:
    script_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
    # Prüfe verschiedene mögliche Orte
    potential_paths = [
        LIB_PATH,
        os.path.join(script_dir, 'libMspRlink.so'),
        os.path.join(script_dir, 'lib/libMspRlink.so'),
        # Füge den Pfad hinzu, der in deiner Fehlermeldung auftauchte
        os.path.join(script_dir, '.venv/Scripts/lib/libMspRlink.so')
    ]
    found_path = None
    for path in potential_paths:
        if os.path.exists(path):
            found_path = path
            break
    if found_path:
        LIB_PATH = found_path
    elif not os.path.exists(LIB_PATH):
         raise FileNotFoundError # Wird unten behandelt
except NameError: # Falls __file__ nicht existiert
    if not os.path.exists(LIB_PATH):
         raise FileNotFoundError
except FileNotFoundError:
     raise FileNotFoundError(f"Shared library libMspRlink.so not found at expected paths like: {LIB_PATH}")

# --- Bibliothek laden ---
try:
    lib = ctypes.CDLL(LIB_PATH)
    print(f"Successfully loaded shared library: {LIB_PATH}")
except OSError as e:
    print(f"Error loading shared library from {LIB_PATH}: {e}", file=sys.stderr)
    sys.exit(1)

# --- C Typen ---
c_int8 = ctypes.c_int8
c_uint8 = ctypes.c_uint8
c_int16 = ctypes.c_int16
c_uint16 = ctypes.c_uint16
c_int32 = ctypes.c_int32
c_uint32 = ctypes.c_uint32
c_float = ctypes.c_float
c_double = ctypes.c_double
c_size_t = ctypes.c_size_t
c_void_p = ctypes.c_void_p
c_bool = ctypes.c_bool
c_int = ctypes.c_int # Für Status und Enums
c_uint = ctypes.c_uint
c_char_p = ctypes.c_char_p

# Opaque Pointer Typen (bleiben c_void_p)
msp_rlink_t_ptr = c_void_p
msp_rlink_devinfo_t_ptr = c_void_p
msp_rlink_devices_t_ptr = c_void_p

# --- Konstanten & Enums ---

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

MSP_STATUS_NAMES = {
    MSP_OK: "MSP_OK", MSP_FTD2XX: "MSP_FTD2XX", MSP_TIMEOUT: "MSP_TIMEOUT",
    MSP_OVERFLOW: "MSP_OVERFLOW", MSP_UNDERFLOW: "MSP_UNDERFLOW",
    MSP_INVALID_ARGS: "MSP_INVALID_ARGS", MSP_NOT_SUPPORTED: "MSP_NOT_SUPPORTED",
    MSP_OTHER_ERROR: "MSP_OTHER_ERROR", MSP_NO_MEMORY: "MSP_NO_MEMORY",
    MSP_NULL_PTR: "MSP_NULL_PTR", MSP_INVALID_SIZE: "MSP_INVALID_SIZE",
    MSP_NOT_FOUND: "MSP_NOT_FOUND", MSP_BUSY: "MSP_BUSY", MSP_MSG_ERR: "MSP_MSG_ERR",
    MSP_CRC_ERR: "MSP_CRC_ERR", MSP_INVALID_LEN: "MSP_INVALID_LEN",
}

# msp_rlink_btn_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_BTN_YT = 0; MSP_RLINK_BTN_YR = 1; MSP_RLINK_BTN_RR = 2; MSP_RLINK_BTN_NOF = 3
class RLinkButton(enum.IntEnum): YELLOW_TIP=0; YELLOW_RING=1; RED_RING=2

# msp_rlink_light_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_LIGHT_BRAKE = 0; MSP_RLINK_LIGHT_DIP = 1; MSP_RLINK_LIGHT_HAZARD = 2
MSP_RLINK_LIGHT_LEFT = 3; MSP_RLINK_LIGHT_RIGHT = 4; MSP_RLINK_LIGHT_NOF = 5
class RLinkLight(enum.IntEnum): BRAKE=0; DIP=1; HAZARD=2; LEFT=3; RIGHT=4

# msp_rlink_mode_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_MODE_1=0; MSP_RLINK_MODE_2=1; MSP_RLINK_MODE_3=2; MSP_RLINK_MODE_4=3
MSP_RLINK_MODE_5=4; MSP_RLINK_MODE_6=5; MSP_RLINK_MODE_7=6; MSP_RLINK_MODE_8=7
MSP_RLINK_MODE_NOF=8
class RLinkMode(enum.IntEnum): MODE_1=0; MODE_2=1; MODE_3=2; MODE_4=3; MODE_5=4; MODE_6=5; MODE_7=6; MODE_8=7

# msp_rlink_profile_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_PROFILE_1=0; MSP_RLINK_PROFILE_2=1; MSP_RLINK_PROFILE_3=2; MSP_RLINK_PROFILE_4=3
MSP_RLINK_PROFILE_5=4; MSP_RLINK_PROFILE_6=5; MSP_RLINK_PROFILE_7=6; MSP_RLINK_PROFILE_8=7
MSP_RLINK_PROFILE_NOF=8
class RLinkProfile(enum.IntEnum): PROFILE_1=0; PROFILE_2=1; PROFILE_3=2; PROFILE_4=3; PROFILE_5=4; PROFILE_6=5; PROFILE_7=6; PROFILE_8=7

# msp_rlink_status_t (Geräte-Status) Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_STATUS_CONFIGURING = 0; MSP_RLINK_STATUS_ERROR = 1; MSP_RLINK_STATUS_POWER_CYCLE = 2
MSP_RLINK_STATUS_SHUTDOWN = 3; MSP_RLINK_STATUS_OUT_OF_FOCUS = 4; MSP_RLINK_STATUS_FOCUS = 5
MSP_RLINK_STATUS_NOF = 6
class RLinkDevStatus(enum.IntEnum): CONFIGURING=0; ERROR=1; POWER_CYCLE=2; SHUTDOWN=3; OUT_OF_FOCUS=4; FOCUS=5

# msp_rlink_axis_id_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_AXIS_ID_0 = 0; MSP_RLINK_AXIS_ID_1 = 1; MSP_RLINK_AXIS_ID_2 = 2; # ... bis 31
MSP_RLINK_AXIS_ID_31 = 31; MSP_RLINK_AXIS_ID_NOF = 32
# Nur ein paar Beispiele im Python Enum
class RLinkAxisId(enum.IntEnum): ID_0=0; ID_1=1; ID_2=2; ID_3=3 # Füge bei Bedarf mehr hinzu

# msp_rlink_axis_dir_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_AXIS_DIR_NONE = 0; MSP_RLINK_AXIS_DIR_UP = 1; MSP_RLINK_AXIS_DIR_DOWN = 2; MSP_RLINK_AXIS_DIR_NOF = 3
class RLinkAxisDir(enum.IntEnum): NONE=0; UP=1; DOWN=2

# msp_rlink_err_t Enum Werte (aus msp_rlinkdef.h)
MSP_RLINK_ERR_NONE = 0; MSP_RLINK_ERR_TIMEOUT = 1; MSP_RLINK_ERR_OUT_OF_MEMORY = 2; MSP_RLINK_ERR_MDEV_ERROR = 3
MSP_RLINK_ERR_NAMES = { 0: "ERR_NONE", 1: "ERR_TIMEOUT", 2: "ERR_OUT_OF_MEMORY", 3: "ERR_MDEV_ERROR" }
class RLinkErrorType(enum.IntEnum): NONE=0; TIMEOUT=1; OUT_OF_MEMORY=2; MDEV_ERROR=3

# Event Masks (aus msp_rlink.h)
MSP_RLINK_EV_DISCONNECTED = 0x01
MSP_RLINK_EV_ERROR = 0x02
MSP_RLINK_EV_DATA_READY = 0x04

# --- Typ-Aliase für die C Enums (intern verwendet) ---
msp_status_t = c_int
msp_rlink_btn_t = c_int
msp_rlink_light_t = c_int
msp_rlink_mode_t = c_int
msp_rlink_profile_t = c_int
msp_rlink_devstatus_t = c_int # Interner Alias für msp_rlink_status_t (Enum)
msp_rlink_axis_id_t = c_int
msp_rlink_axis_dir_t = c_int
msp_rlink_err_t = c_int

# --- Funktions-Prototypen (ALLE) ---
try:
    # --- Device Enumeration ---
    lib.msp_rlink_DevicesConstruct.argtypes = []
    lib.msp_rlink_DevicesConstruct.restype = msp_rlink_devices_t_ptr
    lib.msp_rlink_DevicesDestruct.argtypes = [msp_rlink_devices_t_ptr]
    lib.msp_rlink_DevicesDestruct.restype = None
    lib.msp_rlink_GetNumberOfDevices.argtypes = [msp_rlink_devices_t_ptr, ctypes.POINTER(c_size_t)]
    lib.msp_rlink_GetNumberOfDevices.restype = msp_status_t
    lib.msp_rlink_GetDeviceSerialnumber.argtypes = [msp_rlink_devices_t_ptr, c_size_t, ctypes.POINTER(c_char_p)]
    lib.msp_rlink_GetDeviceSerialnumber.restype = msp_status_t
    lib.msp_rlink_GetDeviceDescription.argtypes = [msp_rlink_devices_t_ptr, c_size_t, ctypes.POINTER(c_char_p)]
    lib.msp_rlink_GetDeviceDescription.restype = msp_status_t
    lib.msp_rlink_GetDevice.argtypes = [msp_rlink_devices_t_ptr, c_size_t, ctypes.POINTER(msp_rlink_devinfo_t_ptr)]
    lib.msp_rlink_GetDevice.restype = msp_status_t

    # --- Instance Lifecycle ---
    lib.msp_rlink_Construct.argtypes = [msp_rlink_devinfo_t_ptr]
    lib.msp_rlink_Construct.restype = msp_rlink_t_ptr
    lib.msp_rlink_Destruct.argtypes = [msp_rlink_t_ptr]
    lib.msp_rlink_Destruct.restype = None

    # --- Connection ---
    lib.msp_rlink_Open.argtypes = [msp_rlink_t_ptr]
    lib.msp_rlink_Open.restype = msp_status_t
    lib.msp_rlink_Close.argtypes = [msp_rlink_t_ptr]
    lib.msp_rlink_Close.restype = msp_status_t

    # --- Sending Commands ---
    lib.msp_rlink_SetXy.argtypes = [msp_rlink_t_ptr, c_int8, c_int8]
    lib.msp_rlink_SetXy.restype = msp_status_t
    lib.msp_rlink_SetAxis.argtypes = [msp_rlink_t_ptr, msp_rlink_axis_id_t, msp_rlink_axis_dir_t]
    lib.msp_rlink_SetAxis.restype = msp_status_t
    lib.msp_rlink_SetBtn.argtypes = [msp_rlink_t_ptr, msp_rlink_btn_t, c_bool]
    lib.msp_rlink_SetBtn.restype = msp_status_t
    lib.msp_rlink_SetHorn.argtypes = [msp_rlink_t_ptr, c_bool]
    lib.msp_rlink_SetHorn.restype = msp_status_t
    lib.msp_rlink_SetLight.argtypes = [msp_rlink_t_ptr, msp_rlink_light_t, c_bool]
    lib.msp_rlink_SetLight.restype = msp_status_t
    lib.msp_rlink_SetError.argtypes = [msp_rlink_t_ptr, c_uint8]
    lib.msp_rlink_SetError.restype = msp_status_t
    lib.msp_rlink_Heartbeat.argtypes = [msp_rlink_t_ptr]
    lib.msp_rlink_Heartbeat.restype = msp_status_t

    # --- Getting Status / Data ---
    lib.msp_rlink_GetMode.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_mode_t)]
    lib.msp_rlink_GetMode.restype = msp_status_t
    lib.msp_rlink_GetProfile.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_profile_t)]
    lib.msp_rlink_GetProfile.restype = msp_status_t
    lib.msp_rlink_GetHorn.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_bool)]
    lib.msp_rlink_GetHorn.restype = msp_status_t
    lib.msp_rlink_GetBatteryInfo.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_bool), ctypes.POINTER(c_uint8), ctypes.POINTER(c_float)]
    lib.msp_rlink_GetBatteryInfo.restype = msp_status_t
    lib.msp_rlink_GetVelocity.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_float), ctypes.POINTER(c_float), ctypes.POINTER(c_float)]
    lib.msp_rlink_GetVelocity.restype = msp_status_t
    lib.msp_rlink_GetSpeed.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_uint8), ctypes.POINTER(c_float), ctypes.POINTER(c_uint8)]
    lib.msp_rlink_GetSpeed.restype = msp_status_t
    lib.msp_rlink_GetLight.argtypes = [msp_rlink_t_ptr, msp_rlink_light_t, ctypes.POINTER(c_bool), ctypes.POINTER(c_bool)]
    lib.msp_rlink_GetLight.restype = msp_status_t
    lib.msp_rlink_GetError.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_uint16), ctypes.POINTER(c_uint16)]
    lib.msp_rlink_GetError.restype = msp_status_t
    lib.msp_rlink_GetDevStatus.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_bool), ctypes.POINTER(msp_rlink_devstatus_t), ctypes.POINTER(c_uint8)]
    lib.msp_rlink_GetDevStatus.restype = msp_status_t
    lib.msp_rlink_GetHms.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_uint16), ctypes.POINTER(c_uint16), ctypes.POINTER(c_uint16), ctypes.POINTER(c_bool), ctypes.POINTER(c_bool), ctypes.POINTER(c_bool)]
    lib.msp_rlink_GetHms.restype = msp_status_t
    lib.msp_rlink_GetLatestError.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(msp_rlink_err_t)]
    lib.msp_rlink_GetLatestError.restype = msp_status_t
    lib.msp_rlink_GetStatus.argtypes = [msp_rlink_t_ptr, ctypes.POINTER(c_uint)] # Event flags
    lib.msp_rlink_GetStatus.restype = msp_status_t

    # --- Events ---
    lib.msp_rlink_SetEventNotification.argtypes = [msp_rlink_t_ptr, c_uint, c_void_p, c_void_p] # cvar/mutex as void*
    lib.msp_rlink_SetEventNotification.restype = msp_status_t

    # --- Logging ---
    lib.msp_rlink_Logging.argtypes = [msp_rlink_t_ptr, c_bool]
    lib.msp_rlink_Logging.restype = None
    lib.msp_rlink_SetLogFile.argtypes = [msp_rlink_t_ptr, c_char_p]
    lib.msp_rlink_SetLogFile.restype = c_bool

except AttributeError as e:
    print(f"Error defining function prototype: {e}", file=sys.stderr)
    print("Please ensure the loaded library exports all expected functions.", file=sys.stderr)
    sys.exit(1)

# --- Helper für Status Check ---
def _check_status(status: int, func_name: str, allowed_ok: list[int] = [MSP_OK]):
    """Checks msp_status_t and raises RLinkError on failure."""
    if status not in allowed_ok:
        raise RLinkError(f"Error in {func_name}", status_code=status)

# --- Device Info Structure (returned by enumerate_devices) ---
class RLinkDeviceInfo:
    def __init__(self, index, serial, description, dev_info_ptr):
        self.index: int = index
        self.serial: str = serial
        self.description: str = description
        self._dev_info_ptr: c_void_p = dev_info_ptr # Store the pointer for Construct

    def __repr__(self):
        return f"RLinkDeviceInfo(index={self.index}, serial='{self.serial}', description='{self.description}')"


# --- Vollständige Wrapper-Klasse ---
class RLink:
    """
    Full Python wrapper for the msp_rlink C library.

    Manages the lifecycle and provides methods for all exported functions.
    Note on udev rules: For this wrapper to work correctly, especially
    device enumeration and opening, appropriate udev rules might be necessary
    depending on the library's internal implementation (TTY vs Raw USB access).
    The user's experience indicates potential issues requiring specific, possibly
    non-standard udev configurations provided by the manufacturer.
    """

    def __init__(self, dev_info: RLinkDeviceInfo):
        """
        Initializes the RLink instance using device info obtained from
        RLink.enumerate_devices().

        Args:
            dev_info (RLinkDeviceInfo): Device information object.
        """
        self._lib = lib # Keep reference to library object
        self.handle = None
        self._opened = False
        self._dev_info_ptr = dev_info._dev_info_ptr # Get pointer from info object

        if not self._dev_info_ptr:
            raise ValueError("Invalid dev_info_ptr provided in RLinkDeviceInfo object.")

        print("Constructing RLink object...")
        # Pass the original ctypes object pointer if available, otherwise the value
        handle_candidate = self._dev_info_ptr
        self.handle = self._lib.msp_rlink_Construct(handle_candidate)

        if not self.handle:
            raise RLinkError(f"msp_rlink_Construct failed (returned NULL) for device info {dev_info}")
        print(f"RLink Handle created: {self.handle}")

    @staticmethod
    def enumerate_devices() -> list[RLinkDeviceInfo]:
        """
        Enumerates connected RLink devices.
        Handles construction and destruction of the temporary devices list.

        Returns:
            list[RLinkDeviceInfo]: A list of found devices.
        """
        print("Enumerating RLink devices...")
        devices_handle = lib.msp_rlink_DevicesConstruct()
        if not devices_handle:
            raise RLinkError("msp_rlink_DevicesConstruct failed (returned NULL)")

        devices_list = []
        try:
            num_devices = c_size_t(0)
            status = lib.msp_rlink_GetNumberOfDevices(devices_handle, ctypes.byref(num_devices))
            _check_status(status, "msp_rlink_GetNumberOfDevices")
            print(f"Found {num_devices.value} device(s) during enumeration.")

            for i in range(num_devices.value):
                sn_ptr = c_char_p()
                descr_ptr = c_char_p()
                dev_info_ptr_holder = c_void_p() # Variable to receive the void*

                # Get Serial
                status_sn = lib.msp_rlink_GetDeviceSerialnumber(devices_handle, i, ctypes.byref(sn_ptr))
                _check_status(status_sn, f"msp_rlink_GetDeviceSerialnumber(index={i})")
                serial = sn_ptr.value.decode('utf-8', errors='replace') if sn_ptr.value else "N/A"

                # Get Description
                status_descr = lib.msp_rlink_GetDeviceDescription(devices_handle, i, ctypes.byref(descr_ptr))
                _check_status(status_descr, f"msp_rlink_GetDeviceDescription(index={i})")
                description = descr_ptr.value.decode('utf-8', errors='replace') if descr_ptr.value else "N/A"

                # Get Device Info Pointer
                status_dev = lib.msp_rlink_GetDevice(devices_handle, i, ctypes.byref(dev_info_ptr_holder))
                _check_status(status_dev, f"msp_rlink_GetDevice(index={i})")
                if not dev_info_ptr_holder.value:
                     print(f"Warning: msp_rlink_GetDevice returned NULL pointer for index {i}", file=sys.stderr)
                     # Skip this device or handle error appropriately
                     continue

                # Store info
                devices_list.append(RLinkDeviceInfo(i, serial, description, dev_info_ptr_holder.value))

        finally:
            # Clean up the devices list handle
            if devices_handle:
                lib.msp_rlink_DevicesDestruct(devices_handle)
                print("Device enumeration list destroyed.")

        return devices_list

    def open(self):
        """Opens the connection to the RLink device."""
        if not self.handle: raise RLinkError("Handle is invalid")
        if self._opened: print("Connection already open."); return
        print("Opening RLink connection...")
        status = self._lib.msp_rlink_Open(self.handle)
        # Check status - raise error if failed
        _check_status(status, "msp_rlink_Open")
        self._opened = True
        print("RLink connection opened successfully.")

    def close(self):
        """Closes the connection to the RLink device."""
        if self.handle and self._opened:
            print("Closing RLink connection...")
            status = self._lib.msp_rlink_Close(self.handle)
            self._opened = False # Assume closed even if status indicates error
            try:
                # Check status but don't raise error, just print warning
                 _check_status(status, "msp_rlink_Close")
                 print("RLink connection closed.")
            except RLinkError as e:
                 print(f"Warning during close: {e}", file=sys.stderr)

    def destruct(self):
        """Closes connection and destroys the RLink handle."""
        self.close()
        if self.handle:
            print("Destroying RLink handle...")
            self._lib.msp_rlink_Destruct(self.handle)
            self.handle = None
            print("RLink handle destroyed.")

    def __del__(self):
        """Destructor ensures cleanup."""
        self.destruct() # Call explicit cleanup method

    def __enter__(self):
        """Context manager entry: opens the device."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: closes the device."""
        self.close() # Consider calling self.destruct() if appropriate for context manager

    # --- Wrapped Methods ---

    def heartbeat(self):
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_Heartbeat(self.handle)
        try: _check_status(status, "msp_rlink_Heartbeat")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr) # Don't raise on heartbeat fail?

    def set_xy(self, x: int, y: int):
        if not self.handle or not self._opened: return
        x_c = c_int8(max(-127, min(127, x))); y_c = c_int8(max(-127, min(127, y)))
        status = self._lib.msp_rlink_SetXy(self.handle, x_c, y_c)
        try: _check_status(status, f"msp_rlink_SetXy({x},{y})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def set_axis(self, axis_id: RLinkAxisId, direction: RLinkAxisDir):
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetAxis(self.handle, c_int(axis_id.value), c_int(direction.value))
        try: _check_status(status, f"msp_rlink_SetAxis(ID={axis_id.value}, Dir={direction.value})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def set_button(self, btn: RLinkButton, pressed: bool):
        """Sets the state of a specific button."""
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetBtn(self.handle, c_int(btn.value), c_bool(pressed))
        try: _check_status(status, f"msp_rlink_SetBtn(Btn={btn.value}, Pressed={pressed})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def set_horn(self, enable: bool):
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetHorn(self.handle, c_bool(enable))
        try: _check_status(status, f"msp_rlink_SetHorn({enable})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def set_light(self, light: RLinkLight, enable: bool):
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetLight(self.handle, c_int(light.value), c_bool(enable))
        try: _check_status(status, f"msp_rlink_SetLight(ID={light.value}, Enable={enable})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def set_error(self, error_code: int):
        """Sets the error code sent by the client (0 = no error)."""
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetError(self.handle, c_uint8(error_code))
        try: _check_status(status, f"msp_rlink_SetError({error_code})")
        except RLinkError as e: print(f"Warning: {e}", file=sys.stderr)

    def get_mode(self) -> RLinkMode:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        mode_val = msp_rlink_mode_t()
        status = self._lib.msp_rlink_GetMode(self.handle, ctypes.byref(mode_val))
        _check_status(status, "msp_rlink_GetMode")
        return RLinkMode(mode_val.value)

    def get_profile(self) -> RLinkProfile:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        profile_val = msp_rlink_profile_t()
        status = self._lib.msp_rlink_GetProfile(self.handle, ctypes.byref(profile_val))
        _check_status(status, "msp_rlink_GetProfile")
        return RLinkProfile(profile_val.value)

    def get_horn(self) -> bool:
        """Gets the actual horn status reported by the device."""
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        horn_val = c_bool()
        status = self._lib.msp_rlink_GetHorn(self.handle, ctypes.byref(horn_val))
        _check_status(status, "msp_rlink_GetHorn")
        return horn_val.value

    def get_battery_info(self) -> tuple[bool, int, float]:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        low = c_bool(); gauge = c_uint8(); current = c_float()
        status = self._lib.msp_rlink_GetBatteryInfo(self.handle, ctypes.byref(low), ctypes.byref(gauge), ctypes.byref(current))
        _check_status(status, "msp_rlink_GetBatteryInfo")
        return low.value, gauge.value, current.value

    def get_velocity(self) -> tuple[float, float, float]:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        m1 = c_float(); m2 = c_float(); turn = c_float()
        status = self._lib.msp_rlink_GetVelocity(self.handle, ctypes.byref(m1), ctypes.byref(m2), ctypes.byref(turn))
        _check_status(status, "msp_rlink_GetVelocity")
        return m1.value, m2.value, turn.value

    def get_speed(self) -> tuple[int, float, int]:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        speed_val = c_uint8(); true_speed = c_float(); limit = c_uint8()
        status = self._lib.msp_rlink_GetSpeed(self.handle, ctypes.byref(speed_val), ctypes.byref(true_speed), ctypes.byref(limit))
        _check_status(status, "msp_rlink_GetSpeed")
        return speed_val.value, true_speed.value, limit.value

    def get_light(self, light: RLinkLight) -> tuple[bool, bool]:
        """Gets the actual status of a specific light (active, lit)."""
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        active = c_bool(); lit = c_bool()
        status = self._lib.msp_rlink_GetLight(self.handle, c_int(light.value), ctypes.byref(active), ctypes.byref(lit))
        _check_status(status, f"msp_rlink_GetLight(ID={light.value})")
        return active.value, lit.value

    def get_error_codes(self) -> tuple[int, int]:
        """Gets interface and RNet error codes."""
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        if_err = c_uint16(); rnet_err = c_uint16()
        status = self._lib.msp_rlink_GetError(self.handle, ctypes.byref(if_err), ctypes.byref(rnet_err))
        _check_status(status, "msp_rlink_GetError")
        return if_err.value, rnet_err.value

    def get_device_status(self) -> tuple[bool, RLinkDevStatus, int]:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        oon = c_bool(); dev_status = msp_rlink_devstatus_t(); warning = c_uint8()
        status = self._lib.msp_rlink_GetDevStatus(self.handle, ctypes.byref(oon), ctypes.byref(dev_status), ctypes.byref(warning))
        _check_status(status, "msp_rlink_GetDevStatus")
        return oon.value, RLinkDevStatus(dev_status.value), warning.value

    def get_hms(self) -> tuple[int, int, int, bool, bool, bool]:
        if not self.handle or not self._opened: raise RLinkError("RLink not open")
        input_p = c_uint16(); inter_p = c_uint16(); output_p = c_uint16()
        sel_in = c_bool(); sel_inter = c_bool(); sel_out = c_bool()
        status = self._lib.msp_rlink_GetHms(self.handle, ctypes.byref(input_p), ctypes.byref(inter_p), ctypes.byref(output_p),
                                            ctypes.byref(sel_in), ctypes.byref(sel_inter), ctypes.byref(sel_out))
        _check_status(status, "msp_rlink_GetHms")
        return input_p.value, inter_p.value, output_p.value, sel_in.value, sel_inter.value, sel_out.value

    def get_latest_error(self) -> RLinkErrorType:
        """Gets the last RLink-specific error code."""
        if not self.handle: raise RLinkError("Handle is invalid") # Can be called even if not open? Assume yes.
        err_val = msp_rlink_err_t()
        status = self._lib.msp_rlink_GetLatestError(self.handle, ctypes.byref(err_val))
        # Don't use _check_status here as it might mask the actual error code
        if status != MSP_OK:
            # Raise a specific error if getting the error code itself fails
             raise RLinkError(f"msp_rlink_GetLatestError failed itself", status_code=status)
        return RLinkErrorType(err_val.value)

    def get_status_flags(self) -> int:
        """Gets the event status flags set by the library."""
        if not self.handle: raise RLinkError("Handle is invalid")
        flags = c_uint()
        status = self._lib.msp_rlink_GetStatus(self.handle, ctypes.byref(flags))
        _check_status(status, "msp_rlink_GetStatus")
        return flags.value

    def set_event_notification(self, mask: int, cvar_ptr: c_void_p = None, mutex_ptr: c_void_p = None):
        """
        Sets up event notifications using C-level condition variables/mutexes.
        WARNING: Passing Python threading primitives here is not directly possible.
                 Use with caution, likely requires custom C extensions or OS handles.
        """
        if not self.handle: raise RLinkError("Handle is invalid")
        status = self._lib.msp_rlink_SetEventNotification(self.handle, c_uint(mask), cvar_ptr, mutex_ptr)
        _check_status(status, "msp_rlink_SetEventNotification")
        print("Event notification set (Callbacks depend on valid cvar/mutex pointers).")

    def set_logging(self, enable: bool):
        """Enables or disables internal logging."""
        if not self.handle: raise RLinkError("Handle is invalid")
        # WARNING: Calling this before Open() caused issues in previous tests with fallback mode!
        # Consider calling only after Open() is successful.
        print(f"Setting internal logging to: {enable}")
        self._lib.msp_rlink_Logging(self.handle, c_bool(enable))

    def set_log_file(self, filename: str) -> bool:
        """Sets the file for internal logging."""
        if not self.handle: raise RLinkError("Handle is invalid")
        # WARNING: Calling this before Open() caused issues in previous tests with fallback mode!
        # Consider calling only after Open() is successful.
        filename_bytes = filename.encode('utf-8')
        print(f"Setting internal log file to: {filename}")
        result = self._lib.msp_rlink_SetLogFile(self.handle, c_char_p(filename_bytes))
        if not result:
            print(f"Warning: Failed to set log file '{filename}'", file=sys.stderr)
        return result

# --- Ende Klasse RLink ---