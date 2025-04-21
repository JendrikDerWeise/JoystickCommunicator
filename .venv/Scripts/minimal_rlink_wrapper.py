import ctypes
import os
import platform
import sys

# --- Konfiguration: Pfad zur Shared Library ---
# Passe diesen Pfad ggf. an oder stelle sicher, dass die Lib im Suchpfad ist.
LIB_FILENAME = 'libMspRlink.so'
try:
    script_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
    LIB_PATH = os.path.join(script_dir, 'lib', LIB_FILENAME) # Annahme: Im Unterordner 'lib'
    if not os.path.exists(LIB_PATH):
         # Fallback: Suche im selben Ordner wie das Skript
         LIB_PATH = os.path.join(script_dir, LIB_FILENAME)
    if not os.path.exists(LIB_PATH):
        # Fallback: Suche in systemweiten Pfaden
        LIB_PATH = LIB_FILENAME # ctypes sucht dann selbst
except NameError:
     LIB_PATH = LIB_FILENAME # Genereller Fallback

# --- Lade die Shared Library ---
try:
    lib = ctypes.CDLL(LIB_PATH)
    print(f"Successfully loaded shared library: {LIB_PATH}")
except OSError as e:
    print(f"Error loading shared library '{LIB_PATH}': {e}", file=sys.stderr)
    print("Please ensure the library and its dependencies (e.g., libMspMdev.so) are findable.", file=sys.stderr)
    sys.exit(1)

# --- Grundlegende C-Typ Definitionen ---
c_int8 = ctypes.c_int8
c_uint8 = ctypes.c_uint8
c_size_t = ctypes.c_size_t
c_void_p = ctypes.c_void_p
c_int = ctypes.c_int
POINTER = ctypes.POINTER

# --- Spezifische Typ-Aliase und Konstanten ---
msp_status_t = c_int
msp_rlink_devices_t_ptr = c_void_p
msp_rlink_devinfo_t_ptr = c_void_p
msp_rlink_t_ptr = c_void_p

MSP_OK = 0

# --- Minimale Fehlerbehandlung ---
class MinimalRLinkError(Exception):
    """Einfache Exception für diesen Wrapper."""
    pass

def _check_status(status: int, func_name: str):
    """Prüft den Statuscode und wirft eine Exception bei Fehlern."""
    # Wir kennen hier nur MSP_OK
    if status != MSP_OK:
        raise MinimalRLinkError(f"Error in function '{func_name}': Status code {status}")

# --- Funktionsprototypen (Nur die benötigten, mit korrekter Syntax!) ---

