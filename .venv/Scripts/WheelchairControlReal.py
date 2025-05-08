#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import os # Für os.path.exists
import json # Für Konfigurationspersistenz
import math # Für math.copysign

# Importiere den VOLLSTÄNDIGEN Wrapper und die benötigten Enums/Klassen
try:
    from full_rlink_wrapper import ( # Annahme: Diese Datei existiert und enthält RLink etc.
        RLink, RLinkError,
        RLinkLight, RLinkAxisId, RLinkAxisDir, RLinkButton,
        MSP_OK # Importiere MSP_OK, falls nicht schon global im Wrapper
    )
except ImportError as e:
    print(f"Fehler: Konnte 'full_rlink_wrapper.py' oder RLink-Klassen nicht finden: {e}", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
HEARTBEAT_INTERVAL = 0.4 # Sekunden zwischen Heartbeats
# !!! WICHTIG: PASSE DIESE ID AN DEINE SITZKANTELUNG AN !!!
SEAT_TILT_AXIS_ID = RLinkAxisId.ID_0 # <-- ÄNDERN ZUM TESTEN
TILT_THRESHOLD_NORMALIZED = 0.5  # Schwellenwert für normalisierte Joystick Y-Achse (-1.0 bis 1.0)

CONFIG_FILE = "wheelchair_config.json" # Name der Speicherdatei
DEFAULT_CONFIG = {
    "gear_factors": { # Faktor für Geschwindigkeit (0.0 bis 1.0)
        "1": 0.2, # 20% der Maximalgeschwindigkeit
        "2": 0.4,
        "3": 0.6,
        "4": 0.8,
        "5": 1.0  # 100%
    },
    "acceleration_step": 10, # Maximale Änderung des Sendewerts (-127 bis 127) pro Aufruf
    "pi_side_deadzone": 0.1, # Deadzone auf dem Pi
    "min_rlink_command": 10
}

class WheelchairControlReal:
    """
    Steuert einen echten Rollstuhl über die RLink-Bibliothek.
    Implementiert Software-Gänge und Beschleunigungsrampen basierend auf
    Werten aus wheelchair_config.json.
    WARNUNG: Setzt voraus, dass die originale (fehlerhafte) udev-Regel
             aktiv ist, damit der verwendete RLink-Wrapper funktioniert!
    """
    _light_on = False
    _warn_on = False
    _horn_on = False
    _tilt_mode_active = False
    _current_axis_dir = {}

    _current_gear = 1 # Wird aus Config geladen oder Default
    _current_sent_x = 0.0
    _current_sent_y = 0.0
    _gear_factors = {}
    _acceleration_step = 10.0


    def __init__(self, device_index=0, config_filepath=CONFIG_FILE):
        print("Initialisiere WheelchairControlReal...")
        self.rlink: RLink | None = None
        self._heartbeat_thread = None
        self._quit_heartbeat = threading.Event()
        self.config_filepath = config_filepath # Pfad zur Konfig-Datei

        self._load_config() # Lade Konfiguration BEIM START

        try:
            self.rlink = RLink(device_index=device_index)
            self.rlink.open()

            # Initialzustand setzen (basierend auf internen Defaults, nicht Config hier)
            self.rlink.set_horn(self._horn_on)
            self.rlink.set_light(RLinkLight.DIP, self._light_on)
            self.rlink.set_light(RLinkLight.HAZARD, self._warn_on)
            self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE
            self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            self.rlink.set_xy(0,0)
            self._current_sent_x = 0.0
            self._current_sent_y = 0.0

            self._quit_heartbeat.clear()
            #self._heartbeat_thread = threading.Thread(target=self._heartbeat_thread_func, daemon=True)
            #self._heartbeat_thread.start()
            print("WheelchairControlReal Initialisierung erfolgreich.")
            print(f"Geladene Konfiguration: Gänge={self._gear_factors}, Beschl.={self._acceleration_step}")

        except RLinkError as e:
            print(f"FATAL: Konnte RLink nicht initialisieren oder öffnen: {e}", file=sys.stderr)
            raise ConnectionError(f"Failed to initialize RLink: {e}") from e
        except Exception as e:
            print(f"FATAL: Unerwarteter Fehler bei Initialisierung: {e}", file=sys.stderr)
            raise ConnectionError(f"Unexpected error during RLink init: {e}") from e

    def send_rlink_heartbeat(self):
        """Sendet einen Heartbeat an RLink, falls verbunden."""
        if self.rlink:
            try:
                self.rlink.heartbeat()
                # print("RLink Heartbeat sent synchronously") # Optional für Debugging
                return True
            except RLinkError as e:
                print(f"Fehler beim synchronen Senden des RLink Heartbeats: {e}", file=sys.stderr)
                return False
            except Exception as e:
                print(f"Unerwarteter Fehler beim synchronen Senden des RLink Heartbeats: {e}", file=sys.stderr)
                return False
        return False

    def _load_config(self):
        """Lädt Konfiguration aus JSON oder verwendet Defaults."""
        if os.path.exists(self.config_filepath):
            try:
                with open(self.config_filepath, 'r') as f:
                    config = json.load(f)
                # Lade und validiere gear_factors
                loaded_gear_factors = config.get("gear_factors", DEFAULT_CONFIG["gear_factors"].copy())
                self._gear_factors = {}
                for i in range(1, 6):
                    key = str(i)
                    try:
                        factor = float(loaded_gear_factors.get(key, DEFAULT_CONFIG["gear_factors"].get(key, 0.2 * i)))
                        self._gear_factors[key] = max(0.0, min(1.0, factor)) # Clamp 0.0-1.0
                    except (ValueError, TypeError):
                        self._gear_factors[key] = DEFAULT_CONFIG["gear_factors"].get(key, 0.2 * i)
                        print(f"Warnung: Ungültiger Faktor für Gang {key} in Config. Verwende Default.")

                # Lade und validiere acceleration_step
                try:
                    loaded_accel_step = float(config.get("acceleration_step", DEFAULT_CONFIG["acceleration_step"]))
                    self._acceleration_step = max(0.1, loaded_accel_step) # Muss positiv sein, min 0.1
                except (ValueError, TypeError):
                    self._acceleration_step = float(DEFAULT_CONFIG["acceleration_step"])
                    print(f"Warnung: Ungültiger acceleration_step in Config. Verwende Default.")

                    # Lade und validiere pi_side_deadzone
                    try:
                        loaded_dz = float(config.get("pi_side_deadzone", DEFAULT_CONFIG["pi_side_deadzone"]))
                        self._pi_side_deadzone = max(0.0, min(0.9, loaded_dz))  # Muss zwischen 0 und <1 sein
                    except (ValueError, TypeError):
                        self._pi_side_deadzone = float(DEFAULT_CONFIG["pi_side_deadzone"])
                        print(f"Warnung: Ungültiger pi_side_deadzone in Config. Verwende Default.")

                    # Lade und validiere min_rlink_command
                    try:
                        loaded_min_cmd = int(config.get("min_rlink_command", DEFAULT_CONFIG["min_rlink_command"]))
                        # Mindestens 1 (da 0 Stillstand ist), maximal vielleicht 40? Begrenzen.
                        self._min_rlink_command = max(1, min(40, loaded_min_cmd))
                    except (ValueError, TypeError):
                        self._min_rlink_command = int(DEFAULT_CONFIG["min_rlink_command"])
                        print(f"Warnung: Ungültiger min_rlink_command in Config. Verwende Default.")

                    print(f"Konfiguration geladen: Accel={self._acceleration_step}, PiDeadzone={self._pi_side_deadzone}, MinCmd={self._min_rlink_command}")

                print(f"Konfiguration aus {self.config_filepath} geladen.")
                return
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warnung: Fehler beim Laden von {self.config_filepath}: {e}. Verwende Defaults.", file=sys.stderr)
        else:
            print(f"Info: Konfigurationsdatei {self.config_filepath} nicht gefunden. Verwende Defaults und erstelle Datei.")

        # Fallback zu Defaults, wenn Datei nicht existiert oder fehlerhaft war
        self._gear_factors = DEFAULT_CONFIG["gear_factors"].copy()
        self._acceleration_step = float(DEFAULT_CONFIG["acceleration_step"])
        self._save_config() # Speichere Defaults

    def _save_config(self):
        """Speichert die aktuelle Konfiguration (nur gear_factors und acceleration_step)."""
        config_data = {
            "gear_factors": self._gear_factors,
            "acceleration_step": self._acceleration_step,
            "pi_side_deadzone": self._pi_side_deadzone,
            "min_rlink_command": self._min_rlink_command
        }
        try:
            with open(self.config_filepath, 'w') as f:
                json.dump(config_data, f, indent=4)
            print(f"Konfiguration in {self.config_filepath} gespeichert.")
        except IOError as e:
            print(f"Fehler beim Speichern der Konfiguration in {self.config_filepath}: {e}", file=sys.stderr)

    # --- Öffentliche Methoden zum Aktualisieren der Konfiguration (für Webinterface) ---
    def update_gear_factor(self, gear: int, factor: float) -> bool:
        gear_str = str(gear)
        if 1 <= gear <= 5 and 0.0 <= factor <= 1.0:
            self._gear_factors[gear_str] = factor
            self._save_config()
            print(f"Gangfaktor für Gang {gear_str} auf {factor} aktualisiert.")
            return True
        print(f"Fehler: Ungültiger Gang ({gear}) oder Faktor ({factor}) für update_gear_factor.", file=sys.stderr)
        return False

    def update_acceleration_step(self, step: float) -> bool:
        if step >= 0.1: # Erlaube kleine Beschleunigungsschritte
            self._acceleration_step = step
            self._save_config()
            print(f"Beschleunigungsschritt auf {step} aktualisiert.")
            return True
        print(f"Fehler: Ungültiger Beschleunigungsschritt ({step}). Muss >= 0.1 sein.", file=sys.stderr)
        return False

    # --- Restliche Methoden (Funktionalität wie zuvor, Heartbeat, Shutdown etc.) ---
    def _heartbeat_thread_func(self):
        print("Heartbeat thread started.")
        while not self._quit_heartbeat.wait(timeout=HEARTBEAT_INTERVAL):
            if self.rlink and self.rlink._opened:
                try:
                    self.rlink.heartbeat()
                except RLinkError as e:
                    print(f"Fehler im Heartbeat-Thread: {e}", file=sys.stderr); break
                except Exception as e:
                     print(f"Unerwarteter Fehler im Heartbeat-Thread: {e}", file=sys.stderr); break
            else: break
        print("Heartbeat thread finished.")

    def shutdown(self):
        print("WheelchairControlReal wird heruntergefahren...")
        self._quit_heartbeat.set()
        if self._heartbeat_thread is not None: self._heartbeat_thread.join(timeout=1.0)
        if self.rlink:
            try:
                 print("Stoppe Bewegung/Achsen vor Shutdown...")
                 self.rlink.set_xy(0, 0)
                 self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                 time.sleep(0.1)
            except Exception as e: print(f"Warnung: Fehler Shutdown-Stop: {e}", file=sys.stderr)
            self.rlink.destruct()
            self.rlink = None
        print("WheelchairControlReal  heruntergefahren.")

    def on_kantelung(self, on: bool):
        if on == self._tilt_mode_active: return
        self._tilt_mode_active = on
        print(f"Kantelungsmodus {'AKTIVIERT' if on else 'DEAKTIVIERT'}")
        if self.rlink:
            if on:
                print(" -> Stoppe Fahren."); self.rlink.set_xy(0, 0); self._current_sent_x = 0.0; self._current_sent_y = 0.0
            else:
                print(" -> Stoppe Kantelung."); self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE

    def get_kantelung(self) -> bool: return self._tilt_mode_active
    def on_horn(self, on: bool): self._horn_on = on; print(f"Hupe: {'AN' if on else 'AUS'}"); self.rlink.set_horn(on) if self.rlink else None
    def set_warn(self):
        self._warn_on = not self._warn_on; print(f"Warnblinker: {'AN' if self._warn_on else 'AUS'}")
        if self.rlink:
             self.rlink.set_light(RLinkLight.HAZARD, self._warn_on)
             if self._warn_on: self.rlink.set_light(RLinkLight.LEFT, False); self.rlink.set_light(RLinkLight.RIGHT, False)
    def get_warn(self) -> bool: return self._warn_on
    def set_lights(self):
        self._light_on = not self._light_on; print(f"Licht (DIP): {'AN' if self._light_on else 'AUS'}")
        if self.rlink: self.rlink.set_light(RLinkLight.DIP, self._light_on)
    def get_lights(self) -> bool: return self._light_on

    def get_wheelchair_speed(self) -> float:
        if self.rlink:
            try: _, true_speed, _ = self.rlink.get_speed(); return true_speed
            except RLinkError as e: print(f"Fehler get_speed: {e}", file=sys.stderr); return 0.0
            except Exception as e: print(f"Unerw. Fehler get_speed: {e}", file=sys.stderr); return 0.0
        else: return 0.0

    def set_direction(self, direction: tuple[float, float]):
        """
        Setzt Fahrtrichtung ODER Kantelung. Im Fahrmodus wird der Input-Bereich [-1, 1]
        (nach der Deadzone) auf den Output-Bereich [min_rlink_command/127, gear_factor] abgebildet,
        um die physikalische Ansprechschwelle zu überwinden, ohne die Maximalgeschwindigkeit
        des Ganges zu verändern. Wendet anschließend eine Beschleunigungsrampe an.
        Erwartet normalisierte Joystick-Werte (-1.0 bis 1.0) von der ML2.
        """
        if not self.rlink: return # Abbruch, wenn keine RLink-Verbindung

        # Eingabevalidierung
        if not isinstance(direction, tuple) or len(direction) != 2:
            print(f"Warnung: Ungültiges Format für set_direction: {direction}", file=sys.stderr)
            # Setze Ziele auf 0, um sicher anzuhalten
            self._target_x_for_ramping = 0.0
            self._target_y_for_ramping = 0.0
            # Wende Rampe an, um sanft zu stoppen (falls noch nicht geschehen)
            if not self._tilt_mode_active: # Nur wenn im Fahrmodus
                 try:
                     self._apply_drive_ramp_and_send()
                 except Exception as e: print(f"Warnung: Fehler beim Stoppen (ramp) bei ungültigem Input: {e}", file=sys.stderr)
            # Kantelung auch stoppen
            last_tilt_dir = self._current_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            if last_tilt_dir != RLinkAxisDir.NONE:
                try:
                    self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                    self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE
                except Exception as e: print(f"Warnung: Fehler beim Stoppen der Kantelung bei ungültigem Input: {e}", file=sys.stderr)
            return

        raw_x, raw_y = direction # -1.0 bis 1.0 von ML2

        # --- Logik für Kantelungsmodus ---
        if self._tilt_mode_active:
            # Fahrmodus stoppen (Ziel auf 0 setzen, Rampe anwenden)
            self._target_x_for_ramping = 0.0
            self._target_y_for_ramping = 0.0
            try:
                 self._apply_drive_ramp_and_send()
            except Exception as e: print(f"Warnung: Fehler beim Stoppen (ramp) bei Wechsel zu Kantelung: {e}", file=sys.stderr)


            # Y-Achse für Kantelung interpretieren
            target_axis_dir = RLinkAxisDir.NONE
            # Deadzone für Kantelung (kann anders sein als Fahr-Deadzone)
            tilt_deadzone = 0.1 # Beispiel
            if raw_y > tilt_deadzone and abs(raw_y) > TILT_THRESHOLD_NORMALIZED: target_axis_dir = RLinkAxisDir.UP
            elif raw_y < -tilt_deadzone and abs(raw_y) > TILT_THRESHOLD_NORMALIZED: target_axis_dir = RLinkAxisDir.DOWN

            last_dir = self._current_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
            if target_axis_dir != last_dir:
                try:
                    self.rlink.set_axis(SEAT_TILT_AXIS_ID, target_axis_dir)
                    self._current_axis_dir[SEAT_TILT_AXIS_ID] = target_axis_dir
                    # Debug.Log($"Set Tilt Axis to: {target_axis_dir}");
                except Exception as e: print(f"Fehler bei set_axis: {e}", file=sys.stderr)
            return # Ende der Methode für Kantelungsmodus

        # --- Logik für Fahrmodus ---
        # Kantelungsmodus stoppen (falls noch aktiv)
        last_tilt_dir = self._current_axis_dir.get(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
        if last_tilt_dir != RLinkAxisDir.NONE:
             try:
                 self.rlink.set_axis(SEAT_TILT_AXIS_ID, RLinkAxisDir.NONE)
                 self._current_axis_dir[SEAT_TILT_AXIS_ID] = RLinkAxisDir.NONE
             except Exception as e: print(f"Warnung: Fehler beim Stoppen der Kantelung bei Wechsel zu Fahrmodus: {e}", file=sys.stderr)

        # --- Input Remapping Logik ---
        gear_str = str(self._current_gear)
        # Maximaler Output-Faktor für diesen Gang (aus Config, 0-1)
        max_speed_factor = self._gear_factors.get(gear_str, 1.0)
        # Minimaler Output-Faktor basierend auf der RLink-Schwelle (aus Config, 0-1)
        min_output_normalized = float(self._min_rlink_command) / 127.0

        # Sicherstellen, dass min Output nicht größer als max Output ist
        # Wenn doch, wird der Output konstant sein (falls > deadzone)
        effective_min_output = min_output_normalized
        if effective_min_output >= max_speed_factor:
            effective_min_output = max_speed_factor

        # Berechne Ziel für X mit Remapping
        target_x = 0.0
        if abs(raw_x) >= self._pi_side_deadzone: # Input außerhalb der Pi-Deadzone?
            # Berechne, wie weit der Input im *aktiven* Bereich (nach Deadzone) ist (0 bis 1)
            input_range = 1.0 - self._pi_side_deadzone
            # Vermeide Division durch Null, falls Deadzone >= 1 (sollte nicht passieren)
            if input_range <= 1e-6: normalized_input_x = 1.0
            else: normalized_input_x = (abs(raw_x) - self._pi_side_deadzone) / input_range

            # Berechne den verfügbaren Output-Bereich über dem Minimum
            output_range = max_speed_factor - effective_min_output
            # Stelle sicher, dass der Bereich nicht negativ ist
            if output_range < 0: output_range = 0

            # Bilde den normalisierten Input auf den Output-Bereich ab und addiere das Minimum
            scaled_output_x = effective_min_output + normalized_input_x * output_range

            # Wende Vorzeichen wieder an und skaliere auf RLink-Wertebereich
            target_x = math.copysign(scaled_output_x * 127.0, raw_x)

        # Berechne Ziel für Y mit Remapping (gleiche Logik)
        target_y = 0.0
        if abs(raw_y) >= self._pi_side_deadzone:
            input_range = 1.0 - self._pi_side_deadzone
            if input_range <= 1e-6: normalized_input_y = 1.0
            else: normalized_input_y = (abs(raw_y) - self._pi_side_deadzone) / input_range

            output_range = max_speed_factor - effective_min_output
            if output_range < 0: output_range = 0
            scaled_output_y = effective_min_output + normalized_input_y * output_range
            target_y = math.copysign(scaled_output_y * 127.0, raw_y)

        # Setze die Ziele für die Rampe
        self._target_x_for_ramping = target_x
        self._target_y_for_ramping = target_y

        # Wende Rampe an und sende Befehl
        try:
            self._apply_drive_ramp_and_send()
        except Exception as e: print(f"Fehler in _apply_drive_ramp_and_send: {e}", file=sys.stderr)

    def _apply_drive_ramp_and_send(self):
        """Interne Methode, um die Rampe anzuwenden und set_xy zu senden."""
        if not self.rlink: return

        # X-Achse Rampe
        delta_x = self._target_x_for_ramping - self._current_sent_x
        if abs(delta_x) < self._acceleration_step:
            self._current_sent_x = self._target_x_for_ramping
        else:
            self._current_sent_x += math.copysign(self._acceleration_step, delta_x)

        # Y-Achse Rampe
        delta_y = self._target_y_for_ramping - self._current_sent_y
        if abs(delta_y) < self._acceleration_step:
            self._current_sent_y = self._target_y_for_ramping
        else:
            self._current_sent_y += math.copysign(self._acceleration_step, delta_y)

        # Begrenzen auf den RLink Wertebereich (-127 bis 127)
        final_x = int(round(max(-127.0, min(127.0, self._current_sent_x))))
        final_y = int(round(max(-127.0, min(127.0, self._current_sent_y))))

        # --- DEBUG AUSGABE ---
        print(f"\rRAMP: Target=({self._target_x_for_ramping:.1f},{self._target_y_for_ramping:.1f}) "
              f"CurrentSent=({self._current_sent_x:.1f},{self._current_sent_y:.1f}) "
              f"FinalSent=({final_x},{final_y})   ", end="", flush=True)
        # --- ENDE DEBUG ---

        self.rlink.set_xy(final_x, final_y)
        # _last_sent_x/y werden nicht mehr für Moduswechsel gebraucht,
        # da _target_x/y_for_ramping im Kantelungsmodus auf 0 gesetzt werden
        # und die Rampe dann sanft auf 0 fährt.

    def set_gear(self, gearUp: bool) -> int:
        """Ändert den Software-Gang."""
        if gearUp:
            if self._current_gear < 5: self._current_gear += 1
        else:
            if self._current_gear > 1: self._current_gear -= 1
        print(f"Software-Gang auf {self._current_gear} gesetzt (Faktor: {self._gear_factors.get(str(self._current_gear), 'N/A')})")
        # Hardware-Gang-Simulation (Button Press) bleibt wie es war, falls benötigt
        # if self.rlink:
        #     # ... (Kommentierter Code für Button Press) ...
        return self._current_gear

    def get_actual_gear(self) -> int:
        """Gibt den aktuellen Software-Gang zurück."""
        return self._current_gear
"""
# --- Testblock ---
if __name__ == '__main__':
    print("Starte Test für WheelchairControlReal mit Software-Gängen & Rampe...")
    print(f"Konfigurationsdatei: {os.path.abspath(CONFIG_FILE)}")
    print(f"Stelle sicher, dass die originale (fehlerhafte) udev-Regel aktiv ist!")

    wc_instance = None
    try:
        wc_instance = WheelchairControlReal(device_index=0)

        print("\n--- Teste Software-Gänge ---")
        # Lade Faktoren aus der Instanz, um sicherzustellen, dass sie geladen wurden
        print(f"Geladene Gang-Faktoren: {wc_instance._gear_factors}")
        print(f"Geladener Beschl.-Schritt: {wc_instance._acceleration_step}")

        for i in range(1, 7): # Teste alle Gänge, inkl. Versuch über Max hinaus
            print(f"Aktueller Gang: {wc_instance.get_actual_gear()}")
            if i < 5: wc_instance.set_gear(True) # True für Gang hoch
            elif i == 5: wc_instance.set_gear(True) # Versuche über Max
            elif i == 6: wc_instance.set_gear(False) # Gehe wieder runter
            time.sleep(0.2)

        print("\n--- Teste Beschleunigungsrampe (Vorwärts) ---")
        print(f"Setze Software-Gang auf 5 für max. Geschwindigkeit.")
        while wc_instance.get_actual_gear() < 5: wc_instance.set_gear(True)

        print("Sende Ziel: (0, 1.0) = Volle Fahrt vorwärts im aktuellen Gang")
        for i in range(30): # Simuliere Joystick wird gehalten
            wc_instance.set_direction((0.0, 1.0)) # Joystick Y voll nach vorn
            print(f"  Loop {i+1}: Gesendet X={int(round(wc_instance._current_sent_x))}, Y={int(round(wc_instance._current_sent_y))}")
            time.sleep(0.05) # Simuliert Intervall der Joystick-Updates (20Hz)

        print("Sende Ziel: (0, 0) - Stoppen")
        for i in range(30): # Simuliere Stopp-Rampe
            wc_instance.set_direction((0.0, 0.0))
            print(f"  Loop {i+1} (Stop): Gesendet X={int(round(wc_instance._current_sent_x))}, Y={int(round(wc_instance._current_sent_y))}")
            if abs(wc_instance._current_sent_x) < 0.01 and abs(wc_instance._current_sent_y) < 0.01 : # Werte sind nah an Null
                # Ein paar Mal Null senden, um sicher zu stoppen
                for _ in range(5):
                    wc_instance.set_direction((0.0,0.0))
                    print(f"  Final Stop: Gesendet X={int(round(wc_instance._current_sent_x))}, Y={int(round(wc_instance._current_sent_y))}")
                    time.sleep(0.05)
                break
            time.sleep(0.05)

        print("\n--- Teste Kantelung ---")
        print("Aktiviere Kantelungsmodus")
        wc_instance.on_kantelung(True)
        print("Kantele HOCH (Joystick Y=1.0)")
        for _ in range(20): # Simuliere halten
            wc_instance.set_direction((0.0, 1.0))
            time.sleep(0.1)
        print("Stoppe Kantelung (Joystick Y=0.0)")
        wc_instance.set_direction((0.0, 0.0))
        time.sleep(0.5)
        print("Deaktiviere Kantelungsmodus")
        wc_instance.on_kantelung(False)
        time.sleep(0.5)
        print("Fahre kurz vorwärts nach Kantelungsmodus-Ende")
        wc_instance.set_direction((0.0, 0.5))
        time.sleep(1)
        wc_instance.set_direction((0.0,0.0))


    except ConnectionError as e:
         print(f"Initialisierungsfehler: {e}")
    except Exception as e:
        print(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if wc_instance:
            wc_instance.shutdown()
    print("\nTest beendet.")
    """