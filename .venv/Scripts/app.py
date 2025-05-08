# server.py (Vollständig, mit ML2-Konfig, Rollstuhl-Konfig und Captive Portal Check - Finaler Versuch!)

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import subprocess
import os
import json
import sys

# --- Konfiguration für Rollstuhl-Parameter ---
CONFIG_FILE = "wheelchair_config.json" # Name der Speicherdatei
DEFAULT_CONFIG = {
    "gear_factors": {
        "1": 0.2, "2": 0.4, "3": 0.6, "4": 0.8, "5": 1.0
    },
    "acceleration_step": 2.0, # Float erlauben
    "pi_side_deadzone": 0.1,  # Standardwert für Pi Deadzone
    "min_rlink_command": 10   # Standardwert für minimale Ansteuerung
}

# --- Flask App Initialisierung ---
app = Flask(__name__)
# Wichtig für Flash-Nachrichten
app.secret_key = os.urandom(24) # Sicherer Zufallskey

# --- Bestehende Konfiguration für Magic Leap Kommunikation ---
DATA_FILE_PI = "data.txt"
# WICHTIG: Pfad an deine Struktur auf der ML2 anpassen!
DATA_FILE_ML2 = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/data.txt'
init_commands = { # Wird nur noch für / (ML2 Config) benötigt
    "joystick": "Steuerung Aktivieren", "lights": "Licht AN/AUS", "warn": "Warnblinker AN/AUS",
    "hornOn": "Hupe AN", "hornOff": "Hupe AUS", "kantelungOn": "Sitzk. AN",
    "kantelungOff": "Sitzk. AUS", "gearUp": "Schneller", "gearDown": "Langsamer",
    "language": "Deutsch"
}

# --- Hilfsfunktionen für JSON Konfiguration ---
def load_config(filepath, defaults):
    """Lädt Konfiguration aus JSON oder gibt Defaults zurück (erweitert)."""
    config = defaults.copy() # Starte immer mit Defaults
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)
                if not isinstance(loaded_data, dict):
                    print(f"Warnung: {filepath} enthält kein valides JSON-Objekt. Verwende Defaults.")
                    return config # Gib ursprüngliche Defaults zurück

                # Lade und validiere bekannte Schlüssel
                # Gear Factors
                loaded_gears = loaded_data.get("gear_factors")
                if isinstance(loaded_gears, dict):
                    valid_gears = {}
                    for i in range(1, 6):
                        key = str(i)
                        try:
                            # Nutze get() auch für defaults, falls key dort fehlt
                            default_val = defaults["gear_factors"].get(key, 0.2 * i)
                            val = float(loaded_gears.get(key, default_val))
                            valid_gears[key] = max(0.0, min(1.0, val)) # Clamp 0-1
                        except (ValueError, TypeError):
                            valid_gears[key] = defaults["gear_factors"].get(key, 0.2 * i)
                    config["gear_factors"] = valid_gears

                # Acceleration Step
                try:
                     val = float(loaded_data.get("acceleration_step", defaults["acceleration_step"]))
                     if val >= 0.1: config["acceleration_step"] = val # Mindestens 0.1
                     else: config["acceleration_step"] = defaults["acceleration_step"]
                except (ValueError, TypeError): pass # Lasse Default drin

                # Pi Side Deadzone
                try:
                     val = float(loaded_data.get("pi_side_deadzone", defaults["pi_side_deadzone"]))
                     config["pi_side_deadzone"] = max(0.0, min(0.95, val)) # Clamp 0 bis <1
                except (ValueError, TypeError): pass

                # Min RLink Command
                try:
                     val = int(loaded_data.get("min_rlink_command", defaults["min_rlink_command"]))
                     config["min_rlink_command"] = max(1, min(50, val)) # Clamp 1 bis 50
                except (ValueError, TypeError): pass

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warnung: Fehler beim Laden von {filepath}: {e}. Verwende Defaults.")
    else:
        print(f"Info: Konfigurationsdatei {filepath} nicht gefunden. Verwende Defaults.")
    return config

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

# --- Captive Portal Check ---
# >>>>> HIER IST DIE FUNKTION WIEDER EINGEFÜGT <<<<<
@app.before_request
def check_for_captive_portal():
    """Leitet Anfragen um, die nicht direkt an die IP des Pi gehen (WLAN Hotspot)."""
    expected_host = "192.168.4.1" # Standard IP des Pi Hotspots (prüfen!)
    allowed_hosts = [expected_host, "localhost", "127.0.0.1"] # Erlaubte Hosts
    host_received = request.host.split(':')[0] # Host aus der Anfrage extrahieren
    # Check if request.url is None or empty before proceeding
    if not request.url:
        app.logger.error("Request URL is empty or None in check_for_captive_portal.")
        # Decide how to handle this - maybe return an error or allow request?
        # For safety, perhaps allow if URL is missing, though this shouldn't happen in normal operation.
        return

    expected_url_root = f'http://{expected_host}/' # Ziel-URL für Redirect

    # Wenn die aufgerufene URL NICHT mit der erwarteten IP beginnt UND der Host nicht erlaubt ist...
    if not request.url.startswith(expected_url_root) and host_received not in allowed_hosts :
        # ... dann leite auf die erwartete IP um (verhindert Captive Portal Fehler)
        app.logger.warning(f"--> Captive portal redirect triggered for host: {request.host}, redirecting to {expected_host}")
        return redirect(expected_url_root)
    # Andernfalls: Anfrage normal weiterverarbeiten
