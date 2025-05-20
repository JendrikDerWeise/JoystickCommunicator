#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys
import os
import math

# Importiere die WheelchairControlReal Klasse und Enums
try:
    # Stelle sicher, dass dieser Import auf deine tatsächliche Datei zeigt
    # und dass diese Datei die notwendigen Definitionen enthält.
    from wheelchair_control_module import (
        WheelchairControlReal, RLinkError,
        RLinkLight, RLinkAxisId, RLinkAxisDir,
        SEAT_TILT_AXIS_ID,  # SEAT_HEIGHT_AXIS_ID, # Auskommentiert
        TILT_THRESHOLD_NORMALIZED  # , HEIGHT_THRESHOLD_NORMALIZED # Auskommentiert
    )
except ImportError as e:
    print(f"Fehler: wheelchair_control_module.py oder Inhalt nicht gefunden: {e}", file=sys.stderr)
    print("Stelle sicher, dass die Datei existiert und die WheelchairControlReal-Klasse enthält.", file=sys.stderr)
    sys.exit(1)

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes, list_devices
except ImportError:
    print("Fehler: 'evdev' nicht gefunden. Installiere mit: pip3 install evdev", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
LOOP_CONTROL_SLEEP = 0.04
JOYSTICK_DEADZONE = 0.15
TRIGGER_THRESHOLD = 0.1  # Normalisierter Wert (0.0-1.0) für Trigger als "gedrückt"

# --- Gamepad Button/Achsen Mappings (Beispiel PS5/Xbox) ---
# Achsen
ABS_LEFT_X = ecodes.ABS_X
ABS_LEFT_Y = ecodes.ABS_Y
ABS_RIGHT_X = ecodes.ABS_RX
ABS_RIGHT_Y = ecodes.ABS_RY
ABS_LT = getattr(ecodes, 'ABS_LT', ecodes.ABS_Z)  # Linker Trigger
ABS_RT = getattr(ecodes, 'ABS_RT', ecodes.ABS_RZ)  # Rechter Trigger

# Knöpfe (Beispiele - passe sie an deinen Controller und deine Wünsche an!)
BTN_HORN = ecodes.BTN_SOUTH  # z.B. Kreuz (PS) / A (Xbox) für Hupe
BTN_LIGHTS = ecodes.BTN_WEST  # z.B. Viereck (PS) / X (Xbox) für Licht
BTN_WARN = ecodes.BTN_NORTH  # z.B. Dreieck (PS) / Y (Xbox) für Warnblinker
BTN_KANTELUNG_MODE = ecodes.BTN_TL  # z.B. L1 (PS) / LB (Xbox) für Kantelungsmodus
# BTN_HEIGHT_MODE = ecodes.BTN_TR    # Auskommentiert, da Sitzhöhe nicht verwendet wird
BTN_QUIT_APP = ecodes.BTN_START  # z.B. Options (PS) / Menu/Start (Xbox) zum Beenden


# Hilfsfunktion zum Formatieren der Button-Namen (außerhalb der Klasse)
def get_btn_display_name(button_code):
    name_or_list = ecodes.BTN.get(button_code)
    if isinstance(name_or_list, list):
        return name_or_list[0].replace('BTN_', '').replace('KEY_', '') if name_or_list else 'N/A (empty list)'
    elif isinstance(name_or_list, str):
        return name_or_list.replace('BTN_', '').replace('KEY_', '')
    return f'N/A (code {button_code})'


class GamepadController:
    def __init__(self, wheelchair_instance: WheelchairControlReal):
        self.wheelchair = wheelchair_instance
        self.gamepad_device = None
        self.event_thread = None
        self.control_thread = None
        self.quit_event = threading.Event()

        self.left_x, self.left_y = 0.0, 0.0
        self.right_x, self.right_y = 0.0, 0.0
        self.lt_value, self.rt_value = 0.0, 0.0

        self._button_states = {}
        self._trigger_pressed_lt, self._trigger_pressed_rt = False, False

        self._gp_kantelung_active = False
        # self._gp_height_active = False # Auskommentiert

        self.min_max_axis_vals = {}  # Wird in _event_thread_func gefüllt

    def _find_gamepad(self):
        print("Suche nach Gamepad...")
        device_paths = list_devices()
        if not device_paths:
            print("WARNUNG: Keine Input-Geräte unter /dev/input/event* gefunden.", file=sys.stderr)
            return None
        print(f"Gefundene Event-Geräte: {device_paths}")
        candidate_devices = []
        for path in device_paths:
            try:
                device = InputDevice(path)
                print(f"\nPrüfe Gerät: {device.path} (Name: '{device.name}', Phys: '{device.phys}')")
                cap = device.capabilities(verbose=False)
                has_ev_key = ecodes.EV_KEY in cap
                has_ev_abs = ecodes.EV_ABS in cap
                print(f"  Hat EV_KEY (Buttons)? {'Ja' if has_ev_key else 'Nein'}")
                print(f"  Hat EV_ABS (Achsen)?  {'Ja' if has_ev_abs else 'Nein'}")

                if "controller" in device.name.lower() and has_ev_key and has_ev_abs:
                    if "motion sensors" in device.name.lower() or "touchpad" in device.name.lower():
                        print(f"  -> Ignoriere spezialisiertes Controller-Interface: {device.name}")
                        device.close()
                        continue

                    print(f"  -> Potentielles Haupt-Gamepad-Interface gefunden: {device.path} ({device.name})")
                    # Grundlegende Prüfung, ob überhaupt ABS-Achsen gemeldet werden
                    if not cap.get(ecodes.EV_ABS, []):
                        print(f"  -> Aber keine ABS-Achsen in Capabilities für {device.name} gelistet. Ignoriere.")
                        device.close()
                        continue
                    candidate_devices.append(device.path)
                else:
                    print(f"  -> Nicht als Gamepad-Hauptinterface eingestuft.")
                    device.close()
            except Exception as e:
                print(f"Fehler beim Prüfen von {path}: {e}", file=sys.stderr)
                if 'device' in locals() and device and hasattr(device, 'fd') and device.fd != -1:
                    try:
                        device.close()
                    except:
                        pass

        if not candidate_devices:
            print("WARNUNG: Kein Gerät erfüllte die Kriterien für ein Gamepad-Hauptinterface.", file=sys.stderr)
            return None

        best_match = None
        # Wähle das erste Gerät, das nicht explizit als Sensor/Touchpad identifiziert wird
        for path in candidate_devices:
            try:
                temp_device = InputDevice(path)  # Kurz öffnen für Namen
                name_lower = temp_device.name.lower()
                temp_device.close()
                if "controller" in name_lower and "motion" not in name_lower and "touchpad" not in name_lower:
                    best_match = path
                    break
            except Exception:
                continue  # Ignoriere Geräte, die nicht geöffnet werden können

        if not best_match and candidate_devices:  # Fallback auf das erste in der Liste
            best_match = candidate_devices[0]
            print(f"WARNUNG: Wähle erstes potentielles Gamepad '{best_match}', Name könnte nicht ideal sein.")

        if best_match:
            print(f"Gamepad ausgewählt: {best_match}")
            return best_match
        else:
            print("WARNUNG: Kein Gerät endgültig ausgewählt.", file=sys.stderr)
            return None

    # --- KORREKT EINGERÜCKTE METHODEN ---
    def _normalize_axis(self, value, min_val, max_val, deadzone=JOYSTICK_DEADZONE):
        if max_val == min_val: return 0.0
        norm_val = (float(value - min_val) / (max_val - min_val)) * 2.0 - 1.0
        if abs(norm_val) < deadzone: return 0.0
        return round(max(-1.0, min(1.0, norm_val)), 3)

    def _normalize_trigger(self, value, min_val, max_val):
        if max_val == min_val: return 0.0
        norm_val = float(value - min_val) / (max_val - min_val)
        return round(max(0.0, min(1.0, norm_val)), 3)

    def _handle_button_event(self, button_code, is_pressed_now):
        was_pressed_before = self._button_states.get(button_code, False)

        if is_pressed_now and not was_pressed_before:
            if button_code == BTN_HORN:
                self.wheelchair.on_horn(not self.wheelchair._horn_on)
            elif button_code == BTN_LIGHTS:
                self.wheelchair.set_lights()
            elif button_code == BTN_WARN:
                self.wheelchair.set_warn()
            elif button_code == BTN_KANTELUNG_MODE:
                self._gp_kantelung_active = not self._gp_kantelung_active
                self.wheelchair.on_kantelung(self._gp_kantelung_active)
                # if self._gp_kantelung_active: # Wenn Kantelung an, Höhe aus (Höhe ist auskommentiert)
                #     self._gp_height_active = False
                #     # self.wheelchair.on_height_mode(False) # Auskommentiert
            # elif button_code == BTN_HEIGHT_MODE: # Auskommentiert
            #     self._gp_height_active = not self._gp_height_active
            #     self.wheelchair.on_height_mode(self._gp_height_active)
            #     if self._gp_height_active:
            #         self._gp_kantelung_active = False
            #         self.wheelchair.on_kantelung(False)

        self._button_states[button_code] = is_pressed_now

    # --- ENDE KORREKT EINGERÜCKTE METHODEN ---

    def _event_thread_func(self):
        print("Gamepad event thread started.")
        device_path = self._find_gamepad()
        if not device_path:
            self.quit_event.set();
            print("Gamepad event thread finished (no device).");
            return
        try:
            self.gamepad_device = InputDevice(device_path)
            abs_capabilities_list = self.gamepad_device.capabilities().get(ecodes.EV_ABS, [])
            if not isinstance(abs_capabilities_list, list):
                print(f"WARNUNG: Unerwarteter Typ für ABS Capabilities: {type(abs_capabilities_list)}", file=sys.stderr)
                abs_capabilities_list = []
            self.min_max_axis_vals = {code: (info.min, info.max) for code, info in abs_capabilities_list}
            print(f"Gamepad '{self.gamepad_device.name}' verbunden.")
            print(f"Gefundene Achsen-Min/Max-Werte: {self.min_max_axis_vals}")
        except Exception as e:
            print(f"Fehler beim Öffnen des Gamepads {device_path}: {e}", file=sys.stderr)
            if isinstance(e, OSError) and e.errno == 13: print("-> Keine Berechtigung?", file=sys.stderr)
            self.quit_event.set();
            print("Gamepad event thread finished (error).");
            return
        try:
            # self.gamepad_device.grab() # Optional
            for event in self.gamepad_device.read_loop():
                if self.quit_event.is_set(): break
                if event.type == ecodes.EV_ABS:
                    min_val, max_val = self.min_max_axis_vals.get(event.code, (0, 255))
                    if event.code == ABS_LEFT_X:
                        self.left_x = self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_LEFT_Y:
                        self.left_y = -self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_RIGHT_X:
                        self.right_x = self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_RIGHT_Y:
                        self.right_y = -self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_LT:
                        self.lt_value = self._normalize_trigger(event.value, min_val, max_val)
                    elif event.code == ABS_RT:
                        self.rt_value = self._normalize_trigger(event.value, min_val, max_val)
                elif event.type == ecodes.EV_KEY:
                    is_pressed = (event.value == 1 or event.value == 2)
                    self._handle_button_event(event.code, is_pressed)
                    if event.code == BTN_QUIT_APP and event.value == 1:
                        print("Gamepad: Quit-Signal (BTN_QUIT_APP) empfangen.")
                        self.quit_event.set();
                        break
        except IOError as e:
            print(f"IOError im Gamepad-Thread: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unerwarteter Fehler im Gamepad-Thread: {e}", file=sys.stderr); import \
                traceback; traceback.print_exc()
        finally:
            self.quit_event.set()
            if self.gamepad_device:
                try:
                    self.gamepad_device.ungrab()
                except:
                    pass
                self.gamepad_device.close()
        print("Gamepad event thread finished.")

    def _control_loop_thread_func(self):
        print("Gamepad control loop started.")
        try:
            while not self.quit_event.is_set():
                if not self.wheelchair or not self.wheelchair.rlink or not self.wheelchair.rlink._opened:
                    time.sleep(0.1);
                    continue

                # if not self._gp_kantelung_active and not self._gp_height_active: # Höhe auskommentiert
                if not self._gp_kantelung_active:
                    self.wheelchair.set_direction((self.left_x, self.left_y))
                else:
                    self.wheelchair.set_direction((0.0, 0.0))

                if self._gp_kantelung_active:
                    self.wheelchair.set_direction((0.0, self.right_y))

                # Sitzhöhe auskommentiert
                # if self._gp_height_active:
                #     height_dir = RLinkAxisDir.NONE
                #     if self.right_x > HEIGHT_THRESHOLD_NORMALIZED: height_dir = RLinkAxisDir.UP
                #     elif self.right_x < -HEIGHT_THRESHOLD_NORMALIZED: height_dir = RLinkAxisDir.DOWN
                #     self.wheelchair.adjust_seat_height(height_dir)

                rt_is_pressed_now = self.rt_value > TRIGGER_THRESHOLD
                lt_is_pressed_now = self.lt_value > TRIGGER_THRESHOLD
                if rt_is_pressed_now and not self._trigger_pressed_rt: self.wheelchair.set_gear(True)
                if lt_is_pressed_now and not self._trigger_pressed_lt: self.wheelchair.set_gear(False)
                self._trigger_pressed_rt = rt_is_pressed_now
                self._trigger_pressed_lt = lt_is_pressed_now

                self.wheelchair.heartbeat()  # Methode in WheelchairControlReal muss heartbeat() heißen
                time.sleep(LOOP_CONTROL_SLEEP)
        except Exception as e:
            print(f"Fehler in Gamepad Control Loop: {e}", file=sys.stderr)
            import traceback;
            traceback.print_exc()
        finally:
            self.quit_event.set()
        print("Gamepad control loop finished.")

    def start(self):
        if self.event_thread and self.event_thread.is_alive():
            print("Gamepad-Threads laufen bereits.");
            return False
        self.quit_event.clear()
        self.event_thread = threading.Thread(target=self._event_thread_func, name="GamepadEventThread", daemon=True)
        self.control_thread = threading.Thread(target=self._control_loop_thread_func, name="GamepadControlThread",
                                               daemon=True)
        self.event_thread.start();
        time.sleep(1.0)  # Mehr Zeit für Gerätefindung
        if self.quit_event.is_set() or not self.event_thread.is_alive():
            print("Fehler: Gamepad Event-Thread konnte nicht initialisiert werden oder wurde sofort beendet.",
                  file=sys.stderr)
            if self.event_thread.is_alive(): self.event_thread.join(0.1)
            return False
        self.control_thread.start()
        print("Gamepad Event- und Control-Threads gestartet.")
        return True

    def stop(self):
        print("GamepadController wird gestoppt...")
        self.quit_event.set()
        if self.event_thread and self.event_thread.is_alive(): self.event_thread.join(timeout=1.0)
        if self.control_thread and self.control_thread.is_alive(): self.control_thread.join(timeout=1.0)
        print("GamepadController gestoppt.")


# --- ENDE KLASSENDEFINITION GamepadController ---


# --- STANDALONE TESTBLOCK ---
if __name__ == '__main__':
    print("Starte Gamepad Controller für Rollstuhl (Standalone Test)...")
    print("---------------------------------------------------------------")
    print("WARNUNG: Stellt sicher, dass die originale (fehlerhafte) udev-Regel aktiv ist!")
    print("         und dass der Benutzer Mitglied der Gruppe 'input' ist oder")
    print("         das Skript mit 'sudo' läuft (für /dev/input/* Zugriff).")
    print("---------------------------------------------------------------")
    print("Gamepad Steuerung (Beispiel PS5/Xbox ähnlich):")
    print(" - Linker Stick: Fahren")
    print(
        f" - Rechter Stick Y: Sitzkantelung (wenn {get_btn_display_name(BTN_KANTELUNG_MODE)} -> Modus ist '{SEAT_TILT_AXIS_ID.name}')")
    # print(f" - Rechter Stick X: Sitzhöhe (wenn {get_btn_display_name(BTN_HEIGHT_MODE)} -> Modus ist '{SEAT_HEIGHT_AXIS_ID.name}')") # Auskommentiert
    print(" - Rechter Trigger (R2/RT): Gang hoch")
    print(" - Linker Trigger (L2/LT): Gang runter")
    print(f" - {get_btn_display_name(BTN_HORN)}: Hupe AN/AUS")
    print(f" - {get_btn_display_name(BTN_LIGHTS)}: Licht AN/AUS")
    print(f" - {get_btn_display_name(BTN_WARN)}: Warnblinker AN/AUS")
    print(f" - {get_btn_display_name(BTN_KANTELUNG_MODE)}: Kantelungsmodus AN/AUS")
    # print(f" - {get_btn_display_name(BTN_HEIGHT_MODE)}: Sitzhöhenmodus AN/AUS") # Auskommentiert
    print(f" - {get_btn_display_name(BTN_QUIT_APP)}: Beenden")
    print("---------------------------------------------------------------")

    wc_real_instance = None
    gamepad_controller_instance = None
    try:
        print("Initialisiere WheelchairControlReal...")
        wc_real_instance = WheelchairControlReal(device_index=0)  # Nutzt wheelchair_config.json

        print("Initialisiere GamepadController...")
        gamepad_controller_instance = GamepadController(wc_real_instance)

        if not gamepad_controller_instance.start():
            print("Fehler beim Starten des Gamepad Controllers. Beende.", file=sys.stderr)
            if wc_real_instance: wc_real_instance.shutdown()
            sys.exit(1)

        print("Gamepad Controller gestartet. Läuft bis zum Quit-Signal (z.B. START-Taste am Gamepad)...")
        while not gamepad_controller_instance.quit_event.is_set():
            time.sleep(0.5)  # Haupt-Thread kann meistens schlafen
        print("Quit-Event vom GamepadController empfangen.")

    except KeyboardInterrupt:
        print("\nCtrl+C erkannt, beende Programm.")
        if gamepad_controller_instance:
            gamepad_controller_instance.quit_event.set()  # Signalisiere Threads
    except RLinkError as e:
        print(f"RLink Fehler im Hauptprogramm: {e}", file=sys.stderr)
    except ConnectionError as e:  # Von WheelchairControlReal init
        print(f"Verbindungsfehler im Hauptprogramm: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Ein unerwarteter Fehler im Hauptprogramm ist aufgetreten: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
    finally:
        print("\nRäume im Hauptprogramm auf...")
        if gamepad_controller_instance:
            gamepad_controller_instance.stop()
        if wc_real_instance:
            wc_real_instance.shutdown()
        print("Programm beendet.")
