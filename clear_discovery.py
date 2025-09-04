#!/usr/bin/env python3
"""
Discovery Reset Tool
Löscht alle alten Discovery Topics und sendet neue
"""

import paho.mqtt.client as mqtt
import time
import json

def clear_discovery_topics():
    """Löscht alle M-Bus Discovery Topics"""
    
    # MQTT Client erstellen
    client = mqtt.Client()
    
    try:
        # Zur MQTT-Broker verbinden (falls verfügbar)
        print("Versuche MQTT-Verbindung...")
        client.connect("localhost", 1883, 60)
        client.loop_start()
        
        # Kurz warten
        time.sleep(1)
        
        # Bekannte Discovery Patterns löschen
        discovery_patterns = [
            # M-Bus Meter Sensoren
            "homeassistant/sensor/mbus_meter_1_energie/config",
            "homeassistant/sensor/mbus_meter_1_energie_bezug/config", 
            "homeassistant/sensor/mbus_meter_1_energie_einspeisung/config",
            "homeassistant/sensor/mbus_meter_1_leistung/config",
            "homeassistant/sensor/mbus_meter_1_spannung_l1/config",
            "homeassistant/sensor/mbus_meter_1_spannung_l2/config", 
            "homeassistant/sensor/mbus_meter_1_spannung_l3/config",
            "homeassistant/sensor/mbus_meter_1_strom_l1/config",
            "homeassistant/sensor/mbus_meter_1_strom_l2/config",
            "homeassistant/sensor/mbus_meter_1_frequenz_in_millihz/config",
            "homeassistant/sensor/mbus_meter_1_messwert_0/config",
            "homeassistant/sensor/mbus_meter_1_wirkleistung/config",
            "homeassistant/sensor/mbus_meter_1_zählerstand_7/config",
            "homeassistant/binary_sensor/mbus_meter_1_status/config",
            
            # Gateway Sensoren  
            "homeassistant/sensor/gateway_*/config",
            "homeassistant/binary_sensor/gateway_*/config"
        ]
        
        print(f"Lösche {len(discovery_patterns)} Discovery Topics...")
        
        for topic in discovery_patterns:
            # Leere Payload mit retain=True löscht das Topic permanent
            result = client.publish(topic, "", retain=True)
            if result.rc == 0:
                print(f"✓ Gelöscht: {topic}")
            else:
                print(f"✗ Fehler bei: {topic}")
            time.sleep(0.1)
        
        print("\nAlle Discovery Topics gelöscht!")
        print("Home Assistant wird automatisch neue Discovery empfangen.")
        
        client.loop_stop()
        client.disconnect()
        
    except Exception as e:
        print(f"MQTT-Fehler: {e}")
        print("Lösung: Home Assistant manuell neu starten oder MQTT-Broker installieren")

if __name__ == "__main__":
    clear_discovery_topics()
