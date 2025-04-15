#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import select  # Für nicht-blockierende Eingabe unter Linux (optional)

# Importiere die benötigten Klassen und Konstanten aus deinem Wrapper
try:
    from rlink_wrapper import (
        MspRlink, RLinkError, RLinkButton, RLinkLight, RLinkMode, RLinkProfile,
        RLinkAxisId, RLinkAxisDir, RLinkErrorType, RLinkDevStatus,
        MSP_RLINK_LIGHT_NOF, MSP_RLINK_EV_DISCONNECTED, MSP_RLINK_EV_ERROR,
        MSP_RLINK_EV_DATA_READY, MSP_OK
        # Füge ggf. weitere benötigte Enums/Konstanten hinzu
    )
except ImportError:
    print("Fehler: Konnte 'rlink_wrapper.py' nicht finden.", file=sys.stderr)
    print("Stelle sicher, dass die Datei im selben Verzeichnis liegt oder im PYTHONPATH.", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
LOOP_WHEELCHAIR_SLEEP = 0.04  # Sekunden Pause im Wheelchair-Thread (ca. 25 Hz)
LOOP_MAIN_POLL_SLEEP = 0.10   # Sekunden Pause im Main-Polling-Thread (ca. 10 Hz)
HEARTBEAT_INTERVAL = 0.5      # Sekunden zwischen Heartbeats

# --- Datenstrukturen für geteilten Zustand ---

class IncomingData:
    """Entspricht incoming_t in C, geschützt durch Lock."""
    def __init__(self):
        self.lock = threading.Lock()
        # Status
        self.oon = False
        self.status = RLinkDevStatus.CONFIGURING
        self.warning = 0
        # HMS
        self.mode = RLinkMode.MODE_1
        self.profile = RLinkProfile.PROFILE_1
        self.inputProcess = 0
        self.interProcess = 0
        self.outputProcess = 0
        self.selInput = False
        self.selInter = False
        self.selOutput = False
        # Horn
        self.horn = False
        # Battery
        self.batt_low = False
        self.batt_gauge = 0
        self.batt_current = 0.0
        # Velocity
        self.m1Vel = 0.0
        self.m2Vel = 0.0
        self.turnVel = 0.0
        # Speed
        self.speed = 0
        self.trueSpeed = 0.0
        self.speedLimitApplied = 0
        # Lights (Status von der Elektronik)
        self.lights = [{'active': False, 'lit': False} for _ in range(MSP_RLINK_LIGHT_NOF)]

class OutgoingData:
    """Entspricht outgoing_t in C, geschützt durch Lock."""
    def __init__(self):
        self.lock = threading.Lock()
        self.x = 0
        self.y = 0
        self.btn = False # Beispiel: Gelber Tip Button
        self.lights = [False] * MSP_RLINK_LIGHT_NOF # Soll-Zustand der Lichter
        self.horn = False
        self.axis0 = RLinkAxisDir.NONE
        self.error = 0 # Zu sendender Fehlercode (0 = kein Fehler)

# --- Globale Events zur Thread-Steuerung ---
quit_event = threading.Event() # Wird gesetzt, um alle Threads zu beenden
toggle_heartbeat_event = threading.Event() # Zum Anstoßen der Heartbeat-Umschaltung

# --- Hilfsfunktionen ---

def print_actions():
    """Zeigt das Menü der möglichen Aktionen an."""
    actions = [
        "up (+Y)", "down (-Y)", "left (-X)", "right (+X)", "neutral (X=0, Y=0)",
        "button press (YT)", "button release (YT)",
        "toggle light brake", "toggle light dip", "toggle light hazard",
        "toggle light left", "toggle light right", "toggle horn",
        "axis 0 up", "axis 0 down", "axis 0 stop",
        "toggle heartbeat", "trigger error (0x01)", "dump state", "quit"
    ]
    print("\nThe following actions to control the wheelchair are supported:")
    for i, action in enumerate(actions):
        print(f"{i:3d}: {action}")
    print("Enter action number: ", end='', flush=True)

def execute_action(action_id: int, outgoing_data: OutgoingData):
    """Modifiziert outgoing_data basierend auf der Aktion."""
    with outgoing_data.lock:
        if action_id == 0:   # UP
            outgoing_data.y = min(100, outgoing_data.y + 20)
        elif action_id == 1: # DOWN
            outgoing_data.y = max(-100, outgoing_data.y - 20)
        elif action_id == 2: # LEFT
            outgoing_data.x = max(-100, outgoing_data.x - 20)
        elif action_id == 3: # RIGHT
            outgoing_data.x = min(100, outgoing_data.x + 20)
        elif action_id == 4: # NEUTRAL
            outgoing_data.x = 0
            outgoing_data.y = 0
        elif action_id == 5: # BUTTON PRESS (YT)
            outgoing_data.btn = True
        elif action_id == 6: # BUTTON RELEASE (YT)
            outgoing_data.btn = False
        elif action_id == 7: # TOGGLE LIGHT BRAKE
            outgoing_data.lights[RLinkLight.BRAKE] = not outgoing_data.lights[RLinkLight.BRAKE]
        elif action_id == 8: # TOGGLE LIGHT DIP
            outgoing_data.lights[RLinkLight.DIP] = not outgoing_data.lights[RLinkLight.DIP]
        elif action_id == 9: # TOGGLE LIGHT HAZARD
            outgoing_data.lights[RLinkLight.HAZARD] = not outgoing_data.lights[RLinkLight.HAZARD]
        elif action_id == 10: # TOGGLE LIGHT LEFT
            outgoing_data.lights[RLinkLight.LEFT] = not outgoing_data.lights[RLinkLight.LEFT]
        elif action_id == 11: # TOGGLE LIGHT RIGHT
            outgoing_data.lights[RLinkLight.RIGHT] = not outgoing_data.lights[RLinkLight.RIGHT]
        elif action_id == 12: # TOGGLE HORN
            outgoing_data.horn = not outgoing_data.horn
        elif action_id == 13: # AXIS 0 UP
            outgoing_data.axis0 = RLinkAxisDir.UP
        elif action_id == 14: # AXIS 0 DOWN
            outgoing_data.axis0 = RLinkAxisDir.DOWN
        elif action_id == 15: # AXIS 0 STOP
            outgoing_data.axis0 = RLinkAxisDir.NONE
        elif action_id == 16: # TOGGLE HEARTBEAT
             toggle_heartbeat_event.set() # Signal an Wheelchair-Thread
        elif action_id == 17: # TRIGGER ERROR
            outgoing_data.error = 1 # Setze einen Fehlercode
        elif action_id == 18: # DUMP STATE (Wird separat behandelt)
            pass
        elif action_id == 19: # QUIT
            quit_event.set()
        else:
            print("Invalid action ID.", flush=True)

def dump_state(incoming_data: IncomingData):
    """Gibt den aktuellen Zustand aus incoming_data aus."""
    with incoming_data.lock:
        print("\n--- Current RLink State ---")
        print("Status:")
        print(f" - OON:               {incoming_data.oon}")
        print(f" - Status:            {incoming_data.status.name} ({incoming_data.status.value})")
        print(f" - Warning:           0x{incoming_data.warning:02x}")

        print("\nBattery:")
        print(f" - Low:               {incoming_data.batt_low}")
        print(f" - Gauge:             {incoming_data.batt_gauge}%")
        print(f" - Current:           {incoming_data.batt_current:.2f} A")

        print("\nHost Modal Selection:")
        print(f" - Mode:              {incoming_data.mode.name} ({incoming_data.mode.value})")
        print(f" - Profile:           {incoming_data.profile.name} ({incoming_data.profile.value})")
        print(f" - Input Process:     0x{incoming_data.inputProcess:04x}")
        print(f" - Inter Process:     0x{incoming_data.interProcess:04x}")
        print(f" - Output Process:    0x{incoming_data.outputProcess:04x}")
        print(f" - Selected Input:    {incoming_data.selInput}")
        print(f" - Selected Inter:    {incoming_data.selInter}")
        print(f" - Selected Output:   {incoming_data.selOutput}")

        print(f"\nHorn Active:        {incoming_data.horn}")

        print("\nVelocity:")
        print(f" - Motor 1 Vel:       {incoming_data.m1Vel:.2f} rad/s")
        print(f" - Motor 2 Vel:       {incoming_data.m2Vel:.2f} rad/s")
        print(f" - Turn Vel:          {incoming_data.turnVel:.2f} rad/s")

        print("\nSpeed:")
        print(f" - Speed Setting:     {incoming_data.speed}")
        print(f" - True Speed:        {incoming_data.trueSpeed * 3.6:.2f} km/h")
        print(f" - Speed Limit Applied: {incoming_data.speedLimitApplied}")

        print("\nLights Status (Active / Lit):")
        for i, name in enumerate(["BRAKE", "DIP", "HAZARD", "LEFT", "RIGHT"]):
             light_state = incoming_data.lights[i]
             print(f" - {name:<10}:       {light_state['active']} / {light_state['lit']}")
        print("---------------------------\n")

# --- Thread-Funktionen ---

def thread_console_logic(outgoing_data: OutgoingData, incoming_data: IncomingData):
    """Liest Benutzereingaben und aktualisiert outgoing_data."""
    print("Console thread started.")
    while not quit_event.is_set():
        print_actions()
        try:
            # Einfache blockierende Eingabe
            line = sys.stdin.readline()
            if not line: # EOF
                 print("\nEOF received, quitting.", flush=True)
                 quit_event.set()
                 break

            line = line.strip()
            if not line:
                continue

            if line == "quit":
                print("Quit command received.", flush=True)
                quit_event.set()
                break

            action_id = int(line)

            if action_id == 18: # Dump State
                dump_state(incoming_data)
            elif 0 <= action_id <= 19:
                 execute_action(action_id, outgoing_data)
                 # Gib den neuen Zustand aus (optional)
                 with outgoing_data.lock:
                     print(f" -> New state: X={outgoing_data.x}, Y={outgoing_data.y}, "
                           f"Horn={outgoing_data.horn}, Light[DIP]={outgoing_data.lights[RLinkLight.DIP]}", flush=True)
            else:
                print("Invalid action number.", flush=True)

        except ValueError:
            print("Invalid input, please enter a number or 'quit'.", flush=True)
        except KeyboardInterrupt:
            print("\nCtrl+C detected, quitting.", flush=True)
            quit_event.set()
            break
        except Exception as e:
             print(f"\nError in console thread: {e}", file=sys.stderr)
             # Bei unerwarteten Fehlern eventuell beenden
             quit_event.set()
             break

    print("Console thread finished.")


def thread_wheelchair_logic(rlink: MspRlink, outgoing_data: OutgoingData):
    """Sendet Kommandos an RLink basierend auf outgoing_data."""
    print("Wheelchair thread started.")
    heartbeat_enabled = True
    last_heartbeat_time = time.time()

    # Speichere den vorherigen Zustand, um nur bei Änderungen zu senden
    previous_outgoing = OutgoingData()
    # Initialisiere previous mit etwas Ungültigem, um beim ersten Mal zu senden
    previous_outgoing.x = -999

    while not quit_event.is_set():
        current_time = time.time()

        # Prüfe, ob Heartbeat umgeschaltet werden soll
        if toggle_heartbeat_event.is_set():
             heartbeat_enabled = not heartbeat_enabled
             print(f"Heartbeat {'enabled' if heartbeat_enabled else 'disabled'}.", flush=True)
             toggle_heartbeat_event.clear() # Event zurücksetzen

        # Sende Heartbeat, falls aktiviert
        if heartbeat_enabled and current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
            try:
                rlink.heartbeat()
                last_heartbeat_time = current_time
            except RLinkError as e:
                print(f"\nWheelchair Thread: Error sending heartbeat: {e}", file=sys.stderr)
                quit_event.set() # Bei Heartbeat-Fehler beenden
                break

        # Hole aktuellen Soll-Zustand (thread-sicher)
        current_outgoing = OutgoingData() # Temporäres Objekt
        with outgoing_data.lock:
            current_outgoing.x = outgoing_data.x
            current_outgoing.y = outgoing_data.y
            current_outgoing.btn = outgoing_data.btn
            current_outgoing.horn = outgoing_data.horn
            current_outgoing.axis0 = outgoing_data.axis0
            current_outgoing.error = outgoing_data.error
            current_outgoing.lights = list(outgoing_data.lights) # Kopie erstellen

        # Vergleiche mit vorherigem Zustand und sende bei Bedarf
        try:
            if previous_outgoing.x != current_outgoing.x or previous_outgoing.y != current_outgoing.y:
                rlink.set_xy(current_outgoing.x, current_outgoing.y)
                # print(f"DEBUG: Sent X={current_outgoing.x}, Y={current_outgoing.y}", flush=True)

            if previous_outgoing.btn != current_outgoing.btn:
                # Annahme: Button ist Yellow Tip
                rlink.set_button(RLinkButton.YELLOW_TIP, current_outgoing.btn)

            if previous_outgoing.horn != current_outgoing.horn:
                rlink.set_horn(current_outgoing.horn)

            for i in range(MSP_RLINK_LIGHT_NOF):
                 if previous_outgoing.lights[i] != current_outgoing.lights[i]:
                     rlink.set_light(RLinkLight(i), current_outgoing.lights[i])

            if previous_outgoing.axis0 != current_outgoing.axis0:
                 # Annahme: Axis 0
                 rlink.set_axis(RLinkAxisId.ID_0, current_outgoing.axis0)

            if previous_outgoing.error != current_outgoing.error:
                 rlink.set_error(current_outgoing.error)
                 if current_outgoing.error != 0: # Fehler zurücksetzen, nachdem er gesendet wurde
                      with outgoing_data.lock:
                           outgoing_data.error = 0


            # Update previous state
            previous_outgoing = current_outgoing

        except RLinkError as e:
             print(f"\nWheelchair Thread: Error sending command: {e}", file=sys.stderr)
             # Entscheide, ob bei Fehlern weitergemacht werden soll oder nicht
             quit_event.set()
             break
        except Exception as e:
            print(f"\nWheelchair Thread: Unexpected error: {e}", file=sys.stderr)
            quit_event.set()
            break

        # Kurze Pause
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
                         incoming_data.selOutput) = rlink.get_hms()

                        incoming_data.horn = rlink.get_horn()

                        (incoming_data.batt_low,
                         incoming_data.batt_gauge,
                         incoming_data.batt_current) = rlink.get_battery_info()

                        (incoming_data.m1Vel,
                         incoming_data.m2Vel,
                         incoming_data.turnVel) = rlink.get_velocity()

                        (incoming_data.speed,
                         incoming_data.trueSpeed,
                         incoming_data.speedLimitApplied) = rlink.get_speed()

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
    rlink = None
    threads = []

    try:
        print("Searching for RLink devices...")
        devices = MspRlink.enumerate_devices()

        if not devices:
            print("No RLink devices found. Exiting.")
            return

        print(f"{len(devices)} device(s) found:")
        device_options = []
        for i, dev in enumerate(devices):
            print(f"  [{i}] {dev.serial}: {dev.description}")
            device_options.append(f"{dev.serial}: {dev.description}")

        # Benutzerauswahl
        selected_index = -1
        while selected_index < 0 or selected_index >= len(devices):
            try:
                choice = input(f"Select device index [0-{len(devices)-1}] or 'quit': ")
                if choice.lower() == 'quit':
                    print("Exiting.")
                    return
                selected_index = int(choice)
                if selected_index < 0 or selected_index >= len(devices):
                    print("Invalid index.")
            except ValueError:
                print("Invalid input, please enter a number.")

        selected_device_info = devices[selected_index]._dev_info_ptr
        print(f"\nConnecting to device {selected_index} ({device_options[selected_index]})...")

        rlink = MspRlink(selected_device_info) # Context Manager nicht ideal für manuelle Thread-Steuerung

        # Logging optional aktivieren
        log_filename = "rlink_console_py.log"
        if rlink.set_log_file(log_filename):
            rlink.set_logging(True)
            print(f"Logging enabled to '{log_filename}'")
        else:
            print(f"Warning: Failed to set log file '{log_filename}'")

        # Gerät öffnen
        rlink.open()
        print("Device opened successfully.")

        # Geteilte Datenobjekte erstellen
        incoming = IncomingData()
        outgoing = OutgoingData()

        # Threads erstellen
        main_thread = threading.Thread(target=thread_main_polling_logic, args=(rlink, incoming), daemon=True)
        wheelchair_thread = threading.Thread(target=thread_wheelchair_logic, args=(rlink, outgoing), daemon=True)
        # Console thread nicht als daemon, damit das Programm nicht beendet, solange er läuft
        console_thread = threading.Thread(target=thread_console_logic, args=(outgoing, incoming))

        threads = [main_thread, wheelchair_thread, console_thread]

        # Threads starten
        print("Starting threads...")
        for t in threads:
            t.start()

        # Auf Beendigung des Konsolen-Threads warten (oder bis quit_event gesetzt wird)
        while console_thread.is_alive():
            if quit_event.wait(timeout=0.5): # Prüfe Event alle 0.5s
                 print("Quit event detected by main.")
                 break

        print("Waiting for threads to finish...")
        # Signalisiere anderen Threads (falls nicht schon durch quit_event geschehen)
        quit_event.set()
        # Warte auf die Beendigung der Daemon-Threads (mit Timeout)
        main_thread.join(timeout=2.0)
        wheelchair_thread.join(timeout=2.0)
        # Stelle sicher, dass der Konsolen-Thread auch beendet ist
        console_thread.join(timeout=2.0)

        print("All threads finished.")

    except RLinkError as e:
        print(f"\nAn RLink error occurred: {e}", file=sys.stderr)
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
    except ImportError as e:
         print(f"\nImport Error: {e}", file=sys.stderr)
    except KeyboardInterrupt:
         print("\nCtrl+C detected in main, shutting down.", file=sys.stderr)
         quit_event.set() # Signalisiere Threads
    except Exception as e:
        print(f"\nAn unexpected error occurred in main: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        quit_event.set() # Signalisiere Threads
    finally:
        print("Cleaning up...")
        # Stelle sicher, dass Threads beendet sind (redundant, falls join erfolgreich war)
        for t in threads:
             if t.is_alive():
                  print(f"Warning: Thread {t.name} still alive.", file=sys.stderr)
        # Schließe die RLink Verbindung, falls sie geöffnet wurde
        if rlink:
            try:
                # Prüfen ob geöffnet, bevor geschlossen wird
                # Annahme: Wrapper hat kein _opened Attribut, daher try/except
                 print("Closing RLink connection...")
                 rlink.close()
                 print("RLink connection closed.")
            except RLinkError as e:
                 print(f"Error closing RLink connection: {e}", file=sys.stderr)
            except Exception as e:
                 print(f"Unexpected error during RLink close: {e}", file=sys.stderr)

        print("Cleanup finished. Exiting.")


if __name__ == "__main__":
    run_application()