#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import os # Für Berechtigungsprüfung

# Importiere die benötigten Klassen und Konstanten aus deinem Wrapper
try:
    from rlink_wrapper import (
        MspRlink, RLinkError, RLinkButton, RLinkLight,
        RLinkAxisId, RLinkAxisDir, RLinkErrorType, RLinkDevStatus,
        MSP_RLINK_LIGHT_NOF # Sicherstellen, dass diese Konstante importiert wird
        # Füge ggf. weitere benötigte Enums/Konstanten hinzu
    )
except ImportError:
    print("Fehler: Konnte 'rlink_wrapper.py' nicht finden.", file=sys.stderr)
    print("Stelle sicher, dass die Datei im selben Verzeichnis liegt oder im PYTHONPATH.", file=sys.stderr)
    sys.exit(1)

# Versuche, evdev zu importieren
try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    print("Fehler: Die Bibliothek 'evdev' wurde nicht gefunden.", file=sys.stderr)
    print("Bitte installiere sie mit: pip3 install evdev", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
LOOP_WHEELCHAIR_SLEEP = 0.04  # Sekunden Pause im Wheelchair-Thread (ca. 25 Hz)
LOOP_MAIN_POLL_SLEEP = 0.10   # Sekunden Pause im Main-Polling-Thread (ca. 10 Hz)
HEARTBEAT_INTERVAL = 0.5      # Sekunden zwischen Heartbeats
MOVEMENT_SPEED = 100     # Max. Wert für X/Y Achse (Bereich -127 bis 127)

# --- Key Mappings für evdev ---
# Füge bei Bedarf weitere Tasten hinzu
KEY_MAP = {
    ecodes.KEY_W: 'w',
    ecodes.KEY_A: 'a',
    ecodes.KEY_S: 's',
    ecodes.KEY_D: 'd',
    ecodes.KEY_H: 'h',
    ecodes.KEY_L: 'l',
    ecodes.KEY_Q: 'q',
    ecodes.KEY_ESC: 'esc',
}

# --- Globale Zustandsvariablen / Events ---
pressed_keys = set()          # Hält die aktuell gedrückten Tasten (aus KEY_MAP Werten)
outgoing_data = None          # Wird in main initialisiert (enthält OutgoingData Objekt)
quit_event = threading.Event() # Wird gesetzt, um alle Threads zu beenden
# Locks werden innerhalb der OutgoingData/IncomingData Klassen verwendet

# --- Datenstrukturen für geteilten Zustand (wie zuvor) ---
class IncomingData:
    # ... (Keine Änderungen gegenüber der Konsolen-Version) ...
    def __init__(self):
        self.lock = threading.Lock()
        self.oon = False; self.status = RLinkDevStatus.CONFIGURING; self.warning = 0
        self.mode = RLinkMode.MODE_1; self.profile = RLinkProfile.PROFILE_1
        self.inputProcess = 0; self.interProcess = 0; self.outputProcess = 0
        self.selInput = False; self.selInter = False; self.selOutput = False
        self.horn = False; self.batt_low = False; self.batt_gauge = 0; self.batt_current = 0.0
        self.m1Vel = 0.0; self.m2Vel = 0.0; self.turnVel = 0.0
        self.speed = 0; self.trueSpeed = 0.0; self.speedLimitApplied = 0
        self.lights = [{'active': False, 'lit': False} for _ in range(MSP_RLINK_LIGHT_NOF)]

class OutgoingData:
    # ... (Keine Änderungen gegenüber der Konsolen-Version) ...
     def __init__(self):
        self.lock = threading.Lock()
        self.x = 0; self.y = 0; self.btn = False
        self.lights = [False] * MSP_RLINK_LIGHT_NOF
        self.horn = False; self.axis0 = RLinkAxisDir.NONE; self.error = 0

# --- Hilfsfunktionen ---
def find_keyboard_device():
    """Sucht automatisch nach einem Tastaturgerät."""
    devices = [InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        capabilities = device.capabilities(verbose=False)
        if ecodes.EV_KEY in capabilities:
            # Prüfe auf Buchstaben-Tasten, um sicherzugehen, dass es eine Tastatur ist
            has_keys = any(code in KEY_MAP for code in capabilities[ecodes.EV_KEY])
            if has_keys:
                print(f"Tastatur gefunden: {device.path} ({device.name})")
                return device.path
    return None

# --- Thread-Funktionen ---

def thread_keyboard_logic(outgoing_data_ref: OutgoingData):
    """Liest Tastaturereignisse mit evdev und aktualisiert Zustände."""
    global pressed_keys, quit_event # Zugriff auf globale Variablen

    print("Keyboard thread started.")
    device_path = find_keyboard_device()

    if not device_path:
        print("Fehler: Keine Tastatur gefunden. Stelle sicher, dass eine angeschlossen ist.", file=sys.stderr)
        quit_event.set() # Signal zum Beenden an andere Threads
        return

    try:
        device = InputDevice(device_path)
        print(f"Verwende Tastatur: {device.path}")
    except OSError as e:
        print(f"Fehler beim Öffnen von {device_path}: {e}", file=sys.stderr)
        if e.errno == 13: # Permission denied
             print("-> Keine Berechtigung. Führe das Skript mit 'sudo' aus", file=sys.stderr)
             print("   oder füge deinen Benutzer zur Gruppe 'input' hinzu:", file=sys.stderr)
             print(f"   sudo usermod -a -G input {os.getlogin()}", file=sys.stderr)
             print("   (Danach neu einloggen!)", file=sys.stderr)
        quit_event.set()
        return

    # Exklusiven Zugriff auf das Gerät anfordern (optional, aber empfohlen)
    try:
        device.grab()
        print("Tastatur exklusiv erfasst (grabbed). Andere Anwendungen erhalten keine Eingaben mehr.")

        # Ereignis-Schleife
        for event in device.read_loop():
            if quit_event.is_set(): # Prüfe, ob das Beenden signalisiert wurde
                break

            if event.type == ecodes.EV_KEY:
                key_event = categorize(event)
                key_code = key_event.scancode
                key_name = KEY_MAP.get(key_code) # Übersetze Code in unseren Namen (w, a, s, d...)
                key_state = key_event.keystate # 0=UP, 1=DOWN, 2=HOLD

                # print(f"DEBUG Key: {key_event.keycode}, State: {key_state}, Mapped: {key_name}") # Zum Debuggen

                if key_name:
                    if key_state == key_event.key_down or key_state == key_event.key_hold:
                        # Taste gedrückt oder gehalten
                        pressed_keys.add(key_name)

                        # Aktionen, die nur bei erstem Drücken ausgelöst werden sollen
                        if key_state == key_event.key_down:
                            if key_name == 'h':
                                with outgoing_data_ref.lock:
                                    outgoing_data_ref.horn = not outgoing_data_ref.horn
                                print(f"Hupe {'AN' if outgoing_data_ref.horn else 'AUS'}")
                            elif key_name == 'l':
                                 with outgoing_data_ref.lock:
                                     # Beispiel: Abblendlicht schalten
                                     light_index = RLinkLight.DIP.value
                                     outgoing_data_ref.lights[light_index] = not outgoing_data_ref.lights[light_index]
                                 print(f"Licht (DIP) {'AN' if outgoing_data_ref.lights[light_index] else 'AUS'}")
                            elif key_name == 'q' or key_name == 'esc':
                                 print(f"Beenden durch '{key_name}' erkannt.")
                                 quit_event.set()
                                 break # Schleife verlassen

                    elif key_state == key_event.key_up:
                        # Taste losgelassen
                        if key_name in pressed_keys:
                            pressed_keys.remove(key_name)

    except IOError as e:
         print(f"Fehler beim Lesen vom Keyboard-Device: {e}", file=sys.stderr)
         quit_event.set()
    except Exception as e:
        print(f"Unerwarteter Fehler im Keyboard-Thread: {e}", file=sys.stderr)
        quit_event.set()
    finally:
        try:
            device.ungrab() # Wichtig: Exklusiven Zugriff freigeben
            print("Tastatur freigegeben (ungrabbed).")
            device.close()
        except Exception as e:
            print(f"Fehler beim Freigeben/Schließen des Geräts: {e}", file=sys.stderr)

    print("Keyboard thread finished.")


def thread_wheelchair_logic(rlink: MspRlink, outgoing_data_ref: OutgoingData):
    """Sendet Kommandos an RLink basierend auf pressed_keys und outgoing_data."""
    global pressed_keys # Zugriff auf globale Variable
    print("Wheelchair thread started.")
    heartbeat_enabled = True # Heartbeat standardmäßig an
    last_heartbeat_time = time.time()

    previous_outgoing = OutgoingData()
    previous_outgoing.x = -999 # Sicherstellen, dass beim ersten Mal gesendet wird

    while not quit_event.is_set():
        current_time = time.time()

        # Heartbeat senden
        if heartbeat_enabled and current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
            try:
                rlink.heartbeat()
                last_heartbeat_time = current_time
            except RLinkError as e:
                print(f"\nWheelchair Thread: Error sending heartbeat: {e}", file=sys.stderr)
                quit_event.set(); break

        # --- Bewegung basierend auf pressed_keys berechnen ---
        target_x = 0
        target_y = 0
        # Kopiere Set für sicheren Zugriff, obwohl GIL helfen sollte
        current_pressed = set(pressed_keys)
        if 'w' in current_pressed: target_y += MOVEMENT_SPEED
        if 's' in current_pressed: target_y -= MOVEMENT_SPEED
        if 'a' in current_pressed: target_x -= MOVEMENT_SPEED
        if 'd' in current_pressed: target_x += MOVEMENT_SPEED

        target_x = max(-127, min(127, target_x))
        target_y = max(-127, min(127, target_y))

        # --- Aktuellen Soll-Zustand aus outgoing_data holen (für Toggles) ---
        current_outgoing = OutgoingData() # Temporäres Objekt
        with outgoing_data_ref.lock:
            # Setze berechnete Bewegung
            current_outgoing.x = target_x
            current_outgoing.y = target_y
            # Übernehme Toggle-Zustände
            current_outgoing.btn = outgoing_data_ref.btn # Falls Button verwendet wird
            current_outgoing.horn = outgoing_data_ref.horn
            current_outgoing.axis0 = outgoing_data_ref.axis0 # Falls Axis verwendet wird
            current_outgoing.error = outgoing_data_ref.error # Falls Error verwendet wird
            current_outgoing.lights = list(outgoing_data_ref.lights) # Kopie

        # --- Vergleiche mit vorherigem Zustand und sende bei Bedarf ---
        try:
            # Bewegung
            if previous_outgoing.x != current_outgoing.x or previous_outgoing.y != current_outgoing.y:
                rlink.set_xy(current_outgoing.x, current_outgoing.y)

            # Hupe
            if previous_outgoing.horn != current_outgoing.horn:
                rlink.set_horn(current_outgoing.horn)

            # Lichter
            for i in range(MSP_RLINK_LIGHT_NOF):
                 if previous_outgoing.lights[i] != current_outgoing.lights[i]:
                     rlink.set_light(RLinkLight(i), current_outgoing.lights[i])

            # Fehler (nur senden wenn != 0, dann im Original zurücksetzen)
            if current_outgoing.error != 0 and previous_outgoing.error != current_outgoing.error:
                 rlink.set_error(current_outgoing.error)
                 with outgoing_data_ref.lock: # Fehler zurücksetzen im Original
                     outgoing_data_ref.error = 0
                 current_outgoing.error = 0 # Auch im temporären Objekt für nächsten Vergleich

            # Weitere (Button, Axis...) hier hinzufügen, falls benötigt

            # Update previous state
            previous_outgoing = current_outgoing

        except RLinkError as e:
             print(f"\nWheelchair Thread: Error sending command: {e}", file=sys.stderr)
             quit_event.set(); break
        except Exception as e:
            print(f"\nWheelchair Thread: Unexpected error: {e}", file=sys.stderr)
            quit_event.set(); break

        time.sleep(LOOP_WHEELCHAIR_SLEEP)

    print("Wheelchair thread finished.")


def thread_main_polling_logic(rlink: MspRlink, incoming_data: IncomingData):
    """Pollt RLink auf Statusänderungen und Daten."""
    print("Main polling thread started.")
    while not quit_event.is_set():
        try:
            # 1. Statusflags abrufen
            flags = rlink.get_status_flags()

            # 2. Fehler / Disconnect prüfen
            if flags & MSP_RLINK_EV_ERROR:
                print("\nMain Thread: RLink error flag detected!", file=sys.stderr)
                latest_err = rlink.get_latest_error()
                print(f" -> Latest RLink Error: {latest_err.name}", file=sys.stderr)
                quit_event.set()
                break
            if flags & MSP_RLINK_EV_DISCONNECTED:
                print("\nMain Thread: RLink disconnected flag detected!", file=sys.stderr)
                quit_event.set()
                break

            # 3. Daten abrufen, wenn Flag gesetzt
            if flags & MSP_RLINK_EV_DATA_READY:
                # print("DEBUG: Data Ready flag set, fetching data...", flush=True)
                with incoming_data.lock:
                    try:
                        # --- Hier sind die expandierten Zeilen ---
                        (incoming_data.oon,
                         incoming_data.status,
                         incoming_data.warning) = rlink.get_device_status()

                        incoming_data.mode = rlink.get_mode()
                        incoming_data.profile = rlink.get_profile()

                        (incoming_data.inputProcess,
                         incoming_data.interProcess,
                         incoming_data.outputProcess,
                         incoming_data.selInput,
                         incoming_data.selInter,
                         incoming_data.selOutput) = rlink.get_hms() # <- Vollständig

                        incoming_data.horn = rlink.get_horn()

                        (incoming_data.batt_low,
                         incoming_data.batt_gauge,
                         incoming_data.batt_current) = rlink.get_battery_info() # <- Vollständig

                        (incoming_data.m1Vel,
                         incoming_data.m2Vel,
                         incoming_data.turnVel) = rlink.get_velocity() # <- Vollständig

                        (incoming_data.speed,
                         incoming_data.trueSpeed,
                         incoming_data.speedLimitApplied) = rlink.get_speed() # <- Vollständig
                        # --- Ende der expandierten Zeilen ---

                        # Licht-Status abrufen (war bereits vollständig)
                        for i in range(MSP_RLINK_LIGHT_NOF):
                             active, lit = rlink.get_light(RLinkLight(i))
                             incoming_data.lights[i]['active'] = active
                             incoming_data.lights[i]['lit'] = lit

                    except RLinkError as e:
                         print(f"\nMain Thread: Error retrieving data: {e}", file=sys.stderr)
                         # Fehler beim Datenabruf könnte kritisch sein
                         quit_event.set()
                         break
            # else:
            #     print("DEBUG: No data ready flag.", flush=True)

        except RLinkError as e:
            print(f"\nMain Thread: Error checking status: {e}", file=sys.stderr)
            quit_event.set()
            break
        except Exception as e:
            print(f"\nMain Thread: Unexpected error: {e}", file=sys.stderr)
            quit_event.set()
            break

        # Pause vor dem nächsten Poll
        time.sleep(LOOP_MAIN_POLL_SLEEP)

    print("Main polling thread finished.")


# --- Hauptprogrammablauf ---
def run_application():
    global outgoing_data # Referenz auf globale Variable setzen

    rlink = None
    threads = []

    try:
        print("Searching for RLink devices...")
        devices = MspRlink.enumerate_devices()
        if not devices: print("No RLink devices found. Exiting."); return

        print(f"{len(devices)} device(s) found:")
        device_options = [f"{dev.serial}: {dev.description}" for i, dev in enumerate(devices)]
        for i, desc in enumerate(device_options): print(f"  [{i}] {desc}")

        selected_index = -1
        while selected_index < 0 or selected_index >= len(devices):
            try:
                choice = input(f"Select device index [0-{len(devices)-1}] or 'quit': ")
                if choice.lower() == 'quit': print("Exiting."); return
                selected_index = int(choice)
                if selected_index < 0 or selected_index >= len(devices): print("Invalid index.")
            except ValueError: print("Invalid input, please enter a number.")

        selected_device_info = devices[selected_index]._dev_info_ptr
        print(f"\nConnecting to device {selected_index} ({device_options[selected_index]})...")

        rlink = MspRlink(selected_device_info)

        log_filename = "rlink_evdev_py.log"
        if rlink.set_log_file(log_filename):
            rlink.set_logging(True); print(f"Logging enabled to '{log_filename}'")
        else: print(f"Warning: Failed to set log file '{log_filename}'")

        rlink.open()
        print("Device opened successfully.")
        print("\nStarting direct keyboard control (using evdev)...")
        print(" - WASD: Bewegung")
        print(" - H:    Hupe an/aus")
        print(" - L:    Licht an/aus (Abblendlicht)")
        print(" - ESC/Q: Beenden")
        print("\nWaiting for keyboard input...")

        # Geteilte Datenobjekte erstellen
        incoming = IncomingData()
        outgoing_data = OutgoingData() # Globale Variable initialisieren

        # Threads erstellen
        main_thread = threading.Thread(target=thread_main_polling_logic, args=(rlink, incoming), daemon=True)
        wheelchair_thread = threading.Thread(target=thread_wheelchair_logic, args=(rlink, outgoing_data), daemon=True)
        # Keyboard thread NICHT als daemon, damit er sauber beenden kann
        keyboard_thread = threading.Thread(target=thread_keyboard_logic, args=(outgoing_data,))

        threads = [main_thread, wheelchair_thread, keyboard_thread]

        print("Starting threads...")
        for t in threads: t.start()

        # Auf Beendigung des Keyboard-Threads warten (oder bis quit_event gesetzt wird)
        while keyboard_thread.is_alive():
            if quit_event.wait(timeout=0.5):
                 print("Quit event detected by main.")
                 break

        print("Waiting for threads to finish...")
        quit_event.set()
        main_thread.join(timeout=2.0)
        wheelchair_thread.join(timeout=2.0)
        keyboard_thread.join(timeout=2.0) # Warte auch auf den Keyboard-Thread

        print("All threads finished.")

    # ... (Restliches Exception Handling und Cleanup wie in der Konsolen-Version) ...
    except RLinkError as e: print(f"\nAn RLink error occurred: {e}", file=sys.stderr)
    except FileNotFoundError as e: print(f"\nError: {e}", file=sys.stderr)
    except ImportError as e: print(f"\nImport Error: {e}", file=sys.stderr)
    except KeyboardInterrupt: print("\nCtrl+C detected, shutting down.", file=sys.stderr); quit_event.set()
    except Exception as e:
        print(f"\nAn unexpected error occurred in main: {e}", file=sys.stderr)
        import traceback; traceback.print_exc(); quit_event.set()
    finally:
        print("Cleaning up...")
        # quit_event sicherheitshalber nochmal setzen
        quit_event.set()
        for t in threads:
             if t.is_alive(): print(f"Warning: Thread {t.name} still alive.", file=sys.stderr); t.join(0.5)
        if rlink:
            try: print("Closing RLink connection..."); rlink.close(); print("RLink connection closed.")
            except Exception as e: print(f"Error closing RLink connection: {e}", file=sys.stderr)
        print("Cleanup finished. Exiting.")

if __name__ == "__main__":
    run_application()