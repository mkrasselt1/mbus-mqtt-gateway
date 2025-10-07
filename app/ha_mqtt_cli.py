"""
Home Assistant MQTT Interface - CLI-kompatible Version
Korrekte Topic-Struktur für Home Assistant Discovery
"""

import json
import time
from typing import Dict, Any, Optional
from datetime import datetime


class HomeAssistantMQTT:
    """Home Assistant MQTT Interface für CLI-basierte M-Bus Daten"""
    
    def __init__(self, mqtt_client, state_topic_prefix="mbus", discovery_topic_prefix="homeassistant"):
        self.mqtt_client = mqtt_client
        self.state_topic_prefix = state_topic_prefix  # Für Messwerte (z.B. "mbus")
        self.discovery_topic_prefix = discovery_topic_prefix  # Für Discovery (immer "homeassistant")
        self.discovery_sent = set()  # Bereits gesendete Discoveries
        self.gateway_topic = f"{discovery_topic_prefix}/sensor/mbus_gateway"
        
        print(f"[HA-MQTT] Home Assistant Interface initialisiert")
        print(f"[HA-MQTT] State Topics: {state_topic_prefix}/*")
        print(f"[HA-MQTT] Discovery Topics: {discovery_topic_prefix}/*")
    
    def send_device_discovery(self, device_info: Dict[str, Any]):
        """Sendet Home Assistant Auto-Discovery für ein neues Gerät"""
        try:
            address = device_info["address"]
            device_id = device_info.get("device_id", f"device_{address}")
            manufacturer = device_info.get("manufacturer", "M-Bus")
            
            print(f"[HA-MQTT] Sende Discovery für Gerät {device_id} (Adresse {address})")
            
            # Discovery bereits gesendet?
            if device_id in self.discovery_sent:
                print(f"[HA-MQTT] Discovery für {device_id} bereits gesendet")
                return
            
            # Discovery wird durch CLI V2 Records dynamisch erstellt
            print(f"[HA-MQTT] Discovery für {device_id} wird bei erstem Datenlesen erstellt")
            
        except Exception as e:
            print(f"[HA-MQTT] Discovery Fehler für Gerät {device_info}: {e}")
    
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
            
            # CLI V2 verwendet 'records'
            records = cli_response.get("records", [])
            
            if not records:
                print(f"[HA-MQTT] Gerät {device_id}: Keine Records in CLI Response")
                print(f"[HA-MQTT] Debug - CLI Response Keys: {list(cli_response.keys())}")
                return
            
            print(f"[HA-MQTT] Publiziere CLI V2 Daten für Gerät {device_id} ({len(records)} Records)")
            
            # Dynamische Discovery für gefundene Records
            self._send_dynamic_discovery_for_records(address, device_id, records, cli_response)
            
            # Publiziere alle Record-Werte
            for i, record in enumerate(records):
                value = record.get("value")
                unit = record.get("unit", "")
                function_field = record.get("function_field", "")
                
                if value is not None:
                    # Topic-Name basierend auf Datentyp bestimmen
                    topic_name = self._map_record_to_topic(record, i)
                    if topic_name:
                        # State Topic mit konfiguriertem Prefix
                        state_topic = f"{self.state_topic_prefix}/sensor/mbus_{device_id}/{topic_name}_{i}/state"
                        self.mqtt_client.publish(state_topic, str(value), retain=True)
                        
                        print(f"[HA-MQTT] {device_id}.{topic_name}_{i}: {value} {unit} -> {state_topic}")
            
            # Status aktualisieren
            status_topic = f"{self.state_topic_prefix}/sensor/mbus_{device_id}/status/state"
            status_data = {
                "status": "online",
                "last_read": cli_response.get("timestamp", datetime.now().isoformat()),
                "read_duration": cli_response.get("read_duration_seconds", 0),
                "data_count": len(records)
            }
            self.mqtt_client.publish(status_topic, json.dumps(status_data), retain=True)
            
        except Exception as e:
            print(f"[HA-MQTT] Publish Fehler für Gerät {address}: {e}")
    
    def _map_record_to_topic(self, record: Dict[str, Any], index: int) -> Optional[str]:
        """Mappt CLI V2 Records zu Home Assistant Topics mit verbesserter Erkennung"""
        value = record.get("value")
        unit = record.get("unit", "").lower().strip()
        function_field = record.get("function_field", "").lower()
        
        print(f"[HA-MQTT] Record {index} Mapping: Unit='{unit}', Function='{function_field}', Value={value}")
        
        # Präzise Unit-basierte Erkennung (höchste Priorität)
        if unit in ["kwh", "wh", "mwh"]:  # Energie-Einheiten
            return "energy"
        elif unit in ["w", "kw", "mw"]:  # Leistungs-Einheiten  
            return "power"
        elif unit in ["v", "volt", "kv"]:  # Spannungs-Einheiten
            return "voltage"
        elif unit in ["a", "ma", "ka", "amp", "ampere"]:  # Strom-Einheiten
            return "current"
        
        # Function-Field basierte Erkennung (zweite Priorität)
        if "energy" in function_field or "work" in function_field:
            return "energy"
        elif "power" in function_field or "leistung" in function_field:
            return "power"
        elif "voltage" in function_field or "spannung" in function_field:
            return "voltage"
        elif "current" in function_field or "strom" in function_field:
            return "current"
        
        # Erweiterte Value-basierte Heuristik mit besserer Logik
        if isinstance(value, (int, float)) and value > 0:
            # Energie: Normalerweise große Werte (> 1000) 
            if value > 1000:
                print(f"[HA-MQTT] Record {index}: Hoher Wert ({value}) -> vermutlich Energy")
                return "energy"
            
            # Spannung: Typisch 230V für EU, 120V für US (100-400V Range)  
            elif 100 <= value <= 400:
                print(f"[HA-MQTT] Record {index}: Spannungsbereich ({value}V) -> Voltage")
                return "voltage"
            
            # Strom: Normalerweise niedrige Werte (0.1-50A für Haushalte)
            elif 0.1 <= value <= 50:
                print(f"[HA-MQTT] Record {index}: Strombereich ({value}A) -> Current")
                return "current"
            
            # Leistung: Mittlere Werte (1-10000W für Haushalte)
            elif 1 <= value <= 10000:
                print(f"[HA-MQTT] Record {index}: Leistungsbereich ({value}W) -> Power")
                return "power"
        
        # Intelligenter Fallback basierend auf typischen M-Bus Reihenfolgen
        # Landis+Gyr und ähnliche Zähler: Energy, Power, Voltage, Current
        fallback_map = {
            0: "energy",    # Erste Messung: Meist Energiezählerstand
            1: "power",     # Zweite Messung: Aktuelle Leistung  
            2: "voltage",   # Dritte Messung: Spannung
            3: "current"    # Vierte Messung: Strom
        }
        
        fallback_topic = fallback_map.get(index, f"sensor_{index}")
        print(f"[HA-MQTT] Record {index} unbekannt - verwende intelligenten Fallback '{fallback_topic}' (Unit: '{unit}', Function: '{function_field}', Value: {value})")
        return fallback_topic
    
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
                        state_topic = f"{self.state_topic_prefix}/sensor/mbus_{device_id}/{topic_name}_{i}/state"
                        
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
                        
                        # Discovery-Nachricht senden (mit discovery_topic_prefix = "homeassistant")
                        discovery_topic = f"{self.discovery_topic_prefix}/sensor/{unique_sensor_id}/config"
                        self.mqtt_client.publish(
                            discovery_topic,
                            json.dumps(sensor_config),
                            retain=True
                        )
                        
                        print(f"[HA-MQTT] Discovery gesendet: {sensor_name} ({unit}) -> {discovery_topic}")
            
            # Gerät als verfügbar markieren
            availability_topic = f"{self.state_topic_prefix}/sensor/mbus_{device_id}/availability"
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
                "version": "CLI-Gateway-v2.0"
            }
            
            # Bridge State
            bridge_topic = f"{self.gateway_topic}/state"
            self.mqtt_client.publish(bridge_topic, json.dumps(gateway_data), retain=True)
            
            # Einfacher Status
            simple_topic = f"{self.state_topic_prefix}/bridge/state"
            self.mqtt_client.publish(simple_topic, status, retain=True)
            
            print(f"[HA-MQTT] Gateway Status: {status}")
            
        except Exception as e:
            print(f"[HA-MQTT] Gateway Status Fehler: {e}")
    
    def update_gateway_status(self, status_data: Dict[str, Any]):
        """Aktualisiert Gateway-Status mit zusätzlichen Daten"""
        try:
            updated_data = {
                "state": "online",
                "timestamp": datetime.now().isoformat(),
                "version": "CLI-Gateway-v2.0",
                **status_data
            }
            
            bridge_topic = f"{self.gateway_topic}/state"
            self.mqtt_client.publish(bridge_topic, json.dumps(updated_data), retain=True)
            
            print(f"[HA-MQTT] Gateway Status aktualisiert: {status_data}")
            
        except Exception as e:
            print(f"[HA-MQTT] Gateway Status Update Fehler: {e}")