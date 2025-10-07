#!/usr/bin/env python3
"""
M-Bus CLI Tool - Version 2 mit direkter meterbus Library Integration
Basiert auf dem funktionierenden pyMeterBus GitHub Code
"""

import argparse
import json
import serial
import sys
import time
from datetime import datetime

try:
    import meterbus
except ImportError:
    print("ERROR: meterbus library nicht gefunden. Installiere mit: pip install pyMeterBus", file=sys.stderr)
    sys.exit(1)


class MBusCLI_V2:
    """M-Bus CLI mit direkter meterbus Library Integration"""
    
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.found_devices = []
    
    def test_connection(self):
        """Testet die M-Bus Verbindung mit meterbus Library"""
        print(f"[INFO] Teste M-Bus Verbindung zu {self.port} (Baudrate: {self.baudrate})", file=sys.stderr)
        
        try:
            with serial.serial_for_url(self.port, self.baudrate, 8, 'E', 1, timeout=1) as ser:
                print(f"[DEBUG] M-Bus Port geöffnet: {ser.name}", file=sys.stderr)
                
                # Test mit ADDRESS_NETWORK_LAYER ping (wie im GitHub Code)
                try:
                    meterbus.send_ping_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                    frame = meterbus.load(meterbus.recv_frame(ser, 1))
                    
                    if isinstance(frame, meterbus.TelegramACK):
                        return {
                            "success": True,
                            "port": self.port,
                            "baudrate": self.baudrate,
                            "message": "M-Bus Verbindung erfolgreich (ADDRESS_NETWORK_LAYER ping)",
                            "timestamp": datetime.now().isoformat()
                        }
                except Exception as ping_error:
                    print(f"[DEBUG] ADDRESS_NETWORK_LAYER ping fehlgeschlagen: {ping_error}", file=sys.stderr)
                
                # Fallback: Einfacher Test
                return {
                    "success": True,
                    "port": self.port,
                    "baudrate": self.baudrate,
                    "message": "Port geöffnet, aber kein ACK empfangen",
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
        """Scannt nach M-Bus Geräten mit meterbus Library (GitHub Methode)"""
        print(f"[INFO] Scanne M-Bus Geräte mit meterbus Library auf {self.port}", file=sys.stderr)
        
        scan_start = time.time()
        devices = []
        
        try:
            with serial.serial_for_url(self.port, self.baudrate, 8, 'E', 1, timeout=1) as ser:
                print(f"[DEBUG] M-Bus Serial geöffnet: {ser.name}", file=sys.stderr)
                
                # 1. Initialisiere Slaves (aus GitHub pyMeterBus Code)
                print("[DEBUG] Initialisiere M-Bus Slaves...", file=sys.stderr)
                
                if not self._init_slaves_meterbus(ser):
                    print("[WARNING] Slave-Initialisierung fehlgeschlagen", file=sys.stderr)
                
                # 2. Sekundäradresse-Scan mit meterbus Library
                print("[DEBUG] Starte Sekundäradresse-Scan...", file=sys.stderr)
                self.found_devices = []
                
                # Starte rekursiven Scan (GitHub Methode)
                self._mbus_scan_secondary_address_range(ser, 0, "FFFFFFFFFFFFFFFF")
                
                devices.extend(self.found_devices)
                
                # 3. Zusätzlich: Primäradresse-Test
                print("[DEBUG] Teste Primäradressen 0-255...", file=sys.stderr)
                for addr in range(0, 256):
                    if addr % 50 == 0:  # Progress alle 50 Adressen
                        print(f"[PROGRESS] Teste Adressen {addr}-{min(addr+49, 255)}...", file=sys.stderr)
                    
                    if self._ping_address_meterbus(ser, addr):
                        device_info = {
                            "address": addr,
                            "type": "primary",
                            "secondary_address": f"primary_{addr}",
                            "found_at": datetime.now().isoformat(),
                            "method": "ping"
                        }
                        devices.append(device_info)
                        print(f"[FOUND] Primäradresse {addr} antwortet", file=sys.stderr)
        
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
            "scan_method": "meterbus_library",
            "port": self.port,
            "baudrate": self.baudrate,
            "timestamp": datetime.now().isoformat()
        }
    
    def _init_slaves_meterbus(self, ser):
        """Initialisiert M-Bus Slaves mit meterbus Library (GitHub Code)"""
        try:
            # Aus GitHub: ping_address mit ADDRESS_NETWORK_LAYER
            if not self._ping_address_meterbus(ser, meterbus.ADDRESS_NETWORK_LAYER, retries=0):
                return self._ping_address_meterbus(ser, meterbus.ADDRESS_NETWORK_LAYER, retries=3)
            return True
        except:
            return False
    
    def _ping_address_meterbus(self, ser, address, retries=5):
        """Pingt M-Bus Adresse mit meterbus Library (GitHub Code)"""
        for i in range(retries + 1):
            try:
                meterbus.send_ping_frame(ser, address, False)
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
                
                if isinstance(frame, meterbus.TelegramACK):
                    return True
                    
            except meterbus.MBusFrameDecodeError:
                pass
            except Exception as e:
                print(f"[DEBUG] Ping Fehler bei {address}: {e}", file=sys.stderr)
            
            time.sleep(0.5)
        
        return False
    
    def _mbus_scan_secondary_address_range(self, ser, pos, mask):
        """Rekursiver Sekundäradresse-Scan mit meterbus Library (GitHub Code)"""
        # F ist Wildcard
        if mask[pos].upper() == 'F':
            l_start, l_end = 0, 9
        else:
            if pos < 15:
                self._mbus_scan_secondary_address_range(ser, pos + 1, mask)
                return
            else:
                l_start = l_end = int(mask[pos], 16)
        
        if mask[pos].upper() == 'F' or pos == 15:
            for i in range(l_start, l_end + 1):
                new_mask = (mask[:pos] + f"{i:1X}" + mask[pos+1:]).upper()
                
                val, match, manufacturer = self._mbus_probe_secondary_address(ser, new_mask)
                
                if val == True:
                    print(f"[FOUND] Device found with id {match} ({manufacturer}), using mask {new_mask}", file=sys.stderr)
                    device_info = {
                        "address": meterbus.ADDRESS_NETWORK_LAYER,
                        "type": "secondary",
                        "secondary_address": match,
                        "manufacturer": manufacturer,
                        "mask": new_mask,
                        "found_at": datetime.now().isoformat(),
                        "method": "secondary_scan"
                    }
                    self.found_devices.append(device_info)
                    
                elif val == False:  # Kollision
                    if pos < 15:
                        self._mbus_scan_secondary_address_range(ser, pos + 1, new_mask)
    
    def _mbus_probe_secondary_address(self, ser, mask):
        """Testet Sekundäradresse mit meterbus Library (GitHub Code)"""
        try:
            # False -> Collision
            # None -> No reply  
            # True -> Single reply
            meterbus.send_select_frame(ser, mask, False)
            
            try:
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
            except meterbus.MBusFrameDecodeError as e:
                frame = e.value
            
            if isinstance(frame, meterbus.TelegramACK):
                # Gerät selektiert - jetzt Daten anfordern
                meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                time.sleep(0.5)
                
                try:
                    frame = meterbus.load(meterbus.recv_frame(ser))
                    
                    if isinstance(frame, meterbus.TelegramLong):
                        return True, frame.secondary_address, frame.manufacturer
                        
                except meterbus.MBusFrameDecodeError:
                    pass
                
                return None, None, None
            
            return frame, None, None
            
        except Exception as e:
            print(f"[DEBUG] Probe Error: {e}", file=sys.stderr)
            return None, None, None
    
    def read_device(self, address_or_id):
        """Liest Daten von M-Bus Gerät mit meterbus Library"""
        print(f"[INFO] Lese M-Bus Daten von {address_or_id}", file=sys.stderr)
        
        read_start = time.time()
        
        try:
            with serial.serial_for_url(self.port, self.baudrate, 8, 'E', 1, timeout=1) as ser:
                
                if isinstance(address_or_id, str) and len(address_or_id) >= 16:
                    # Sekundäradresse - SELECT Frame senden
                    print(f"[DEBUG] Verwende Sekundäradresse: {address_or_id}", file=sys.stderr)
                    
                    meterbus.send_select_frame(ser, address_or_id, False)
                    time.sleep(0.1)
                    
                    # Nach Selektion REQ_UD2 an ADDRESS_NETWORK_LAYER
                    meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                    
                else:
                    # Primäradresse - direkt REQ_UD2
                    address = int(address_or_id) if isinstance(address_or_id, str) else address_or_id
                    print(f"[DEBUG] Verwende Primäradresse: {address}", file=sys.stderr)
                    
                    meterbus.send_request_frame(ser, address, False)
                
                time.sleep(0.5)
                
                # Antwort lesen
                try:
                    frame = meterbus.load(meterbus.recv_frame(ser))
                    
                    if isinstance(frame, meterbus.TelegramLong):
                        # Daten extrahieren
                        data_records = []
                        
                        for record in frame.records:
                            record_data = {
                                "value": getattr(record, 'parsed_value', None),
                                "unit": getattr(record, 'unit', None),
                                "function_field": getattr(record, 'function_field', None),
                                "storage_number": getattr(record, 'storage_number', None),
                                "tariff": getattr(record, 'tariff', None),
                                "device_type": getattr(record, 'device_type', None),
                            }
                            data_records.append(record_data)
                        
                        return {
                            "success": True,
                            "address": address_or_id,
                            "manufacturer": getattr(frame, 'manufacturer', None),
                            "identification": getattr(frame, 'identification', None),
                            "version": getattr(frame, 'version', None),
                            "device_type": getattr(frame, 'device_type', None),
                            "records": data_records,
                            "record_count": len(data_records),
                            "read_duration_seconds": round(time.time() - read_start, 3),
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Unerwarteter Frame-Typ: {type(frame)}",
                            "address": address_or_id
                        }
                        
                except meterbus.MBusFrameDecodeError as e:
                    return {
                        "success": False,
                        "error": f"Frame Decode Error: {e}",
                        "address": address_or_id
                    }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "address": address_or_id,
                "read_duration_seconds": round(time.time() - read_start, 3)
            }


def main():
    parser = argparse.ArgumentParser(description='M-Bus CLI Tool V2 (meterbus Library)')
    parser.add_argument('command', choices=['test', 'scan', 'read'], 
                       help='Auszuführender Befehl')
    parser.add_argument('--port', required=True, 
                       help='Serieller Port (z.B. /dev/ttyAMA0)')
    parser.add_argument('--baudrate', type=int, default=9600,
                       help='Baudrate (Standard: 9600)')
    parser.add_argument('--address', 
                       help='Geräte-Adresse für read Befehl (Primär: 0-250, Sekundär: 16-stellige Hex)')
    
    args = parser.parse_args()
    
    # CLI Tool initialisieren
    cli = MBusCLI_V2(args.port, args.baudrate)
    
    try:
        result = None
        
        if args.command == 'test':
            result = cli.test_connection()
        elif args.command == 'scan':
            result = cli.scan_devices()
        elif args.command == 'read':
            if not args.address:
                result = {
                    "success": False,
                    "error": "Address parameter required for read command"
                }
            else:
                result = cli.read_device(args.address)
        
        # JSON Ausgabe
        if result:
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