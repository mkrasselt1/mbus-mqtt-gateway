#!/usr/bin/env python3
"""
Test-Script für die Home Assistant MQTT Integration
Testet die MQTT Discovery und State Publishing Funktionalität
"""

from app.device_manager import device_manager
from app.ha_mqtt import HomeAssistantMQTT
from app.config import Config
import time

def test_ha_mqtt_integration():
    """Testet die Home Assistant MQTT Integration"""
    print("=" * 70)
    print("HOME ASSISTANT MQTT INTEGRATION TEST")
    print("=" * 70)
    
    # Konfiguration laden
    config = Config()
    
    # MQTT Client initialisieren
    print("\n1. MQTT Client initialisieren...")
    mqtt_client = HomeAssistantMQTT(
        broker=config.data.get("mqtt_broker", "localhost"),
        port=config.data.get("mqtt_port", 1883),
        username=config.data.get("mqtt_username", ""),
        password=config.data.get("mqtt_password", ""),
        topic_prefix=config.data.get("mqtt_topic", "homeassistant")
    )
    
    # DeviceManager mit MQTT verknüpfen
    device_manager.set_mqtt_client(mqtt_client)
    
    # MQTT Verbindung herstellen
    print("\n2. MQTT Verbindung herstellen...")
    if mqtt_client.connect():
        print("✅ MQTT erfolgreich verbunden")
    else:
        print("❌ MQTT Verbindung fehlgeschlagen")
        return
    
    # Warten auf Verbindung
    time.sleep(2)
    
    # Test-Daten hinzufügen
    print("\n3. Test-Geräte hinzufügen...")
    
    # Erstes M-Bus Gerät simulieren
    test_data1 = {
        "manufacturer": "Kamstrup",
        "medium": "Heat",
        "identification": "12345678",
        "records": [
            {"name": "Energie", "value": 1234.5678, "unit": "kWh"},
            {"name": "Leistung", "value": 45.2, "unit": "kW"},
            {"name": "Vorlauftemperatur", "value": 65.3, "unit": "°C"},
            {"name": "Rücklauftemperatur", "value": 42.1, "unit": "°C"},
            {"name": "Volumenstrom", "value": 0.85, "unit": "m³/h"}
        ]
    }
    
    device_manager.update_mbus_device_data(5, test_data1)
    print("✅ M-Bus Gerät 5 (Kamstrup Heat Meter) hinzugefügt")
    
    # Zweites M-Bus Gerät simulieren  
    test_data2 = {
        "manufacturer": "Landis+Gyr",
        "medium": "Electricity",
        "identification": "87654321",
        "records": [
            {"name": "Wirkenergie", "value": 5678.91, "unit": "kWh"},
            {"name": "Blindenergie", "value": 234.56, "unit": "kvarh"},
            {"name": "Spannung L1", "value": 229.8, "unit": "V"},
            {"name": "Strom L1", "value": 12.5, "unit": "A"},
            {"name": "Leistungsfaktor", "value": 0.95, "unit": "cos φ"}
        ]
    }
    
    device_manager.update_mbus_device_data(10, test_data2)
    print("✅ M-Bus Gerät 10 (Landis+Gyr Electricity Meter) hinzugefügt")
    
    # Gateway-Updates simulieren
    print("\n4. Gateway-Updates simulieren...")
    device_manager.update_gateway_uptime(3600)  # 1 Stunde
    device_manager.update_gateway_ip()
    print("✅ Gateway-Daten aktualisiert")
    
    # Warten auf Discovery und State Publishing
    print("\n5. Warte auf Discovery und State Publishing...")
    time.sleep(5)
    
    # Status ausgeben
    print("\n6. Aktueller Gerätestatus:")
    device_manager.print_status()
    
    # Geräte-Änderungen simulieren
    print("\n7. Geräte-Änderungen simulieren...")
    
    # Werte für erstes Gerät ändern
    updated_data1 = {
        "manufacturer": "Kamstrup",
        "medium": "Heat", 
        "identification": "12345678",
        "records": [
            {"name": "Energie", "value": 1235.1234, "unit": "kWh"},  # Neuer Wert
            {"name": "Leistung", "value": 48.7, "unit": "kW"},       # Neuer Wert
            {"name": "Vorlauftemperatur", "value": 67.1, "unit": "°C"},
            {"name": "Rücklauftemperatur", "value": 43.2, "unit": "°C"},
            {"name": "Volumenstrom", "value": 0.91, "unit": "m³/h"}
        ]
    }
    
    device_manager.update_mbus_device_data(5, updated_data1)
    print("✅ M-Bus Gerät 5 Werte aktualisiert")
    
    # Ein Gerät offline setzen
    device_manager.set_device_offline("mbus_meter_10")
    print("✅ M-Bus Gerät 10 offline gesetzt")
    
    # Warten auf MQTT Updates
    time.sleep(3)
    
    # Erneute Discovery erzwingen (simuliert Reconnect)
    print("\n8. Erneute Discovery erzwingen (simuliert Reconnect)...")
    mqtt_client.force_rediscovery()
    
    # Warten
    time.sleep(5)
    
    # Finale Status-Ausgabe
    print("\n9. Finale Status-Ausgabe:")
    device_manager.print_status()
    
    print("\n10. MQTT Client Informationen:")
    print(f"   - Verbunden: {'✅' if mqtt_client.connected else '❌'}")
    print(f"   - Home Assistant Online: {'✅' if mqtt_client.ha_online else '❌'}")
    print(f"   - Discovery Nachrichten gesendet: {len(mqtt_client.discovery_sent)}")
    print(f"   - Broker: {mqtt_client.broker}:{mqtt_client.port}")
    
    # Cleanup
    print("\n11. Cleanup...")
    mqtt_client.disconnect()
    
    print("\n" + "=" * 70)
    print("TEST ABGESCHLOSSEN")
    print("=" * 70)
    print("\nHinweise:")
    print("- Überprüfen Sie Home Assistant für neue Auto-Discovery Geräte")
    print("- Topics sind unter 'homeassistant/sensor/' und 'homeassistant/binary_sensor/'")
    print("- State Topics sind unter 'homeassistant/device/<device_id>/state'")

if __name__ == "__main__":
    test_ha_mqtt_integration()
