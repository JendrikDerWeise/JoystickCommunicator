#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import random # Nur noch für set_gear benötigt
import os

# Importiere den VOLLSTÄNDIGEN Wrapper und die benötigten Enums/Klassen
try:
    from full_rlink_wrapper import ( # Annahme: Klassen sind in dieser Datei
        RLink, RLinkError,
        RLinkLight, RLinkAxisId, RLinkAxisDir, RLinkButton, # Füge RLinkButton hinzu
        MSP_OK # Importiere MSP_OK, falls nicht schon global
    )
except ImportError as e:
    # Falls 'full_rlink_wrapper.py' die Klassen nicht enthält, passe den Import an
    print(f"Fehler: Konnte 'full_rlink_wrapper.py' oder RLink-Klassen nicht finden: {e}", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
HEARTBEAT_INTERVAL = 0.1 # Sekunden zwischen Heartbeats
# !!! WICHTIG: PASSE DIESE ID AN DEINE SITZKANTELUNG AN !!!
SEAT_TILT_AXIS_ID = RLinkAxisId.ID_0 # <-- ÄNDERN ZUM TESTEN
# Schwellenwert für Joystick Y-Achse zur Aktivierung der Kantelung
TILT_THRESHOLD = 50

class WheelchairControlReal:
    """
    Steuert einen echten Rollstuhl über die RLink-Bibliothek.
    Implementiert Modusumschaltung für Kantelung über Joystick.
    Ersetzt die Platzhalterklasse WheelchairControl.
    WARNUNG: Setzt voraus, dass die originale (fehlerhafte) udev-Regel
             aktiv ist, damit der verwendete RLink-Wrapper funktioniert!
    """
    # Interne Zustände
    _actual_gear = 1
    _light_on = False
    _warn_on = False
    _horn_on = False
    _tilt_mode_active = False # NEU: Zustand für Kantelungsmodus
    # Merkt sich die letzte gesendete Richtung für jede Achse
    _current_axis_dir = {}
    # Merkt sich die letzten gesendeten Fahrwerte
    _last_sent_x = 0
    _last_sent_y = 0


    def __init__(self, device_index=0):
        """Initialisiert die Verbindung zum Rollstuhl."""
        print("Initialisiere WheelchairControlReal...")
        self.rlink: RLink | None = None
        self._heartbeat_thread = None
        self._quit_heartbeat = threading.Event()

        try:
            self.rlink = RLink(device_index=device_index)
            self.rlink.open()

            # Initialzustand setzen
            self.rlink.set_horn(self._horn_on)
            self.rlink.set_light(RLinkLight.DIP, self._light_on)
            self.rlink.set_light(RLinkLight.HAZARD, self._warn_on)
            self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE
            self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            self.rlink.set_xy(0,0) # Sicherstellen, dass wir stehen

            self._quit_heartbeat.clear()
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_thread_func, daemon=True)
            self._heartbeat_thread.start()
            print("WheelchairControlReal Initialisierung erfolgreich.")

        except RLinkError as e:
            print(f"FATAL: Konnte RLink nicht initialisieren oder öffnen: {e}", file=sys.stderr)
            raise ConnectionError(f"Failed to initialize RLink: {e}") from e
        except Exception as e:
            print(f"FATAL: Unerwarteter Fehler bei Initialisierung: {e}", file=sys.stderr)
            raise ConnectionError(f"Unexpected error during RLink init: {e}") from e

    def _heartbeat_thread_func(self):
        """Sendet periodisch Heartbeats."""
        print("Heartbeat thread started.")
        while not self._quit_heartbeat.wait(timeout=HEARTBEAT_INTERVAL):
            if self.rlink and self.rlink._opened:
                try:
                    self.rlink.heartbeat()
                except RLinkError as e:
                    print(f"Fehler im Heartbeat-Thread: {e}", file=sys.stderr)
                    break
                except Exception as e:
                     print(f"Unerwarteter Fehler im Heartbeat-Thread: {e}", file=sys.stderr)
                     break
            else:
                break
        print("Heartbeat thread finished.")

    def shutdown(self):
        """Beendet den Heartbeat-Thread und gibt RLink-Ressourcen frei."""
        print("WheelchairControlReal wird heruntergefahren...")
        self._quit_heartbeat.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1.0)

        if self.rlink:
            try:
                 print("Stoppe Bewegung/Achsen vor Shutdown...")
                 self.rlink.set_xy(0, 0)
                 self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                 # Hier ggf. weitere Achsen stoppen
                 time.sleep(0.1) # Kurze Pause geben
            except Exception as e:
                 print(f"Warnung: Fehler beim Stoppen der Achsen/Bewegung beim Shutdown: {e}", file=sys.stderr)
            self.rlink.destruct()
            self.rlink = None
        print("WheelchairControlReal heruntergefahren.")

    # --- Angepasste Methoden ---

    def on_kantelung(self, on: bool):
        """Schaltet den Kantelungsmodus ein oder aus."""
        if on == self._tilt_mode_active:
            return # Kein Wechsel nötig

        self._tilt_mode_active = on
        print(f"Kantelungsmodus {'AKTIVIERT' if on else 'DEAKTIVIERT'}")

        if self.rlink:
            if on:
                # Kantelung aktiviert -> Fahren stoppen
                print(" -> Stoppe Fahren.")
                self.rlink.set_xy(0, 0)
                self._last_sent_x = 0
                self._last_sent_y = 0
            else:
                # Kantelung deaktiviert -> Kantelung stoppen
                print(" -> Stoppe Kantelung.")
                self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE

    def get_kantelung(self) -> bool:
        """Gibt zurück, ob der Kantelungsmodus AKTIV ist."""
        return self._tilt_mode_active

    def on_horn(self, on: bool):
        """Schaltet die Hupe ein/aus."""
        self._horn_on = on
        if self.rlink:
            self.rlink.set_horn(self._horn_on)

    def set_warn(self):
        """Schaltet den Warnblinker um."""
        self._warn_on = not self._warn_on
        print(f"Schalte Warnblinker {'AN' if self._warn_on else 'AUS'}")
        if self.rlink:
             self.rlink.set_light(RLinkLight.HAZARD, self._warn_on)
             if self._warn_on: # Andere Blinker aus bei Warnblinker an
                  self.rlink.set_light(RLinkLight.LEFT, False)
                  self.rlink.set_light(RLinkLight.RIGHT, False)

    def get_warn(self) -> bool:
        """Gibt den aktuellen Zustand des Warnblinkers zurück."""
        return self._warn_on

    def set_lights(self):
        """Schaltet das Abblendlicht (DIP) um."""
        self._light_on = not self._light_on
        print(f"Schalte Abblendlicht {'AN' if self._light_on else 'AUS'}")
        if self.rlink:
            self.rlink.set_light(RLinkLight.DIP, True)

    def get_lights(self) -> bool:
        """Gibt den aktuellen Zustand des Abblendlichts zurück."""
        return self._light_on

    def get_wheelchair_speed(self) -> float:
        """Liest die aktuelle 'trueSpeed' vom Rollstuhl."""
        if self.rlink:
            try:
                _, true_speed, _ = self.rlink.get_speed() # speed_setting, limit_flag ignorieren wir hier
                return true_speed
            except RLinkError as e:
                print(f"Fehler beim Abrufen der Geschwindigkeit: {e}", file=sys.stderr)
                return 0.0
            except Exception as e:
                 print(f"Unerwarteter Fehler beim Abrufen der Geschwindigkeit: {e}", file=sys.stderr)
                 return 0.0
        else:
            return 0.0

    def set_direction(self, direction: tuple[int, int]):
        """Setzt die Fahrtrichtung ODER die Kantelungsrichtung, je nach Modus."""
        if not self.rlink: return

        if not isinstance(direction, tuple) or len(direction) != 2:
            print(f"Warnung: Ungültiges Format für set_direction erwartet (x, y), erhalten: {direction}", file=sys.stderr)
            # Im Zweifelsfall alles anhalten
            if self._tilt_mode_active:
                 self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                 self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE
            else:
                 self.rlink.set_xy(0, 0)
                 self._last_sent_x = 0
                 self._last_sent_y = 0
            return

        x, y = direction
        x = x*100
        y = y*100
        x = int(x); y = int(y) # Sicherstellen, dass es ints sind
        deadzone_threshold_scaled = 15  # Beispiel: Werte unter +/- 15 ignorieren (anpassen!)
        if abs(x) < deadzone_threshold_scaled:
            x = 0
        if abs(y) < deadzone_threshold_scaled:
            y = 0

        if self._tilt_mode_active:
            # --- KANTELUNGSMODUS ---
            # Sicherstellen, dass Fahren gestoppt ist (nur bei Änderung senden)
            if self._last_sent_x != 0 or self._last_sent_y != 0:
                self.rlink.set_xy(0, 0)
                self._last_sent_x = 0
                self._last_sent_y = 0

            # Y-Achse für Kantelung interpretieren
            target_axis_dir = RLinkAxisDir.NONE
            if y > TILT_THRESHOLD:
                target_axis_dir = RLinkAxisDir.UP
            elif y < -TILT_THRESHOLD:
                target_axis_dir = RLinkAxisDir.DOWN

            # Nur senden, wenn sich die Richtung geändert hat
            last_dir = self._current_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            if target_axis_dir != last_dir:
                self.rlink.set_axis(SEAT_TILT_AXIS_ID, target_axis_dir)
                self._current_axis_dir[SEAT_TILT_AXIS_ID] = target_axis_dir

        else:
            # --- FAHRMODUS ---
            # Sicherstellen, dass Kantelung gestoppt ist (nur bei Änderung senden)
            last_dir = self._current_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            if last_dir != RLinkAxisDir.NONE:
                 self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                 self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE

            # Fahrbefehl senden (Wrapper begrenzt Werte auf -127 bis 127)
            # Sende nur wenn geändert, um Flackern bei Stop zu vermeiden? Nein, continuous send war besser.
            self.rlink.set_xy(x, y)
            self._last_sent_x = x # Merken für den Moduswechsel
            self._last_sent_y = y


    def set_gear(self, gearUp: bool) -> int:
        """Simuliert das Ändern des Ganges und gibt ihn auf der Konsole aus.
        if gearUp:
            if self._actual_gear < 5:
                self._actual_gear += 1
                print(f"DEBUG: Gang hochgeschaltet auf {self._actual_gear}")
        else:
            if self._actual_gear > 1:
                self._actual_gear -= 1
                print(f"DEBUG: Gang runtergeschaltet auf {self._actual_gear}")"""

        # TODO: Hier könnte die Simulation eines Tastendrucks erfolgen,
        #       wenn die Taste bekannt ist. Z.B.:
        if self.rlink:
            print(f"DEBUG: Sende Button-Press für Gangwechsel (Taste: YR?)")
            button_to_press = RLinkButton.YELLOW_RING # Beispiel!
            self.rlink.set_button(button_to_press, True)
            time.sleep(0.1) # Kurze Verzögerung für einen Tastendruck
            self.rlink.set_button(button_to_press, False)
        # else:
        #      print("DEBUG: RLink nicht verbunden, Gangwechsel nur simuliert.")

        return self._actual_gear

    def get_actual_gear(self):
        return self._actual_gear

