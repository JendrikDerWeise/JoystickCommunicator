#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import sys

# Importiere die benötigten Klassen und Konstanten aus deinem Wrapper
try:
    from rlink_wrapper import (MspRlink, RLinkError, RLinkButton, RLinkLight,
                               RLinkAxisId, RLinkAxisDir, RLinkErrorType,
                               # Füge ggf. weitere benötigte Enums/Konstanten hinzu
                              )
except ImportError:
    print("Fehler: Konnte 'rlink_wrapper.py' nicht finden.")
    print("Stelle sicher, dass die Datei im selben Verzeichnis liegt oder im PYTHONPATH.")
    sys.exit(1)

# Versuche, pynput zu importieren
try:
    from pynput import keyboard
except ImportError:
    print("Fehler: Die Bibliothek 'pynput' wurde nicht gefunden.")
    print("Bitte installiere sie mit: pip install pynput")
    sys.exit(1)

# --- Konfiguration ---
LOOP_SLEEP_TIME = 0.05  # Sekunden Pause in der Hauptschleife (ca. 20 Hz Update-Rate)
HEARTBEAT_INTERVAL = 0.5 # Sekunden zwischen Heartbeats
MOVEMENT_SPEED = 100     # Max. Wert für X/Y Achse (Bereich -127 bis 127)

# --- Globale Zustandsvariablen ---
# Diese werden vom Keyboard-Listener-Thread modifiziert und vom Haupt-Thread gelesen.
# Das ist in Python dank des GIL (Global Interpreter Lock) meist unproblematisch für einfache Typen.
keys_pressed = set()
horn_on = False
lights_on = False # Zustand für das Hauptlicht (z.B. Abblendlicht)
running = True    # Flag zum Beenden der Hauptschleife

# --- Keyboard Listener Callbacks ---

def on_press(key):
    """Wird aufgerufen, wenn eine Taste gedrückt wird."""
    global horn_on, lights_on, running

    try:
        # Füge normale Tasten zum Set hinzu
        keys_pressed.add(key.char.lower())

        # Spezielle Tastenbehandlung (Toggles, Quit)
        char = key.char.lower()
        if char == 'h':
            horn_on = not horn_on # Horn-Zustand umschalten
            print(f"Hupe {'AN' if horn_on else 'AUS'}")
            # Direkter Aufruf hier ist möglich, aber besser im Hauptloop für Konsistenz
        elif char == 'l':
            lights_on = not lights_on # Licht-Zustand umschalten
            print(f"Licht {'AN' if lights_on else 'AUS'}")
            # Direkter Aufruf hier ist möglich, aber besser im Hauptloop
        elif char == 'q': # Alternative zum Beenden
             print("Beenden durch 'q'...")
             running = False

    except AttributeError:
        # Spezielle Tasten (Shift, Strg, Esc, etc.)
        if key == keyboard.Key.esc:
            print("Beenden durch ESC...")
            running = False
        # Füge spezielle Tasten (falls relevant) hinzu, z.B. key.name
        # keys_pressed.add(key.name)

def on_release(key):
    """Wird aufgerufen, wenn eine Taste losgelassen wird."""
    try:
        keys_pressed.remove(key.char.lower())
    except (AttributeError, KeyError):
        # Spezielle Tasten oder Taste war nicht im Set
        pass
        # if key.name in keys_pressed:
        #     keys_pressed.remove(key.name)

# --- Hauptfunktion ---

