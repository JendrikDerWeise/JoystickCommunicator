#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket
import random
import struct
import os
import json  # Wird von WheelchairControlReal intern für Config genutzt

# Importiere deine Module
try:
    from WheelchairControlReal import WheelchairControlReal, RLinkError
except ImportError as e:
    print(f"[ZMQ-Server] Fehler: wheelchair_control_module.py nicht gefunden: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from gamepad_controller import GamepadController
except ImportError as e:
    print(f"[ZMQ-Server] Fehler: gamepad_controller.py nicht gefunden: {e}", file=sys.stderr)
    GamepadController = None
    print("[ZMQ-Server] WARNUNG: Gamepad-Steuerung wird nicht verfügbar sein.")

# --- Konstanten ---
HEARTBEAT_INTERVAL_TO_ML = 2  # Sekunden (Heartbeat-Intervall AN DEN *Client* ML2)
RECONNECT_INTERVAL_ZMQ = 10  # Sekunden (Wartezeit vor ZMQ-Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)

# --- ZeroMQ-Kontext erstellen (global für dieses Skript) ---
context = zmq.Context.instance()

# --- Globale Variablen für dieses Skript ---
magic_leap_ip = None
publisher_socket_to_ml = None
subscriber_socket_from_ml = None
wheelchair: WheelchairControlReal | None = None
gamepad_ctrl: GamepadController | None = None

# --- Trigger-Dateien (Pfade müssen mit app.py übereinstimmen) ---
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"
JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"
GAMEPAD_MODE_TRIGGER_FILE = "/tmp/gamepad_mode_trigger.txt"
last_config_send_time = 0
gamepad_control_is_active_by_trigger = False  # Gesteuert durch Webinterface-Trigger


# --- Netzwerk- und Konvertierungsfunktionen ---
def is_little_endian():
    return sys.byteorder == 'little'


def to_network_order(value, data_type):
    pack_format = data_type
    if is_little_endian() and data_type in ('i', 'f', 'd'): pack_format = '>' + data_type
    try:
        return struct.pack(pack_format, value)
    except Exception as e:
        raise ValueError(f"Pack-Fehler für Typ {data_type}, Wert {value}: {e}")


def from_network_order(data, data_type):
    pack_format = data_type
    if is_little_endian() and data_type in ('i', 'f', 'd'): pack_format = '>' + data_type
    try:
        return struct.unpack(pack_format, data)[0]
    except Exception as e:
        raise ValueError(f"Unpack-Fehler für Typ {data_type}, Daten {data}: {e}")


def get_correct_network_interface(target_ip_for_subnet_check):
    if not target_ip_for_subnet_check: return None
    try:
        target_subnet = ".".join(target_ip_for_subnet_check.split(".")[:3])
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    for ip_info in iface_details[netifaces.AF_INET]:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1' and ".".join(ip_address.split(".")[:3]) == target_subnet:
                            print(f"[ZMQ-Server] Korrekte Schnittstelle: {interface} ({ip_address})")
                            return ip_address
            except Exception:
                pass
        print(f"[ZMQ-Server] Warnung: Keine passende Schnittstelle im Subnetz von {target_ip_for_subnet_check}.",
              file=sys.stderr)
        return None
    except NameError:
        print("[ZMQ-Server] Fehler: 'netifaces' nicht gefunden.", file=sys.stderr); return None
    except Exception as e:
        print(f"[ZMQ-Server] Fehler in get_correct_network_interface: {e}", file=sys.stderr); return None


def get_magic_leap_ip_adb():  # Deine ursprüngliche, funktionierende Version
    try:
        start_time = time.time()
        timeout = 10
        while time.time() - start_time < timeout:
            print("[ZMQ-Server] Versuche ADB Befehl: adb shell ip route")
            result = subprocess.run(['adb', 'shell', 'ip', 'route'], capture_output=True, text=True, check=True,
                                    timeout=5)
            for line in result.stdout.splitlines():
                if "dev mlnet0" or "eth1" in line:
                    match = re.search(r'src (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                    if match:
                        ip_address = match.group(1)
                        print(f"[ZMQ-Server] Magic Leap 2 IP-Adresse (via ip route): {ip_address}")
                        return ip_address
            time.sleep(1)
        print("[ZMQ-Server] Timeout beim Ermitteln der IP-Adresse über ADB.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[ZMQ-Server] Fehler Ausführung 'adb shell ip route': {e}, Code: {e.returncode}, Output: {e.output}",
              file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("[ZMQ-Server] Timeout bei Ausführung von 'adb shell ip route'.", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("[ZMQ-Server] Fehler: 'adb' nicht gefunden. Ist ADB im PATH?", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ZMQ-Server] Unerwarteter Fehler bei ADB-IP-Ermittlung: {e}", file=sys.stderr)
        return None


def send_pc_ip_and_port_to_ml(ml_ip, pc_ip_for_ml, port_for_ml):
    if not pc_ip_for_ml:
        print("[ZMQ-Server] Fehler: Keine PC-IP zum Senden an ML2 vorhanden.", file=sys.stderr)
        return False
    temp_file = "pc_ip_port_zmq.txt"
    target_path_on_ml = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/'
    adb_command = ['adb', 'push', temp_file, target_path_on_ml]
    try:
        with open(temp_file, "w") as f:
            f.write(f"{pc_ip_for_ml}:{port_for_ml}")
        print(f"[ZMQ-Server] Versuche: {' '.join(adb_command)}")
        subprocess.run(adb_command, check=True, capture_output=True, timeout=10)
        print(
            f"[ZMQ-Server] PC IP ({pc_ip_for_ml}) und Port ({port_for_ml}) auf ML2 kopiert nach {target_path_on_ml}{temp_file}.")
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return True
    except Exception as e:
        print(f"[ZMQ-Server] Fehler beim Senden der PC IP/Port an ML2: {e}", file=sys.stderr)
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False


def process_gamepad_mode_trigger():
    """Prüft und verarbeitet die Gamepad-Modus-Trigger-Datei."""
    global gamepad_ctrl, gamepad_control_is_active_by_trigger, wheelchair

    if os.path.exists(GAMEPAD_MODE_TRIGGER_FILE):
        try:
            with open(GAMEPAD_MODE_TRIGGER_FILE, "r") as f:
                content = f.read().strip()
            command_part = content.split(":")[0]  # Extrahiere den Befehl (ENABLE_GAMEPAD/DISABLE_GAMEPAD)

            if command_part == "ENABLE_GAMEPAD":
                if GamepadController and (gamepad_ctrl is None or gamepad_ctrl.quit_event.is_set()):
                    print("[ZMQ-Server] Aktiviere Gamepad-Steuerung via Trigger...")
                    gamepad_ctrl = GamepadController(wheelchair)
                    if not gamepad_ctrl.start():
                        print("[ZMQ-Server] WARNUNG: GamepadController konnte nicht gestartet werden.", file=sys.stderr)
                        gamepad_ctrl = None
                        gamepad_control_is_active_by_trigger = False  # Zurücksetzen
                    else:
                        print("[ZMQ-Server] GamepadController erfolgreich gestartet.")
                        gamepad_control_is_active_by_trigger = True
                elif gamepad_ctrl and not gamepad_ctrl.quit_event.is_set():
                    print("[ZMQ-Server] Gamepad-Steuerung ist bereits aktiv (via Trigger).")
                    gamepad_control_is_active_by_trigger = True
                else:
                    print("[ZMQ-Server] GamepadController nicht verfügbar, kann nicht aktiviert werden.")
                    gamepad_control_is_active_by_trigger = False

            elif command_part == "DISABLE_GAMEPAD":
                if gamepad_ctrl and not gamepad_ctrl.quit_event.is_set():
                    print("[ZMQ-Server] Deaktiviere Gamepad-Steuerung via Trigger...")
                    gamepad_ctrl.stop()
                    gamepad_ctrl = None  # Wichtig: Instanz auf None setzen
                    print("[ZMQ-Server] GamepadController gestoppt.")
                gamepad_control_is_active_by_trigger = False

            os.remove(GAMEPAD_MODE_TRIGGER_FILE)
            print(
                f"[ZMQ-Server] Gamepad-Modus-Trigger verarbeitet. Web-Schalter-Status: {'AN' if gamepad_control_is_active_by_trigger else 'AUS'}")

        except Exception as e_gp_trigger:
            print(f"[ZMQ-Server] Fehler Verarbeitung Gamepad-Modus-Trigger: {e_gp_trigger}", file=sys.stderr)


# --- Hauptfunktion des ZMQ-Servers ---
def run_server():
    global magic_leap_ip, last_heartbeat_from_ml, publisher_socket_to_ml, subscriber_socket_from_ml
    global wheelchair
    global gamepad_ctrl
    global last_config_send_time
    global context
    global gamepad_control_is_active_by_trigger

    # GamepadController wird jetzt durch process_gamepad_mode_trigger() initialisiert/gestoppt

    while True:
        print("\n" + "=" * 30 + " ZMQ-SERVERTEIL (NEU)START " + "=" * 30)
        current_publisher_socket = None
        current_subscriber_socket = None
        pc_port_for_ml = None

        process_gamepad_mode_trigger()  # Prüfe Trigger zu Beginn jeder äußeren Schleife

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip:
            print(f"[ZMQ-Server] Konnte ML2 IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        pc_ip_for_ml = get_correct_network_interface(magic_leap_ip)
        if not pc_ip_for_ml:
            print(f"[ZMQ-Server] Konnte eigene passende IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        try:
            current_publisher_socket = context.socket(zmq.PUB)
            pc_port_for_ml = current_publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_ml}")
            publisher_socket_to_ml = current_publisher_socket
            print(f"[ZMQ-Server] Publisher (an ML2) gebunden an tcp://{pc_ip_for_ml}:{pc_port_for_ml}")

            current_subscriber_socket = context.socket(zmq.SUB)
            current_subscriber_socket.setsockopt(zmq.RCVTIMEO, INITIAL_CONNECTION_TIMEOUT * 1000)
            subscriber_socket_from_ml = current_subscriber_socket

            send_pc_ip_and_port(magic_leap_ip, pc_port_for_ml)
        except Exception as e:
            print(f"[ZMQ-Server] Fehler im ZMQ Socket Setup: {e}", file=sys.stderr)
            if current_publisher_socket: current_publisher_socket.close(linger=0)
            if current_subscriber_socket: current_subscriber_socket.close(linger=0)
            publisher_socket_to_ml = None;
            subscriber_socket_from_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        print(f"[ZMQ-Server] Warte auf READY von ML2 an tcp://{magic_leap_ip}:{pc_port_for_ml + 1}...")
        ready_received = False
        try:
            subscriber_socket_from_ml.connect(f"tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
            subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"READY")
            topic, _ = subscriber_socket_from_ml.recv_multipart()
            if topic == b"READY":
                print("[ZMQ-Server] READY von ML2 empfangen!")
                subscriber_socket_from_ml.setsockopt(zmq.UNSUBSCRIBE, b"READY")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"gear")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"lights")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"warn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"horn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"kantelung")
                ready_received = True
                print(f"[ZMQ-Server] Subscriber (von ML2) verbunden mit tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
                subscriber_socket_from_ml.setsockopt(zmq.RCVTIMEO, 1000)

                if publisher_socket_to_ml and wheelchair:
                    publisher_socket_to_ml.send_multipart(
                        [b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])
                    publisher_socket_to_ml.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                    publisher_socket_to_ml.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                    publisher_socket_to_ml.send_multipart(
                        [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    publisher_socket_to_ml.send_multipart(
                        [b"gamepad_status", to_network_order(gamepad_control_is_active_by_trigger, '?')])

        except zmq.error.Again:
            print("[ZMQ-Server] Timeout beim Warten auf READY von ML2.")
        except Exception as e:
            print(f"[ZMQ-Server] Fehler beim Warten auf READY: {e}", file=sys.stderr)

        if not ready_received:
            print("[ZMQ-Server] Setup der ML2-Verbindung nicht erfolgreich, starte ZMQ-Teil neu...")
            if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
            if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        print("[ZMQ-Server] Beginne Hauptkommunikation mit ML2...")
        last_heartbeat_from_ml = time.time()
        last_heartbeat_send_to_ml = 0
        current_ml_x = 0.0
        current_ml_y = 0.0

        while True:  # Innere ZMQ-Kommunikationsschleife
            try:
                current_time = time.time()
                process_gamepad_mode_trigger()  # Prüfe Trigger auch hier regelmäßig

                # --- Heartbeat AN ML2 senden ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed and \
                        current_time - last_heartbeat_send_to_ml > HEARTBEAT_INTERVAL_TO_ML:
                    publisher_socket_to_ml.send_multipart([b"heartbeat", b""])
                    last_heartbeat_send_to_ml = current_time

                # --- Trigger-Dateien für andere Befehle prüfen ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                    if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                        try:
                            print(f"[ZMQ-Server] Trigger '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                            publisher_socket_to_ml.send_multipart([b"joystick_toggle_visibility", b"toggle"])
                            print(f"[ZMQ-Server] -> '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' an ML2 gesendet.")
                            os.remove(JOYSTICK_VISIBILITY_TRIGGER_FILE)
                        except Exception as e_trig_vis:
                            print(f"[ZMQ-Server] Fehler Trigger JoystickVis: {e_trig_vis}", file=sys.stderr)
                    if os.path.exists(CONFIG_TRIGGER_FILE):
                        try:
                            trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                            if trigger_timestamp > last_config_send_time:
                                with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                    config_json_str = f.read()
                                if config_json_str:
                                    print(f"[ZMQ-Server] Sende ML2 Joystick Konfiguration (Trigger)...")
                                    publisher_socket_to_ml.send_multipart(
                                        [b"joystick_settings", config_json_str.encode('utf-8')])
                                    last_config_send_time = trigger_timestamp
                                os.remove(CONFIG_TRIGGER_FILE)
                        except Exception as e_cfg_trig:
                            print(f"[ZMQ-Server] Fehler Trigger Config: {e_cfg_trig}", file=sys.stderr)

                # --- Daten an ML2 senden (Geschwindigkeit) ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                    if wheelchair:
                        speed = wheelchair.get_wheelchair_speed()
                        publisher_socket_to_ml.send_multipart([b"topic_float", to_network_order(speed, 'f')])

                # --- Nachrichten von ML2 empfangen ---
                try:
                    if subscriber_socket_from_ml and not subscriber_socket_from_ml.closed and \
                            subscriber_socket_from_ml.poll(timeout=10):
                        topic, message = subscriber_socket_from_ml.recv_multipart()

                        if topic == b"heartbeat":
                            last_heartbeat_from_ml = time.time()
                        elif topic == b"joystickPos":
                            x = from_network_order(message[0:4], 'f')
                            y = from_network_order(message[4:8], 'f')
                            current_ml_x = x
                            current_ml_y = y
                        elif topic == b"gear":
                            if wheelchair:
                                received_value = from_network_order(message, '?')
                                actual_gear = wheelchair.set_gear(received_value)
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"gear", to_network_order(actual_gear, 'i')])
                        elif topic == b"lights":
                            if wheelchair:
                                wheelchair.set_lights()
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"lights", to_network_order(wheelchair.get_lights(), '?')])
                        elif topic == b"warn":
                            if wheelchair:
                                wheelchair.set_warn()
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"warn", to_network_order(wheelchair.get_warn(), '?')])
                        elif topic == b"horn":
                            if wheelchair: wheelchair.on_horn(from_network_order(message, '?'))
                        elif topic == b"kantelung":
                            if wheelchair:
                                received_value = from_network_order(message, '?')
                                wheelchair.on_kantelung(received_value)  # Dies schaltet den Modus in wheelchair
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                        else:
                            print(f"[ZMQ-Server] Unbekanntes Topic von ML2: {topic}")
                except zmq.error.Again:
                    pass

                # --- STEUERLOGIK UND RLINK HEARTBEAT ---
                gamepad_is_actually_running = gamepad_ctrl and not gamepad_ctrl.quit_event.is_set()

                if wheelchair:
                    # RLink Heartbeat IMMER senden, da GamepadController es auch tut
                    if hasattr(wheelchair, 'heartbeat'):
                        wheelchair.heartbeat()

                        # Wenn der Gamepad-Modus NICHT über das Webinterface explizit aktiviert ist
                    # ODER der GamepadController aus irgendeinem Grund nicht läuft,
                    # dann steuert die ML2.
                    if not gamepad_control_is_active_by_trigger or not gamepad_is_actually_running:
                        # print(f"DEBUG: ML2 steuert mit ({current_ml_x}, {current_ml_y})")
                        wheelchair.set_direction((current_ml_x, current_ml_y))
                    # else: Gamepad ist aktiv und vom Webinterface gewünscht, GamepadController.py sendet Befehle
                # --- ENDE STEUERLOGIK ---

                if time.time() - last_heartbeat_from_ml > RECONNECT_INTERVAL_ZMQ:
                    print("[ZMQ-Server] Heartbeat-Timeout von ML2!")
                    break

                # Wenn Gamepad-Modus via Web AN war, aber der Gamepad-Thread sich beendet hat
                if gamepad_control_is_active_by_trigger and (gamepad_ctrl is None or gamepad_ctrl.quit_event.is_set()):
                    print(
                        "[ZMQ-Server] Gamepad-Controller war gewünscht, ist aber beendet. Versuche Neustart oder deaktiviere.")
                    if gamepad_ctrl: gamepad_ctrl.stop()  # Alten stoppen, falls noch Referenz da
                    gamepad_ctrl = None
                    gamepad_control_is_active_by_trigger = False  # Zurücksetzen, damit ML2 wieder steuert
                    # Sende Status an ML2, dass Gamepad-Modus aus ist
                    if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                        publisher_socket_to_ml.send_multipart([b"gamepad_status", to_network_order(False, '?')])
                    # Kein 'break' hier, ML2 soll weiterlaufen

                time.sleep(0.01)  # Kurze Pause für die ZMQ-Hauptschleife
            except zmq.ZMQError as e:
                print(f"[ZMQ-Server] Fehler in ZMQ-Kommunikation: {e}"); break
            except Exception as e:
                print(f"[ZMQ-Server] Unerwarteter Fehler Hauptschleife: {e}"); import \
                    traceback; traceback.print_exc(); break

        print("[ZMQ-Server] ZMQ Kommunikationsschleife beendet. Starte ZMQ-Teil neu...")
        if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
        if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
        time.sleep(RECONNECT_INTERVAL_ZMQ)


# --- Programmstart ---
if __name__ == "__main__":
    # Globale Instanz für WheelchairControlReal ist schon oben erstellt
    # Globale Instanz für GamepadController (gamepad_ctrl) wird in run_server() verwaltet
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nCtrl+C erkannt. Beende Hauptserver...")
    finally:
        print("Beende alle Komponenten des Hauptservers...")
        if gamepad_ctrl:  # Ist global
            gamepad_ctrl.stop()
        if wheelchair:  # Ist global
            wheelchair.shutdown()

        if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
            publisher_socket_to_ml.close(linger=0)
        if subscriber_socket_from_ml and not subscriber_socket_from_ml.closed:
            subscriber_socket_from_ml.close(linger=0)

        if context and not context.closed:
            print("Schließe globalen ZeroMQ-Kontext.")
            context.term()
        print("Hauptserver beendet.")

