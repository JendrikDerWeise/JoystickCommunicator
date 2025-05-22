import zmq
import subprocess
import time
import re
import netifaces
import sys
import socket  # Für UDP-Broadcast
import random
import struct
from WheelchairControlReal import WheelchairControlReal
from RearCamera import RearCamera
import os

# --- Konstanten ---
HEARTBEAT_INTERVAL = 2  # Sekunden (Heartbeat-Intervall vom *Client*)
RECONNECT_INTERVAL = 10# Sekunden (Wartezeit vor Server-Neustart)
INITIAL_CONNECTION_TIMEOUT = 30  # Sekunden (Timeout für das erste "READY"-Signal)
BROADCAST_PORT = 50000     # Port für UDP-Broadcast (optional)

# --- ZeroMQ-Kontext erstellen ---
context = zmq.Context()

# --- Globale Variablen ---
magic_leap_ip = None  # IP-Adresse der Magic Leap 2
last_heartbeat = 0    # Zeitpunkt des letzten empfangenen Heartbeats
publisher_socket = None # Publisher Socket (zum Senden von Daten)
subscriber_socket = None # Subscriber Socket (zum Empfangen von Heartbeats und READY)
wheelchair = WheelchairControlReal()

# --- Camera ---
rear_camera = None # Initialize rear_camera
camera_stream_active = False # Track camera state
MIN_REVERSE_SPEED_THRESHOLD = -0.1
last_frame_send_time = 0
VIDEO_FRAME_INTERVAL = 1.0 / 15

# --- Globale Variablen für ML2 Konfig-Senden ---
CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag" # Wie in app.py definiert
last_config_send_time = 0 # Zeitstempel des letzten Config-Sendens

JOYSTICK_VISIBILITY_TRIGGER_FILE = "/tmp/joystick_visibility_trigger.txt"
GAMEPAD_MODE_TRIGGER_FILE = "/tmp/gamepad_mode_trigger.txt"
gamepad_control_is_active_by_trigger = False

try:
    from gamepad_controller import GamepadController  # Annahme: gamepad_controller.py ist im selben Verzeichnis
except ImportError as e:
    print(f"Fehler: gamepad_controller.py nicht gefunden: {e}", file=sys.stderr)
    GamepadController = None  # Ermöglicht Start auch ohne Gamepad-Modul
    print("WARNUNG: Gamepad-Steuerung wird nicht verfügbar sein.")

gamepad_ctrl: GamepadController | None = None

def is_little_endian():
    """Überprüft, ob das System Little-Endian ist."""
    return sys.byteorder == 'little'

def to_network_order(value, data_type):
    if data_type == 'i': # Integer
      if is_little_endian():
          return struct.pack('>i', value)  # '>' für Big-Endian
      return struct.pack('i',value)
    elif data_type == 'f':  # Float
      if is_little_endian():
          return struct.pack('>f', value)
      return struct.pack('f',value)
    elif data_type == 'd':  # Double
      if is_little_endian():
        return struct.pack('>d', value)
      return struct.pack('d',value)
    elif data_type == '?': #Bool
      return struct.pack('?', value)
    else:
        raise ValueError("Ungültiger Datentyp")


def from_network_order(data, data_type):
    """Konvertiert einen Wert von Big-Endian (Network Byte Order) zum Host-System."""
    if data_type == 'i':
      if is_little_endian():
        return struct.unpack('>i', data)[0]  # '>' für Big-Endian
      return struct.unpack('i',data)[0]
    elif data_type == 'f':
       if is_little_endian():
        return struct.unpack('>f', data)[0]
       return struct.unpack('f', data)[0]
    elif data_type == 'd':
       if is_little_endian():
          return struct.unpack('>d',data)[0]
       return struct.unpack('d',data)[0]
    elif data_type == '?':
        return struct.unpack('?',data)[0]
    else:
        raise ValueError("Ungültiger Datentyp")


