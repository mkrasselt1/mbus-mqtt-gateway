#!/usr/bin/env python3
"""
Configuration validator and converter
Validates config.yaml or converts config.json to new format.
"""

import sys
import json
from pathlib import Path

try:
    from src.config import load_config, Config
    print("✓ Imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    print("\nPlease install dependencies:")
    print("  pip3 install -r requirements-new.txt")
    sys.exit(1)


def validate_config(config_path: str) -> bool:
    """Validate configuration file."""
    try:
        print(f"\n📄 Loading configuration: {config_path}")
        config = load_config(config_path)
        
        print("✓ Configuration loaded successfully\n")
        
        # Display key settings
        print("📊 Configuration Summary:")
        print(f"  MQTT Broker:    {config.mqtt.broker}:{config.mqtt.port}")
        print(f"  M-Bus Port:     {config.mbus.port}")
        print(f"  M-Bus Baudrate: {config.mbus.baudrate}")
        print(f"  Read Interval:  {config.mbus.read_interval}s")
        print(f"  Scan Interval:  {config.mbus.scan_interval}s")
        print(f"  Log Level:      {config.logging.level}")
        print(f"  Health Port:    {config.monitoring.http_port}")
        print(f"  Database:       {config.persistence.database}")
        
        print("\n✅ Configuration is valid!")
        return True
        
    except FileNotFoundError as e:
        print(f"✗ Configuration file not found: {e}")
        return False
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def convert_legacy_config(json_path: str, output_path: str) -> bool:
    """Convert legacy config.json to new config.yaml."""
    try:
        print(f"\n🔄 Converting {json_path} to {output_path}")
        
        config = Config.load_from_legacy_json(json_path)
        config.save_to_file(output_path)
        
        print(f"✓ Converted successfully to {output_path}")
        print("\nPlease review the generated config.yaml and adjust as needed.")
        return True
        
    except Exception as e:
        print(f"✗ Conversion failed: {e}")
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Validate:  python3 validate_config.py config.yaml")
        print("  Convert:   python3 validate_config.py config.json config.yaml")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    # Convert mode
    if len(sys.argv) == 3:
        output_path = sys.argv[2]
        success = convert_legacy_config(input_path, output_path)
    
    # Validate mode
    else:
        success = validate_config(input_path)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
