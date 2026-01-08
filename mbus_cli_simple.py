#!/usr/bin/env python3
"""
Einfaches M-Bus CLI basierend auf dem offiziellen pyMeterBus Beispiel
Verwendet die originale pyMeterBus Library ohne zusätzliche VIF-Skalierung
"""

import argparse
import time
import sys
import json
from datetime import datetime

try:
    import meterbus
    from serial import serial_for_url, SerialException
except ImportError as e:
    print(f"Benötigte Library nicht gefunden: {e}", file=sys.stderr)
    sys.exit(1)

def ping_address(ser, address, retries=5, read_echo=False):
    """Pingt M-Bus Adresse - aus pyMeterBus Beispiel"""
    for i in range(0, retries + 1):
        meterbus.send_ping_frame(ser, address, read_echo)
        try:
            frame = meterbus.load(meterbus.recv_frame(ser, 1))
            if isinstance(frame, meterbus.TelegramACK):
                return True
        except meterbus.MBusFrameDecodeError:
            pass
        time.sleep(0.5)
    return False

def format_port(port):
    """Formatiert Port für serial_for_url (konvertiert IP:Port zu socket://IP:Port)"""
    if not isinstance(port, str):
        return port
    if '://' in port:
        return port
    if ':' in port and not port.upper().startswith('COM') and not port.startswith('/'):
        return f"socket://{port}"
    return port

def scan_primary_addresses(port, baudrate):
    """Scannt primäre M-Bus Adressen"""
    print("Scanne primäre M-Bus Adressen...", file=sys.stderr)
    port = format_port(port)
    found_devices = []
    
    try:
        with serial_for_url(port, baudrate, parity='E', stopbits=1, timeout=1) as ser:
            for address in range(0, meterbus.MAX_PRIMARY_SLAVES + 1):
                if ping_address(ser, address, 3):
                    found_devices.append(address)
                    print(f"Gerät gefunden auf Adresse {address}", file=sys.stderr)
    except Exception as e:
        print(f"Scan-Fehler: {e}", file=sys.stderr)
        return []
    
    return found_devices

def read_device_data(port, baudrate, address):
    """Liest Daten von M-Bus Gerät - basierend auf pyMeterBus Beispiel"""
    port = format_port(port)
    try:
        ibt = meterbus.inter_byte_timeout(baudrate)
        with serial_for_url(port, baudrate, parity='E', stopbits=1, 
                          inter_byte_timeout=ibt, timeout=1) as ser:
            
            frame = None
            
            if meterbus.is_primary_address(address):
                print(f"[INFO] Lese Primäradresse {address}", file=sys.stderr)
                if ping_address(ser, address, 3, False):
                    meterbus.send_request_frame(ser, address, read_echo=False)
                    frame = meterbus.load(
                        meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
                else:
                    print(f"[ERROR] Keine Antwort von Adresse {address}", file=sys.stderr)
                    return None
                    
            elif meterbus.is_secondary_address(address):
                print(f"[INFO] Lese Sekundäradresse {address}", file=sys.stderr)
                if ping_address(ser, meterbus.ADDRESS_NETWORK_LAYER, 3, False):
                    meterbus.send_select_frame(ser, address, False)
                    try:
                        ack_frame = meterbus.load(meterbus.recv_frame(ser, 1))
                    except meterbus.MBusFrameDecodeError as e:
                        ack_frame = e.value
                    
                    # Stelle sicher, dass Select Frame ACK erhalten wurde
                    assert isinstance(ack_frame, meterbus.TelegramACK)
                    
                    meterbus.send_request_frame(
                        ser, meterbus.ADDRESS_NETWORK_LAYER, read_echo=False)
                    time.sleep(0.3)
                    frame = meterbus.load(
                        meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
                else:
                    print(f"[ERROR] Keine Antwort vom Network Layer", file=sys.stderr)
                    return None
            
            if frame is not None:
                return extract_frame_data(frame)
            else:
                print(f"[ERROR] Kein Frame erhalten", file=sys.stderr)
                return None
                
    except Exception as e:
        print(f"[ERROR] Read-Fehler: {e}", file=sys.stderr)
        return None

def extract_frame_data(frame):
    """Extrahiert Daten aus pyMeterBus Frame - ORIGINALWERTE ohne zusätzliche Skalierung"""
    try:
        # Records extrahieren - genau wie im pyMeterBus Beispiel
        recs = []
        for rec in frame.records:
            # Einheit behandeln - wenn None oder leer, dann leer lassen
            unit = rec.unit
            if unit is None:
                unit = ""
            else:
                unit = str(unit)
            
            # Wert für JSON-Serialisierung konvertieren
            value = rec.value
            try:
                # Versuche Decimal oder andere numerische Typen in float umzuwandeln
                value = float(value)
            except (ValueError, TypeError):
                # Bei nicht-numerischen Werten (z.B. Strings, Datumsangaben) als String belassen
                value = str(value)
            
            recs.append({
                'value': value,
                'unit': unit
            })
        
        # Frame-Daten - genau wie im pyMeterBus Beispiel
        result = {
            'manufacturer': frame.body.bodyHeader.manufacturer_field.decodeManufacturer,
            'identification': ''.join(map('{:02x}'.format, frame.body.bodyHeader.id_nr)),
            'access_no': frame.body.bodyHeader.acc_nr_field.parts[0],
            'medium': frame.body.bodyHeader.measure_medium_field.parts[0],
            'records': recs,
            'timestamp': datetime.now().isoformat(),
            'record_count': len(recs)
        }
        
        print(f"[INFO] {len(recs)} Records extrahiert", file=sys.stderr)
        for idx, rec in enumerate(recs):
            print(f"[INFO] Record {idx+1}: {rec['value']} {rec['unit']}", file=sys.stderr)
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Frame-Extraktion fehlgeschlagen: {e}", file=sys.stderr)
        return None

def main():
    parser = argparse.ArgumentParser(
        description='Einfaches M-Bus CLI basierend auf pyMeterBus',
        epilog='Beispiele:\n'
               '  Serial: --port COM3 oder --port /dev/ttyUSB0\n'
               '  TCP/IP: --port 192.168.1.100:8899\n'
               '  Explizit: --port socket://192.168.1.100:8899',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', required=True, 
                       help='Serial port (COM3, /dev/ttyUSB0) oder TCP (192.168.1.100:8899)')
    parser.add_argument('--baudrate', type=int, default=9600, help='Baudrate')
    
    subparsers = parser.add_subparsers(dest='command', help='Verfügbare Kommandos')
    
    # Scan Kommando
    scan_parser = subparsers.add_parser('scan', help='Scanne M-Bus Adressen')
    
    # Read Kommando
    read_parser = subparsers.add_parser('read', help='Lese M-Bus Gerät')
    read_parser.add_argument('--address', required=True, help='M-Bus Adresse (primär oder sekundär)')
    
    args = parser.parse_args()
    
    if args.command == 'scan':
        devices = scan_primary_addresses(args.port, args.baudrate)
        result = {
            "command": "scan",
            "found_devices": devices,
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(result, indent=2))
        
    elif args.command == 'read':
        # Adresse parsen
        try:
            address = int(args.address)
        except ValueError:
            address = args.address.upper()
        
        data = read_device_data(args.port, args.baudrate, address)
        if data:
            result = {
                "command": "read",
                "address": address,
                "success": True,
                "data": data
            }
        else:
            result = {
                "command": "read", 
                "address": address,
                "success": False,
                "error": "Keine Daten erhalten"
            }
        
        print(json.dumps(result, indent=2))
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()