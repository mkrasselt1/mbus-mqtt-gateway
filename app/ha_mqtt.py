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
        
        # Object ID für eindeutige Identifizierung
        object_id = f"{device.device_id}_{attribute_name}".replace(" ", "_").lower()
        
        # Component Type basierend auf Attribut-Typ bestimmen
        component = "sensor"
        if attribute.value_type == "binary_sensor":
            component = "binary_sensor"
        elif attribute.value_type == "switch":
            component = "switch"
        
        # State Topic
        state_topic = f"{self.topic_prefix}/device/{device.device_id}/state"
        
        # Discovery Config
        config = {
            "name": f"{device.name} {attribute_name}",
            "unique_id": object_id,
            "state_topic": state_topic,
            "device": device_info,
            "availability_topic": f"{self.topic_prefix}/bridge/state",
            "payload_available": "online",
            "payload_not_available": "offline"
        }
        
        # Value Template für das spezifische Attribut
        config["value_template"] = f"{{{{ value_json.{attribute_name} }}}}"
        
        # Unit of measurement hinzufügen wenn vorhanden
        if attribute.unit and attribute.unit.lower() != "none":
            config["unit_of_measurement"] = attribute.unit
        
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
        
        # Volume
        elif "volumen" in attr_lower or "volume" in attr_lower or unit_lower in ["m³", "l", "m3"]:
            config["icon"] = "mdi:gauge"
        
        # Flow rate
        elif "strom" in attr_lower or "flow" in attr_lower or "m³/h" in unit_lower:
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
        
        # Default
        else:
            config["icon"] = "mdi:gauge"
    
    def _send_device_discovery(self, device: Device) -> bool:
        """Sendet Discovery für alle Attribute eines Geräts"""
        if not self.connected:
            return False
        
        success_count = 0
        total_attributes = len(device.attributes)
        
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
        
        print(f"[MQTT] Discovery für {device.name}: {success_count}/{total_attributes} Attribute gesendet")
        return success_count > 0
    
    def _send_all_discovery(self):
        """Sendet Discovery für alle Geräte"""
        if not self.connected:
            print("[MQTT] Nicht verbunden - überspringe Discovery")
            return
        
        print("[MQTT] Sende Discovery für alle Geräte...")
        devices = device_manager.get_all_devices()
        
        for device_id, device in devices.items():
            if device.attributes:  # Nur Geräte mit Attributen
                self._send_device_discovery(device)
                time.sleep(0.1)  # Kurze Pause zwischen Geräten
    
    def publish_device_state(self, device: Device, check_new_attributes: bool = True):
        """Veröffentlicht den aktuellen Status eines Geräts"""
        if not self.connected:
            return False
        
        # Prüfe auf neue Attribute und sende Discovery falls nötig
        if check_new_attributes:
            self._check_and_send_discovery_for_new_attributes(device)
        
        # State aus allen Attributen zusammenstellen
        state = {}
        for attr_name, attribute in device.attributes.items():
            value = attribute.value
            # Robuste Decimal/Float Konvertierung für JSON Serialisierung
            value = self._ensure_json_serializable(value)
            state[attr_name] = value
        
        # State Topic
        state_topic = f"{self.topic_prefix}/device/{device.device_id}/state"
        
        # State als JSON veröffentlichen mit Decimal-sicherer Serialisierung
        try:
            state_json = json.dumps(state)
        except TypeError as e:
            print(f"[MQTT] JSON Serialisierung fehlgeschlagen: {e}")
            # Fallback: Alle Werte zu Strings konvertieren
            state_safe = {}
            for k, v in state.items():
                try:
                    state_safe[k] = float(v) if isinstance(v, (int, float)) or hasattr(v, '__float__') else str(v)
                except:
                    state_safe[k] = str(v)
            state_json = json.dumps(state_safe)
        success = self.publish(state_topic, state_json)
        
        if success:
            print(f"[MQTT] State für {device.name} veröffentlicht: {len(state)} Attribute")
        
        return success
    
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
                    # Discovery Topic
                    component = "binary_sensor" if device.attributes[attr_name].value_type == "binary_sensor" else "sensor"
                    object_id = f"{device.device_id}_{attr_name}".replace(" ", "_").lower()
                    discovery_topic = f"homeassistant/{component}/{object_id}/config"
                    
                    # Discovery Config senden
                    config_json = json.dumps(config)
                    if self.publish(discovery_topic, config_json, retain=True):
                        # Discovery als gesendet markieren
                        discovery_key = f"{device.device_id}_{attr_name}"
                        with self._lock:
                            self.discovery_sent.add(discovery_key)
                            self.last_discovery_time[discovery_key] = time.time()
                        
                        print(f"[MQTT] Discovery für neues Attribut {attr_name} gesendet")
                    
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
        self._reset_discovery()
        if self.connected:
            threading.Timer(1.0, self._send_all_discovery).start()
            print("[MQTT] Erneute Discovery eingeleitet")
