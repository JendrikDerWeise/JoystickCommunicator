#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket  # Für UDP-Broadcast
import random
import struct
# Importiere WheelchairControlReal so, wie es in deinem Skript war
from WheelchairControlReal import WheelchairControlReal  # Annahme: Diese Klasse enthält die Logik
import os

# --- NEU: Import für GamepadController ---
try:
    from gamepad_controller import GamepadController
except ImportError as e:
    print(f"Fehler: gamepad_controller.py nicht gefunden oder Inhalt fehlerhaft: {e}", file=sys.stderr)
    GamepadController = None
    print("WARNUNG: Gamepad-Steuerung wird nicht verfügbar sein.")
# --- ENDE NEU ---


# --- Konstanten ---
HEARTBEAT_INTERVAL_TO_ML = 2  # Sekunden (Heartbeat-Intervall AN DEN *Client* ML2)
RECONNECT_INTERVAL_ZMQ = 10  # Sekunden (Wartezeit vor ZMQ-Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()  # Nur einmal global erstellen

# --- Globale Variablen ---
magic_leap_ip = None
publisher_socket_to_ml = None
subscriber_socket_from_ml = None
gamepad_ctrl: GamepadController | None = None

try:
    wheelchair = WheelchairControlReal()
except Exception as e_wc:
    print(f"FATAL: Fehler bei der Initialisierung von WheelchairControlReal: {e_wc}", file=sys.stderr)
    sys.exit(1)

CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"
last_config_send_time = 0
JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"


# --- Deine bestehenden Funktionen (is_little_endian, to_network_order, etc. bleiben unverändert) ---
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


def get_correct_network_interface(magic_leap_ip):
    if not magic_leap_ip: return None
    try:
        magic_leap_subnet = ".".join(magic_leap_ip.split(".")[:3])
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    for ip_info in iface_details[netifaces.AF_INET]:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1' and ".".join(ip_address.split(".")[:3]) == magic_leap_subnet:
                            print(f"Korrekte Schnittstelle gefunden: {interface} ({ip_address})")
                            return ip_address
            except Exception as e:
                print(f"Fehler bei Überprüfung Interface {interface}: {e}", file=sys.stderr)
        print(f"Warnung: Keine passende Schnittstelle im Subnetz von {magic_leap_ip} gefunden.", file=sys.stderr)
        return None
    except NameError:
        print("Fehler: 'netifaces' nicht gefunden. (pip install netifaces)", file=sys.stderr); return None
    except Exception as e:
        print(f"Unerwarteter Fehler in get_correct_network_interface: {e}", file=sys.stderr); return None


