#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import os

# Importiere den VOLLSTÄNDIGEN Wrapper und die benötigten Enums/Klassen
try:
    # Stelle sicher, dass du RLink aus der korrigierten full_rlink_wrapper.py importierst
    from full_rlink_wrapper import (
        RLink, RLinkError, # Hauptklasse importieren
        RLinkLight, RLinkAxisId, RLinkAxisDir # Benötigte Enums
    )
except ImportError as e:
    print(f"Fehler: Konnte 'full_rlink_wrapper.py' nicht finden: {e}", file=sys.stderr)
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
LOOP_CONTROL_SLEEP = 0.04 # Sekunden Pause in der Haupt-Steuerschleife (ca. 25 Hz)
# HEARTBEAT_INTERVAL = 0.5 # Wird nicht mehr für if benötigt
MOVEMENT_SPEED = 100    # Max. Wert für X/Y Achse (Bereich -127 bis 127)

# !!! WICHTIG: PASSE DIESE ID AN DEINE SITZKANTELUNG AN !!!
# Probiere ID_0, ID_1, ID_2 etc. aus, bis die richtige Achse reagiert.
SEAT_TILT_AXIS_ID = RLinkAxisId.ID_0 # <-- ÄNDERN ZUM TESTEN

# --- Key Mappings ---
KEY_MAP = {
    ecodes.KEY_W: 'w',
    ecodes.KEY_A: 'a',
    ecodes.KEY_S: 's',
    ecodes.KEY_D: 'd',
    ecodes.KEY_H: 'h', # Horn
    ecodes.KEY_L: 'l', # Light (DIP)
    ecodes.KEY_T: 't', # Tilt Up
    ecodes.KEY_G: 'g', # Tilt Down
    ecodes.KEY_Q: 'q',
    ecodes.KEY_ESC: 'esc',
}

