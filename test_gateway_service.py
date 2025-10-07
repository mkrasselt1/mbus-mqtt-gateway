#!/usr/bin/env python3
"""
Test Script für M-Bus Gateway Service
Testet den neuen CLI-basierten Service mit Mock-Daten
"""

import json
import time
import threading
import sys
import os
from datetime import datetime

# Mock MQTT Client für Testing
class MockMQTTClient:
    """Mock MQTT Client für Service Testing"""
    
    def __init__(self):
        self.published_messages = []
        self.connected = False
        
    def connect(self, host, port, keepalive):
        print(f"[MOCK-MQTT] Verbinde zu {host}:{port}")
        self.connected = True
        return 0
    
    def publish(self, topic, payload, retain=False):
        message = {
            "topic": topic,
            "payload": payload,
            "retain": retain,
            "timestamp": datetime.now().isoformat()
        }
        self.published_messages.append(message)
        print(f"[MOCK-MQTT] PUB: {topic} = {payload}")
        return True
    
    def loop_start(self):
        pass
    
    def loop_stop(self):
        pass
    
    def disconnect(self):
        self.connected = False
        print("[MOCK-MQTT] Verbindung getrennt")
    
    def username_pw_set(self, username, password):
        pass

# Mock Service für Testing
class MockMBusGatewayService:
    """Mock-Version des Gateway Service für Testing"""
    
    def __init__(self):
        self.mqtt_client = MockMQTTClient()
        self.running = True
        self.devices = {}
        
        # Mock Config
        self.config_data = {
            "mbus_port": "/dev/mock",
            "mbus_baudrate": 9600,
            "mqtt_broker": "localhost",
            "mqtt_port": 1883,
            "mqtt_topic": "homeassistant"
        }
        
        # CLI Mock Response
        self.mock_scan_response = {
            "success": True,
            "devices": [
                {
                    "address": 0,
                    "device_id": "00047028B5151002",
                    "manufacturer": "ISKRA",
                    "medium": "electricity",
                    "response_length": 91,
                    "found_at": datetime.now().isoformat()
                },
                {
                    "address": 1,
                    "device_id": "12345678901234567",
                    "manufacturer": "EMH", 
                    "medium": "electricity",
                    "response_length": 157,
                    "found_at": datetime.now().isoformat()
                }
            ],
            "device_count": 2,
            "scan_duration_seconds": 1.5,
            "timestamp": datetime.now().isoformat()
        }
        
        self.mock_read_responses = {
            0: {
                "success": True,
                "address": 0,
                "device_id": "00047028B5151002",
                "data": {
                    "energy_active_kwh": {
                        "value": 1642.072,
                        "unit": "kWh",
                        "description": "Active Energy",
                        "record_index": 1
                    },
                    "power_active_w": {
                        "value": 679.6,
                        "unit": "W",
                        "description": "Active Power",
                        "record_index": 2
                    },
                    "voltage_v": {
                        "value": 221.6,
                        "unit": "V",
                        "description": "Voltage",
                        "record_index": 3
                    },
                    "current_a": {
                        "value": 2.95,
                        "unit": "A",
                        "description": "Current",
                        "record_index": 4
                    }
                },
                "read_duration_seconds": 0.201,
                "timestamp": datetime.now().isoformat()
            },
            1: {
                "success": True,
                "address": 1,
                "device_id": "12345678901234567",
                "data": {
                    "energy_active_kwh": {
                        "value": 3611.123,
                        "unit": "kWh",
                        "description": "Active Energy",
                        "record_index": 1
                    },
                    "power_active_w": {
                        "value": 1384.7,
                        "unit": "W",
                        "description": "Active Power",
                        "record_index": 2
                    }
                },
                "read_duration_seconds": 0.2,
                "timestamp": datetime.now().isoformat()
            }
        }
    
    def test_discovery(self):
        """Testet Device Discovery"""
        print("\n=== DISCOVERY TEST ===")
        
        # Mock Discovery ausführen
        response = self.mock_scan_response
        
        print(f"Discovery Response: {json.dumps(response, indent=2)}")
        
        # Devices verarbeiten
        for device_info in response["devices"]:
            address = device_info["address"]
            self.devices[address] = device_info
            print(f"Gerät registriert: Adresse {address} = {device_info['device_id']}")
        
        print(f"Discovery abgeschlossen: {len(self.devices)} Geräte")
    
    def test_reading(self):
        """Testet Datenlesung"""
        print("\n=== READING TEST ===")
        
        if not self.devices:
            print("Keine Geräte für Reading Test")
            return
        
        for address in self.devices.keys():
            print(f"\n--- Lese Daten von Adresse {address} ---")
            
            response = self.mock_read_responses.get(address)
            if response:
                print(f"Read Response: {json.dumps(response, indent=2)}")
                
                # Datenverarbeitung simulieren
                data = response.get("data", {})
                print(f"Verarbeite {len(data)} Messwerte:")
                
                for key, value in data.items():
                    if isinstance(value, dict):
                        val = value.get("value", "N/A")
                        unit = value.get("unit", "")
                        print(f"  {key}: {val} {unit}")
            else:
                print(f"Keine Mock-Daten für Adresse {address}")
    
    def test_mqtt_publishing(self):
        """Testet MQTT Publishing mit HA-MQTT Interface"""
        print("\n=== MQTT PUBLISHING TEST ===")
        
        # HA-MQTT Interface importieren
        try:
            from app.ha_mqtt_cli import HomeAssistantMQTT
            
            ha_mqtt = HomeAssistantMQTT(self.mqtt_client, "homeassistant")
            
            # Gateway Discovery
            print("--- Gateway Discovery ---")
            ha_mqtt.send_gateway_discovery()
            
            # Device Discovery
            print("\n--- Device Discovery ---")
            for device_info in self.mock_scan_response["devices"]:
                ha_mqtt.send_device_discovery(device_info)
            
            # Data Publishing
            print("\n--- Data Publishing ---")
            for address, read_response in self.mock_read_responses.items():
                ha_mqtt.publish_device_data(address, read_response)
            
            # Gateway Status
            print("\n--- Gateway Status ---")
            ha_mqtt.publish_gateway_status("online")
            ha_mqtt.update_gateway_status({
                "device_count": len(self.devices),
                "last_discovery": datetime.now().isoformat()
            })
            
            # Zeige publizierte Nachrichten
            print(f"\n--- Publizierte MQTT Nachrichten ({len(self.mqtt_client.published_messages)}) ---")
            for i, msg in enumerate(self.mqtt_client.published_messages):
                print(f"{i+1:2d}. {msg['topic']}")
                if len(str(msg['payload'])) < 100:
                    print(f"     Payload: {msg['payload']}")
                else:
                    print(f"     Payload: {str(msg['payload'])[:100]}...")
                print()
            
        except Exception as e:
            print(f"MQTT Test Fehler: {e}")
    
    def run_full_test(self):
        """Führt vollständigen Service Test aus"""
        print("=== M-BUS GATEWAY SERVICE TEST ===")
        print(f"Start: {datetime.now().isoformat()}")
        print()
        
        try:
            # 1. Discovery Test
            self.test_discovery()
            
            # 2. Reading Test  
            self.test_reading()
            
            # 3. MQTT Publishing Test
            self.test_mqtt_publishing()
            
            print("\n=== TEST ERFOLGREICH ABGESCHLOSSEN ===")
            
        except Exception as e:
            print(f"\n=== TEST FEHLER: {e} ===")


def main():
    """Hauptfunktion für Service Testing"""
    if len(sys.argv) > 1 and sys.argv[1] == "mock":
        # Mock Service Test
        service = MockMBusGatewayService()
        service.run_full_test()
    else:
        print("M-Bus Gateway Service Test")
        print()
        print("Usage:")
        print("  python test_gateway_service.py mock    # Mock Service Test")
        print()
        print("Für echten Service Test:")
        print("  python mbus_gateway_service.py")


if __name__ == "__main__":
    main()