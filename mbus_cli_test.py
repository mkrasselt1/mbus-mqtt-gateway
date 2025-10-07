#!/usr/bin/env python3
"""
M-Bus CLI Test Script - Lokal testbar ohne Hardware
Simuliert M-Bus Geräte-Kommunikation für Development
"""

import json
import time
import random
from datetime import datetime

class MockMBusDevice:
    """Simuliert ein M-Bus Gerät für Testing"""
    
    def __init__(self, address, device_id, manufacturer="MOCK", medium="electricity"):
        self.address = address
        self.device_id = device_id
        self.manufacturer = manufacturer
        self.medium = medium
        self.version = "1.0"
        self.access_number = random.randint(1000, 9999)
        
        # Simulierte Messwerte
        self.base_energy = random.uniform(1000, 5000)  # kWh
        self.base_power = random.uniform(500, 2000)    # W
        
    def get_simulated_data(self):
        """Generiert simulierte Messdaten"""
        # Simuliere leichte Schwankungen
        energy_offset = random.uniform(-10, 50)  # Energie steigt meist
        power_offset = random.uniform(-200, 200)  # Leistung schwankt
        
        current_energy = self.base_energy + energy_offset
        current_power = abs(self.base_power + power_offset)  # Leistung immer positiv
        
        # Update base values
        self.base_energy = current_energy
        self.base_power = current_power
        
        return {
            "energy_active_kwh": {
                "value": round(current_energy, 3),
                "unit": "kWh",
                "description": "Active Energy",
                "record_index": 1
            },
            "power_active_w": {
                "value": round(current_power, 1),
                "unit": "W", 
                "description": "Active Power",
                "record_index": 2
            },
            "voltage_v": {
                "value": round(random.uniform(220, 240), 1),
                "unit": "V",
                "description": "Voltage",
                "record_index": 3
            },
            "current_a": {
                "value": round(current_power / 230, 2),  # I = P / U
                "unit": "A",
                "description": "Current", 
                "record_index": 4
            }
        }
    
    def get_device_info(self):
        """Gibt Geräteinformationen zurück"""
        return {
            "success": True,
            "device_id": self.device_id,
            "address": self.address,
            "manufacturer": self.manufacturer,
            "version": self.version,
            "medium": self.medium,
            "access_number": str(self.access_number),
            "identification": self.device_id,
            "timestamp": datetime.now().isoformat()
        }


class MockMBusCLI:
    """Simulierte Version des M-Bus CLI für Testing ohne Hardware"""
    
    def __init__(self, port="/dev/mock", baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        
        # Simulierte Geräte erstellen
        self.mock_devices = {
            0: MockMBusDevice(0, "00047028B5151002", "ISKRA", "electricity"),
            1: MockMBusDevice(1, "12345678901234567", "EMH", "electricity"),
            5: MockMBusDevice(5, "11111111111111111", "ITRON", "gas"),
        }
    
    def test_connection(self):
        """Simuliert Verbindungstest"""
        time.sleep(0.1)  # Simuliere Verbindungszeit
        
        return {
            "success": True,
            "port": self.port,
            "baudrate": self.baudrate,
            "status": "Mock Serial Port erfolgreich simuliert",
            "timestamp": datetime.now().isoformat()
        }
    
    def scan_devices(self):
        """Simuliert Gerätescan"""
        print(f"[MOCK] Simuliere Scan auf {self.port}", file=sys.stderr)
        
        devices = []
        scan_start = time.time()
        
        # Simuliere Scan-Zeit
        for address in range(0, 10):
            time.sleep(0.05)  # Simuliere Scan-Delay
            
            if address in self.mock_devices:
                device = self.mock_devices[address]
                devices.append({
                    "address": address,
                    "device_id": device.device_id,
                    "manufacturer": device.manufacturer,
                    "medium": device.medium,
                    "response_length": random.randint(50, 200),
                    "response_hex": "68" + "".join([f"{random.randint(0,255):02x}" for _ in range(10)]) + "16",
                    "found_at": datetime.now().isoformat()
                })
                print(f"[MOCK] Gerät simuliert an Adresse {address}: {device.device_id}", file=sys.stderr)
        
        scan_duration = time.time() - scan_start
        
        return {
            "success": True,
            "devices": devices,
            "device_count": len(devices),
            "scan_duration_seconds": round(scan_duration, 2),
            "tested_addresses": list(range(0, 10)),
            "port": self.port,
            "baudrate": self.baudrate,
            "timestamp": datetime.now().isoformat(),
            "mock_mode": True
        }
    
    def read_device(self, address):
        """Simuliert Gerätedaten-Lesung"""
        print(f"[MOCK] Simuliere Datenlesung von Adresse {address}", file=sys.stderr)
        
        read_start = time.time()
        time.sleep(0.2)  # Simuliere Read-Delay
        
        if address in self.mock_devices:
            device = self.mock_devices[address]
            data = device.get_simulated_data()
            
            return {
                "success": True,
                "address": address,
                "device_id": device.device_id,
                "data": data,
                "response_length": random.randint(80, 150),
                "response_hex": "68" + "".join([f"{random.randint(0,255):02x}" for _ in range(20)]) + "16",
                "read_duration_seconds": round(time.time() - read_start, 3),
                "timestamp": datetime.now().isoformat(),
                "port": self.port,
                "baudrate": self.baudrate,
                "mock_mode": True
            }
        else:
            return {
                "success": False,
                "error": f"Kein simuliertes Gerät an Adresse {address}",
                "address": address,
                "available_addresses": list(self.mock_devices.keys()),
                "mock_mode": True
            }


def demo_cli_usage():
    """Demonstriert die CLI Nutzung mit Mock-Daten"""
    print("=== M-Bus CLI Demo (Mock Mode) ===\n")
    
    cli = MockMBusCLI()
    
    # 1. Verbindungstest
    print("1. VERBINDUNGSTEST:")
    result = cli.test_connection()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    
    # 2. Gerätescan
    print("2. GERÄTESCAN:")
    result = cli.scan_devices()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    
    # 3. Gerätedaten lesen
    print("3. GERÄTEDATEN LESEN:")
    
    # Lese Daten von gefundenen Geräten
    for address in [0, 1, 5]:
        print(f"\n--- Adresse {address} ---")
        result = cli.read_device(address)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Teste nicht existentes Gerät
    print(f"\n--- Adresse 99 (nicht existent) ---")
    result = cli.read_device(99)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo_cli_usage()
    else:
        print("Usage:")
        print("  python mbus_cli_test.py demo    # Führe Demo aus")
        print("")
        print("Für echte Hardware:")
        print("  python mbus_cli.py test --port /dev/ttyUSB0 --baudrate 9600")
        print("  python mbus_cli.py scan --port /dev/ttyUSB0 --baudrate 9600")
        print("  python mbus_cli.py read --port /dev/ttyUSB0 --baudrate 9600 --address 1")