# --- Tastatur-Controller Klasse (mit Lock und korrigierter Logik) ---
class KeyboardController:
    def __init__(self, rlink_instance: RLink): # Typ-Hinweis auf RLink
        """Initialisiert den Controller."""
        self.rlink = rlink_instance
        self.pressed_keys = set()
        self.keys_lock = threading.Lock() # Lock für pressed_keys
        self.horn_on = False
        self.lights_on = False # Zustand für Abblendlicht (DIP)
        self.quit_event = threading.Event()
        self.keyboard_device = None
        self.keyboard_thread = None
        # Initialisiere last_sent Werte
        self._last_sent_x = 0
        self._last_sent_y = 0
        self._last_sent_horn = self.horn_on
        self._last_sent_light = self.lights_on
        self._last_sent_axis_dir = {} # Zustand für Achsen merken

    def _find_keyboard_device(self):
        """Sucht automatisch nach einem Tastaturgerät."""
        devices = [InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                has_keys = any(code in KEY_MAP for code in capabilities[ecodes.EV_KEY])
                if has_keys:
                    print(f"Tastatur gefunden: {device.path} ({device.name})")
                    return device.path
        return None

    def _keyboard_thread_func(self):
        """Thread-Funktion: Liest Tastaturereignisse und aktualisiert Zustände (mit Lock)."""
        print("Keyboard thread started.")
        device_path = self._find_keyboard_device()
        if not device_path:
            print("Fehler: Keine Tastatur gefunden.", file=sys.stderr)
            self.quit_event.set(); print("Keyboard thread finished due to error."); return

        try:
            self.keyboard_device = InputDevice(device_path)
            print(f"Verwende Tastatur: {self.keyboard_device.path}")
        except OSError as e:
            print(f"Fehler beim Öffnen von {device_path}: {e}", file=sys.stderr)
            if e.errno == 13: print("-> Keine Berechtigung. 'sudo' oder Gruppe 'input'?", file=sys.stderr)
            self.quit_event.set(); print("Keyboard thread finished due to error."); return

        try:
            self.keyboard_device.grab()
            print("Tastatur exklusiv erfasst.")

            for event in self.keyboard_device.read_loop():
                if self.quit_event.is_set(): break

                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)
                    key_code = key_event.scancode
                    key_name = KEY_MAP.get(key_code)
                    key_state = key_event.keystate

                    if key_name:
                        with self.keys_lock: # Lock verwenden
                            if key_state == key_event.key_down or key_state == key_event.key_hold:
                                self.pressed_keys.add(key_name)
                            elif key_state == key_event.key_up:
                                self.pressed_keys.discard(key_name)

                        if key_state == key_event.key_down: # Nur bei erstem Drücken
                            if key_name == 'h':
                                self.horn_on = not self.horn_on
                                print(f"\nHupe {'AN' if self.horn_on else 'AUS'}", flush=True)
                            elif key_name == 'l':
                                self.lights_on = not self.lights_on
                                print(f"\nLicht (DIP) {'AN' if self.lights_on else 'AUS'}", flush=True)
                            elif key_name == 'q' or key_name == 'esc':
                                print(f"\nBeenden durch '{key_name}' erkannt.", flush=True)
                                self.quit_event.set(); break
        except IOError as e:
             print(f"\nFehler beim Lesen vom Keyboard-Device (getrennt?): {e}", file=sys.stderr)
             self.quit_event.set()
        except Exception as e:
            print(f"\nUnerwarteter Fehler im Keyboard-Thread: {e}", file=sys.stderr)
            self.quit_event.set()
        finally:
            if self.keyboard_device:
                try: self.keyboard_device.ungrab(); print("Tastatur freigegeben.")
                except Exception: pass
                try: self.keyboard_device.close()
                except Exception: pass
        print("Keyboard thread finished.")

    def start(self):
        """Startet den Keyboard-Listener-Thread."""
        if self.keyboard_thread is not None and self.keyboard_thread.is_alive():
            print("Keyboard thread läuft bereits.")
            return False
        self.quit_event.clear()
        self.keyboard_thread = threading.Thread(target=self._keyboard_thread_func, daemon=True)
        self.keyboard_thread.start()
        time.sleep(0.5) # Kurz warten
        if not self.keyboard_thread.is_alive() or self.quit_event.is_set():
             print("Fehler: Keyboard Thread konnte nicht korrekt gestartet werden.", file=sys.stderr)
             return False
        print("Keyboard listener thread gestartet.")
        return True

    def stop(self):
        """Stoppt den Keyboard-Listener-Thread."""
        print("Keyboard listener wird gestoppt...")
        self.quit_event.set()
        if self.keyboard_thread is not None:
            self.keyboard_thread.join(timeout=1.0)
            if self.keyboard_thread.is_alive():
                 print("Warnung: Keyboard thread hat sich nach Timeout nicht beendet.", file=sys.stderr)
        print("Keyboard listener gestoppt.")

    def run_control_loop(self):
        """Haupt-Steuerschleife, sendet Befehle an RLink."""
        if not self.rlink or not self.rlink._opened:
             print("Fehler: RLink ist nicht initialisiert oder geöffnet.", file=sys.stderr)
             self.quit_event.set(); return
        if not self.keyboard_thread or not self.keyboard_thread.is_alive():
             print("Fehler: Keyboard thread läuft nicht.", file=sys.stderr)
             self.quit_event.set(); return

        print("\nSteuerung aktiv:")
        print(" - WASD:  Fahren")
        print(" - T:     Sitzkantelung HOCH")
        print(" - G:     Sitzkantelung RUNTER")
        print(" - H:     Hupe AN/AUS")
        print(" - L:     Licht (DIP) AN/AUS")
        print(" - ESC/Q: Beenden")
        print(f"--- ACHTUNG: Sitzkantelung ist auf AXIS ID {SEAT_TILT_AXIS_ID.value} gemappt (ggf. ändern!) ---")
        print("\nWarte auf Eingaben...")

        speed_info_str = "Speed: --- km/h (Set:---, Lim:---)" # Platzhalter

        try:
            while not self.quit_event.is_set():
                # 1. Heartbeat IMMER senden
                self.rlink.heartbeat()

                # Kopiere gedrückte Tasten für diesen Durchlauf (mit Lock)
                with self.keys_lock:
                    current_pressed = set(self.pressed_keys)

                # 2. Bewegung berechnen
                target_x = 0; target_y = 0
                if 'w' in current_pressed: target_y += MOVEMENT_SPEED
                if 's' in current_pressed: target_y -= MOVEMENT_SPEED
                if 'a' in current_pressed: target_x -= MOVEMENT_SPEED
                if 'd' in current_pressed: target_x += MOVEMENT_SPEED
                target_x = max(-127, min(127, target_x))
                target_y = max(-127, min(127, target_y))

                # 3. Bewegungs-Befehl immer senden
                self.rlink.set_xy(target_x, target_y)

                # 4. Hupe / Licht nur senden, wenn geändert
                if self.horn_on != self._last_sent_horn:
                    self.rlink.set_horn(self.horn_on)
                    self._last_sent_horn = self.horn_on
                if self.lights_on != self._last_sent_light:
                    self.rlink.set_light(RLinkLight.DIP, self.lights_on)
                    self._last_sent_light = self.lights_on

                # 5. Achsensteuerung (Sitzkantelung)
                target_axis_dir = RLinkAxisDir.NONE
                if 't' in current_pressed: target_axis_dir = RLinkAxisDir.UP
                elif 'g' in current_pressed: target_axis_dir = RLinkAxisDir.DOWN

                last_dir = self._last_sent_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                if target_axis_dir != last_dir:
                    self.rlink.set_axis(SEAT_TILT_AXIS_ID, target_axis_dir)
                    self._last_sent_axis_dir[SEAT_TILT_AXIS_ID] = target_axis_dir

                # 6. Geschwindigkeit abrufen
                try:
                    speed_setting, true_speed, limit_flag = self.rlink.get_speed()
                    true_speed_kmh = true_speed * 3.6
                    speed_info_str = f"Speed: {true_speed_kmh:4.1f} km/h (Set:{speed_setting}, Lim:{limit_flag})"
                except RLinkError as e:
                    speed_info_str = f"Speed: Error ({e.status_code if hasattr(e, 'status_code') else '?'})"
                except Exception:
                    speed_info_str = "Speed: Error (Unknown)"

                # 7. Debug/Status-Ausgabe
                status_line = f"\rKeys: [{','.join(sorted(list(current_pressed))):<10s}] | Target: ({target_x:+4d},{target_y:+4d}) | Tilt: {target_axis_dir.name if target_axis_dir != RLinkAxisDir.NONE else 'NONE': <4s} | {speed_info_str}      "
                print(status_line, end="", flush=True)

                # 8. Schlafen
                time.sleep(LOOP_CONTROL_SLEEP)

        except KeyboardInterrupt:
            print("\nCtrl+C erkannt, beende Steuerschleife.", flush=True)
            self.quit_event.set()
        except Exception as e:
            print(f"\nFehler in der Steuerschleife: {e}", file=sys.stderr)
            self.quit_event.set()
        finally:
             print() # Zeilenumbruch nach Ende der Schleife

