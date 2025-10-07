#!/usr/bin/env python3
"""
M-Bus Command Tester - testet verschiedene M-Bus Kommandos
"""

import serial
import time
import argparse

def test_mbus_commands(port, address, baudrate=9600):
    """Testet verschiedene M-Bus Kommandos"""
    
    commands = [
        ("SND_NKE", 0x40, "Normalisierung"),
        ("REQ_UD1", 0x5A, "Daten anfordern (Klasse 1)"),  
        ("REQ_UD2", 0x5B, "Daten anfordern (Klasse 2)"),
        ("REQ_UD3", 0x5C, "Daten anfordern (Klasse 3)"),
    ]
    
    try:
        with serial.Serial(port, baudrate, parity='E', stopbits=1, timeout=1.0) as ser:
            print(f"🔧 Teste M-Bus Kommandos für Adresse {address}")
            print(f"📡 Port: {port} @ {baudrate} baud")
            print("=" * 60)
            
            for cmd_name, cmd_code, description in commands:
                print(f"\n📤 {cmd_name} (0x{cmd_code:02X}): {description}")
                
                # Buffer leeren
                ser.reset_input_buffer()
                
                # Frame konstruieren
                checksum = (cmd_code + address) % 256
                frame = bytes([0x10, cmd_code, address, checksum, 0x16])
                print(f"   Frame: {frame.hex().upper()}")
                
                # Senden
                ser.write(frame)
                time.sleep(0.5)
                
                # Response prüfen
                available = ser.in_waiting
                if available > 0:
                    response = ser.read(available)
                    print(f"   📥 Response ({len(response)} bytes): {response.hex().upper()}")
                    
                    # Kurze Analyse
                    if len(response) == 1 and response[0] == 0xE5:
                        print("   ✅ ACK empfangen")
                    elif len(response) > 5:
                        print("   📊 Datenframe empfangen")
                    else:
                        print("   ❓ Unbekannte Antwort")
                else:
                    print("   ❌ Keine Antwort")
                
                time.sleep(0.2)  # Pause zwischen Kommandos
                
    except Exception as e:
        print(f"❌ Fehler: {e}")

def main():
    parser = argparse.ArgumentParser(description='M-Bus Command Tester')
    parser.add_argument('port', help='Serial port')
    parser.add_argument('address', type=int, help='M-Bus address')
    parser.add_argument('-b', '--baudrate', type=int, default=9600, help='Baudrate')
    
    args = parser.parse_args()
    test_mbus_commands(args.port, args.address, args.baudrate)

if __name__ == "__main__":
    main()