#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import os

# Importiere den NEUEN minimalen Wrapper und die Enum
try:
    from mini_rlink_wrapper_v2 import MiniRlink, RLinkError, RLinkLight
except ImportError as e:
    print(f"Fehler: Konnte 'mini_rlink_wrapper_v2.py' nicht finden: {e}", file=sys.stderr)
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
HEARTBEAT_INTERVAL = 0.5 # Sekunden zwischen Heartbeats
MOVEMENT_SPEED = 20    # Max. Wert für X/Y Achse (Bereich -127 bis 127)

# --- Key Mappings ---
KEY_MAP = {
    ecodes.KEY_W: 'w',
    ecodes.KEY_A: 'a',
    ecodes.KEY_S: 's',
    ecodes.KEY_D: 'd',
    ecodes.KEY_H: 'h', # Horn
    ecodes.KEY_L: 'l', # Light (DIP)
    ecodes.KEY_Q: 'q',
    ecodes.KEY_ESC: 'esc',
}

# --- Tastatur-Controller Klasse ---
class KeyboardController:
    def __init__(self, rlink_instance: MiniRlink):
        self.rlink = rlink_instance
        self.pressed_keys = set()
        self.horn_on = False
        self.lights_on = False # Zustand für Abblendlicht (DIP)
        self.quit_event = threading.Event()
        self.keyboard_device = None
        self.keyboard_thread = None
        self._last_sent_x = -999 # Um unnötiges Senden zu vermeiden
        self._last_sent_y = -999
        self._last_sent_horn = None
        self._last_sent_light = None

    def _find_keyboard_device(self):
        """Sucht automatisch nach einem Tastaturgerät."""
        # ... (Code aus wasd_control_evdev.py kann hierhin kopiert werden) ...
        devices = [InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            capabilities = device.capabilities(verbose=False)
            if ecodes.EV_KEY in capabilities:
                has_keys = any(code in KEY_MAP for code in capabilities[ecodes.EV_KEY])
                if has_keys: return device.path
        return None

    def _keyboard_thread_func(self):
        """Liest Tastaturereignisse und aktualisiert Zustände."""
        print("Keyboard thread started.")
        device_path = self._find_keyboard_device()
        if not device_path:
            print("Fehler: Keine Tastatur gefunden.", file=sys.stderr)
            self.quit_event.set(); return

        try:
            self.keyboard_device = InputDevice(device_path)
            print(f"Verwende Tastatur: {self.keyboard_device.path}")
        except OSError as e:
            print(f"Fehler beim Öffnen von {device_path}: {e}", file=sys.stderr)
            if e.errno == 13: print("-> Keine Berechtigung. 'sudo' oder Gruppe 'input'?", file=sys.stderr)
            self.quit_event.set(); return

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
                        if key_state == key_event.key_down or key_state == key_event.key_hold:
                            self.pressed_keys.add(key_name)
                            if key_state == key_event.key_down: # Nur bei erstem Drücken toggeln/quitten
                                if key_name == 'h':
                                    self.horn_on = not self.horn_on
                                elif key_name == 'l':
                                    self.lights_on = not self.lights_on
                                elif key_name == 'q' or key_name == 'esc':
                                    print(f"Beenden durch '{key_name}' erkannt.")
                                    self.quit_event.set(); break
                        elif key_state == key_event.key_up:
                            if key_name in self.pressed_keys:
                                self.pressed_keys.remove(key_name)
        except Exception as e:
            print(f"Fehler im Keyboard-Thread: {e}", file=sys.stderr)
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
            return
        self.quit_event.clear()
        self.keyboard_thread = threading.Thread(target=self._keyboard_thread_func, daemon=True)
        self.keyboard_thread.start()
        print("Keyboard listener thread gestartet.")

    def stop(self):
        """Stoppt den Keyboard-Listener-Thread."""
        print("Keyboard listener wird gestoppt...")
        self.quit_event.set()
        if self.keyboard_thread is not None:
            self.keyboard_thread.join(timeout=1.0) # Warte kurz
        print("Keyboard listener gestoppt.")

    def run_control_loop(self):
        """Haupt-Steuerschleife, sendet Befehle an RLink."""
        if not self.rlink or not self.rlink._opened:
             print("Fehler: RLink ist nicht initialisiert oder geöffnet.", file=sys.stderr)
             return
        if not self.keyboard_thread or not self.keyboard_thread.is_alive():
             print("Fehler: Keyboard thread läuft nicht.", file=sys.stderr)
             return

        print("\nSteuerung aktiv:")
        print(" - WASD: Bewegung")
        print(" - H:    Hupe an/aus")
        print(" - L:    Licht an/aus (Abblendlicht)")
        print(" - ESC/Q: Beenden")
        print("\nWarte auf Eingaben...")

        last_heartbeat_time = time.time()

        try:
            while not self.quit_event.is_set():
                current_time = time.time()

                # 1. Bewegung berechnen
                target_x = 0
                target_y = 0
                # Sicherer Zugriff auf das Set (obwohl GIL helfen sollte)
                current_pressed = set(self.pressed_keys)
                if 'w' in current_pressed: target_y += MOVEMENT_SPEED
                if 's' in current_pressed: target_y -= MOVEMENT_SPEED
                if 'a' in current_pressed: target_x -= MOVEMENT_SPEED
                if 'd' in current_pressed: target_x += MOVEMENT_SPEED
                target_x = max(-127, min(127, target_x))
                target_y = max(-127, min(127, target_y))

                # 2. Befehle nur senden, wenn nötig
                #if target_x != self._last_sent_x or target_y != self._last_sent_y:
                self.rlink.set_xy(target_x, target_y)
                    #self._last_sent_x = target_x
                    #self._last_sent_y = target_y

                if self.horn_on != self._last_sent_horn:
                    self.rlink.set_horn(self.horn_on)
                    self._last_sent_horn = self.horn_on

                if self.lights_on != self._last_sent_light:
                    # Beispiel: Schalte Abblendlicht (DIP)
                    self.rlink.set_light(RLinkLight.DIP, self.lights_on)
                    self._last_sent_light = self.lights_on

                # 3. Heartbeat
                if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    self.rlink.heartbeat()
                    last_heartbeat_time = current_time

                # 4. Schlafen
                #time.sleep(LOOP_CONTROL_SLEEP)

        except KeyboardInterrupt:
            print("\nCtrl+C erkannt, beende Steuerschleife.", flush=True)
            self.quit_event.set()
        except Exception as e:
            print(f"\nFehler in der Steuerschleife: {e}", file=sys.stderr)
            self.quit_event.set()

        print("Steuerschleife beendet.")


# --- Hauptprogrammablauf ---
if __name__ == "__main__":
    # WICHTIG: Stelle sicher, dass die originale, fehlerhafte udev-Regel aktiv ist!
    print("WARNUNG: Dieses Skript basiert auf dem funktionierenden Minimal-Wrapper.")
    print("         Es wird erwartet, dass die *originale* (fehlerhafte) udev-Regel aktiv ist,")
    print("         damit die Enumeration und das Öffnen funktionieren (via Raw-USB Fallback).")
    print("-" * 60)

    rlink_connection = None
    controller = None
    try:
        # Wähle das erste gefundene Gerät
        rlink_connection = MiniRlink(device_index=0)
        # Öffne die Verbindung (wird in __init__ nicht mehr gemacht)
        rlink_connection.open()

        # Initialisiere Licht/Hupe aus
        rlink_connection.set_horn(False)
        rlink_connection.set_light(RLinkLight.DIP, False)

        controller = KeyboardController(rlink_connection)
        controller.start() # Startet Keyboard Thread
        controller.run_control_loop() # Startet Haupt-Steuerlogik

    except RLinkError as e:
        print(f"\nEin RLink-Fehler ist aufgetreten: {e}", file=sys.stderr)
    except FileNotFoundError as e:
         print(f"\nFehler: {e}", file=sys.stderr)
    except ImportError as e:
         print(f"\nImport Fehler: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nEin unerwarteter Fehler ist aufgetreten: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        print("Räume auf...")
        if controller:
            controller.stop() # Stoppt Keyboard Thread und wartet kurz
        # RLink Verbindung wird durch __del__ oder __exit__ von MiniRlink geschlossen
        # Aber zur Sicherheit hier nochmal (falls Context Manager nicht genutzt wird)
        if rlink_connection:
             rlink_connection.close()

        print("Aufgeräumt. Programm beendet.")