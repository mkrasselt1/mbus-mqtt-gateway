#!/bin/bash
################################################################################
# M-Bus MQTT Gateway - Linux Service Manager
# Verwaltet den systemd Service
################################################################################

set -e

SERVICE_NAME="mbus-gateway"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/mbus-gateway"
USER="mbus"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}"
    echo "============================================================"
    echo "  M-Bus MQTT Gateway - Service Manager"
    echo "============================================================"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "Dieses Script muss als root ausgeführt werden"
        echo "Verwenden Sie: sudo $0 $1"
        exit 1
    fi
}

install_service() {
    print_header
    echo "Installation des Services..."
    echo
    
    check_root
    
    # 1. Prüfe Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 nicht gefunden!"
        exit 1
    fi
    print_success "Python3 gefunden: $(python3 --version)"
    
    # 2. Erstelle Benutzer falls nicht vorhanden
    if ! id "$USER" &> /dev/null; then
        useradd -r -s /bin/false -d "$INSTALL_DIR" "$USER"
        print_success "Benutzer '$USER' erstellt"
    else
        print_info "Benutzer '$USER' existiert bereits"
    fi
    
    # 3. Erstelle Verzeichnisse
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/logs"
    mkdir -p "$INSTALL_DIR/app"
    print_success "Verzeichnisse erstellt"
    
    # 4. Kopiere Dateien
    cp -r "$SCRIPT_DIR"/*.py "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR"/app/* "$INSTALL_DIR/app/" 2>/dev/null || true
    cp "$SCRIPT_DIR/config.json" "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
    print_success "Dateien kopiert"
    
    # 5. Installiere Dependencies
    print_info "Installiere Python-Abhängigkeiten..."
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        pip3 install -r "$INSTALL_DIR/requirements.txt" > /dev/null 2>&1 || \
            print_warning "Einige Dependencies konnten nicht installiert werden"
        print_success "Dependencies installiert"
    fi
    
    # 6. Setze Berechtigungen
    chown -R "$USER:$USER" "$INSTALL_DIR"
    chmod +x "$INSTALL_DIR"/*.py
    print_success "Berechtigungen gesetzt"
    
    # 7. Erstelle systemd Service
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=M-Bus MQTT Gateway
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONIOENCODING=utf-8"
ExecStart=/usr/bin/python3 $INSTALL_DIR/run_service.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mbus-gateway

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/logs

[Install]
WantedBy=multi-user.target
EOF
    print_success "Service-Datei erstellt: $SERVICE_FILE"
    
    # 8. Systemd neu laden
    systemctl daemon-reload
    print_success "Systemd neu geladen"
    
    # 9. Service aktivieren
    systemctl enable "$SERVICE_NAME"
    print_success "Service aktiviert (startet automatisch beim Booten)"
    
    echo
    print_success "Installation abgeschlossen!"
    echo
    print_info "Nächste Schritte:"
    echo "  • Service starten:  sudo systemctl start $SERVICE_NAME"
    echo "  • Status prüfen:    sudo systemctl status $SERVICE_NAME"
    echo "  • Logs anzeigen:    sudo journalctl -u $SERVICE_NAME -f"
    echo
}

start_service() {
    check_root
    print_info "Starte Service..."
    systemctl start "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service läuft"
        status_service
    else
        print_error "Service konnte nicht gestartet werden"
        echo
        echo "Letzte Log-Einträge:"
        journalctl -u "$SERVICE_NAME" -n 20 --no-pager
        exit 1
    fi
}

stop_service() {
    check_root
    print_info "Stoppe Service..."
    systemctl stop "$SERVICE_NAME"
    sleep 1
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service gestoppt"
    else
        print_error "Service konnte nicht gestoppt werden"
        exit 1
    fi
}

restart_service() {
    check_root
    print_info "Starte Service neu..."
    systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service neu gestartet"
        status_service
    else
        print_error "Service konnte nicht neu gestartet werden"
        exit 1
    fi
}

status_service() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  SERVICE STATUS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    systemctl status "$SERVICE_NAME" --no-pager || true
    
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  LETZTE LOG-EINTRÄGE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    journalctl -u "$SERVICE_NAME" -n 15 --no-pager
    
    echo
    echo "Für Live-Logs: sudo journalctl -u $SERVICE_NAME -f"
}

logs_service() {
    echo "Zeige Live-Logs (Strg+C zum Beenden)..."
    echo
    journalctl -u "$SERVICE_NAME" -f
}

uninstall_service() {
    print_header
    echo "Deinstallation des Services..."
    echo
    
    check_root
    
    # 1. Service stoppen
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        print_success "Service gestoppt"
    fi
    
    # 2. Service deaktivieren
    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl disable "$SERVICE_NAME"
        print_success "Service deaktiviert"
    fi
    
    # 3. Service-Datei entfernen
    if [ -f "$SERVICE_FILE" ]; then
        rm "$SERVICE_FILE"
        print_success "Service-Datei entfernt"
    fi
    
    # 4. Systemd neu laden
    systemctl daemon-reload
    print_success "Systemd neu geladen"
    
    # 5. Dateien entfernen (optional)
    read -p "Installation in $INSTALL_DIR löschen? (j/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[JjYy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        print_success "Dateien gelöscht"
    else
        print_info "Dateien beibehalten in: $INSTALL_DIR"
    fi
    
    # 6. Benutzer entfernen (optional)
    read -p "Benutzer '$USER' löschen? (j/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[JjYy]$ ]]; then
        userdel "$USER"
        print_success "Benutzer gelöscht"
    else
        print_info "Benutzer beibehalten: $USER"
    fi
    
    echo
    print_success "Deinstallation abgeschlossen!"
}

show_help() {
    print_header
    echo "Verwendung: $0 <BEFEHL>"
    echo
    echo "Befehle:"
    echo "  install     Installiert den Service"
    echo "  start       Startet den Service"
    echo "  stop        Stoppt den Service"
    echo "  restart     Startet den Service neu"
    echo "  status      Zeigt Service-Status und Logs"
    echo "  logs        Zeigt Live-Logs"
    echo "  uninstall   Deinstalliert den Service"
    echo "  help        Zeigt diese Hilfe"
    echo
    echo "Beispiele:"
    echo "  sudo $0 install"
    echo "  sudo $0 start"
    echo "  sudo $0 status"
    echo "  sudo $0 logs"
    echo
}

# Main
case "${1:-}" in
    install)
        install_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    logs)
        logs_service
        ;;
    uninstall)
        uninstall_service
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unbekannter Befehl: $1"
        echo
        show_help
        exit 1
        ;;
esac