# >>>>> ENDE EINGEFÜGTE FUNKTION <<<<<

# --- Routen für ML2 Sprachbefehle ---

@app.route("/")
def index():
    """Zeigt die Hauptseite an (ML2 Daten holen/anzeigen)."""
    initial_data = {}
    print("Lade Daten für Indexseite von ML2...")
    try:
        # Daten von ML2 holen (mit Timeout und Fehlerbehandlung)
        pull_result = subprocess.run(
            ["adb", "pull", DATA_FILE_ML2, DATA_FILE_PI],
            capture_output=True, text=True, check=False, timeout=5
        )

        lines = [] # Initialisiere lines
        if pull_result.returncode != 0:
            print(f"Warnung: Fehler beim adb pull ({pull_result.returncode}): {pull_result.stderr or 'Kein stderr'}")
            if os.path.exists(DATA_FILE_PI):
                 print(f"Info: Verwende lokal vorhandene Datei {DATA_FILE_PI}")
                 with open(DATA_FILE_PI, "r") as f: lines = [line.strip() for line in f.readlines()]
            else:
                 print(f"Info: Weder Pull erfolgreich noch lokale Datei {DATA_FILE_PI} vorhanden. Verwende Init-Werte.")
                 lines = list(init_commands.values())
        else:
            print(f"Info: adb pull erfolgreich.")
            with open(DATA_FILE_PI, "r") as f: lines = [line.strip() for line in f.readlines()]

        # Stelle sicher, dass genügend Zeilen vorhanden sind
        keys = list(init_commands.keys())
        default_values = list(init_commands.values())
        while len(lines) < len(keys): lines.append(default_values[len(lines)])

        # Erstelle Dictionary
        initial_data = dict(zip(keys, lines[:len(keys)]))

    except subprocess.TimeoutExpired:
        print("Fehler: ADB pull timed out.", file=sys.stderr)
        initial_data = init_commands.copy()
    except FileNotFoundError:
         print("Fehler: 'adb' Kommando nicht gefunden. Ist ADB installiert und im PATH?", file=sys.stderr)
         initial_data = init_commands.copy()
    except Exception as e:
        print(f"Fehler beim Laden/Verarbeiten der Daten für Index: {e}", file=sys.stderr)
        initial_data = init_commands.copy()

    return render_template("index.html", data=initial_data)

@app.route("/save", methods=["POST"])
def save_data():
    """Speichert die Daten für die ML2 und überträgt sie."""
    try:
        form_data = [ request.form.get(key, init_commands[key]) for key in init_commands.keys() ]

        with open(DATA_FILE_PI, "w") as f:
            for item in form_data: f.write(item + "\n")

        print(f"Versuche adb push {DATA_FILE_PI} nach {DATA_FILE_ML2}")
        push_result = subprocess.run(
            ["adb", "push", DATA_FILE_PI, DATA_FILE_ML2],
            capture_output=True, text=True, check=True, timeout=10
        )
        print(f"ADB push stdout: {push_result.stdout or 'Kein Output'}")
        flash("Sprachbefehle gespeichert und übertragen!", "success")

    except subprocess.CalledProcessError as e:
        print(f"ADB push error: {e.stderr}", file=sys.stderr)
        flash(f"Fehler bei Übertragung: {e.stderr or 'Kein stderr'}", "error")
    except subprocess.TimeoutExpired:
        print("Fehler: ADB push timed out.", file=sys.stderr)
        flash("Fehler: Zeitüberschreitung bei Übertragung (ADB push).", "error")
    except FileNotFoundError:
         print("Fehler: 'adb' Kommando nicht gefunden.", file=sys.stderr)
         flash("Fehler: ADB-Kommando nicht gefunden. Ist es installiert und im PATH?", "error")
    except Exception as e:
        print(f"Unerwarteter Fehler beim Speichern/Senden: {e}", file=sys.stderr)
        flash(f"Fehler beim Speichern der Sprachbefehle: {str(e)}", "error")

    return redirect(url_for('index'))


# --- Routen für Rollstuhl-Konfiguration ---

@app.route('/config', methods=['GET'])
def show_config():
    """Zeigt das Konfigurationsformular für den Rollstuhl an."""
    current_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    # Sicherstellen, dass alle Gänge im Dictionary sind für das Template
    for i in range(1, 6):
        if str(i) not in current_config["gear_factors"]:
            current_config["gear_factors"][str(i)] = DEFAULT_CONFIG["gear_factors"][str(i)]
    return render_template('config.html', config=current_config)

