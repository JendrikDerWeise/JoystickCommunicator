# test_enum.py
import sys
try:
    # Stelle sicher, dass rlink_wrapper im selben Verzeichnis ist
    # oder im PYTHONPATH
    from rlink_wrapper import MspRlink, RLinkError
    print("Wrapper importiert. Suche Geräte...")
    # Stelle sicher, dass die fehlerhafte udev-Regel auskommentiert/entfernt ist!
    devices = MspRlink.enumerate_devices()
    print(f"Enumeration erfolgreich: {len(devices)} Gerät(e) gefunden.")
    for i, dev in enumerate(devices):
         print(f"  [{i}] {dev.serial}: {dev.description}")
except ImportError as e:
    print(f"Import Fehler: {e}", file=sys.stderr)
except RLinkError as e:
    print(f"RLinkError während Enumeration: {e}", file=sys.stderr)
except Exception as e:
    print(f"Anderer Fehler während Enumeration: {e}", file=sys.stderr)