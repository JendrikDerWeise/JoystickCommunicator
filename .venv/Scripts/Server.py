#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket
import random  # Für alte get_wheelchair_speed, falls noch irgendwo referenziert
import struct
import os  # Für os.path.exists, os.remove

# Importiere deine Module
try:
    from WheelchairControlReal import WheelchairControlReal, RLinkError
except ImportError as e:
    print(f"Fehler: wheelchair_control_module.py nicht gefunden oder Inhalt fehlerhaft: {e}", file=sys.stderr)
    sys.exit(1)

try:
    from gamepad_controller import GamepadController
except ImportError as e:
    print(f"Fehler: gamepad_controller.py nicht gefunden oder Inhalt fehlerhaft: {e}", file=sys.stderr)
    sys.exit(1)

# --- Konstanten ---
HEARTBEAT_INTERVAL_ML = 2  # Sekunden (Heartbeat-Intervall vom *Client* ML2)
RECONNECT_INTERVAL_ZMQ = 10  # Sekunden (Wartezeit vor ZMQ-Server-Neustart)
# INITIAL_CONNECTION_TIMEOUT = 30 # Wird jetzt im ZMQ-Socket direkt gesetzt
# BROADCAST_PORT = 50000 # Unverändert, falls genutzt

# --- ZeroMQ-Kontext erstellen (global) ---
context = zmq.Context.instance()  # Globale Instanz verwenden

# --- Globale Variablen (mit Bedacht verwenden!) ---
magic_leap_ip = None
# Die folgenden Sockets werden in run_server() verwaltet
publisher_socket_to_ml = None  # Socket zum Senden an die Magic Leap
subscriber_socket_from_ml = None  # Socket zum Empfangen von der Magic Leap

# Instanzen für Rollstuhl und Gamepad (werden in run_server initialisiert)
wc_instance: WheelchairControlReal | None = None
gamepad_ctrl: GamepadController | None = None

# --- Trigger-Dateien (wie in deinem Flask-Server) ---
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"  # Für ML2 Joystick-Einstellungen
JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"
last_config_send_time = 0


# --- Netzwerk- und Konvertierungsfunktionen (unverändert) ---
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
                            print(
                                f"Korrekte Netzwerkschnittstelle für Subnetz {target_subnet} gefunden: {interface} ({ip_address})")
                            return ip_address
            except Exception:
                pass  # Ignoriere Fehler bei einzelnen Interfaces
        print(f"Warnung: Keine passende Netzwerkschnittstelle im Subnetz von {target_ip_for_subnet_check} gefunden.",
              file=sys.stderr)
        return None
    except NameError:
        print("Fehler: 'netifaces' nicht gefunden. (pip install netifaces)", file=sys.stderr); return None
    except Exception as e:
        print(f"Fehler in get_correct_network_interface: {e}", file=sys.stderr); return None


def get_magic_leap_ip_adb():
    adb_command = ['adb', 'shell', 'ip', 'addr']
    try:
        start_time = time.time();
        timeout = 15
        while time.time() - start_time < timeout:
            print(f"Versuche ADB Befehl: {' '.join(adb_command)}")
            try:
                result = subprocess.run(adb_command, capture_output=True, text=True, check=True, timeout=5)
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        ip_address = line.split()[1].split('/')[0]
                        # Annahme: ML2 USB-Netzwerk ist oft ein spezifisches Subnetz
                        # Du hattest 192.168.42.x, das ist gut für die Unterscheidung
                        if ip_address.startswith("192.168.42.") or ip_address.startswith(
                                "192.168.168."):  # Oder andere bekannte ML2 Subnetze
                            print(f"Magic Leap 2 IP-Adresse gefunden: {ip_address}")
                            return ip_address
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                print(f"ADB-Fehler oder Timeout: {e}", file=sys.stderr)
            except FileNotFoundError:
                print("Fehler: 'adb.exe' nicht gefunden. Ist ADB im PATH?", file=sys.stderr);
                return None
            print("Warte 1s vor nächstem ADB Versuch...")
            time.sleep(1)
        print(f"Timeout ({timeout}s) beim Ermitteln der ML2 IP über ADB.");
        return None
    except Exception as e:
        print(f"Genereller Fehler bei ADB-IP-Ermittlung: {e}", file=sys.stderr); return None


