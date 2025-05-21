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
from WheelchairControlReal import WheelchairControlReal  # Dein Import
import os

# --- NEU: Import für GamepadController ---
try:
    from gamepad_controller import GamepadController  # Annahme: gamepad_controller.py ist im selben Verzeichnis
except ImportError as e:
    print(f"Fehler: gamepad_controller.py nicht gefunden: {e}", file=sys.stderr)
    GamepadController = None  # Ermöglicht Start auch ohne Gamepad-Modul
    print("WARNUNG: Gamepad-Steuerung wird nicht verfügbar sein.")
# --- ENDE NEU ---

# --- Konstanten (aus deinem Skript) ---
HEARTBEAT_INTERVAL = 2  # Sekunden (Heartbeat-Intervall vom *Client*)
RECONNECT_INTERVAL = 10  # Sekunden (Wartezeit vor Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)
BROADCAST_PORT = 50000  # Port für UDP-Broadcast (optional)

# --- ZeroMQ-Kontext erstellen (aus deinem Skript) ---
context = zmq.Context()

# --- Globale Variablen (aus deinem Skript) ---
magic_leap_ip = None
last_heartbeat = 0  # Zeit des letzten empfangenen Heartbeats von ML2
publisher_socket = None
subscriber_socket = None
try:
    wheelchair = WheelchairControlReal()  # Deine globale Instanz
except Exception as e_wc_global:
    print(f"FATAL: Globale Initialisierung von WheelchairControlReal fehlgeschlagen: {e_wc_global}", file=sys.stderr)
    sys.exit(1)

# --- NEU: Globale Instanz für GamepadController ---
gamepad_ctrl: GamepadController | None = None
# --- ENDE NEU ---

# --- Globale Variablen für ML2 Konfig-Senden (aus deinem Skript) ---
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"
last_config_send_time = 0
JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"
# NEU: Trigger-Datei für Gamepad-Modus (falls du es später vom Webinterface steuern willst)
GAMEPAD_MODE_TRIGGER_FILE = "/tmp/gamepad_mode_trigger.txt"
gamepad_control_is_active_by_trigger = False  # Gesteuert durch Webinterface-Trigger (optional)


# --- Deine bestehenden Funktionen (is_little_endian, etc.) ---
def is_little_endian():
    return sys.byteorder == 'little'


def to_network_order(value, data_type):
    if data_type == 'i':
        if is_little_endian(): return struct.pack('>i', value)
        return struct.pack('i', value)
    elif data_type == 'f':
        if is_little_endian(): return struct.pack('>f', value)
        return struct.pack('f', value)
    elif data_type == 'd':
        if is_little_endian(): return struct.pack('>d', value)
        return struct.pack('d', value)
    elif data_type == '?':
        return struct.pack('?', value)
    else:
        raise ValueError(f"Ungültiger Datentyp: {data_type}")


def from_network_order(data, data_type):
    if data_type == 'i':
        if is_little_endian(): return struct.unpack('>i', data)[0]
        return struct.unpack('i', data)[0]
    elif data_type == 'f':
        if is_little_endian(): return struct.unpack('>f', data)[0]
        return struct.unpack('f', data)[0]
    elif data_type == 'd':
        if is_little_endian(): return struct.unpack('>d', data)[0]
        return struct.unpack('d', data)[0]
    elif data_type == '?':
        return struct.unpack('?', data)[0]
    else:
        raise ValueError(f"Ungültiger Datentyp: {data_type}")


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
        print("Fehler: 'netifaces' nicht gefunden.", file=sys.stderr); return None
    except Exception as e:
        print(f"Unerwarteter Fehler in get_correct_network_interface: {e}", file=sys.stderr); return None


def get_magic_leap_ip_adb():  # Deine ursprüngliche, funktionierende Version
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


def send_pc_ip_and_port(magic_leap_ip, port):  # Deine ursprüngliche Version
    try:
        correct_interface_ip = get_correct_network_interface(magic_leap_ip)
        if not correct_interface_ip:
            print("Keine passende Netzwerkschnittstelle gefunden.")
            return False
        temp_file = "pc_ip.txt"  # Dein Originalname
        with open(temp_file, "w") as f:
            f.write(f"{correct_interface_ip}:{port}")
        target_path_on_ml = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files'  # Dein Originalpfad
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

