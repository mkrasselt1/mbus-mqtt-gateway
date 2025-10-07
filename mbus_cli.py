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
        """Scannt nach verfügbaren M-Bus Geräten (vereinfacht)"""
        print(f"[INFO] Scanne M-Bus Geräte auf {self.port} (Baudrate: {self.baudrate})", file=sys.stderr)
        
        devices = []
        scan_start = time.time()
        
        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as ser:
                # Teste einige bekannte Adressen
                test_addresses = [0, 1, 2, 3, 4, 5, 10, 254]  # Häufige Adressen
                
                for address in test_addresses:
                    try:
                        print(f"[SCAN] Teste Adresse {address}...", file=sys.stderr)
                        
                        # Versuche meterbus.send_request_frame
                        if hasattr(meterbus, 'send_request_frame'):
                            meterbus.send_request_frame(ser, address)
                            time.sleep(0.1)  # Kurze Pause
                            
                            # Versuche Antwort zu lesen
                            response = ser.read(255)  # Lese bis zu 255 Bytes
                            
                            if len(response) > 0:
                                devices.append({
                                    "address": address,
                                    "response_length": len(response),
                                    "response_hex": response.hex(),
                                    "found_at": datetime.now().isoformat()
                                })
                                print(f"[FOUND] Gerät an Adresse {address} (Response: {len(response)} Bytes)", file=sys.stderr)
                        
                    except Exception as e:
                        print(f"[DEBUG] Adresse {address} Fehler: {e}", file=sys.stderr)
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
            "tested_addresses": test_addresses,
            "port": self.port,
            "baudrate": self.baudrate,
            "timestamp": datetime.now().isoformat()
        }
    
    def read_device(self, address):
        """Liest Daten von einem spezifischen Gerät (vereinfacht)"""
        print(f"[INFO] Lese Daten von Adresse {address}", file=sys.stderr)
        
        read_start = time.time()
        
        try:
            with serial.Serial(self.port, self.baudrate, timeout=self.timeout) as ser:
                # Sende Request Frame
                if hasattr(meterbus, 'send_request_frame'):
                    meterbus.send_request_frame(ser, address)
                else:
                    # Fallback: Manueller Frame-Aufbau
                    # Vereinfachter REQ_UD2 Frame
                    frame = bytes([0x10, 0x5B, address, 0x5B + address, 0x16])
                    ser.write(frame)
                
                time.sleep(0.2)  # Warte auf Antwort
                
                # Lese Antwort
                response = ser.read(255)
                
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
                        "address": address,
                        "response_length": len(response),
                        "response_hex": response.hex(),
                        "frame_data": frame_data,
                        "read_duration_seconds": round(time.time() - read_start, 3),
                        "timestamp": datetime.now().isoformat(),
                        "port": self.port,
                        "baudrate": self.baudrate
                    }
                else:
                    return {
                        "success": False,
                        "error": "Keine Antwort vom Gerät",
                        "address": address,
                        "response_length": 0
                    }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "address": address,
                "read_duration_seconds": round(time.time() - read_start, 3)
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


if __name__ == "__main__":
    main()