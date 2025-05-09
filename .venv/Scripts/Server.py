import zmq
import subprocess
import time
import re
import netifaces
import sys
import os # Hinzugefügt für os.path.exists und os.path.getmtime
import json # Hinzugefügt für das Lesen der JSON-Konfig (falls nötig, aktuell liest Trigger-File)
import struct
from WheelchairControlReal import WheelchairControlReal

# --- Konstanten ---
HEARTBEAT_INTERVAL_FROM_ML2 = 2  # Sekunden (Erwartetes Heartbeat-Intervall VOM Client/ML2)
RECONNECT_INTERVAL = 10 # Sekunden (Wartezeit vor Server-Neustart)
# INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal) # Nicht mehr explizit so verwendet
BROADCAST_PORT = 50000     # Port für UDP-Broadcast (optional)

HEARTBEAT_INTERVAL_TO_ML2 = 2 # Sekunden (Wie oft Pi Heartbeat AN ML2 sendet) # --- KORREKTUR/NEU ---
RLINK_HEARTBEAT_INTERVAL = 0.2 # Sekunden (Wie oft RLink Heartbeat gesendet wird) # --- KORREKTUR/NEU ---

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()

# --- Globale Variablen ---
magic_leap_ip = None
last_heartbeat_from_ml2 = 0 # Zeitpunkt des letzten empfangenen Heartbeats von ML2
publisher_socket = None
subscriber_socket = None
wheelchair = WheelchairControlReal()

CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag" # Datei, die von app.py erstellt wird
last_config_send_time = 0 # Zeitstempel des letzten Config-Sendens

# --- Funktionen (is_little_endian, to_network_order, from_network_order bleiben unverändert) ---
def is_little_endian():
    return sys.byteorder == 'little'

def to_network_order(value, data_type):
    # ... (Code wie zuvor)
    if data_type == 'i':
      if is_little_endian(): return struct.pack('>i', value)
      return struct.pack('i',value)
    elif data_type == 'f':
      if is_little_endian(): return struct.pack('>f', value)
      return struct.pack('f',value)
    elif data_type == 'd':
      if is_little_endian(): return struct.pack('>d', value)
      return struct.pack('d',value)
    elif data_type == '?':
      return struct.pack('?', value)
    else: raise ValueError("Ungültiger Datentyp")

def from_network_order(data, data_type):
    # ... (Code wie zuvor)
    if data_type == 'i':
      if is_little_endian(): return struct.unpack('>i', data)[0]
      return struct.unpack('i',data)[0]
    elif data_type == 'f':
       if is_little_endian(): return struct.unpack('>f', data)[0]
       return struct.unpack('f', data)[0]
    elif data_type == 'd':
       if is_little_endian(): return struct.unpack('>d',data)[0]
       return struct.unpack('d',data)[0]
    elif data_type == '?':
        return struct.unpack('?',data)[0]
    else: raise ValueError("Ungültiger Datentyp")

def get_correct_network_interface(magic_leap_ip_addr): # Umbenannt zur Klarheit
    # ... (Code wie zuvor) ...
    if not magic_leap_ip_addr: return None
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
            except Exception as e: print(f"Fehler bei Überprüfung der Schnittstelle {interface}: {e}")
        print("Warnung: Keine passende Netzwerkschnittstelle für Subnetz von ML2 gefunden.")
        # Fallback: Versuche, eine beliebige nicht-loopback IP zu finden
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in iface_details:
                    for ip_info in iface_details[netifaces.AF_INET]:
                        ip_address = ip_info['addr']
                        if ip_address != '127.0.0.1' and not ip_address.startswith("172."): # Ignoriere Docker etc.
                             print(f"Fallback-Schnittstelle verwendet: {interface} ({ip_address})")
                             return ip_address
            except: pass
        return None
    except Exception as e: print(f"Unerwarteter Fehler in get_correct_network_interface: {e}"); return None


