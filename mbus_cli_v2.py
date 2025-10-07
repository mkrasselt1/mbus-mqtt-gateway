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


def convert_to_json_safe(value):
    """Konvertiert Werte zu JSON-sicheren Typen mit Plausibilitätsprüfung"""
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            float_value = float(value)
            # Plausibilitätsprüfung für Energy/Power Messwerte
            if float_value > 1_000_000:  # > 1 Million
                print(f"[WARNING] Unplausibler Wert {float_value} - möglicherweise falsche Skalierung", file=sys.stderr)
                # Versuche verschiedene Skalierungen
                if float_value > 1_000_000_000:  # > 1 Milliarde
                    scaled = float_value / 1_000_000  # Divide by million
                    print(f"[WARNING] Skaliere Wert {float_value} -> {scaled} (÷1,000,000)", file=sys.stderr)
                    return scaled
                elif float_value > 1_000_000:  # > 1 Million
                    scaled = float_value / 1_000  # Divide by thousand
                    print(f"[WARNING] Skaliere Wert {float_value} -> {scaled} (÷1,000)", file=sys.stderr)
                    return scaled
            return float_value
        elif isinstance(value, (int, float)):
            # Plausibilitätsprüfung für numerische Werte
            if value > 1_000_000:  # > 1 Million
                print(f"[WARNING] Unplausibler Wert {value} - möglicherweise falsche Skalierung", file=sys.stderr)
                if value > 1_000_000_000:  # > 1 Milliarde
                    scaled = value / 1_000_000  # Divide by million
                    print(f"[WARNING] Skaliere Wert {value} -> {scaled} (÷1,000,000)", file=sys.stderr)
                    return scaled
                elif value > 1_000_000:  # > 1 Million
                    scaled = value / 1_000  # Divide by thousand
                    print(f"[WARNING] Skaliere Wert {value} -> {scaled} (÷1,000)", file=sys.stderr)
                    return scaled
            return value
        elif hasattr(value, '__dict__'):
            return str(value)
        return value
    except:
        return str(value) if value is not None else None


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
        """Liest Daten von M-Bus Gerät mit robustem Raw-Parsing"""
        print(f"[INFO] Lese M-Bus Daten von {address_or_id}", file=sys.stderr)
        
        read_start = time.time()
        
        try:
            with serial.Serial(self.port, self.baudrate, parity='E', stopbits=1, timeout=2.0) as ser:
                
                if isinstance(address_or_id, str) and len(address_or_id) >= 16:
                    # Sekundäradresse - SELECT Frame senden
                    print(f"[DEBUG] Verwende Sekundäradresse: {address_or_id}", file=sys.stderr)
                    
                    try:
                        meterbus.send_select_frame(ser, address_or_id, False)
                        time.sleep(0.1)
                        
                        # Nach Selektion REQ_UD2 an ADDRESS_NETWORK_LAYER
                        meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, False)
                    except:
                        # Fallback: Raw SELECT Frame
                        self._send_raw_select_frame(ser, address_or_id)
                        self._send_raw_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER)
                    
                else:
                    # Primäradresse - direkt REQ_UD2
                    address = int(address_or_id) if isinstance(address_or_id, str) else address_or_id
                    print(f"[DEBUG] Verwende Primäradresse: {address}", file=sys.stderr)
                    
                    # SND_NKE (Normalisierung) zuerst
                    self._send_raw_nke_frame(ser, address)
                    time.sleep(0.1)
                    
                    # REQ_UD2 (Daten anfordern)
                    self._send_raw_request_frame(ser, address)
                
                time.sleep(0.5)
                
                # Raw Response lesen
                available = ser.in_waiting
                if available > 0:
                    raw_response = ser.read(available)
                    print(f"[DEBUG] Raw Response: {len(raw_response)} bytes", file=sys.stderr)
                    
                    # Entferne führendes ACK (0xE5) falls vorhanden
                    if len(raw_response) > 0 and raw_response[0] == 0xE5:
                        print("[DEBUG] ACK am Anfang erkannt, entferne es", file=sys.stderr)
                        frame_data = raw_response[1:]
                    else:
                        frame_data = raw_response
                    
                    # Versuche zuerst meterbus Library
                    meterbus_result = None
                    try:
                        # Simuliere meterbus recv_frame
                        if len(frame_data) > 6:
                            frame = meterbus.load(frame_data)
                            if isinstance(frame, meterbus.TelegramLong):
                                meterbus_result = self._extract_meterbus_data(frame)
                                print("[DEBUG] meterbus Library Parsing erfolgreich", file=sys.stderr)
                    except Exception as e:
                        print(f"[DEBUG] meterbus Library fehlgeschlagen: {e}", file=sys.stderr)
                    
                    # Fallback: Manueller Parser
                    manual_result = self._parse_raw_mbus_frame(frame_data)
                    if manual_result:
                        print("[DEBUG] Manueller Parser erfolgreich", file=sys.stderr)
                    
                    # Kombiniere Ergebnisse
                    result = {
                        "success": True,
                        "address": address_or_id,
                        "raw_response_hex": raw_response.hex().upper(),
                        "raw_response_length": len(raw_response),
                        "frame_data_hex": frame_data.hex().upper(),
                        "frame_data_length": len(frame_data),
                        "read_duration_seconds": round(time.time() - read_start, 3),
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    if meterbus_result:
                        result["meterbus_data"] = meterbus_result
                        print("[DEBUG] meterbus Daten hinzugefügt", file=sys.stderr)
                    
                    if manual_result:
                        result.update(manual_result)
                        print("[DEBUG] Manuelle Parser-Daten hinzugefügt", file=sys.stderr)
                    
                    return result
                else:
                    return {
                        "success": False,
                        "error": "Keine Antwort vom Gerät",
                        "address": address_or_id,
                        "read_duration_seconds": round(time.time() - read_start, 3)
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "address": address_or_id,
                "read_duration_seconds": round(time.time() - read_start, 3)
            }
    
    def _send_raw_nke_frame(self, ser, address):
        """Sendet SND_NKE Frame (Raw)"""
        checksum = (0x40 + address) % 256
        frame = bytes([0x10, 0x40, address, checksum, 0x16])
        ser.write(frame)
    
    def _send_raw_request_frame(self, ser, address):
        """Sendet REQ_UD2 Frame (Raw)"""
        checksum = (0x5B + address) % 256
        frame = bytes([0x10, 0x5B, address, checksum, 0x16])
        ser.write(frame)
    
    def _send_raw_select_frame(self, ser, secondary_address):
        """Sendet SELECT Frame (Raw)"""
        try:
            frame_data = bytes.fromhex(secondary_address)
            if len(frame_data) == 8:
                header = bytes([0x68, 0x0B, 0x0B, 0x68, 0x53, 0xFD, 0x52])
                checksum = sum(header[4:] + frame_data) % 256
                frame = header + frame_data + bytes([checksum, 0x16])
                ser.write(frame)
        except:
            pass
    
    def _extract_meterbus_data(self, frame):
        """Extrahiert Daten aus meterbus TelegramLong"""
        try:
            data_records = []
            
            for record in frame.records:
                record_data = {
                    "value": convert_to_json_safe(getattr(record, 'parsed_value', None)),
                    "unit": getattr(record, 'unit', None),
                    "function_field": getattr(record, 'function_field', None),
                    "storage_number": getattr(record, 'storage_number', None),
                    "tariff": getattr(record, 'tariff', None),
                    "device_type": getattr(record, 'device_type', None),
                }
                data_records.append(record_data)
            
            return {
                "manufacturer": getattr(frame, 'manufacturer', None),
                "identification": convert_to_json_safe(getattr(frame, 'identification', None)),
                "version": getattr(frame, 'version', None),
                "device_type": getattr(frame, 'device_type', None),
                "records": data_records,
                "record_count": len(data_records)
            }
        except Exception as e:
            print(f"[DEBUG] meterbus data extraction error: {e}", file=sys.stderr)
            return None
    
    def _parse_raw_mbus_frame(self, data):
        """Parst M-Bus Frame manuell (integriert aus mbus_frame_parser.py)"""
        try:
            if len(data) < 6 or data[0] != 0x68:
                return None
            
            l_field = data[1]
            c_field = data[4]
            a_field = data[5]
            ci_field = data[6] if len(data) > 6 else 0
            
            # Extrahiere Datenbereich
            data_start = 7
            data_end = 6 + l_field - 1
            
            if data_end > data_start and data_end <= len(data):
                frame_data = data[data_start:data_end]
                
                # Parse M-Bus Identifikation
                device_info = self._parse_mbus_identification(frame_data)
                
                # Parse Data Records
                records = self._parse_mbus_records(frame_data[8:] if len(frame_data) > 8 else b'')
                
                return {
                    "frame_type": "variable_length",
                    "address": a_field,
                    "ci_field": f"0x{ci_field:02X}",
                    "device_id": device_info.get("device_id"),
                    "manufacturer": device_info.get("manufacturer"),
                    "version": device_info.get("version"),
                    "device_type": device_info.get("device_type"),
                    "device_type_name": device_info.get("device_type_name"),
                    "records": records,
                    "record_count": len(records)
                }
        except Exception as e:
            print(f"[DEBUG] Manual parsing error: {e}", file=sys.stderr)
            return None
    
    def _parse_mbus_identification(self, data):
        """Parst M-Bus Identifikationsbereich"""
        try:
            if len(data) < 8:
                return {}
            
            # Device ID (4 bytes, little endian)
            device_id = int.from_bytes(data[0:4], byteorder='little')
            
            # Manufacturer (2 bytes)
            mfg_code = int.from_bytes(data[4:6], byteorder='little')
            manufacturer = self._decode_manufacturer(mfg_code)
            
            # Version & Device Type
            version = data[6]
            device_type = data[7]
            device_type_name = self._decode_device_type(device_type)
            
            return {
                "device_id": device_id,
                "manufacturer": manufacturer,
                "manufacturer_code": f"0x{mfg_code:04X}",
                "version": version,
                "device_type": device_type,
                "device_type_name": device_type_name
            }
        except:
            return {}
    
    def _parse_mbus_records(self, data):
        """Parst M-Bus Data Records"""
        records = []
        pos = 0
        
        try:
            while pos < len(data) - 1:
                if pos >= len(data):
                    break
                
                record = {}
                
                # DIF
                dif = data[pos]
                record["dif"] = f"0x{dif:02X}"
                pos += 1
                
                # Skip DIF extensions
                while pos < len(data) and (data[pos-1] & 0x80):
                    pos += 1
                
                if pos >= len(data):
                    break
                
                # VIF
                vif = data[pos]
                record["vif"] = f"0x{vif:02X}"
                record["vif_description"] = self._decode_vif(vif)
                pos += 1
                
                # Skip VIF extensions
                while pos < len(data) and (data[pos-1] & 0x80):
                    if pos < len(data):
                        pos += 1
                
                # Data
                data_length = self._get_data_length(dif)
                if data_length > 0 and pos + data_length <= len(data):
                    value_bytes = data[pos:pos + data_length]
                    record["raw_data"] = value_bytes.hex().upper()
                    
                    if data_length <= 4:
                        raw_value = int.from_bytes(value_bytes, byteorder='little')
                        
                        # VIF-basierte Skalierung anwenden
                        scaled_value, unit = self._apply_vif_scaling(raw_value, vif)
                        record["value"] = scaled_value
                        record["unit"] = unit
                        record["raw_value"] = raw_value  # Für Debug-Zwecke
                        
                        # Zusätzliche Plausibilitätsprüfung
                        if scaled_value > 100_000:  # Sehr hoher Wert
                            print(f"[WARNING] Sehr hoher Wert nach VIF-Skalierung: {scaled_value} (Raw: {raw_value}, VIF: 0x{vif:02X})", file=sys.stderr)
                    
                    pos += data_length
                else:
                    pos += 1
                
                records.append(record)
                
                if len(records) > 20:  # Sicherheit
                    break
                    
        except Exception as e:
            print(f"[DEBUG] Record parsing error: {e}", file=sys.stderr)
        
        return records
    
    def _decode_manufacturer(self, code):
        """Dekodiert Herstellercode"""
        manufacturer_codes = {
            0x15B5: "Landis+Gyr",
            0x2C2D: "Kamstrup", 
            0x4024: "Sensus",
            0x4D26: "TCH",
            0x5B15: "Elster/Honeywell"
        }
        
        if code in manufacturer_codes:
            return manufacturer_codes[code]
        
        try:
            c1 = chr(((code >> 10) & 0x1F) + ord('A') - 1)
            c2 = chr(((code >> 5) & 0x1F) + ord('A') - 1) 
            c3 = chr((code & 0x1F) + ord('A') - 1)
            return f"{c1}{c2}{c3}"
        except:
            return f"Code_{code:04X}"
    
    def _decode_device_type(self, device_type):
        """Dekodiert Gerätetyp"""
        device_types = {
            0x02: "Elektrizität",
            0x03: "Gas", 
            0x04: "Wärme (Outlet)",
            0x06: "Warmwasser",
            0x07: "Wasser",
            0x16: "Cold Water",
            0x17: "Dual Water"
        }
        return device_types.get(device_type, f"Typ_{device_type:02X}")
    
    def _apply_vif_scaling(self, raw_value, vif):
        """Wendet VIF-basierte Skalierung auf Rohwerte an - Korrekte M-Bus Implementation"""
        try:
            # M-Bus VIF-basierte Skalierung nach EN 13757-3
            # Wichtig: Viele M-Bus Geräte senden bereits skalierte Werte!
            
            if vif >= 0x00 and vif <= 0x07:  # Energy Wh (E000 0nnn)
                # 0x00-0x07: Energy in Wh * 10^(nnn-3)
                # Aber oft sind die Rohwerte bereits in 0.01 oder 0.001 Wh!
                exponent = (vif & 0x07) - 3  # -3 bis +4
                
                # Heuristik: Wenn der Wert sehr groß ist, ist er wahrscheinlich bereits in kleineren Einheiten
                if raw_value > 100_000_000:  # > 100 Millionen
                    # Vermutlich in 0.001 Wh Einheiten
                    scaled = raw_value * 0.001  # Zu Wh
                    unit = "Wh" if scaled < 1000 else "kWh"
                    if scaled >= 1000:
                        scaled /= 1000
                    print(f"[VIF] Energy große Zahl (0.001 Wh): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                elif raw_value > 1_000_000:  # > 1 Million
                    # Vermutlich in 0.01 Wh Einheiten  
                    scaled = raw_value * 0.01  # Zu Wh
                    unit = "Wh" if scaled < 1000 else "kWh"
                    if scaled >= 1000:
                        scaled /= 1000
                    print(f"[VIF] Energy mittlere Zahl (0.01 Wh): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                else:
                    # Standard VIF-Skalierung
                    factor = 10 ** exponent
                    scaled = raw_value * factor
                    unit = "Wh" if scaled < 1000 else "kWh"
                    if scaled >= 1000:
                        scaled /= 1000
                    print(f"[VIF] Energy Standard VIF 0x{vif:02X}: {raw_value} * 10^{exponent} -> {scaled} {unit}", file=sys.stderr)
                
                return scaled, unit
                
            elif vif >= 0x28 and vif <= 0x2F:  # Power W (E010 1nnn)
                # 0x28-0x2F: Power in W * 10^(nnn-3)
                exponent = (vif & 0x07) - 3  # -3 bis +4
                
                # Heuristik für Leistungswerte
                if raw_value > 100_000:  # > 100k
                    # Vermutlich in 0.01 W Einheiten
                    scaled = raw_value * 0.01
                    unit = "W" if scaled < 1000 else "kW"
                    if scaled >= 1000:
                        scaled /= 1000
                    print(f"[VIF] Power (0.01 W): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                else:
                    # Standard VIF-Skalierung
                    factor = 10 ** exponent
                    scaled = raw_value * factor
                    unit = "W" if scaled < 1000 else "kW"
                    if scaled >= 1000:
                        scaled /= 1000
                    print(f"[VIF] Power Standard VIF 0x{vif:02X}: {raw_value} * 10^{exponent} -> {scaled} {unit}", file=sys.stderr)
                
                return scaled, unit
                
            elif vif >= 0x48 and vif <= 0x4F:  # Voltage V (E100 1nnn)
                # 0x48-0x4F: Voltage in V * 10^(nnn-3)
                exponent = (vif & 0x07) - 3  # -3 bis +4
                
                # Spannungswerte sind oft in 0.1 V oder 0.01 V
                if raw_value > 10_000:  # > 10k
                    # Vermutlich in 0.01 V Einheiten
                    scaled = raw_value * 0.01
                    print(f"[VIF] Voltage (0.01 V): {raw_value} -> {scaled} V", file=sys.stderr)
                elif raw_value > 1_000:  # > 1k
                    # Vermutlich in 0.1 V Einheiten (typisch für EU 230V)
                    scaled = raw_value * 0.1
                    print(f"[VIF] Voltage (0.1 V): {raw_value} -> {scaled} V", file=sys.stderr)
                else:
                    # Standard VIF-Skalierung
                    factor = 10 ** exponent
                    scaled = raw_value * factor
                    print(f"[VIF] Voltage Standard VIF 0x{vif:02X}: {raw_value} * 10^{exponent} -> {scaled} V", file=sys.stderr)
                
                return scaled, "V"
                
            elif vif >= 0x50 and vif <= 0x57:  # Current A (E101 0nnn)
                # 0x50-0x57: Current in A * 10^(nnn-3) 
                exponent = (vif & 0x07) - 3  # -3 bis +4
                
                # Stromwerte sind oft in 0.01 A oder 0.001 A
                if raw_value > 10_000:  # > 10k
                    # Vermutlich in 0.001 A Einheiten (mA)
                    scaled = raw_value * 0.001
                    print(f"[VIF] Current (0.001 A): {raw_value} -> {scaled} A", file=sys.stderr)
                elif raw_value > 1_000:  # > 1k
                    # Vermutlich in 0.01 A Einheiten
                    scaled = raw_value * 0.01
                    print(f"[VIF] Current (0.01 A): {raw_value} -> {scaled} A", file=sys.stderr)
                else:
                    # Standard VIF-Skalierung
                    factor = 10 ** exponent
                    scaled = raw_value * factor
                    print(f"[VIF] Current Standard VIF 0x{vif:02X}: {raw_value} * 10^{exponent} -> {scaled} A", file=sys.stderr)
                
                return scaled, "A"
                
            else:
                # Unbekannter VIF - verwende intelligente Heuristik
                print(f"[VIF] Unbekannter VIF 0x{vif:02X}, verwende Heuristik", file=sys.stderr)
                
                # Basierend auf typischen Wertebereichen
                if raw_value > 100_000_000:  # > 100M -> Energy in 0.001 Wh
                    scaled = raw_value * 0.001 / 1000  # Zu kWh
                    unit = "kWh"
                    print(f"[VIF] Heuristik Energy (0.001 Wh): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                elif raw_value > 1_000_000:  # > 1M -> Energy in 0.01 Wh oder Power in 0.01 W
                    if 10_000_000 <= raw_value <= 50_000_000:  # Energy range
                        scaled = raw_value * 0.01 / 1000  # Zu kWh
                        unit = "kWh"
                        print(f"[VIF] Heuristik Energy (0.01 Wh): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                    else:  # Power range
                        scaled = raw_value * 0.01  # Zu W
                        unit = "W" if scaled < 1000 else "kW"
                        if scaled >= 1000:
                            scaled /= 1000
                        print(f"[VIF] Heuristik Power (0.01 W): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                elif 1_000 <= raw_value <= 10_000:  # Voltage range (0.1 V)
                    scaled = raw_value * 0.1
                    unit = "V"
                    print(f"[VIF] Heuristik Voltage (0.1 V): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                elif 100 <= raw_value <= 5_000:  # Current range (0.01 A)
                    scaled = raw_value * 0.01
                    unit = "A"
                    print(f"[VIF] Heuristik Current (0.01 A): {raw_value} -> {scaled} {unit}", file=sys.stderr)
                else:
                    scaled = raw_value
                    unit = ""
                    print(f"[VIF] Heuristik: Keine Skalierung für {raw_value}", file=sys.stderr)
                
                return scaled, unit
                
        except Exception as e:
            print(f"[ERROR] VIF-Skalierung fehlgeschlagen für VIF 0x{vif:02X}, Wert {raw_value}: {e}", file=sys.stderr)
            return raw_value, ""
    
    def _decode_vif(self, vif):
        """Dekodiert Value Information Field"""
        vif_codes = {
            0x04: "Energy (Wh)",
            0x07: "Energy (kWh)",
            0x2B: "Power (W)",
            0x2E: "Power (kW)",
            0x6D: "Date/Time",
            0x24: "Volume (10^-2 m³)",
            0xFD: "Extension VIF"
        }
        return vif_codes.get(vif, f"VIF_{vif:02X}")
    
    def _get_data_length(self, dif):
        """Ermittelt Datenlänge aus DIF"""
        length_table = [0, 1, 2, 3, 4, 6, 8, 12]
        return length_table[dif & 0x07]


def json_serializer(obj):
    """JSON Serializer für komplexe Objekte"""
    try:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            return str(obj)
        return str(obj)
    except:
        return str(obj)


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
        
        # JSON Ausgabe mit Decimal-Unterstützung
        if result:
            print(json.dumps(result, ensure_ascii=False, default=json_serializer))
        
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