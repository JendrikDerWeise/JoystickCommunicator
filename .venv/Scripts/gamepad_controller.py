# gamepad_controller.py
import time
import threading
import sys
import os
import math

try:
    # Passe den Modulnamen an, falls deine WheelchairControlReal-Klasse woanders liegt
    from WheelchairControlReal import (
        WheelchairControlReal, RLinkError,
        RLinkLight, RLinkAxisId, RLinkAxisDir,
        SEAT_TILT_AXIS_ID, #SEAT_HEIGHT_AXIS_ID,  # Importiere die Achsen-IDs
        TILT_THRESHOLD_NORMALIZED#, HEIGHT_THRESHOLD_NORMALIZED
    )
except ImportError as e:
    print(f"Fehler: wheelchair_control_module.py oder Inhalt nicht gefunden: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes, list_devices
except ImportError:
    print("Fehler: 'evdev' nicht gefunden. Installiere mit: pip3 install evdev", file=sys.stderr)
    sys.exit(1)

# --- Konfiguration ---
LOOP_SLEEP_TIME = 0.04  # Hauptschleife des GamepadControllers
JOYSTICK_DEADZONE = 0.15
TRIGGER_THRESHOLD = 0.1  # Normalisierter Wert (0.0-1.0)

# --- Gamepad Button/Achsen Mappings (Beispiel Xbox) ---
# Achsen
ABS_LEFT_X = ecodes.ABS_X    # Code 0
ABS_LEFT_Y = ecodes.ABS_Y    # Code 1
ABS_RIGHT_X = ecodes.ABS_RX   # Code 3 (in evtest als ABS_RX, Code 3)
ABS_RIGHT_Y = ecodes.ABS_RY   # Code 4 (in evtest als ABS_RY, Code 4)
ABS_LT = ecodes.ABS_Z      # Code 2 (Linker Trigger analog)
ABS_RT = ecodes.ABS_RZ      # Code 5 (Rechter Trigger analog)

BTN_HORN = ecodes.BTN_SOUTH    # Kreuz für Hupe
BTN_LIGHTS = ecodes.BTN_WEST   # Viereck für Licht
BTN_WARN = ecodes.BTN_NORTH    # Dreieck für Warnblinker
BTN_KANTELUNG_MODE = ecodes.BTN_TL # L1 für Kantelungsmodus
BTN_HEIGHT_MODE = ecodes.BTN_TR    # R1 für Höhenmodus
BTN_QUIT_APP = ecodes.BTN_START  # Options-Taste zum Beenden (oder BTN_MODE)

def get_btn_display_name(button_code):
    """
    Holt den Namen eines Buttons und formatiert ihn für die Anzeige.
    Behandelt den Fall, dass ecodes.BTN[code] eine Liste zurückgibt.
    """
    name_or_list = ecodes.BTN.get(button_code) # .get() ist sicherer als direkter Zugriff
    if isinstance(name_or_list, list):
        if name_or_list: # Stelle sicher, dass die Liste nicht leer ist
            return name_or_list[0].replace('BTN_', '').replace('KEY_', '') # Nimm den ersten Alias
        return 'N/A (empty list)'
    elif isinstance(name_or_list, str):
        return name_or_list.replace('BTN_', '').replace('KEY_', '')
    return f'N/A (code {button_code})'


class GamepadController:
    def __init__(self, wheelchair_instance: WheelchairControlReal):
        self.wheelchair = wheelchair_instance
        self.gamepad_device = None
        self.event_thread = None
        self.control_thread = None  # NEU für eigene Befehlsschleife
        self.quit_event = threading.Event()

        self.left_x, self.left_y = 0.0, 0.0
        self.right_x, self.right_y = 0.0, 0.0
        self.lt_value, self.rt_value = 0.0, 0.0

        self._button_states = {}  # Für Flankenerkennung
        self._trigger_pressed_lt, self._trigger_pressed_rt = False, False

        # Diese steuern die Modi für den Gamepad-Controller selbst
        self._gp_kantelung_active = False
        self._gp_height_active = False

    def _event_thread_func(self):
        print("Gamepad event thread started.")
        device_path = self._find_gamepad()
        if not device_path:
            self.quit_event.set()
            print("Gamepad event thread finished (no device).")
            return

        try:
            self.gamepad_device = InputDevice(device_path)

            # --- KORRIGIERTE STELLE ---
            # capabilities[ecodes.EV_ABS] gibt eine Liste von Tupeln (code, AbsInfo) zurück
            # oder eine leere Liste, wenn keine ABS-Events vorhanden sind.
            abs_capabilities_list = self.gamepad_device.capabilities().get(ecodes.EV_ABS, [])
            if not isinstance(abs_capabilities_list, list):  # Sicherheitscheck
                print(f"WARNUNG: Unerwarteter Typ für ABS Capabilities: {type(abs_capabilities_list)}", file=sys.stderr)
                abs_capabilities_list = []  # Fallback auf leere Liste

            self.min_max_axis_vals = {
                code: (info.min, info.max)
                for code, info in abs_capabilities_list  # Iteriere direkt über die Liste der Tupel
            }
            # --- ENDE KORRIGIERTE STELLE ---

            print(f"Gamepad '{self.gamepad_device.name}' verbunden.")
            print(f"Gefundene Achsen-Min/Max-Werte: {self.min_max_axis_vals}")  # Wichtige Debug-Ausgabe

            # Optional den exklusiven Zugriff anfordern:
            # try:
            #     self.gamepad_device.grab()
            #     print("Tastatur exklusiv erfasst (grabbed).")
            # except Exception as e_grab:
            #     print(f"Warnung: Konnte Gamepad nicht exklusiv erfassen: {e_grab}", file=sys.stderr)

        except Exception as e:
            print(f"Fehler beim Öffnen oder Initialisieren des Gamepads {device_path}: {e}", file=sys.stderr)
            if isinstance(e, OSError) and e.errno == 13:
                print("-> Möglicherweise fehlende Berechtigungen für /dev/input/* (sudo oder Gruppe 'input'?)",
                      file=sys.stderr)
            self.quit_event.set()
            print("Gamepad event thread finished (error).")
            return

        try:
            for event in self.gamepad_device.read_loop():
                if self.quit_event.is_set():
                    break

                # print(f"RAW EVENT: type={event.type}, code={event.code}, value={event.value}") # Intensives Debugging
                if event.type == ecodes.EV_ABS:
                    min_val, max_val = self.min_max_axis_vals.get(event.code, (0, 255))  # Default auf 0-255

                    if event.code == ABS_LEFT_X:
                        self.left_x = self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_LEFT_Y:
                        self.left_y = -self._normalize_axis(event.value, min_val, max_val)  # Y oft invertiert
                    elif event.code == ABS_RIGHT_X:
                        self.right_x = self._normalize_axis(event.value, min_val, max_val)
                    elif event.code == ABS_RIGHT_Y:
                        self.right_y = -self._normalize_axis(event.value, min_val, max_val)  # Y oft invertiert
                    elif event.code == ABS_LT:
                        self.lt_value = self._normalize_trigger(event.value, min_val, max_val)
                    elif event.code == ABS_RT:
                        self.rt_value = self._normalize_trigger(event.value, min_val, max_val)

                elif event.type == ecodes.EV_KEY:
                    is_pressed = (event.value == 1 or event.value == 2)  # DOWN oder HOLD
                    self._handle_button_event(event.code, is_pressed)

                    # Spezifische Quit-Logik (redundant, wenn _handle_button_event es tut, aber sicher)
                    if event.code == BTN_QUIT_APP and event.value == 1:  # Nur bei Drücken
                        print("Gamepad: Quit-Signal (BTN_QUIT_APP) empfangen.")
                        self.quit_event.set()
                        break
        except IOError as e:
            # Dieser Fehler tritt oft auf, wenn das Gamepad getrennt wird
            print(f"IOError im Gamepad-Thread (Gamepad getrennt?): {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unerwarteter Fehler im Gamepad-Event-Thread: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
        finally:
            self.quit_event.set()  # Sicherstellen, dass auch der Control-Thread beendet wird
            if self.gamepad_device:
                try:
                    self.gamepad_device.ungrab()
                    # print("Gamepad freigegeben (ungrabbed).") # Optional
                except Exception:
                    pass  # Fehler beim Ungrab ignorieren
                try:
                    self.gamepad_device.close()
                except Exception as e_close:
                    print(f"Fehler beim Schließen des Gamepad-Geräts: {e_close}", file=sys.stderr)
        print("Gamepad event thread finished.")

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

                # Filterung primär über den Namen und grundlegende Fähigkeiten
                if "controller" in device.name.lower() and has_ev_key and has_ev_abs:
                    # Ignoriere bekannte Sub-Devices, die nicht die Haupt-Inputs liefern
                    if "motion sensors" in device.name.lower() or "touchpad" in device.name.lower():
                        print(f"  -> Ignoriere spezialisiertes Controller-Interface: {device.name}")
                        device.close()  # Schließe Gerät, wenn es nicht das Haupt-Interface ist
                        continue

                    print(f"  -> Potentielles Haupt-Gamepad-Interface gefunden: {device.path} ({device.name})")
                    # Wir können die genauen Achsen hier nicht mehr 100% aus capabilities validieren,
                    # da sie für PS5 anscheinend nicht alle direkt gelistet sind.
                    # Wir verlassen uns darauf, dass das "Haupt"-Controller-Device die nötigen Achsen hat.
                    # Überprüfen wir zumindest, ob *irgendwelche* ABS-Achsen gemeldet werden.
                    if not cap.get(ecodes.EV_ABS, []):
                        print(
                            f"  -> Aber keine ABS-Achsen in Capabilities für {device.name} gelistet, obwohl EV_ABS vorhanden. Seltsam.")
                        device.close()
                        continue

                    candidate_devices.append(device.path)
                else:
                    print(
                        f"  -> Nicht als Gamepad-Hauptinterface eingestuft (Name oder Basisfähigkeiten passen nicht).")
                    device.close()  # Schließe Gerät, wenn es nicht in Frage kommt

            except Exception as e:
                print(f"Fehler beim Prüfen von {path}: {e}", file=sys.stderr)
                if 'device' in locals() and device:  # Sicherstellen, dass device Objekt existiert
                    try:
                        device.close()
                    except:
                        pass

        if not candidate_devices:
            print("WARNUNG: Kein Gerät erfüllte die Kriterien für ein Gamepad-Hauptinterface.", file=sys.stderr)
            return None

        # Wenn mehrere Kandidaten, nimm den ersten (oder implementiere eine Logik,
        # z.B. den mit den meisten Achsen/Buttons, aber das wird komplexer)
        if len(candidate_devices) > 1:
            print(f"WARNUNG: Mehrere potentielle Gamepad-Hauptinterfaces gefunden: {candidate_devices}",
                  file=sys.stderr)
            print(f"Verwende das erste gefundene: {candidate_devices[0]}", file=sys.stderr)

        selected_path = candidate_devices[0]
        print(f"Gamepad ausgewählt: {selected_path}")
        return selected_path

    def _control_loop_thread_func(self):
        """Periodisch Zustände verarbeiten und Befehle senden."""
        print("Gamepad control loop started.")
        try:
            while not self.quit_event.is_set():
                if not self.wheelchair or not self.wheelchair.rlink or not self.wheelchair.rlink._opened:
                    time.sleep(0.1)  # Warte, wenn Rollstuhl nicht bereit
                    continue

                # 1. Fahren (Linker Stick)
                # set_direction in WheelchairControlReal handhabt jetzt Modi
                # Wenn Kantelung oder Höhe aktiv ist, wird Fahren dort auf (0,0) gesetzt.
                if not self._gp_kantelung_active and not self._gp_height_active:
                    self.wheelchair.set_direction((self.left_x, self.left_y))
                else:
                    # Wenn ein Modifikator-Modus aktiv ist, senden wir (0,0) für Fahren,
                    # um sicherzustellen, dass die Rampe in WheelchairControlReal auf 0 geht.
                    self.wheelchair.set_direction((0.0, 0.0))

                # 2. Kantelung (Rechter Stick Y, wenn Modus via LB aktiv)
                if self._gp_kantelung_active:  # Modus wird durch LB im Event-Thread umgeschaltet
                    # WheelchairControlReal.set_direction nutzt Y für Kantelung, wenn dessen _tilt_mode_active ist
                    self.wheelchair.set_direction((0.0, self.right_y))

                # 3. Sitzhöhe (Rechter Stick X, wenn Modus via RB aktiv)
                '''if self._gp_height_active:  # Modus wird durch RB im Event-Thread umgeschaltet
                    height_dir = RLinkAxisDir.NONE
                    if self.right_x > HEIGHT_THRESHOLD_NORMALIZED:
                        height_dir = RLinkAxisDir.UP
                    elif self.right_x < -HEIGHT_THRESHOLD_NORMALIZED:
                        height_dir = RLinkAxisDir.DOWN
                    self.wheelchair.adjust_seat_height(height_dir)  # Rufe neue Methode auf
'''
                # 4. Gänge (Trigger) - mit Flankenerkennung
                rt_is_pressed_now = self.rt_value > TRIGGER_THRESHOLD
                lt_is_pressed_now = self.lt_value > TRIGGER_THRESHOLD

                if rt_is_pressed_now and not self._trigger_pressed_rt:
                    self.wheelchair.set_gear(True)  # Gang hoch
                if lt_is_pressed_now and not self._trigger_pressed_lt:
                    self.wheelchair.set_gear(False)  # Gang runter

                self._trigger_pressed_rt = rt_is_pressed_now
                self._trigger_pressed_lt = lt_is_pressed_now

                # 5. Heartbeat an RLink senden
                self.wheelchair.send_rlink_heartbeat()

                time.sleep(LOOP_CONTROL_SLEEP)
        except Exception as e:
            print(f"Fehler in Gamepad Control Loop: {e}", file=sys.stderr)
            import traceback;
            traceback.print_exc()
            self.quit_event.set()  # Bei Fehler auch beenden
        print("Gamepad control loop finished.")

    def start(self):
        """Startet die Gamepad-Verarbeitungs-Threads."""
        if self.event_thread and self.event_thread.is_alive():
            print("Gamepad-Threads laufen bereits.");
            return False  # Threads laufen schon

        self.quit_event.clear()
        self.event_thread = threading.Thread(target=self._event_thread_func, name="GamepadEventThread", daemon=True)
        self.event_thread.start()

        time.sleep(0.5)  # Gib dem Event-Thread etwas Zeit, das Gerät zu finden/öffnen

        if self.quit_event.is_set() or not self.event_thread.is_alive():  # Prüfen, ob Event-Thread korrekt gestartet ist
            print("Fehler: Gamepad Event-Thread konnte nicht initialisiert werden oder wurde sofort beendet.",
                  file=sys.stderr)
            # Stelle sicher, dass der Thread auch wirklich beendet wird, falls er noch minimal lief
            if self.event_thread.is_alive():
                self.event_thread.join(timeout=0.2)
            return False  # Signalisiere Fehler beim Starten

        # Starte den Control-Thread nur, wenn der Event-Thread erfolgreich gestartet ist
        self.control_thread = threading.Thread(target=self._control_loop_thread_func, name="GamepadControlThread",
                                               daemon=True)
        self.control_thread.start()

        print("Gamepad Event- und Control-Threads gestartet.")
        return True
    def stop(self):
        print("GamepadController wird gestoppt...")
        self.quit_event.set()
        if self.event_thread: self.event_thread.join(timeout=1.0)
        if self.control_thread: self.control_thread.join(timeout=1.0)
        print("GamepadController gestoppt.")

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
        #print(
            #f" - Rechter Stick X: Sitzhöhe (wenn {get_btn_display_name(BTN_HEIGHT_MODE)} -> Modus ist '{SEAT_HEIGHT_AXIS_ID.name}')")
    print(" - Rechter Trigger (R2/RT): Gang hoch")
    print(" - Linker Trigger (L2/LT): Gang runter")
    print(f" - {get_btn_display_name(BTN_HORN)}: Hupe AN/AUS")
    print(f" - {get_btn_display_name(BTN_LIGHTS)}: Licht AN/AUS")
    print(f" - {get_btn_display_name(BTN_WARN)}: Warnblinker AN/AUS")
    print(f" - {get_btn_display_name(BTN_KANTELUNG_MODE)}: Kantelungsmodus AN/AUS")
    #print(f" - {get_btn_display_name(BTN_HEIGHT_MODE)}: Sitzhöhenmodus AN/AUS")
    print(f" - {get_btn_display_name(BTN_QUIT_APP)}: Beenden")
    print("---------------------------------------------------------------")
    wc_real_instance = None
    gamepad_controller_instance = None
    try:
        print("Initialisiere WheelchairControlReal...")
        wc_real_instance = WheelchairControlReal(device_index=0)
        print("Initialisiere GamepadController...")
        gamepad_controller_instance = GamepadController(wc_real_instance)

        if not gamepad_controller_instance.start():
            print("Fehler beim Starten des Gamepad Controllers. Beende.", file=sys.stderr)
            if wc_real_instance: wc_real_instance.shutdown()
            sys.exit(1)

        while not gamepad_controller_instance.quit_event.is_set():
            time.sleep(0.5)
        print("Quit-Event vom GamepadController empfangen.")

    except KeyboardInterrupt:
        print("\nCtrl+C erkannt, beende Programm.")
    except RLinkError as e:
        print(f"RLink Fehler im Hauptprogramm: {e}", file=sys.stderr)
    except ConnectionError as e:
        print(f"Verbindungsfehler im Hauptprogramm: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}", file=sys.stderr); import traceback; traceback.print_exc()
    finally:
        print("\nRäume im Hauptprogramm auf...")
        if gamepad_controller_instance: gamepad_controller_instance.stop()
        if wc_real_instance: wc_real_instance.shutdown()
        print("Programm beendet.")
