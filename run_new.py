from multiprocessing import Process
from app.mbus import MBusClient
from app.config import Config
import signal
import sys
import time

# Globale Variablen für sauberes Shutdown
shutdown_flag = False
processes = []

def signal_handler(signum, frame):
    """Signal-Handler für sauberes Shutdown bei Strg+C"""
    global shutdown_flag
    print("\n[INFO] Shutdown-Signal empfangen (Strg+C)...")
    print("[INFO] Starte sauberes Herunterfahren...")
    
    shutdown_flag = True
    
    # Prozesse beenden
    for process in processes:
        try:
            print(f"[INFO] Beende Prozess: {process.name}")
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                print(f"[WARN] Prozess {process.name} antwortet nicht - erzwinge Beendigung")
                process.kill()
        except Exception as e:
            print(f"[WARN] Fehler beim Beenden von Prozess {process.name}: {e}")
    
    print("[INFO] Shutdown abgeschlossen")
    sys.exit(0)

# Signal-Handler registrieren
signal.signal(signal.SIGINT, signal_handler)

def start_mbus_scanning():
    """Startet nur M-Bus Scanning ohne MQTT"""
    global shutdown_flag
    
    config = Config()
    
    # M-Bus Client ohne MQTT initialisieren
    mbus_client = MBusClient(
        port=config.data["mbus_port"],
        baudrate=config.data["mbus_baudrate"],
        mqtt_client=None  # Kein MQTT
    )
    
    # Scan-Intervall aus Konfiguration lesen (Standard: 60 Minuten)
    scan_interval = config.data.get("mbus_scan_interval_minutes", 60)
    
    try:
        mbus_client.start(scan_interval_minutes=scan_interval)
    except KeyboardInterrupt:
        print("[INFO] M-Bus Service beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Fehler im M-Bus Service: {e}")
    finally:
        print("[INFO] M-Bus Service ordnungsgemäß beendet")

if __name__ == "__main__":
    try:
        print("[INFO] Starte MBus Scanner...")
        
        # Nur M-Bus Prozess starten
        mbus_process = Process(target=start_mbus_scanning, name="MBus-Service")
        processes.append(mbus_process)
        
        mbus_process.start()
        
        print("[INFO] M-Bus Scanner gestartet")
        print("[INFO] Drücken Sie Strg+C für sauberes Herunterfahren")
        
        # Hauptthread wartet auf Prozesse
        try:
            while not shutdown_flag:
                # Prüfe ob Prozess noch lebt
                if not mbus_process.is_alive():
                    print(f"[WARN] Prozess {mbus_process.name} ist unerwartet beendet")
                    break
                
                time.sleep(5)  # Alle 5 Sekunden prüfen
        except KeyboardInterrupt:
            pass  # Wird vom Signal-Handler behandelt
        
    except KeyboardInterrupt:
        print("[INFO] Hauptprozess beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Unerwarteter Fehler: {e}")
    finally:
        # Sauberes Shutdown falls nicht durch Signal-Handler ausgelöst
        if not shutdown_flag:
            signal_handler(signal.SIGINT, None)
