# app.py (Flask Webserver)

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import subprocess
import os
import json
import sys

# --- Konfiguration für Rollstuhl-Pi-Parameter ---
CONFIG_FILE_PI = "wheelchair_config.json"  # Für Pi-seitige Rollstuhlparameter
DEFAULT_CONFIG_PI = {
    "gear_factors": {
        "1": 0.2, "2": 0.4, "3": 0.6, "4": 0.8, "5": 1.0
    },
    "acceleration_step": 2.0,
    "pi_side_deadzone": 0.1,
    "min_rlink_command": 10
}

# --- Konfiguration für ML2 Joystick-Parameter ---
CONFIG_FILE_ML2 = "ml2_joystick_config.json"  # Für ML2-seitige Joystick-Parameter
DEFAULT_CONFIG_ML2 = {
    "activationDuration": 1.0,
    "graceDuration": 0.5,
    "recenterDuration": 0.25,
    "rotationThreshold": 1.5,
    "rotationSmoothSpeed": 10.0,
    "historyLength": 0,
    "handleSmoothSpeed": 8.0,
    "visualizerSmoothSpeed": 8.0,
    "rotationExponent": 1.8,
    "rotationDeadZone": 0.1,
    "outputSensitivity": 0.7
}

# --- Trigger-Datei für ZeroMQ-Server ---
# Server.py wird diese Datei überwachen und bei Änderung/Erstellung den Inhalt an ML2 senden
ZMQ_ML2_CONFIG_TRIGGER_FILE = "send_ml2_config_trigger.flag"

# --- Flask App Initialisierung ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Konfiguration für ML2 Sprachbefehle (Legacy) ---
DATA_FILE_PI_LEGACY = "data.txt"  # Für alte Sprachbefehl-Logik
DATA_FILE_ML2_LEGACY = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/data.txt'
init_commands_legacy = {
    "joystick": "Steuerung Aktivieren", "lights": "Licht AN/AUS", "warn": "Warnblinker AN/AUS",
    "hornOn": "Hupe AN", "hornOff": "Hupe AUS", "kantelungOn": "Sitzk. AN",
    "kantelungOff": "Sitzk. AUS", "gearUp": "Schneller", "gearDown": "Langsamer",
    "language": "Deutsch"
}


# --- Hilfsfunktionen für JSON Konfiguration (generisch) ---
def load_config(filepath, defaults):
    config = defaults.copy()
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    # Überschreibe Defaults nur mit tatsächlich geladenen Keys,
                    # um die Struktur der Defaults beizubehalten, falls Keys fehlen
                    for key in defaults.keys():
                        if key in loaded_data:
                            # Hier könnte man noch Typ-Prüfungen und Validierungen für jeden Key machen
                            if isinstance(defaults[key], dict) and isinstance(loaded_data[key], dict):
                                # Für verschachtelte Dictionaries wie gear_factors
                                for sub_key in defaults[key].keys():
                                    if sub_key in loaded_data[key]:
                                        try:  # Versuch der Typkonvertierung für Sub-Keys
                                            if isinstance(defaults[key][sub_key], float):
                                                config[key][sub_key] = float(loaded_data[key][sub_key])
                                            elif isinstance(defaults[key][sub_key], int):
                                                config[key][sub_key] = int(loaded_data[key][sub_key])
                                            else:  # String oder anderes
                                                config[key][sub_key] = loaded_data[key][sub_key]
                                        except (ValueError, TypeError):
                                            print(
                                                f"Warnung: Ungültiger Typ für {key}.{sub_key} in {filepath}. Verwende Default.")
                                            # Default ist schon in config[key][sub_key]
                                    # else: Default für sub_key bleibt erhalten
                            else:  # Für nicht-verschachtelte Keys
                                try:  # Versuch der Typkonvertierung
                                    if isinstance(defaults[key], float):
                                        config[key] = float(loaded_data[key])
                                    elif isinstance(defaults[key], int):
                                        config[key] = int(loaded_data[key])
                                    else:  # String oder anderes
                                        config[key] = loaded_data[key]
                                except (ValueError, TypeError):
                                    print(f"Warnung: Ungültiger Typ für {key} in {filepath}. Verwende Default.")
                                    # Default bleibt erhalten
                        # else: Default für key bleibt erhalten
                else:
                    print(f"Warnung: {filepath} enthält kein valides JSON-Objekt. Verwende Defaults.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warnung: Fehler beim Laden von {filepath}: {e}. Verwende Defaults.")
    else:
        print(
            f"Info: Konfigurationsdatei {filepath} nicht gefunden. Verwende Defaults und erstelle sie beim Speichern.")
    return config