try:
    # msp_rlink_DevicesConstruct() -> msp_rlink_devices_t*
    msp_rlink_DevicesConstruct = lib.msp_rlink_DevicesConstruct
    msp_rlink_DevicesConstruct.argtypes = [] # Keine Argumente
    msp_rlink_DevicesConstruct.restype = msp_rlink_devices_t_ptr

    # msp_rlink_DevicesDestruct(msp_rlink_devices_t* devices) -> void
    msp_rlink_DevicesDestruct = lib.msp_rlink_DevicesDestruct
    msp_rlink_DevicesDestruct.argtypes = [msp_rlink_devices_t_ptr]
    msp_rlink_DevicesDestruct.restype = None # void

    # msp_rlink_GetNumberOfDevices(msp_rlink_devices_t* devices, size_t* nofDevices) -> msp_status_t
    msp_rlink_GetNumberOfDevices = lib.msp_rlink_GetNumberOfDevices
    msp_rlink_GetNumberOfDevices.argtypes = [msp_rlink_devices_t_ptr, POINTER(c_size_t)]
    msp_rlink_GetNumberOfDevices.restype = msp_status_t

    # msp_rlink_GetDevice(msp_rlink_devices_t* devices, size_t index, msp_rlink_devinfo_t** devinfo) -> msp_status_t
    msp_rlink_GetDevice = lib.msp_rlink_GetDevice
    # ACHTUNG: Zweites Argument ist size_t (Index), drittes ist Pointer auf Pointer!
    msp_rlink_GetDevice.argtypes = [msp_rlink_devices_t_ptr, c_size_t, POINTER(msp_rlink_devinfo_t_ptr)]
    msp_rlink_GetDevice.restype = msp_status_t

    # msp_rlink_Construct(msp_rlink_devinfo_t* devinfo) -> msp_rlink_t*
    msp_rlink_Construct = lib.msp_rlink_Construct
    msp_rlink_Construct.argtypes = [msp_rlink_devinfo_t_ptr]
    msp_rlink_Construct.restype = msp_rlink_t_ptr

    # msp_rlink_Destruct(msp_rlink_t* self) -> void
    msp_rlink_Destruct = lib.msp_rlink_Destruct
    msp_rlink_Destruct.argtypes = [msp_rlink_t_ptr]
    msp_rlink_Destruct.restype = None # void

    # msp_rlink_Open(msp_rlink_t* self) -> msp_status_t
    msp_rlink_Open = lib.msp_rlink_Open
    msp_rlink_Open.argtypes = [msp_rlink_t_ptr]
    msp_rlink_Open.restype = msp_status_t

    # msp_rlink_Close(msp_rlink_t* self) -> msp_status_t
    msp_rlink_Close = lib.msp_rlink_Close
    msp_rlink_Close.argtypes = [msp_rlink_t_ptr]
    msp_rlink_Close.restype = msp_status_t # Gibt Status zurück!

    # msp_rlink_Heartbeat(msp_rlink_t* self) -> msp_status_t
    msp_rlink_Heartbeat = lib.msp_rlink_Heartbeat
    msp_rlink_Heartbeat.argtypes = [msp_rlink_t_ptr]
    msp_rlink_Heartbeat.restype = msp_status_t # Gibt Status zurück!

    # msp_rlink_SetXy(msp_rlink_t* self, int8_t x, int8_t y) -> msp_status_t
    msp_rlink_SetXy = lib.msp_rlink_SetXy
    msp_rlink_SetXy.argtypes = [msp_rlink_t_ptr, c_int8, c_int8]
    msp_rlink_SetXy.restype = msp_status_t # Gibt Status zurück!

except AttributeError as e:
    print(f"Error setting up function prototype: {e}", file=sys.stderr)
    print("Ensure the function exists in the shared library.", file=sys.stderr)
    sys.exit(1)

# --- Optionale minimale Wrapper-Klasse ---
class MinimalRlink:
    """Eine sehr einfache Klasse, die den Handle kapselt."""
    def __init__(self, dev_info_ptr):
        self.handle = msp_rlink_Construct(dev_info_ptr)
        if not self.handle:
            raise MinimalRLinkError("msp_rlink_Construct returned NULL handle.")
        self._opened = False
        print(f"MinimalRlink: Constructed handle {self.handle}")

    def open(self):
        print("MinimalRlink: Calling msp_rlink_Open...")
        status = msp_rlink_Open(self.handle)
        print(f"MinimalRlink: msp_rlink_Open returned status {status}")
        _check_status(status, "msp_rlink_Open")
        self._opened = True
        print("MinimalRlink: Opened successfully.")

    def close(self):
        if self._opened and self.handle:
            print("MinimalRlink: Calling msp_rlink_Close...")
            status = msp_rlink_Close(self.handle)
            print(f"MinimalRlink: msp_rlink_Close returned status {status}")
            self._opened = False
            # Wir prüfen den Status hier nicht, um Destruct zu erlauben
            # _check_status(status, "msp_rlink_Close")
        else:
             print("MinimalRlink: Already closed or not opened.")


    def heartbeat(self):
        if self._opened and self.handle:
            # print("MinimalRlink: Calling msp_rlink_Heartbeat...") # Zu viel Output
            status = msp_rlink_Heartbeat(self.handle)
            # Herzschlagfehler oft nicht kritisch, daher keine Exception?
            if status != MSP_OK:
                 print(f"Warning: msp_rlink_Heartbeat failed with status {status}", file=sys.stderr)
        else:
             print("Warning: Tried to send heartbeat but not open.", file=sys.stderr)


    def set_xy(self, x, y):
        if self._opened and self.handle:
            # print(f"MinimalRlink: Calling msp_rlink_SetXy({x}, {y})...") # Zu viel Output
            status = msp_rlink_SetXy(self.handle, c_int8(x), c_int8(y))
            # Fehler beim Setzen kann passieren, wirft aber hier Exception
            _check_status(status, f"msp_rlink_SetXy({x},{y})")
        else:
             print(f"Warning: Tried to set_xy({x},{y}) but not open.", file=sys.stderr)


    def __del__(self):
        # Wird aufgerufen, wenn das Objekt zerstört wird (Garbage Collection)
        if hasattr(self, 'handle') and self.handle:
             print("MinimalRlink: In __del__, ensuring closed and destructed.")
             try:
                  self.close() # Versuche zu schließen
             finally:
                  # Rufe Destruct auf, auch wenn Close fehlschlägt
                  print("MinimalRlink: Calling msp_rlink_Destruct...")
                  msp_rlink_Destruct(self.handle)
                  print("MinimalRlink: msp_rlink_Destruct called.")
                  self.handle = None # Verhindere Doppelaufruf