def get_magic_leap_ip_adb():
    # ... (Code wie zuvor, aber mit Korrektur) ...
    try:
        start_time = time.time(); timeout = 10
        while time.time() - start_time < timeout:
            result = subprocess.run(['adb', 'shell', 'ip', 'route'], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                # --- KORREKTUR der Bedingung ---
                if "dev mlnet0" in line or "eth1" in line or "wlan0" in line: # Typische Interface-Namen, erweitere bei Bedarf
                # --- ENDE KORREKTUR ---
                    match = re.search(r'src (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                    if match:
                        ip_address = match.group(1)
                        print(f"Magic Leap 2 IP-Adresse (über ip route): {ip_address}")
                        return ip_address
            time.sleep(1)
        print("Timeout beim Ermitteln der IP-Adresse über ADB."); return None
    except subprocess.CalledProcessError as e: print(f"Fehler bei 'adb shell ip route': {e}, Code: {e.returncode}, Out: {e.output}"); return None
    except Exception as e: print(f"Unerwarteter Fehler bei ADB-IP-Ermittlung: {e}"); return None

def send_pc_ip_and_port(ml_ip, pc_port_to_send): # Umbenannt zur Klarheit
    # ... (Code wie zuvor) ...
    try:
        correct_interface_ip = get_correct_network_interface(ml_ip)
        if not correct_interface_ip: print("Keine passende Netzwerkschnittstelle für PC-IP gefunden."); return False
        temp_file = "pc_ip.txt"
        with open(temp_file, "w") as f: f.write(f"{correct_interface_ip}:{pc_port_to_send}")
        # Pfad für adb push anpassen, falls nötig
        adb_target_path = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/pc_ip.txt'
        subprocess.run(['adb', 'push', temp_file, adb_target_path], check=True)
        print(f"PC IP ({correct_interface_ip}) und Port ({pc_port_to_send}) auf ML2 kopiert nach {adb_target_path}.")
        return True
    except subprocess.CalledProcessError as e: print(f"Fehler beim Kopieren (adb push): {e}"); return False
    except Exception as e: print(f"Fehler beim Schreiben/Kopieren der IP/Ports: {e}"); return False


def run_server():
    global magic_leap_ip, last_heartbeat_from_ml2, publisher_socket, subscriber_socket, last_config_send_time

    while True:
        print("Server wird (neu)gestartet...")
        # Sockets und Variablen zurücksetzen
        if subscriber_socket: subscriber_socket.close(linger=0)
        if publisher_socket: publisher_socket.close(linger=0)
        subscriber_socket = None; publisher_socket = None
        pc_pub_port = None
        magic_leap_ip = None
        last_heartbeat_from_ml2 = 0
        last_config_send_time = 0 # Reset, um Config beim Neustart zu senden

        magic_leap_ip = get_magic_leap_ip_adb()
        if not magic_leap_ip: print("Konnte Magic Leap IP nicht ermitteln. Warte..."); time.sleep(5); continue

        pc_ip_for_binding = get_correct_network_interface(magic_leap_ip)
        if not pc_ip_for_binding:
             pc_ip_for_binding = "0.0.0.0" # Binde an alle Interfaces als Fallback
             print(f"Konnte spezifische PC-IP nicht ermitteln, binde Publisher an {pc_ip_for_binding}.")
        #else: # Dies ist nur die IP für das Binden, nicht die, die gesendet wird.
             # pc_ip_to_send_to_ml2 = pc_ip_for_binding # Ist das korrekt? Nein, get_correct_network_interface für send_pc_ip

        try:
            publisher_socket = context.socket(zmq.PUB)
            pc_pub_port = publisher_socket.bind_to_random_port(f"tcp://{pc_ip_for_binding}")
            print(f"Publisher Socket (PC) gebunden an {pc_ip_for_binding}:{pc_pub_port}")

            # IP und Port des *Publishers* an ML2 senden, damit ML2 *diesen* abonnieren kann
            # Der Subscriber der ML2 verbindet sich dann mit pc_ip_to_send_to_ml2:pc_pub_port
            if not send_pc_ip_and_port(magic_leap_ip, pc_pub_port): # Sende Port des Publishers
                print("Konnte PC-IP und Publisher-Port nicht an Magic Leap senden. Fehler möglich.")
                # Hier nicht abbrechen, vielleicht klappt es trotzdem, wenn ML2 die IP schon kennt

            # Subscriber Socket für Nachrichten VON der ML2
            subscriber_socket = context.socket(zmq.SUB)
            # ML2 publiziert auf pc_pub_port + 1 (Konvention)
            ml2_pub_address = f"tcp://{magic_leap_ip}:{pc_pub_port + 1}"
            print(f"Versuche Subscriber (PC) mit ML2 Publisher zu verbinden an {ml2_pub_address}...")

            # Warten auf READY von ML2
            print("Warte auf READY-Signal von ML2...")
            ready_received = False
            subscriber_socket.connect(ml2_pub_address) # Einmal verbinden
            subscriber_socket.setsockopt(zmq.RCVTIMEO, 5000) # 5 Sekunden Timeout für recv

            # Erster READY Empfang
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
            try:
                topic, message = subscriber_socket.recv_multipart()
                if topic == b"READY":
                    print("READY von ML2 empfangen!")
                    ready_received = True
                else:
                    print(f"Unerwartetes Topic statt READY: {topic}")
            except zmq.error.Again:
                print("Timeout beim Warten auf READY von ML2.")
            except zmq.ZMQError as e:
                print(f"ZMQ Fehler beim Warten auf READY: {e}")
            except Exception as e:
                print(f"Allg. Fehler beim Warten auf READY: {e}")

            if not ready_received:
                print("Verbindung zu ML2 konnte nicht initial hergestellt werden (kein READY). Neustart...")
                subscriber_socket.disconnect(ml2_pub_address) # Wichtig vor erneutem connect in nächster Iteration
                time.sleep(RECONNECT_INTERVAL)
                continue # Zum Anfang der äußeren while-Schleife

            # Abonnieren der regulären Topics NACH READY
            print("Abonniere reguläre Topics...")
            subscriber_socket.setsockopt(zmq.UNSUBSCRIBE, b"READY") # READY nicht mehr nötig
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
            # ... (andere Topics wie zuvor) ...
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
            subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")

            # Initiale Status-Infos an ML2 senden
            try:
                publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                publisher_socket.send_multipart([b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')]) # Sende aktuellen Gang
            except Exception as e: print(f"Fehler beim Senden initialer Status-Infos: {e}")


        except zmq.ZMQError as e:
            print(f"Socket-Setup Fehler: {e}")
            time.sleep(RECONNECT_INTERVAL); continue
        except Exception as e:
            print(f"Allg. Fehler im Setup: {e}")
            time.sleep(RECONNECT_INTERVAL); continue


        # --- Hauptkommunikationsschleife ---
        print("Beginne mit der Hauptkommunikation...")
        last_heartbeat_from_ml2 = time.time() # Initialisiere Heartbeat-Zeitstempel
        last_heartbeat_to_ml2_send_time = 0
        last_rlink_heartbeat_send_time = time.time()

        while True:
            try:
                # --- Heartbeat AN Magic Leap senden ---
                if time.time() - last_heartbeat_to_ml2_send_time > HEARTBEAT_INTERVAL_TO_ML2:
                    if publisher_socket: publisher_socket.send_multipart([b"heartbeat", b"pi_is_alive"])
                    last_heartbeat_to_ml2_send_time = time.time()

                # --- Heartbeat ZUM Rollstuhl (RLink) senden ---
                if time.time() - last_rlink_heartbeat_send_time > RLINK_HEARTBEAT_INTERVAL:
                    if not wheelchair.send_rlink_heartbeat(): # Verwendet die Methode aus WheelchairControlReal
                        print("Warnung: RLink Heartbeat konnte nicht gesendet werden.")
                    last_rlink_heartbeat_send_time = time.time()

                # --- NEU: ML2 Joystick-Konfiguration senden (falls getriggert) ---
                if os.path.exists(CONFIG_TRIGGER_FILE):
                    try:
                        trigger_timestamp = os.path.getmtime(CONFIG_TRIGGER_FILE)
                        if trigger_timestamp > last_config_send_time:
                            with open(CONFIG_TRIGGER_FILE, 'r') as f:
                                config_json_str = f.read()
                            if config_json_str and publisher_socket:
                                print(f"Sende ML2 Joystick Konfiguration (Länge: {len(config_json_str)})...")
                                publisher_socket.send_multipart([b"joystick_settings", config_json_str.encode('utf-8')])
                                last_config_send_time = trigger_timestamp
                                # Trigger-Datei löschen, um nicht ständig zu senden
                                try:
                                    os.remove(CONFIG_TRIGGER_FILE)
                                    print("Trigger-Datei für ML2-Konfig gelöscht.")
                                except OSError as e_remove:
                                    print(f"Fehler beim Löschen der Trigger-Datei: {e_remove}")
                            elif not config_json_str:
                                print("Trigger-Datei ist leer, lösche sie.")
                                os.remove(CONFIG_TRIGGER_FILE) # Leere Datei auch löschen
                    except FileNotFoundError:
                        pass # Falls Datei zwischen exists und open gelöscht wurde
                    except Exception as e_config:
                        print(f"Fehler beim Lesen/Senden der ML2 Joystick Konfiguration: {e_config}")
                # --- ENDE NEU ---

                # --- Statusdaten an ML2 senden (z.B. Geschwindigkeit) ---
                if publisher_socket:
                    speed = wheelchair.get_wheelchair_speed()
                    speed_bytes = to_network_order(speed, 'f')
                    publisher_socket.send_multipart([b"wheelchair_speed", speed_bytes])

                # --- Nachrichten von ML2 empfangen ---
                # Verwende poll mit kurzem Timeout, um die Schleife nicht zu blockieren
                if subscriber_socket and subscriber_socket.poll(10): # 10ms Timeout
                    topic, message_data = subscriber_socket.recv_multipart() # Umbenannt von 'message'

                    if topic == b"heartbeat":
                        last_heartbeat_from_ml2 = time.time()
                        # print("Heartbeat von ML2 empfangen") # Kann sehr häufig sein
                    elif topic == b"joystickPos":
                        # Annahme: message_data ist ein Byte-Array mit 2 Floats (je 4 Bytes)
                        if len(message_data) == 8:
                            x = from_network_order(message_data[0:4], 'f')
                            y = from_network_order(message_data[4:8], 'f')
                            direction = (x, y)
                            wheelchair.set_direction(direction)
                        else:
                            print(f"Warnung: joystickPos Nachricht hat falsche Länge: {len(message_data)}")
                    # ... (andere Topic-Verarbeitungen wie zuvor für gear, lights, etc.) ...
                    elif topic == b"gear":
                        received_value = from_network_order(message_data, '?'); actual_gear = wheelchair.set_gear(received_value)
                        if publisher_socket: publisher_socket.send_multipart([b"gear", to_network_order(actual_gear, 'i')])
                    elif topic == b"lights":
                        from_network_order(message_data, '?'); wheelchair.set_lights()
                        if publisher_socket: publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                    elif topic == b"warn":
                        from_network_order(message_data, '?'); wheelchair.set_warn()
                        if publisher_socket: publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                    elif topic == b"horn":
                        wheelchair.on_horn(from_network_order(message_data, '?'))
                    elif topic == b"kantelung":
                        wheelchair.on_kantelung(from_network_order(message_data, '?'))
                        if publisher_socket: publisher_socket.send_multipart([b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    # else: print(f"Unerwartetes Topic: {topic}") # Kann bei vielen Topics stören

                # --- Heartbeat-Timeout-Überprüfung (für Verbindung ZUR ML2) ---
                if time.time() - last_heartbeat_from_ml2 > RECONNECT_INTERVAL: # Verwendet jetzt RECONNECT_INTERVAL (10s)
                    print("Heartbeat-Timeout von Magic Leap! Starte Verbindung neu.")
                    break  # Beende die innere Kommunikationsschleife, um Neuverbindung zu triggern

                time.sleep(0.01) # Kurze Pause, um CPU-Last zu reduzieren, aber reaktiv bleiben

            except zmq.ZMQError as e: print(f"ZMQ-Fehler in Kommunikation: {e}"); break
            except Exception as e: print(f"Unerwarteter Fehler in Kommunikation: {e}"); break

        # --- Aufräumen vor Server-Neustart der äußeren Schleife ---
        print("Kommunikationsschleife beendet. Schließe Sockets und starte Server neu...")
        # Sockets werden am Anfang der äußeren Schleife geschlossen und neu erstellt

if __name__ == "__main__":
    # Stelle sicher, dass der Rollstuhl bei einem unsauberen Beenden gestoppt wird
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nServer durch Benutzer (Strg+C) beendet.")
    except Exception as e:
        print(f"\nKritischer Fehler im Server: {e}")
    finally:
        print("Führe finale Aufräumarbeiten durch...")
        if wheelchair: # Globale Variable
            wheelchair.shutdown()
        if context: # Globale Variable
            context.term()
        print("Server vollständig beendet.")