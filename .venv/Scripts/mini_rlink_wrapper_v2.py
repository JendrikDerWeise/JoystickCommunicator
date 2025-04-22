# mini_rlink_wrapper_v2.py
import ctypes
import os
import platform
import sys
import enum
import time # Für eventuelle Delays

class RLinkError(Exception):
    """Custom exception for RLink errors."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

    def __str__(self):
        base_msg = super().__str__()
        if self.status_code is not None:
            # TODO: MSP_STATUS_NAMES Mapping hinzufügen für bessere Meldungen
            return f"{base_msg} [Status={self.status_code}]"
        else:
            return base_msg

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
c_float = ctypes.c_float
c_char_p = ctypes.c_char_p

# --- Konstanten ---
MSP_OK = 0
# Licht-Konstanten
MSP_RLINK_LIGHT_BRAKE = 0
MSP_RLINK_LIGHT_DIP = 1
MSP_RLINK_LIGHT_HAZARD = 2
MSP_RLINK_LIGHT_LEFT = 3
MSP_RLINK_LIGHT_RIGHT = 4
MSP_RLINK_LIGHT_NOF = 5
# Axis ID Konstanten (Beispiele)
MSP_RLINK_AXIS_ID_0 = 0
MSP_RLINK_AXIS_ID_1 = 1
MSP_RLINK_AXIS_ID_2 = 2
# ... etc. bis MSP_RLINK_AXIS_ID_31 ...
# Axis Direction Konstanten
MSP_RLINK_AXIS_DIR_NONE = 0
MSP_RLINK_AXIS_DIR_UP = 1
MSP_RLINK_AXIS_DIR_DOWN = 2

# --- Python Enums für Lesbarkeit ---
class RLinkLight(enum.IntEnum):
    BRAKE = MSP_RLINK_LIGHT_BRAKE
    DIP = MSP_RLINK_LIGHT_DIP
    HAZARD = MSP_RLINK_LIGHT_HAZARD
    LEFT = MSP_RLINK_LIGHT_LEFT
    RIGHT = MSP_RLINK_LIGHT_RIGHT

class RLinkAxisId(enum.IntEnum):
    ID_0 = MSP_RLINK_AXIS_ID_0
    ID_1 = MSP_RLINK_AXIS_ID_1
    ID_2 = MSP_RLINK_AXIS_ID_2
    # Füge weitere hinzu, wenn bekannt/benötigt

class RLinkAxisDir(enum.IntEnum):
    NONE = MSP_RLINK_AXIS_DIR_NONE
    UP = MSP_RLINK_AXIS_DIR_UP
    DOWN = MSP_RLINK_AXIS_DIR_DOWN

# --- Funktions-Prototypen (Nur die benötigten/funktionierenden) ---
try:
    # Setup / Teardown
    lib.msp_rlink_DevicesConstruct.argtypes = []
    lib.msp_rlink_DevicesConstruct.restype = c_void_p
    lib.msp_rlink_GetNumberOfDevices.argtypes = [c_void_p, ctypes.POINTER(c_size_t)]
    lib.msp_rlink_GetNumberOfDevices.restype = c_int
    lib.msp_rlink_GetDevice.argtypes = [c_void_p, c_size_t, ctypes.POINTER(c_void_p)]
    lib.msp_rlink_GetDevice.restype = c_int
    lib.msp_rlink_Construct.argtypes = [c_void_p]
    lib.msp_rlink_Construct.restype = c_void_p
    lib.msp_rlink_Destruct.argtypes = [c_void_p]
    lib.msp_rlink_Destruct.restype = None
    lib.msp_rlink_Open.argtypes = [c_void_p]
    lib.msp_rlink_Open.restype = c_int
    lib.msp_rlink_Close.argtypes = [c_void_p]
    lib.msp_rlink_Close.restype = c_int

    # Steuerung / Status
    lib.msp_rlink_Heartbeat.argtypes = [c_void_p]
    lib.msp_rlink_Heartbeat.restype = c_int
    lib.msp_rlink_SetXy.argtypes = [c_void_p, c_int8, c_int8]
    lib.msp_rlink_SetXy.restype = c_int
    lib.msp_rlink_SetHorn.argtypes = [c_void_p, c_bool]
    lib.msp_rlink_SetHorn.restype = c_int
    lib.msp_rlink_SetLight.argtypes = [c_void_p, c_int, c_bool] # ID als c_int
    lib.msp_rlink_SetLight.restype = c_int
    lib.msp_rlink_SetAxis.argtypes = [c_void_p, c_int, c_int] # IDs/Dirs als c_int
    lib.msp_rlink_SetAxis.restype = c_int
    lib.msp_rlink_GetSpeed.argtypes = [
        c_void_p, ctypes.POINTER(c_uint8), ctypes.POINTER(c_float), ctypes.POINTER(c_uint8)
    ]
    lib.msp_rlink_GetSpeed.restype = c_int

    # Logging (optional, falls man es doch mal braucht, aber NICHT vor Open aufrufen!)
    # lib.msp_rlink_SetLogFile.argtypes = [c_void_p, c_char_p]
    # lib.msp_rlink_SetLogFile.restype = c_bool
    # lib.msp_rlink_Logging.argtypes = [c_void_p, c_bool]
    # lib.msp_rlink_Logging.restype = None

except AttributeError as e:
    print(f"Fehler beim Definieren der Funktionsprototypen: {e}", file=sys.stderr)
    print("Stelle sicher, dass die Bibliothek geladen wurde und die Funktionen exportiert sind.", file=sys.stderr)
    sys.exit(1)


# --- Einfache Wrapper-Klasse ---
class MiniRlink:
    """
    Minimaler Wrapper basierend auf den funktionierenden Teilen,
    angepasst für Tastatursteuerung (Fahren, Licht, Hupe, Achse, Speed).
    NUTZT DEN RAW-USB-FALLBACK der Bibliothek.
    Setzt voraus, dass die *originale, fehlerhafte* udev-Regel aktiv ist!
    """
    def __init__(self, device_index=0):
        self.handle = None
        self._devinfo_c_void_p = None # Attribut initialisieren
        self._opened = False
        self._lib = lib # Referenz halten

        devices_handle = None # Sicherstellen, dass Variable existiert
        devinfo_holder = None # Sicherstellen, dass Variable existiert

        try:
            devices_handle = self._lib.msp_rlink_DevicesConstruct()
            if not devices_handle:
                raise RLinkError("msp_rlink_DevicesConstruct fehlgeschlagen (NULL erhalten)")

            nofDevices = c_size_t(0)
            status = self._lib.msp_rlink_GetNumberOfDevices(devices_handle, ctypes.byref(nofDevices))
            if status != MSP_OK:
                raise RLinkError(f"msp_rlink_GetNumberOfDevices fehlgeschlagen", status_code=status)
            if nofDevices.value == 0:
                raise RLinkError("Keine RLink-Geräte gefunden bei Enumeration.")
            if device_index >= nofDevices.value:
                 raise RLinkError(f"Geräteindex {device_index} ungültig (nur {nofDevices.value} Geräte gefunden).")

            # Definiere den Holder HIER, *bevor* er mit byref verwendet wird
            devinfo_holder = c_void_p()

            status = self._lib.msp_rlink_GetDevice(devices_handle, device_index, ctypes.byref(devinfo_holder))

            # Prüfe Status UND ob der zurückgegebene Pointer gültig ist (nicht NULL)
            if status != MSP_OK or not devinfo_holder.value:
                 returned_ptr_value = devinfo_holder.value if devinfo_holder is not None else 'None (holder not assigned)'
                 raise RLinkError(f"msp_rlink_GetDevice für Index {device_index} fehlgeschlagen. Erhaltener Pointer-Wert: {returned_ptr_value}", status_code=status)

            # Nur wenn GetDevice erfolgreich war, weise das Ergebnis dem Attribut zu
            self._devinfo_c_void_p = devinfo_holder
            print(f"Geräteinformation für Index {device_index} erhalten (Pointer Objekt: {self._devinfo_c_void_p}, Wert: {self._devinfo_c_void_p.value}).")

            print("Konstruiere RLink Objekt...")
            # Übergebe das ctypes c_void_p Objekt direkt
            if self._devinfo_c_void_p is None:
                 raise RLinkError("Interner Fehler: _devinfo_c_void_p ist None vor Construct")

            self.handle = self._lib.msp_rlink_Construct(self._devinfo_c_void_p)
            if not self.handle:
                 devinfo_val_str = self._devinfo_c_void_p.value if self._devinfo_c_void_p else "None"
                 raise RLinkError(f"msp_rlink_Construct fehlgeschlagen (NULL erhalten) bei Übergabe von devinfo={devinfo_val_str}")
            print(f"RLink Handle erhalten: {self.handle}")

        finally:
            # Es scheint sicherer, DevicesDestruct hier wegzulassen, da devinfo (und damit der Pointer im Handle)
            # möglicherweise länger benötigt wird. Kläre dies ggf. mit dem Hersteller.
            if devices_handle:
                 # self._lib.msp_rlink_DevicesDestruct(devices_handle)
                 pass

    def open(self):
        """Öffnet die Verbindung zum Gerät."""
        if not self.handle: raise RLinkError("Handle ist ungültig.")
        if self._opened: return # Bereits offen

        print("Öffne RLink Verbindung...")
        status = self._lib.msp_rlink_Open(self.handle)
        if status != MSP_OK:
            raise RLinkError(f"msp_rlink_Open fehlgeschlagen", status_code=status)
        self._opened = True
        print("RLink Verbindung geöffnet.")

    def close(self):
        """Schließt die Verbindung zum Gerät."""
        if self.handle and self._opened:
            print("Schließe RLink Verbindung...")
            status = self._lib.msp_rlink_Close(self.handle)
            self._opened = False # Auch wenn Close fehlschlägt
            if status != MSP_OK:
                 print(f"Warnung: msp_rlink_Close fehlgeschlagen, Status: {status}", file=sys.stderr)
            else:
                 print("RLink Verbindung geschlossen.")

    def heartbeat(self):
        """Sendet einen Heartbeat, um die Verbindung aktiv zu halten."""
        if not self.handle or not self._opened:
            # print("Warnung: Heartbeat übersprungen, RLink nicht offen.", file=sys.stderr)
            return # Ignorieren wenn nicht offen
        status = self._lib.msp_rlink_Heartbeat(self.handle)
        if status != MSP_OK:
            print(f"Warnung: msp_rlink_Heartbeat fehlgeschlagen, Status: {status}", file=sys.stderr)
            # Hier könnte man überlegen, einen Fehler auszulösen oder quit_event zu setzen
            # raise RLinkError("Heartbeat fehlgeschlagen", status_code=status)

    def set_xy(self, x: int, y: int):
        """Setzt die X/Y-Fahrwerte."""
        if not self.handle or not self._opened: return
        x_c = c_int8(max(-127, min(127, x)))
        y_c = c_int8(max(-127, min(127, y)))
        status = self._lib.msp_rlink_SetXy(self.handle, x_c, y_c)
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetXy({x}, {y}) fehlgeschlagen, Status: {status}", file=sys.stderr)

    def set_horn(self, enable: bool):
        """Schaltet die Hupe ein oder aus."""
        if not self.handle or not self._opened: return
        status = self._lib.msp_rlink_SetHorn(self.handle, c_bool(enable))
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetHorn({enable}) fehlgeschlagen, Status: {status}", file=sys.stderr)

    def set_light(self, light: RLinkLight, enable: bool):
        """Schaltet ein bestimmtes Licht ein oder aus."""
        if not self.handle or not self._opened: return
        light_c = c_int(light.value) # Nutze den Int-Wert des Enums
        status = self._lib.msp_rlink_SetLight(self.handle, light_c, c_bool(enable))
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetLight(ID={light.value}, Enable={enable}) fehlgeschlagen, Status: {status}", file=sys.stderr)

    def set_axis(self, axis_id: RLinkAxisId, direction: RLinkAxisDir):
        """Setzt die Bewegungsrichtung für eine bestimmte Achse."""
        if not self.handle or not self._opened: return
        axis_id_c = c_int(axis_id.value)
        direction_c = c_int(direction.value)
        status = self._lib.msp_rlink_SetAxis(self.handle, axis_id_c, direction_c)
        if status != MSP_OK:
             print(f"Warnung: msp_rlink_SetAxis(ID={axis_id.value}, Dir={direction.value}) fehlgeschlagen, Status: {status}", file=sys.stderr)

    def get_speed(self) -> tuple[int, float, int]:
        """Ruft die aktuellen Geschwindigkeitswerte vom RLink-Gerät ab."""
        if not self.handle or not self._opened:
            raise RLinkError("RLink ist nicht geöffnet oder Handle ungültig")

        speed_val = c_uint8()
        true_speed_val = c_float()
        limit_applied_val = c_uint8()

        status = self._lib.msp_rlink_GetSpeed(
            self.handle,
            ctypes.byref(speed_val),
            ctypes.byref(true_speed_val),
            ctypes.byref(limit_applied_val)
        )

        if status != MSP_OK:
            raise RLinkError(f"msp_rlink_GetSpeed fehlgeschlagen", status_code=status)

        return speed_val.value, true_speed_val.value, limit_applied_val.value

    def __del__(self):
        """Destruktor: Versucht zu schließen und zu zerstören."""
        # print("DEBUG: MiniRlink __del__ aufgerufen") # Zum Debuggen
        self.close() # Versuch zu schließen
        if self.handle:
            try:
                # ACHTUNG: Destruct könnte fehlschlagen, wenn devinfo noch von DevicesConstruct gehalten wird.
                # Es ist sicherer, Destruct explizit aufzurufen, wenn man fertig ist.
                # self._lib.msp_rlink_Destruct(self.handle)
                # print("RLink Handle zerstört.")
                pass # Expliziten Aufruf von destruct() bevorzugen
            except Exception as e:
                print(f"Fehler in __del__ beim Destruct: {e}", file=sys.stderr)
            self.handle = None

    def destruct(self):
        """Manuelle Methode zum Schließen und Zerstören des Handles."""
        self.close()
        if self.handle:
             print("Zerstöre RLink Handle...")
             self._lib.msp_rlink_Destruct(self.handle)
             self.handle = None
             print("RLink Handle zerstört.")

    def __enter__(self):
        """Context Manager: Öffnet die Verbindung."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context Manager: Schließt die Verbindung."""
        self.close()
        # Hier nicht automatisch destruct aufrufen, da das Objekt noch existieren könnte
# --- Ende Klasse MiniRlink ---