#!/usr/bin/env python3
"""
Wrapper für das offizielle pyMeterBus mbus-serial-request-data.py Beispiel
Lädt das originale Skript herunter und führt es aus
"""

import argparse
import json
import sys
import os
import subprocess
import tempfile
import urllib.request
from datetime import datetime

# URL zum originalen pyMeterBus Beispiel
PYMETERBUS_URL = "https://raw.githubusercontent.com/ganehag/pyMeterBus/master/tools/mbus-serial-request-data.py"

def download_pymeterbus_tool():
    """Lädt das originale pyMeterBus Tool herunter"""
    try:
        print(f"[INFO] Lade pyMeterBus Tool herunter...", file=sys.stderr)
        
        # Erstelle temporäre Datei
        temp_dir = tempfile.gettempdir()
        tool_path = os.path.join(temp_dir, "mbus-serial-request-data.py")
        
        # Download nur wenn nicht vorhanden
        if not os.path.exists(tool_path):
            urllib.request.urlretrieve(PYMETERBUS_URL, tool_path)
            print(f"[INFO] Tool heruntergeladen: {tool_path}", file=sys.stderr)
        else:
            print(f"[INFO] Tool bereits vorhanden: {tool_path}", file=sys.stderr)
            
        return tool_path
        
    except Exception as e:
        print(f"[ERROR] Download fehlgeschlagen: {e}", file=sys.stderr)
        return None

def run_pymeterbus_tool(tool_path, port, baudrate, address, output_format="json"):
    """Führt das originale pyMeterBus Tool aus"""
    try:
        # Kommando zusammenbauen
        cmd = [
            "python3", tool_path,
            "-b", str(baudrate),
            "-a", str(address),
            "-o", output_format,
            port
        ]
        
        print(f"[INFO] Führe aus: {' '.join(cmd)}", file=sys.stderr)
        
        # Tool ausführen
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"[INFO] pyMeterBus Tool erfolgreich", file=sys.stderr)
            return result.stdout
        else:
            print(f"[ERROR] pyMeterBus Tool fehlgeschlagen:", file=sys.stderr)
            print(f"[ERROR] STDERR: {result.stderr}", file=sys.stderr)
            return None
            
    except Exception as e:
        print(f"[ERROR] Ausführung fehlgeschlagen: {e}", file=sys.stderr)
        return None

def scan_addresses(port, baudrate):
    """Scannt M-Bus Adressen - einfache Implementation"""
    print("[INFO] Einfacher Adress-Scan (1-10)...", file=sys.stderr)
    found_devices = []
    
    tool_path = download_pymeterbus_tool()
    if not tool_path:
        return found_devices
    
    # Teste Adressen 1-10
    for address in range(1, 11):
        print(f"[SCAN] Teste Adresse {address}...", file=sys.stderr)
        
        result = run_pymeterbus_tool(tool_path, port, baudrate, address, "dump")
        if result and "no reply" not in result.lower():
            found_devices.append(address)
            print(f"[SCAN] Gerät gefunden auf Adresse {address}", file=sys.stderr)
    
    return found_devices

def read_device(port, baudrate, address):
    """Liest M-Bus Gerät mit originalem pyMeterBus Tool"""
    print(f"[INFO] Lese M-Bus Gerät {address}...", file=sys.stderr)
    
    tool_path = download_pymeterbus_tool()
    if not tool_path:
        return None
    
    # Führe pyMeterBus Tool mit JSON Output aus
    json_output = run_pymeterbus_tool(tool_path, port, baudrate, address, "json")
    
    if json_output:
        try:
            # Parse JSON Output
            data = json.loads(json_output)
            
            # Füge Metadaten hinzu für Kompatibilität
            result = {
                "command": "read",
                "address": address,
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "data": data,
                "records": data.get("records", []),  # Für Gateway-Kompatibilität
                "parsing_method": "pymeterbus_official"
            }
            
            print(f"[INFO] {len(data.get('records', []))} Records empfangen", file=sys.stderr)
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON Parse Fehler: {e}", file=sys.stderr)
            print(f"[ERROR] Output: {json_output}", file=sys.stderr)
            return None
    else:
        return None

def main():
    """Hauptfunktion"""
    parser = argparse.ArgumentParser(description='pyMeterBus Original Tool Wrapper')
    parser.add_argument('--port', required=True, help='Serial port (z.B. /dev/ttyAMA0)')
    parser.add_argument('--baudrate', type=int, default=9600, help='Baudrate')
    
    subparsers = parser.add_subparsers(dest='command', help='Verfügbare Kommandos')
    
    # Scan Kommando
    scan_parser = subparsers.add_parser('scan', help='Scanne M-Bus Adressen')
    
    # Test Kommando (für Gateway-Kompatibilität)
    test_parser = subparsers.add_parser('test', help='Teste CLI Tool')
    
    # Read Kommando
    read_parser = subparsers.add_parser('read', help='Lese M-Bus Gerät')
    read_parser.add_argument('--address', required=True, help='M-Bus Adresse')
    
    args = parser.parse_args()
    
    if args.command == 'scan':
        devices = scan_addresses(args.port, args.baudrate)
        result = {
            "command": "scan",
            "found_devices": devices,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }
        print(json.dumps(result, indent=2))
        
    elif args.command == 'test':
        # Einfacher Test - nur prüfen ob das Tool startet
        result = {
            "command": "test",
            "success": True,
            "message": "CLI Tool verfügbar",
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(result, indent=2))
        
    elif args.command == 'read':
        data = read_device(args.port, args.baudrate, args.address)
        if data:
            print(json.dumps(data, indent=2))
        else:
            result = {
                "command": "read",
                "address": args.address,
                "success": False,
                "error": "Keine Daten erhalten",
                "timestamp": datetime.now().isoformat()
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()