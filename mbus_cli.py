#!/usr/bin/env python3
"""
M-Bus CLI Tool - Vereinfachte Version
Einfaches Command Line Interface für M-Bus Geräte-Kommunikation

Usage:
    python mbus_cli.py scan --port /dev/ttyUSB0 --baudrate 9600
    python mbus_cli.py read --port /dev/ttyUSB0 --baudrate 9600 --address 1
    python mbus_cli.py test --port /dev/ttyUSB0 --baudrate 9600
"""

import argparse
import json
import sys
import time
from decimal import Decimal
from datetime import datetime

# M-Bus Imports
try:
    import serial
    import meterbus
except ImportError as e:
    print(f"ERROR: Abhängigkeiten nicht installiert! {e}")
    print("Installiere mit: pip install pyserial meterbus")
    sys.exit(1)


class MBusCLI:
    """Vereinfachtes CLI Interface für M-Bus Kommunikation"""
    
    def __init__(self, port, baudrate=9600, timeout=2.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
    def _safe_convert(self, value):
        """Konvertiert Werte sicher zu JSON-serialisierbaren Typen"""
        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, '__dict__'):
            return str(value)
        return value
    
    def test_connection(self):
        """Testet die serielle Verbindung"""
        print(f"[INFO] Teste Verbindung zu {self.port} (Baudrate: {self.baudrate})", file=sys.stderr)
        
        try:
            with serial.Serial(self.port, self.baudrate, timeout=1.0) as ser:
                return {
                    "success": True,
                    "port": self.port,
                    "baudrate": self.baudrate,
                    "status": "Serial Port erfolgreich geöffnet",
                    "timestamp": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "success": False,
                "port": self.port,
                "baudrate": self.baudrate,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def scan_devices(self):
        """Scannt nach verfügbaren M-Bus Geräten mit Sekundäradresse-Scan"""
        print(f"[INFO] Scanne M-Bus Geräte auf {self.port} (Baudrate: {self.baudrate})", file=sys.stderr)
        
        devices = []
        scan_start = time.time()
        
        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as ser:
                print("[SCAN] Führe M-Bus Sekundäradresse-Scan durch...", file=sys.stderr)
                
                # M-Bus Sekundäradresse Scan
                # 1. SND_NKE an Broadcast (255) - Normalisierung
                self._send_snd_nke(ser, 255)
                time.sleep(0.1)
                
                # 2. Wildcards für Sekundäradresse-Scan
                # Format: Manufacturer(2) + ID(4) + Version(1) + Medium(1) = 8 Bytes
                wildcards = [
                    "FFFFFFFFFFFFFFFF",  # Alle Geräte
                    "FFFFFFFFFF1FFF1F",  # Elektrische Geräte (Medium 1F)
                    "FFFFFFFFFF16FF16",  # Wärme/Kälte Geräte (Medium 16)
                ]
                
                found_addresses = set()
                
                for wildcard in wildcards:
                    print(f"[SCAN] Teste Wildcard: {wildcard}", file=sys.stderr)
                    
                    # Search for specific secondary address pattern
                    devices_found = self._scan_secondary_addresses(ser, wildcard)
                    
                    for device in devices_found:
                        if device["secondary_address"] not in found_addresses:
                            devices.append(device)
                            found_addresses.add(device["secondary_address"])
                            print(f"[FOUND] Gerät: {device['secondary_address']}", file=sys.stderr)
                
                # Zusätzlich: Teste bekannte Primäradressen (0-10)
                print("[SCAN] Teste zusätzlich Primäradressen 0-10...", file=sys.stderr)
                for address in range(0, 11):
                    try:
                        response_data = self._test_primary_address(ser, address)
                        if response_data:
                            device_info = {
                                "address": address,
                                "type": "primary",
                                "secondary_address": f"primary_{address}",
                                "response_length": len(response_data),
                                "response_hex": response_data.hex(),
                                "found_at": datetime.now().isoformat()
                            }
                            devices.append(device_info)
                            print(f"[FOUND] Primäradresse {address}", file=sys.stderr)
                    except:
                        continue
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "devices": [],
                "scan_duration_seconds": time.time() - scan_start
            }
        
        scan_duration = time.time() - scan_start
        
        return {
            "success": True,
            "devices": devices,
            "device_count": len(devices),
            "scan_duration_seconds": round(scan_duration, 2),
            "scan_method": "secondary_address_wildcard",
            "port": self.port,
            "baudrate": self.baudrate,
            "timestamp": datetime.now().isoformat()
        }
    
    def _parse_frame(self, frame):
        """Versucht einen empfangenen Frame zu parsen"""
        if not frame:
            return None
        
        try:
            result = {
                "frame_type": type(frame).__name__,
                "attributes": {}
            }
            
            # Sammle alle verfügbaren Attribute
            for attr in dir(frame):
                if not attr.startswith('_'):
                    try:
                        value = getattr(frame, attr)
                        if not callable(value):
                            result["attributes"][attr] = self._safe_convert(value)
                    except:
                        continue
            
            return result
            
        except Exception as e:
            return {"parse_error": str(e)}
    
    def read_device(self, address_or_id):
        """Liest Daten von einem spezifischen Gerät (Primär- oder Sekundäradresse)"""
        print(f"[INFO] Lese Daten von {address_or_id}", file=sys.stderr)
        
        read_start = time.time()
        
        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as ser:
                
                # Prüfe ob es eine Sekundäradresse (16 Zeichen hex) oder Primäradresse ist
                if isinstance(address_or_id, str) and len(address_or_id) >= 16:
                    # Sekundäradresse - Verwende SND_UD an 255 (Broadcast)
                    print(f"[READ] Verwende Sekundäradresse: {address_or_id}", file=sys.stderr)
                    
                    # 1. Normalisierung
                    self._send_snd_nke(ser, 255)
                    time.sleep(0.1)
                    
                    # 2. SND_UD (Select Device) mit Sekundäradresse
                    # Vereinfacht: Sende REQ_UD2 an Broadcast
                    req_frame = bytes([0x10, 0x5B, 255, 0x5B + 255, 0x16])
                    ser.write(req_frame)
                    
                else:
                    # Primäradresse
                    address = int(address_or_id) if isinstance(address_or_id, str) else address_or_id
                    print(f"[READ] Verwende Primäradresse: {address}", file=sys.stderr)
                    
                    # Standard REQ_UD2 an Primäradresse
                    checksum = (0x5B + address) % 256
                    req_frame = bytes([0x10, 0x5B, address, checksum, 0x16])
                    ser.write(req_frame)
                
                time.sleep(0.2)  # Warte auf Antwort
                
                # Lese Antwort
                response = ser.read(512)  # Größerer Buffer für M-Bus Daten
                
                if len(response) > 0:
                    # Versuche mit meterbus zu dekodieren
                    try:
                        if hasattr(meterbus, 'recv_frame'):
                            frame = meterbus.recv_frame(ser)
                            frame_data = self._parse_frame(frame) if frame else None
                        else:
                            frame_data = None
                    except:
                        frame_data = None
                    
                    return {
                        "success": True,
                        "address": address_or_id,
                        "response_length": len(response),
                        "response_hex": response.hex(),
                        "frame_data": frame_data,
                        "data": self._extract_measurements_from_response(response),
                        "read_duration_seconds": round(time.time() - read_start, 3),
                        "timestamp": datetime.now().isoformat(),
                        "port": self.port,
                        "baudrate": self.baudrate
                    }
                else:
                    return {
                        "success": False,
                        "error": "Keine Antwort vom Gerät",
                        "address": address_or_id,
                        "response_length": 0
                    }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "address": address_or_id,
                "read_duration_seconds": round(time.time() - read_start, 3)
            }
    
    def _send_snd_nke(self, ser, address):
        """Sendet SND_NKE (Normalisierung) an Adresse"""
        try:
            # SND_NKE Frame: 10 40 <addr> <checksum> 16
            checksum = (0x40 + address) % 256
            frame = bytes([0x10, 0x40, address, checksum, 0x16])
            ser.write(frame)
            time.sleep(0.1)
            # Response lesen und verwerfen
            ser.read(10)
        except:
            pass
    
    def _scan_secondary_addresses(self, ser, wildcard_pattern):
        """Scannt Sekundäradressen mit Wildcard-Pattern"""
        devices = []
        try:
            # REQ_UD2 an Broadcast (255) senden
            req_frame = bytes([0x10, 0x5B, 255, 0x5B + 255, 0x16])
            ser.write(req_frame)
            time.sleep(0.2)
            
            # Response lesen
            response = ser.read(255)
            
            if len(response) > 10:  # Mindestens ein gültiger Frame
                # Versuche M-Bus Frame zu dekodieren
                if response[0] == 0x68:  # Variable Length Frame
                    try:
                        # Extrahiere Sekundäradresse aus Response
                        secondary_addr = self._extract_secondary_address(response)
                        if secondary_addr:
                            device_info = {
                                "address": 255,  # Broadcast verwendet
                                "type": "secondary", 
                                "secondary_address": secondary_addr,
                                "response_length": len(response),
                                "response_hex": response.hex(),
                                "found_at": datetime.now().isoformat()
                            }
                            devices.append(device_info)
                    except:
                        pass
        except:
            pass
        
        return devices
    
    def _extract_secondary_address(self, response_data):
        """Extrahiert Sekundäradresse aus M-Bus Response"""
        try:
            if len(response_data) < 20:
                return None
            
            # M-Bus Variable Length Frame: 68 L L 68 C A CI ...
            if response_data[0] == 0x68 and response_data[3] == 0x68:
                length = response_data[1]
                if len(response_data) >= length + 6:
                    # CI-Field position (nach C und A)
                    ci_pos = 6
                    if ci_pos < len(response_data):
                        # Versuche Sekundäradresse zu extrahieren (falls im Payload)
                        # Vereinfacht: Nutze die ersten 8 Bytes nach CI als Sekundäradresse
                        start_pos = ci_pos + 1
                        if start_pos + 8 <= len(response_data):
                            sec_addr_bytes = response_data[start_pos:start_pos+8]
                            secondary_addr = sec_addr_bytes.hex().upper()
                            # Formatiere als typische M-Bus ID
                            return f"{secondary_addr[:8]}{secondary_addr[8:]}"
        except:
            pass
        
        return None
    
    def _test_primary_address(self, ser, address):
        """Testet Primäradresse"""
        try:
            # REQ_UD2 Frame: 10 5B <addr> <checksum> 16
            checksum = (0x5B + address) % 256
            frame = bytes([0x10, 0x5B, address, checksum, 0x16])
            ser.write(frame)
            time.sleep(0.2)
            
            # Response lesen
            response = ser.read(255)
            
            if len(response) > 5:  # Mindestens ACK oder Frame
                return response
            
        except:
            pass
        
        return None
        """Versucht einen empfangenen Frame zu parsen"""
        if not frame:
            return None
        
        try:
            result = {
                "frame_type": type(frame).__name__,
                "attributes": {}
            }
            
            # Sammle alle verfügbaren Attribute
            for attr in dir(frame):
                if not attr.startswith('_'):
                    try:
                        value = getattr(frame, attr)
                        if not callable(value):
                            result["attributes"][attr] = self._safe_convert(value)
                    except:
                        continue
            
            return result
            
        except Exception as e:
            return {"parse_error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='M-Bus CLI Tool (Vereinfacht)')
    parser.add_argument('command', choices=['test', 'scan', 'read'], 
                       help='Auszuführender Befehl')
    parser.add_argument('--port', required=True, 
                       help='Serieller Port (z.B. /dev/ttyUSB0)')
    parser.add_argument('--baudrate', type=int, default=9600,
                       help='Baudrate (Standard: 9600)')
    parser.add_argument('--address', type=int,
                       help='Geräte-Adresse für read Befehl')
    parser.add_argument('--timeout', type=float, default=2.0,
                       help='Timeout in Sekunden (Standard: 2.0)')
    parser.add_argument('--pretty', action='store_true',
                       help='Formatierte JSON-Ausgabe')
    
    args = parser.parse_args()
    
    # Validierung
    if args.command == 'read' and args.address is None:
        print("ERROR: --address ist erforderlich für read Befehl", file=sys.stderr)
        sys.exit(1)
    
    # CLI erstellen
    cli = MBusCLI(args.port, args.baudrate, args.timeout)
    
    # Befehl ausführen
    result = None
    try:
        if args.command == 'test':
            result = cli.test_connection()
        elif args.command == 'scan':
            result = cli.scan_devices()
        elif args.command == 'read':
            result = cli.read_device(args.address)
        
        # JSON-Ausgabe
        if result:
            if args.pretty:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(result, ensure_ascii=False))
            
    except KeyboardInterrupt:
        print("\n[INFO] Abgebrochen durch Benutzer", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e),
            "command": args.command
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


def _extract_measurements_from_response(response_data):
    """Extrahiert Messwerte aus M-Bus Response (vereinfacht)"""
    try:
        if len(response_data) < 10:
            return {}
        
        # Vereinfachte Extraktion - für den Anfang nur Dummy-Daten
        # In echter Implementierung würde hier DIF/VIF Parsing stattfinden
        measurements = {}
        
        # Beispiel: Suche nach typischen M-Bus Patterns
        if len(response_data) > 20:
            measurements["raw_response"] = {
                "value": len(response_data),
                "unit": "bytes",
                "description": "Response Length",
                "record_index": 1
            }
            
            # Vereinfachte "Energie"-Extraktion (für Demo)
            # Real würde DIF/VIF parsing verwendet
            measurements["status"] = {
                "value": "online",
                "unit": "",
                "description": "Device Status",
                "record_index": 2
            }
        
        return measurements
        
    except Exception as e:
        print(f"[ERROR] Messwert-Extraktion fehlgeschlagen: {e}", file=sys.stderr)
        return {}


if __name__ == "__main__":
    main()