def get_correct_network_interface(magic_leap_ip):
    """
    Findet die Netzwerkschnittstelle des PCs, die im gleichen Subnetz wie die
    Magic Leap 2 ist.  Wird benötigt, um die *eigene* IP-Adresse des PCs zu
    bestimmen, an die der PublisherSocket gebunden werden soll.
    """
    if not magic_leap_ip:  # Stelle sicher, dass eine IP-Adresse vorhanden ist
        return None

    try:
        magic_leap_subnet = ".".join(magic_leap_ip.split(".")[:3])  # z.B. "192.168.1"
        interfaces = netifaces.interfaces()  # Liste aller Netzwerkschnittstellen
        for interface in interfaces:
            try:
                iface_details = netifaces.ifaddresses(interface)  # Details der Schnittstelle
                if netifaces.AF_INET in iface_details:  # IPv4-Adressen?
                    ipv4_details = iface_details[netifaces.AF_INET]
                    for ip_info in ipv4_details:
                        ip_address = ip_info['addr']  # IP-Adresse der Schnittstelle
                        if ip_address != '127.0.0.1':  # Loopback-Adresse ignorieren
                            interface_subnet = ".".join(ip_address.split(".")[:3])
                            if interface_subnet == magic_leap_subnet:  # Passt das Subnetz?
                                print(f"Korrekte Schnittstelle gefunden: {interface} ({ip_address})")
                                return ip_address  # Korrekte IP-Adresse zurückgeben
            except Exception as e:
                print(f"Fehler bei der Überprüfung der Schnittstelle {interface}: {e}")
                # Bei Fehlern einfach weitermachen mit der nächsten Schnittstelle
        return None  # Keine passende Schnittstelle gefunden

    except Exception as e:
        print(f"Unerwarteter Fehler in get_correct_network_interface: {e}")
        return None


