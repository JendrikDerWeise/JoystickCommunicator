# mini_rlink_wrapper_v2.py
import ctypes
import os
import platform
import sys
import enum
import time # Für eventuelle Delays

class RLinkError(Exception):
    """Custom exception for RLink errors."""
    pass

# Lade die Bibliothek (Pfad wie im funktionierenden Minimal-Skript annehmen)
# PASSE DIESEN PFAD GGF. AN!
LIB_PATH = "/usr/local/lib/libMspRlink.so"
# Alternativ versuchen, relativ zum Skript zu laden, falls im Projekt vorhanden
try:
    script_dir = os.path.dirname(__file__) if '__file__' in locals() else '.'
    local_path = os.path.join(script_dir, 'libMspRlink.so')
    if os.path.exists(local_path):
        LIB_PATH = local_path
    elif not os.path.exists(LIB_PATH) and platform.system() == "Linux":
         # Fallback, wenn weder lokal noch /usr/local/lib
         local_path = os.path.join(script_dir, 'lib/libMspRlink.so') # Versuch im unterordner
         if os.path.exists(local_path):
              LIB_PATH = local_path
         elif not os.path.exists(LIB_PATH):
              # Letzter Versuch im venv/lib, falls doch vorhanden
              venv_path = os.path.join(script_dir, '.venv/Scripts/lib/libMspRlink.so')
              if os.path.exists(venv_path):
                   LIB_PATH = venv_path

except NameError:
    pass # LIB_PATH bleibt auf /usr/local/lib

if not os.path.exists(LIB_PATH):
    # Wenn immer noch nicht gefunden, Fehler ausgeben
    raise FileNotFoundError(f"Shared library libMspRlink.so not found at expected paths like: {LIB_PATH}")

try:
    lib = ctypes.CDLL(LIB_PATH)
    print(f"Successfully loaded shared library: {LIB_PATH}")
except OSError as e:
    print(f"Error loading shared library from {LIB_PATH}: {e}", file=sys.stderr)
    sys.exit(1)

# --- C Typen ---
c_int8 = ctypes.c_int8
c_uint8 = ctypes.c_uint8
c_size_t = ctypes.c_size_t
c_void_p = ctypes.c_void_p
c_bool = ctypes.c_bool
c_int = ctypes.c_int # Für Status und Enums

# --- Konstanten ---
MSP_OK = 0
# Füge hier direkt die Werte für msp_rlink_light_t hinzu (aus rlink_wrapper.py kopiert)
MSP_RLINK_LIGHT_BRAKE = 0
MSP_RLINK_LIGHT_DIP = 1
MSP_RLINK_LIGHT_HAZARD = 2
MSP_RLINK_LIGHT_LEFT = 3
MSP_RLINK_LIGHT_RIGHT = 4
MSP_RLINK_LIGHT_NOF = 5

# Optional: Python Enum für Lesbarkeit im Haupt-Skript
class RLinkLight(enum.IntEnum):
    BRAKE = MSP_RLINK_LIGHT_BRAKE
    DIP = MSP_RLINK_LIGHT_DIP
    HAZARD = MSP_RLINK_LIGHT_HAZARD
    LEFT = MSP_RLINK_LIGHT_LEFT
    RIGHT = MSP_RLINK_LIGHT_RIGHT

