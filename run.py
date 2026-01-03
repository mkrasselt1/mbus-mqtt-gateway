from multiprocessing import Process
from app.mbus import MBusClient
from app.config import Config
from app.device_manager import device_manager
from app.ha_mqtt import HomeAssistantMQTT
import signal
import sys
import time
import threading
import logging
import os

# Logging für M-Bus Library konfigurieren
logging.getLogger('meterbus').setLevel(logging.WARNING)
logging.getLogger('serial').setLevel(logging.WARNING)

# Globale Variablen für sauberes Shutdown
shutdown_flag = False
processes = []
start_time = time.time()  # Für Uptime-Berechnung
mqtt_client = None  # Globale MQTT Client Referenz

def signal_handler(signum, frame):
    """Signal-Handler für sauberes Shutdown bei Strg+C"""
    global shutdown_flag, mqtt_client
    print("\n[INFO] Shutdown-Signal empfangen (Strg+C)...")
    print("[INFO] Starte sauberes Herunterfahren...")
    
    shutdown_flag = True
    
    # MQTT Client ordnungsgemäß trennen
    if mqtt_client:
        try:
            print("[INFO] Trenne MQTT Verbindung...")
            mqtt_client.disconnect()
        except Exception as e:
            print(f"[WARN] Fehler beim MQTT Disconnect: {e}")
    
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
        mqtt_client=None,  # Kein MQTT
        debug=config.data.get("enable_debug", False)
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

def start_gateway_monitoring():
    """Startet Gateway-Überwachung und regelmäßige Updates"""
    global shutdown_flag
    
    # Config laden für Debug-Einstellungen
    config = Config()
    enable_debug = config.data.get("enable_debug", False)
    
    # Lokale Start-Zeit für diesen Thread
    thread_start_time = time.time()
    status_counter = 0
    
    print(f"[INFO] Gateway-Monitoring gestartet um {time.strftime('%H:%M:%S')}")
    
    try:
        while not shutdown_flag:
            # Gateway IP-Adresse aktualisieren
            device_manager.update_gateway_ip()
            
            # Gateway Uptime aktualisieren (seit Thread-Start)
            uptime = int(time.time() - thread_start_time)
            device_manager.update_gateway_uptime(uptime)
            
            # Debug: Uptime ausgeben (nur wenn Debug aktiviert)
            if enable_debug and uptime % 60 == 0:  # Jede Minute
                print(f"[DEBUG] Gateway Uptime: {uptime} Sekunden ({uptime//60} Minuten)")
            
            # Status nur alle 5 Minuten ausgeben (20 * 15 Sekunden)
            status_counter += 1
            if status_counter >= 20:
                device_manager.print_status()
                status_counter = 0
            
            # 15 Sekunden warten (mit Shutdown-Check) - häufigere Updates
            for _ in range(15):
                if shutdown_flag:
                    break
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("[INFO] Gateway-Monitoring beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Fehler im Gateway-Monitoring: {e}")
    finally:
        print("[INFO] Gateway-Monitoring ordnungsgemäß beendet")

