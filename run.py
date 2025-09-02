from multiprocessing import Process
from app.mbus import MBusClient
from app.mqtt import MQTTClient
from app.config import Config
import socket
import time
import uuid
import signal
import sys

# Globale Variablen für sauberes Shutdown
shutdown_flag = False
processes = []
mqtt_clients = []

def signal_handler(signum, frame):
    """Signal-Handler für sauberes Shutdown bei Strg+C"""
    global shutdown_flag
    print("\n[INFO] Shutdown-Signal empfangen (Strg+C)...")
    print("[INFO] Starte sauberes Herunterfahren...")
    
    shutdown_flag = True
    
    # MQTT-Clients ordnungsgemäß trennen
    for client in mqtt_clients:
        try:
            print(f"[INFO] Trenne MQTT-Client...")
            client.disconnect()
        except Exception as e:
            print(f"[WARN] Fehler beim Trennen des MQTT-Clients: {e}")
    
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
signal.signal(signal.SIGTERM, signal_handler)

def start_mbus_to_mqtt():
    global shutdown_flag, mqtt_clients
    
    config = Config()
    mqtt_client = MQTTClient(
        config.data["mqtt_broker"],
        config.data["mqtt_port"],
        username=config.data["mqtt_username"],
        password=config.data["mqtt_password"],
        topic_prefix=config.data["mqtt_topic"]
    )
    mqtt_clients.append(mqtt_client)  # Für sauberes Shutdown registrieren
    mqtt_client.connect()

    # Pass the mqtt_client to MBusClient
    mbus_client = MBusClient(
        port=config.data["mbus_port"],
        baudrate=config.data["mbus_baudrate"],
        mqtt_client=mqtt_client,)
    
    # Scan-Intervall aus Konfiguration lesen (Standard: 60 Minuten)
    scan_interval = config.data.get("mbus_scan_interval_minutes", 60)
    
    try:
        mbus_client.start(scan_interval_minutes=scan_interval)
    except KeyboardInterrupt:
        print("[INFO] M-Bus Service beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Fehler im M-Bus Service: {e}")
    finally:
        mqtt_client.disconnect()
        print("[INFO] M-Bus Service ordnungsgemäß beendet")
        
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_mac():
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> ele) & 0xff:02x}' for ele in range(40, -1, -8))

def publish_ip_loop():
    global shutdown_flag, mqtt_clients
    
    config = Config()
    mqtt_client = MQTTClient(
        config.data["mqtt_broker"],
        config.data["mqtt_port"],
        username=config.data["mqtt_username"],
        password=config.data["mqtt_password"],
        topic_prefix=config.data["mqtt_topic"]
    )
    mqtt_clients.append(mqtt_client)  # Für sauberes Shutdown registrieren
    
    print(f"[DEBUG] Verbinde zu MQTT-Broker {config.data['mqtt_broker']}:{config.data['mqtt_port']} ...")
    mqtt_client.connect()
    print("[DEBUG] MQTT-Verbindung hergestellt.")
    mac = get_mac().replace(":", "")
    print(f"[DEBUG] Verwende MAC-Adresse: {mac}")
    
    # IP-Discovery-Callback registrieren
    def send_ip_discovery():
        mqtt_client.publish_ip_discovery(mac)
        print("[DEBUG] IP-Discovery gesendet")
    
    mqtt_client.add_discovery_callback(send_ip_discovery)
    
    # Legacy Reconnect-Callback setzen
    mqtt_client.set_reconnect_callback(send_ip_discovery)
    
    # Initial Discovery zur Warteschlange hinzufügen
    mqtt_client.publish_ip_discovery(mac)
    print("[DEBUG] IP-Discovery zur Warteschlange hinzugefügt.")
    
    try:
        while not shutdown_flag:
            ip = get_local_ip()
            topic = f"system/{mac}/ip"
            print(f"[DEBUG] Sende IP {ip} an Topic {mqtt_client.topic_prefix}/{topic}")
            mqtt_client.publish(topic, ip)
            
            # Sleep mit regelmäßiger Überprüfung des Shutdown-Flags
            for _ in range(60):  # 60 Sekunden aufteilen in 1-Sekunden-Schritte
                if shutdown_flag:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        print("[INFO] IP-Loop beendet durch Benutzer")
    except Exception as e:
        print(f"[ERROR] Fehler in IP-Loop: {e}")
    finally:
        mqtt_client.disconnect()
        print("[INFO] IP-Service ordnungsgemäß beendet")

if __name__ == "__main__":
    try:
        print("[INFO] Starte MBus MQTT Gateway...")
        
        # Prozesse starten und registrieren
        mbus_process = Process(target=start_mbus_to_mqtt, name="MBus-Service")
        ip_process = Process(target=publish_ip_loop, name="IP-Service")
        
        processes.extend([mbus_process, ip_process])
        
        mbus_process.start()
        ip_process.start()
        
        print("[INFO] Alle Services gestartet")
        print("[INFO] MBus MQTT Gateway läuft...")
        print("[INFO] Drücken Sie Strg+C für sauberes Herunterfahren")
        
        # Hauptthread wartet auf Prozesse (ohne Webserver)
        try:
            while not shutdown_flag:
                # Prüfe ob Prozesse noch leben
                for process in processes:
                    if not process.is_alive():
                        print(f"[WARN] Prozess {process.name} ist unerwartet beendet")
                
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