def send_pc_ip_and_port_to_ml(ml_ip, pc_ip_for_ml, port_for_ml):
    # ... (Deine bestehende Funktion, stelle sicher, dass sie robust ist) ...
    # Wichtig: Diese Funktion wird jetzt nur einmal pro ZMQ-Server-Neustart aufgerufen.
    if not pc_ip_for_ml:
        print("Fehler: Keine PC-IP zum Senden an ML2 vorhanden.", file=sys.stderr)
        return False
    temp_file = "pc_ip_port.txt"  # Eindeutigerer Name
    target_path_on_ml = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/'  # Nur Verzeichnis!
    adb_command = ['adb', 'push', temp_file, target_path_on_ml]
    try:
        with open(temp_file, "w") as f:
            f.write(f"{pc_ip_for_ml}:{port_for_ml}")
        print(f"Versuche: {' '.join(adb_command)}")
        subprocess.run(adb_command, check=True, capture_output=True, timeout=10)
        print(f"PC IP ({pc_ip_for_ml}) und Port ({port_for_ml}) auf ML2 kopiert nach {target_path_on_ml}{temp_file}.")
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return True
    except Exception as e:
        print(f"Fehler beim Senden der PC IP/Port an ML2: {e}", file=sys.stderr)
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False


# --- Hauptfunktion des ZMQ-Servers ---
def run_server():
    global magic_leap_ip, last_heartbeat, publisher_socket_to_ml, subscriber_socket_from_ml
    global wc_instance, gamepad_ctrl, context  # Zugriff auf globale Instanzen
    global last_config_send_time  # Für den Config-Trigger

    # Initialisiere WheelchairControlReal und GamepadController EINMALIG hier
    # (oder außerhalb, wenn run_server mehrmals ohne kompletten Neustart aufgerufen wird)
    # Für dieses Beispiel: Einmalige Initialisierung beim ersten Aufruf von run_server
    if wc_instance is None:
        try:
            print("Initialisiere WheelchairControlReal für den Server...")
            wc_instance = WheelchairControlReal(device_index=0)
        except ConnectionError as e:
            print(f"FEHLER: WheelchairControlReal konnte nicht initialisiert werden: {e}", file=sys.stderr)
            return  # Beendet run_server, wenn Rollstuhl nicht geht
        except Exception as e:
            print(f"Allgemeiner Fehler bei WC Init: {e}", file=sys.stderr)
            return

    if gamepad_ctrl is None:
        try:
            print("Initialisiere GamepadController...")
            gamepad_ctrl = GamepadController(wc_instance)  # Übergib wc_instance
            if not gamepad_ctrl.start():
                print("WARNUNG: GamepadController konnte nicht gestartet werden.", file=sys.stderr)
                gamepad_ctrl = None  # Kein Gamepad, aber Server läuft weiter
            else:
                print("GamepadController erfolgreich gestartet.")
        except Exception as e:
            print(f"FEHLER bei Initialisierung des GamepadControllers: {e}", file=sys.stderr)
            gamepad_ctrl = None

    # --- Äußere Schleife für ZMQ-Server-Neustart (Verbindung zur ML2) ---
    while True:
        print("\n" + "=" * 30 + " ZMQ-SERVERTEIL (NEU)START " + "=" * 30)
        # Sockets für diesen Durchlauf zurücksetzen
        current_publisher_socket = None
        current_subscriber_socket = None
        pc_port_for_ml = None

        # --- IP-Ermittlung und Socket-Setup für ML2 ---
        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip:
            print(f"Konnte ML2 IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ)
            continue

        pc_ip_for_ml = get_correct_network_interface(magic_leap_ip)
        if not pc_ip_for_ml:
            print(f"Konnte eigene passende IP nicht ermitteln. Warte {RECONNECT_INTERVAL_ZMQ}s...")
            time.sleep(RECONNECT_INTERVAL_ZMQ)
            continue

        try:
            current_publisher_socket = context.socket(zmq.PUB)
            pc_port_for_ml = current_publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_ml}")
            publisher_socket_to_ml = current_publisher_socket  # Globalen Socket aktualisieren
            print(f"ZMQ Publisher (an ML2) gebunden an tcp://{pc_ip_for_ml}:{pc_port_for_ml}")

            current_subscriber_socket = context.socket(zmq.SUB)
            current_subscriber_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5s Timeout für recv
            subscriber_socket_from_ml = current_subscriber_socket  # Globalen Socket aktualisieren

            send_pc_ip_and_port_to_ml(magic_leap_ip, pc_ip_for_ml, pc_port_for_ml)

        except Exception as e:
            print(f"Fehler im ZMQ Socket Setup: {e}", file=sys.stderr)
            if current_publisher_socket: current_publisher_socket.close(linger=0)
            if current_subscriber_socket: current_subscriber_socket.close(linger=0)
            publisher_socket_to_ml = None;
            subscriber_socket_from_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ)
            continue

        # --- Warten auf READY von ML2 ---
        print(f"Warte auf READY von ML2 an tcp://{magic_leap_ip}:{pc_port_for_ml + 1}...")
        ready_received = False
        try:
            subscriber_socket_from_ml.connect(f"tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
            subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"READY")

            # Warte auf READY mit Timeout (RCVTIMEO ist gesetzt)
            topic, _ = subscriber_socket_from_ml.recv_multipart()  # Timeout von RCVTIMEO wird hier wirksam
            if topic == b"READY":
                print("READY von ML2 empfangen!")
                subscriber_socket_from_ml.setsockopt(zmq.UNSUBSCRIBE, b"READY")  # Wichtig!
                # Weitere Topics abonnieren
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"gear")  # Für ML-gesteuerte Gangwechsel
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"lights")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"warn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"horn")
                subscriber_socket_from_ml.setsockopt(zmq.SUBSCRIBE, b"kantelung")
                ready_received = True
                print(f"ZMQ Subscriber (von ML2) verbunden mit tcp://{magic_leap_ip}:{pc_port_for_ml + 1}")
                # Initiale Zustände an ML2 senden
                if publisher_socket_to_ml and wc_instance:
                    publisher_socket_to_ml.send_multipart(
                        [b"gear", to_network_order(wc_instance.get_actual_gear(), 'i')])
                    publisher_socket_to_ml.send_multipart([b"lights", to_network_order(wc_instance.get_lights(), '?')])
                    publisher_socket_to_ml.send_multipart([b"warn", to_network_order(wc_instance.get_warn(), '?')])
                    publisher_socket_to_ml.send_multipart(
                        [b"kantelung", to_network_order(wc_instance.get_kantelung(), '?')])
                    if gamepad_ctrl:  # Sende auch Gamepad-Modi, falls aktiv
                        publisher_socket_to_ml.send_multipart(
                            [b"height_mode", to_network_order(gamepad_ctrl._gp_height_active, '?')])


        except zmq.error.Again:  # Timeout
            print("Timeout beim Warten auf READY von ML2.")
        except Exception as e:
            print(f"Fehler beim Warten auf READY: {e}", file=sys.stderr)

        if not ready_received:
            print("Setup der ML2-Verbindung nicht erfolgreich, starte ZMQ-Teil neu...")
            if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
            if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
            time.sleep(RECONNECT_INTERVAL_ZMQ)
            continue  # Neustart der äußeren ZMQ-Schleife

        # --- Hauptkommunikationsschleife (ZMQ mit ML2) ---
        print("Beginne Hauptkommunikation mit ML2...")
        last_heartbeat_received_from_ml = time.time()
        last_status_send_to_ml_time = 0

        while True:  # Innere ZMQ-Kommunikationsschleife
            current_time = time.time()
            try:
                # --- Daten an ML2 senden (z.B. Geschwindigkeit, Status) ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed and \
                        current_time - last_status_send_to_ml_time > 0.5:  # Sende Status alle 0.5s
                    if wc_instance:
                        speed = wc_instance.get_wheelchair_speed()
                        publisher_socket_to_ml.send_multipart([b"topic_float", to_network_order(speed, 'f')])
                        # Weitere Status-Updates an ML2 hier senden, falls nötig
                    last_status_send_to_ml_time = current_time

                # --- Nachrichten von ML2 empfangen ---
                try:
                    if subscriber_socket_from_ml and not subscriber_socket_from_ml.closed and \
                            subscriber_socket_from_ml.poll(timeout=10):  # Kurzer Poll, um nicht zu blockieren
                        topic, message = subscriber_socket_from_ml.recv_multipart()

                        if topic == b"heartbeat":
                            last_heartbeat_received_from_ml = time.time()
                        elif topic == b"joystickPos":
                            # Nur verarbeiten, wenn KEIN Gamepad aktiv ist oder Gamepad Fehler hat
                            if not gamepad_ctrl or gamepad_ctrl.quit_event.is_set():
                                x = from_network_order(message[0:4], 'f')
                                y = from_network_order(message[4:8], 'f')
                                if wc_instance: wc_instance.set_direction((x, y))
                            # else: print("Gamepad aktiv, ignoriere ML2 Joystick.")
                        elif topic == b"gear":
                            if wc_instance:
                                received_value = from_network_order(message, '?')
                                actual_gear = wc_instance.set_gear(received_value)
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"gear", to_network_order(actual_gear, 'i')])
                        elif topic == b"lights":
                            if wc_instance:
                                wc_instance.set_lights()  # Toggle
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"lights", to_network_order(wc_instance.get_lights(), '?')])
                        elif topic == b"warn":
                            if wc_instance:
                                wc_instance.set_warn()  # Toggle
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"warn", to_network_order(wc_instance.get_warn(), '?')])
                        elif topic == b"horn":
                            if wc_instance: wc_instance.on_horn(from_network_order(message, '?'))
                        elif topic == b"kantelung":
                            # ML2 kann den Kantelungsmodus umschalten, wenn Gamepad nicht aktiv
                            if wc_instance and (not gamepad_ctrl or gamepad_ctrl.quit_event.is_set()):
                                received_value = from_network_order(message, '?')
                                wc_instance.on_kantelung(received_value)
                                if publisher_socket_to_ml: publisher_socket_to_ml.send_multipart(
                                    [b"kantelung", to_network_order(wc_instance.get_kantelung(), '?')])
                        else:
                            print(f"Unbekanntes Topic von ML2: {topic}")
                except zmq.error.Again:
                    pass  # Timeout beim Pollen ist normal

                # --- Trigger-Dateien prüfen (für Befehle vom Webinterface) ---
                if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
                    if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                        try:
                            print(f"Trigger '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                            publisher_socket_to_ml.send_multipart([b"joystick_toggle_visibility", b"toggle"])
                            print("-> joystick_toggle_visibility an ML2 gesendet.")
                            os.remove(JOYSTICK_VISIBILITY_TRIGGER_FILE)
                        except Exception as e_trig:
                            print(f"Fehler Trigger JoystickVis: {e_trig}", file=sys.stderr)

                    if os.path.exists(CONFIG_TRIGGER_FILE):  # Für ML2 Joystick Config
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

                # --- Heartbeat-Timeout von ML2 prüfen ---
                if current_time - last_heartbeat_received_from_ml > RECONNECT_INTERVAL_ZMQ * 1.5:
                    print(
                        f"Heartbeat-Timeout von ML2! Letzter Empfang vor {current_time - last_heartbeat_received_from_ml:.1f}s.")
                    break  # Innere Schleife verlassen -> ZMQ-Neustart

                # --- Prüfen, ob Gamepad-Controller beendet wurde ---
                if gamepad_ctrl and gamepad_ctrl.quit_event.is_set():
                    print("Gamepad-Controller hat Beenden signalisiert. Starte ZMQ-Teil neu (oder beende Server).")
                    # Hier könntest du entscheiden, ob der Server ganz stoppt oder nur ZMQ neu startet
                    # und versucht, den Gamepad-Controller neu zu initialisieren.
                    # Fürs Erste: Nur ZMQ-Teil neu starten.
                    break  # Innere Schleife verlassen

                time.sleep(0.01)  # Sehr kurze Pause, da Gamepad-Loop eigene Pause hat

            except zmq.ZMQError as e:
                print(f"ZMQ-Fehler in Kommunikation: {e}"); break
            except Exception as e:
                print(f"Unerwarteter Fehler in ZMQ-Loop: {e}"); import traceback; traceback.print_exc(); break

        # --- Aufräumen vor ZMQ-Neustart ---
        print("ZMQ Kommunikationsschleife beendet. Starte ZMQ-Teil neu...")
        if subscriber_socket_from_ml: subscriber_socket_from_ml.close(linger=0); subscriber_socket_from_ml = None
        if publisher_socket_to_ml:  publisher_socket_to_ml.close(linger=0);  publisher_socket_to_ml = None
        time.sleep(RECONNECT_INTERVAL_ZMQ)


# --- Programmstart ---
if __name__ == "__main__":
    # Globale Instanz für den ZMQ-Kontext
    # context wird schon global oben erstellt: context = zmq.Context.instance()

    try:
        run_server()  # Startet die Hauptlogik mit der äußeren Schleife
    except KeyboardInterrupt:
        print("\nCtrl+C erkannt. Beende Hauptserver...")
    finally:
        print("Beende alle Komponenten des Hauptservers.")
        if gamepad_ctrl:  # gamepad_ctrl ist jetzt global (oder in run_server deklariert)
            gamepad_ctrl.stop()
        if wc_instance:  # wc_instance ist jetzt global (oder in run_server deklariert)
            wc_instance.shutdown()

        # Sockets werden in run_server() Schleife geschlossen oder hier als Fallback
        if publisher_socket_to_ml and not publisher_socket_to_ml.closed:
            publisher_socket_to_ml.close(linger=0)
        if subscriber_socket_from_ml and not subscriber_socket_from_ml.closed:
            subscriber_socket_from_ml.close(linger=0)

        if not context.closed:
            print("Schließe globalen ZeroMQ-Kontext.")
            context.term()
        print("Hauptserver beendet.")