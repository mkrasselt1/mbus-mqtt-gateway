from multiprocessing import Process
from app.mbus import MBusClient
from app.config import Config
from app.device_manager import device_manager
from app.ha_mqtt import HomeAssistantMQTT
from app.logger import setup_app_logging, log_or_print, is_running_as_service
import signal
import sys
import time
import threading
import os

# Logging initialisieren
setup_app_logging()

# Zeige Modus an
if is_running_as_service():
    log_or_print("Starte im Service-Modus (Logging in logs/gateway.log)")
else:
    log_or_print("Starte im Konsolen-Modus (Ausgabe auf Console + Log-Datei)")

# Globale Variablen für sauberes Shutdown
shutdown_flag = False
processes = []
start_time = time.time()  # Für Uptime-Berechnung
mqtt_client = None  # Globale MQTT Client Referenz

def signal_handler(signum, frame):
    """Signal-Handler für sauberes Shutdown bei Strg+C"""
    global shutdown_flag, mqtt_client
    log_or_print("\nShutdown-Signal empfangen (Strg+C)...")
    log_or_print("Starte sauberes Herunterfahren...")
    
    shutdown_flag = True
    
    # MQTT Client ordnungsgemäß trennen
    if mqtt_client:
        try:
            log_or_print("Trenne MQTT Verbindung...")
            mqtt_client.disconnect()
        except Exception as e:
            log_or_print(f"Fehler beim MQTT Disconnect: {e}", 'warning')
    
    # Prozesse beenden
    for process in processes:
        try:
            log_or_print(f"Beende Prozess: {process.name}")
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                log_or_print(f"Prozess {process.name} antwortet nicht - erzwinge Beendigung", 'warning')
                process.kill()
        except Exception as e:
            log_or_print(f"Fehler beim Beenden von Prozess {process.name}: {e}", 'warning')
    
    log_or_print("Shutdown abgeschlossen")
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
        log_or_print("M-Bus Service beendet durch Benutzer")
    except Exception as e:
        log_or_print(f"Fehler im M-Bus Service: {e}", 'error')
    finally:
        log_or_print("M-Bus Service ordnungsgemäß beendet")

def start_gateway_monitoring():
    """Startet Gateway-Überwachung und regelmäßige Updates"""
    global shutdown_flag
    
    # Config laden für Debug-Einstellungen
    config = Config()
    enable_debug = config.data.get("enable_debug", False)
    
    # Lokale Start-Zeit für diesen Thread
    thread_start_time = time.time()
    status_counter = 0
    
    log_or_print(f"Gateway-Monitoring gestartet um {time.strftime('%H:%M:%S')}")
    
    try:
        while not shutdown_flag:
            # Gateway IP-Adresse aktualisieren
            device_manager.update_gateway_ip()
            
            # Gateway Uptime aktualisieren (seit Thread-Start)
            uptime = int(time.time() - thread_start_time)
            device_manager.update_gateway_uptime(uptime)
            
            # Debug: Uptime ausgeben (nur wenn Debug aktiviert)
            if enable_debug and uptime % 60 == 0:  # Jede Minute
                log_or_print(f"Gateway Uptime: {uptime} Sekunden ({uptime//60} Minuten)", 'debug')
            
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
        log_or_print("Gateway-Monitoring beendet durch Benutzer")
    except Exception as e:
        log_or_print(f"Fehler im Gateway-Monitoring: {e}", 'error')
    finally:
        log_or_print("Gateway-Monitoring ordnungsgemäß beendet")

