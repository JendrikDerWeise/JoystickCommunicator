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
from WheelchairControlReal import WheelchairControlReal
import os

# --- NEU: Import für GamepadController ---
try:
    from gamepad_controller import GamepadController
except ImportError as e:
    print(f"Fehler: gamepad_controller.py nicht gefunden oder Inhalt fehlerhaft: {e}", file=sys.stderr)
    # Entscheide, ob der Server ohne Gamepad-Möglichkeit starten soll oder nicht
    # sys.exit(1) # Beendet das Skript
    GamepadController = None  # Setze auf None, damit der Rest des Codes nicht abbricht
    print("WARNUNG: Gamepad-Steuerung wird nicht verfügbar sein.")
# --- ENDE NEU ---


# --- Konstanten ---
HEARTBEAT_INTERVAL = 2  # Sekunden (Heartbeat-Intervall vom *Client* ML2)
RECONNECT_INTERVAL = 10  # Sekunden (Wartezeit vor Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)
BROADCAST_PORT = 50000  # Port für UDP-Broadcast (optional)

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()

# --- Globale Variablen (mit Bedacht verwenden!) ---
magic_leap_ip = None  # IP-Adresse der Magic Leap 2
last_heartbeat = 0  # Zeitpunkt des letzten empfangenen Heartbeats von ML2
publisher_socket = None  # Publisher Socket (zum Senden von Daten an ML2)
subscriber_socket = None  # Subscriber Socket (zum Empfangen von Heartbeats und READY von ML2)

# --- NEU: Globale Instanz für GamepadController ---
gamepad_ctrl: GamepadController | None = None
# --- ENDE NEU ---

# WheelchairControlReal wird global initialisiert, wie in deinem Skript
# Stelle sicher, dass WheelchairControlReal keine Exceptions wirft, die hier nicht gefangen werden
try:
    wc_instance = WheelchairControlReal()
except Exception as e_wc:
    print(f"FATAL: Fehler bei der Initialisierung von WheelchairControlReal: {e_wc}", file=sys.stderr)
    print("Der Server kann ohne funktionierende Rollstuhlsteuerung nicht sinnvoll starten.")
    sys.exit(1)

# --- Globale Variablen für ML2 Konfig-Senden ---
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"
last_config_send_time = 0
JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"


# --- Deine bestehenden Funktionen (is_little_endian, to_network_order, etc.) ---
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
        raise ValueError("Ungültiger Datentyp")


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
        raise ValueError("Ungültiger Datentyp")


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
                print(f"Fehler bei Überprüfung Interface {interface}: {e}")
        print(f"Warnung: Keine passende Schnittstelle im Subnetz von {magic_leap_ip} gefunden.", file=sys.stderr)
        return None
    except NameError:
        print("Fehler: 'netifaces' nicht gefunden.", file=sys.stderr); return None
    except Exception as e:
        print(f"Unerwarteter Fehler in get_correct_network_interface: {e}"); return None


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
        temp_file = "pc_ip.txt"  # Name geändert zu pc_ip.txt wie in deinem Original
        with open(temp_file, "w") as f:
            f.write(f"{correct_interface_ip}:{port}")
        # Dein Original-Zielpfad
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


