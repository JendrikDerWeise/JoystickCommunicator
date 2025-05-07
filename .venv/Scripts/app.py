# server.py (Erweitert um Konfigurations-Interface)

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash # flash hinzugefügt
import subprocess
import os
import json # NEU für Konfiguration
import sys # Für sys.exit falls nötig (optional)

# --- Konfiguration für Rollstuhl-Parameter ---
CONFIG_FILE = "wheelchair_config.json" # Name der Speicherdatei (im selben Verzeichnis wie server.py)
DEFAULT_CONFIG = {
    "gear_factors": {
        "1": 0.2, "2": 0.4, "3": 0.6, "4": 0.8, "5": 1.0
    },
    "acceleration_step": 10.0 # Float erlauben für feinere Schritte
}

# --- Flask App Initialisierung ---
app = Flask(__name__)
# Wichtig für Flash-Nachrichten (Bestätigungen/Fehler im Webinterface)
app.secret_key = os.urandom(24) # Sicherer Zufallskey

# --- Bestehende Konfiguration für Magic Leap Kommunikation ---
# Pfad zur Datei auf dem Raspberry Pi
DATA_FILE_PI = "data.txt"
# Pfad zur Datei auf der Magic Leap 2 (anpassen!)
DATA_FILE_ML2 = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/data.txt'
# Initiale Befehlswörter (oder Standardwerte für die Textfelder)
init_commands = {
    "joystick": "Steuerung Aktivieren",
    "lights": "Licht AN/AUS",
    "warn": "Warnblinker AN/AUS",
    "hornOn": "Hupe AN",
    "hornOff": "Hupe AUS",
    "kantelungOn": "Sitzk. AN",
    "kantelungOff": "Sitzk. AUS",
    "gearUp": "Schneller",
    "gearDown": "Langsamer",
    "language": "Deutsch" # Beispiel
}