# --- NEU: Funktion zum Verarbeiten des Gamepad-Modus-Triggers ---
def process_gamepad_mode_trigger():
    global gamepad_ctrl, gamepad_control_is_active_by_trigger, wheelchair

    if os.path.exists(GAMEPAD_MODE_TRIGGER_FILE):
        try:
            with open(GAMEPAD_MODE_TRIGGER_FILE, "r") as f:
                content = f.read().strip()
            command_part = content.split(":")[0]

            if command_part == "ENABLE_GAMEPAD":
                if GamepadController and (gamepad_ctrl is None or gamepad_ctrl.quit_event.is_set()):
                    print("[ZMQ-Server] Aktiviere Gamepad-Steuerung via Trigger...")
                    gamepad_ctrl = GamepadController(wheelchair)
                    if not gamepad_ctrl.start():
                        print("[ZMQ-Server] WARNUNG: GamepadController konnte nicht gestartet werden.", file=sys.stderr)
                        gamepad_ctrl = None
                        gamepad_control_is_active_by_trigger = False
                    else:
                        print("[ZMQ-Server] GamepadController erfolgreich gestartet.")
                        gamepad_control_is_active_by_trigger = True
                elif gamepad_ctrl and not gamepad_ctrl.quit_event.is_set():
                    print("[ZMQ-Server] Gamepad-Steuerung ist bereits aktiv.")
                    gamepad_control_is_active_by_trigger = True
                else:
                    print("[ZMQ-Server] GamepadController Modul nicht geladen, kann nicht aktiviert werden.")
                    gamepad_control_is_active_by_trigger = False

            elif command_part == "DISABLE_GAMEPAD":
                if gamepad_ctrl and not gamepad_ctrl.quit_event.is_set():
                    print("[ZMQ-Server] Deaktiviere Gamepad-Steuerung via Trigger...")
                    gamepad_ctrl.stop()
                    gamepad_ctrl = None
                    print("[ZMQ-Server] GamepadController gestoppt.")
                gamepad_control_is_active_by_trigger = False

            os.remove(GAMEPAD_MODE_TRIGGER_FILE)
            print(
                f"[ZMQ-Server] Gamepad-Modus-Trigger verarbeitet. Web-Schalter-Status: {'AN' if gamepad_control_is_active_by_trigger else 'AUS'}")
            # Sende den neuen Status an die ML2, damit sie es ggf. anzeigen kann
            if publisher_socket and not publisher_socket.closed:
                publisher_socket.send_multipart(
                    [b"gamepad_status", to_network_order(gamepad_control_is_active_by_trigger, '?')])


        except Exception as e_gp_trigger:
            print(f"[ZMQ-Server] Fehler Verarbeitung Gamepad-Modus-Trigger: {e_gp_trigger}", file=sys.stderr)


# --- ENDE NEU ---