if __name__ == "__main__":
    try:
        log_or_print("Starte MBus Scanner mit Home Assistant MQTT Integration...")
        
        config = Config()
        
        # MQTT Client für Home Assistant initialisieren
        log_or_print("Initialisiere Home Assistant MQTT Client...")
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
            log_or_print("MQTT erfolgreich verbunden")
            log_or_print("MQTT State wird automatisch bei Datenänderungen veröffentlicht")
        else:
            log_or_print("MQTT Verbindung fehlgeschlagen - fahre ohne MQTT fort", 'warning')
        
        # M-Bus Client initialisieren  
        mbus_client = MBusClient(
            port=config.data["mbus_port"],
            baudrate=config.data["mbus_baudrate"],
            mqtt_client=None,  # Wird über DeviceManager gekoppelt
            debug=config.data.get("enable_debug", False)
        )
        
        log_or_print("Alle Services gestartet:")
        log_or_print("- M-Bus Scanner: Scannt und liest M-Bus Geräte")
        log_or_print("- Gateway-Monitoring: Überwacht Gateway-Status")
        log_or_print("- Home Assistant MQTT: Auto-Discovery und State Publishing")
        log_or_print("Drücken Sie Strg+C für sauberes Herunterfahren")
        
        # Gateway-Monitoring in separatem Thread
        gateway_thread = threading.Thread(target=start_gateway_monitoring, name="Gateway-Monitoring", daemon=True)
        gateway_thread.start()
        
        # Bekannte Geräte aus Config laden (unabhängig von Discovery)
        known_devices = config.data.get('known_devices', [])
        enabled_devices = [d for d in known_devices if d.get('enabled', True)]
        
        if enabled_devices:
            log_or_print(f"Gefunden: {len(enabled_devices)} aktivierte Geräte in Config")
            
            # CLI Tool Setup
            use_cli_v2 = config.data.get('use_cli_v2', True)
            cli_tool = "mbus_cli_original.py" if use_cli_v2 else "mbus_cli_simple.py"
            log_or_print(f"Verwende CLI Tool: {cli_tool}")
            
            # Starte Reading-Loop für bekannte Geräte in separatem Thread
            def read_known_devices():
                import subprocess
                import json
                
                reading_interval = config.data.get("reading_interval_minutes", 1) * 60  # in Sekunden
                log_or_print(f"Reading-Intervall: {reading_interval} Sekunden")
                log_or_print("Starte Reading-Loop für bekannte Geräte...")
                
                last_read_time = 0
                while not shutdown_flag:
                    current_time = time.time()
                    
                    # Prüfe ob Reading-Intervall abgelaufen ist
                    if current_time - last_read_time >= reading_interval:
                        log_or_print(f"Starte Datenlesung für {len(enabled_devices)} Geräte...")
                        
                        devices_read = 0
                        for device in enabled_devices:
                            if shutdown_flag:
                                break
                                
                            address = device['address']
                            device_name = device.get('name', f"Device_{address}")
                            baudrate = device.get('baudrate', config.data.get('mbus_baudrate', 9600))
                            
                            try:
                                log_or_print(f"Lese {device_name} (Adresse {address})...", 'debug')
                                
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
                                                log_or_print(f"{device_name}: [OK] {record_count} Messwerte")
                                                devices_read += 1
                                            else:
                                                log_or_print(f"{device_name}: [FAIL] Keine Records gefunden", 'warning')
                                        else:
                                            log_or_print(f"{device_name}: [FAIL] CLI erfolglos", 'warning')
                                    except json.JSONDecodeError as e:
                                        log_or_print(f"{device_name}: [ERROR] JSON Parse Fehler: {e}", 'error')
                                else:
                                    log_or_print(f"{device_name}: [ERROR] CLI Fehler (Exit: {result.returncode})", 'error')
                                    if result.stderr:
                                        log_or_print(f"STDERR: {result.stderr[:200]}", 'error')
                                
                            except subprocess.TimeoutExpired:
                                log_or_print(f"{device_name}: [ERROR] Timeout (15s)", 'error')
                            except Exception as e:
                                log_or_print(f"{device_name}: [ERROR] Fehler: {e}", 'error')
                        
                        log_or_print(f"Zyklus abgeschlossen: {devices_read}/{len(enabled_devices)} erfolgreich")
                        last_read_time = current_time
                    
                    # Warte kurz vor nächster Prüfung
                    time.sleep(5)
            
            # Reading-Thread starten
            reading_thread = threading.Thread(target=read_known_devices, name="Known-Devices-Reading", daemon=True)
            reading_thread.start()
        else:
            log_or_print("Keine aktivierten Geräte in Config gefunden")
        
        # M-Bus Scanning im Hintergrund-Thread (nur wenn Discovery aktiviert)
        enable_discovery = config.data.get("enable_discovery", True)
        if enable_discovery:
            scan_interval = config.data.get("mbus_scan_interval_minutes", 60)
            mbus_thread = threading.Thread(target=lambda: mbus_client.start(scan_interval_minutes=scan_interval), name="M-Bus-Scanning", daemon=True)
            mbus_thread.start()
            log_or_print(f"M-Bus Discovery aktiviert - Scan alle {scan_interval} Minuten im Hintergrund")
        
        # Warte auf Shutdown-Signal
        log_or_print("Warte auf Shutdown-Signal...")
        try:
            while not shutdown_flag:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
    except KeyboardInterrupt:
        log_or_print("Programm beendet durch Benutzer")
    except Exception as e:
        log_or_print(f"Unerwarteter Fehler: {e}", 'error')
    finally:
        log_or_print("Programm ordnungsgemäß beendet")
