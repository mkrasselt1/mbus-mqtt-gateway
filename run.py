from multiprocessing import Process
from app.mbus import MBusClient
from app.config import Config
from app.device_manager import device_manager
from app.ha_mqtt import HomeAssistantMQTT
import signal
import sys
import time
import threading

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

def start_gateway_monitoring():
    """Startet Gateway-Überwachung und regelmäßige Updates"""
    global shutdown_flag
    
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
            
            # Debug: Uptime ausgeben
            if uptime % 60 == 0:  # Jede Minute
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
            mqtt_client=None  # Wird über DeviceManager gekoppelt
        )
        
        print("[INFO] Alle Services gestartet:")
        print("[INFO] - M-Bus Scanner: Scannt und liest M-Bus Geräte")
        print("[INFO] - Gateway-Monitoring: Überwacht Gateway-Status")
        print("[INFO] - Home Assistant MQTT: Auto-Discovery und State Publishing")
        print("[INFO] Drücken Sie Strg+C für sauberes Herunterfahren")
        
        # Gateway-Monitoring in separatem Thread
        gateway_thread = threading.Thread(target=start_gateway_monitoring, name="Gateway-Monitoring", daemon=True)
        gateway_thread.start()
        
        # M-Bus Scanning im Hauptthread
        scan_interval = config.data.get("mbus_scan_interval_minutes", 60)
        mbus_client.start(scan_interval_minutes=scan_interval)
        
    except KeyboardInterrupt:
        print("[INFO] Programm beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Unerwarteter Fehler: {e}")
    finally:
        print("[INFO] Programm ordnungsgemäß beendet")
