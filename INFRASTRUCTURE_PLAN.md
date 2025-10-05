# M-Bus MQTT Gateway - Infrastruktur-Plan für maximale Zuverlässigkeit

## 🎯 Zielsetzung
Ein hochverfügbares, produktionsreifes M-Bus zu MQTT Gateway für Home Assistant mit:
- **99.9% Uptime** (max. 8.76h Ausfall/Jahr)
- **Automatische Fehlerbehandlung** ohne manuelle Eingriffe
- **Datenintegrität** - keine verlorenen Messwerte
- **Schnelle Recovery** bei Fehlern (< 60 Sekunden)

---

## 🏗️ Architektur-Überblick

```
┌─────────────────────────────────────────────────────────┐
│                   Systemd Service Layer                  │
│  • Auto-Restart bei Crash                                │
│  • Resource Limits (Memory, CPU)                         │
│  • Watchdog Integration                                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Application Layer (Python)                  │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐       │
│  │  M-Bus     │→ │  Device    │→ │    MQTT     │       │
│  │  Handler   │  │  Manager   │  │   Handler   │       │
│  └────────────┘  └────────────┘  └─────────────┘       │
│         ↓               ↓                ↓              │
│  ┌────────────────────────────────────────────┐        │
│  │        State Persistence Layer             │        │
│  │  (SQLite / JSON für Offline-Pufferung)    │        │
│  └────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                 Monitoring & Recovery                    │
│  • Health Checks (alle 30s)                             │
│  • Metrics Export (Prometheus/InfluxDB optional)        │
│  • Automatic Recovery Strategies                        │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Module & Komponenten

### 1. **M-Bus Handler** (mbus_handler.py)
**Verantwortlichkeiten:**
- M-Bus Geräte scannen & auslesen
- Serial Port Management mit Timeouts
- Retry-Logik bei Kommunikationsfehlern
- Heartbeat für Health Monitoring

**Verbesserungen:**
```python
✅ Timeout für jeden Serial Read (max. 5s)
✅ Connection Pool für Serial Ports
✅ Exponential Backoff bei Fehlern
✅ Circuit Breaker Pattern (nach 5 Fehlern → Pause)
✅ Separate Worker Threads pro Gerät
✅ Graceful Degradation (einzelnes Gerät offline ≠ Gateway offline)
```

### 2. **Device Manager** (device_manager.py)
**Verantwortlichkeiten:**
- Zentrale Device Registry
- State Management mit Versionierung
- Change Detection (nur bei Änderungen publizieren)
- Offline/Online Tracking

**Verbesserungen:**
```python
✅ SQLite für State Persistence
✅ Atomic State Updates (keine Race Conditions)
✅ TTL-basierte Offline-Erkennung (statt manuell)
✅ Event-basierte Architektur (Observer Pattern)
✅ State Snapshots für Recovery
```

### 3. **MQTT Handler** (mqtt_handler.py)
**Verantwortlichkeiten:**
- Robuste MQTT-Verbindung mit Auto-Reconnect
- Home Assistant Discovery Management
- Queueing bei Verbindungsverlust
- Retained Messages Management

**Verbesserungen:**
```python
✅ Asynchrone MQTT mit Offline-Queue
✅ Discovery-State in Datenbank persistieren
✅ Separate Threads für Discovery & State Updates
✅ Exponential Backoff für Reconnect
✅ Health-Check via MQTT (für externe Monitoring)
✅ LWT (Last Will Testament) pro Device
```

### 4. **State Persistence Layer** (state_persistence.py)
**Neu - bisher fehlend!**

**Verantwortlichkeiten:**
- Lokale Datenpufferung bei MQTT-Ausfall
- Recovery nach Gateway-Neustart
- Change History (optional, für Debugging)

**Implementation:**
```python
✅ SQLite für Zuverlässigkeit
✅ WAL-Modus für Performance
✅ Automatic Cleanup alter Einträge
✅ Export-Funktion für Backup
```

### 5. **Health Monitor** (health_monitor.py)
**Verantwortlichkeiten:**
- Überwachung aller Komponenten
- Automatische Recovery-Aktionen
- Systemd Watchdog Integration
- Metrics Collection

**Verbesserungen:**
```python
✅ Komponentenweise Health Checks
✅ Graduated Recovery (Soft → Hard → Restart)
✅ Deadlock Detection
✅ Memory Leak Detection
✅ Systemd Watchdog Ping (sd_notify)
```

---

## 🔧 Technische Implementierung

### Phase 1: Stabilisierung (Woche 1)
**Ziel:** Beseitigung kritischer Bugs

1. **MQTT Availability verbessern**
   - `expire_after: 300` (statt 180)
   - Heartbeat alle 60s (statt 90s)
   - Separate LWT Topics pro Device

2. **Serial Port Robustheit**
   - Timeouts auf alle Serial Operations
   - Port Lock File (`/var/lock/LCK..ttyUSB0`)
   - Automatic Port Re-enumeration

3. **Threading Fixes**
   - `threading.Event` für sauberes Shutdown
   - Join mit Timeout für alle Threads
   - Exception Handler in allen Threads

4. **Error Handling**
   - Try-Except um alle MQTT Publishes
   - Logging mit Rotation (max 50MB)
   - Stack Traces in separates Error Log

### Phase 2: Persistence Layer (Woche 2)
**Ziel:** Datenverlust bei Neustarts verhindern

1. **SQLite State Database**
   ```sql
   CREATE TABLE device_states (
       device_id TEXT PRIMARY KEY,
       state_json TEXT NOT NULL,
       last_update REAL NOT NULL,
       online BOOLEAN DEFAULT 1
   );
   
   CREATE TABLE mqtt_queue (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       topic TEXT NOT NULL,
       payload TEXT NOT NULL,
       retain BOOLEAN DEFAULT 0,
       created_at REAL NOT NULL
   );
   ```

2. **State Recovery on Startup**
   - Lade letzten bekannten State aus DB
   - Publiziere als "stale" mit Timestamp
   - Warte auf frische Daten vom M-Bus

3. **Offline Queue**
   - Bei MQTT Disconnect: Queue in DB
   - Bei Reconnect: Arbeite Queue ab (FIFO)
   - Max. Queue Size: 10.000 Messages

### Phase 3: Monitoring & Observability (Woche 3)
**Ziel:** Proaktive Fehlererkennung

1. **Health Endpoints**
   ```python
   # HTTP Server auf :8080
   GET /health          → {"status": "healthy", "components": {...}}
   GET /metrics         → Prometheus Format
   GET /state           → Current State Snapshot
   POST /trigger-scan   → Manuelles Scannen
   ```

2. **Metrics**
   - `mbus_reads_total{device="X"}` - Counter
   - `mbus_read_duration_seconds{device="X"}` - Histogram
   - `mbus_errors_total{device="X", type="timeout"}` - Counter
   - `mqtt_publish_total{result="success|failure"}` - Counter
   - `mqtt_queue_size` - Gauge

3. **Alerting** (optional)
   - E-Mail bei kritischen Fehlern
   - Pushover/Telegram Benachrichtigung
   - Home Assistant Notifications

### Phase 4: Erweiterte Features (Woche 4)
**Ziel:** Enterprise-Grade Betrieb

1. **Configuration Management**
   - YAML statt JSON (besser lesbar)
   - Hot-Reload bei Config-Änderungen
   - Schema Validation (Pydantic)

2. **Remote Management**
   - MQTT Command Topics
   - Web UI für Konfiguration
   - Firmware Update Mechanismus

3. **High Availability** (optional)
   - Zweites Gateway im Standby
   - Shared State via Redis/etcd
   - Automatic Failover

---

## 🚨 Kritische Konfigurationsparameter

### M-Bus Timing
```python
SERIAL_TIMEOUT = 5.0          # Max. 5s pro Read
RETRY_DELAY = 2.0             # 2s Pause zwischen Retries
MAX_RETRIES = 3               # 3 Versuche pro Device
SCAN_INTERVAL = 15            # Alle 15s lesen (aktuell)
DEVICE_OFFLINE_TIMEOUT = 90   # Nach 90s ohne Antwort → offline
```

### MQTT Reliability
```python
MQTT_KEEPALIVE = 60           # MQTT Keepalive
MQTT_RECONNECT_DELAY = 5      # Initialer Reconnect Delay
MQTT_MAX_RECONNECT = 300      # Max. 5 Min Delay
EXPIRE_AFTER = 300            # HA zeigt "unavailable" nach 5 Min
HEARTBEAT_INTERVAL = 60       # State Refresh alle 60s
QOS = 1                       # At-least-once delivery
```

### Resource Limits
```ini
[Service]
MemoryMax=256M                # Max. 256MB RAM
CPUQuota=50%                  # Max. 50% CPU
Restart=always                # Immer neustarten
RestartSec=10s                # 10s Pause vor Neustart
WatchdogSec=120s              # Watchdog Timeout
```

---

## 📊 Monitoring Dashboard (Home Assistant Lovelace)

```yaml
type: vertical-stack
cards:
  - type: entity
    entity: binary_sensor.mbus_gateway_status
    name: Gateway Status
  
  - type: entities
    title: M-Bus Geräte
    entities:
      - sensor.mbus_meter_1_energie_bezug
      - sensor.mbus_meter_1_wirkleistung
      - binary_sensor.mbus_meter_1_status
  
  - type: history-graph
    title: Leistung (24h)
    entities:
      - sensor.mbus_meter_1_wirkleistung
    hours_to_show: 24
  
  - type: custom:mini-graph-card
    name: Gateway Uptime
    entities:
      - sensor.mbus_gateway_uptime
    hours_to_show: 168  # 7 Tage
