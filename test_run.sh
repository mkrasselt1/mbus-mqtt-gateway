#!/bin/bash
#
# Test-Script für M-Bus Gateway v2
# Führt das Gateway im Vordergrund aus (zum Testen)
#

set -e

# Wechsle ins Projektverzeichnis
cd "$(dirname "$0")"

echo "=========================================="
echo "M-Bus Gateway v2 - Test Mode"
echo "=========================================="
echo ""

# Prüfe Python-Umgebung
if [ -f "venv/bin/python3" ]; then
    PYTHON="./venv/bin/python3"
    echo "Using venv: $PYTHON"
elif [ -f ".venv/bin/python3" ]; then
    PYTHON="./.venv/bin/python3"
    echo "Using .venv: $PYTHON"
else
    PYTHON="python3"
    echo "Using system python: $PYTHON"
fi

# Prüfe Config
if [ -f "config.yaml" ]; then
    CONFIG="config.yaml"
    echo "Using config: $CONFIG"
elif [ -f "/etc/mbus-gateway/config.yaml" ]; then
    CONFIG="/etc/mbus-gateway/config.yaml"
    echo "Using config: $CONFIG"
else
    echo "ERROR: No config.yaml found!"
    echo "Create one first or specify path as argument"
    exit 1
fi

# Zeige Config-Zusammenfassung
echo ""
echo "Configuration Summary:"
$PYTHON -c "
import sys
sys.path.insert(0, 'src')
from config import load_config

try:
    config = load_config('$CONFIG')
    print(f'  MQTT Broker:    {config.mqtt.broker}:{config.mqtt.port}')
    print(f'  MQTT User:      {config.mqtt.username or \"(none)\"}')
    print(f'  MQTT Topic:     {config.mqtt.topic_prefix}')
    print(f'  M-Bus Port:     {config.mbus.port}')
    print(f'  M-Bus Baudrate: {config.mbus.baudrate}')
    print(f'  Read Interval:  {config.mbus.read_interval}s')
    print(f'  Log Level:      {config.logging.level}')
except Exception as e:
    print(f'  ERROR: {e}')
    sys.exit(1)
"

echo ""
echo "=========================================="
echo "Starting Gateway..."
echo "Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Starte Gateway im Vordergrund
exec $PYTHON -m src.main "$CONFIG"