# --- Beispielverwendung (ähnlich deinem minimal_test.py) ---
if __name__ == "__main__":
    import time

    print("--- Start Minimal Wrapper Test ---")
    # Stelle sicher, dass die originale, fehlerhafte udev-Regel aktiv ist!
    print("INFO: Running with original (faulty) udev rule expected.")

    devices_ptr = None
    rlink_instance = None

    try:
        print("\nEnumerating devices...")
        devices_ptr = msp_rlink_DevicesConstruct()
        if not devices_ptr:
             raise MinimalRLinkError("msp_rlink_DevicesConstruct failed.")

        nofDevices = c_size_t(0)
        status = msp_rlink_GetNumberOfDevices(devices_ptr, ctypes.byref(nofDevices))
        _check_status(status, "msp_rlink_GetNumberOfDevices")
        print(f"Number of connected devices: {nofDevices.value}")

        if nofDevices.value > 0:
            devinfo_ptr = c_void_p() # Pointer, der gefüllt wird
            devid = 0 # Index des ersten Geräts
            print(f"\nGetting device info for index {devid}...")
            status = msp_rlink_GetDevice(devices_ptr, c_size_t(devid), ctypes.byref(devinfo_ptr))
            _check_status(status, "msp_rlink_GetDevice")
            print(f"Device info pointer retrieved: {devinfo_ptr}")

            if devinfo_ptr: # Prüfen, ob der Pointer gültig ist
                print("\nConstructing RLink object using MinimalRlink class...")
                # Verwende die minimale Klasse
                rlink_instance = MinimalRlink(devinfo_ptr)

                print("\nOpening connection using instance method...")
                rlink_instance.open() # Ruft intern msp_rlink_Open auf

                print("\nStarting control loop...")
                idx = 0
                start_time = time.time()
                while idx < 30 and time.time() - start_time < 15: # Max 15 Sekunden
                    idx = idx + 1
                    rlink_instance.heartbeat()

                    if idx > 25:
                        if idx == 21: print("Driving forward...")
                        rlink_instance.set_xy(0, 100)
                    else: # idx <= 20
                        if idx == 1: print("Sending neutral...")
                        rlink_instance.set_xy(0, 0)

                    time.sleep(0.1)

                print("\nControl loop finished.")

            else:
                 print("Error: msp_rlink_GetDevice did not return a valid devinfo pointer.")

        else:
            print("No devices found!")

    except MinimalRLinkError as e:
        print(f"\n--- MinimalRLinkError ---")
        print(f"{e}")
        print(f"------------------------")
    except Exception as e:
        print(f"\n--- Unexpected Error ---")
        print(f"{e}")
        import traceback
        traceback.print_exc()
        print(f"------------------------")

    finally:
        # Wichtig: Räume die Geräte-Liste auf
        if devices_ptr:
            print("\nCleaning up device list...")
            msp_rlink_DevicesDestruct(devices_ptr)
            print("Device list destructed.")

        # Das rlink_instance Objekt wird durch __del__ aufgeräumt,
        # wenn es nicht mehr referenziert wird (oder explizit oben, falls Fehler).
        # Wir brauchen hier keinen expliziten Destruct-Aufruf mehr.

        print("\n--- Minimal Wrapper Test End ---")