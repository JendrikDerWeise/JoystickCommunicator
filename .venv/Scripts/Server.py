import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket  # Für UDP-Broadcast
import random  # Beibehalten aus deinem Original
import struct
import os  # Für die neue Trigger-File-Logik benötigt

from WheelchairControlReal import WheelchairControlReal

# --- Konstanten ---
HEARTBEAT_INTERVAL = 2  # Sekunden (Heartbeat-Intervall vom *Client*)
RECONNECT_INTERVAL = 10  # Sekunden (Wartezeit vor Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)
BROADCAST_PORT = 50000  # Port für UDP-Broadcast (optional)

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()

# --- Globale Variablen (mit Bedacht verwenden!) ---
magic_leap_ip = None  # IP-Adresse der Magic Leap 2
last_heartbeat = 0  # Zeitpunkt des letzten empfangenen Heartbeats
publisher_socket = None  # Publisher Socket (zum Senden von Daten)
subscriber_socket = None  # Subscriber Socket (zum Empfangen von Heartbeats und READY)
wheelchair = WheelchairControlReal()

# Globale Variablen für das Senden der ML2-Konfiguration (aus deinem vorherigen Code übernommen)
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"
last_config_send_time = 0


def is_little_endian():
    """Überprüft, ob das System Little-Endian ist."""
    return sys.byteorder == 'little'


def to_network_order(value, data_type):
    if data_type == 'i':  # Integer
        if is_little_endian():
            return struct.pack('>i', value)  # '>' für Big-Endian
        return struct.pack('i', value)
    elif data_type == 'f':  # Float
        if is_little_endian():
            return struct.pack('>f', value)
        return struct.pack('f', value)
    elif data_type == 'd':  # Double
        if is_little_endian():
            return struct.pack('>d', value)
        return struct.pack('d', value)
    elif data_type == '?':  # Bool
        return struct.pack('?', value)
    else:
        raise ValueError("Ungültiger Datentyp")


def from_network_order(data, data_type):
    """Konvertiert einen Wert von Big-Endian (Network Byte Order) zum Host-System."""
    if data_type == 'i':
        if is_little_endian():
            return struct.unpack('>i', data)[0]  # '>' für Big-Endian
        return struct.unpack('i', data)[0]
    elif data_type == 'f':
        if is_little_endian():
            return struct.unpack('>f', data)[0]
        return struct.unpack('f', data)[0]
    elif data_type == 'd':
        if is_little_endian():
            return struct.unpack('>d', data)[0]
        return struct.unpack('d', data)[0]
    elif data_type == '?':
        return struct.unpack('?', data)[0]
    else:
        raise ValueError("Ungültiger Datentyp")


def get_correct_network_interface(magic_leap_ip_addr):  # magic_leap_ip -> magic_leap_ip_addr zur Klarheit
    """
    Findet die Netzwerkschnittstelle des PCs, die im gleichen Subnetz wie die
    Magic Leap 2 ist.  Wird benötigt, um die *eigene* IP-Adresse des PCs zu
    bestimmen, an die der PublisherSocket gebunden werden soll.
    """
    if not magic_leap_ip_addr:  # magic_leap_ip -> magic_leap_ip_addr
        return None

    try:
        magic_leap_subnet = ".".join(magic_leap_ip_addr.split(".")[:3])  # magic_leap_ip -> magic_leap_ip_addr
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    ipv4_details = iface_details[netifaces.AF_INET]
                    for ip_info in ipv4_details:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1':
                            interface_subnet = ".".join(ip_address.split(".")[:3])
                            if interface_subnet == magic_leap_subnet:
                                print(f"Korrekte Schnittstelle gefunden: {interface} ({ip_address})")
                                return ip_address
            except Exception as e:
                print(f"Fehler bei der Überprüfung der Schnittstelle {interface}: {e}")
        # Fallback, falls kein Subnetz-Match (aus deinem Original-Code beibehalten)
        print("Warnung: Keine passende Netzwerkschnittstelle für ML2-Subnetz gefunden. Versuche Fallback.")
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    for ip_info in iface_details[netifaces.AF_INET]:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1' and not ip_address.startswith("172."):
                            print(f"Fallback-Schnittstelle verwendet: {interface} ({ip_address})")
                            return ip_address
            except:
                pass
        return None

    except Exception as e:
        print(f"Unerwarteter Fehler in get_correct_network_interface: {e}")
        return None


