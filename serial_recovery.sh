#!/bin/bash
# Serial Port Recovery Script
# Führt komplette Serial Port Wiederherstellung durch

echo "=== SERIAL PORT RECOVERY SCRIPT ==="
echo "Timestamp: $(date)"

# 1. Service stoppen
echo "1. Stoppe M-Bus Service..."
sudo systemctl stop mbus-mqtt-gateway.service
sleep 2

# 2. Alle Prozesse die den Port verwenden beenden
echo "2. Beende Prozesse auf /dev/ttyAMA0..."
sudo fuser -k /dev/ttyAMA0 2>/dev/null || echo "   Keine Prozesse zu beenden"
sleep 2

# 3. Port Permissions prüfen
echo "3. Prüfe Port Permissions..."
ls -la /dev/ttyAMA0
if [ ! -c /dev/ttyAMA0 ]; then
    echo "   ❌ Port /dev/ttyAMA0 nicht verfügbar!"
else
    echo "   ✅ Port verfügbar"
fi

# 4. Kernel Module reload (falls USB-Serial)
echo "4. USB-Serial Module Check..."
lsmod | grep -E "(usbserial|cp210x|ftdi)" && {
    echo "   USB-Serial Module gefunden - Reload..."
    sudo modprobe -r cp210x 2>/dev/null || true
    sudo modprobe -r ftdi_sio 2>/dev/null || true
    sleep 1
    sudo modprobe cp210x 2>/dev/null || true
    sudo modprobe ftdi_sio 2>/dev/null || true
    sleep 2
} || echo "   Keine USB-Serial Module"

# 5. GPIO Serial Reset (für Raspberry Pi)
echo "5. GPIO Serial Reset..."
if [ -f /boot/config.txt ]; then
    echo "   Raspberry Pi erkannt - GPIO Serial Check"
    # Hier könnte GPIO Reset implementiert werden
fi

# 6. Warten für Stabilisierung
echo "6. Warte 10 Sekunden für Stabilisierung..."
sleep 10

# 7. Port Test
echo "7. Port Funktionstest..."
python3 -c "
import serial
try:
    ser = serial.Serial('/dev/ttyAMA0', 2400, timeout=1)
    print('   ✅ Port Test erfolgreich')
    ser.close()
except Exception as e:
    print(f'   ❌ Port Test fehlgeschlagen: {e}')
"

# 8. Service neu starten
echo "8. Starte M-Bus Service..."
sudo systemctl start mbus-mqtt-gateway.service
sleep 3

# 9. Status prüfen
echo "9. Service Status:"
sudo systemctl status mbus-mqtt-gateway.service --no-pager

echo ""
echo "=== RECOVERY ABGESCHLOSSEN ==="
echo "Überwache Logs mit: sudo journalctl -u mbus-mqtt-gateway.service -f"