def run_server():
    """Hauptfunktion des Servers."""
    global magic_leap_ip, last_heartbeat, publisher_socket, subscriber_socket
    global wheelchair  # Zugriff auf die globale Instanz
    global gamepad_ctrl  # Zugriff auf die globale Gamepad-Instanz
    global last_config_send_time

    # --- NEU: GamepadController initialisieren, falls möglich ---
    if GamepadController and gamepad_ctrl is None:  # Nur wenn Klasse importiert wurde und noch keine Instanz existiert
        try:
            print("Initialisiere GamepadController...")
            gamepad_ctrl = GamepadController(wheelchair)  # Übergib die globale wheelchair Instanz
            if not gamepad_ctrl.start():
                print("WARNUNG: GamepadController konnte nicht gestartet werden. Läuft ohne Gamepad-Steuerung.",
                      file=sys.stderr)
                gamepad_ctrl = None  # Setze zurück, falls Start fehlschlägt
            else:
                print("GamepadController erfolgreich gestartet.")
        except Exception as e_gp:
            print(f"FEHLER bei Initialisierung des GamepadControllers: {e_gp}", file=sys.stderr)
            gamepad_ctrl = None
    # --- ENDE NEU ---

    while True:  # Äußere Schleife für Server-Neustart
        print("Server wird (neu)gestartet...")
        # Lokale Variablen für Sockets in diesem Durchlauf
        current_subscriber_socket = None
        current_publisher_socket = None
        pc_port = None

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
            current_publisher_socket = context.socket(zmq.PUB)
            pc_port = current_publisher_socket.bind_to_random_port(f"tcp://{pc_ip}")
            publisher_socket = current_publisher_socket  # Weise globaler Variable zu
            print(f"Publisher Socket (PC) gebunden an {pc_ip}:{pc_port}")

            current_subscriber_socket = context.socket(zmq.SUB)
            # Setze RCVTIMEO hier, bevor connect aufgerufen wird
            current_subscriber_socket.setsockopt(zmq.RCVTIMEO, INITIAL_CONNECTION_TIMEOUT * 1000)
            subscriber_socket = current_subscriber_socket  # Weise globaler Variable zu

            if not send_pc_ip_and_port(magic_leap_ip, pc_port):
                print("Konnte PC-IP und Port nicht an Magic Leap senden. Setze fort...")
        except zmq.ZMQError as e:
            print(f"Socket-Fehler: {e}")
            if current_subscriber_socket: current_subscriber_socket.close(linger=0)
            if current_publisher_socket:  current_publisher_socket.close(linger=0)
            publisher_socket = None;
            subscriber_socket = None  # Globale Sockets zurücksetzen
            time.sleep(RECONNECT_INTERVAL);
            continue
        except Exception as e_setup:  # Fange andere Setup-Fehler ab
            print(f"Allgemeiner Fehler im Socket Setup: {e_setup}")
            if current_subscriber_socket: current_subscriber_socket.close(linger=0)
            if current_publisher_socket:  current_publisher_socket.close(linger=0)
            publisher_socket = None;
            subscriber_socket = None
            time.sleep(RECONNECT_INTERVAL);
            continue

        print("Warte auf READY-Signal von ML2...")
        ready_received = False
        try:
            # connect und subscribe hier, NACHDEM der Socket erstellt wurde
            subscriber_socket.connect(f"tcp://{magic_leap_ip}:{pc_port + 1}")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
            topic, message = subscriber_socket.recv_multipart()  # Wartet max RCVTIMEO
            if topic == b"READY":
                print("READY empfangen!")
                subscriber_socket.setsockopt(zmq.UNSUBSCRIBE, b"READY")  # Wichtig!
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")

                #publisher_socket.send_multipart([b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])
                publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                # Sende auch Kantelungs- und Höhenmodus-Status, falls Gamepad aktiv
                publisher_socket.send_multipart([b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                if gamepad_ctrl and hasattr(gamepad_ctrl, '_gp_height_active'):
                    publisher_socket.send_multipart(
                        [b"height_mode", to_network_order(gamepad_ctrl._gp_height_active, '?')])

                ready_received = True
                print(f"Subscriber (PC) verbunden mit ML2 an {magic_leap_ip}:{pc_port + 1}")
                # Setze RCVTIMEO für die Hauptschleife auf einen kürzeren Wert
                subscriber_socket.setsockopt(zmq.RCVTIMEO, 1000)  # z.B. 1 Sekunde

        except zmq.error.Again:  # Timeout beim Empfangen von READY
            print("Timeout beim Warten auf READY von ML2.")
        except zmq.ZMQError as e:
            print(f"Fehler beim Warten/Verbinden (ZMQ): {e}")
        except Exception as e_ready:  # Fange andere Fehler im READY-Block ab
            print(f"Unerwarteter Fehler im READY-Block: {e_ready}")

        if not ready_received:
            print("Setup der ML2-Verbindung nicht erfolgreich, starte ZMQ-Teil neu...")
            if subscriber_socket: subscriber_socket.close(linger=0); subscriber_socket = None
            if publisher_socket:  publisher_socket.close(linger=0);  publisher_socket = None
            time.sleep(RECONNECT_INTERVAL)
            continue

        # --- Ende Socket-Setup ---

        # --- Hauptkommunikationsschleife (nach Empfang von READY) ---
        print("Beginne mit der Hauptkommunikation...")
        last_heartbeat = time.time()  # Zeit des letzten *empfangenen* Heartbeats von ML2
        last_heartbeat_send_to_ml = 0  # Zeitpunkt des letzten Sendens eines Heartbeats AN ML2
        # last_rlink_heartbeat_send = time.time() # Wird jetzt vom GamepadController gehandhabt
        # HEARTBEAT_INTERVAL_RLINK = 0.2 # Wird jetzt vom GamepadController gehandhabt

        while True:  # Hauptkommunikationsschleife
            try:
                current_time = time.time()
                # --- Heartbeat AN ML2 senden ---
                if publisher_socket and not publisher_socket.closed and \
                        current_time - last_heartbeat_send_to_ml > HEARTBEAT_INTERVAL:  # Nutze dein HEARTBEAT_INTERVAL
                    publisher_socket.send_multipart([b"heartbeat", b""])
                    last_heartbeat_send_to_ml = current_time

                # --- Heartbeat ZUM Rollstuhl(RLink) ---
                # Wird jetzt vom GamepadController in seinem eigenen Thread gemacht,
                # wenn gamepad_ctrl aktiv ist.
                # Wenn KEIN Gamepad aktiv ist, müssen wir es hier tun.
                if wc_instance and (not gamepad_ctrl or gamepad_ctrl.quit_event.is_set()):
                    # Rufe die synchrone Heartbeat-Methode von WheelchairControlReal
                    # Diese Methode existiert in deiner WheelchairControlReal Klasse
                    # (aus Antwort #47, send_rlink_heartbeat)
                    # Stelle sicher, dass sie `heartbeat()` heißt oder passe den Aufruf an.
                    # Annahme: Sie heißt jetzt `heartbeat()`
                    if hasattr(wc_instance, 'heartbeat'):
                        wc_instance.heartbeat()
                    elif hasattr(wc_instance, 'send_rlink_heartbeat'):  # Fallback zum alten Namen
                        wc_instance.send_rlink_heartbeat()
                    # else: print("WARNUNG: Keine Heartbeat-Methode in wc_instance gefunden")

                # --- Trigger-Dateien prüfen ---
                if publisher_socket and not publisher_socket.closed:
                    if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                        try:
                            print(f"Trigger-Datei '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                            publisher_socket.send_multipart(
                                [b"joystick_toggle_visibility", b"toggle"])  # Payload "toggle"
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
                                    publisher_socket.send_multipart(
                                        [b"joystick_settings", config_json_str.encode('utf-8')])
                                    last_config_send_time = trigger_timestamp
                                os.remove(CONFIG_TRIGGER_FILE)
                        except Exception as e_cfg_trig:
                            print(f"Fehler Trigger Config: {e_cfg_trig}", file=sys.stderr)

                # --- Daten an ML2 senden (z.B. Geschwindigkeit) ---
                if publisher_socket and not publisher_socket.closed:
                    speed = wc_instance.get_wheelchair_speed()
                    float_value = to_network_order(speed, 'f')
                    publisher_socket.send_multipart([b"topic_float", float_value])

                # --- Nachrichten von ML2 empfangen ---
                try:
                    if subscriber_socket and not subscriber_socket.closed and \
                            subscriber_socket.poll(timeout=100):  # Kurzer, nicht-blockierender Poll
                        topic, message = subscriber_socket.recv_multipart()

                        if topic == b"heartbeat":
                            last_heartbeat = time.time()  # Zeit des letzten EMPFANGENEN Heartbeats
                            # print("Heartbeat von ML2 empfangen") # Optional
                        elif topic == b"joystickPos":
                            # Nur verarbeiten, wenn KEIN Gamepad aktiv ist
                            if not gamepad_ctrl or gamepad_ctrl.quit_event.is_set():
                                x = from_network_order(message[0:4], 'f')
                                y = from_network_order(message[4:8], 'f')
                                wc_instance.set_direction((x, y))
                            # else:
                            #    print("Gamepad aktiv, ignoriere ML2 Joystick-Daten.")
                        elif topic == b"gear":
                            # Gangwechsel von ML2, auch wenn Gamepad aktiv ist?
                            # Oder soll Gamepad Vorrang haben? Hier: ML2 kann Gang ändern.
                            received_value = from_network_order(message, '?')
                            actual_gear = wc_instance.set_gear(received_value)
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"gear", to_network_order(actual_gear, 'i')])
                        elif topic == b"lights":
                            # ML2 sendet nur Trigger, WheelchairControlReal toggelt
                            wc_instance.set_lights()
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"lights", to_network_order(wc_instance.get_lights(), '?')])
                        elif topic == b"warn":
                            wc_instance.set_warn()
                            if publisher_socket: publisher_socket.send_multipart(
                                [b"warn", to_network_order(wc_instance.get_warn(), '?')])
                        elif topic == b"horn":
                            wc_instance.on_horn(from_network_order(message, '?'))
                        elif topic == b"kantelung":
                            # ML2 kann Kantelungsmodus umschalten, wenn Gamepad nicht aktiv
                            if not gamepad_ctrl or gamepad_ctrl.quit_event.is_set():
                                received_value = from_network_order(message, '?')
                                wc_instance.on_kantelung(received_value)
                                if publisher_socket: publisher_socket.send_multipart(
                                    [b"kantelung", to_network_order(wc_instance.get_kantelung(), '?')])
                        else:
                            print(f"Unerwartetes Topic von ML2: {topic}")
                except zmq.error.Again:
                    pass  # Timeout beim Pollen ist normal, nichts zu tun

                # --- Heartbeat-Timeout-Überprüfung (von ML2) ---
                if time.time() - last_heartbeat > RECONNECT_INTERVAL:  # Dein RECONNECT_INTERVAL
                    print("Heartbeat-Timeout von ML2!")
                    break  # Beende die innere Kommunikationsschleife -> führt zu ZMQ-Neustart

                # --- Prüfen, ob Gamepad-Controller beendet wurde ---
                if gamepad_ctrl and gamepad_ctrl.quit_event.is_set():
                    print("Gamepad-Controller hat Beenden signalisiert. Starte ZMQ-Teil neu.")
                    # Hier könntest du versuchen, den Gamepad-Controller neu zu starten
                    # oder den Server ganz zu beenden. Fürs Erste: ZMQ-Neustart.
                    gamepad_ctrl.stop()  # Stoppe den alten Controller
                    gamepad_ctrl = None  # Setze zurück, damit er oben neu initialisiert wird
                    break  # Innere Schleife verlassen

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
        if wc_instance:  # wc_instance ist global
            wc_instance.shutdown()

        # Globale Sockets hier schließen, falls sie noch offen sind
        # (obwohl sie in der Schleife schon geschlossen werden sollten)
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