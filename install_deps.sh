#!/bin/bash
#
# Install dependencies via system packages (Debian/Ubuntu/Raspberry Pi OS)
# This avoids pip and uses apt instead
#

set -e

echo "=========================================="
echo "Installing M-Bus Gateway Dependencies"
echo "Via System Packages (apt)"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./install_deps.sh"
    exit 1
fi

echo ""
echo "Updating package list..."
apt-get update

echo ""
echo "Installing Python dependencies..."

# Core Python packages
apt-get install -y \
    python3-pip \
    python3-full \
    python3-serial \
    python3-yaml \
    python3-paho-mqtt \
    python3-aiohttp \
    python3-aiofiles

echo ""
echo "Installing additional dependencies via pip (in system)..."
# Some packages don't have apt equivalents, install with --break-system-packages
pip3 install --break-system-packages \
    python-meterbus \
    pydantic \
    pydantic-settings \
    structlog \
    aiosqlite \
    tenacity \
    prometheus-client

echo ""
echo "=========================================="
echo "✅ Dependencies installed successfully!"
echo "=========================================="
echo ""
echo "Installed packages:"
python3 -c "
import sys
packages = [
    'serial',
    'yaml', 
    'paho.mqtt.client',
    'aiohttp',
    'meterbus',
    'pydantic',
    'structlog',
    'aiosqlite'
]
for pkg in packages:
    try:
        __import__(pkg)
        print(f'  ✓ {pkg}')
    except ImportError:
        print(f'  ✗ {pkg} (missing)')
"

echo ""
echo "Next: Run installation script"
echo "  sudo ./install.sh"