def run_server():
    """Hauptfunktion des Servers."""
    global magic_leap_ip, last_heartbeat, publisher_socket, subscriber_socket
    global wheelchair, gamepad_ctrl, last_config_send_time, gamepad_control_is_active_by_trigger  # Globale Variablen

    # GamepadController wird jetzt durch process_gamepad_mode_trigger() initialisiert/gestoppt,
    # das zu Beginn jeder äußeren Schleife und in der inneren Schleife aufgerufen wird.

    while True:  # Äußere Schleife für Server-Neustart
        print("Server wird (neu)gestartet...")
        # Lokale Socket-Variablen für diesen Durchlauf, um globale nicht zu früh zu ändern
        current_local_subscriber_socket = None
        current_local_publisher_socket = None
        pc_port = None

        process_gamepad_mode_trigger()  # Prüfe Web-Interface Wunsch für Gamepad

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip:
            print("Konnte Magic Leap IP nicht ermitteln. Warte 5 Sekunden...")
            time.sleep(5);
            continue
        pc_ip = get_correct_network_interface(magic_leap_ip)
        if not pc_ip:
            print("Konnte eigene IP-Adresse nicht ermitteln. Warte 5 Sekunden...")
            time.sleep(5);
            continue

        try:
            current_local_publisher_socket = context.socket(zmq.PUB)
            pc_port = current_local_publisher_socket.bind_to_random_port(f"tcp://{pc_ip}")
            publisher_socket = current_local_publisher_socket  # Globale Variable setzen
            print(f"Publisher Socket (PC) gebunden an {pc_ip}:{pc_port}")

            current_local_subscriber_socket = context.socket(zmq.SUB)
            # INITIAL_CONNECTION_TIMEOUT aus deinen Konstanten
            current_local_subscriber_socket.setsockopt(zmq.RCVTIMEO, INITIAL_CONNECTION_TIMEOUT * 1000)
            subscriber_socket = current_local_subscriber_socket  # Globale Variable setzen

            if not send_pc_ip_and_port(magic_leap_ip, pc_port):
                print("Konnte PC-IP und Port nicht an Magic Leap senden. Setze fort...")
        except zmq.ZMQError as e:
            print(f"Socket-Fehler: {e}")
            if current_local_subscriber_socket: current_local_subscriber_socket.close(linger=0)
            if current_local_publisher_socket:  current_local_publisher_socket.close(linger=0)
            publisher_socket = None;
            subscriber_socket = None
            time.sleep(RECONNECT_INTERVAL);
            continue
        except Exception as e_setup:
            print(f"Allgemeiner Fehler im Socket Setup: {e_setup}")
            if current_local_subscriber_socket: current_local_subscriber_socket.close(linger=0)
            if current_local_publisher_socket:  current_local_publisher_socket.close(linger=0)
            publisher_socket = None;
            subscriber_socket = None
            time.sleep(RECONNECT_INTERVAL);
            continue

        print("Warte auf READY-Signal von ML2...")
        ready_received = False
        try:
            subscriber_socket.connect(f"tcp://{magic_leap_ip}:{pc_port + 1}")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
            topic, message = subscriber_socket.recv_multipart()
            if topic == b"READY":
                print("READY empfangen!")
                subscriber_socket.setsockopt(zmq.UNSUBSCRIBE, b"READY")  # Wichtig
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")

                # Sende initiale Zustände an ML2
                publisher_socket.send_multipart([b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])
                publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                publisher_socket.send_multipart([b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                # Sende initialen Gamepad-Status (basierend auf Trigger-Datei)
                publisher_socket.send_multipart(
                    [b"gamepad_status", to_network_order(gamepad_control_is_active_by_trigger, '?')])

                ready_received = True
                print(f"Subscriber (PC) verbunden mit ML2 an {magic_leap_ip}:{pc_port + 1}")
                subscriber_socket.setsockopt(zmq.RCVTIMEO, 1000)  # Kürzerer Timeout für Hauptschleife
        except zmq.error.Again:
            print("Timeout beim Warten auf READY von ML2.")
        except zmq.ZMQError as e:
            print(f"Fehler beim Warten/Verbinden (ZMQ): {e}")
        except Exception as e_ready:
            print(f"Unerwarteter Fehler im READY-Block: {e_ready}")

        if not ready_received:
            print("Setup der ML2-Verbindung nicht erfolgreich, starte ZMQ-Teil neu...")
            if subscriber_socket: subscriber_socket.close(linger=0); subscriber_socket = None
            if publisher_socket:  publisher_socket.close(linger=0);  publisher_socket = None
            time.sleep(RECONNECT_INTERVAL);
            continue

        print("Beginne mit der Hauptkommunikation...")
        last_heartbeat = time.time()  # Zeit des letzten *empfangenen* Heartbeats von ML2
        # float_value = 0 # Nicht mehr global benötigt, wird in Schleife deklariert
        last_heartbeat_send_to_ml = 0  # Zeit des letzten Sendens AN ML2
        # last_rlink_heartbeat_send = time.time() # Wird jetzt vom GamepadController ODER hier gehandhabt
        # HEARTBEAT_INTERVAL_RLINK = 0.2 # Wird jetzt vom GamepadController ODER hier gehandhabt

        # --- NEU: Letzte Joystick-Werte von ML2 speichern ---
        current_ml_x = 0.0
        current_ml_y = 0.0
        # --- ENDE NEU ---

        while True:  # Hauptkommunikationsschleife
            try:
                current_time = time.time()
                process_gamepad_mode_trigger()  # Prüfe Web-Interface Wunsch für Gamepad auch hier

                # --- Heartbeat AN ML2 senden (dein Originalcode) ---
                if current_time - last_heartbeat_send_to_ml > HEARTBEAT_INTERVAL:  # Nutze dein HEARTBEAT_INTERVAL
                    if publisher_socket and not publisher_socket.closed:
                        publisher_socket.send_multipart([b"heartbeat", b""])
                    last_heartbeat_send_to_ml = current_time

                # --- Heartbeat ZUM Rollstuhl(RLink) ---
                # Wird vom GamepadController gesendet, wenn dieser aktiv ist.
                # Ansonsten hier senden, um die Verbindung aufrechtzuerhalten.
                gamepad_is_currently_active = gamepad_ctrl and not gamepad_ctrl.quit_event.is_set()
                if wheelchair and hasattr(wheelchair, 'heartbeat'):
                    if not gamepad_is_currently_active or not gamepad_control_is_active_by_trigger:
                        print("DEBUG: Server.py sendet RLink Heartbeat") # Für Debugging
                        wheelchair.heartbeat()

                # --- Trigger-Dateien für andere Befehle prüfen (dein Originalcode) ---
                if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                    try:
                        print(f"Trigger-Datei '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                        if publisher_socket and not publisher_socket.closed:
                            print("Sende 'joystick_toggle_visibility' an ML2...")
                            publisher_socket.send_multipart(
                                [b"joystick_toggle_visibility", b"toggle"])  # b"" oder b"toggle"
                        else:
                            print("Fehler: ZMQ Publisher-Socket nicht bereit für Joystick-Toggle.", file=sys.stderr)
                        try:
                            os.remove(JOYSTICK_VISIBILITY_TRIGGER_FILE)
                        except OSError as e_rem:
                            print(f"Fehler Löschen Trigger '{JOYSTICK_VISIBILITY_TRIGGER_FILE}': {e_rem}",
                                  file=sys.stderr)
                    except Exception as e_trig:
                        print(f"Fehler Verarbeitung Joystick-Sichtbarkeit-Trigger: {e_trig}", file=sys.stderr)

                if os.path.exists(CONFIG_TRIGGER_FILE):
                    try:
                        trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                        if trigger_timestamp > last_config_send_time:
                            with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                config_json_str = f.read()
                            if config_json_str and publisher_socket and not publisher_socket.closed:
                                print(f"Sende ML2 Joystick Konfiguration (Trigger, Länge: {len(config_json_str)})...")
                                publisher_socket.send_multipart([b"joystick_settings", config_json_str.encode('utf-8')])
                                last_config_send_time = trigger_timestamp
                            try:
                                os.remove(CONFIG_TRIGGER_FILE)
                            except OSError as e_rem:
                                print(f"Fehler Löschen Trigger '{CONFIG_TRIGGER_FILE}': {e_rem}", file=sys.stderr)
                    except Exception as e_config:
                        print(f"Fehler Lesen/Senden ML2 Joystick Konfiguration: {e_config}", file=sys.stderr)

                # --- Daten an ML2 senden (Geschwindigkeit - dein Originalcode) ---
                if publisher_socket and not publisher_socket.closed:
                    speed = wheelchair.get_wheelchair_speed()
                    float_value_bytes = to_network_order(speed, 'f')  # Benenne Variable um, um Konflikt zu vermeiden
                    publisher_socket.send_multipart([b"topic_float", float_value_bytes])

                # --- Nachrichten von ML2 empfangen (dein Originalcode, leicht angepasst) ---
                ml_joystick_command_received_this_cycle = False
                try:
                    if subscriber_socket and not subscriber_socket.closed and subscriber_socket.poll(
                            timeout=10):  # Kurzer Poll
                        topic, message = subscriber_socket.recv_multipart()

                        if topic == b"heartbeat":
                            last_heartbeat = time.time()  # Zeit des letzten EMPFANGENEN Heartbeats
                            # print("Heartbeat von ML2 empfangen") # Optional
                        elif topic == b"joystickPos":
                            x = from_network_order(message[0:4], 'f')
                            y = from_network_order(message[4:8], 'f')
                            current_ml_x = x  # Aktualisiere immer die zuletzt bekannten ML2-Werte
                            current_ml_y = y
                            ml_joystick_command_received_this_cycle = True
                            wheelchair.set_direction((current_ml_x, current_ml_y))
                        elif topic == b"gear":
                            received_value = from_network_order(message, '?')
                            actual_gear = wheelchair.set_gear(received_value)
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"gear", to_network_order(actual_gear, 'i')])
                        elif topic == b"lights":
                            received_value = from_network_order(message, '?')  # Wert von ML2 ist nur Trigger
                            wheelchair.set_lights()  # Methode toggelt intern
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"lights", to_network_order(wheelchair.get_lights(), '?')])
                        elif topic == b"warn":
                            received_value = from_network_order(message, '?')
                            wheelchair.set_warn()
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"warn", to_network_order(wheelchair.get_warn(), '?')])
                        elif topic == b"horn":
                            received_value = from_network_order(message, '?')
                            wheelchair.on_horn(received_value)
                        elif topic == b"kantelung":
                            received_value = from_network_order(message, '?')
                            wheelchair.on_kantelung(received_value)
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                        else:
                            print(f"Unerwartetes Topic von ML2: {topic}")
                except zmq.error.Again:
                    pass  # Timeout beim Pollen ist normal

                # --- STEUERLOGIK ---
                # Wenn der Gamepad-Modus über das Webinterface AKTIVIERT ist
                # UND der GamepadController tatsächlich läuft (nicht None und quit_event nicht gesetzt),
                # dann hat das Gamepad die Steuerung (seine Threads senden die Befehle).
                # Ansonsten steuert die ML2.
                #gamepad_is_currently_active_and_controlling = gamepad_ctrl and not gamepad_ctrl.quit_event.is_set()

                '''if not gamepad_control_is_active_by_trigger or not gamepad_is_currently_active:
                    # Gamepad ist NICHT aktiv oder NICHT vom Web gewünscht -> ML2 steuert
                    # Sende die zuletzt bekannten/aktuellen ML2-Werte kontinuierlich
                    # print(f"DEBUG: ML2 steuert mit ({current_ml_x}, {current_ml_y})")
                    wheelchair.set_direction((current_ml_x, current_ml_y))'''
                # else:
                # print("DEBUG: Gamepad steuert (oder sollte steuern).")
                # Gamepad ist aktiv und vom Webinterface gewünscht.
                # Der GamepadController.py sendet die Befehle in seinem eigenen Thread.
                # Hier muss nichts für set_direction getan werden.

                # --- Heartbeat-Timeout-Überprüfung (von ML2) ---
                if time.time() - last_heartbeat > RECONNECT_INTERVAL:  # Dein RECONNECT_INTERVAL
                    print("Heartbeat-Timeout von ML2!")
                    break  # Beende die innere Kommunikationsschleife -> führt zu ZMQ-Neustart

                # --- Prüfen, ob Gamepad-Controller (falls er mal lief) vom Benutzer am Gamepad beendet wurde ---
                if gamepad_control_is_active_by_trigger and gamepad_is_currently_active and gamepad_ctrl.quit_event.is_set():
                    print("[ZMQ-Server] Gamepad-Controller wurde vom Benutzer am Gamepad beendet.")
                    gamepad_ctrl.stop()
                    gamepad_ctrl = None
                    gamepad_control_is_active_by_trigger = False  # Web-Schalter auch zurücksetzen
                    if publisher_socket and not publisher_socket.closed:  # Informiere ML2
                        publisher_socket.send_multipart([b"gamepad_status", to_network_order(False, '?')])
                    # Kein break hier, ML2 soll weiterlaufen können

                time.sleep(0.01)  # Sehr kurze Pause, um CPU zu schonen

            except zmq.ZMQError as e:
                print(f"Fehler in der ZMQ-Kommunikation: {e}")
                break
            except Exception as e:
                print(f"Unerwarteter Fehler in der Hauptschleife: {e}")
                import traceback;
                traceback.print_exc()
                break

        # --- Aufräumen vor ZMQ-Neustart ---
        print("ZMQ Kommunikationsschleife beendet. Starte ZMQ-Teil neu...")
        if subscriber_socket: subscriber_socket.close(linger=0); subscriber_socket = None
        if publisher_socket:  publisher_socket.close(linger=0);  publisher_socket = None
        time.sleep(RECONNECT_INTERVAL)


# --- Programmstart ---
if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nCtrl+C erkannt. Beende Hauptserver...")
    finally:
        print("Beende alle Komponenten des Hauptservers...")
        if gamepad_ctrl:  # gamepad_ctrl ist global
            gamepad_ctrl.stop()
        if wheelchair:  # wheelchair ist global
            wheelchair.shutdown()

        # Globale Sockets hier schließen, da sie in der Schleife neu zugewiesen werden
        if publisher_socket and not publisher_socket.closed:
            print("Schließe globalen Publisher Socket...")
            publisher_socket.close(linger=0)
        if subscriber_socket and not subscriber_socket.closed:
            print("Schließe globalen Subscriber Socket...")
            subscriber_socket.close(linger=0)

        if context and not context.closed:
            print("Schließe globalen ZeroMQ-Kontext.")
            context.term()
        print("Hauptserver beendet.")