def get_magic_leap_ip_adb():
    """Ermittelt die IP-Adresse der Magic Leap 2 über ADB (zuverlässiger)."""
    try:
        start_time = time.time()
        timeout = 10

        while time.time() - start_time < timeout:
            # 'adb shell ip route' gibt die Routing-Tabelle aus.
            # Die Ausgabe ist je nach Android-Version und Gerät unterschiedlich.
            # Das folgende Kommando funktioniert auf der ML2 und filtert die Ausgabe.
            result = subprocess.run(['adb', 'shell', 'ip', 'route'], capture_output=True, text=True, check=True)

            # Suche nach der Zeile, die "wlan0" oder "usb0" enthält (oder den Namen des Netzwerkadapters)
            for line in result.stdout.splitlines():
                if "dev mlnet0" or "eth1" in line:  # <---  Anpassen, falls nötig!
                    # Extrahiere die IP-Adresse nach "src"
                    match = re.search(r'src (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                    if match:
                        ip_address = match.group(1)
                        print(f"Magic Leap 2 IP-Adresse (über ip route): {ip_address}")
                        return ip_address

            time.sleep(1)  # Kurze Pause, bevor der Befehl erneut ausgeführt wird.

        print("Timeout beim Ermitteln der IP-Adresse über ADB.")
        return None

    except subprocess.CalledProcessError as e:
        print(f"Fehler bei der Ausführung von 'adb shell ip route': {e}, Rückgabecode: {e.returncode}, Ausgabe: {e.output}")
        return None
    except Exception as e:
        print(f"Unerwarteter Fehler bei der ADB-IP-Ermittlung: {e}")
        return None


def send_pc_ip_and_port(magic_leap_ip, port):
    """Schreibt die IP-Adresse des PCs *und* den Port in eine Datei."""
    try:
        correct_interface_ip = get_correct_network_interface(magic_leap_ip)
        if not correct_interface_ip:
            print("Keine passende Netzwerkschnittstelle gefunden.")
            return False

        temp_file = "pc_ip.txt"
        with open(temp_file, "w") as f:
            f.write(f"{correct_interface_ip}:{port}")  # IP und Port, getrennt durch :

        subprocess.run(['adb', 'push', temp_file, '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files'], check=True)
        print(f"PC IP-Adresse ({correct_interface_ip}) und Port ({port}) auf Magic Leap 2 kopiert.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Kopieren der Datei (adb push): {e}")
        return False
    except Exception as e:
        print(f"Fehler beim Schreiben/Kopieren der IP-Adresse und des Ports: {e}")
        return False

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

def run_server():
    """Hauptfunktion des Servers."""
    global magic_leap_ip, last_heartbeat, publisher_socket, subscriber_socket
    global rear_camera, camera_stream_active, last_frame_send_time

    while True:  # Äußere Schleife für Server-Neustart
        print("Server wird (neu)gestartet...")
        subscriber_socket = None
        publisher_socket = None
        pc_port = None
        # --- IP-Ermittlung (ADB + UDP Broadcast Fallback) ---
        magic_leap_ip = get_magic_leap_ip_adb()  # Versuche zuerst ADB

        if not magic_leap_ip:
            print("Konnte Magic Leap IP nicht ermitteln. Warte 5 Sekunden...")
            time.sleep(5)
            continue

        pc_ip = get_correct_network_interface(magic_leap_ip)
        if not pc_ip:
            print("Konnte eigene IP-Adresse nicht ermitteln. Warte 5 Sekunden...")
            time.sleep(5)
            continue

        # --- Socket-Setup (innerhalb der Schleife) ---
        try:
            publisher_socket = context.socket(zmq.PUB)
            # WICHTIG: Dynamischen Port für den PublisherSocket verwenden
            pc_port = publisher_socket.bind_to_random_port(f"tcp://{pc_ip}")  # Dynamischen Port zuweisen
            print(f"Publisher Socket (PC) gebunden an {pc_ip}:{pc_port}")

            subscriber_socket = context.socket(zmq.SUB)

            # --- Sende IP und Port an die Magic Leap 2 ---
            if not send_pc_ip_and_port(magic_leap_ip, pc_port):  # Sende IP *und* Port
                print("Konnte PC-IP und Port nicht an Magic Leap senden. Setze fort...")
                #Kein continue, da ansonsten die Sockets nicht geschlossen werden.

        except zmq.ZMQError as e:
            print(f"Socket-Fehler: {e}")
            if subscriber_socket: subscriber_socket.close()
            if publisher_socket:  publisher_socket.close()
            print(f"Fehler beim Binden/Verbinden der Sockets: {e}")
            time.sleep(RECONNECT_INTERVAL)
            continue

        print("Warte auf READY-Signal von ML2...")
        #start_time = time.time()
        ready_received = False

        while not ready_received: #and time.time() - start_time < INITIAL_CONNECTION_TIMEOUT:
            try:
                subscriber_socket.connect(f"tcp://{magic_leap_ip}:{pc_port + 1}")
                subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"READY")
                topic, message = subscriber_socket.recv_multipart()  # 1 Sekunde Timeout
                if topic == b"READY":
                    print("READY empfangen!")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")  # Wechsle zu normalen Heartbeats
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"joystickPos")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"gear")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"lights")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"warn")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"horn")
                    subscriber_socket.setsockopt(zmq.SUBSCRIBE, b"kantelung")

                    publisher_socket.send_multipart([b"gear", to_network_order(wheelchair.get_actual_gear(), 'i')])
                    publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                    publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                    ready_received = True
                    print(f"Subscriber (PC) verbunden mit ML2 an {magic_leap_ip}:{pc_port + 1}")
            except zmq.error.Again:  # Timeout beim Empfangen
                # Timeout abgelaufen, versuche erneut zu verbinden in der nächsten Iteration
                subscriber_socket.disconnect(
                f"tcp://{magic_leap_ip}:{pc_port + 1}")  # Muss getrennt werden, bevor es erneut verbunden werden kann.
                continue  # Weiter zur nächsten Iteration
            except zmq.ZMQError as e:
                print(f"Fehler beim Warten/Verbinden (ZMQ): {e}")
                if subscriber_socket: subscriber_socket.close()
                if publisher_socket:  publisher_socket.close()
                time.sleep(RECONNECT_INTERVAL)
                break  # Innere Schleife verlassen
            except Exception as e:
                print(f"Unerwarteter Fehler: {e}")
                if subscriber_socket: subscriber_socket.close()
                if publisher_socket:  publisher_socket.close()
                time.sleep(RECONNECT_INTERVAL)
                break  # Innere Schleife verlassen.
            if not ready_received:
                print("Timeout beim Warten auf Initialen Heartbeat.")
                if subscriber_socket: subscriber_socket.close()
                if publisher_socket: publisher_socket.close()
                time.sleep(RECONNECT_INTERVAL)
                continue  # Starte den Server neu.

        # --- Ende Socket-Setup ---

        # --- Konfiguration RearCam ---
        global rear_camera  # Ensure we're using the global instance
        try:
            print("Attempting to initialize RearCamera...")
            rear_camera = RearCamera()  # Use default resolution/framerate or specify
            # Test if camera can start (optional, but good for early feedback)
            if rear_camera.picam2 is None:  # Check if Picamera2 object itself failed to init
                print("WARNUNG: RearCamera Picamera2 object ist None. Kamerastreaming nicht verfügbar.")
                rear_camera = None  # Explicitly set to None if unusable
            elif not rear_camera.start_stream():
                print("WARNUNG: RearCamera konnte den Stream nicht initial starten. Kamerastreaming nicht verfügbar.")
                rear_camera.stop_stream()  # Ensure it's stopped if start failed
                # rear_camera = None # Decide if you want to disable it completely or allow retries
            else:
                print("RearCamera initial gestartet und gestoppt für Test. Bereit.")
                rear_camera.stop_stream()  # Stop it, will be activated by reverse movement
        except Exception as e_cam_init:
            print(f"WARNUNG: Kritischer Fehler bei Initialisierung der RearCamera: {e_cam_init}")
            rear_camera = None  # Disable camera functionality
        # --- Ende CamConfig ---

        # --- Hauptkommunikationsschleife (nach Empfang von READY) ---
        print("Beginne mit der Hauptkommunikation...")

        last_heartbeat = time.time()
        float_value = 0
        last_heartbeat_send = 0  # Zeitpunkt des letzten Sendens.
        last_rlink_heartbeat_send = time.time()  # NEU: Für Heartbeat ZUM Rollstuhl
        HEARTBEAT_INTERVAL_RLINK = 0.2

        while True:  # Hauptkommunikationsschleife
            try:
                process_gamepad_mode_trigger()
                # --- Sende Heartbeat (alle 2 Sekunden) ---
                if time.time() - last_heartbeat_send > HEARTBEAT_INTERVAL:
                    publisher_socket.send_multipart([b"heartbeat", b""])
                    last_heartbeat_send = time.time()  # Aktualisiere den Zeitpunkt des Sendens

                # --- Heartbeat ZUM Rollstuhl(RLink) ---
                if time.time() - last_rlink_heartbeat_send > HEARTBEAT_INTERVAL_RLINK:
                    if wheelchair.send_rlink_heartbeat():  # Rufe die neue Methode auf
                        last_rlink_heartbeat_send = time.time()
                    else:
                        print("Konnte RLink Heartbeat nicht senden, möglicherweise Verbindungsproblem.")

                if os.path.exists(JOYSTICK_VISIBILITY_TRIGGER_FILE):
                    try:
                        print(f"Trigger-Datei '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gefunden.")
                        if publisher_socket and not publisher_socket.closed:
                            print("Sende 'joystick_toggle_visibility' an ML2...")
                            publisher_socket.send_multipart([b"joystick_toggle_visibility", b""])
                            # Erfolgsmeldung oder weitere Verarbeitung
                        else:
                            print("Fehler: ZMQ Publisher-Socket nicht bereit für Joystick-Toggle.", file=sys.stderr)

                        # Trigger-Datei löschen, um erneutes Ausführen zu verhindern
                        try:
                            os.remove(JOYSTICK_VISIBILITY_TRIGGER_FILE)
                            print(f"Trigger-Datei '{JOYSTICK_VISIBILITY_TRIGGER_FILE}' gelöscht.")
                        except OSError as e_remove:
                            print(
                                f"Fehler beim Löschen der Trigger-Datei '{JOYSTICK_VISIBILITY_TRIGGER_FILE}': {e_remove}",
                                file=sys.stderr)
                    except Exception as e_trigger:
                        print(f"Fehler bei der Verarbeitung der Joystick-Sichtbarkeits-Trigger-Datei: {e_trigger}",
                              file=sys.stderr)

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
                            elif not config_json_str:  # Falls Datei leer ist
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

                speed = wheelchair.get_wheelchair_speed()
                float_value = to_network_order(speed, 'f')
                publisher_socket.send_multipart([b"topic_float", float_value])
                current_y_command = wheelchair._current_sent_y
                #publisher_socket.send_multipart([b"topic_string", string_value.encode()])

                # --- Cam activation ---

                if rear_camera and rear_camera.picam2:
                    if current_y_command < MIN_REVERSE_SPEED_THRESHOLD and not camera_stream_active:
                        if rear_camera.start_stream():
                            camera_stream_active = True
                            print("Rear camera stream started due to reverse movement.")
                            publisher_socket.send_multipart([b"rear_camera_status", b"STARTING"])
                    elif current_y_command >= MIN_REVERSE_SPEED_THRESHOLD and camera_stream_active:
                        rear_camera.stop_stream()
                        camera_stream_active = False
                        print("Rear camera stream stopped.")
                        publisher_socket.send_multipart([b"rear_camera_status", b"STOPPED"])

                    # Rate-limit video frame sending
                    if camera_stream_active and (time.time() - last_frame_send_time > VIDEO_FRAME_INTERVAL):
                        frame = rear_camera.get_frame()
                        if frame:
                            publisher_socket.send_multipart([b"rear_video_stream", frame])
                            last_frame_send_time = time.time()  # Aktualisiere den Zeitpunkt des letzten Sendens
                        # else:
                        # print("Failed to get frame from rear camera")

                # Empfange Nachrichten (mit Timeout)
                if subscriber_socket.poll(10):  # 1 Sekunde Timeout
                    topic, message = subscriber_socket.recv_multipart()

                    if topic == b"heartbeat":
                        last_heartbeat = time.time()
                        print("Heartbeat empfangen")
                    elif topic == b"joystickPos":
                        x = from_network_order(message[0:4], 'f')
                        y = from_network_order(message[4:8], 'f')

                        direction = (x, y)
                        if not gamepad_control_is_active_by_trigger:
                            wheelchair.set_direction(direction)
                    elif topic == b"gear":
                        received_value = from_network_order(message, '?')
                        actual_gear = wheelchair.set_gear(received_value)
                        publisher_socket.send_multipart([b"gear", to_network_order(actual_gear, 'i')])
                    elif topic == b"lights":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_lights()
                        publisher_socket.send_multipart([b"lights", to_network_order(wheelchair.get_lights(), '?')])
                        print("lights: " + str(wheelchair.get_lights()))
                    elif topic == b"warn":
                        received_value = from_network_order(message, '?')
                        wheelchair.set_warn()
                        publisher_socket.send_multipart([b"warn", to_network_order(wheelchair.get_warn(), '?')])
                        print("warn: " + str(wheelchair.get_warn()))
                    elif topic == b"horn":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_horn(received_value)
                    elif topic == b"kantelung":
                        received_value = from_network_order(message, '?')
                        wheelchair.on_kantelung(received_value)
                        publisher_socket.send_multipart([b"kantelung", to_network_order(wheelchair.get_kantelung(), '?')])
                    else:
                        print(f"Unerwartetes Topic: {topic}")

                # Heartbeat-Timeout-Überprüfung
                if time.time() - last_heartbeat > RECONNECT_INTERVAL:
                    print("Heartbeat-Timeout!")
                    break  # Beende die Hauptschleife

            except zmq.ZMQError as e:
                print(f"Fehler in der Kommunikation: {e}")
                break  # Beende die Hauptschleife
            except Exception as e:
                print(f"Unerwarteter Fehler: {e}")
                break # Beende die Hauptschleife.

        # --- Aufräumen beim Neustart ---
        print("Server wird in Kürze neu gestartet...")
        try:
            if subscriber_socket:
                subscriber_socket.close()
            if publisher_socket:
                publisher_socket.close()
        except Exception as e:
             print(f"Fehler beim Schließen der Sockets: {e}")
        time.sleep(RECONNECT_INTERVAL)


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
        if rear_camera:  # Ensure camera is stopped if server loop breaks
            rear_camera.stop_stream()

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