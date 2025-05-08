# server.py (Erweitert um Konfigurations-Interface für neue Parameter)

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import subprocess
import os
import json
import sys

# --- Konfiguration für Rollstuhl-Parameter ---
CONFIG_FILE = "wheelchair_config.json"
DEFAULT_CONFIG = {
    "gear_factors": {
        "1": 0.2, "2": 0.4, "3": 0.6, "4": 0.8, "5": 1.0
    },
    "acceleration_step": 2.0,
    "pi_side_deadzone": 0.1, # NEU: Standardwert für Pi Deadzone
    "min_rlink_command": 10  # NEU: Standardwert für minimale Ansteuerung
}

# --- Flask App Initialisierung ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Bestehende Konfiguration für Magic Leap Kommunikation ---
DATA_FILE_PI = "data.txt"
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
                # Gear Factors (wie zuvor, aber mit besserem Default-Handling)
                loaded_gears = loaded_data.get("gear_factors")
                if isinstance(loaded_gears, dict):
                    valid_gears = {}
                    for i in range(1, 6):
                        key = str(i)
                        try:
                            val = float(loaded_gears.get(key, defaults["gear_factors"][key]))
                            valid_gears[key] = max(0.0, min(1.0, val)) # Clamp 0-1
                        except (ValueError, TypeError):
                            valid_gears[key] = defaults["gear_factors"][key]
                    config["gear_factors"] = valid_gears
                # else: Lasse Default drin

                # Acceleration Step (wie zuvor)
                try:
                     val = float(loaded_data.get("acceleration_step", defaults["acceleration_step"]))
                     if val > 0: config["acceleration_step"] = val
                except (ValueError, TypeError): pass # Lasse Default drin

                # NEU: Pi Side Deadzone
                try:
                     val = float(loaded_data.get("pi_side_deadzone", defaults["pi_side_deadzone"]))
                     config["pi_side_deadzone"] = max(0.0, min(0.95, val)) # Clamp 0 bis <1
                except (ValueError, TypeError): pass # Lasse Default drin

                # NEU: Min RLink Command
                try:
                     val = int(loaded_data.get("min_rlink_command", defaults["min_rlink_command"]))
                     config["min_rlink_command"] = max(1, min(50, val)) # Clamp 1 bis 50 (Beispiel)
                except (ValueError, TypeError): pass # Lasse Default drin

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warnung: Fehler beim Laden von {filepath}: {e}. Verwende Defaults.")
            # Config enthält bereits Defaults
    else:
        print(f"Info: Konfigurationsdatei {filepath} nicht gefunden. Verwende Defaults.")
        # Config enthält bereits Defaults
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

# --- Bestehende Flask Routen (/ , /save) ---
# Diese bleiben unverändert und beziehen sich auf die ML2-Befehle (init_commands, data.txt)
@app.route("/")
def index():
     # ... (Code wie zuvor) ...
     return render_template("index.html", data=initial_data) # Nutzt index.html

@app.route("/save", methods=["POST"])
def save_data():
     # ... (Code wie zuvor) ...
     return jsonify({"success": True, "message": "Daten gespeichert und übertragen!", "output": push_result.stdout})


# --- Routen für Rollstuhl-Konfiguration ---

@app.route('/config', methods=['GET'])
def show_config():
    """Zeigt das Konfigurationsformular für den Rollstuhl an."""
    current_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    # Stelle sicher, dass alle Gänge im Dictionary sind (für das Template)
    for i in range(1, 6):
        if str(i) not in current_config["gear_factors"]:
            current_config["gear_factors"][str(i)] = DEFAULT_CONFIG["gear_factors"][str(i)]
    # Übergebe Konfig an das *neue* Template 'config.html'
    return render_template('config.html', config=current_config)

