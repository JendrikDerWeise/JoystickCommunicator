import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket  # Für UDP-Broadcast
import random  # Wird aktuell nicht verwendet, kann ggf. entfernt werden
import struct
import os  # Wird für os.path.exists und os.path.getmtime benötigt

from WheelchairControlReal import WheelchairControlReal

# --- Konstanten ---
HEARTBEAT_INTERVAL = 2  # Sekunden (Heartbeat-Intervall vom *Client* ZUM Pi)
RECONNECT_INTERVAL = 10  # Sekunden (Wartezeit vor Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal) # Aktuell nicht verwendet
BROADCAST_PORT = 50000  # Port für UDP-Broadcast (optional)

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()

# --- Globale Variablen (mit Bedacht verwenden!) ---
magic_leap_ip = None  # IP-Adresse der Magic Leap 2
last_heartbeat = 0  # Zeitpunkt des letzten empfangenen Heartbeats VON ML2
publisher_socket = None  # Publisher Socket (Pi sendet AN ML2)
subscriber_socket = None  # Subscriber Socket (Pi empfängt VON ML2)
wheelchair = WheelchairControlReal()

# Globale Variablen für das Senden der ML2-Konfiguration
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"  # Name der Datei, die app.py erstellt
last_config_send_time = 0  # Zeitstempel, wann die Config zuletzt gesendet wurde


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


def get_correct_network_interface(magic_leap_ip_addr):  # Name der Variable geändert zur Klarheit
    """
    Findet die Netzwerkschnittstelle des PCs, die im gleichen Subnetz wie die
    Magic Leap 2 ist.  Wird benötigt, um die *eigene* IP-Adresse des PCs zu
    bestimmen, an die der PublisherSocket gebunden werden soll.
    """
    if not magic_leap_ip_addr:
        return None

    try:
        magic_leap_subnet = ".".join(magic_leap_ip_addr.split(".")[:3])
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
        print("Warnung: Keine passende Netzwerkschnittstelle für ML2-Subnetz gefunden. Versuche Fallback.")
        # Fallback: Versuche, eine beliebige nicht-loopback IP zu finden, die nicht Docker ist
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    for ip_info in iface_details[netifaces.AF_INET]:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1' and not ip_address.startswith("172."):  # Ignoriere Docker etc.
                            print(f"Fallback-Schnittstelle verwendet: {interface} ({ip_address})")
                            return ip_address
            except:
                pass  # Ignoriere Fehler bei Fallback-Suche
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
                # Korrekte Bedingung für 'or'
                if "dev mlnet0" in line or "eth1" in line or "wlan0" in line:  # Füge ggf. weitere Interface-Namen hinzu
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
    except FileNotFoundError:
        print("Fehler: 'adb' Kommando nicht gefunden. Ist ADB installiert und im PATH?")
        return None
    except Exception as e:
        print(f"Unerwarteter Fehler bei der ADB-IP-Ermittlung: {e}")
        return None


def send_pc_ip_and_port(ml_ip_addr, pc_port_to_send):  # Variablen umbenannt
    """Schreibt die IP-Adresse des PCs *und* den Port in eine Datei."""
    try:
        # Hole die korrekte PC-IP-Adresse, die im selben Subnetz wie die ML2 ist
        pc_ip_to_send = get_correct_network_interface(ml_ip_addr)
        if not pc_ip_to_send:
            print("Konnte korrekte PC IP zum Senden an ML2 nicht ermitteln.")
            return False

        temp_file = "pc_ip.txt"
        with open(temp_file, "w") as f:
            f.write(f"{pc_ip_to_send}:{pc_port_to_send}")

        # Pfad auf der Magic Leap 2 - stelle sicher, dass dieser korrekt und beschreibbar ist!
        ml2_target_path = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/pc_ip.txt'
        subprocess.run(['adb', 'push', temp_file, ml2_target_path], check=True)
        print(
            f"PC IP-Adresse ({pc_ip_to_send}) und Port ({pc_port_to_send}) auf Magic Leap 2 kopiert nach {ml2_target_path}.")
        # os.remove(temp_file) # Temporäre Datei kann gelöscht werden
        return True

    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Kopieren der Datei (adb push): {e}")
        return False
    except FileNotFoundError:
        print("Fehler: 'adb' Kommando nicht gefunden beim Senden der PC-IP.")
        return False
    except Exception as e:
        print(f"Fehler beim Schreiben/Kopieren der IP-Adresse und des Ports: {e}")
        return False