# --- Ende Klasse KeyboardController ---


# --- Hauptprogrammablauf (Korrigiert für Wrapper mit interner Enumeration) ---
if __name__ == "__main__":
    print("WARNUNG: Dieses Skript basiert auf dem funktionierenden Minimal-Wrapper.")
    print("         Es wird erwartet, dass die *originale* (fehlerhafte) udev-Regel aktiv ist,")
    print("         damit die Enumeration und das Öffnen funktionieren (via Raw-USB Fallback).")
    print("-" * 60)
    print("Steuerung:")
    print(" - WASD:  Fahren")
    print(" - T:     Sitzkantelung HOCH")
    print(" - G:     Sitzkantelung RUNTER")
    print(" - H:     Hupe AN/AUS")
    print(" - L:     Licht (DIP) AN/AUS")
    print(" - ESC/Q: Beenden")
    print(f"--- ACHTUNG: Sitzkantelung ist auf AXIS ID {SEAT_TILT_AXIS_ID.value} gemappt (ggf. ändern!) ---")
    print("-" * 60)

    rlink_connection = None # Die RLink Instanz
    controller = None     # Die KeyboardController Instanz

    try:
        # --- Initialisierung mit Index (Wrapper macht Enumeration intern) ---
        print("Initialisiere RLink für Gerät 0...")
        # Erstelle Instanz, __init__ enumeriert und konstruiert
        rlink_connection = RLink(device_index=0) # Verwende Index 0

        # Öffne die Verbindung
        rlink_connection.open()

        # Initialisiere Lichter/Hupe/Achse
        rlink_connection.set_horn(False)
        rlink_connection.set_light(RLinkLight.DIP, False)
        rlink_connection.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)

        # Erstelle und starte den Keyboard Controller
        controller = KeyboardController(rlink_connection)
        if controller.start(): # Startet Keyboard Thread, gibt True bei Erfolg zurück
            controller.run_control_loop() # Startet Haupt-Steuerlogik (blockierend bis Ende)
        else:
             print("Konnte Keyboard-Controller nicht starten. Beende.", file=sys.stderr)

    except RLinkError as e:
        print(f"\nEin RLink-Fehler ist aufgetreten: {e}", file=sys.stderr)
    except FileNotFoundError as e:
         print(f"\nFehler beim Laden der Bibliothek: {e}", file=sys.stderr)
    except ImportError as e: # Falls evdev oder Wrapper fehlt
         print(f"\nImport Fehler: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nCtrl+C erkannt, räume auf...", file=sys.stderr)
        if controller: controller.quit_event.set() # Signalisiere Threads
    except Exception as e:
        print(f"\nEin unerwarteter Fehler ist aufgetreten: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        if controller: controller.quit_event.set() # Signalisiere Threads
    finally:
        # Aufräumen
        print("\nRäume auf...")
        if controller:
            controller.stop() # Stoppt Keyboard Thread
        if rlink_connection:
            # Schließe Verbindung und zerstöre RLink Handle explizit mit Methode
            rlink_connection.destruct()

        print("Aufgeräumt. Programm beendet.")