# --- Beispielhafte Nutzung ---
# if __name__ == '__main__':
#     print("Starte Beispiel für WheelchairControlReal...")
#     # WICHTIG: Setzt funktionierenden Wrapper und korrekte udev-Regel/Setup voraus!
#     #         (In diesem Fall: Originale, fehlerhafte udev-Regel)
#     wheelchair = None
#     try:
#         wheelchair = WheelchairControlReal(device_index=0)
#
#         print("\n--- Test Kommandos ---")
#         print("Aktiviere Kantelungsmodus...")
#         wheelchair.on_kantelung(True)
#         time.sleep(0.5)
#
#         print("Sende Kantelungsbefehl (HOCH)...")
#         wheelchair.set_direction((0, 100)) # Y=100 -> UP
#         time.sleep(3)
#
#         print("Stoppe Kantelung (Joystick Mitte)...")
#         wheelchair.set_direction((0, 0)) # Y=0 -> NONE
#         time.sleep(1)
#
#         print("Deaktiviere Kantelungsmodus...")
#         wheelchair.on_kantelung(False)
#         time.sleep(0.5)
#
#         print("Fahre vorwärts...")
#         wheelchair.set_direction((0, 50))
#         time.sleep(2)
#
#         print("Stoppe...")
#         wheelchair.set_direction((0, 0))
#         time.sleep(1)
#
#         # Geschwindigkeit lesen
#         speed = wheelchair.get_wheelchair_speed()
#         print(f"Aktuelle Geschwindigkeit (trueSpeed): {speed:.2f}")
#
#     except ConnectionError as e:
#          print(f"Verbindung zum Rollstuhl konnte nicht hergestellt werden: {e}")
#     except RLinkError as e:
#          print(f"Laufzeitfehler bei RLink-Kommunikation: {e}")
#     except Exception as e:
#         print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
#         import traceback
#         traceback.print_exc()
#     finally:
#         if wheelchair:
#             wheelchair.shutdown()
#
#     print("\nBeispiel beendet.")