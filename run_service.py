"""
Service Wrapper mit vollständiger Fehlerbehandlung
Fängt ALLE Fehler ab und schreibt sie ins Log
"""
import sys
import os
import traceback
from datetime import datetime

# Stelle sicher, dass wir im richtigen Verzeichnis sind
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

# Log-Verzeichnis erstellen
log_dir = os.path.join(script_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

# Debug-Log-Datei
debug_log = os.path.join(log_dir, 'service_debug.log')

def write_debug(message):
    """Schreibe Debug-Nachricht in separate Datei"""
    try:
        with open(debug_log, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} - {message}\n")
            f.flush()
    except Exception as e:
        # Wenn selbst das fehlschlägt, versuche in stderr
        try:
            print(f"DEBUG LOG FAILED: {e}", file=sys.stderr)
        except:
            pass

# Start
write_debug("="*60)
write_debug("SERVICE WRAPPER GESTARTET")
write_debug(f"Python: {sys.version}")
write_debug(f"Executable: {sys.executable}")
write_debug(f"CWD: {os.getcwd()}")
write_debug(f"Script Dir: {script_dir}")
write_debug(f"sys.path: {sys.path[:3]}")

try:
    write_debug("Importiere app.logger...")
    from app.logger import setup_app_logging, is_running_as_service
    write_debug("✓ app.logger importiert")
    
    write_debug("Setup Logging...")
    setup_app_logging()
    write_debug(f"✓ Logging setup abgeschlossen (Service-Modus: {is_running_as_service()})")
    
    write_debug("Importiere run.py Module...")
    # Jetzt das eigentliche Programm starten
    import run
    write_debug("✓ run.py erfolgreich importiert und gestartet")
    
except Exception as e:
    write_debug(f"KRITISCHER FEHLER: {e}")
    write_debug(f"Exception Type: {type(e).__name__}")
    write_debug("\nFull Traceback:")
    write_debug(traceback.format_exc())
    write_debug("="*60)
    
    # Exit mit Code 1 = Fehler
    sys.exit(1)