@app.route('/save_config', methods=['POST'])
def save_config_route():
    """Empfängt die Formulardaten für Rollstuhl-Konfig und speichert sie (erweitert)."""
    try:
        config = load_config(CONFIG_FILE, DEFAULT_CONFIG) # Lade aktuelle Config als Basis
        new_gear_factors = {}
        valid = True

        # Lese und validiere Gang-Faktoren (wie zuvor)
        for i in range(1, 6):
            key = f'gear{i}'; factor_str = request.form.get(key)
            if factor_str is None: flash(f"Fehlender Wert für Gang {i}.", "error"); valid = False; continue
            try:
                factor = float(factor_str)
                if 0.0 <= factor <= 1.0: new_gear_factors[str(i)] = factor
                else: flash(f"Ungültiger Wert für Gang {i} (0.0-1.0).", "error"); valid = False
            except ValueError: flash(f"Ungültiger Zahlenwert für Gang {i}.", "error"); valid = False

        # Lese und validiere Beschleunigung (wie zuvor)
        new_accel_step = config["acceleration_step"]
        accel_str = request.form.get('acceleration')
        if accel_str is None: flash("Fehlender Wert für Beschleunigung.", "error"); valid = False
        else:
            try:
                accel = float(accel_str)
                if accel > 0: new_accel_step = accel
                else: flash("Beschleunigung muss > 0 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Zahlenwert für Beschleunigung.", "error"); valid = False

        # --- NEU: Lese und validiere Pi Side Deadzone ---
        new_pi_deadzone = config["pi_side_deadzone"]
        pideadzone_str = request.form.get('pi_deadzone') # Name aus HTML Formular
        if pideadzone_str is None: flash("Fehlender Wert für Pi Deadzone.", "error"); valid = False
        else:
            try:
                dz = float(pideadzone_str)
                if 0.0 <= dz < 1.0 : new_pi_deadzone = dz # Muss < 1 sein
                else: flash("Pi Deadzone muss zwischen 0.0 und < 1.0 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Zahlenwert für Pi Deadzone.", "error"); valid = False

        # --- NEU: Lese und validiere Min RLink Command ---
        new_min_command = config["min_rlink_command"]
        mincmd_str = request.form.get('min_command') # Name aus HTML Formular
        if mincmd_str is None: flash("Fehlender Wert für Min. RLink Command.", "error"); valid = False
        else:
            try:
                cmd = int(mincmd_str)
                if 1 <= cmd <= 50: new_min_command = cmd # Bereich 1-50 (Beispiel)
                else: flash("Min. RLink Command muss zwischen 1 und 50 sein.", "error"); valid = False
            except ValueError: flash("Ungültiger Ganzzahl-Wert für Min. RLink Command.", "error"); valid = False

        # Speichern, wenn alles gültig war
        if valid:
            config["gear_factors"] = new_gear_factors
            config["acceleration_step"] = new_accel_step
            config["pi_side_deadzone"] = new_pi_deadzone # NEU
            config["min_rlink_command"] = new_min_command # NEU
            if save_config(CONFIG_FILE, config):
                flash("Einstellungen erfolgreich gespeichert!", "success")
            else:
                flash("Fehler beim Speichern der Einstellungen.", "error")
        else:
             flash("Einstellungen NICHT gespeichert (ungültige Werte vorhanden).", "warning")

    except Exception as e:
        flash(f"Unerwarteter Fehler beim Speichern: {e}", "error")
        print(f"Unerwarteter Fehler in /save_config: {e}", file=sys.stderr)

    # Leite immer zurück zur Konfigurationsseite, um Feedback anzuzeigen
    return redirect(url_for('show_config'))

# --- ENDE NEUE Routen ---


# --- Server Start ---
if __name__ == "__main__":
    print("Starte kombinierten Flask Server (ML2-Konfig + Rollstuhl-Konfig)...")
    # Initialisiere/Lade Rollstuhl-Konfigurationsdatei beim Start
    # load_config erstellt Datei mit Defaults, falls nicht vorhanden
    loaded_wheelchair_config = load_config(CONFIG_FILE, DEFAULT_CONFIG)
    # Speichere die (potenziell ergänzten/korrigierten) Werte direkt zurück
    save_config(CONFIG_FILE, loaded_wheelchair_config)

    print("\nÖffne einen Webbrowser und gehe zu:")
    print(f"http://<IP-Adresse-des-Pi>:80/       (für ML2 Sprachbefehle)")
    print(f"http://<IP-Adresse-des-Pi>:80/config (für Rollstuhl Parameter)")
    print("(Drücke Strg+C zum Beenden)")
    try:
        app.run(host="0.0.0.0", port=80, debug=False) # Debug=False für Produktion
    except OSError as e:
        # ... (Fehlerbehandlung für Port 80 wie zuvor) ...
        if e.errno == 98 or "Address already in use" in str(e): print(f"\nFEHLER: Port 80 wird bereits verwendet.", file=sys.stderr)
        elif e.errno == 13 or "Permission denied" in str(e): print(f"\nFEHLER: Keine Berechtigung für Port 80.\nVersuche 'sudo python3 {os.path.basename(__file__)}'", file=sys.stderr)
        else: print(f"\nFEHLER beim Starten des Servers: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nAllgemeiner FEHLER beim Starten des Servers: {e}", file=sys.stderr)