# --- Hilfsfunktionen für JSON Konfiguration ---
def load_config(filepath, defaults):
    """Lädt Konfiguration aus JSON-Datei oder gibt Defaults zurück."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)
                # --- Robustere Prüfung & Ergänzung fehlender Werte ---
                if not isinstance(config, dict): # Prüfen ob überhaupt ein Dictionary geladen wurde
                    print(f"Warnung: {filepath} enthält kein valides JSON-Objekt. Verwende Defaults.")
                    return defaults.copy()

                if "gear_factors" not in config or not isinstance(config["gear_factors"], dict):
                    config["gear_factors"] = defaults["gear_factors"].copy()
                else: # Stelle sicher, dass alle Gänge 1-5 existieren & numerisch sind
                    default_gears = defaults["gear_factors"]
                    current_gears = config["gear_factors"]
                    for i in range(1, 6):
                        key = str(i)
                        if key not in current_gears:
                            current_gears[key] = default_gears.get(key, 0.2 * i) # Füge fehlenden Gang hinzu
                        else:
                             try: # Konvertiere zu float, falls es als String gespeichert wurde
                                  current_gears[key] = float(current_gears[key])
                                  # Optional: Wertebereich prüfen
                                  current_gears[key] = max(0.0, min(1.0, current_gears[key]))
                             except (ValueError, TypeError):
                                  print(f"Warnung: Ungültiger Wert für Gang {key} in {filepath} gefunden. Setze Default.")
                                  current_gears[key] = default_gears.get(key, 0.2 * i)

                if "acceleration_step" not in config:
                    config["acceleration_step"] = defaults["acceleration_step"]
                else:
                    try: # Konvertiere zu float
                         config["acceleration_step"] = float(config["acceleration_step"])
                         if config["acceleration_step"] <= 0: # Muss positiv sein
                              print(f"Warnung: Ungültiger Wert für acceleration_step in {filepath}. Setze Default.")
                              config["acceleration_step"] = defaults["acceleration_step"]
                    except (ValueError, TypeError):
                         print(f"Warnung: Ungültiger Wert für acceleration_step in {filepath}. Setze Default.")
                         config["acceleration_step"] = defaults["acceleration_step"]

                return config
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warnung: Fehler beim Laden von {filepath}: {e}. Verwende Defaults.")
            return defaults.copy()
    else:
        print(f"Info: Konfigurationsdatei {filepath} nicht gefunden. Verwende Defaults.")
        return defaults.copy()

def save_config(filepath, config_data):
    """Speichert Konfiguration als JSON-Datei."""
    try:
        with open(filepath, 'w') as f:
            json.dump(config_data, f, indent=4)
        print(f"Konfiguration erfolgreich in {filepath} gespeichert.")
        return True
    except IOError as e:
        print(f"Fehler beim Speichern von {filepath}: {e}", file=sys.stderr)
        return False

# --- Bestehende Flask Routen ---

@app.before_request
def check_for_captive_portal():
    # --- Diese Logik bleibt unverändert ---
    expected_host = "192.168.4.1"
    allowed_hosts = [expected_host, "localhost", "127.0.0.1"]
    host_received = request.host.split(':')[0]
    expected_url_root = f'http://{expected_host}/'
    if not request.url.startswith(expected_url_root) and host_received not in allowed_hosts :
        app.logger.warning(f"--> Captive portal redirect triggered for host: {request.host}")
        return redirect(f'http://{expected_host}/')

@app.route("/")
def index():
    """Zeigt die Hauptseite an (ML2 Daten holen/anzeigen)."""
    initial_data = {}
    print("Lade Daten für Indexseite von ML2...") # Info
    try:
        # Daten von ML2 holen
        pull_result = subprocess.run(
            ["adb", "pull", DATA_FILE_ML2, DATA_FILE_PI],
            capture_output=True, text=True, check=False, timeout=5 # Kürzerer Timeout?
        )

        if pull_result.returncode != 0:
            print(f"Warnung: Fehler beim adb pull ({pull_result.returncode}): {pull_result.stderr or 'Kein stderr'}")
            if os.path.exists(DATA_FILE_PI):
                 print(f"Info: Verwende lokal vorhandene Datei {DATA_FILE_PI}")
                 # Lese lokale Datei, falls pull fehlschlägt aber Datei existiert
                 with open(DATA_FILE_PI, "r") as f:
                     lines = [line.strip() for line in f.readlines()]
            else:
                 print(f"Info: Weder Pull erfolgreich noch lokale Datei {DATA_FILE_PI} vorhanden. Verwende Init-Werte.")
                 lines = list(init_commands.values()) # Nutze Werte aus init_commands
        else:
            print(f"Info: adb pull erfolgreich.")
            with open(DATA_FILE_PI, "r") as f:
                 lines = [line.strip() for line in f.readlines()]

        # Stelle sicher, dass genügend Zeilen vorhanden sind, fülle mit Defaults auf
        keys = list(init_commands.keys())
        default_values = list(init_commands.values())
        while len(lines) < len(keys):
            lines.append(default_values[len(lines)])

        # Erstelle Dictionary dynamisch
        initial_data = dict(zip(keys, lines))
        # Korrigiere den Sprach-Key, falls nötig
        if "language" not in initial_data:
             initial_data["language"] = default_values[keys.index("language")]


    except subprocess.TimeoutExpired:
        print("Fehler: ADB pull timed out.", file=sys.stderr)
        initial_data = init_commands.copy() # Nutze Defaults
    except FileNotFoundError:
         print("Fehler: 'adb' Kommando nicht gefunden. Ist ADB installiert und im PATH?", file=sys.stderr)
         initial_data = init_commands.copy() # Nutze Defaults
    except Exception as e:
        print(f"Fehler beim Laden/Verarbeiten der Daten für Index: {e}", file=sys.stderr)
        initial_data = init_commands.copy() # Nutze Defaults

    # Rendere das Template für die ML2-Konfiguration
    return render_template("index.html", data=initial_data)

@app.route("/save", methods=["POST"])
def save_data():
    """Speichert die Daten für die ML2 und überträgt sie."""
    try:
        # Extrahiere alle erwarteten Formularfelder
        form_data = [
            request.form.get("joystick", ""), request.form.get("lights", ""),
            request.form.get("warn", ""), request.form.get("hornOn", ""),
            request.form.get("hornOff", ""), request.form.get("kantelungOn", ""),
            request.form.get("kantelungOff", ""), request.form.get("gearUp", ""),
            request.form.get("gearDown", ""), request.form.get("language", "English")
        ]

        # Daten in lokale Datei schreiben
        with open(DATA_FILE_PI, "w") as f:
            for item in form_data:
                 f.write(item + "\n")

        # Daten an ML2 übertragen
        print(f"Versuche adb push {DATA_FILE_PI} nach {DATA_FILE_ML2}")
        push_result = subprocess.run(
            ["adb", "push", DATA_FILE_PI, DATA_FILE_ML2],
            capture_output=True, text=True, check=True, timeout=10
        )
        print(f"ADB push stdout: {push_result.stdout or 'Kein Output'}")
        return jsonify({"success": True, "message": "Daten gespeichert und übertragen!", "output": push_result.stdout})

    except subprocess.CalledProcessError as e:
        print(f"ADB push error: {e.stderr}", file=sys.stderr)
        return jsonify({"success": False, "message": "Fehler bei Übertragung: " + (e.stderr or 'Kein stderr'), "output": ""})
    except subprocess.TimeoutExpired:
        print("Fehler: ADB push timed out.", file=sys.stderr)
        return jsonify({"success": False, "message": "ADB push timed out.", "output":""})
    except FileNotFoundError:
         print("Fehler: 'adb' Kommando nicht gefunden.", file=sys.stderr)
         return jsonify({"success": False, "message": "Fehler: ADB nicht gefunden.", "output":""})
    except Exception as e:
        print(f"Unerwarteter Fehler beim Speichern/Senden: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "Fehler beim Speichern: " + str(e), "output":""})

# --- NEUE Routen für Rollstuhl-Konfiguration ---

@app.route('/config', methods=['GET'])
def show_config():
    """Zeigt das Konfigurationsformular für den Rollstuhl an."""
    current_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    # Übergebe Konfig an das *neue* Template 'config.html'
    return render_template('config.html', config=current_config)

@app.route('/save_config', methods=['POST'])
def save_config_route():
    """Empfängt die Formulardaten für Rollstuhl-Konfig und speichert sie."""
    try:
        config = load_config(CONFIG_FILE, DEFAULT_CONFIG) # Lade aktuelle Config
        new_gear_factors = {}
        valid = True

        # Lese und validiere Gang-Faktoren
        for i in range(1, 6):
            key = f'gear{i}'; factor_str = request.form.get(key)
            if factor_str is None:
                flash(f"Fehlender Wert für Gang {i}.", "error"); valid = False; continue
            try:
                factor = float(factor_str)
                if 0.0 <= factor <= 1.0: new_gear_factors[str(i)] = factor
                else: flash(f"Ungültiger Wert für Gang {i} (0.0-1.0).", "error"); valid = False
            except ValueError: flash(f"Ungültiger Zahlenwert für Gang {i}.", "error"); valid = False

        # Lese und validiere Beschleunigung
        new_accel_step = config["acceleration_step"] # Behalte alten Wert bei Fehler
        accel_str = request.form.get('acceleration')
        if accel_str is None:
             flash("Fehlender Wert für Beschleunigung.", "error"); valid = False
        else:
            try:
                accel = float(accel_str)
                if accel > 0: new_accel_step = accel
                else: flash("Beschleunigung muss > 0 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Zahlenwert für Beschleunigung.", "error"); valid = False

        # Speichern, wenn alles gültig war
        if valid:
            config["gear_factors"] = new_gear_factors
            config["acceleration_step"] = new_accel_step
            if save_config(CONFIG_FILE, config):
                flash("Einstellungen erfolgreich gespeichert!", "success")
            else:
                flash("Fehler beim Speichern der Einstellungen.", "error")
        else:
             flash("Einstellungen nicht gespeichert (ungültige Werte).", "warning")

    except Exception as e:
        flash(f"Unerwarteter Fehler beim Speichern: {e}", "error")
        print(f"Unerwarteter Fehler in /save_config: {e}", file=sys.stderr) # Logge Fehler serverseitig

    # Leite immer zurück zur Konfigurationsseite
    return redirect(url_for('show_config'))

# --- ENDE NEUE Routen ---


# --- Server Start ---
if __name__ == "__main__":
    print("Starte kombinierten Flask Server (ML2-Konfig + Rollstuhl-Konfig)...")
    # Initialisiere Rollstuhl-Konfigurationsdatei, falls nicht vorhanden
    initial_wheelchair_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    save_config(CONFIG_FILE, initial_wheelchair_config)

    print("\nÖffne einen Webbrowser und gehe zu:")
    print(f"http://<IP-Adresse-des-Pi>:80/       (für ML2-Konfiguration)")
    print(f"http://<IP-Adresse-des-Pi>:80/config (für Rollstuhl-Parameter)")
    print("(Drücke Strg+C zum Beenden)")
    try:
        # Port 80 erfordert oft Root-Rechte oder spezielle Konfigurationen
        app.run(host="0.0.0.0", port=80, debug=False)
    except OSError as e:
        if e.errno == 98 or "Address already in use" in str(e): # Fehlercode für Linux/Windows
             print(f"\nFEHLER: Port 80 wird bereits verwendet.", file=sys.stderr)
        elif e.errno == 13 or "Permission denied" in str(e):
             print(f"\nFEHLER: Keine Berechtigung für Port 80.", file=sys.stderr)
             print("Versuche das Skript mit 'sudo python3 server.py' zu starten oder einen Port > 1024 zu verwenden.", file=sys.stderr)
        else:
             print(f"\nFEHLER beim Starten des Servers: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nAllgemeiner FEHLER beim Starten des Servers: {e}", file=sys.stderr)