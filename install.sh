#!/bin/bash
#
# Installation script for M-Bus MQTT Gateway
# Run as root: sudo ./install.sh
#

set -e

echo "=========================================="
echo "M-Bus MQTT Gateway Installation"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo ./install.sh)"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/mbus-gateway"
CONFIG_DIR="/etc/mbus-gateway"
DATA_DIR="/var/lib/mbus-gateway"
LOG_DIR="/var/log/mbus-gateway"
SERVICE_FILE="/etc/systemd/system/mbus-gateway.service"
USER="mbus"
GROUP="mbus"

echo ""
echo "[1/8] Creating system user and group..."
if ! id -u $USER > /dev/null 2>&1; then
    useradd -r -s /bin/false -d $INSTALL_DIR -c "M-Bus Gateway Service" $USER
    echo "  ✓ User '$USER' created"
else
    echo "  ℹ User '$USER' already exists"
fi

echo ""
echo "[2/8] Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $CONFIG_DIR
mkdir -p $DATA_DIR
mkdir -p $LOG_DIR

echo "  ✓ Directories created"

echo ""
echo "[3/8] Installing Python dependencies..."

# Check if we should use system packages or pip
if [ -f "install_deps.sh" ]; then
    echo "  Using install_deps.sh for dependency installation..."
    chmod +x install_deps.sh
    ./install_deps.sh
else
    # Fallback: Try pip with break-system-packages
    echo "  Installing via pip (with --break-system-packages)..."
    pip3 install -r requirements-new.txt --upgrade --break-system-packages
fi

echo "  ✓ Dependencies installed"

echo ""
echo "[4/8] Copying application files..."
cp -r src $INSTALL_DIR/
cp mbus-gateway.service $SERVICE_FILE

echo "  ✓ Files copied"

echo ""
echo "[5/8] Setting up configuration..."
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    if [ -f "config.yaml" ]; then
        cp config.yaml $CONFIG_DIR/
        echo "  ✓ Configuration copied"
    elif [ -f "config.json" ]; then
        echo "  ℹ Found legacy config.json - will be auto-converted on first run"
        cp config.json $CONFIG_DIR/
    else
        echo "  ⚠ No configuration found - please create $CONFIG_DIR/config.yaml"
    fi
else
    echo "  ℹ Configuration already exists - keeping current"
fi

echo ""
echo "[6/8] Setting permissions..."
chown -R $USER:$GROUP $INSTALL_DIR
chown -R $USER:$GROUP $DATA_DIR
chown -R $USER:$GROUP $LOG_DIR
chown -R root:root $CONFIG_DIR
chmod 755 $CONFIG_DIR
chmod 644 $CONFIG_DIR/*.yaml 2>/dev/null || true
chmod 644 $CONFIG_DIR/*.json 2>/dev/null || true

# Add user to dialout group for serial port access
usermod -a -G dialout $USER

echo "  ✓ Permissions set"

echo ""
echo "[7/8] Enabling systemd service..."
systemctl daemon-reload
systemctl enable mbus-gateway.service

echo "  ✓ Service enabled"

echo ""
echo "[8/8] Configuration check..."
if [ -f "$CONFIG_DIR/config.yaml" ] || [ -f "$CONFIG_DIR/config.json" ]; then
    echo "  ✓ Configuration found"
    
    echo ""
    echo "=========================================="
    echo "Installation completed successfully!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "  1. Edit configuration: sudo nano $CONFIG_DIR/config.yaml"
    echo "  2. Start service:      sudo systemctl start mbus-gateway"
    echo "  3. Check status:       sudo systemctl status mbus-gateway"
    echo "  4. View logs:          sudo journalctl -u mbus-gateway -f"
    echo "  5. Health check:       curl http://localhost:8080/health"
    echo ""
else
    echo "  ⚠ No configuration found!"
    echo ""
    echo "=========================================="
    echo "Installation completed with warnings"
    echo "=========================================="
    echo ""
    echo "Please create configuration:"
    echo "  1. Copy template:      sudo cp config.yaml $CONFIG_DIR/"
    echo "  2. Edit configuration: sudo nano $CONFIG_DIR/config.yaml"
    echo "  3. Start service:      sudo systemctl start mbus-gateway"
    echo ""
fi

exit 0
