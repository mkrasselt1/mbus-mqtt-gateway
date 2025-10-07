#!/usr/bin/env python3
"""
Einfacher M-Bus Test - kopiert das funktionierende mbus-serial-scan-secondary.py Pattern
"""

import serial
import time
import argparse
import sys

def test_basic_communication(port, baudrate=9600):
    """Testet grundlegende serielle Kommunikation"""
    print(f"[TEST] Teste grundlegende Kommunikation mit {port} @ {baudrate}")
    
    try:
        with serial.Serial(port, baudrate, timeout=1.0) as ser:
            print(f"[TEST] Port geöffnet: {ser.name}")
            print(f"[TEST] Einstellungen: {baudrate} baud, 8E1, timeout=1s")
            
            # Buffer leeren
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Einfacher Echo-Test (falls möglich)
            test_data = b'\x10\x40\x01\x41\x16'  # SND_NKE an Adresse 1
            print(f"[TEST] Sende Test-Frame: {test_data.hex()}")
            
            ser.write(test_data)
            time.sleep(0.5)
            
            available = ser.in_waiting
            print(f"[TEST] Verfügbare Bytes: {available}")
            
            if available > 0:
                response = ser.read(available)
                print(f"[TEST] Response: {response.hex()}")
                return True
            else:
                print("[TEST] Keine Antwort")
                return False
                
    except Exception as e:
        print(f"[ERROR] Kommunikationstest fehlgeschlagen: {e}")
        return False

def test_mbus_addresses(port, baudrate=9600, max_address=255):
    """Testet M-Bus Adressen 0-max_address mit detailliertem Logging"""
    print(f"[SCAN] Teste M-Bus Adressen 0-{max_address} auf {port}")
    
    found_devices = []
    
    try:
        with serial.Serial(port, baudrate, parity='E', stopbits=1, timeout=1.0) as ser:
            print(f"[SCAN] M-Bus Port geöffnet: {ser.name}")
            
            for addr in range(0, max_address + 1):
                if addr % 10 == 0:  # Progress Update alle 10 Adressen
                    print(f"\n[PROGRESS] Teste Adressen {addr}-{min(addr+9, max_address)}...")
                
                print(f"[SCAN] Teste Adresse {addr}...", end='', flush=True)
                
                # Buffer leeren
                ser.reset_input_buffer()
                
                # REQ_UD2 Frame
                checksum = (0x5B + addr) % 256
                frame = bytes([0x10, 0x5B, addr, checksum, 0x16])
                
                ser.write(frame)
                time.sleep(0.1)  # Kürzere Wartezeit für schnelleren Scan
                
                available = ser.in_waiting
                
                if available > 0:
                    response = ser.read(available)
                    print(f" ✅ GEFUNDEN: {len(response)} bytes")
                    print(f"[FOUND] Response: {response.hex()}")
                    
                    found_devices.append({
                        "address": addr,
                        "response_length": len(response),
                        "response": response.hex()
                    })
                else:
                    print(" ❌")
                    
    except Exception as e:
        print(f"\n[ERROR] Scan fehlgeschlagen: {e}")
    
    print(f"\n[RESULT] Scan abgeschlossen: {len(found_devices)} Geräte gefunden")
    for device in found_devices:
        print(f"[RESULT] Adresse {device['address']}: {device['response_length']} bytes")
    
    return found_devices

def test_with_meterbus_library(port, baudrate=9600):
    """Testet mit der meterbus Library direkt"""
    print(f"[LIB] Teste mit meterbus Library auf {port}")
    
    try:
        import meterbus
        
        with serial.serial_for_url(port, baudrate, 8, 'E', 1, timeout=1) as ser:
            print(f"[LIB] meterbus Serial geöffnet")
            
            # Versuche ADDRESS_NETWORK_LAYER ping wie im GitHub Code
            print("[LIB] Teste ADDRESS_NETWORK_LAYER ping...")
            
            try:
                meterbus.send_ping_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
                
                if isinstance(frame, meterbus.TelegramACK):
                    print("[LIB] ADDRESS_NETWORK_LAYER ping erfolgreich!")
                    return True
                else:
                    print(f"[LIB] Unerwartete Antwort: {type(frame)}")
                    
            except Exception as e:
                print(f"[LIB] Ping fehlgeschlagen: {e}")
                
    except ImportError:
        print("[LIB] meterbus Library nicht verfügbar")
    except Exception as e:
        print(f"[LIB] Fehler: {e}")
    
    return False

def main():
    parser = argparse.ArgumentParser(description='Einfacher M-Bus Kommunikationstest')
    parser.add_argument('port', help='Serieller Port (z.B. /dev/ttyAMA0)')
    parser.add_argument('-b', '--baudrate', type=int, default=9600, help='Baudrate')
    parser.add_argument('--test', choices=['basic', 'scan', 'meterbus', 'all'], 
                       default='all', help='Test-Modus')
    parser.add_argument('--max-address', type=int, default=10, 
                       help='Maximale Primäradresse für Scan (Standard: 10, Max: 255)')
    
    args = parser.parse_args()
    
    print(f"M-Bus Kommunikationstest")
    print(f"Port: {args.port}")
    print(f"Baudrate: {args.baudrate}")
    print(f"Test: {args.test}")
    print(f"Max-Address: {args.max_address}")
    print("-" * 50)
    
    if args.test in ['basic', 'all']:
        print("\n=== BASIC COMMUNICATION TEST ===")
        test_basic_communication(args.port, args.baudrate)
    
    if args.test in ['scan', 'all']:
        print("\n=== M-BUS ADDRESS SCAN ===")
        test_mbus_addresses(args.port, args.baudrate, args.max_address)
    
    if args.test in ['meterbus', 'all']:
        print("\n=== METERBUS LIBRARY TEST ===")
        test_with_meterbus_library(args.port, args.baudrate)

if __name__ == "__main__":
    main()