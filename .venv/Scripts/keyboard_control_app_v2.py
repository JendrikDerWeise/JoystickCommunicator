#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Innerhalb von keyboard_control_app_v2.py

# --- (Imports und Konstanten wie zuvor) ---
import time
import threading
import sys
import os
try:
    from mini_rlink_wrapper_v2 import MiniRlink, RLinkError, RLinkLight # Importiere den korrekten Wrapper
except ImportError as e:
    print(f"Fehler: Konnte 'mini_rlink_wrapper_v2.py' nicht finden: {e}", file=sys.stderr)
    sys.exit(1)
try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
except ImportError:
    print("Fehler: Die Bibliothek 'evdev' wurde nicht gefunden.", file=sys.stderr)
    print("Bitte installiere sie mit: pip3 install evdev", file=sys.stderr)
    sys.exit(1)

LOOP_CONTROL_SLEEP = 0.04
HEARTBEAT_INTERVAL = 0.5
MOVEMENT_SPEED = 100

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
# -----------------------------------------

# --- Tastatur-Controller Klasse (Komplett & Korrigiert) ---
class KeyboardController:
    def __init__(self, rlink_instance: MiniRlink):
        """Initialisiert den Controller."""
        self.rlink = rlink_instance
        self.pressed_keys = set()
        self.keys_lock = threading.Lock() # Lock für pressed_keys
        self.horn_on = False
        self.lights_on = False # Zustand für Abblendlicht (DIP)
        self.quit_event = threading.Event()
        self.keyboard_device = None
        self.keyboard_thread = None
        # Initialisiere last_sent Werte, um unnötiges Senden beim Start zu vermeiden
        self._last_sent_x = 0
        self._last_sent_y = 0
        self._last_sent_horn = self.horn_on # Initialisiere mit aktuellem Zustand
        self._last_sent_light = self.lights_on # Initialisiere mit aktuellem Zustand

    def _find_keyboard_device(self):
        """Sucht automatisch nach einem Tastaturgerät."""
        devices = [InputDevice(path) for path in evdev.list_devices()]
        for device in devices:
            capabilities = device.capabilities(verbose=False)
            # Prüft auf EV_KEY (Tastenereignisse)
            if ecodes.EV_KEY in capabilities:
                # Prüft zusätzlich, ob bekannte Buchstabentasten vorhanden sind
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
            print("Fehler: Keine Tastatur gefunden. Stelle sicher, dass eine angeschlossen ist.", file=sys.stderr)
            self.quit_event.set() # Signal zum Beenden an andere Threads
            print("Keyboard thread finished due to error.")
            return

        try:
            self.keyboard_device = InputDevice(device_path)
            print(f"Verwende Tastatur: {self.keyboard_device.path}")
        except OSError as e:
            print(f"Fehler beim Öffnen von {device_path}: {e}", file=sys.stderr)
            if e.errno == 13: # Permission denied
                 print("-> Keine Berechtigung. Führe das Skript mit 'sudo' aus", file=sys.stderr)
                 print("   oder füge deinen Benutzer zur Gruppe 'input' hinzu:", file=sys.stderr)
                 print(f"   sudo usermod -a -G input {os.getlogin()}", file=sys.stderr)
                 print("   (Danach neu einloggen!)", file=sys.stderr)
            self.quit_event.set()
            print("Keyboard thread finished due to error.")
            return

        try:
            # Exklusiven Zugriff anfordern
            self.keyboard_device.grab()
            print("Tastatur exklusiv erfasst (grabbed).")

            # Ereignis-Schleife
            for event in self.keyboard_device.read_loop():
                if self.quit_event.is_set(): # Prüfe, ob das Beenden signalisiert wurde
                    break

                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)
                    key_code = key_event.scancode
                    key_name = KEY_MAP.get(key_code) # Übersetze Code in unseren Namen (w, a, s, d...)
                    key_state = key_event.keystate # 0=UP, 1=DOWN, 2=HOLD/REPEAT

                    if key_name:
                        # Lock verwenden für sicheren Zugriff auf pressed_keys
                        with self.keys_lock:
                            if key_state == key_event.key_down or key_state == key_event.key_hold:
                                self.pressed_keys.add(key_name)
                            elif key_state == key_event.key_up:
                                # Sicher entfernen, falls vorhanden
                                self.pressed_keys.discard(key_name) # discard() gibt keinen Fehler, wenn nicht vorhanden

                        # Toggle-Aktionen / Quit nur bei erstem Drücken (key_down) auslösen
                        if key_state == key_event.key_down:
                            if key_name == 'h':
                                self.horn_on = not self.horn_on # Zustand für Hauptschleife ändern
                                print(f"Hupe {'AN' if self.horn_on else 'AUS'}") # Direktes Feedback
                            elif key_name == 'l':
                                self.lights_on = not self.lights_on # Zustand für Hauptschleife ändern
                                print(f"Licht (DIP) {'AN' if self.lights_on else 'AUS'}") # Direktes Feedback
                            elif key_name == 'q' or key_name == 'esc':
                                print(f"Beenden durch '{key_name}' erkannt.")
                                self.quit_event.set()
                                break # Keyboard-Schleife verlassen

        except IOError as e:
             # Kann passieren, wenn das Gerät getrennt wird
             print(f"Fehler beim Lesen vom Keyboard-Device (getrennt?): {e}", file=sys.stderr)
             self.quit_event.set()
        except Exception as e:
            print(f"Unerwarteter Fehler im Keyboard-Thread: {e}", file=sys.stderr)
            self.quit_event.set()
        finally:
            # Wichtig: Gerät immer freigeben und schließen
            if self.keyboard_device:
                try:
                    self.keyboard_device.ungrab()
                    print("Tastatur freigegeben (ungrabbed).")
                except Exception as e:
                    # Kann fehlschlagen, wenn Gerät nicht mehr verbunden ist
                    print(f"Warnung beim Freigeben der Tastatur: {e}", file=sys.stderr)
                try:
                    self.keyboard_device.close()
                except Exception as e:
                    print(f"Fehler beim Schließen des Geräts: {e}", file=sys.stderr)

        print("Keyboard thread finished.")

    def start(self):
        """Startet den Keyboard-Listener-Thread."""
        if self.keyboard_thread is not None and self.keyboard_thread.is_alive():
            print("Keyboard thread läuft bereits.")
            return False # Nicht erneut starten
        self.quit_event.clear() # Sicherstellen, dass Quit-Flag zurückgesetzt ist
        self.keyboard_thread = threading.Thread(target=self._keyboard_thread_func, daemon=True)
        self.keyboard_thread.start()
        # Kurze Pause, um sicherzustellen, dass der Thread gestartet ist und evtl. das Gerät findet
        time.sleep(0.5)
        if not self.keyboard_thread.is_alive() or self.quit_event.is_set():
             print("Fehler: Keyboard Thread konnte nicht korrekt gestartet werden.", file=sys.stderr)
             return False # Start fehlgeschlagen
        print("Keyboard listener thread gestartet.")
        return True # Start erfolgreich

    def stop(self):
        """Stoppt den Keyboard-Listener-Thread."""
        print("Keyboard listener wird gestoppt...")
        self.quit_event.set() # Signal zum Beenden senden
        if self.keyboard_thread is not None:
            # Warte auf den Thread, aber nicht ewig
            self.keyboard_thread.join(timeout=1.0)
            if self.keyboard_thread.is_alive():
                 print("Warnung: Keyboard thread hat sich nach Timeout nicht beendet.", file=sys.stderr)
        print("Keyboard listener gestoppt.")

    def run_control_loop(self):
        """Haupt-Steuerschleife, sendet Befehle an RLink (mit Lock für Lesenzugriff)."""
        if not self.rlink or not self.rlink._opened:
             print("Fehler: RLink ist nicht initialisiert oder geöffnet.", file=sys.stderr)
             self.quit_event.set() # Beenden signalisieren
             return
        if not self.keyboard_thread or not self.keyboard_thread.is_alive():
             print("Fehler: Keyboard thread läuft nicht.", file=sys.stderr)
             self.quit_event.set() # Beenden signalisieren
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
                # Lock verwenden für sicheren Lesezugriff auf pressed_keys
                with self.keys_lock:
                    # Kopie innerhalb des Locks erstellen für atomaren Zustand
                    current_pressed = set(self.pressed_keys)

                # Berechnung basierend auf der sicheren Kopie
                if 'w' in current_pressed: target_y += MOVEMENT_SPEED
                if 's' in current_pressed: target_y -= MOVEMENT_SPEED
                if 'a' in current_pressed: target_x -= MOVEMENT_SPEED
                if 'd' in current_pressed: target_x += MOVEMENT_SPEED
                target_x = max(-127, min(127, target_x))
                target_y = max(-127, min(127, target_y))

                # 2. Bewegungs-Befehl immer senden
                self.rlink.set_xy(target_x, target_y)

                # 3. Hupe / Licht nur senden, wenn Zustand sich geändert hat
                #    (Lesen von self.horn_on/lights_on ist hier thread-sicher genug)
                if self.horn_on != self._last_sent_horn:
                    self.rlink.set_horn(self.horn_on)
                    self._last_sent_horn = self.horn_on

                if self.lights_on != self._last_sent_light:
                    # Beispiel: Schalte Abblendlicht (DIP)
                    self.rlink.set_light(RLinkLight.DIP, self.lights_on)
                    self._last_sent_light = self.lights_on

                # 4. Heartbeat
                if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    self.rlink.heartbeat()
                    last_heartbeat_time = current_time

                # 5. Schlafen (WICHTIG und AKTIV!)
                time.sleep(LOOP_CONTROL_SLEEP)

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