def get_magic_leap_ip_adb():
    try:
        start_time = time.time()
        timeout = 10
        while time.time() - start_time < timeout:
            print("Versuche ADB Befehl: adb shell ip route")
            result = subprocess.run(['adb', 'shell', 'ip', 'route'], capture_output=True, text=True, check=True,
                                    timeout=5)
            for line in result.stdout.splitlines():
                if "dev mlnet0" or "eth1" in line:
                    match = re.search(r'src (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                    if match:
                        ip_address = match.group(1)
                        print(f"Magic Leap 2 IP-Adresse (über ip route): {ip_address}")
                        return ip_address
            time.sleep(1)
        print("Timeout beim Ermitteln der IP-Adresse über ADB.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Fehler Ausführung 'adb shell ip route': {e}, Code: {e.returncode}, Output: {e.output}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("Timeout bei Ausführung von 'adb shell ip route'.", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Fehler: 'adb' nicht gefunden. Ist ADB im PATH?", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unerwarteter Fehler bei ADB-IP-Ermittlung: {e}", file=sys.stderr)
        return None


def send_pc_ip_and_port(magic_leap_ip, port):
    try:
        correct_interface_ip = get_correct_network_interface(magic_leap_ip)
        if not correct_interface_ip:
            print("Keine passende Netzwerkschnittstelle gefunden.")
            return False
        temp_file = "pc_ip.txt"
        with open(temp_file, "w") as f:
            f.write(f"{correct_interface_ip}:{port}")
        target_path_on_ml = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files'
        subprocess.run(['adb', 'push', temp_file, target_path_on_ml], check=True, timeout=10)
        print(
            f"PC IP-Adresse ({correct_interface_ip}) und Port ({port}) auf Magic Leap 2 kopiert nach {target_path_on_ml}/{temp_file}.")
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Kopieren der Datei (adb push): {e}", file=sys.stderr)
        if hasattr(e, 'stderr') and e.stderr: print(f"ADB Stderr: {e.stderr}", file=sys.stderr)
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False
    except FileNotFoundError:
        print("Fehler: 'adb' nicht gefunden.", file=sys.stderr)
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False
    except Exception as e:
        print(f"Fehler beim Schreiben/Kopieren der IP-Adresse und des Ports: {e}", file=sys.stderr)
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False


# --- Ende deiner bestehenden Funktionen ---

def run_server():
    global magic_leap_ip, last_heartbeat_from_ml, publisher_socket_to_ml, subscriber_socket_from_ml
    global wheelchair
    global gamepad_ctrl
    global last_config_send_time
    global context

    if GamepadController and gamepad_ctrl is None:
        try:
            print("Initialisiere GamepadController...")
            gamepad_ctrl = GamepadController(wheelchair)
            if not gamepad_ctrl.start():
                print("WARNUNG: GamepadController konnte nicht gestartet werden.", file=sys.stderr)
                gamepad_ctrl = None
            else:
                print("GamepadController erfolgreich gestartet.")
        except Exception as e_gp:
            print(f"FEHLER bei Initialisierung des GamepadControllers: {e_gp}", file=sys.stderr)
            gamepad_ctrl = None

    while True:
        print("\n" + "=" * 30 + " ZMQ-SERVERTEIL (NEU)START " + "=" * 30)
        current_publisher_socket = None
        current_subscriber_socket = None
        pc_port_for_ml = None

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip:
            print(f"Konnte ML2 IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        pc_ip_for_ml = get_correct_network_interface(magic_leap_ip)
        if not pc_ip_for_ml:
            print(f"Konnte eigene passende IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        try:
            current_publisher_socket = context.socket(zmq.PUB)
            pc_port_for_ml = current_publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_ml}")
            publisher_socket_to_ml = current_publisher_socket
            print(f"ZMQ Publisher (an ML2) gebunden an tcp://{pc_ip_for_ml}:{pc_port_for_ml}")

            current_subscriber_socket = context.socket(zmq.SUB)
            current_subscriber_socket.setsockopt(zmq.RCVTIMEO, INITIAL_CONNECTION_TIMEOUT * 1000)
            subscriber_socket_from_ml = current_subscriber_socket

            send_pc_ip_and_port(magic_leap_ip, pc_port_for_ml)
        except Exception as e:
            print(f"Fehler im ZMQ Socket Setup: {e}", file=sys.stderr)
            if current_publisher_socket: current_publisher_socket.close(linger=0)
            if current_subscriber_socket: current_subscriber_socket.close(linger=0)
            publisher_socket_to_ml = None;
            subscriber_socket_from_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        print(f"Warte auf READY von ML2 an tcp://{magic_leap_ip}:{pc_port_for_ml + 1}...")
        ready_received = False
        try:
            subscriber_socket_from_ml.connect(f"tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
            subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"READY")
            topic, _ = subscriber_socket_from_ml.recv_multipart()
            if topic == b"READY":
                print("READY von ML2 empfangen!")
                subscriber_socket_from_ml.setsockopt(zmq.UNSUBSCRIBE, b"READY")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"gear")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"lights")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"warn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"horn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"kantelung")
                ready_received = True
                print(f"ZMQ Subscriber (von ML2) verbunden mit tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
                subscriber_socket_from_ml.setsockopt(zmq.RCVTIMEO, 1000)

                if publisher_socket_to_ml and wheelchair:
                    publisher_socket_to_ml.send_multipart(
                        [b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])
                    publisher_socket_to_ml.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                    publisher_socket_to_ml.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                    publisher_socket_to_ml.send_multipart(
                        [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    if gamepad_ctrl and hasattr(gamepad_ctrl, '_gp_height_active'):
                        publisher_socket_to_ml.send_multipart(
                            [b"height_mode", to_network_order(gamepad_ctrl._gp_height_active, '?')])
        except zmq.error.Again:
            print("Timeout beim Warten auf READY von ML2.")
        except Exception as e:
            print(f"Fehler beim Warten auf READY: {e}", file=sys.stderr)

        if not ready_received:
            print("Setup der ML2-Verbindung nicht erfolgreich, starte ZMQ-Teil neu...")
            if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
            if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ);
            continue

        print("Beginne Hauptkommunikation mit ML2...")
        last_heartbeat_from_ml = time.time()
        last_heartbeat_send_to_ml = 0
        current_ml_x = 0.0
        current_ml_y = 0.0

        while True:  # Innere ZMQ-Kommunikationsschleife
            try:
                current_time = time.time()
                # --- Heartbeat AN ML2 senden ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed and \
                        current_time - last_heartbeat_send_to_ml > HEARTBEAT_INTERVAL_TO_ML:
                    publisher_socket_to_ml.send_multipart([b"heartbeat", b""])
                    last_heartbeat_send_to_ml = current_time

                # --- Trigger-Dateien prüfen ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                    if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                        try:
                            print(f"Trigger '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                            publisher_socket_to_ml.send_multipart([b"joystick_toggle_visibility", b"toggle"])
                            print(f"-> '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' an ML2 gesendet.")
                            os.remove(JOYSTICK_VISIBILITY_TRIGGER_FILE)
                        except Exception as e_trig_vis:
                            print(f"Fehler Trigger JoystickVis: {e_trig_vis}", file=sys.stderr)
                    if os.path.exists(CONFIG_TRIGGER_FILE):
                        try:
                            trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                            if trigger_timestamp > last_config_send_time:
                                with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                    config_json_str = f.read()
                                if config_json_str:
                                    print(f"Sende ML2 Joystick Konfiguration (Trigger)...")
                                    publisher_socket_to_ml.send_multipart(
                                        [b"joystick_settings", config_json_str.encode('utf-8')])
                                    last_config_send_time = trigger_timestamp
                                os.remove(CONFIG_TRIGGER_FILE)
                        except Exception as e_cfg_trig:
                            print(f"Fehler Trigger Config: {e_cfg_trig}", file=sys.stderr)

                # --- Daten an ML2 senden (Geschwindigkeit) ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                    if wheelchair:
                        speed = wheelchair.get_wheelchair_speed()
                        float_value = to_network_order(speed, 'f')
                        publisher_socket_to_ml.send_multipart([b"topic_float", float_value])

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
                            # Der wheelchair.set_direction Aufruf für ML2 erfolgt jetzt
                            # im Steuerlogik-Block unten, wenn KEIN Gamepad aktiv ist.
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
                                wheelchair.on_kantelung(received_value)
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                        else:
                            print(f"Unbekanntes Topic von ML2: {topic}")
                except zmq.error.Again:
                    pass

                # --- STEUERLOGIK UND RLINK HEARTBEAT ---
                gamepad_is_active_and_controlling = gamepad_ctrl and not gamepad_ctrl.quit_event.is_set()

                if wheelchair:
                    # RLink Heartbeat IMMER senden, wenn wheelchair existiert
                    if hasattr(wheelchair, 'heartbeat'):
                        wheelchair.heartbeat()  # Dies ist die Methode aus WheelchairControlReal

                    # Wenn KEIN Gamepad aktiv ist, verwende die zuletzt von ML2
                    # empfangenen Joystick-Werte (oder 0,0 initial).
                    # Dieser Block sendet nun kontinuierlich.
                    if not gamepad_is_active_and_controlling:
                        # print(f"DEBUG: ML2-Only - Sende ({current_ml_x}, {current_ml_y}) an RLink") # DEBUG
                        wheelchair.set_direction((current_ml_x, current_ml_y))
                    # Wenn das Gamepad aktiv ist, sendet der GamepadController.py
                    # in seinem eigenen Thread wheelchair.set_direction() und wheelchair.heartbeat().
                    # Der letzte Befehl an wheelchair.set_direction() "gewinnt" durch die häufigen Aufrufe.
                # --- ENDE STEUERLOGIK ---

                if time.time() - last_heartbeat_from_ml > RECONNECT_INTERVAL_ZMQ:
                    print("Heartbeat-Timeout von ML2!")
                    break
                if gamepad_ctrl and gamepad_ctrl.quit_event.is_set():
                    print("Gamepad-Controller hat Beenden signalisiert. Starte ZMQ-Teil neu.")
                    gamepad_ctrl.stop()
                    gamepad_ctrl = None
                    break
                time.sleep(0.01)
            except zmq.ZMQError as e:
                print(f"Fehler in der ZMQ-Kommunikation: {e}"); break
            except Exception as e:
                print(f"Unerwarteter Fehler in der Hauptschleife: {e}"); import traceback; traceback.print_exc(); break

        print("ZMQ Kommunikationsschleife beendet. Starte ZMQ-Teil neu...")
        if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
        if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
        time.sleep(RECONNECT_INTERVAL_ZMQ)


# --- Programmstart ---
if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nCtrl+C erkannt. Beende Hauptserver...")
    finally:
        print("Beende alle Komponenten des Hauptservers...")
        if gamepad_ctrl:
            gamepad_ctrl.stop()
        if wheelchair:
            wheelchair.shutdown()

        if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
            print("Schließe globalen Publisher Socket...")
            publisher_socket_to_ml.close(linger=0)
        if subscriber_socket_from_ml and not subscriber_socket_from_ml.closed:
            print("Schließe globalen Subscriber Socket...")
            subscriber_socket_from_ml.close(linger=0)

        if context and not context.closed:
            print("Schließe globalen ZeroMQ-Kontext.")
            context.term()
        print("Hauptserver beendet.")