@app.route('/save_config', methods=['POST'])
def save_config_route():
    """Empfängt die Formulardaten für Rollstuhl-Konfig und speichert sie (erweitert)."""
    try:
        config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
        new_gear_factors = {}
        valid = True

        # Lese und validiere Gang-Faktoren
        for i in range(1, 6):
            key = f'gear{i}'; factor_str = request.form.get(key)
            if factor_str is None: flash(f"Fehlender Wert für Gang {i}.", "error"); valid = False; continue
            try:
                factor = float(factor_str)
                if 0.0 <= factor <= 1.0: new_gear_factors[str(i)] = factor
                else: flash(f"Ungültiger Wert für Gang {i} (muss 0.0-1.0 sein).", "error"); valid = False
            except ValueError: flash(f"Ungültiger Zahlenwert für Gang {i}.", "error"); valid = False

        # Lese und validiere Beschleunigung
        new_accel_step = config["acceleration_step"]
        accel_str = request.form.get('acceleration')
        if accel_str is None: flash("Fehlender Wert für Beschleunigung.", "error"); valid = False
        else:
            try:
                accel = float(accel_str)
                if accel >= 0.1: new_accel_step = accel
                else: flash("Beschleunigung muss >= 0.1 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Zahlenwert für Beschleunigung.", "error"); valid = False

        # Lese und validiere Pi Side Deadzone
        new_pi_deadzone = config["pi_side_deadzone"]
        pideadzone_str = request.form.get('pi_deadzone')
        if pideadzone_str is None: flash("Fehlender Wert für Pi Deadzone.", "error"); valid = False
        else:
            try:
                dz = float(pideadzone_str)
                if 0.0 <= dz < 1.0 : new_pi_deadzone = dz
                else: flash("Pi Deadzone muss zwischen 0.0 und < 1.0 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Zahlenwert für Pi Deadzone.", "error"); valid = False

        # Lese und validiere Min RLink Command
        new_min_command = config["min_rlink_command"]
        mincmd_str = request.form.get('min_command')
        if mincmd_str is None: flash("Fehlender Wert für Min. RLink Command.", "error"); valid = False
        else:
            try:
                cmd = int(mincmd_str)
                if 1 <= cmd <= 50: new_min_command = cmd
                else: flash("Min. RLink Command muss zwischen 1 und 50 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Ganzzahl-Wert für Min. RLink Command.", "error"); valid = False

        # Speichern, wenn alles gültig war
        if valid:
            config["gear_factors"] = new_gear_factors
            config["acceleration_step"] = new_accel_step
            config["pi_side_deadzone"] = new_pi_deadzone
            config["min_rlink_command"] = new_min_command
            if save_config(CONFIG_FILE, config):
                flash("Rollstuhl-Einstellungen erfolgreich gespeichert!", "success")
            else:
                flash("Fehler beim Speichern der Rollstuhl-Einstellungen.", "error")
        else:
             flash("Rollstuhl-Einstellungen NICHT gespeichert (ungültige Werte).", "warning")

    except Exception as e:
        flash(f"Unerwarteter Fehler beim Speichern der Rollstuhl-Konfig: {e}", "error")
        print(f"Unerwarteter Fehler in /save_config: {e}", file=sys.stderr)

    return redirect(url_for('show_config'))

# --- ENDE NEUE Routen ---


# --- Server Start ---
if __name__ == "__main__":
    print("Starte kombinierten Flask Server (ML2-Konfig + Rollstuhl-Konfig)...")
    loaded_wheelchair_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    save_config(CONFIG_FILE, loaded_wheelchair_config) # Stellt sicher, dass Datei mit aktuellen Defaults/Validierungen existiert

    print("\nÖffne einen Webbrowser und gehe zu:")
    print(f"http://<IP-Adresse-des-Pi>:80/       (für ML2 Sprachbefehle)")
    print(f"http://<IP-Adresse-des-Pi>:80/config (für Rollstuhl Parameter)")
    print("(Ersetze <IP-Adresse-des-Pi> mit der tatsächlichen IP, z.B. 192.168.4.1 im Hotspot-Modus)")
    print("(Drücke Strg+C zum Beenden)")
    try:
        app.run(host="0.0.0.0", port=80, debug=True)
    except OSError as e:
        if e.errno == 98 or "Address already in use" in str(e): print(f"\nFEHLER: Port 80 wird bereits verwendet.", file=sys.stderr)
        elif e.errno == 13 or "Permission denied" in str(e): print(f"\nFEHLER: Keine Berechtigung für Port 80.\nVersuche 'sudo python3 {os.path.basename(__file__)}'", file=sys.stderr)
        else: print(f"\nFEHLER beim Starten des Servers: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nAllgemeiner FEHLER beim Starten des Servers: {e}", file=sys.stderr)