def save_config(filepath, config_data):
    try:
        with open(filepath, 'w') as f:
            json.dump(config_data, f, indent=4)
        print(f"Konfiguration erfolgreich in {filepath} gespeichert.")
        return True
    except IOError as e:
        print(f"Fehler beim Speichern von {filepath}: {e}", file=sys.stderr)
        return False


# --- Captive Portal Check ---
@app.before_request
def check_for_captive_portal():
    # ... (Code wie in deiner letzten funktionierenden Version) ...
    expected_host = "192.168.4.1";
    allowed_hosts = [expected_host, "localhost", "127.0.0.1"]
    host_received = request.host.split(':')[0]
    if not request.url: app.logger.error("Request URL is empty/None in captive portal check."); return
    expected_url_root = f'http://{expected_host}/'
    if not request.url.startswith(expected_url_root) and host_received not in allowed_hosts:
        app.logger.warning(f"--> Captive portal redirect: {request.host} to {expected_host}")
        return redirect(expected_url_root)


# --- Routen für ML2 Sprachbefehle (Legacy) ---
@app.route("/")
def index():
    # ... (Code wie in deiner letzten funktionierenden Version für data.txt) ...
    initial_data = init_commands_legacy.copy()  # Start mit Defaults
    try:
        # ADB Pull Logik hier
        # ... (Deine Logik zum Holen und Verarbeiten von DATA_FILE_PI_LEGACY) ...
        if os.path.exists(DATA_FILE_PI_LEGACY):  # Beispiel, wenn Pull fehlgeschlagen, aber Datei da ist
            with open(DATA_FILE_PI_LEGACY, "r") as f:
                lines = [line.strip() for line in f.readlines()]
            keys = list(init_commands_legacy.keys())
            for i, key in enumerate(keys):
                if i < len(lines): initial_data[key] = lines[i]
    except Exception as e:
        print(f"Fehler beim Laden der Legacy-Daten für Index: {e}")
    return render_template("index.html", data=initial_data)


@app.route("/save", methods=["POST"])
def save_data():
    # ... (Code wie in deiner letzten funktionierenden Version für data.txt) ...
    try:
        form_data = [request.form.get(key, init_commands_legacy[key]) for key in init_commands_legacy.keys()]
        with open(DATA_FILE_PI_LEGACY, "w") as f:
            for item in form_data: f.write(item + "\n")
        # ADB Push Logik hier
        # ...
        flash("Sprachbefehle (Legacy) gespeichert und übertragen!", "success")
    except Exception as e:
        flash(f"Fehler beim Speichern der Sprachbefehle: {str(e)}", "error")
    return redirect(url_for('index'))


# --- Routen für Rollstuhl-Pi-Parameter Konfiguration ---
@app.route('/config', methods=['GET'])
def show_config():
    current_pi_config = load_config(CONFIG_FILE_PI, DEFAULT_CONFIG_PI)
    # Sicherstellen, dass alle Gänge im Dictionary sind für das Template
    for i in range(1, 6):
        key = str(i)
        if key not in current_pi_config["gear_factors"]:
            # Nimm Default für diesen spezifischen Gang, falls er fehlt
            current_pi_config["gear_factors"][key] = DEFAULT_CONFIG_PI["gear_factors"].get(key, 0.2 * i)
    return render_template('config.html', config=current_pi_config)


