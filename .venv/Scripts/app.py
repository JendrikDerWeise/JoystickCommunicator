from flask import Flask, render_template, request, jsonify, redirect, url_for
import subprocess
import os

app = Flask(__name__)

# Pfad zur Datei auf dem Raspberry Pi
DATA_FILE_PI = "data.txt"
# Pfad zur Datei auf der Magic Leap 2 (anpassen!)
DATA_FILE_ML2 = '/storage/emulated/0/Android/data/de.IMC.EyeJoystick/files/data.txt'
init_commands={"steuerung","licht","warnblinker","hupe an","hupe aus","sitz an", "sitz aus","schneller","langsamer"}

@app.before_request
def check_for_captive_portal():
    # Hostname, unter dem der Pi im Hotspot erreichbar ist
    expected_host = "192.168.4.1"
    # Erlaube auch den Zugriff über localhost oder den Standard-Flask-Hostnamen für lokale Tests
    allowed_hosts = [expected_host, "localhost", "127.0.0.1"]

    # request.host enthält den Hostnamen *ohne* Port
    if request.host.split(':')[0] not in allowed_hosts:
        # Wenn der angefragte Host nicht der erwartete ist,
        # leite auf die Startseite unter der korrekten IP um.
        print(f"Captive portal redirect triggered for host: {request.host}") #Debug-Ausgabe
        return redirect(url_for('index', _external=True, _scheme='http', _host=expected_host))
# --- Ende NEU ---

@app.route("/")
def index():
    """Zeigt die Hauptseite an, liest Daten von ML2."""
    try:
        # Daten von ML2 holen
        pull_result = subprocess.run(
            ["adb", "pull", DATA_FILE_ML2, DATA_FILE_PI],
            capture_output=True,
            text=True,
            check=False,
            timeout=10 # Timeout, falls adb hängt
        )

        if pull_result.returncode != 0 : # Fehler beim Pullen
          print(f"Fehler beim pull: {pull_result.stderr}")
          #Wenn die Datei nicht existiert, ist das kein Fehler.
          initial_data = init_commands
        else: #Kein Fehler beim Pullen
            # Datei einlesen (falls vorhanden)
            if os.path.exists(DATA_FILE_PI):
                with open(DATA_FILE_PI, "r") as f:
                    lines = f.readlines()
                    # Stelle sicher, dass genügend Zeilen vorhanden sind
                    while len(lines) < 3:
                        lines.append("")
                    initial_data = {"joystick": lines[0].strip(),
                                    "lights": lines[1].strip(),
                                    "warn": lines[2].strip(),
                                    "hornOn": lines[3].strip(),
                                    "hornOff": lines[4].strip(),
                                    "kantelungOn": lines[5].strip(),
                                    "kantelungOff": lines[6].strip(),
                                    "gearUp": lines[7].strip(),
                                    "gearDown": lines[8].strip(),
                                    "language": lines[3].strip() if len(lines) > 3 else "English"}
            else: #Datei konnte nicht von ML2 geholt werden, weil Fehler.
                initial_data = init_commands

    except subprocess.TimeoutExpired:
        print("ADB pull timed out.")
        initial_data = {"text1": "", "text2": "", "text3": ""}
    except Exception as e:
        print(f"Fehler beim Laden oder Verarbeiten der Daten: {e}")
        initial_data = {"text1": "", "text2": "", "text3": ""}  # Standardwerte

    return render_template("index.html", data=initial_data)

@app.route("/save", methods=["POST"])
def save_data():
    """Speichert die Daten und überträgt sie an die ML2."""
    try:
        text1 = request.form["joystick"]
        text2 = request.form["lights"]
        text3 = request.form["warn"]
        text4 = request.form["hornOn"]
        text5 = request.form["hornOff"]
        text6 = request.form["kantelungOn"]
        text7 = request.form["kantelungOff"]
        text8 = request.form["gearUp"]
        text9 = request.form["gearDown"]
        language = request.form["language"]

        # Daten in Datei speichern
        with open(DATA_FILE_PI, "w") as f:
            f.write(text1 + "\n")
            f.write(text2 + "\n")
            f.write(text3 + "\n")
            f.write(text4 + "\n")
            f.write(text5 + "\n")
            f.write(text6 + "\n")
            f.write(text7 + "\n")
            f.write(text8 + "\n")
            f.write(text9 + "\n")
            f.write(language + "\n")

        # Daten an ML2 übertragen
        push_result = subprocess.run(
            ["adb", "push", DATA_FILE_PI, DATA_FILE_ML2],
            capture_output=True,
            text=True,
            check=True,  # Exception bei Fehler
            timeout=10
        )
         # Erfolgsmeldung (oder Fehlermeldung) zurückgeben
        return jsonify({"success": True, "message": "Daten gespeichert und übertragen!" , "output": push_result.stdout})

    except subprocess.CalledProcessError as e:
        print(f"ADB push error: {e.stderr}")
        return jsonify({"success": False, "message": "Fehler bei der Übertragung: " + e.stderr, "output": ""})

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "ADB push timed out.", "output":""})

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"success": False, "message": "Fehler beim Speichern: " + str(e),"output":""})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=True) # Port 80 für direkten Zugriff