# --- Funktions-Prototypen (NUR die benötigten, mit KORREKTEN argtypes) ---
try:
    # void* msp_rlink_DevicesConstruct(void)
    lib.msp_rlink_DevicesConstruct.argtypes = []
    lib.msp_rlink_DevicesConstruct.restype = c_void_p

    # msp_status_t msp_rlink_GetNumberOfDevices(msp_rlink_devices_t* devices, size_t* nofDevices)
    lib.msp_rlink_GetNumberOfDevices.argtypes = [c_void_p, ctypes.POINTER(c_size_t)]
    lib.msp_rlink_GetNumberOfDevices.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_GetDevice(msp_rlink_devices_t* devices, size_t index, msp_rlink_devinfo_t** devinfo)
    lib.msp_rlink_GetDevice.argtypes = [c_void_p, c_size_t, ctypes.POINTER(c_void_p)] # POINTER(c_void_p) für devinfo**
    lib.msp_rlink_GetDevice.restype = c_int # msp_status_t

    # msp_rlink_t* msp_rlink_Construct(msp_rlink_devinfo_t* devinfo)
    lib.msp_rlink_Construct.argtypes = [c_void_p]
    lib.msp_rlink_Construct.restype = c_void_p # msp_rlink_t*

    # void msp_rlink_Destruct(msp_rlink_t* self)
    lib.msp_rlink_Destruct.argtypes = [c_void_p]
    lib.msp_rlink_Destruct.restype = None

    # msp_status_t msp_rlink_Open(msp_rlink_t* self)
    lib.msp_rlink_Open.argtypes = [c_void_p]
    lib.msp_rlink_Open.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_Close(msp_rlink_t* self)
    lib.msp_rlink_Close.argtypes = [c_void_p]
    lib.msp_rlink_Close.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_Heartbeat(msp_rlink_t* self)
    lib.msp_rlink_Heartbeat.argtypes = [c_void_p]
    lib.msp_rlink_Heartbeat.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_SetXy(msp_rlink_t* self, int8_t x, int8_t y)
    lib.msp_rlink_SetXy.argtypes = [c_void_p, c_int8, c_int8]
    lib.msp_rlink_SetXy.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_SetHorn(msp_rlink_t* self, bool enable)
    lib.msp_rlink_SetHorn.argtypes = [c_void_p, c_bool]
    lib.msp_rlink_SetHorn.restype = c_int # msp_status_t

    # msp_status_t msp_rlink_SetLight(msp_rlink_t* self, msp_rlink_light_t light, bool enable)
    # Annahme: msp_rlink_light_t ist int-basiert
    lib.msp_rlink_SetLight.argtypes = [c_void_p, c_int, c_bool]
    lib.msp_rlink_SetLight.restype = c_int # msp_status_t

except AttributeError as e:
    print(f"Fehler beim Definieren der Funktionsprototypen: {e}", file=sys.stderr)
    print("Stelle sicher, dass die Bibliothek geladen wurde und die Funktionen exportiert sind.", file=sys.stderr)
    sys.exit(1)