@app.route('/save_config', methods=['POST'])
def save_config_route():
    try:
        config = load_config(CONFIG_FILE_PI, DEFAULT_CONFIG_PI)
        valid = True;
        new_gear_factors = {}

        # Lese und validiere Gang-Faktoren
        for i in range(1, 6):
            key_html = f'gear{i}';
            key_json = str(i)
            factor_str = request.form.get(key_html)
            if factor_str is None: flash(f"Fehlender Wert für Gang {i}.", "error"); valid = False; continue
            try:
                factor = float(factor_str)
                if 0.0 <= factor <= 1.0:
                    new_gear_factors[key_json] = factor
                else:
                    flash(f"Ungültiger Wert für Gang {i} (0.0-1.0).", "error"); valid = False
            except ValueError:
                flash(f"Ungültiger Zahlenwert für Gang {i}.", "error"); valid = False
        if valid: config["gear_factors"] = new_gear_factors

        # Lese und validiere Beschleunigung
        accel_str = request.form.get('acceleration')
        if accel_str is None:
            flash("Fehlender Wert für Beschleunigung.", "error"); valid = False
        else:
            try:
                accel = float(accel_str)
                if accel >= 0.1:
                    config["acceleration_step"] = accel
                else:
                    flash("Beschleunigung muss >= 0.1 sein.", "error"); valid = False
            except ValueError:
                flash("Ungültiger Zahlenwert für Beschleunigung.", "error"); valid = False

        # Lese und validiere Pi Side Deadzone
        pideadzone_str = request.form.get('pi_deadzone')
        if pideadzone_str is None:
            flash("Fehlender Wert für Pi Deadzone.", "error"); valid = False
        else:
            try:
                dz = float(pideadzone_str)
                if 0.0 <= dz < 1.0:
                    config["pi_side_deadzone"] = dz
                else:
                    flash("Pi Deadzone muss 0.0 bis <1.0 sein.", "error"); valid = False
            except ValueError:
                flash("Ungültiger Zahlenwert für Pi Deadzone.", "error"); valid = False

        # Lese und validiere Min RLink Command
        mincmd_str = request.form.get('min_command')
        if mincmd_str is None:
            flash("Fehlender Wert für Min. RLink Command.", "error"); valid = False
        else:
            try:
                cmd = int(mincmd_str)
                if 1 <= cmd <= 50:
                    config["min_rlink_command"] = cmd
                else:
                    flash("Min. RLink Command muss 1 bis 50 sein.", "error"); valid = False
            except ValueError:
                flash("Ungültiger Ganzzahl-Wert für Min. RLink Cmd.", "error"); valid = False

        if valid:
            if save_config(CONFIG_FILE_PI, config):
                flash("Rollstuhl Pi-Parameter erfolgreich gespeichert!", "success")
            else:
                flash("Fehler beim Speichern der Pi-Parameter.", "error")
        else:
            flash("Pi-Parameter NICHT gespeichert (ungültige Werte).", "warning")
    except Exception as e:
        flash(f"Fehler Speichern Pi-Konfig: {e}", "error");
        print(f"Fehler in /save_config: {e}", file=sys.stderr)
    return redirect(url_for('show_config'))


# --- Routen für ML2 Joystick-Parameter Konfiguration ---
@app.route('/ml2_config', methods=['GET'])
def show_ml2_config():
    current_ml2_config = load_config(CONFIG_FILE_ML2, DEFAULT_CONFIG_ML2)
    return render_template('ml2_config.html', config=current_ml2_config)