def run_server():
    """Hauptfunktion des Servers."""
    global magic_leap_ip, last_heartbeat, publisher_socket, subscriber_socket, last_config_send_time  # last_config_send_time hinzugefügt

    while True:
        print("Server wird (neu)gestartet...")
        # Sockets sauber schließen, falls sie aus einer vorherigen Iteration noch existieren
        if subscriber_socket: subscriber_socket.close(linger=0); subscriber_socket = None
        if publisher_socket: publisher_socket.close(linger=0); publisher_socket = None

        pc_ip_for_binding = "0.0.0.0"  # Standardmäßig an alle Interfaces binden
        pc_pub_port = None  # Port für den Publisher dieses Servers (Pi -> ML2)
        last_config_send_time = 0  # Reset für das Senden der Config beim Neustart

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip: print("Konnte Magic Leap IP nicht ermitteln. Warte 5 Sek..."); time.sleep(5); continue

        # Die IP zum Binden kann 0.0.0.0 sein, für send_pc_ip_and_port brauchen wir die spezifische.
        # get_correct_network_interface wird in send_pc_ip_and_port intern aufgerufen.

        try:
            publisher_socket = context.socket(zmq.PUB)
            pc_pub_port = publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_binding}")
            print(f"Publisher Socket (Pi -> ML2) gebunden an tcp://{pc_ip_for_binding}:{pc_pub_port}")

            # Subscriber für Nachrichten VON der ML2
            subscriber_socket = context.socket(zmq.SUB)
            # Port, auf dem die ML2 publiziert (Konvention: pc_pub_port + 1)
            ml2_publisher_port = pc_pub_port + 1

            # Sende die Info (IP des Pi im ML2-Subnetz und Port *des Pi-Publishers*) an die ML2
            if not send_pc_ip_and_port(magic_leap_ip, pc_pub_port):
                print("Warnung: PC-IP und Publisher-Port konnten nicht an Magic Leap gesendet werden.")
                # Optional: Hier abbrechen oder weitermachen und hoffen, dass ML2 die Info schon hat

            # Verbinde den Subscriber dieses Servers mit dem Publisher der ML2
            ml2_publisher_address = f"tcp://{magic_leap_ip}:{ml2_publisher_port}"
            print(f"Versuche Subscriber (Pi <- ML2) zu verbinden mit {ml2_publisher_address}")
            subscriber_socket.connect(ml2_publisher_address)
            subscriber_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 Sek. Timeout für READY

            print("Warte auf READY-Signal von ML2...")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
            ready_received = False
            try:
                topic, message = subscriber_socket.recv_multipart()
                if topic == b"READY":
                    print("READY von ML2 empfangen!")
                    ready_received = True
                else:
                    print(f"Unerwartetes Topic statt READY empfangen: {topic}")
            except zmq.error.Again:
                print("Timeout beim Warten auf READY-Signal.")
            except zmq.ZMQError as e:
                print(f"ZMQ-Fehler beim Warten auf READY: {e}")
            except Exception as e:
                print(f"Allgemeiner Fehler beim Warten auf READY: {e}")

            if not ready_received:
                print("Initiales READY nicht empfangen. Starte Server neu.")
                time.sleep(RECONNECT_INTERVAL)
                continue

            # Reguläre Topics abonnieren, NACHDEM READY empfangen wurde
            subscriber_socket.setsockopt(zmq.UNSUBSCRIBE, b"READY")  # Nicht mehr auf READY hören
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")
            print(f"Subscriber (Pi <- ML2) verbunden und Topics abonniert an {ml2_publisher_address}")

            # Sende initiale Statuswerte an ML2
            publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
            publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
            publisher_socket.send_multipart([b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])


        except zmq.ZMQError as e:
            print(f"Socket-Setup Fehler: {e}");
            time.sleep(RECONNECT_INTERVAL);
            continue
        except Exception as e:
            print(f"Allgemeiner Fehler im Setup: {e}");
            time.sleep(RECONNECT_INTERVAL);
            continue

        # --- Hauptkommunikationsschleife (nach Empfang von READY) ---
        print("Beginne mit der Hauptkommunikation...")
        last_heartbeat = time.time()  # Dies ist last_heartbeat_from_ml2

        # Umbenennung der Variablen aus deinem Code für Klarheit hier im Kommentar
        # last_heartbeat_send -> last_heartbeat_to_ml2_send_time (für Pi -> ML2 Heartbeat)
        # last_rlink_heartbeat_send -> last_rlink_heartbeat_send_time (für Pi -> RLink Heartbeat)
        # HEARTBEAT_INTERVAL (unten neu definiert auf 0.2) -> wird für beide verwendet, sollte getrennt sein

        last_heartbeat_to_ml2_send_time = 0
        last_rlink_heartbeat_send_time = time.time()

        # Die folgende Zeile überschreibt die globale Konstante HEARTBEAT_INTERVAL (2s)
        # mit einem neuen Wert (0.2s). Das ist fehleranfällig.
        # Ich verwende die umbenannten Konstanten von oben.
        # HEARTBEAT_INTERVAL = 0.2 # Diese Zeile aus deinem Code
        # sollte separate Konstanten verwenden.

        while True:  # Hauptkommunikationsschleife
            try:
                # --- Heartbeat AN ML2 senden ---
                if time.time() - last_heartbeat_to_ml2_send_time > HEARTBEAT_INTERVAL_TO_ML2:  # Nutzt 2s
                    publisher_socket.send_multipart([b"heartbeat", b"pi_is_alive"])  # Aussagekräftigere Nachricht
                    last_heartbeat_to_ml2_send_time = time.time()

                # --- Heartbeat ZUM Rollstuhl(RLink) ---
                if time.time() - last_rlink_heartbeat_send_time > RLINK_HEARTBEAT_INTERVAL:  # Nutzt 0.2s
                    if wheelchair.send_rlink_heartbeat():  # Ruft Methode aus WheelchairControlReal auf
                        last_rlink_heartbeat_send_time = time.time()
                    else:
                        print("Konnte RLink Heartbeat nicht senden, möglicherweise Verbindungsproblem.")

                # --- BEGINN DER ERGÄNZUNG für ML2 Joystick-Konfiguration ---
                if os.path.exists(CONFIG_TRIGGER_FILE):
                    try:
                        trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                        # Sende Config, wenn Trigger-Datei neuer ist als letzter Sendeversuch
                        # oder wenn noch nie gesendet wurde (last_config_send_time = 0)
                        if trigger_timestamp > last_config_send_time:
                            with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                config_json_str = f.read()

                            if config_json_str and publisher_socket:
                                print(f"Sende ML2 Joystick Konfiguration (Trigger, Länge: {len(config_json_str)})...")
                                publisher_socket.send_multipart([b"joystick_settings", config_json_str.encode('utf-8')])
                                last_config_send_time = trigger_timestamp  # Aktualisiere Zeitstempel des Sendens
                                # Lösche die Trigger-Datei, um wiederholtes Senden zu vermeiden
                                try:
                                    os.remove(CONFIG_TRIGGER_FILE)
                                    print("Trigger-Datei für ML2-Konfig gelöscht.")
                                except OSError as e_remove:
                                    print(f"Fehler beim Löschen der Trigger-Datei '{CONFIG_TRIGGER_FILE}': {e_remove}")
                            elif not config_json_str:  # Falls Datei leer ist
                                print("Trigger-Datei ist leer, lösche sie.")
                                try:
                                    os.remove(CONFIG_TRIGGER_FILE)
                                except OSError as e_remove:
                                    print(
                                        f"Fehler beim Löschen der leeren Trigger-Datei '{CONFIG_TRIGGER_FILE}': {e_remove}")
                    except FileNotFoundError:
                        # Kann passieren, wenn die Datei zwischen os.path.exists und open gelöscht wird
                        pass
                    except Exception as e_config:
                        print(f"Fehler beim Lesen/Senden der ML2 Joystick Konfiguration: {e_config}")
                # --- ENDE DER ERGÄNZUNG ---

                # Sende Rollstuhlgeschwindigkeit AN ML2
                speed = wheelchair.get_wheelchair_speed()
                float_value = to_network_order(speed, 'f')  # float_value war schon deklariert
                publisher_socket.send_multipart([b"wheelchair_speed", float_value])  # Topic geändert
                # publisher_socket.send_multipart([b"topic_string", string_value.encode()]) # Auskommentiert

                # Empfange Nachrichten von ML2 (mit kurzem Timeout, um Loop nicht zu blockieren)
                # Dein Code hatte hier 1000ms, was sehr lang ist, wenn nichts kommt.
                # Ein kürzerer Poll ist besser für die Reaktionsfähigkeit der anderen Sende-Tasks.
                if subscriber_socket.poll(10):  # Poll für 10 Millisekunden
                    topic, message = subscriber_socket.recv_multipart()

                    if topic == b"heartbeat":
                        last_heartbeat = time.time()  # Dies ist last_heartbeat_from_ml2
                        # print("Heartbeat von ML2 empfangen") # Kann sehr häufig sein, ggf. auskommentieren
                    elif topic == b"joystickPos":
                        if len(message) == 8:  # 2 Floats = 8 Bytes
                            x = from_network_order(message[0:4], 'f')
                            y = from_network_order(message[4:8], 'f')
                            direction = (x, y)
                            wheelchair.set_direction(direction)
                        else:
                            print(f"Warnung: joystickPos Nachricht hat falsche Länge: {len(message)} statt 8 Bytes")
                    elif topic == b"gear":
                        received_value = from_network_order(message, '?')
                        actual_gear = wheelchair.set_gear(received_value)
                        publisher_socket.send_multipart([b"gear", to_network_order(actual_gear, 'i')])
                    elif topic == b"lights":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_lights()
                        publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                        # print("lights: " + str(wheelchair.get_lights()))
                    elif topic == b"warn":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_warn()
                        publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                        # print("warn: " + str(wheelchair.get_warn()))
                    elif topic == b"horn":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_horn(received_value)
                    elif topic == b"kantelung":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_kantelung(received_value)
                        publisher_socket.send_multipart(
                            [b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    # else:
                    # print(f"Unerwartetes Topic empfangen: {topic}") # Kann sehr gesprächig sein

                # Heartbeat-Timeout-Überprüfung (VON ML2)
                if time.time() - last_heartbeat > RECONNECT_INTERVAL:  # Verwendet RECONNECT_INTERVAL (10s)
                    print("Heartbeat-Timeout VON Magic Leap! Starte Verbindung neu.")
                    break  # Beende die innere Kommunikationsschleife

                time.sleep(0.01)  # Kleine Pause, um CPU-Last zu reduzieren

            except zmq.ZMQError as e:
                print(f"Fehler in der Kommunikation (ZMQ): {e}")
                break
            except Exception as e:
                print(f"Unerwarteter Fehler in der Hauptschleife: {e}")
                break

        # --- Aufräumen beim Neustart der äußeren Schleife ---
        print("Kommunikationsschleife beendet. Server wird in Kürze neu gestartet...")
        # Sockets werden am Anfang der äußeren Schleife geschlossen und neu erstellt
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
        if 'wheelchair' in globals() and wheelchair:  # Prüfe, ob wheelchair definiert und nicht None ist
            wheelchair.shutdown()
        # Sockets werden bereits in der run_server Schleife oder durch context.term() geschlossen
        if 'context' in globals() and context and not context.closed:  # Prüfe, ob context definiert und nicht geschlossen
            print("Schließe ZeroMQ-Kontext...")
            context.term()
        print("Server vollständig beendet.")