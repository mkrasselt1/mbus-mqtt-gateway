#!/usr/bin/env python3
"""
M-Bus MQTT Gateway Service - CLI-basierte Architektur
Robuster Service der das CLI-Tool nutzt für M-Bus Kommunikation

Features:
- Device Discovery alle 15 Minuten
- Datenlesung jede Minute 
- Home Assistant MQTT Auto-Discovery
- Prozess-basierte Isolation für Stabilität
- JSON-basierte Kommunikation
"""

import json
import time
import threading
import subprocess
import signal
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# MQTT Import
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt nicht installiert! pip install paho-mqtt")
    sys.exit(1)

# Lokale Imports
from app.config import Config
from app.ha_mqtt_cli import HomeAssistantMQTT


class MBusGatewayService:
    """Hauptservice für M-Bus MQTT Gateway mit CLI-basierter Architektur"""
    
    def __init__(self, config_file="config.json"):
        # Konfiguration laden
        self.config = Config()  # Config() lädt automatisch config.json
        print(f"[SERVICE] M-Bus Gateway Service gestartet")
        print(f"[CONFIG] Port: {self.config.data['mbus_port']}, Baudrate: {self.config.data['mbus_baudrate']}")
        
        # Service Status
        self.running = True
        self.devices = {}  # address -> device_info
        self.last_discovery = None
        self.discovery_interval = self.config.data.get('discovery_interval_minutes', 15) * 60
        self.read_interval = self.config.data.get('reading_interval_minutes', 1) * 60
        
        # Lade bekannte Geräte aus Config sofort
        self._load_known_devices_from_config()
        
        # MQTT Setup (optional für Test-Modus)
        self.mqtt_client = None
        self.ha_mqtt = None
        self.test_mode = os.environ.get('MBUS_TEST_MODE', 'false').lower() == 'true'
        
        if not self.test_mode:
            self._setup_mqtt()
        else:
            print("[SERVICE] Test-Modus: MQTT deaktiviert")
        
        # CLI Kommando Setup  
        use_cli_v2 = self.config.data.get('use_cli_v2', True)
        cli_script = "mbus_cli_v2.py" if use_cli_v2 else "mbus_cli.py"
        
        self.cli_command = [
            sys.executable,  # Python Executable
            cli_script       # CLI Script
        ]
        
        print(f"[SERVICE] CLI: {cli_script}")
        
        # Threading
        self.discovery_thread = None
        self.reading_thread = None
        self.shutdown_event = threading.Event()
        
        # M-Bus Bus Lock (verhindert gleichzeitige CLI Aufrufe)
        self.mbus_lock = threading.Lock()
        
        # Signal Handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_known_devices_from_config(self):
        """Lädt bekannte Geräte aus der Konfiguration"""
        known_devices = self.config.data.get('known_devices', [])
        
        if known_devices:
            print(f"[CONFIG] Lade {len(known_devices)} bekannte Geräte aus Config...")
            
            for device in known_devices:
                if device.get('enabled', True):
                    address = device['address']
                    device_info = {
                        "address": address,
                        "type": device.get('type', 'primary'),
                        "name": device.get('name', f"Device_{address}"),
                        "source": "config",
                        "last_seen": datetime.now().isoformat(),
                        "discovery_method": "config"
                    }
                    
                    self.devices[address] = device_info
                    print(f"[CONFIG] Gerät hinzugefügt: Adresse {address} ({device_info['name']})")
            
            print(f"[CONFIG] {len(self.devices)} Geräte aus Config geladen")
        else:
            print("[CONFIG] Keine bekannten Geräte in Config gefunden")
    
    def _publish_mqtt(self, method_name, *args, **kwargs):
        """Hilfsfunktion für MQTT Publishing mit Null-Check"""
        if self.ha_mqtt and hasattr(self.ha_mqtt, method_name):
            method = getattr(self.ha_mqtt, method_name)
            return method(*args, **kwargs)
        elif not self.test_mode:
            print(f"[MQTT] Warnung: {method_name} nicht verfügbar")
        
    def _setup_mqtt(self):
        """Initialisiert MQTT Verbindung"""
        try:
            # MQTT Client erstellen
            self.mqtt_client = mqtt.Client()
            
            # Credentials falls vorhanden
            if self.config.data.get("mqtt_username"):
                self.mqtt_client.username_pw_set(
                    self.config.data["mqtt_username"],
                    self.config.data.get("mqtt_password", "")
                )
            
            # Callbacks
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            
            # Verbinde zu MQTT Broker
            print(f"[MQTT] Verbinde zu {self.config.data['mqtt_broker']}:{self.config.data['mqtt_port']}")
            self.mqtt_client.connect(
                self.config.data["mqtt_broker"],
                self.config.data["mqtt_port"],
                60
            )
            
            # MQTT Loop in eigenem Thread starten
            self.mqtt_client.loop_start()
            
            # Home Assistant MQTT Interface
            self.ha_mqtt = HomeAssistantMQTT(self.mqtt_client, self.config.data["mqtt_topic"])
            
        except Exception as e:
            print(f"[ERROR] MQTT Setup fehlgeschlagen: {e}")
            raise
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT Verbindung hergestellt"""
        if rc == 0:
            print("[MQTT] Erfolgreich verbunden")
            # Gateway Status publizieren
            if self.ha_mqtt:
                self.ha_mqtt.publish_gateway_status("online")
        else:
            print(f"[MQTT] Verbindung fehlgeschlagen: Code {rc}")
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT Verbindung getrennt"""
        print(f"[MQTT] Verbindung getrennt: Code {rc}")
    
    def _signal_handler(self, signum, frame):
        """Signal Handler für sauberes Shutdown"""
        print(f"\n[SERVICE] Signal {signum} erhalten - Service wird beendet...")
        self.running = False
        self.shutdown_event.set()
    
    def _run_cli_command(self, command_args: List[str], timeout: int = 30, cli_tool: Optional[str] = None) -> Optional[Dict]:
        """Führt CLI Kommando aus und parst JSON Response"""
        try:
            # CLI Tool bestimmen falls nicht angegeben
            if cli_tool is None:
                use_cli_v2 = self.config.data.get('use_cli_v2', True)
                cli_tool = "mbus_cli_v2.py" if use_cli_v2 else "mbus_cli.py"
            
            # M-Bus Lock acquired - verhindert gleichzeitige Bus-Zugriffe
            print(f"[CLI] Warte auf M-Bus Lock...")
            with self.mbus_lock:
                print(f"[CLI] M-Bus Lock erhalten")
                # Vollständiges Kommando zusammenbauen mit spezifischem CLI Tool
                full_command = ["python3", cli_tool] + command_args
                
                print(f"[CLI] Führe aus: {' '.join(full_command)}")
                
                # Prozess starten
                result = subprocess.run(
                    full_command,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=os.path.dirname(os.path.abspath(__file__))  # Working Directory
                )
                
                print(f"[CLI] M-Bus Lock freigegeben")
                
                # Exit Code prüfen
                if result.returncode != 0:
                    print(f"[CLI] Fehler - Exit Code: {result.returncode}")
                    print(f"[CLI] STDERR: {result.stderr}")
                    return None
                
                # JSON parsen
                try:
                    response = json.loads(result.stdout)
                    return response
                except json.JSONDecodeError as e:
                    print(f"[CLI] JSON Parse Fehler: {e}")
                    print(f"[CLI] STDOUT: {result.stdout}")
                    return None
                
        except subprocess.TimeoutExpired:
            print(f"[CLI] Timeout nach {timeout} Sekunden")
            return None
        except Exception as e:
            print(f"[CLI] Unerwarteter Fehler: {e}")
            return None
    
    def discover_devices(self) -> bool:
        """Führt Device Discovery durch"""
        print("[DISCOVERY] Starte M-Bus Device Discovery...")
        start_time = time.time()
        
        # Verwende CLI V2 für bessere Kompatibilität  
        cli_tool = "mbus_cli_v2.py" if self.config.data.get('use_cli_v2', True) else "mbus_cli.py"
        
        # CLI Scan ausführen
        cli_args = [
            "scan",
            "--port", self.config.data["mbus_port"],
            "--baudrate", str(self.config.data["mbus_baudrate"])
        ]
        
        response = self._run_cli_command(cli_args, timeout=120, cli_tool=cli_tool)  # 2 Minuten Timeout für Scan
        
        if not response or not response.get("success"):
            print(f"[DISCOVERY] Fehlgeschlagen: {response.get('error') if response else 'Keine Antwort'}")
            
            # Fallback: Verwende bekannte Geräte aus Config
            known_devices = self.config.data.get('known_devices', [])
            if known_devices:
                print(f"[DISCOVERY] Fallback: Verwende {len(known_devices)} bekannte Geräte aus Config")
                for device in known_devices:
                    if device.get('enabled', True):
                        address = device['address']
                        if address not in self.devices:
                            print(f"[DISCOVERY] Bekanntes Gerät hinzugefügt: Adresse {address}")
                            
                            device_info = {
                                "address": address,
                                "type": device.get('type', 'primary'),
                                "name": device.get('name', f"Device_{address}"),
                                "source": "config"
                            }
                            
                            # Home Assistant Auto-Discovery senden
                            self._publish_mqtt('send_device_discovery', device_info)
                            
                            # Device Info speichern
                            self.devices[address] = {
                                "address": address,
                                "type": device_info["type"],
                                "last_seen": datetime.now().isoformat(),
                                "discovery_method": "config",
                                "name": device_info["name"]
                            }
                return len(known_devices) > 0
            
            return False
        
        # Devices verarbeiten
        found_devices = response.get("devices", [])
        new_device_count = 0
        
        for device_info in found_devices:
            address = device_info["address"]
            
            if address not in self.devices:
                new_device_count += 1
                print(f"[DISCOVERY] Neues Gerät: Adresse {address}")
                
                # Home Assistant Auto-Discovery senden
                self._publish_mqtt('send_device_discovery', device_info)
            
            # Device Info aktualisieren
            self.devices[address] = {
                "address": address,
                "device_id": device_info.get("device_id", f"device_{address}"),
                "manufacturer": device_info.get("manufacturer", "unknown"),
                "medium": device_info.get("medium", "unknown"),
                "last_seen": datetime.now().isoformat(),
                "discovery_info": device_info
            }
        
        # Discovery Status aktualisieren
        self.last_discovery = datetime.now()
        duration = time.time() - start_time
        
        print(f"[DISCOVERY] Abgeschlossen: {len(found_devices)} Geräte gefunden ({new_device_count} neu) in {duration:.2f}s")
        
        # Gateway Status Update
        self._publish_mqtt('update_gateway_status', {
            "device_count": len(self.devices),
            "last_discovery": self.last_discovery.isoformat(),
            "discovery_duration": round(duration, 2)
        })
        
        return True
    
    def read_device_data(self, address: int) -> Optional[Dict]:
        """Liest Daten von einem einzelnen Gerät"""
        cli_args = [
            "read",
            "--port", self.config.data["mbus_port"],
            "--baudrate", str(self.config.data["mbus_baudrate"]),
            "--address", str(address)
        ]
        
        response = self._run_cli_command(cli_args, timeout=15)
        
        if response and response.get("success"):
            # Letzte Aktivität aktualisieren
            if address in self.devices:
                self.devices[address]["last_read"] = datetime.now().isoformat()
                self.devices[address]["last_data"] = response
            
            return response
        else:
            error = response.get("error") if response else "Keine Antwort"
            print(f"[READ] Gerät {address} Fehler: {error}")
            return None
    
    def read_all_devices(self):
        """Liest Daten von allen bekannten Geräten"""
        if not self.devices:
            print("[READ] Keine Geräte bekannt - überspringe Datenlesung")
            return
        
        print(f"[READ] Lese Daten von {len(self.devices)} Geräten...")
        read_start = time.time()
        successful_reads = 0
        
        for address in self.devices.keys():
            try:
                device_data = self.read_device_data(address)
                
                if device_data:
                    successful_reads += 1
                    
                    # Daten zu Home Assistant senden
                    self._publish_mqtt('publish_device_data', address, device_data)
                    
                    print(f"[READ] Gerät {address}: ✅ {len(device_data.get('data', {}))} Messwerte")
                else:
                    print(f"[READ] Gerät {address}: ❌ Keine Daten")
                    
            except Exception as e:
                print(f"[READ] Gerät {address} Fehler: {e}")
                continue
        
        # Read Cycle Status
        read_duration = time.time() - read_start
        print(f"[READ] Zyklus abgeschlossen: {successful_reads}/{len(self.devices)} erfolgreich (Zeit: {read_duration:.2f}s)")
        
        # Gateway Status Update
        self._publish_mqtt('update_gateway_status', {
            "last_read": datetime.now().isoformat(),
            "successful_reads": successful_reads,
            "total_devices": len(self.devices),
            "read_duration": round(read_duration, 2)
        })
    
    def discovery_loop(self):
        """Discovery Thread - läuft alle 15 Minuten"""
        print("[DISCOVERY] Discovery Thread gestartet")
        
        # Erste Discovery sofort ausführen
        self.discover_devices()
        
        while not self.shutdown_event.is_set():
            try:
                # Warte 15 Minuten oder bis Shutdown
                if self.shutdown_event.wait(self.discovery_interval):
                    break  # Shutdown angefordert
                
                # Discovery ausführen
                self.discover_devices()
                
            except Exception as e:
                print(f"[DISCOVERY] Thread Fehler: {e}")
                # Bei Fehler trotzdem weitermachen nach kurzer Pause
                time.sleep(60)
        
        print("[DISCOVERY] Discovery Thread beendet")
    
    def reading_loop(self):
        """Reading Thread - läuft jede Minute"""
        print("[READING] Reading Thread gestartet")
        
        # Kurze Wartezeit für System-Initialisierung
        print("[READING] Warte 10 Sekunden für System-Initialisierung...")
        time.sleep(10)
        
        # Wenn keine Geräte geladen, versuche Discovery
        if not self.devices:
            print("[READING] Keine Geräte gefunden, starte Discovery...")
            self.discover_devices()
        
        # Falls immer noch keine Geräte, warte auf Discovery
        retry_count = 0
        while not self.devices and not self.shutdown_event.is_set() and retry_count < 6:
            print(f"[READING] Warte auf Geräte... (Versuch {retry_count + 1}/6)")
            time.sleep(10)
            retry_count += 1
        
        if not self.devices:
            print("[READING] WARNUNG: Keine Geräte gefunden, aber Reading-Loop startet trotzdem")
        else:
            print(f"[READING] {len(self.devices)} Geräte verfügbar, starte Reading-Loop")
        
        while not self.shutdown_event.is_set():
            try:
                # Daten von allen Geräten lesen
                if self.devices:
                    self.read_all_devices()
                else:
                    print("[READING] Keine Geräte verfügbar, überspringe Reading")
                
                # Warte 1 Minute oder bis Shutdown
                if self.shutdown_event.wait(self.read_interval):
                    break  # Shutdown angefordert
                
            except Exception as e:
                print(f"[READING] Thread Fehler: {e}")
                # Bei Fehler trotzdem weitermachen nach kurzer Pause
                time.sleep(30)
        
        print("[READING] Reading Thread beendet")
    
    def run(self):
        """Hauptmethode - startet den Service"""
        try:
            print("[SERVICE] Starte M-Bus Gateway Service...")
            
            # CLI Tool Verfügbarkeit prüfen
            cli_test = self._run_cli_command([
                "test",
                "--port", self.config.data["mbus_port"],
                "--baudrate", str(self.config.data["mbus_baudrate"])
            ])
            
            if not cli_test or not cli_test.get("success"):
                print(f"[ERROR] CLI Tool Test fehlgeschlagen: {cli_test.get('error') if cli_test else 'Keine Antwort'}")
                return False
            
            print("[SERVICE] CLI Tool Test erfolgreich")
            
            # Threads starten
            self.discovery_thread = threading.Thread(target=self.discovery_loop, name="Discovery")
            self.reading_thread = threading.Thread(target=self.reading_loop, name="Reading")
            
            self.discovery_thread.start()
            self.reading_thread.start()
            
            print("[SERVICE] Service erfolgreich gestartet")
            print("[SERVICE] Drücke Ctrl+C zum Beenden")
            
            # Hauptthread wartet auf Shutdown
            while self.running:
                time.sleep(1)
                
                # Thread Status prüfen
                if not self.discovery_thread.is_alive():
                    print("[ERROR] Discovery Thread ist gestorben!")
                    break
                if not self.reading_thread.is_alive():
                    print("[ERROR] Reading Thread ist gestorben!")
                    break
            
        except Exception as e:
            print(f"[ERROR] Service Fehler: {e}")
            return False
        
        finally:
            self._shutdown()
        
        return True
    
    def _shutdown(self):
        """Sauberes Shutdown"""
        print("[SERVICE] Shutdown wird eingeleitet...")
        
        # Shutdown Event setzen
        self.shutdown_event.set()
        
        # Gateway offline Status
        if self.ha_mqtt:
            self.ha_mqtt.publish_gateway_status("offline")
        
        # Threads beenden
        if self.discovery_thread and self.discovery_thread.is_alive():
            print("[SERVICE] Warte auf Discovery Thread...")
            self.discovery_thread.join(timeout=5)
        
        if self.reading_thread and self.reading_thread.is_alive():
            print("[SERVICE] Warte auf Reading Thread...")
            self.reading_thread.join(timeout=5)
        
        # MQTT beenden
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        print("[SERVICE] Shutdown abgeschlossen")


def main():
    """Hauptfunktion"""
    print("M-Bus MQTT Gateway Service - CLI-basierte Architektur")
    print("=" * 60)
    
    try:
        # Service erstellen und starten
        service = MBusGatewayService()
        success = service.run()
        
        if success:
            print("[MAIN] Service ordnungsgemäß beendet")
            sys.exit(0)
        else:
            print("[MAIN] Service mit Fehler beendet")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n[MAIN] Service durch Benutzer beendet")
        sys.exit(0)
    except Exception as e:
        print(f"[MAIN] Unerwarteter Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()