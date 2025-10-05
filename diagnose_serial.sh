#!/bin/bash
#
# M-Bus Serial Port Diagnose
# Prüft ob der Serial Port funktioniert
#

echo "=========================================="
echo "M-Bus Serial Port Diagnose"
echo "=========================================="
echo ""

PORT="/dev/ttyAMA0"
BAUDRATE=9600

echo "Port: $PORT"
echo "Baudrate: $BAUDRATE"
echo ""

# 1. Prüfe ob Port existiert
echo "[1/6] Checking if port exists..."
if [ -e "$PORT" ]; then
    echo "  ✓ Port exists"
    ls -l "$PORT"
else
    echo "  ✗ Port does not exist!"
    echo "  Available ports:"
    ls -l /dev/tty* | grep -E "(USB|AMA|ACM)"
    exit 1
fi

# 2. Prüfe Berechtigungen
echo ""
echo "[2/6] Checking permissions..."
if [ -r "$PORT" ] && [ -w "$PORT" ]; then
    echo "  ✓ Port is readable and writable"
else
    echo "  ✗ No read/write permission!"
    echo "  Fix with: sudo chmod 666 $PORT"
    echo "  Or add user to dialout group: sudo usermod -a -G dialout $USER"
fi

# 3. Prüfe ob Port belegt ist
echo ""
echo "[3/6] Checking if port is in use..."
if lsof "$PORT" 2>/dev/null; then
    echo "  ⚠ Port is currently in use!"
else
    echo "  ✓ Port is free"
fi

# 4. Prüfe UART Konfiguration (nur für ttyAMA0)
if [[ "$PORT" == *"ttyAMA0"* ]]; then
    echo ""
    echo "[4/6] Checking UART configuration..."
    
    # Prüfe /boot/config.txt
    if grep -q "enable_uart=1" /boot/firmware/config.txt 2>/dev/null || \
       grep -q "enable_uart=1" /boot/config.txt 2>/dev/null; then
        echo "  ✓ UART is enabled in config.txt"
    else
        echo "  ⚠ UART might not be enabled!"
        echo "  Add to /boot/firmware/config.txt:"
        echo "    enable_uart=1"
        echo "    dtoverlay=disable-bt"
    fi
    
    # Prüfe ob Bluetooth den UART blockiert
    if systemctl is-active --quiet hciuart 2>/dev/null; then
        echo "  ⚠ Bluetooth UART service is running (might conflict)"
        echo "  Disable with: sudo systemctl disable hciuart"
    else
        echo "  ✓ Bluetooth UART is not running"
    fi
fi

# 5. Teste Serial Kommunikation
echo ""
echo "[5/6] Testing serial communication..."

# Einfacher Read-Test
if command -v timeout &> /dev/null; then
    echo "  Reading from port for 2 seconds..."
    if timeout 2 cat "$PORT" 2>/dev/null | od -An -tx1 | head -5; then
        echo "  ✓ Can read from port (data shown above if any)"
    else
        echo "  ⚠ Read test completed (no data received in 2s - might be normal)"
    fi
else
    echo "  (skipping - timeout command not available)"
fi

# 6. Python Serial Test
echo ""
echo "[6/6] Testing with Python pyserial..."
python3 << 'PYEOF'
import serial
import sys

try:
    ser = serial.Serial(
        port="/dev/ttyAMA0",
        baudrate=9600,
        bytesize=8,
        parity='E',  # Even parity for M-Bus
        stopbits=1,
        timeout=2
    )
    print(f"  ✓ Port opened successfully")
    print(f"    Baudrate: {ser.baudrate}")
    print(f"    Parity: {ser.parity}")
    print(f"    Timeout: {ser.timeout}s")
    
    # Versuche kurz zu lesen
    ser.read(10)
    print(f"  ✓ Read test successful")
    
    ser.close()
    print(f"  ✓ Port closed successfully")
    
except serial.SerialException as e:
    print(f"  ✗ Serial error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)
PYEOF

echo ""
echo "=========================================="
echo "Diagnose complete!"
echo "=========================================="
echo ""
echo "If M-Bus devices are not found:"
echo "  1. Check physical wiring"
echo "  2. Verify M-Bus master is powered"
echo "  3. Check baudrate matches your devices"
echo "  4. Try: sudo python3 mbus-serial-request-data.py"
echo ""
