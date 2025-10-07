#!/usr/bin/env python3
"""
M-Bus Frame Parser - Dekodiert M-Bus Frames manuell
"""

def parse_mbus_frame(hex_data):
    """Parst einen M-Bus Frame und extrahiert alle Informationen"""
    
    # Konvertiere Hex-String zu Bytes wenn nötig
    if isinstance(hex_data, str):
        data = bytes.fromhex(hex_data.replace(' ', ''))
    else:
        data = hex_data
    
    print("=" * 60)
    print("🔍 M-Bus Frame Parser")
    print("=" * 60)
    
    if len(data) < 6:
        print("❌ Frame zu kurz")
        return None
    
    # Variable Length Frame (0x68)
    if data[0] == 0x68:
        l_field = data[1]
        c_field = data[4]
        a_field = data[5]
        ci_field = data[6] if len(data) > 6 else 0
        
        print(f"📋 Frame-Typ: Variable Length Frame")
        print(f"📏 Länge: {l_field} bytes")
        print(f"🎯 C-Field: 0x{c_field:02X}")
        print(f"📍 A-Field (Adresse): {a_field}")
        print(f"🔧 CI-Field: 0x{ci_field:02X}")
        
        # Extrahiere Datenbereich
        data_start = 7  # Nach CI-Field
        data_end = 6 + l_field - 1  # -1 für Checksum
        
        if data_end > data_start and data_end <= len(data):
            frame_data = data[data_start:data_end]
            print(f"📊 Daten ({len(frame_data)} bytes): {frame_data.hex().upper()}")
            
            # Parse die eigentlichen M-Bus Daten
            parse_mbus_data(frame_data)
            
            return {
                "frame_type": "variable_length",
                "length": l_field,
                "c_field": c_field,
                "address": a_field, 
                "ci_field": ci_field,
                "data": frame_data
            }
    
    return None

def parse_mbus_data(data):
    """Parst M-Bus Datenbereich (DIF/VIF Records)"""
    print(f"\n📈 M-Bus Daten-Analyse:")
    
    if len(data) < 8:
        print("❌ Datenbereich zu kurz für Analyse")
        return
    
    # M-Bus Identification Number (4 bytes, little endian)
    id_bytes = data[0:4]
    device_id = int.from_bytes(id_bytes, byteorder='little')
    print(f"🆔 Geräte-ID: {device_id} (0x{device_id:08X})")
    
    # Manufacturer (2 bytes)
    if len(data) >= 6:
        mfg_bytes = data[4:6]
        mfg_code = int.from_bytes(mfg_bytes, byteorder='little')
        manufacturer = decode_manufacturer(mfg_code)
        print(f"🏭 Hersteller: {manufacturer} (Code: 0x{mfg_code:04X})")
    
    # Version & Device Type
    if len(data) >= 8:
        version = data[6]
        device_type = data[7]
        print(f"📱 Version: {version}")
        print(f"🔧 Gerätetyp: {decode_device_type(device_type)} (0x{device_type:02X})")
    
    # Parse Data Records (DIF/VIF)
    if len(data) > 8:
        records_data = data[8:]
        print(f"\n📋 Datenrecords ({len(records_data)} bytes):")
        parse_data_records(records_data)

def decode_manufacturer(code):
    """Dekodiert Herstellercode"""
    if code == 0:
        return "Unbekannt"
    
    # M-Bus Herstellercode ist 3-stellig Base32
    # Häufige Codes:
    manufacturer_codes = {
        0x15B5: "Landis+Gyr",
        0x2C2D: "Kamstrup", 
        0x4024: "Sensus",
        0x4D26: "TCH",
        0x5B15: "Elster/Honeywell"
    }
    
    if code in manufacturer_codes:
        return manufacturer_codes[code]
    
    # Versuche Base32-Dekodierung
    try:
        c1 = chr(((code >> 10) & 0x1F) + ord('A') - 1)
        c2 = chr(((code >> 5) & 0x1F) + ord('A') - 1) 
        c3 = chr((code & 0x1F) + ord('A') - 1)
        return f"{c1}{c2}{c3}"
    except:
        return f"Code_{code:04X}"

