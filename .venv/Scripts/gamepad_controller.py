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

        # Innerhalb der Klasse GamepadController

    def _find_gamepad(self):
        print("Suche nach Gamepad...")
        device_paths = list_devices()
        if not device_paths:
            print("WARNUNG: Keine Input-Geräte unter /dev/input/event* gefunden.", file=sys.stderr)
            return None

        print(f"Gefundene Event-Geräte: {device_paths}")
        potential_gamepads = []

        for path in device_paths:
            try:
                device = InputDevice(path)
                print(f"\nPrüfe Gerät: {device.path} (Name: '{device.name}', Phys: '{device.phys}')")

                cap = device.capabilities(verbose=False)
                has_ev_key = ecodes.EV_KEY in cap
                has_ev_abs = ecodes.EV_ABS in cap

                print(f"  Hat EV_KEY (Buttons)? {'Ja' if has_ev_key else 'Nein'}")
                print(f"  Hat EV_ABS (Achsen)?  {'Ja' if has_ev_abs else 'Nein'}")

                if has_ev_key and has_ev_abs:
                    abs_axes_codes = cap.get(ecodes.EV_ABS, [])  # Liste der gemeldeten Achs-Codes
                    key_codes = cap.get(ecodes.EV_KEY, [])  # Liste der gemeldeten Button-Codes

                    # --- Genauere Prüfung der Achsen ---
                    # ABS_X (Code 0), ABS_Y (Code 1) für linken Stick
                    # ABS_RX (Code 3), ABS_RY (Code 4) für rechten Stick
                    # ABS_Z (Code 2 für LT), ABS_RZ (Code 5 für RT)

                    # Wir erwarten, dass unser Controller diese Achsen anbietet:
                    expected_abs_axes = {
                        ABS_LEFT_X, ABS_LEFT_Y,  # Linker Stick ist essentiell
                        ABS_RIGHT_X, ABS_RIGHT_Y,  # Rechter Stick für Kantelung/Höhe
                        ABS_LT, ABS_RT  # Trigger für Gänge
                    }

                    # Welche davon sind in den Capabilities vorhanden?
                    present_abs_axes = set(abs_axes_codes)
                    has_left_stick = ABS_LEFT_X in present_abs_axes and ABS_LEFT_Y in present_abs_axes
                    has_right_stick = ABS_RIGHT_X in present_abs_axes and ABS_RIGHT_Y in present_abs_axes
                    has_triggers = ABS_LT in present_abs_axes and ABS_RT in present_abs_axes

                    print(f"  Hat Linken Stick?   {'Ja' if has_left_stick else 'Nein'}")
                    print(f"  Hat Rechten Stick?  {'Ja' if has_right_stick else 'Nein'}")
                    print(f"  Hat Trigger?        {'Ja' if has_triggers else 'Nein'}")

                    # Prüfe auf einige typische Buttons
                    present_key_codes = set(key_codes)
                    has_main_action_button = BTN_HORN in present_key_codes  # z.B. Kreuz/A
                    has_shoulder_button = BTN_KANTELUNG_MODE in present_key_codes  # z.B. L1/LB

                    print(f"  Hat gemappten Horn-Button? {'Ja' if has_main_action_button else 'Nein'}")
                    print(f"  Hat gemappten Kantelungs-Button? {'Ja' if has_shoulder_button else 'Nein'}")

                    # Kriterien: Muss linken Stick UND rechten Stick UND Trigger UND Hauptaktionsbuttons haben
                    # Diese Kriterien sind jetzt strenger, um das "Haupt"-Interface zu finden.
                    if has_left_stick and has_right_stick and has_triggers and has_main_action_button and has_shoulder_button:
                        # Zusätzlicher Check auf den Namen, um "Motion Sensors" etc. auszuschließen
                        if "controller" in device.name.lower() and "motion" not in device.name.lower() and "touchpad" not in device.name.lower():
                            print(f"  -> QUALIFIZIERTES Gamepad gefunden: {device.path} ({device.name})")
                            potential_gamepads.append(device.path)
                        else:
                            print(
                                f"  -> Erfüllt Achsen/Button-Kriterien, aber Name ('{device.name}') passt nicht optimal (ignoriere Motion/Touchpad).")
                    elif "controller" in device.name.lower() and has_left_stick and has_main_action_button:
                        # Fallback: Wenn der Name "Controller" enthält und zumindest linken Stick + Hauptbutton hat
                        print(
                            f"  -> Potentielles Gamepad (Fallback auf Name & Min-Kriterien): {device.path} ({device.name})")
                        potential_gamepads.append(device.path)  # Füge es hinzu, aber vielleicht weniger priorisiert
                    else:
                        print(f"  -> Nicht als primäres Gamepad eingestuft.")
                else:
                    print(f"  -> Kein Gamepad (fehlt EV_KEY oder EV_ABS).")
            except Exception as e:
                print(f"Fehler beim Prüfen von {path}: {e}", file=sys.stderr)

        if not potential_gamepads:
            print("WARNUNG: Kein Gerät erfüllte die Kriterien für ein Gamepad.", file=sys.stderr)
            return None

        # Wähle das beste Gerät aus (z.B. das mit den meisten erwarteten Features oder dem spezifischsten Namen)
        # Fürs Erste nehmen wir das erste, das die strengeren Kriterien erfüllte,
        # oder das erste aus dem Fallback.
        # Ideal wäre eine Priorisierung, aber das macht es komplex.
        # Wir nehmen einfach das erste gefundene, das die Bedingungen erfüllt hat.

        # Filtere nach Namen, um Motion Sensors etc. explizit auszuschließen, FALLS es mehrere gibt
        best_match = None
        for path in potential_gamepads:
            device = InputDevice(path)  # Erneutes Öffnen ist nicht ideal, aber für die Logik hier ok
            if "controller" in device.name.lower() and "motion" not in device.name.lower() and "touchpad" not in device.name.lower():
                best_match = path
                break  # Nimm das erste, das kein Sensor/Touchpad ist
            device.close()  # Schließe wieder

        if not best_match and potential_gamepads:
            best_match = potential_gamepads[0]  # Fallback auf das erste gefundene
            print(f"WARNUNG: Wähle Gamepad '{best_match}', Name könnte nicht ideal sein.")

        if best_match:
            print(f"Gamepad ausgewählt: {best_match}")
            return best_match
        else:
            print("WARNUNG: Kein Gerät endgültig ausgewählt.", file=sys.stderr)
            return None

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
