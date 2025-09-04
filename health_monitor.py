#!/usr/bin/env python3
"""
MBus Gateway Health Monitor
Überwacht den MBus Service und startet ihn bei Problemen neu
"""

import time
import subprocess
import json
import os
from datetime import datetime

class HealthMonitor:
    def __init__(self):
        self.service_name = "mbus-mqtt-gateway.service"
        self.last_log_check = time.time()
        self.last_activity_time = time.time()
        self.max_silence_time = 180  # 3 Minuten ohne Aktivität = Problem (war 5 Min)
        self.last_restart_time = 0
        self.restart_count = 0
        self.heartbeat_file = "/tmp/mbus_heartbeat.txt"
        
    def write_heartbeat(self):
        """Schreibt einen Heartbeat-File für den Service"""
        try:
            with open(self.heartbeat_file, "w") as f:
                f.write(f"{time.time()}\n{datetime.now().isoformat()}\n")
        except Exception as e:
            print(f"[ERROR] Fehler beim Schreiben des Heartbeat: {e}")
    
    def check_heartbeat_file(self):
        """Prüft ob der Service noch ein Heartbeat-Signal sendet"""
        try:
            if not os.path.exists(self.heartbeat_file):
                return False
                
            with open(self.heartbeat_file, "r") as f:
                lines = f.readlines()
                if len(lines) >= 1:
                    heartbeat_time = float(lines[0].strip())
                    age = time.time() - heartbeat_time
                    
                    if age < self.max_silence_time:
                        self.last_activity_time = heartbeat_time
                        return True
                    else:
                        print(f"[WARN] Heartbeat File ist {age:.1f}s alt (zu alt)")
                        return False
        except Exception as e:
            print(f"[ERROR] Fehler beim Lesen des Heartbeat: {e}")
            return False
        
        return False
        
    def check_service_status(self):
        """Prüft ob der systemd Service läuft"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() == "active"
        except Exception as e:
            print(f"[ERROR] Fehler beim Prüfen des Service-Status: {e}")
            return False
    
    def get_recent_logs(self, minutes=10):
        """Holt die letzten Logs des Services"""
        try:
            result = subprocess.run([
                "journalctl", "-u", self.service_name, 
                f"--since={minutes} minutes ago", 
                "--no-pager", "-n", "50"
            ], capture_output=True, text=True, timeout=30)
            
            return result.stdout
        except Exception as e:
            print(f"[ERROR] Fehler beim Lesen der Logs: {e}")
            return ""
    
    def check_for_activity(self):
        """Prüft ob der Service noch aktiv Daten verarbeitet"""
        
        # 1. Heartbeat File prüfen (zuverlässiger)
        if self.check_heartbeat_file():
            return True
        
        # 2. Fallback: Log-basierte Prüfung
        logs = self.get_recent_logs(3)  # Letzte 3 Minuten
        
        # Suche nach Aktivitäts-Indikatoren
        activity_indicators = [
            "[DEBUG] Neue Daten von Device",
            "[DEBUG] Lese Daten von Device", 
            "[INFO] M-Bus Gerät",
            "[DEBUG] Zyklus abgeschlossen",
            "Records"
        ]
        
        for indicator in activity_indicators:
            if indicator in logs:
                self.last_activity_time = time.time()
                return True
        
        return False
    
    def force_kill_service(self):
        """Forciert das Beenden eines hängenden Services"""
        try:
            print("[ACTION] Versuche Service mit SIGKILL zu beenden...")
            subprocess.run(["systemctl", "kill", "-s", "SIGKILL", self.service_name], timeout=10)
            time.sleep(5)
            return True
        except Exception as e:
            print(f"[ERROR] Fehler beim Force-Kill: {e}")
            return False
    
    def restart_service(self):
        """Startet den Service neu"""
        print(f"[ACTION] Starte {self.service_name} neu...")
        try:
            # Service stoppen
            subprocess.run(["systemctl", "stop", self.service_name], timeout=30)
            time.sleep(5)
            
            # Service starten
            result = subprocess.run(["systemctl", "start", self.service_name], timeout=30)
            
            if result.returncode == 0:
                print(f"[SUCCESS] {self.service_name} erfolgreich neu gestartet")
                self.last_activity_time = time.time()
                return True
            else:
                print(f"[ERROR] Fehler beim Starten des Services")
                return False
                
        except Exception as e:
            print(f"[ERROR] Exception beim Service-Neustart: {e}")
            return False
    
    def log_health_status(self):
        """Loggt den aktuellen Gesundheitsstatus"""
        now = datetime.now()
        time_since_activity = time.time() - self.last_activity_time
        service_active = self.check_service_status()
        
        status = {
            "timestamp": now.isoformat(),
            "service_active": service_active,
            "time_since_activity": time_since_activity,
            "status": "healthy" if service_active and time_since_activity < self.max_silence_time else "unhealthy"
        }
        
        print(f"[HEALTH] {status}")
        
        return status
    
    def run(self):
        """Hauptüberwachungsschleife"""
        print("[HEALTH] MBus Gateway Health Monitor gestartet")
        print(f"[HEALTH] Überwache Service: {self.service_name}")
        print(f"[HEALTH] Max. Stillstand: {self.max_silence_time}s")
        
        while True:
            try:
                # Service-Status prüfen
                service_active = self.check_service_status()
                
                if not service_active:
                    print(f"[WARN] Service {self.service_name} ist nicht aktiv!")
                    self.restart_service()
                    time.sleep(60)  # Warten nach Neustart
                    continue
                
                # Aktivität prüfen
                has_activity = self.check_for_activity()
                time_since_activity = time.time() - self.last_activity_time
                
                if time_since_activity > self.max_silence_time:
                    print(f"[WARN] Keine Aktivität seit {time_since_activity:.1f}s - Service möglicherweise hängend")
                    
                    # Logs der letzten 10 Minuten ausgeben für Debugging
                    recent_logs = self.get_recent_logs(10)
                    print("[DEBUG] Letzte Logs:")
                    print(recent_logs[-1000:])  # Letzte 1000 Zeichen
                    
                    self.restart_service()
                    time.sleep(60)  # Warten nach Neustart
                    continue
                
                # Gesundheitsstatus loggen (alle 5 Minuten)
                if time.time() - self.last_log_check > 300:
                    self.log_health_status()
                    self.last_log_check = time.time()
                
                # Kurze Pause vor nächster Prüfung
                time.sleep(30)
                
            except KeyboardInterrupt:
                print("[INFO] Health Monitor beendet durch Benutzer")
                break
            except Exception as e:
                print(f"[ERROR] Fehler im Health Monitor: {e}")
                time.sleep(60)

if __name__ == "__main__":
    monitor = HealthMonitor()
    monitor.run()
