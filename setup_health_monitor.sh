#!/bin/bash
#
# Setup Script für MBus Gateway Health Monitor
# Installiert und konfiguriert automatisches Monitoring
#

set -e  # Exit bei Fehlern

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== MBus Gateway Health Monitor Setup ===${NC}"

# Prüfe ob als root ausgeführt
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Dieses Script muss als root ausgeführt werden (sudo)${NC}"
   exit 1
fi

# Pfade definieren
INSTALL_DIR="/opt/mbus-mqtt-gateway"
SERVICE_FILE="/etc/systemd/system/mbus-health-monitor.service"
MAIN_SERVICE="mbus-mqtt-gateway.service"

# Aktuellen User ermitteln (für den Service)
ACTUAL_USER=$(who am i | awk '{print $1}')
if [ -z "$ACTUAL_USER" ]; then
    ACTUAL_USER="root"  # Fallback
fi

echo -e "${YELLOW}Service wird als User '$ACTUAL_USER' ausgeführt${NC}"

echo -e "${YELLOW}Prüfe Installationsverzeichnis...${NC}"
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}Fehler: $INSTALL_DIR nicht gefunden!${NC}"
    exit 1
fi

echo -e "${YELLOW}Prüfe ob Haupt-Service existiert...${NC}"
if ! systemctl list-unit-files | grep -q "$MAIN_SERVICE"; then
    echo -e "${RED}Fehler: $MAIN_SERVICE nicht installiert!${NC}"
    exit 1
fi

echo -e "${YELLOW}Kopiere Health Monitor Dateien...${NC}"
cp "$INSTALL_DIR/health_monitor.py" "$INSTALL_DIR/health_monitor.py" 2>/dev/null || echo "health_monitor.py bereits vorhanden"
chmod +x "$INSTALL_DIR/health_monitor.py"

echo -e "${YELLOW}Erstelle systemd Service...${NC}"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=MBus Gateway Health Monitor
After=mbus-mqtt-gateway.service
Wants=mbus-mqtt-gateway.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python health_monitor.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Kill hanging python processes
KillMode=control-group
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Lade systemd Konfiguration neu...${NC}"
systemctl daemon-reload

echo -e "${YELLOW}Aktiviere Health Monitor Service...${NC}"
systemctl enable mbus-health-monitor.service

echo -e "${YELLOW}Starte Health Monitor...${NC}"
systemctl start mbus-health-monitor.service

# Warte kurz und prüfe Status
sleep 3

echo -e "${YELLOW}Prüfe Service Status...${NC}"
if systemctl is-active --quiet mbus-health-monitor.service; then
    echo -e "${GREEN}✓ Health Monitor läuft erfolgreich${NC}"
else
    echo -e "${RED}✗ Health Monitor konnte nicht gestartet werden${NC}"
    systemctl status mbus-health-monitor.service
    exit 1
fi

echo -e "${BLUE}=== Installation abgeschlossen ===${NC}"
echo ""
echo -e "${GREEN}Health Monitor wurde erfolgreich installiert!${NC}"
echo ""
echo "Nützliche Befehle:"
echo "  Status prüfen:     sudo systemctl status mbus-health-monitor.service"
echo "  Logs anzeigen:     sudo journalctl -u mbus-health-monitor.service -f"
echo "  Neustart:          sudo systemctl restart mbus-health-monitor.service"
echo "  Deaktivieren:      sudo systemctl disable mbus-health-monitor.service"
echo ""

echo -e "${YELLOW}Zeige aktuelle Logs (letzte 20 Zeilen):${NC}"
journalctl -u mbus-health-monitor.service -n 20 --no-pager

echo ""
echo -e "${BLUE}Setup abgeschlossen! Health Monitor überwacht jetzt automatisch den MBus Service.${NC}"
