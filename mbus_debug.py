#!/usr/bin/env python3
"""
M-Bus Raw Debug Tool - zeigt unverarbeitete M-Bus Kommunikation
"""

import serial
import time
import argparse
import sys

def debug_mbus_communication(port, address, baudrate=9600):
    """Detailliertes M-Bus Debugging für spezifische Adresse"""
    print(f"=== M-Bus Raw Debug für Adresse {address} ===")
    print(f"Port: {port}, Baudrate: {baudrate}")
    
    try:
        with serial.Serial(port, baudrate, parity='E', stopbits=1, timeout=2.0) as ser:
            print(f"✅ Serial Port geöffnet: {ser.name}")
            print(f"📊 Einstellungen: {baudrate}E1, timeout=2s")
            
            # Buffer leeren
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            print("🧹 Buffer geleert")
            
            # 1. SND_NKE (Normalisierung) senden
            print(f"\n1️⃣ Sende SND_NKE (Normalisierung) an Adresse {address}")
            nke_checksum = (0x40 + address) % 256
            nke_frame = bytes([0x10, 0x40, address, nke_checksum, 0x16])
            print(f"📤 SND_NKE Frame: {nke_frame.hex().upper()}")
            
            ser.write(nke_frame)
            time.sleep(0.3)
            
            # Response prüfen
            available = ser.in_waiting
            if available > 0:
                nke_response = ser.read(available)
                print(f"📥 SND_NKE Response: {nke_response.hex().upper()} ({len(nke_response)} bytes)")
                if len(nke_response) > 0 and nke_response[0] == 0xE5:
                    print("✅ ACK empfangen - Gerät bestätigt Normalisierung")
                else:
                    print("⚠️ Unerwartete Antwort auf SND_NKE")
            else:
                print("❌ Keine Antwort auf SND_NKE")
            
            # 2. REQ_UD2 (Daten anfordern) senden
            print(f"\n2️⃣ Sende REQ_UD2 (Datenanforderung) an Adresse {address}")
            req_checksum = (0x5B + address) % 256
            req_frame = bytes([0x10, 0x5B, address, req_checksum, 0x16])
            print(f"📤 REQ_UD2 Frame: {req_frame.hex().upper()}")
            
            ser.reset_input_buffer()  # Buffer vor Request leeren
            ser.write(req_frame)
            time.sleep(1.0)  # Längere Wartezeit für Daten
            
            # Response prüfen
            available = ser.in_waiting
            print(f"📊 Verfügbare Bytes: {available}")
            
            if available > 0:
                data_response = ser.read(available)
                print(f"📥 REQ_UD2 Response: {data_response.hex().upper()}")
                print(f"📏 Response Länge: {len(data_response)} bytes")
                
                # Frame analysieren
                analyze_mbus_frame(data_response)
                
                return data_response
            else:
                print("❌ Keine Daten empfangen")
                return None
                
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None

def analyze_mbus_frame(data):
    """Analysiert M-Bus Frame Struktur"""
    print(f"\n🔍 Frame-Analyse:")
    
    if len(data) == 0:
        print("❌ Leerer Frame")
        return
    
    if len(data) == 1:
        if data[0] == 0xE5:
            print("✅ Single Character: ACK (0xE5)")
        else:
            print(f"❓ Single Character: 0x{data[0]:02X}")
        return
    
    # Prüfe Frame-Typ
    if data[0] == 0x10:
        print("📋 Frame-Typ: Short Frame (0x10)")
        if len(data) >= 5:
            c_field = data[1]
            a_field = data[2] 
            checksum = data[3]
            end = data[4]
            print(f"   C-Field: 0x{c_field:02X}")
            print(f"   A-Field: {a_field}")
            print(f"   Checksum: 0x{checksum:02X}")
            print(f"   End: 0x{end:02X}")
    
    elif data[0] == 0x68:
        print("📋 Frame-Typ: Variable Length Frame (0x68)")
        if len(data) >= 6:
            l_field = data[1]
            l_field2 = data[2]
            start2 = data[3]
            c_field = data[4]
            a_field = data[5]
            
            print(f"   L-Field: {l_field} bytes")
            print(f"   L-Field (repeat): {l_field2}")
            print(f"   Start (repeat): 0x{start2:02X}")
            print(f"   C-Field: 0x{c_field:02X}")
            print(f"   A-Field: {a_field}")
            
            if l_field == l_field2 and start2 == 0x68:
                print("✅ Header ist konsistent")
                
                if len(data) >= 6 + l_field:
                    ci_field = data[6] if len(data) > 6 else None
                    print(f"   CI-Field: 0x{ci_field:02X}" if ci_field else "   CI-Field: fehlt")
                    
                    # Zeige Data-Bereich
                    if len(data) > 7:
                        data_start = 7
                        data_end = 6 + l_field - 1  # -1 für Checksum
                        if data_end > data_start:
                            data_bytes = data[data_start:data_end]
                            print(f"   Data ({len(data_bytes)} bytes): {data_bytes.hex().upper()}")
                    
                    checksum = data[6 + l_field - 1] if len(data) >= 6 + l_field else None
                    end_byte = data[6 + l_field] if len(data) > 6 + l_field else None
                    
                    print(f"   Checksum: 0x{checksum:02X}" if checksum else "   Checksum: fehlt")
                    print(f"   End: 0x{end_byte:02X}" if end_byte else "   End: fehlt")
            else:
                print("❌ Header ist inkonsistent")
    else:
        print(f"❓ Unbekannter Frame-Typ: 0x{data[0]:02X}")
    
    # Hex-Dump für detaillierte Analyse
    print(f"\n📄 Hex-Dump:")
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = ' '.join(f'{b:02X}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        print(f"   {i:04X}: {hex_str:<48} |{ascii_str}|")

def main():
    parser = argparse.ArgumentParser(description='M-Bus Raw Communication Debug')
    parser.add_argument('port', help='Serial port (e.g., /dev/ttyAMA0)')
    parser.add_argument('address', type=int, help='M-Bus address to debug')
    parser.add_argument('-b', '--baudrate', type=int, default=9600, help='Baudrate')
    
    args = parser.parse_args()
    
    if args.address < 0 or args.address > 255:
        print("❌ Adresse muss zwischen 0 und 255 liegen")
        sys.exit(1)
    
    debug_mbus_communication(args.port, args.address, args.baudrate)

if __name__ == "__main__":
    main()