if __name__ == "__main__":
    try:
        print("[INFO] Starte MBus Scanner mit Home Assistant MQTT Integration...")
        
        config = Config()
        
        # MQTT Client für Home Assistant initialisieren
        print("[INFO] Initialisiere Home Assistant MQTT Client...")
        mqtt_client = HomeAssistantMQTT(
            broker=config.data["mqtt_broker"],
            port=config.data["mqtt_port"],
            username=config.data.get("mqtt_username", ""),
            password=config.data.get("mqtt_password", ""),
            topic_prefix=config.data.get("mqtt_topic", "homeassistant")
        )
        
        # MQTT Client mit DeviceManager verknüpfen
        device_manager.set_mqtt_client(mqtt_client)
        
        # MQTT Verbindung aufbauen
        if mqtt_client.connect():
            print("[INFO] MQTT erfolgreich verbunden")
            print("[INFO] MQTT State wird automatisch bei Datenänderungen veröffentlicht")
        else:
            print("[WARN] MQTT Verbindung fehlgeschlagen - fahre ohne MQTT fort")
        
        # M-Bus Client initialisieren  
        mbus_client = MBusClient(
            port=config.data["mbus_port"],
            baudrate=config.data["mbus_baudrate"],
            mqtt_client=None,  # Wird über DeviceManager gekoppelt
            debug=config.data.get("enable_debug", False)
        )
        
        print("[INFO] Alle Services gestartet:")
        print("[INFO] - M-Bus Scanner: Scannt und liest M-Bus Geräte")
        print("[INFO] - Gateway-Monitoring: Überwacht Gateway-Status")
        print("[INFO] - Home Assistant MQTT: Auto-Discovery und State Publishing")
        print("[INFO] Drücken Sie Strg+C für sauberes Herunterfahren")
        
        # Gateway-Monitoring in separatem Thread
        gateway_thread = threading.Thread(target=start_gateway_monitoring, name="Gateway-Monitoring", daemon=True)
        gateway_thread.start()
        
        # Bekannte Geräte aus Config laden (unabhängig von Discovery)
        known_devices = config.data.get('known_devices', [])
        enabled_devices = [d for d in known_devices if d.get('enabled', True)]
        
        if enabled_devices:
            print(f"[INFO] Gefunden: {len(enabled_devices)} aktivierte Geräte in Config")
            
            # CLI Tool Setup
            use_cli_v2 = config.data.get('use_cli_v2', True)
            cli_tool = "mbus_cli_original.py" if use_cli_v2 else "mbus_cli_simple.py"
            print(f"[INFO] Verwende CLI Tool: {cli_tool}")
            
            # Starte Reading-Loop für bekannte Geräte in separatem Thread
            def read_known_devices():
                import subprocess
                import json
                
                reading_interval = config.data.get("reading_interval_minutes", 1) * 60  # in Sekunden
                print(f"[INFO] Reading-Intervall: {reading_interval} Sekunden")
                print(f"[INFO] Starte Reading-Loop für bekannte Geräte...")
                
                last_read_time = 0
                while not shutdown_flag:
                    current_time = time.time()
                    
                    # Prüfe ob Reading-Intervall abgelaufen ist
                    if current_time - last_read_time >= reading_interval:
                        print(f"[READ] Starte Datenlesung für {len(enabled_devices)} Geräte...")
                        
                        devices_read = 0
                        for device in enabled_devices:
                            if shutdown_flag:
                                break
                                
                            address = device['address']
                            device_name = device.get('name', f"Device_{address}")
                            baudrate = device.get('baudrate', config.data.get('mbus_baudrate', 9600))
                            
                            try:
                                print(f"[READ] Lese {device_name} (Adresse {address})...")
                                
                                cli_args = [
                                    sys.executable, cli_tool,
                                    "--port", config.data["mbus_port"],
                                    "--baudrate", str(baudrate),
                                    "read",
                                    "--address", str(address)
                                ]
                                
                                result = subprocess.run(
                                    cli_args,
                                    capture_output=True,
                                    text=True,
                                    timeout=15,
                                    cwd=os.path.dirname(os.path.abspath(__file__))
                                )
                                
                                if result.returncode == 0:
                                    try:
                                        device_data = json.loads(result.stdout)
                                        if device_data.get("success"):
                                            # Daten über DeviceManager verarbeiten
                                            if 'data' in device_data and 'records' in device_data['data']:
                                                normalized_data = {
                                                    'device_name': device_name,  # Name aus Config
                                                    'manufacturer': device_data['data'].get('manufacturer', 'Unknown'),
                                                    'identification': device_data['data'].get('identification', ''),
                                                    'access_no': device_data['data'].get('access_no', 0),
                                                    'medium': device_data['data'].get('medium', 'Unknown'),
                                                    'records': device_data['data']['records']
                                                }
                                            elif 'records' in device_data:
                                                normalized_data = device_data.copy()
                                                normalized_data['device_name'] = device_name  # Name aus Config
                                            else:
                                                normalized_data = None
                                            
                                            if normalized_data and 'records' in normalized_data:
                                                # Device Manager aktualisieren (sendet automatisch MQTT)
                                                device_manager.update_mbus_device_data(address, normalized_data)
                                                
                                                record_count = len(normalized_data['records'])
                                                print(f"[READ] {device_name}: ✅ {record_count} Messwerte")
                                                devices_read += 1
                                            else:
                                                print(f"[READ] {device_name}: ❌ Keine Records gefunden")
                                        else:
                                            print(f"[READ] {device_name}: ❌ CLI erfolglos")
                                    except json.JSONDecodeError as e:
                                        print(f"[READ] {device_name}: ❌ JSON Parse Fehler: {e}")
                                else:
                                    print(f"[READ] {device_name}: ❌ CLI Fehler (Exit: {result.returncode})")
                                    if result.stderr:
                                        print(f"[READ] STDERR: {result.stderr[:200]}")
                                
                            except subprocess.TimeoutExpired:
                                print(f"[READ] {device_name}: ❌ Timeout (15s)")
                            except Exception as e:
                                print(f"[READ] {device_name}: ❌ Fehler: {e}")
                        
                        print(f"[READ] Zyklus abgeschlossen: {devices_read}/{len(enabled_devices)} erfolgreich")
                        last_read_time = current_time
                    
                    # Warte kurz vor nächster Prüfung
                    time.sleep(5)
            
            # Reading-Thread starten
            reading_thread = threading.Thread(target=read_known_devices, name="Known-Devices-Reading", daemon=True)
            reading_thread.start()
        else:
            print("[INFO] Keine aktivierten Geräte in Config gefunden")
        
        # M-Bus Scanning im Hintergrund-Thread (nur wenn Discovery aktiviert)
        enable_discovery = config.data.get("enable_discovery", True)
        if enable_discovery:
            scan_interval = config.data.get("mbus_scan_interval_minutes", 60)
            mbus_thread = threading.Thread(target=lambda: mbus_client.start(scan_interval_minutes=scan_interval), name="M-Bus-Scanning", daemon=True)
            mbus_thread.start()
            print(f"[INFO] M-Bus Discovery aktiviert - Scan alle {scan_interval} Minuten im Hintergrund")
        
        # Warte auf Shutdown-Signal
        print("[INFO] Warte auf Shutdown-Signal...")
        try:
            while not shutdown_flag:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
    except KeyboardInterrupt:
        print("[INFO] Programm beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Unerwarteter Fehler: {e}")
    finally:
        print("[INFO] Programm ordnungsgemäß beendet")