def decode_device_type(device_type):
    """Dekodiert Gerätetyp"""
    device_types = {
        0x00: "Andere",
        0x01: "Öl", 
        0x02: "Elektrizität",
        0x03: "Gas",
        0x04: "Wärme (Outlet)",
        0x05: "Dampf",
        0x06: "Warmwasser",
        0x07: "Wasser",
        0x08: "Wärme Cost Allocator",
        0x09: "Compressed Air",
        0x0A: "Cooling (Outlet)",
        0x0B: "Cooling (Inlet)",
        0x0C: "Wärme (Inlet)",
        0x0D: "Wärme/Kälte",
        0x0E: "Bus/System",
        0x0F: "Unbekannt",
        0x15: "Hot Water",
        0x16: "Cold Water",
        0x17: "Dual Water",
        0x18: "Pressure",
        0x19: "A/D Converter"
    }
    
    return device_types.get(device_type, f"Unbekannt_{device_type:02X}")

def parse_data_records(data):
    """Parst M-Bus Data Records (vereinfacht)"""
    pos = 0
    record_num = 1
    
    while pos < len(data) - 1:
        if pos >= len(data):
            break
            
        print(f"\n📊 Record #{record_num}:")
        
        # DIF (Data Information Field)
        dif = data[pos]
        print(f"   DIF: 0x{dif:02X}")
        pos += 1
        
        # Prüfe auf Extension DIF
        while pos < len(data) and (data[pos-1] & 0x80):
            print(f"   DIF Extension: 0x{data[pos]:02X}")
            pos += 1
        
        if pos >= len(data):
            break
            
        # VIF (Value Information Field)  
        vif = data[pos]
        print(f"   VIF: 0x{vif:02X} - {decode_vif(vif)}")
        pos += 1
        
        # Prüfe auf Extension VIF
        while pos < len(data) and (data[pos-1] & 0x80):
            if pos < len(data):
                print(f"   VIF Extension: 0x{data[pos]:02X}")
                pos += 1
        
        # Datenbreite aus DIF extrahieren
        data_length = get_data_length(dif)
        
        if data_length > 0 and pos + data_length <= len(data):
            value_bytes = data[pos:pos + data_length]
            print(f"   Data ({data_length} bytes): {value_bytes.hex().upper()}")
            
            # Versuche Wert zu interpretieren
            if data_length <= 4:
                value = int.from_bytes(value_bytes, byteorder='little')
                print(f"   Wert: {value}")
            
            pos += data_length
        else:
            print(f"   Data: unbekannte Länge oder zu wenig Daten")
            pos += 1
        
        record_num += 1
        
        if record_num > 10:  # Verhindere Endlosschleife
            print("   ... (weitere Records)")
            break

def decode_vif(vif):
    """Dekodiert Value Information Field (vereinfacht)"""
    # Häufige VIF Codes
    vif_codes = {
        0x04: "Energy (Wh)",
        0x05: "Energy (10 Wh)", 
        0x06: "Energy (100 Wh)",
        0x07: "Energy (kWh)",
        0x08: "Energy (10 kWh)",
        0x2B: "Power (W)",
        0x2C: "Power (10 W)",
        0x2D: "Power (100 W)", 
        0x2E: "Power (kW)",
        0x6D: "Date/Time",
        0x24: "Volume (10^-2 m³)",
        0xFD: "Extension VIF"
    }
    
    return vif_codes.get(vif, f"VIF_{vif:02X}")

def get_data_length(dif):
    """Ermittelt Datenlänge aus DIF"""
    length_table = [0, 1, 2, 3, 4, 6, 8, 12]
    return length_table[dif & 0x07]

# Test mit den empfangenen Daten
if __name__ == "__main__":
    # Ihre empfangenen Daten
    frame_hex = "683D3D6808027228700400B5151002BC000000046D2009273A0403954B3A02040324864AFD042B0000000002FDC8FF01140903FD5900000002FF52F40101FD17008F16"
    
    parse_mbus_frame(frame_hex)