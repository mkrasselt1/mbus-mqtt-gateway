#!/usr/bin/env python3
"""
Test-Script für den DeviceManager
Zeigt die Funktionalität der zentralen Dateninstanz
"""

from app.device_manager import device_manager
import time

def test_device_manager():
    """Testet die DeviceManager Funktionalität"""
    print("=" * 60)
    print("DEVICE MANAGER TEST")
    print("=" * 60)
    
    # 1. Gateway ist bereits initialisiert
    print("\n1. Gateway Status:")
    gateway = device_manager.get_device(device_manager.gateway_id)
    if gateway:
        print(f"   Gateway ID: {gateway.device_id}")
        print(f"   Name: {gateway.name}")
        print(f"   IP: {gateway.get_attribute_value('ip_address')}")
    
    # 2. M-Bus Gerät simulieren
    print("\n2. Simuliere M-Bus Gerät...")
    test_device_id = "mbus_meter_5"
    
    # Simulierte M-Bus Daten
    test_data = {
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
    
    device_manager.update_mbus_device_data(5, test_data)
    
    # 3. Gateway Updates simulieren
    print("\n3. Simuliere Gateway-Updates...")
    for i in range(3):
        device_manager.update_gateway_uptime(i * 60)  # 0, 60, 120 Sekunden
        device_manager.update_gateway_ip()
        time.sleep(1)
    
    # 4. Zweites M-Bus Gerät hinzufügen
    print("\n4. Füge zweites M-Bus Gerät hinzu...")
    test_data2 = {
        "manufacturer": "Landis+Gyr",
        "medium": "Electricity", 
        "identification": "87654321",
        "records": [
            {"name": "Wirkenergie", "value": 5678.91, "unit": "kWh"},
            {"name": "Blindenergie", "value": 234.56, "unit": "kvarh"},
            {"name": "Spannung L1", "value": 229.8, "unit": "V"},
            {"name": "Strom L1", "value": 12.5, "unit": "A"}
        ]
    }
    
    device_manager.update_mbus_device_data(10, test_data2)
    
    # 5. Ein Gerät offline setzen
    print("\n5. Setze Gerät offline...")
    device_manager.set_device_offline("mbus_meter_10")
    
    # 6. Finale Status-Ausgabe
    print("\n6. Finale Status-Übersicht:")
    device_manager.print_status()
    
    # 7. Geräte nach Typ abfragen
    print("\n7. Geräte nach Typ:")
    gateways = device_manager.get_devices_by_type("gateway")
    mbus_devices = device_manager.get_devices_by_type("mbus_meter")
    
    print(f"   Gateways: {len(gateways)}")
    print(f"   M-Bus Geräte: {len(mbus_devices)}")
    
    # 8. Attribut-Zugriff testen
    print("\n8. Direkter Attribut-Zugriff:")
    test_device = device_manager.get_device("mbus_meter_5")
    if test_device:
        energie = test_device.get_attribute_value("Energie")
        print(f"   Energie von Gerät 5: {energie}")
    
    print("\n" + "=" * 60)
    print("TEST ABGESCHLOSSEN")
    print("=" * 60)

if __name__ == "__main__":
    test_device_manager()
