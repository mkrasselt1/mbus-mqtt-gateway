#!/bin/bash
#
# Migration script from old to new M-Bus Gateway
# Run as root: sudo ./migrate.sh
#

set -e

echo "=========================================="
echo "M-Bus Gateway Migration (v1 -> v2)"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo ./migrate.sh)"
    exit 1
fi

OLD_SERVICE="mbus-mqtt-gateway.service"
NEW_SERVICE="mbus-gateway.service"
OLD_CONFIG="config.json"
NEW_CONFIG_DIR="/etc/mbus-gateway"

echo ""
echo "[1/7] Checking old installation..."

if systemctl is-active --quiet $OLD_SERVICE; then
    echo "  ✓ Found running old service"
    OLD_RUNNING=true
else
    echo "  ℹ Old service not running"
    OLD_RUNNING=false
fi

if [ -f "$OLD_CONFIG" ]; then
    echo "  ✓ Found old configuration"
    OLD_CONFIG_EXISTS=true
else
    echo "  ⚠ Old configuration not found"
    OLD_CONFIG_EXISTS=false
fi

echo ""
echo "[2/7] Backing up old configuration..."
if [ "$OLD_CONFIG_EXISTS" = true ]; then
    cp $OLD_CONFIG ${OLD_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)
    echo "  ✓ Backup created"
else
    echo "  ℹ Nothing to backup"
fi

echo ""
echo "[3/7] Stopping old service..."
if [ "$OLD_RUNNING" = true ]; then
    systemctl stop $OLD_SERVICE
    echo "  ✓ Old service stopped"
else
    echo "  ℹ Nothing to stop"
fi

echo ""
echo "[4/7] Installing new version..."
./install.sh

echo ""
echo "[5/7] Migrating configuration..."
if [ "$OLD_CONFIG_EXISTS" = true ] && [ ! -f "$NEW_CONFIG_DIR/config.yaml" ]; then
    cp $OLD_CONFIG $NEW_CONFIG_DIR/
    echo "  ✓ Configuration migrated"
    echo "  ℹ Will be auto-converted on first start"
else
    echo "  ℹ Using existing configuration"
fi

echo ""
echo "[6/7] Starting new service..."
systemctl start $NEW_SERVICE
sleep 5

if systemctl is-active --quiet $NEW_SERVICE; then
    echo "  ✓ New service started successfully"
else
    echo "  ✗ Service failed to start"
    echo "  Check logs: sudo journalctl -u $NEW_SERVICE -n 50"
    exit 1
fi

echo ""
echo "[7/7] Cleanup..."
read -p "Disable old service? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    systemctl disable $OLD_SERVICE 2>/dev/null || true
    echo "  ✓ Old service disabled"
else
    echo "  ℹ Old service kept (can be manually removed later)"
fi

echo ""
echo "=========================================="
echo "Migration completed successfully!"
echo "=========================================="
echo ""
echo "Status:"
echo "  New service:   systemctl status $NEW_SERVICE"
echo "  Logs:          journalctl -u $NEW_SERVICE -f"
echo "  Health check:  curl http://localhost:8080/health"
echo "  Configuration: $NEW_CONFIG_DIR/config.yaml"
echo ""
echo "Old service can be completely removed with:"
echo "  sudo systemctl disable $OLD_SERVICE"
echo "  sudo rm /etc/systemd/system/$OLD_SERVICE"
echo ""
