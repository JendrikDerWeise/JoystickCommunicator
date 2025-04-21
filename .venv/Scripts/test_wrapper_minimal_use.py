# test_wrapper_minimal_use.py
import sys
import ctypes
import time # Nur für eine kleine Pause

try:
    # Importiere die Klasse und Konstanten aus dem vollständigen Wrapper
    from rlink_wrapper import (MspRlink, RLinkError, MSP_OK, MSP_STATUS_NAMES,
                               lib) # Importiere auch 'lib' für direkten Destruct-Aufruf

    print("Wrapper importiert. Suche Geräte...")
    # Stelle sicher, dass die originale, fehlerhafte udev-Regel aktiv ist!

    rlink_instance = None # Definiere außerhalb von try für finally
    devices_list = None # Halte die Liste für devinfo

    try:
        # Schritt 1: Enumerieren mit der statischen Methode des Wrappers
        devices_list = MspRlink.enumerate_devices()
        if not devices_list:
            print("Enumeration fehlgeschlagen: Keine Geräte gefunden.")
            sys.exit(1)
        print(f"Enumeration erfolgreich: {len(devices_list)} Gerät(e) gefunden.")
        # Hole den Pointer direkt aus der zurückgegebenen Liste
        # Wichtig: Halte 'devices_list', damit das Objekt mit dem Pointer nicht verschwindet
        dev_info_ptr = devices_list[0]._dev_info_ptr

        # Schritt 2: Konstruktor der Wrapper-Klasse aufrufen
        print("Konstruiere RLink Objekt via Wrapper-Klasse...")
        # Erstelle die Instanz - dies ruft intern msp_rlink_Construct auf
        rlink_instance = MspRlink(dev_info_ptr)
        print(f"Wrapper-Instanz erstellt. Handle: {rlink_instance.handle}") # Prüfe den Handle

        # Schritt 3: Open-Methode der Wrapper-Klasse aufrufen
        print("Versuche rlink_instance.open()...")
        rlink_instance.open() # Dies ruft intern lib.msp_rlink_Open(self.handle) auf

        # Wenn open erfolgreich war:
        print("Öffnen via Wrapper erfolgreich!")
        print("Warte 1 Sekunde...")
        time.sleep(1)
        print("Schließe via Wrapper...")
        rlink_instance.close() # Ruft msp_rlink_Close auf
        print("Schließen erfolgreich.")

    except RLinkError as e:
        print(f"RLinkError aufgetreten: {e}", file=sys.stderr)
        # Gib den Statuscode aus, falls verfügbar in der Exception
        if hasattr(e, 'status_code') and e.status_code is not None:
             status_name = MSP_STATUS_NAMES.get(e.status_code, "UNKNOWN")
             print(f" -> Status: {status_name}({e.status_code})", file=sys.stderr)

    except Exception as e:
        print(f"Anderer Fehler: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

    finally:
        # Manuelles Aufräumen (nur Destruct, Close wurde oben versucht)
        # Normalerweise würde __del__ das machen, aber hier explizit
        if rlink_instance and hasattr(rlink_instance, 'handle') and rlink_instance.handle:
            print("Rufe msp_rlink_Destruct manuell auf...")
            try:
                 lib.msp_rlink_Destruct(rlink_instance.handle)
                 print("Destruct erfolgreich.")
                 # Verhindere, dass __del__ es nochmal versucht
                 rlink_instance.handle = None
            except Exception as e:
                 print(f"Fehler bei manuellem Destruct: {e}", file=sys.stderr)
        else:
            print("Kein gültiges Handle zum Aufräumen gefunden.")

        # WICHTIG: Referenz auf devinfo löschen (DevicesDestruct fehlt hier!)
        # Normalerweise würde man auch die Devices-Liste zerstören
        print("Skript-Ende.")


except ImportError as e:
    print(f"Import Fehler: {e}", file=sys.stderr)
except Exception as e:
    print(f"Genereller Fehler beim Setup: {e}", file=sys.stderr)