#!/usr/bin/env python3
"""
Simple Config Converter: config.json → config.yaml
Requires only standard library (no external dependencies)
"""

import json
import sys
from pathlib import Path


def json_to_yaml_simple(data, indent=0):
    """Convert Python dict to YAML string (simple implementation)."""
    yaml_lines = []
    indent_str = "  " * indent
    
    for key, value in data.items():
        if isinstance(value, dict):
            yaml_lines.append(f"{indent_str}{key}:")
            yaml_lines.append(json_to_yaml_simple(value, indent + 1))
        elif isinstance(value, list):
            yaml_lines.append(f"{indent_str}{key}:")
            for item in value:
                if isinstance(item, dict):
                    yaml_lines.append(f"{indent_str}  -")
                    yaml_lines.append(json_to_yaml_simple(item, indent + 2))
                else:
                    yaml_lines.append(f"{indent_str}  - {item}")
        elif isinstance(value, str):
            # Quote strings that might need it
            if value and (' ' in value or value.lower() in ['true', 'false', 'null']):
                yaml_lines.append(f'{indent_str}{key}: "{value}"')
            else:
                yaml_lines.append(f"{indent_str}{key}: {value}")
        elif isinstance(value, bool):
            yaml_lines.append(f"{indent_str}{key}: {str(value).lower()}")
        elif value is None:
            yaml_lines.append(f"{indent_str}{key}:")
        else:
            yaml_lines.append(f"{indent_str}{key}: {value}")
    
    return "\n".join(yaml_lines)


def convert_config(json_path: str, yaml_path: str):
    """Convert config.json to config.yaml with proper structure."""
    
    print(f"📄 Reading {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        legacy_data = json.load(f)
    
    print(f"   Found settings:")
    for key, value in legacy_data.items():
        print(f"   - {key}: {value}")
    
    # Convert to new structure
    print(f"\n🔄 Converting to new format...")
    
    new_config = {
        "mqtt": {
            "broker": legacy_data.get("mqtt_broker", "localhost"),
            "port": legacy_data.get("mqtt_port", 1883),
            "username": legacy_data.get("mqtt_username", ""),
            "password": legacy_data.get("mqtt_password", ""),
            "topic_prefix": legacy_data.get("mqtt_topic", "homeassistant"),
            "qos": 1,
            "keepalive": 60
        },
        "mbus": {
            "port": legacy_data.get("mbus_port", "/dev/ttyUSB0"),
            "baudrate": legacy_data.get("mbus_baudrate", 9600),
            "timeout": 5.0,
            "scan_interval": legacy_data.get("mbus_scan_interval_minutes", 60) * 60,  # to seconds
            "read_interval": 15,
            "max_retries": 3,
            "retry_delay": 2.0
        },
        "homeassistant": {
            "discovery_prefix": "homeassistant",
            "bridge_state_topic": "mbus/bridge/state",
            "availability": {
                "expire_after": 300,
                "heartbeat_interval": 60
            }
        },
        "persistence": {
            "database": "/var/lib/mbus-gateway/state.db",
            "enable_recovery": True,
            "history_days": 7,
            "max_queue_size": 10000,
            "cleanup_interval": 86400
        },
        "monitoring": {
            "enable_http": True,
            "http_port": 8080,
            "enable_metrics": True,
            "metrics_path": "/metrics",
            "enable_watchdog": True,
            "watchdog_interval": 30
        },
        "logging": {
            "level": "INFO",
            "format": "text",
            "file": "/var/log/mbus-gateway/gateway.log",
            "max_size_mb": 50,
            "backup_count": 5,
            "error_file": "/var/log/mbus-gateway/error.log"
        },
        "gateway": {
            "name": "M-Bus Gateway",
            "manufacturer": "Custom",
            "model": "M-Bus MQTT Gateway v2",
            "version": "2.0.0"
        },
        "advanced": {
            "circuit_breaker": {
                "enabled": True,
                "failure_threshold": 5,
                "timeout": 300
            },
            "worker_threads": 4,
            "graceful_shutdown_timeout": 30,
            "memory_limit_mb": 256
        }
    }
    
    print(f"✅ Converted successfully!")
    print(f"\n💾 Writing {yaml_path}...")
    
    # Write YAML
    with open(yaml_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("# M-Bus MQTT Gateway Configuration\n")
        f.write("# Converted from config.json\n")
        f.write(f"# Generated: {Path(json_path).stat().st_mtime}\n\n")
        
        # Write YAML
        yaml_content = json_to_yaml_simple(new_config)
        f.write(yaml_content)
    
    print(f"✅ Successfully created {yaml_path}")
    print(f"\n📝 Important changes:")
    print(f"   - scan_interval: {legacy_data.get('mbus_scan_interval_minutes', 60)} min → {new_config['mbus']['scan_interval']} seconds")
    print(f"   - read_interval: NEW → {new_config['mbus']['read_interval']} seconds (devices read every 15s)")
    print(f"   - expire_after: NEW → {new_config['homeassistant']['availability']['expire_after']}s (was causing 'unavailable')")
    print(f"   - persistence: NEW → SQLite database enabled")
    print(f"   - monitoring: NEW → Health check on port {new_config['monitoring']['http_port']}")
    
    print(f"\n⚠️  Please review and adjust:")
    print(f"   - MQTT broker IP: {new_config['mqtt']['broker']}")
    print(f"   - M-Bus port: {new_config['mbus']['port']}")
    print(f"   - Baudrate: {new_config['mbus']['baudrate']}")
    print(f"\n✅ Config conversion complete!")


def main():
    if len(sys.argv) != 3:
        print("Usage: python convert_config.py config.json config.yaml")
        print("\nExample:")
        print("  python convert_config.py config.json config-new.yaml")
        sys.exit(1)
    
    json_path = sys.argv[1]
    yaml_path = sys.argv[2]
    
    if not Path(json_path).exists():
        print(f"❌ Error: {json_path} not found!")
        sys.exit(1)
    
    if Path(yaml_path).exists():
        response = input(f"⚠️  {yaml_path} already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)
    
    try:
        convert_config(json_path, yaml_path)
    except Exception as e:
        print(f"\n❌ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