@app.route('/save_ml2_config', methods=['POST'])
def save_ml2_config_route():
    try:
        config = load_config(CONFIG_FILE_ML2, DEFAULT_CONFIG_ML2)  # Aktuelle/Defaults laden
        valid = True

        # --- Alle ML2 Parameter hier abrufen und validieren ---
        # Beispielhaft für einige Parameter:
        try:
            config["activationDuration"] = max(0.1, min(5.0, float(
                request.form.get('activationDuration', config["activationDuration"]))))
        except (ValueError, TypeError):
            flash("Ungültige Aktivierungsdauer", "error"); valid = False

        try:
            config["graceDuration"] = max(0.1,
                                          min(3.0, float(request.form.get('graceDuration', config["graceDuration"]))))
        except (ValueError, TypeError):
            flash("Ungültige Toleranzperiode", "error"); valid = False

        try:
            config["recenterDuration"] = max(0.05, min(2.0, float(
                request.form.get('recenterDuration', config["recenterDuration"]))))
        except (ValueError, TypeError):
            flash("Ungültige Re-Zentrierungsdauer", "error"); valid = False

        try:
            config["rotationThreshold"] = max(0.5, min(5.0, float(
                request.form.get('rotationThreshold', config["rotationThreshold"]))))
        except (ValueError, TypeError):
            flash("Ungültige Rotationsschwelle", "error"); valid = False

        try:
            config["rotationSmoothSpeed"] = max(1.0, min(50.0, float(
                request.form.get('rotationSmoothSpeed', config["rotationSmoothSpeed"]))))
        except (ValueError, TypeError):
            flash("Ungültige Rotationsglättung", "error"); valid = False

        try:
            config["historyLength"] = max(0, min(20, int(request.form.get('historyLength', config["historyLength"]))))
        except (ValueError, TypeError):
            flash("Ungültige History-Länge", "error"); valid = False

        try:
            config["handleSmoothSpeed"] = max(1.0, min(50.0, float(
                request.form.get('handleSmoothSpeed', config["handleSmoothSpeed"]))))
        except (ValueError, TypeError):
            flash("Ungültige Griffglättung", "error"); valid = False

        try:
            config["visualizerSmoothSpeed"] = max(1.0, min(50.0, float(
                request.form.get('visualizerSmoothSpeed', config["visualizerSmoothSpeed"]))))
        except (ValueError, TypeError):
            flash("Ungültige Visualizerglättung", "error"); valid = False

        try:
            config["rotationExponent"] = max(1.0, min(3.0, float(
                request.form.get('rotationExponent', config["rotationExponent"]))))
        except (ValueError, TypeError):
            flash("Ungültiger Rotationsexponent", "error"); valid = False

        try:
            config["rotationDeadZone"] = max(0.0, min(0.49, float(
                request.form.get('rotationDeadZone', config["rotationDeadZone"]))))
        except (ValueError, TypeError):
            flash("Ungültige Rotations-Deadzone", "error"); valid = False

        try:
            config["outputSensitivity"] = max(0.1, min(1.0, float(
                request.form.get('outputSensitivity', config["outputSensitivity"]))))
        except (ValueError, TypeError):
            flash("Ungültige Output-Sensitivität", "error"); valid = False

        if valid:
            if save_config(CONFIG_FILE_ML2, config):  # Speichere in ml2_joystick_config.json
                flash("ML2-Joystick-Einstellungen gespeichert.", "success")
                # Erstelle/Aktualisiere die Trigger-Datei mit dem JSON-Inhalt
                try:
                    with open(ZMQ_ML2_CONFIG_TRIGGER_FILE, "w") as f:
                        json.dump(config, f)  # Schreibe das config Dictionary als JSON
                    print(
                        f"Trigger-Datei '{ZMQ_ML2_CONFIG_TRIGGER_FILE}' für ML2-Konfigurationsupdate geschrieben/aktualisiert.")
                    flash("ML2-Konfigurationsupdate ausgelöst.", "info")
                except Exception as e_trigger:
                    flash(f"Fehler beim Schreiben der Trigger-Datei: {e_trigger}", "error")
                    print(f"Fehler beim Schreiben der Trigger-Datei: {e_trigger}", file=sys.stderr)
            else:
                flash("Fehler beim Speichern der ML2-Joystick-Einstellungen.", "error")
        else:
            flash("ML2-Joystick-Einstellungen NICHT gespeichert (ungültige Werte).", "warning")

    except Exception as e:
        flash(f"Unerwarteter Fehler beim Speichern der ML2-Konfig: {e}", "error")
        print(f"Unerwarteter Fehler in /save_ml2_config: {e}", file=sys.stderr)

    return redirect(url_for('show_ml2_config'))


# --- Server Start ---
if __name__ == "__main__":
    print("Starte Flask Server (ML2-Sprache, Rollstuhl-Pi, ML2-Joystick Konfig)...")
    # Initialisiere/Lade Konfig-Dateien beim Start & speichere sie (um Defaults zu garantieren)
    save_config(CONFIG_FILE_PI, load_config(CONFIG_FILE_PI, DEFAULT_CONFIG_PI))
    save_config(CONFIG_FILE_ML2, load_config(CONFIG_FILE_ML2, DEFAULT_CONFIG_ML2))

    print("\nÖffne einen Webbrowser und gehe zu:")
    print(f"http://<IP-DES-PI>:80/           (ML2 Sprachbefehle)")
    print(f"http://<IP-DES-PI>:80/config     (Rollstuhl Pi-Parameter)")
    print(f"http://<IP-DES-PI>:80/ml2_config (ML2 Joystick-Parameter)")
    print("(Ersetze <IP-DES-PI> mit der IP des Raspberry Pi, z.B. 192.168.4.1 im Hotspot-Modus)")
    print("(Drücke Strg+C zum Beenden)")
    try:
        app.run(host="0.0.0.0", port=80, debug=True)  # DEBUG MODE FÜR ENTWICKLUNG
    except OSError as e:
        # ... (Fehlerbehandlung Port 80 wie zuvor) ...
        if e.errno == 98 or "Address already in use" in str(e):
            print(f"\nFEHLER: Port 80 wird bereits verwendet.", file=sys.stderr)
        elif e.errno == 13 or "Permission denied" in str(e):
            print(f"\nFEHLER: Keine Berechtigung für Port 80.\nVersuche 'sudo python3 {os.path.basename(__file__)}'",
                  file=sys.stderr)
        else:
            print(f"\nFEHLER beim Starten des Servers: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nAllgemeiner FEHLER beim Starten des Servers: {e}", file=sys.stderr)