import paho.mqtt.client as mqtt
import json
import time
import threading
from typing import Dict, Set, Optional
from app.device_manager import device_manager, Device

class HomeAssistantMQTT:
    """MQTT Client mit Home Assistant Auto-Discovery Integration"""
    
    def __init__(self, broker: str, port: int = 1883, username: str = "", password: str = "", topic_prefix: str = "homeassistant"):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        
        # MQTT Client
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Discovery Tracking
        self.discovery_sent: Set[str] = set()  # Set der bereits gesendeten Discovery-Nachrichten
        self.last_discovery_time: Dict[str, float] = {}  # Wann wurde Discovery für jedes Gerät zuletzt gesendet
        self.connected = False
        self.ha_online = False
        
        # Threading
        self._lock = threading.Lock()
        self._heartbeat_thread = None
        self._heartbeat_running = False
        
        # Home Assistant Status überwachen
        self.client.message_callback_add("homeassistant/status", self._on_ha_status)
        
        print(f"[MQTT] HomeAssistantMQTT initialisiert für Broker {broker}:{port}")
    
    def connect(self) -> bool:
        """Verbindung zum MQTT Broker herstellen"""
        try:
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Last Will Testament setzen
            self.client.will_set(f"{self.topic_prefix}/bridge/state", "offline", retain=True)
            
            print(f"[MQTT] Verbinde zu {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            
            # Kurz warten auf Verbindung
            for _ in range(50):  # 5 Sekunden warten
                if self.connected:
                    # Heartbeat für Availability starten
                    self._start_heartbeat()
                    return True
                time.sleep(0.1)
            
            print("[MQTT] Timeout beim Verbindungsaufbau")
            return False
            
        except Exception as e:
            print(f"[MQTT] Fehler beim Verbinden: {e}")
            return False
    
    def disconnect(self):
        """Verbindung trennen"""
        if self.client:
            # Heartbeat stoppen
            self._stop_heartbeat()
            
            # Offline Status senden
            self.publish(f"{self.topic_prefix}/bridge/state", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            print("[MQTT] Verbindung getrennt")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback bei MQTT Verbindung"""
        if rc == 0:
            self.connected = True
            print("[MQTT] Erfolgreich verbunden")
            
            # Bridge Status als online setzen
            self.publish(f"{self.topic_prefix}/bridge/state", "online", retain=True)
            
            # Home Assistant Status abonnieren
            client.subscribe("homeassistant/status")
            
            # Discovery zurücksetzen bei Reconnect
            self._reset_discovery()
            
            # Discovery sofort senden (falls HA bereits online)
            threading.Timer(2.0, self._send_all_discovery).start()
            
        else:
            print(f"[MQTT] Verbindung fehlgeschlagen mit Code {rc}")
            self.connected = False
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback bei MQTT Trennung"""
        self.connected = False
        self.ha_online = False
        print(f"[MQTT] Verbindung getrennt (Code: {rc})")
        
        # Discovery zurücksetzen bei Disconnect
        self._reset_discovery()
    
    def _on_message(self, client, userdata, msg):
        """Standard Message Callback"""
        pass
    
    def _on_ha_status(self, client, userdata, msg):
        """Callback für Home Assistant Status"""
        try:
            status = msg.payload.decode()
            print(f"[MQTT] Home Assistant Status: {status}")
            
            if status == "online":
                if not self.ha_online:
                    self.ha_online = True
                    print("[MQTT] Home Assistant ist online - sende Discovery Nachrichten")
                    # Discovery mit kurzer Verzögerung senden
                    threading.Timer(2.0, self._send_all_discovery).start()
            else:
                self.ha_online = False
        except Exception as e:
            print(f"[MQTT] Fehler beim Verarbeiten des HA Status: {e}")
    
    def _reset_discovery(self):
        """Setzt Discovery-Status zurück (nach Disconnect)"""
        with self._lock:
            self.discovery_sent.clear()
            self.last_discovery_time.clear()
            print("[MQTT] Discovery-Status zurückgesetzt")
    
    def publish(self, topic: str, payload: str, retain: bool = False) -> bool:
        """Nachricht veröffentlichen"""
        if not self.connected:
            print(f"[MQTT] Nicht verbunden - kann Topic {topic} nicht veröffentlichen")
            return False
        
        try:
            result = self.client.publish(topic, payload, retain=retain)
            return result.rc == 0
        except Exception as e:
            print(f"[MQTT] Fehler beim Veröffentlichen: {e}")
            return False
    
    def _ensure_json_serializable(self, value):
        """Stellt sicher, dass ein Wert JSON-serialisierbar ist"""
        from decimal import Decimal
        
        if isinstance(value, Decimal):
            try:
                return round(float(value), 4)
            except (ValueError, OverflowError):
                return str(value)
        elif isinstance(value, float):
            return round(value, 4)
        elif hasattr(value, '__class__') and 'Decimal' in str(type(value)):
            # Fallback für dynamisch geladene Decimal-Klassen
            try:
                return round(float(value), 4)
            except (ValueError, OverflowError, TypeError):
                return str(value)
        else:
            return value
    
    def _get_friendly_sensor_name(self, attribute_name: str, unit: str = "") -> str:
        """Erstellt einen kurzen, benutzerfreundlichen Sensor-Namen"""
        # Spezielle Mappings für häufige Attribute
        name_mappings = {
            "energie_wh": "Energie",
            "energie": "Energie",
            "energie_bezug_wh": "Energie Bezug",
            "energie_einspeisung_wh": "Energie Einspeisung", 
            "wirkleistung_w": "Wirkleistung",
            "wirkleistung": "Wirkleistung",
            "leistung_w": "Leistung",
            "leistung": "Leistung",
            "spannung_v": "Spannung",
            "spannung": "Spannung",
            "strom_a": "Strom",
            "strom": "Strom",
            "temperatur": "Temperatur",
            "temperatur_c": "Temperatur",
            "ip_address": "IP-Adresse",
            "uptime": "Laufzeit",
            "status": "Status",
        }
        
        # Normalisierte Version für Vergleich
        normalized = attribute_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        
        # Spezielle Mappings prüfen
        if normalized in name_mappings:
            return name_mappings[normalized]
        
        # Energie-Varianten
        if "energie" in normalized:
            if "bezug" in normalized:
                return "Energie Bezug"
            elif "einspeisung" in normalized:
                return "Energie Einspeisung"
            else:
                return "Energie"
        
        # Zählerstände
        if "zahlerstand" in normalized or "zaehlerstand" in normalized:
            number = normalized.split("_")[-1] if "_" in normalized else ""
            return f"Zählerstand {number}" if number.isdigit() else "Zählerstand"
        
        # Messwerte
        if "messwert" in normalized:
            parts = normalized.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                return f"Messwert {parts[1]}"
            return "Messwert"
        
        # Fallback: Ersten Teil des Attributnamens verwenden und bereinigen
        clean_name = attribute_name.split("(")[0].strip()  # Entfernt Einheit in Klammern
        clean_name = clean_name.replace("_", " ").title()  # Unterstriche zu Leerzeichen, Titel-Case
        
        return clean_name
    
    def _normalize_unit_for_ha(self, unit: str) -> str:
        """Normalisiert Einheiten für Home Assistant Standards"""
        if not unit:
            return unit
        
        unit_lower = unit.lower().strip()
        
        # Temperatur-Einheiten
        if unit_lower == "c" or unit_lower == "celsius":
            return "°C"
        elif unit_lower == "k" or unit_lower == "kelvin":
            return "K"
        elif unit_lower == "f" or unit_lower == "fahrenheit":
            return "°F"
        
        # Volumen mit Hochzeichen normalisieren
        if "m^3" in unit_lower or "m3" in unit_lower:
            return unit.replace("m^3", "m³").replace("m3", "m³")
        
        # Ansonsten original zurückgeben
        return unit
    
    def _convert_to_iso8601(self, datetime_str: str) -> str:
        """Konvertiert datetime-String zu ISO 8601 mit lokaler Zeitzone"""
        from datetime import datetime, timezone
        import time
        
        try:
            # Parse das M-Bus datetime Format: "2026-01-03T13:11"
            if isinstance(datetime_str, str):
                # Füge Sekunden hinzu falls nicht vorhanden
                if len(datetime_str) == 16:  # Format: YYYY-MM-DDTHH:MM
                    datetime_str += ":00"
                
                # Parse zu datetime object
                dt = datetime.fromisoformat(datetime_str)
                
                # Füge lokale Zeitzone hinzu
                local_offset = time.timezone if time.daylight == 0 else time.altzone
                tz_hours = -local_offset // 3600
                tz_mins = (-local_offset % 3600) // 60
                
                # Formatiere mit Zeitzone: 2026-01-03T13:11:00+01:00
                return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}{tz_hours:+03d}:{tz_mins:02d}"
            
            return str(datetime_str)
        except Exception as e:
            print(f"[WARN] Datetime-Konvertierung fehlgeschlagen: {e}")
            return str(datetime_str)
    
    def _generate_discovery_config(self, device: Device, attribute_name: str) -> Optional[Dict]:
        """Generiert Home Assistant Discovery Config für ein Geräte-Attribut"""
        attribute = device.attributes.get(attribute_name)
        if not attribute:
            return None
        
        # Basis Device Info
        device_info = {
            "identifiers": [device.device_id],
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "sw_version": device.sw_version
        }
        
        # Object ID für eindeutige Identifizierung (MQTT-kompatibel - nur alphanumerisch und Unterstriche)
        # Schritt 1: Sonderzeichen ersetzen
        safe_attr_name = attribute_name.replace("^", "").replace("/", "_").replace("³", "3").replace("°", "")
        safe_attr_name = safe_attr_name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        # Schritt 2: Klammern und Leerzeichen entfernen
        safe_attr_name = safe_attr_name.replace("(", "").replace(")", "").replace(" ", "_")
        # Schritt 3: Nur alphanumerische Zeichen und Unterstriche behalten
        safe_attr_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe_attr_name)
        # Schritt 4: Mehrfache Unterstriche zu einem reduzieren und lowercase
        safe_attr_name = '_'.join(filter(None, safe_attr_name.split('_'))).lower()
        object_id = f"{device.device_id}_{safe_attr_name}"
        
        # Component Type basierend auf Attribut-Typ bestimmen
        component = "sensor"
        if attribute.value_type == "binary_sensor":
            component = "binary_sensor"
        elif attribute.value_type == "switch":
            component = "switch"
        
        # State Topic - SEPARATE für jedes Attribut (MQTT-kompatibel)
        state_topic = f"{self.topic_prefix}/device/{device.device_id}/{safe_attr_name}"
        
        # Discovery Config
        config = {
            "name": attribute_name,  # Verwende den vollen Namen mit Index (z.B. "Energie Bezug (Wh)_1")
            "unique_id": object_id,
            "state_topic": state_topic,
            "device": device_info,
            "availability": [
                {
                    "topic": f"{self.topic_prefix}/bridge/state",
                    "payload_available": "online",
                    "payload_not_available": "offline"
                },
                {
                    "topic": state_topic,
                    "payload_available": ".*",  # Jeder Wert = verfügbar
                    "value_template": "{{ 'online' if value != '' else 'offline' }}"
                }
            ],
            "availability_mode": "any",  # EINER der beiden Topics reicht
            "expire_after": 180  # 3 Minuten ohne Update = offline
        }
        
        # KEIN Value Template mehr nötig - direkter Wert
        # config["value_template"] = f"{{{{ value_json.{attribute_name} }}}}"
        
        # Unit of measurement hinzufügen wenn vorhanden
        if attribute.unit and attribute.unit.lower() != "none":
            # Normalisiere Einheiten für Home Assistant
            normalized_unit = self._normalize_unit_for_ha(attribute.unit)
            config["unit_of_measurement"] = normalized_unit
        
        # Device Class und Icon basierend auf Name/Unit setzen
        self._add_device_class_and_icon(config, attribute_name, attribute.unit)
        
        # Binary Sensor spezifische Konfiguration
        if component == "binary_sensor":
            if attribute_name.lower() == "status":
                config["payload_on"] = "online"
                config["payload_off"] = "offline"
        
        return config
    
    def _add_device_class_and_icon(self, config: Dict, attr_name: str, unit: str):
        """Fügt passende device_class und icon basierend auf Attribut hinzu"""
        attr_lower = attr_name.lower()
        unit_lower = unit.lower() if unit else ""
        
        # Energy
        if "energie" in attr_lower or "energy" in attr_lower or unit_lower in ["kwh", "mwh", "wh"]:
            config["device_class"] = "energy"
            config["icon"] = "mdi:lightning-bolt"
        
        # Power
        elif "leistung" in attr_lower or "power" in attr_lower or unit_lower in ["kw", "mw", "w"]:
            config["device_class"] = "power"
            config["icon"] = "mdi:flash"
        
        # Temperature
        elif "temperatur" in attr_lower or "temperature" in attr_lower or unit_lower in ["°c", "°f", "c", "f"]:
            config["device_class"] = "temperature"
            config["icon"] = "mdi:thermometer"
        
        # Voltage
        elif "spannung" in attr_lower or "voltage" in attr_lower or unit_lower == "v":
            config["device_class"] = "voltage"
            config["icon"] = "mdi:lightning-bolt"
        
        # Current
        elif "strom" in attr_lower or "current" in attr_lower or unit_lower == "a":
            config["device_class"] = "current"
            config["icon"] = "mdi:current-ac"
        
        # Volume (Gas/Water)
        elif "volumen" in attr_lower or "volume" in attr_lower or "m³" in unit_lower or "m3" in unit_lower:
            config["device_class"] = "gas"  # oder "water" - beide funktionieren für m³
            config["state_class"] = "total_increasing"
            config["icon"] = "mdi:gauge"
        
        # Flow rate (Durchfluss)
        elif "durchfluss" in attr_lower or "flow" in attr_lower or "m³/h" in unit_lower or "m3/h" in unit_lower or "l/h" in unit_lower:
            config["icon"] = "mdi:water-pump"
        
        # IP Address
        elif "ip" in attr_lower:
            config["icon"] = "mdi:ip-network"
        
        # Status
        elif "status" in attr_lower:
            config["icon"] = "mdi:check-circle"
        
        # Uptime
        elif "uptime" in attr_lower:
            config["icon"] = "mdi:clock"
        
        # Timestamp/DateTime
        elif "date" in attr_lower or "time" in attr_lower or unit_lower in ["date time", "datetime"]:
            config["device_class"] = "timestamp"
            config["icon"] = "mdi:clock-outline"
        
        # Default
        else:
            config["icon"] = "mdi:gauge"
    
    def _send_device_discovery(self, device: Device) -> bool:
        """Sendet Discovery für alle Attribute eines Geräts"""
        if not self.connected:
            return False
        
        success_count = 0
        total_attributes = len(device.attributes)
        
        print(f"[MQTT] Sende Discovery für {device.device_id} mit {total_attributes} Attributen")
        
        for attr_name in device.attributes.keys():
            config = self._generate_discovery_config(device, attr_name)
            if config:
                # Discovery Topic
                component = "binary_sensor" if device.attributes[attr_name].value_type == "binary_sensor" else "sensor"
                object_id = f"{device.device_id}_{attr_name}".replace(" ", "_").lower()
                discovery_topic = f"homeassistant/{component}/{object_id}/config"
                
                # Discovery Config senden
                config_json = json.dumps(config)
                if self.publish(discovery_topic, config_json, retain=True):
                    success_count += 1
                    
                    # Discovery als gesendet markieren
                    discovery_key = f"{device.device_id}_{attr_name}"
                    with self._lock:
                        self.discovery_sent.add(discovery_key)
                        self.last_discovery_time[discovery_key] = time.time()
                    
                    print(f"[MQTT] ✓ Discovery für {attr_name} erfolgreich")
                else:
                    print(f"[MQTT] ✗ Discovery für {attr_name} FEHLGESCHLAGEN!")
                
                time.sleep(0.1)  # Kurze Pause zwischen Attributen
        
        print(f"[MQTT] Discovery für {device.name}: {success_count}/{total_attributes} Attribute erfolgreich")
        return success_count == total_attributes  # Alle müssen erfolgreich sein
    
    def _send_all_discovery(self):
        """Sendet Discovery für alle Geräte"""
        if not self.connected:
            print("[MQTT] Nicht verbunden - überspringe Discovery")
            return
        
        print("[MQTT] Sende Discovery für alle Geräte...")
        devices = device_manager.get_all_devices()
        
        # Erst alle Gateway-Sensoren senden
        gateway_devices = [d for d in devices.values() if d.device_type == "gateway"]
        
        for gateway_device in gateway_devices:
            print(f"[MQTT] Sende Discovery für Gateway {gateway_device.device_id}")
            self._send_device_discovery(gateway_device)
            time.sleep(0.2)
        
        # Dann alle M-Bus Geräte
        mbus_devices = [d for d in devices.values() if d.device_type == "mbus_meter"]
        
        for device in mbus_devices:
            if device.attributes:  # Nur M-Bus Geräte mit Attributen
                print(f"[MQTT] Sende Discovery für Gerät {device.device_id}")
                self._send_device_discovery(device)
                time.sleep(0.2)  # Längere Pause für Stabilität
    
    def publish_device_state(self, device: Device, check_new_attributes: bool = True):
        """Veröffentlicht den aktuellen Status eines Geräts"""
        if not self.connected:
            return False
        
        # Prüfe auf neue Attribute und sende Discovery falls nötig
        if check_new_attributes:
            self._check_and_send_discovery_for_new_attributes(device)
        
        # SEPARATE State Topics für jedes Attribut
        for attr_name, attribute in device.attributes.items():
            value = attribute.value
            # Robuste Decimal/Float Konvertierung für JSON Serialisierung
            value = self._ensure_json_serializable(value)
            
            # MQTT-kompatiblen Attributnamen erstellen
            safe_attr_name = attr_name.replace(" ", "_").replace("(", "").replace(")", "").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").lower()
            
            # Separater State Topic für dieses Attribut
            state_topic = f"{self.topic_prefix}/device/{device.device_id}/{safe_attr_name}"
            
            # Direkten Wert (nicht JSON) senden mit RETAIN
            try:
                # Datetime-Werte in ISO 8601 mit Zeitzone konvertieren
                if attribute.unit and attribute.unit.lower() in ["date time", "datetime"]:
                    value = self._convert_to_iso8601(value)
                
                if isinstance(value, (str, int, float)):
                    payload = str(value)
                else:
                    payload = json.dumps(value)
                
                # State Topics MÜSSEN retained werden für Home Assistant
                self.publish(state_topic, payload, retain=True)
                
            except Exception as e:
                print(f"[MQTT] Fehler beim Senden von {attr_name}: {e}")
        
        return True
    
    def _check_and_send_discovery_for_new_attributes(self, device: Device):
        """Prüft ob es neue Attribute gibt und sendet Discovery dafür"""
        if not self.connected:
            return
        
        new_attributes = []
        
        with self._lock:
            for attr_name in device.attributes.keys():
                discovery_key = f"{device.device_id}_{attr_name}"
                if discovery_key not in self.discovery_sent:
                    new_attributes.append(attr_name)
        
        # Discovery für neue Attribute senden
        if new_attributes:
            print(f"[MQTT] Neue Attribute erkannt für {device.name}: {new_attributes}")
            for attr_name in new_attributes:
                config = self._generate_discovery_config(device, attr_name)
                if config:
                    # Discovery Topic mit KONSISTENTER Object-ID-Generierung
                    component = "binary_sensor" if device.attributes[attr_name].value_type == "binary_sensor" else "sensor"
                    
                    # GLEICHE Bereinigung wie in _generate_discovery_config
                    safe_attr_name = attr_name.replace(" ", "_").replace("(", "").replace(")", "").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").lower()
                    object_id = f"{device.device_id}_{safe_attr_name}"
                    
                    discovery_topic = f"homeassistant/{component}/{object_id}/config"
                    
                    # Discovery Config senden
                    config_json = json.dumps(config)
                    if self.publish(discovery_topic, config_json, retain=True):
                        # Discovery als gesendet markieren (mit ORIGINALNAMEN)
                        discovery_key = f"{device.device_id}_{attr_name}"
                        with self._lock:
                            self.discovery_sent.add(discovery_key)
                            self.last_discovery_time[discovery_key] = time.time()
                        
                        print(f"[MQTT] Discovery für neues Attribut {attr_name} gesendet")
                    else:
                        print(f"[MQTT] Fehler beim Senden der Discovery für {attr_name}")
                    
                    time.sleep(0.1)  # Kurze Pause zwischen Discovery-Nachrichten
    
    def publish_all_device_states(self):
        """Veröffentlicht den Status aller Geräte"""
        devices = device_manager.get_all_devices()
        
        for device_id, device in devices.items():
            if device.attributes:  # Nur Geräte mit Attributen
                self.publish_device_state(device)
                time.sleep(0.05)  # Kurze Pause zwischen Geräten
    
    def force_rediscovery(self):
        """Erzwingt erneute Discovery für alle Geräte"""
        print("[MQTT] Erzwinge komplette Neu-Discovery...")
        
        # Alle alten Discovery Topics löschen
        self._clear_all_discovery_topics()
        
        # Discovery Status zurücksetzen
        self._reset_discovery()
        
        if self.connected:
            # Kurz warten und dann neue Discovery senden
            threading.Timer(2.0, self._send_all_discovery).start()
            print("[MQTT] Erneute Discovery eingeleitet")
    
    def _clear_all_discovery_topics(self):
        """Löscht alle alten Discovery Topics"""
        if not self.connected:
            return
            
        # Bekannte Discovery-Präfixe löschen
        discovery_patterns = [
            "homeassistant/sensor/mbus_meter_+/+/config",
            "homeassistant/binary_sensor/mbus_meter_+/+/config", 
            "homeassistant/sensor/gateway_+/+/config",
            "homeassistant/binary_sensor/gateway_+/+/config"
        ]
        
        for pattern in discovery_patterns:
            # Leere Payload mit retain=True löscht das Topic
            self.client.publish(pattern.replace('+', '1'), "", retain=True)
            time.sleep(0.05)
        
        print("[MQTT] Alte Discovery Topics gelöscht")
    
    def _start_heartbeat(self):
        """Startet den Heartbeat-Thread für Availability"""
        if not self._heartbeat_running:
            self._heartbeat_running = True
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()
            print("[MQTT] Heartbeat für Availability gestartet")
    
    def _stop_heartbeat(self):
        """Stoppt den Heartbeat-Thread"""
        self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2)
            self._heartbeat_thread = None
            print("[MQTT] Heartbeat gestoppt")
    
    def _heartbeat_loop(self):
        """Heartbeat-Schleife für regelmäßige State-Updates"""
        while self._heartbeat_running:
            try:
                if self.connected and self.ha_online:
                    # Alle 90 Sekunden alle Gerätezustände erneuern
                    # Das liegt unter dem expire_after von 180s
                    self.publish_all_device_states()
                    
                time.sleep(90)  # 90 Sekunden Intervall
                
            except Exception as e:
                print(f"[MQTT] Fehler im Heartbeat: {e}")
                time.sleep(30)  # Bei Fehler kürzere Pause