# --- Einfache Wrapper-Klasse ---
class MiniRlink:
    """
    Minimaler Wrapper basierend auf den funktionierenden Teilen,
    angepasst für Tastatursteuerung (Fahren, Licht, Hupe).
    NUTZT DEN RAW-USB-FALLBACK der Bibliothek.
    Setzt voraus, dass die *originale, fehlerhafte* udev-Regel aktiv ist!
    """
    def __init__(self, device_index=0):
        self.handle = None
        self.devinfo = None
        self._opened = False
        self._lib = lib # Referenz halten

        devices_handle = self._lib.msp_rlink_DevicesConstruct()
        if not devices_handle:
            raise RLinkError("msp_rlink_DevicesConstruct fehlgeschlagen (NULL erhalten)")

        try:
            nofDevices = c_size_t(0)
            status = self._lib.msp_rlink_GetNumberOfDevices(devices_handle, ctypes.byref(nofDevices))
            if status != MSP_OK:
                raise RLinkError(f"msp_rlink_GetNumberOfDevices fehlgeschlagen, Status: {status}")
            if nofDevices.value == 0:
                raise RLinkError("Keine RLink-Geräte gefunden bei Enumeration.")
            if device_index >= nofDevices.value:
                 raise RLinkError(f"Geräteindex {device_index} ungültig (nur {nofDevices.value} Geräte gefunden).")

                 # Erstelle eine Variable, die den Output-Pointer (msp_rlink_devinfo_t* / void*) aufnehmen kann
                 devinfo_holder = c_void_p()

                 # Übergebe die Adresse dieser Variable an die C-Funktion.
                 # byref(devinfo_holder) hat den korrekten Typ POINTER(c_void_p)
                 status = self._lib.msp_rlink_GetDevice(devices_handle, device_index, ctypes.byref(devinfo_holder))

                 # Prüfe Status und ob der zurückgegebene Pointer gültig ist (nicht NULL)
                 if status != MSP_OK or not devinfo_holder.value:  # .value prüft auf non-NULL
                     # Den Pointer-Wert ausgeben, falls vorhanden, auch bei Fehlerstatus
                     returned_ptr_value = devinfo_holder.value if devinfo_holder else 'None'
                     raise RLinkError(
                         f"msp_rlink_GetDevice für Index {device_index} fehlgeschlagen. Status: {status}, Erhaltener Pointer-Wert: {returned_ptr_value}")

                 # Speichere den Pointer-Wert, den die C-Funktion in devinfo_holder geschrieben hat
                 #self.devinfo = devinfo_holder.value  # .value gibt den eigentlichen Pointer-Wert zurück
                 # Optional: Behalte das ctypes-Objekt, falls du es brauchst
            self._devinfo_c_void_p = devinfo_holder
            print(f"Geräteinformation für Index {device_index} erhalten (Pointer Objekt: {self._devinfo_c_void_p}).")

            # Destruct der Device-Liste wird hier nicht gemacht, da devinfo noch gebraucht wird
            # TODO: Klären, ob DevicesDestruct nach Construct aufgerufen werden muss/sollte. Annahme: Nein.

            print("Konstruiere RLink Objekt...")
            self.handle = self._lib.msp_rlink_Construct(self._devinfo_c_void_p)
            if not self.handle:
                raise RLinkError(
                    f"msp_rlink_Construct fehlgeschlagen (NULL erhalten) bei Übergabe von devinfo={self._devinfo_c_void_p}")
            print(f"RLink Handle erhalten: {self.handle}")

        finally:
            # TODO: DevicesDestruct aufrufen? Wenn ja, wann?
            # self._lib.msp_rlink_DevicesDestruct(devices_handle) # Möglicherweise hier?
            pass

    def open(self):
        if not self.handle: raise RLinkError("Handle ist ungültig.")
        if self._opened: return # Bereits offen

        print("Öffne RLink Verbindung...")
        status = self._lib.msp_rlink_Open(self.handle)
        if status != MSP_OK:
            # Hier den Fehlercode ausgeben, der im funktionierenden Skript kam
            raise RLinkError(f"msp_rlink_Open fehlgeschlagen, Status: {status}")
        self._opened = True
        print("RLink Verbindung geöffnet.")

    def close(self):
        if self.handle and self._opened:
            print("Schließe RLink Verbindung...")
            status = self._lib.msp_rlink_Close(self.handle)
            self._opened = False # Auch wenn Close fehlschlägt
            if status != MSP_OK:
                 print(f"Warnung: msp_rlink_Close fehlgeschlagen, Status: {status}", file=sys.stderr)
            else:
                 print("RLink Verbindung geschlossen.")

    def heartbeat(self):
        if not self.handle or not self._opened: return # Ignorieren wenn nicht offen
        status = self._lib.msp_rlink_Heartbeat(self.handle)
        if status != MSP_OK:
            print(f"Warnung: msp_rlink_Heartbeat fehlgeschlagen, Status: {status}", file=sys.stderr)
            # TODO: Fehler ernster nehmen? Quit Event setzen?
            # quit_event.set() # Beispiel, braucht Zugriff auf quit_event

    def set_xy(self, x: int, y: int):
        if not self.handle or not self._opened: return
        # Werte auf int8 begrenzen
        x_c = c_int8(max(-127, min(127, x)))
        y_c = c_int8(max(-127, min(127, y)))
        status = self._lib.msp_rlink_SetXy(self.handle, x_c, y_c)
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetXy fehlgeschlagen, Status: {status}", file=sys.stderr)

    def set_horn(self, enable: bool):
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetHorn(self.handle, c_bool(enable))
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetHorn fehlgeschlagen, Status: {status}", file=sys.stderr)

    def set_light(self, light: RLinkLight, enable: bool):
        if not self.handle or not self._opened: return
        light_c = c_int(light.value) # Nutze den Int-Wert des Enums
        status = self._lib.msp_rlink_SetLight(self.handle, light_c, c_bool(enable))
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetLight fehlgeschlagen, Status: {status}", file=sys.stderr)

    def __del__(self):
        self.close() # Versuch zu schließen
        if self.handle:
            try:
                # TODO: Wann sollte Destruct aufgerufen werden? Evtl. erst wenn devinfo nicht mehr gebraucht wird?
                # self._lib.msp_rlink_Destruct(self.handle)
                # print("RLink Handle zerstört.")
                pass # Verschiebe Destruct, falls devinfo länger leben muss
            except Exception as e:
                print(f"Fehler in __del__ beim Destruct: {e}", file=sys.stderr)
            self.handle = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()