def main():
    global running, horn_on, lights_on # Zugriff auf globale Zustände

    rlink = None # RLink Instanz
    listener = None # Keyboard Listener

    try:
        print("Suche nach RLink Geräten...")
        devices = MspRlink.enumerate_devices()

        if not devices:
            print("Keine RLink Geräte gefunden. Beende.")
            return

        print(f"{len(devices)} Gerät(e) gefunden:")
        for i, dev in enumerate(devices):
            print(f"  [{i}] {dev}")

        # Wähle das erste Gerät automatisch aus
        # TODO: Optional den Benutzer auswählen lassen, wenn mehrere Geräte vorhanden sind
        selected_device_info = devices[0]._dev_info_ptr
        print(f"\nVerbinde mit Gerät 0 (SN: {devices[0].serial})...")

        # Verwende den Context Manager des Wrappers für sicheres Öffnen/Schließen
        with MspRlink(selected_device_info) as rlink:
            print("Verbindung erfolgreich hergestellt.")
            print("\nSteuerung aktiv:")
            print(" - WASD: Bewegung")
            print(" - H:    Hupe an/aus")
            print(" - L:    Licht an/aus (Abblendlicht)")
            print(" - ESC/Q: Beenden")

            # Initialisiere Horn und Licht auf AUS beim Start
            try:
                rlink.set_horn(False)
                rlink.set_light(RLinkLight.DIP, False) # Annahme: DIP ist das Hauptlicht
                horn_on = False
                lights_on = False
            except RLinkError as e:
                 print(f"Warnung: Fehler beim Initialisieren von Horn/Licht: {e}")


            # Starte den Keyboard Listener in einem separaten Thread
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.start()

            last_heartbeat_time = time.time()
            last_horn_state = horn_on
            last_lights_state = lights_on

            while running:
                current_time = time.time()

                # 1. Berechne Bewegungsvektor basierend auf gedrückten Tasten
                target_x = 0
                target_y = 0

                if 'w' in keys_pressed:
                    target_y += MOVEMENT_SPEED
                if 's' in keys_pressed:
                    target_y -= MOVEMENT_SPEED
                if 'a' in keys_pressed:
                    target_x -= MOVEMENT_SPEED
                if 'd' in keys_pressed:
                    target_x += MOVEMENT_SPEED

                # Werte auf den gültigen Bereich (-127 bis 127) begrenzen
                target_x = max(-127, min(127, target_x))
                target_y = max(-127, min(127, target_y))

                # 2. Sende Bewegungskommandos
                try:
                    rlink.set_xy(target_x, target_y)
                except RLinkError as e:
                    print(f"\nFehler beim Senden von set_xy: {e}")
                    running = False # Bei Fehler beenden
                    continue # Schleife abbrechen

                # 3. Sende Horn/Licht-Kommandos (nur wenn sich der Zustand geändert hat)
                try:
                    if horn_on != last_horn_state:
                        rlink.set_horn(horn_on)
                        last_horn_state = horn_on

                    if lights_on != last_lights_state:
                        # Hier RLinkLight.DIP als Beispiel verwenden
                        rlink.set_light(RLinkLight.DIP, lights_on)
                        last_lights_state = lights_on
                except RLinkError as e:
                    print(f"\nFehler beim Senden von Horn/Licht: {e}")
                    # Fehler hier muss nicht unbedingt zum Abbruch führen
                    # Setze den last_state zurück, um erneuten Versuch zu ermöglichen
                    if horn_on != last_horn_state: last_horn_state = not horn_on
                    if lights_on != last_lights_state: last_lights_state = not lights_on


                # 4. Sende Heartbeat regelmäßig
                if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    try:
                        rlink.heartbeat()
                        last_heartbeat_time = current_time
                    except RLinkError as e:
                        print(f"\nFehler beim Senden des Heartbeats: {e}")
                        running = False # Bei Fehler beenden
                        continue

                # 5. Kurze Pause einlegen
                time.sleep(LOOP_SLEEP_TIME)

            print("Hauptschleife beendet.")

    except RLinkError as e:
        print(f"\nEin RLink-Fehler ist aufgetreten: {e}", file=sys.stderr)
    except FileNotFoundError as e: # Fängt Fehler vom Wrapper ab, falls Lib nicht gefunden
         print(f"\nFehler: {e}", file=sys.stderr)
    except ImportError as e: # Fängt pynput/wrapper Import Fehler ab
         print(f"\nImport Fehler: {e}", file=sys.stderr)
    except Exception as e:
        print(f"\nEin unerwarteter Fehler ist aufgetreten: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        print("Räume auf...")
        # Stoppe den Keyboard Listener, falls er läuft
        if listener and listener.is_alive():
            listener.stop()
            listener.join() # Warte auf Beendigung des Listener-Threads
            print("Keyboard Listener gestoppt.")

        # Die RLink-Verbindung wird automatisch durch den 'with'-Block geschlossen
        # (rlink.__exit__ ruft rlink.close() auf)
        # Falls kein 'with' verwendet würde, bräuchte man hier:
        # if rlink and rlink._opened:
        #     try:
        #         rlink.close()
        #     except RLinkError as e:
        #         print(f"Fehler beim Schließen der RLink Verbindung: {e}", file=sys.stderr)

        print("Aufgeräumt. Programm beendet.")

# --- Skriptstart ---
if __name__ == "__main__":
    main()