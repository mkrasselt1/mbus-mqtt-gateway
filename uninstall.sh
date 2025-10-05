#!/bin/bash
#
# Uninstall script for M-Bus MQTT Gateway
# Run as root: sudo ./uninstall.sh
#

set -e

echo "=========================================="
echo "M-Bus MQTT Gateway Uninstallation"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo ./uninstall.sh)"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/mbus-gateway"
CONFIG_DIR="/etc/mbus-gateway"
DATA_DIR="/var/lib/mbus-gateway"
LOG_DIR="/var/log/mbus-gateway"
SERVICE_FILE="/etc/systemd/system/mbus-gateway.service"
USER="mbus"

echo ""
read -p "Remove configuration and data? (y/N): " -n 1 -r
echo
REMOVE_DATA=$REPLY

echo ""
echo "[1/5] Stopping service..."
systemctl stop mbus-gateway.service 2>/dev/null || true
systemctl disable mbus-gateway.service 2>/dev/null || true
echo "  ✓ Service stopped"

echo ""
echo "[2/5] Removing service file..."
rm -f $SERVICE_FILE
systemctl daemon-reload
echo "  ✓ Service file removed"

echo ""
echo "[3/5] Removing application files..."
rm -rf $INSTALL_DIR
echo "  ✓ Application files removed"

if [[ $REMOVE_DATA =~ ^[Yy]$ ]]; then
    echo ""
    echo "[4/5] Removing data and configuration..."
    rm -rf $CONFIG_DIR
    rm -rf $DATA_DIR
    rm -rf $LOG_DIR
    echo "  ✓ Data and configuration removed"
else
    echo ""
    echo "[4/5] Keeping data and configuration..."
    echo "  ℹ Config: $CONFIG_DIR"
    echo "  ℹ Data: $DATA_DIR"
    echo "  ℹ Logs: $LOG_DIR"
fi

echo ""
echo "[5/5] Removing system user..."
if id -u $USER > /dev/null 2>&1; then
    userdel $USER 2>/dev/null || true
    echo "  ✓ User removed"
else
    echo "  ℹ User already removed"
fi

echo ""
echo "=========================================="
echo "Uninstallation completed!"
echo "=========================================="

if [[ ! $REMOVE_DATA =~ ^[Yy]$ ]]; then
    echo ""
    echo "To remove remaining data manually:"
    echo "  sudo rm -rf $CONFIG_DIR"
    echo "  sudo rm -rf $DATA_DIR"
    echo "  sudo rm -rf $LOG_DIR"
fi

echo ""