def get_magic_leap_ip_adb():
    """Ermittelt die IP-Adresse der Magic Leap 2 über ADB (zuverlässiger)."""
    try:
        start_time = time.time()
        timeout = 10

        while time.time() - start_time < timeout:
            result = subprocess.run(['adb', 'shell', 'ip', 'route'], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                # Deine Originalbedingung, die ich nicht ändere:
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
        print(
            f"Fehler bei der Ausführung von 'adb shell ip route': {e}, Rückgabecode: {e.returncode}, Ausgabe: {e.output}")
        return None
    except FileNotFoundError:  # Hinzugefügt für den Fall, dass adb nicht gefunden wird
        print("Fehler: 'adb' Kommando nicht gefunden. Ist ADB installiert und im PATH?")
        return None
    except Exception as e:
        print(f"Unerwarteter Fehler bei der ADB-IP-Ermittlung: {e}")
        return None


def send_pc_ip_and_port(ml_ip_addr, pc_port_to_send):  # Variablen umbenannt zur Klarheit
    """Schreibt die IP-Adresse des PCs *und* den Port in eine Datei."""
    try:
        correct_interface_ip = get_correct_network_interface(ml_ip_addr)
        if not correct_interface_ip:
            print("Keine passende Netzwerkschnittstelle für send_pc_ip_and_port gefunden.")
            return False

        temp_file = "pc_ip.txt"
        with open(temp_file, "w") as f:
            f.write(f"{correct_interface_ip}:{pc_port_to_send}")

        # Dein Original-Pfad
        ml2_target_path = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/pc_ip.txt'
        subprocess.run(['adb', 'push', temp_file, ml2_target_path], check=True)
        print(
            f"PC IP-Adresse ({correct_interface_ip}) und Port ({pc_port_to_send}) auf Magic Leap 2 kopiert nach {ml2_target_path}.")
        # os.remove(temp_file) # Optional: temporäre Datei löschen
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Kopieren der Datei (adb push): {e}")
        return False
    except FileNotFoundError:  # Hinzugefügt
        print("Fehler: 'adb' Kommando nicht gefunden beim Senden der PC-IP.")
        return False
    except Exception as e:
        print(f"Fehler beim Schreiben/Kopieren der IP-Adresse und des Ports: {e}")
        return False


def run_server():
    """Hauptfunktion des Servers."""
    # Globale Variablen, die hier modifiziert werden
    global magic_leap_ip, last_heartbeat, publisher_socket, subscriber_socket, last_config_send_time

    while True:  # Äußere Schleife für Server-Neustart
        print("Server wird (neu)gestartet...")
        # Sockets und relevante Zustandsvariablen vor jedem Versuch zurücksetzen
        if subscriber_socket: subscriber_socket.close(linger=0); subscriber_socket = None
        if publisher_socket: publisher_socket.close(linger=0); publisher_socket = None

        pc_ip_for_binding = "0.0.0.0"  # Binde an alle Interfaces
        pc_port = None  # Wird dynamisch zugewiesen

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip:
            print("Konnte Magic Leap IP nicht ermitteln. Warte 5 Sekunden...");
            time.sleep(5);
            continue

        # pc_ip in get_correct_network_interface() wird für send_pc_ip_and_port intern ermittelt.
        # Hier binden wir an 0.0.0.0 für Robustheit.

        try:
            publisher_socket = context.socket(zmq.PUB)
            pc_port = publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_binding}")
            print(f"Publisher Socket (Pi -> ML2) gebunden an tcp://{pc_ip_for_binding}:{pc_port}")

            subscriber_socket = context.socket(zmq.SUB)
            # Der Port, auf dem die ML2 publiziert, ist pc_port + 1 (deine Konvention)
            ml2_publisher_port = pc_port + 1

            if not send_pc_ip_and_port(magic_leap_ip, pc_port):  # Sende den Port des Pi-Publishers
                print("Warnung: Konnte PC-IP und Publisher-Port nicht an Magic Leap senden.")
                # Nicht unbedingt abbrechen, vielleicht kennt ML2 die Info schon

            ml2_publisher_address = f"tcp://{magic_leap_ip}:{ml2_publisher_port}"
            print(f"Versuche Subscriber (Pi <- ML2) zu verbinden mit {ml2_publisher_address}")
            subscriber_socket.connect(ml2_publisher_address)
            subscriber_socket.setsockopt(zmq.RCVTIMEO, 5000)  # Timeout für Empfang

            print("Warte auf READY-Signal von ML2...")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
            ready_received = False
            try:
                topic, message = subscriber_socket.recv_multipart()
                if topic == b"READY":
                    print("READY von ML2 empfangen!")
                    ready_received = True
                else:
                    print(
                        f"Unerwartetes Topic statt READY: {topic}")  # Wird durch Timeout abgefangen, wenn nichts kommt
            except zmq.error.Again:  # Wird durch RCVTIMEO ausgelöst
                print("Timeout beim Warten auf READY-Signal von ML2.")
            # Andere ZMQError oder Exception werden hier nicht spezifisch behandelt, könnten aber auftreten

            if not ready_received:
                print("Initiales READY nicht empfangen. Starte Server neu.")
                time.sleep(RECONNECT_INTERVAL)
                continue  # Zurück zum Anfang der äußeren while-Schleife

            # Reguläre Topics abonnieren, wenn READY empfangen wurde
            subscriber_socket.setsockopt(zmq.UNSUBSCRIBE, b"READY")  # Wichtig: Nicht mehr auf READY hören
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")
            print(f"Subscriber (Pi <- ML2) erfolgreich verbunden und Topics abonniert auf {ml2_publisher_address}")

            # Sende initiale Status-Infos an ML2 (aus deinem Originalcode)
            publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
            publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
            publisher_socket.send_multipart(
                [b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])  # Sende aktuellen Gang

        except zmq.ZMQError as e:
            print(f"Socket-Fehler im Setup-Teil: {e}")
            time.sleep(RECONNECT_INTERVAL)
            continue
        except Exception as e:
            print(f"Allgemeiner Fehler im Setup-Teil: {e}")
            time.sleep(RECONNECT_INTERVAL)
            continue

        # --- Hauptkommunikationsschleife (nach Empfang von READY) ---
        print("Beginne mit der Hauptkommunikation...")

        last_heartbeat = time.time()  # Dies ist für den Empfang von ML2
        # Die folgenden Variablen sind aus deinem Originalcode
        float_value = 0
        last_heartbeat_send = 0  # Zeitpunkt des letzten Sendens des Pi->ML2 Heartbeats
        last_rlink_heartbeat_send = time.time()
        # Die folgende Zeile ist aus deinem Code und überschreibt die globale Konstante.
        # Ich lasse sie hier, wie von dir gewünscht, obwohl es zu Verwirrung führen kann.
        HEARTBEAT_INTERVAL = 0.2  # Wird für Pi->ML2 und Pi->RLink Heartbeat verwendet

        while True:  # Hauptkommunikationsschleife
            try:
                # --- Sende Heartbeat AN ML2 ---
                if time.time() - last_heartbeat_send > HEARTBEAT_INTERVAL:  # Verwendet das neu definierte 0.2s Intervall
                    publisher_socket.send_multipart([b"heartbeat", b"pi_is_alive"])  # Aussagekräftigere Nachricht
                    last_heartbeat_send = time.time()

                # --- Heartbeat ZUM Rollstuhl(RLink) ---
                if time.time() - last_rlink_heartbeat_send > HEARTBEAT_INTERVAL:  # Verwendet auch das 0.2s Intervall
                    if wheelchair.send_rlink_heartbeat():  # Methode aus WheelchairControlReal
                        last_rlink_heartbeat_send = time.time()
                    else:
                        print("Konnte RLink Heartbeat nicht senden, möglicherweise Verbindungsproblem.")

                # --- BEGINN DER ERGÄNZUNG für ML2 Joystick-Konfiguration ---
                if os.path.exists(CONFIG_TRIGGER_FILE):
                    try:
                        trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                        if trigger_timestamp > last_config_send_time:
                            with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                config_json_str = f.read()

                            if config_json_str and publisher_socket:
                                print(f"Sende ML2 Joystick Konfiguration (Trigger, Länge: {len(config_json_str)})...")
                                publisher_socket.send_multipart([b"joystick_settings", config_json_str.encode('utf-8')])
                                last_config_send_time = trigger_timestamp
                                try:
                                    os.remove(CONFIG_TRIGGER_FILE)
                                    print("Trigger-Datei für ML2-Konfig gelöscht.")
                                except OSError as e_remove:
                                    print(f"Fehler beim Löschen der Trigger-Datei '{CONFIG_TRIGGER_FILE}': {e_remove}")
                            elif not config_json_str:
                                print("Trigger-Datei ist leer, lösche sie.")
                                try:
                                    os.remove(CONFIG_TRIGGER_FILE)
                                except OSError as e_remove:
                                    print(
                                        f"Fehler beim Löschen der leeren Trigger-Datei '{CONFIG_TRIGGER_FILE}': {e_remove}")
                    except FileNotFoundError:
                        pass
                    except Exception as e_config:
                        print(f"Fehler beim Lesen/Senden der ML2 Joystick Konfiguration: {e_config}")
                # --- ENDE DER ERGÄNZUNG ---

                # Sende Rollstuhlgeschwindigkeit an ML2
                speed = wheelchair.get_wheelchair_speed()
                float_value = to_network_order(speed, 'f')
                publisher_socket.send_multipart([b"wheelchair_speed", float_value])  # Topic geändert
                # Dein Originalcode sendet "topic_float", ändere ggf. "wheelchair_speed" zurück, falls ML2 das erwartet

                # Empfange Nachrichten (mit Timeout, wie in deinem Original)
                if subscriber_socket.poll(1000):  # 1 Sekunde Timeout
                    topic, message = subscriber_socket.recv_multipart()

                    if topic == b"heartbeat":
                        last_heartbeat = time.time()  # Zeitstempel für Heartbeat VON ML2
                        # print("Heartbeat von ML2 empfangen") # Sehr häufig, ggf. auskommentieren
                    elif topic == b"joystickPos":
                        if len(message) == 8:  # 2 Floats = 8 Bytes
                            x = from_network_order(message[0:4], 'f')
                            y = from_network_order(message[4:8], 'f')
                            direction = (x, y)
                            wheelchair.set_direction(direction)
                        else:
                            print(f"Warnung: joystickPos Nachricht hat falsche Länge: {len(message)} statt 8 Bytes.")
                    elif topic == b"gear":
                        received_value = from_network_order(message, '?')
                        actual_gear = wheelchair.set_gear(received_value)
                        publisher_socket.send_multipart([b"gear", to_network_order(actual_gear, 'i')])
                    elif topic == b"lights":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_lights()
                        publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                        # print("lights: " + str(wheelchair.get_lights())) # Auskommentiert aus deinem Code
                    elif topic == b"warn":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_warn()
                        publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                        # print("warn: " + str(wheelchair.get_warn())) # Auskommentiert aus deinem Code
                    elif topic == b"horn":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_horn(received_value)
                    elif topic == b"kantelung":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_kantelung(received_value)
                        publisher_socket.send_multipart(
                            [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    else:
                        print(f"Unerwartetes Topic empfangen: {topic}")

                # Heartbeat-Timeout-Überprüfung (VON ML2)
                # Dein Originalcode verwendet RECONNECT_INTERVAL (10s) und die globale Konstante HEARTBEAT_INTERVAL (2s)
                # Es ist unklar, welche hier verwendet werden soll. Ich nehme die globale Konstante HEARTBEAT_INTERVAL,
                # die oben auf 2s gesetzt ist, für den Empfang.
                # Wenn du RECONNECT_INTERVAL (10s) willst, ändere es hier.
                if time.time() - last_heartbeat > HEARTBEAT_INTERVAL:  # Verwendet jetzt die globale Konstante (2s)
                    print("Heartbeat-Timeout VON Magic Leap! Starte Verbindung neu.")
                    break  # Beende die innere Kommunikationsschleife

            except zmq.ZMQError as e:
                print(f"Fehler in der Kommunikation (ZMQ): {e}")
                break
            except Exception as e:
                print(f"Unerwarteter Fehler in der Hauptschleife: {e}")
                break

        # --- Aufräumen beim Neustart der äußeren Schleife ---
        print("Kommunikationsschleife beendet. Server wird in Kürze neu gestartet...")
        # Sockets werden bereits am Anfang der äußeren Schleife geschlossen
        time.sleep(RECONNECT_INTERVAL)


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nServer durch Benutzer (Strg+C) beendet.")
    except Exception as e:
        print(f"\nKritischer Fehler im Hauptteil des Servers: {e}")
    finally:
        print("Führe finale Aufräumarbeiten durch...")
        # Dein Original-Cleanup, falls wheelchair oder context nicht existieren
        if 'wheelchair' in globals() and wheelchair:
            wheelchair.shutdown()
        if 'context' in globals() and context and not context.closed:
            print("Schließe ZeroMQ-Kontext...")
            context.term()
        print("Server vollständig beendet.")