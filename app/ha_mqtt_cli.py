"""
Home Assistant MQTT Interface - CLI-kompatible Version
Erweiterte Version für JSON-basierte CLI-Daten
"""

import json
import time
from typing import Dict, Any, Optional
from datetime import datetime


class HomeAssistantMQTT:
    """Home Assistant MQTT Interface für CLI-basierte M-Bus Daten"""
    
    def __init__(self, mqtt_client, topic_prefix="homeassistant"):
        self.mqtt_client = mqtt_client
        self.topic_prefix = topic_prefix
        self.discovery_sent = set()  # Bereits gesendete Discoveries
        self.gateway_topic = f"{topic_prefix}/sensor/mbus_gateway"
        
        print(f"[HA-MQTT] Home Assistant Interface initialisiert (Topic: {topic_prefix})")
    
    def send_device_discovery(self, device_info: Dict[str, Any]):
        """Sendet Home Assistant Auto-Discovery für ein neues Gerät"""
        try:
            address = device_info["address"]
            device_id = device_info.get("device_id", f"device_{address}")
            manufacturer = device_info.get("manufacturer", "M-Bus")
            medium = device_info.get("medium", "unknown")
            
            print(f"[HA-MQTT] Sende Discovery für Gerät {device_id} (Adresse {address})")
            
            # Device Information für Home Assistant
            device_config = {
                "identifiers": [f"mbus_{device_id}"],
                "name": f"M-Bus {device_id}",
                "manufacturer": manufacturer,
                "model": f"{medium.title()} Meter",
                "sw_version": "CLI-Gateway-v1.0"
            }
            
            # Basis-Konfiguration für Sensoren
            base_config = {
                "device": device_config,
                "availability": [
                    {
                        "topic": f"{self.gateway_topic}/state",
                        "value_template": "{{ value_json.state }}"
                    },
                    {
                        "topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/availability"
                    }
                ],
                "availability_mode": "any"
            }
            
            # Standard-Sensoren für M-Bus Geräte erstellen
            sensors = self._create_standard_sensors(device_id, base_config)
            
            # Discovery-Nachrichten senden
            for sensor_name, sensor_config in sensors.items():
                discovery_topic = f"{self.topic_prefix}/sensor/mbus_{device_id}_{sensor_name}/config"
                self.mqtt_client.publish(
                    discovery_topic,
                    json.dumps(sensor_config),
                    retain=True
                )
            
            # Gerät als verfügbar markieren
            availability_topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/availability"
            self.mqtt_client.publish(availability_topic, "online", retain=True)
            
            # Discovery-Status speichern
            self.discovery_sent.add(device_id)
            
            print(f"[HA-MQTT] Discovery für {device_id} gesendet ({len(sensors)} Sensoren)")
            
        except Exception as e:
            print(f"[HA-MQTT] Discovery Fehler für Gerät {device_info}: {e}")
    
    def _create_standard_sensors(self, device_id: str, base_config: Dict) -> Dict[str, Dict]:
        """Erstellt Standard-Sensoren für M-Bus Geräte"""
        sensors = {}
        
        # Energy Sensor (kWh)
        sensors["energy"] = {
            **base_config,
            "name": f"M-Bus {device_id} Energy",
            "unique_id": f"mbus_{device_id}_energy",
            "state_topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/energy/state",
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
            "icon": "mdi:flash"
        }
        
        # Power Sensor (W)
        sensors["power"] = {
            **base_config,
            "name": f"M-Bus {device_id} Power",
            "unique_id": f"mbus_{device_id}_power",
            "state_topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/power/state",
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
            "icon": "mdi:lightning-bolt"
        }
        
        # Voltage Sensor (V)
        sensors["voltage"] = {
            **base_config,
            "name": f"M-Bus {device_id} Voltage",
            "unique_id": f"mbus_{device_id}_voltage",
            "state_topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/voltage/state",
            "unit_of_measurement": "V",
            "device_class": "voltage",
            "state_class": "measurement",
            "icon": "mdi:flash-triangle"
        }
        
        # Current Sensor (A)
        sensors["current"] = {
            **base_config,
            "name": f"M-Bus {device_id} Current",
            "unique_id": f"mbus_{device_id}_current",
            "state_topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/current/state",
            "unit_of_measurement": "A",
            "device_class": "current",
            "state_class": "measurement",
            "icon": "mdi:current-ac"
        }
        
        # Status Sensor
        sensors["status"] = {
            **base_config,
            "name": f"M-Bus {device_id} Status",
            "unique_id": f"mbus_{device_id}_status",
            "state_topic": f"{self.topic_prefix}/sensor/mbus_{device_id}/status/state",
            "icon": "mdi:check-circle"
        }
        
        return sensors
    
    def publish_device_data(self, address: int, cli_response: Dict[str, Any]):
        """Publiziert Gerätedaten von CLI Response zu Home Assistant"""
        try:
            if not cli_response.get("success"):
                print(f"[HA-MQTT] Gerät {address}: CLI Response nicht erfolgreich")
                return
            
            device_id = cli_response.get("device_id", f"device_{address}")
            
            # Für CLI V2: Verwende identification falls verfügbar
            if "identification" in cli_response:
                device_id = cli_response["identification"] or f"device_{address}"
            elif "address" in cli_response:
                device_id = f"device_{cli_response['address']}"
            
            # CLI V2 verwendet 'records' statt 'data'
            records = cli_response.get("records", [])
            data = cli_response.get("data", {})  # Fallback für altes CLI
            
            if not records and not data:
                print(f"[HA-MQTT] Gerät {device_id}: Keine Daten in CLI Response")
                print(f"[HA-MQTT] Debug - CLI Response Keys: {list(cli_response.keys())}")
                return
            
            # CLI V2 Records verarbeiten
            if records:
                print(f"[HA-MQTT] Publiziere CLI V2 Daten für Gerät {device_id} ({len(records)} Records)")
                
                # Dynamische Discovery für gefundene Records
                self._send_dynamic_discovery_for_records(address, device_id, records, cli_response)
                
                for i, record in enumerate(records):
                    value = record.get("value")
                    unit = record.get("unit", "")
                    function_field = record.get("function_field", "")
                    
                    if value is not None:
                        # Topic-Name basierend auf Datentyp bestimmen
                        topic_name = self._map_record_to_topic(record, i)
                        if topic_name:
                            # Eindeutiges Topic mit Index für jeden Record
                            topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/{topic_name}_{i}/state"
                            self.mqtt_client.publish(topic, str(value), retain=True)
                            
                            print(f"[HA-MQTT] {device_id}.{topic_name}_{i}: {value} {unit}")
            
            # Altes CLI Format (falls verwendet)
            elif data:
                print(f"[HA-MQTT] Publiziere Legacy CLI Daten für Gerät {device_id} ({len(data)} Messwerte)")
                
                for data_key, data_value in data.items():
                    if isinstance(data_value, dict) and "value" in data_value:
                        value = data_value["value"]
                        unit = data_value.get("unit", "")
                        description = data_value.get("description", "")
                        
                        # Topic-Name basierend auf Datentyp bestimmen
                        topic_name = self._map_data_to_topic(data_key, unit, description)
                        if topic_name:
                            topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/{topic_name}/state"
                            self.mqtt_client.publish(topic, str(value), retain=True)
                            
                            print(f"[HA-MQTT] {device_id}.{topic_name}: {value} {unit}")
            
            # Status aktualisieren
            status_topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/status/state"
            status_data = {
                "status": "online",
                "last_read": cli_response.get("timestamp", datetime.now().isoformat()),
                "read_duration": cli_response.get("read_duration_seconds", 0),
                "data_count": len(records) if records else len(data)
            }
            self.mqtt_client.publish(status_topic, json.dumps(status_data), retain=True)
            
        except Exception as e:
            print(f"[HA-MQTT] Publish Fehler für Gerät {address}: {e}")
    
    def _map_data_to_topic(self, data_key: str, unit: str, description: str) -> Optional[str]:
        """Mappt CLI-Datentypen zu Home Assistant Topics"""
        key_lower = data_key.lower()
        unit_lower = unit.lower()
        desc_lower = description.lower()
        
        # Energy Mapping
        if "energy" in key_lower or "kwh" in unit_lower or "energy" in desc_lower:
            return "energy"
        
        # Power Mapping
        if "power" in key_lower or "w" == unit_lower or "power" in desc_lower:
            return "power"
        
        # Voltage Mapping
        if "voltage" in key_lower or "v" == unit_lower or "voltage" in desc_lower:
            return "voltage"
        
        # Current Mapping
        if "current" in key_lower or "a" == unit_lower or "current" in desc_lower:
            return "current"
        
        # Fallback: Versuche aus data_key zu extrahieren
        if "energy" in key_lower:
            return "energy"
        elif "power" in key_lower:
            return "power"
        elif "voltage" in key_lower:
            return "voltage"
        elif "current" in key_lower:
            return "current"
        
        # Unbekannter Typ
        print(f"[HA-MQTT] Unbekannter Datentyp: {data_key} ({unit}) - überspringe")
        return None
    
    def _map_record_to_topic(self, record: Dict[str, Any], index: int) -> Optional[str]:
        """Mappt CLI V2 Records zu Home Assistant Topics"""
        value = record.get("value")
        unit = record.get("unit", "").lower()
        function_field = record.get("function_field", "").lower()
        
        # Unit-basiertes Mapping (prioritär)
        if "kwh" in unit or "wh" in unit:
            return "energy"
        elif "w" == unit or "kw" in unit:
            return "power"  
        elif "v" == unit or "volt" in unit:
            return "voltage"
        elif "a" == unit or "amp" in unit:
            return "current"
        
        # Function-Field basiertes Mapping
        if "energy" in function_field:
            return "energy"
        elif "power" in function_field:
            return "power"
        elif "voltage" in function_field:
            return "voltage"
        elif "current" in function_field:
            return "current"
        
        # Value-basiertes Mapping (Heuristik)
        if isinstance(value, (int, float)):
            if value > 1000:  # Wahrscheinlich Energie in Wh
                return "energy"
            elif value > 100:  # Wahrscheinlich Spannung in V
                return "voltage"
            elif value < 50 and value > 0:  # Wahrscheinlich Strom in A oder Leistung in W
                if value < 10:
                    return "current"
                else:
                    return "power"
        
        # Fallback: Index-basiert
        topic_map = {0: "energy", 1: "power", 2: "voltage", 3: "current"}
        topic = topic_map.get(index, f"sensor_{index}")
        
        print(f"[HA-MQTT] Record {index} unbekannt - verwende Fallback '{topic}' (Unit: {unit}, Value: {value})")
        return topic
    
    def _send_dynamic_discovery_for_records(self, address: int, device_id: str, records: list, cli_response: dict):
        """Sendet dynamische Home Assistant Discovery basierend auf CLI V2 Records"""
        try:
            if device_id in self.discovery_sent:
                return  # Discovery bereits gesendet
            
            print(f"[HA-MQTT] Sende dynamische Discovery für {device_id} mit {len(records)} Records")
            
            # Device Information aus CLI Response
            manufacturer = cli_response.get("manufacturer", "M-Bus")
            identification = cli_response.get("identification", device_id)
            
            # Device-Konfiguration
            device_config = {
                "identifiers": [f"mbus_{device_id}"],
                "name": f"M-Bus {identification}",
                "manufacturer": manufacturer,
                "model": "M-Bus Meter",
                "sw_version": "CLI-Gateway-v2.0"
            }
            
            # Basis-Konfiguration für alle Sensoren
            base_config = {
                "device": device_config,
                "availability": [
                    {
                        "topic": f"{self.gateway_topic}/state",
                        "value_template": "{{ value_json.state }}"
                    }
                ],
                "availability_mode": "any"
            }
            
            # Für jeden Record eine Discovery-Nachricht erstellen
            for i, record in enumerate(records):
                value = record.get("value")
                unit = record.get("unit", "")
                function_field = record.get("function_field", "")
                
                if value is not None:
                    topic_name = self._map_record_to_topic(record, i)
                    if topic_name:  # Nur wenn topic_name nicht None ist
                        sensor_name = self._get_sensor_name_from_topic(topic_name, unit, function_field)
                        device_class = self._get_device_class_from_topic(topic_name)
                        state_class = self._get_state_class_from_topic(topic_name)
                        icon = self._get_icon_from_topic(topic_name)
                        
                        # Sensor-Konfiguration mit eindeutiger ID pro Record
                        unique_sensor_id = f"mbus_{device_id}_{topic_name}_{i}"  # Index hinzufügen für Eindeutigkeit
                        state_topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/{topic_name}_{i}/state"
                        
                        sensor_config = {
                            **base_config,
                            "name": f"M-Bus {identification} {sensor_name} {i}",  # Index auch im Namen für Klarheit
                            "unique_id": unique_sensor_id,
                            "state_topic": state_topic,
                            "unit_of_measurement": unit,
                            "icon": icon
                        }
                        
                        # Optional: Device Class und State Class hinzufügen
                        if device_class:
                            sensor_config["device_class"] = device_class
                        if state_class:
                            sensor_config["state_class"] = state_class
                        
                        # Discovery-Nachricht senden
                        discovery_topic = f"{self.topic_prefix}/sensor/{unique_sensor_id}/config"
                        self.mqtt_client.publish(
                            discovery_topic,
                            json.dumps(sensor_config),
                            retain=True
                        )
                        
                        print(f"[HA-MQTT] Discovery gesendet: {sensor_name} ({unit})")
            
            # Gerät als verfügbar markieren
            availability_topic = f"{self.topic_prefix}/sensor/mbus_{device_id}/availability"
            self.mqtt_client.publish(availability_topic, "online", retain=True)
            
            # Discovery-Status speichern
            self.discovery_sent.add(device_id)
            
        except Exception as e:
            print(f"[HA-MQTT] Dynamische Discovery Fehler für {device_id}: {e}")
    
    def _get_sensor_name_from_topic(self, topic_name: str, unit: str, function_field: str) -> str:
        """Mappt Topic-Namen zu benutzerfreundlichen Sensor-Namen"""
        name_map = {
            "energy": "Energy",
            "power": "Power", 
            "voltage": "Voltage",
            "current": "Current"
        }
        return name_map.get(topic_name, function_field or topic_name.title())
    
    def _get_device_class_from_topic(self, topic_name: str) -> Optional[str]:
        """Mappt Topic-Namen zu Home Assistant Device Classes"""
        class_map = {
            "energy": "energy",
            "power": "power",
            "voltage": "voltage", 
            "current": "current"
        }
        return class_map.get(topic_name)
    
    def _get_state_class_from_topic(self, topic_name: str) -> Optional[str]:
        """Mappt Topic-Namen zu Home Assistant State Classes"""
        if topic_name == "energy":
            return "total_increasing"
        elif topic_name in ["power", "voltage", "current"]:
            return "measurement"
        return None
    
    def _get_icon_from_topic(self, topic_name: str) -> str:
        """Mappt Topic-Namen zu Home Assistant Icons"""
        icon_map = {
            "energy": "mdi:flash",
            "power": "mdi:lightning-bolt",
            "voltage": "mdi:flash-triangle",
            "current": "mdi:current-ac"
        }
        return icon_map.get(topic_name, "mdi:gauge")
    
    def publish_gateway_status(self, status: str):
        """Publiziert Gateway-Status"""
        try:
            gateway_data = {
                "state": status,
                "timestamp": datetime.now().isoformat(),
                "version": "CLI-Gateway-v1.0"
            }
            
            # Bridge State
            bridge_topic = f"{self.gateway_topic}/state"
            self.mqtt_client.publish(bridge_topic, json.dumps(gateway_data), retain=True)
            
            # Einfacher Status
            simple_topic = f"{self.topic_prefix}/bridge/state"
            self.mqtt_client.publish(simple_topic, status, retain=True)
            
            print(f"[HA-MQTT] Gateway Status: {status}")
            
        except Exception as e:
            print(f"[HA-MQTT] Gateway Status Fehler: {e}")
    
    def update_gateway_status(self, status_data: Dict[str, Any]):
        """Aktualisiert Gateway-Status mit zusätzlichen Daten"""
        try:
            gateway_data = {
                "state": "online",
                "timestamp": datetime.now().isoformat(),
                "version": "CLI-Gateway-v1.0",
                **status_data  # Zusätzliche Daten hinzufügen
            }
            
            topic = f"{self.gateway_topic}/state"
            self.mqtt_client.publish(topic, json.dumps(gateway_data), retain=True)
            
        except Exception as e:
            print(f"[HA-MQTT] Gateway Status Update Fehler: {e}")
    
    def send_gateway_discovery(self):
        """Sendet Discovery für das Gateway selbst"""
        try:
            config = {
                "name": "M-Bus Gateway",
                "unique_id": "mbus_gateway_status",
                "state_topic": f"{self.gateway_topic}/state",
                "value_template": "{{ value_json.state }}",
                "json_attributes_topic": f"{self.gateway_topic}/state",
                "icon": "mdi:home-assistant",
                "device": {
                    "identifiers": ["mbus_gateway"],
                    "name": "M-Bus MQTT Gateway",
                    "manufacturer": "Custom",
                    "model": "CLI-Gateway",
                    "sw_version": "v1.0"
                }
            }
            
            discovery_topic = f"{self.gateway_topic}/config"
            self.mqtt_client.publish(discovery_topic, json.dumps(config), retain=True)
            
            print("[HA-MQTT] Gateway Discovery gesendet")
            
        except Exception as e:
            print(f"[HA-MQTT] Gateway Discovery Fehler: {e}")