```

---

## 🔍 Debugging & Troubleshooting

### Log-Levels
```python
DEBUG   → Alle M-Bus Kommunikation, MQTT Messages
INFO    → State Changes, Discovery, Scans
WARNING → Timeouts, Retries, Offline Devices
ERROR   → Fatale Fehler, Exceptions
```

### Wichtige Log-Dateien
```
/var/log/mbus-gateway/main.log         # Haupt-Log (rotierend)
/var/log/mbus-gateway/error.log        # Nur Errors
/var/log/mbus-gateway/mbus_comm.log    # M-Bus Kommunikation
/tmp/mbus_heartbeat.txt                # Liveness File
```

### Häufige Probleme

| Problem | Ursache | Lösung |
|---------|---------|--------|
| "Nicht verfügbar" in HA | MQTT State nicht rechtzeitig erneuert | Heartbeat-Interval verringern |
| Serial Timeouts | Falscher Baudrate / defektes Kabel | Baudrate prüfen, Kabel tauschen |
| Hoher CPU-Verbrauch | Zu häufiges Scannen | SCAN_INTERVAL erhöhen |
| Memory Leaks | Nicht geschlossene Serial Ports | `with` Statement nutzen |
| Discovery nicht sichtbar | MQTT Broker Neustart | Force Rediscovery auslösen |

---

## 🎯 Success Metrics

### KPIs für Produktionsbetrieb
- **Uptime:** > 99.9% (< 8.76h Ausfall/Jahr)
- **Data Loss Rate:** < 0.01% (max. 1 von 10.000 Readings)
- **Recovery Time:** < 60s nach Fehler
- **MQTT Latency:** < 500ms (Sensor → HA)
- **False Offline Rate:** < 0.1% (False Positives)

### Acceptance Criteria
✅ Gateway überlebt Netzwerkausfall (5 Min)
✅ Gateway überlebt MQTT Broker Neustart
✅ Gateway überlebt M-Bus Device Ausfall
✅ Alle Daten persistent bei Neustart
✅ Home Assistant zeigt keine "unavailable" (außer echten Ausfällen)
✅ Automatic Recovery ohne manuellen Eingriff
✅ Logs zeigen < 1% Error Rate

---

## 📝 Implementierungs-Roadmap

### Sprint 1 (Woche 1) - Kritische Fixes
- [ ] MQTT Expire After auf 300s erhöhen
- [ ] Serial Timeouts implementieren
- [ ] Threading Shutdown verbessern
- [ ] Exception Handling überall
- [ ] Log Rotation einrichten

### Sprint 2 (Woche 2) - Persistence
- [ ] SQLite State Database
- [ ] State Recovery on Startup
- [ ] MQTT Offline Queue
- [ ] Atomic State Updates

### Sprint 3 (Woche 3) - Monitoring
- [ ] Health Check Endpoint
- [ ] Prometheus Metrics
- [ ] Systemd Watchdog Integration
- [ ] Dashboard in Home Assistant

### Sprint 4 (Woche 4) - Optimization
- [ ] Configuration Hot-Reload
- [ ] Performance Optimierung
- [ ] Dokumentation
- [ ] Integration Tests

---

## 🚀 Quick Wins (Sofort umsetzbar)

Diese Änderungen verbessern die Stabilität **sofort**:

1. **MQTT Expire After erhöhen:**
   ```python
   config["expire_after"] = 300  # statt 180
   ```

2. **Heartbeat häufiger:**
   ```python
   time.sleep(60)  # statt 90
   ```

3. **Serial Timeout:**
   ```python
   with serial_for_url(self.port, self.baudrate, timeout=5) as ser:
   ```

4. **State Topics ALLE retained:**
   ```python
   self.publish(state_topic, payload, retain=True)  # Überall!
   ```

5. **Bridge State häufiger:**
   ```python
   if uptime_seconds % 60 == 0:  # Jede Minute
       self.mqtt_client.publish("mbus/bridge/state", "online", retain=True)
   ```

---

## 💡 Best Practices

### Allgemein
- **Fail Fast, Recover Gracefully** - Fehler schnell erkennen, langsam erholen
- **Idempotent Operations** - Mehrfaches Ausführen = gleiches Ergebnis
- **Defensive Programming** - Erwarte das Unerwartete
- **Observable Systems** - Logging, Metrics, Tracing

### M-Bus spezifisch
- **Nie blockieren** - Timeouts überall
- **Einzelgerät-Fehler isolieren** - Ein Fehler ≠ Totalausfall
- **Scan-Interval anpassen** - Je nach Datenänderungsrate

### MQTT spezifisch
- **Retained Messages nutzen** - Wichtig für HA Neustart
- **QoS 1 für State** - At-least-once Delivery
- **Separate Topics** - Nicht alles in ein JSON

---

## 📚 Referenzen & Tools

### Empfohlene Libraries
- `paho-mqtt` - MQTT Client (aktuell in Nutzung) ✅
- `python-meterbus` - M-Bus Protocol (aktuell in Nutzung) ✅
- `pydantic` - Config Validation
- `prometheus-client` - Metrics Export
- `watchdog` (Systemd) - Process Supervision

### Testing Tools
- `mosquitto_pub/sub` - MQTT Testing
- `pytest` - Unit & Integration Tests
- `locust` - Load Testing
- `wireshark` - M-Bus Protocol Debugging

### Monitoring
- **Grafana** - Metriken-Visualisierung
- **Prometheus** - Metrics Sammlung
- **Loki** - Log Aggregation
- **Uptime Kuma** - Simple Uptime Monitoring

---

## ✅ Nächste Schritte

1. **Review dieses Plans** mit allen Stakeholdern
2. **Priorisierung** der Sprints (was ist am wichtigsten?)
3. **Quick Wins implementieren** (heute noch möglich!)
4. **Sprint Planning** für nächste 4 Wochen
5. **Setup Monitoring** (minimal: Health Check Endpoint)

---

**Autor:** GitHub Copilot  
**Datum:** 5. Oktober 2025  
**Version:** 1.0  
**Status:** Draft - Ready for Review
