import time
import socket
import uuid
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

@dataclass
class DeviceAttribute:
    """Repräsentiert ein einzelnes Attribut eines Geräts"""
    name: str
    value: Any
    unit: str
    last_updated: float = field(default_factory=time.time)
    value_type: str = "unknown"  # sensor, binary_sensor, switch, etc.
    
    def update_value(self, new_value: Any):
        """Aktualisiert den Wert und Zeitstempel"""
        # Konvertiere Decimal zu float für JSON-Kompatibilität
        if isinstance(new_value, Decimal):
            try:
                self.value = float(new_value)
            except (ValueError, OverflowError):
                # Fallback für sehr große oder ungültige Decimal-Werte
                self.value = str(new_value)
        else:
            self.value = new_value
        self.last_updated = time.time()

@dataclass
class Device:
    """Repräsentiert ein Gerät (M-Bus Meter oder Gateway)"""
    device_id: str
    device_type: str  # "mbus_meter", "gateway"
    name: str
    manufacturer: str = "Unknown"
    model: str = "Unknown"
    sw_version: str = ""
    attributes: Dict[str, DeviceAttribute] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    online: bool = True
    
    def update_attribute(self, attr_name: str, value: Any, unit: str = "", value_type: str = "sensor"):
        """Aktualisiert oder erstellt ein Attribut"""
        if attr_name in self.attributes:
            self.attributes[attr_name].update_value(value)
        else:
            self.attributes[attr_name] = DeviceAttribute(
                name=attr_name,
                value=value,
                unit=unit,
                value_type=value_type
            )
        self.last_seen = time.time()
        self.online = True
    
    def get_attribute_value(self, attr_name: str) -> Any:
        """Holt den Wert eines Attributs"""
        attr = self.attributes.get(attr_name)
        return attr.value if attr else None
    
    def set_offline(self):
        """Markiert das Gerät als offline"""
        self.online = False
        self.last_seen = time.time()

class DeviceManager:
    """Zentrale Instanz zur Verwaltung aller Geräte und deren Zustände"""
    
    def __init__(self):
        self.devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self.gateway_id = self._get_gateway_id()
        
        # MQTT Client Referenz (wird später gesetzt)
        self.mqtt_client = None
        
        # Gateway-Gerät initialisieren
        self._initialize_gateway()
    
    def _get_gateway_id(self) -> str:
        """Generiert eine eindeutige Gateway-ID basierend auf MAC-Adresse"""
        mac = uuid.getnode()
        mac_str = ':'.join(f'{(mac >> ele) & 0xff:02x}' for ele in range(40, -1, -8))
        return f"gateway_{mac_str.replace(':', '')}"
    
    def _get_local_ip(self) -> str:
        """Ermittelt die lokale IP-Adresse"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip
    
    def _initialize_gateway(self):
        """Initialisiert das Gateway-Gerät"""
        with self._lock:
            gateway = Device(
                device_id=self.gateway_id,
                device_type="gateway",
                name="M-Bus Gateway",
                manufacturer="Custom",
                model="M-Bus MQTT Gateway",
                sw_version="1.0.0"
            )
            
            # Grundlegende Gateway-Attribute
            gateway.update_attribute("ip_address", self._get_local_ip(), "", "sensor")
            gateway.update_attribute("status", "online", "", "binary_sensor")
            gateway.update_attribute("uptime", 0, "seconds", "sensor")
            
            self.devices[self.gateway_id] = gateway
            print(f"[INFO] Gateway initialisiert: {self.gateway_id}")
    
    def set_mqtt_client(self, mqtt_client):
        """Setzt den MQTT Client für automatische Updates"""
        self.mqtt_client = mqtt_client
        print(f"[INFO] MQTT Client an DeviceManager gekoppelt")
    
    def add_or_update_device(self, device_id: str, device_type: str = "mbus_meter", 
                           name: Optional[str] = None, manufacturer: str = "Unknown", 
                           model: str = "Unknown", sw_version: str = "") -> Device:
        """Fügt ein neues Gerät hinzu oder aktualisiert ein existierendes"""
        with self._lock:
            if device_id in self.devices:
                device = self.devices[device_id]
                device.last_seen = time.time()
                device.online = True
            else:
                device = Device(
                    device_id=device_id,
                    device_type=device_type,
                    name=name or f"Device {device_id}",
                    manufacturer=manufacturer,
                    model=model,
                    sw_version=sw_version
                )
                self.devices[device_id] = device
                print(f"[INFO] Neues Gerät hinzugefügt: {device_id}")
            
            return device
    
    def update_device_attribute(self, device_id: str, attr_name: str, value: Any, 
                              unit: str = "", value_type: str = "sensor"):
        """Aktualisiert ein Attribut eines Geräts"""
        with self._lock:
            if device_id in self.devices:
                self.devices[device_id].update_attribute(attr_name, value, unit, value_type)
            else:
                print(f"[WARN] Gerät {device_id} nicht gefunden für Attribut-Update")
    
    def update_mbus_device_data(self, address: int, data: Dict[str, Any]):
        """Aktualisiert M-Bus Gerätedaten aus dem MBusClient"""
        device_id = f"mbus_meter_{address}"
        
        # Name aus Config verwenden, falls vorhanden
        device_name = data.get("device_name", f"M-Bus Meter {address}")
        
        # Gerät hinzufügen/aktualisieren mit Metadaten
        device = self.add_or_update_device(
            device_id=device_id,
            device_type="mbus_meter",
            name=device_name,
            manufacturer=data.get("manufacturer", "Unknown"),
            model=data.get("medium", "Unknown"),
            sw_version=data.get("identification", "")
        )
        
        # Alle Records als Attribute hinzufügen
        records = data.get("records", [])
        for idx, record in enumerate(records):
            # Name aus Record oder generiere ihn aus der Einheit
            base_name = record.get("name")
            if not base_name:
                unit = record.get("unit", "")
                base_name = self._get_sensor_name_from_unit(unit, idx)
            
            # Immer Index anhängen für eindeutige Namen
            attr_name = f"{base_name}_{idx}"
            value = record.get("value", 0)
            unit = record.get("unit", "")
            
            self.update_device_attribute(device_id, attr_name, value, unit, "sensor")
        
        # Status-Attribut setzen
        self.update_device_attribute(device_id, "status", "online", "", "binary_sensor")
        
        # MQTT State Update senden (falls MQTT Client verfügbar)
        if self.mqtt_client and device_id in self.devices:
            device = self.devices[device_id]
            try:
                self.mqtt_client.publish_device_state(device)
            except Exception as e:
                print(f"[WARN] MQTT State Update fehlgeschlagen für {device_id}: {e}")
        
        print(f"[INFO] M-Bus Gerät {device_id} aktualisiert mit {len(records)} Attributen")
    
    def _get_sensor_name_from_unit(self, unit: str, index: int) -> str:
        """
        Generiert aussagekräftigen Sensor-Namen basierend auf der Einheit.
        """
        if not unit or unit.lower() == "none":
            return f"Zählerstand {index}"
        
        unit_lower = unit.lower()
        
        # Energie-Einheiten
        if unit_lower in ["kwh", "wh", "mwh", "gwh"]:
            return f"Energie Bezug ({unit})"
        elif unit_lower in ["kvarh", "varh"]:
            return f"Blindenergie ({unit})"
        
        # Leistungs-Einheiten
        elif unit_lower in ["w", "kw", "mw", "gw"]:
            return f"Wirkleistung ({unit})"
        elif unit_lower in ["var", "kvar", "mvar"]:
            return f"Blindleistung ({unit})"
        elif unit_lower in ["va", "kva", "mva"]:
            return f"Scheinleistung ({unit})"
        
        # Elektrische Größen
        elif unit_lower in ["v", "kv", "mv"]:
            return f"Spannung ({unit})"
        elif unit_lower in ["a", "ma", "ka"]:
            return f"Strom ({unit})"
        elif unit_lower in ["hz", "khz"]:
            return f"Frequenz ({unit})"
        elif unit_lower in ["°", "deg", "degree"]:
            return f"Phasenwinkel ({unit})"
        
        # Volumetrische Einheiten
        elif unit_lower in ["m³", "m3", "m^3", "l", "liter"]:
            return f"Volumen ({unit})"
        elif unit_lower in ["m³/h", "m3/h", "m^3/h", "l/h", "l/min"]:
            return f"Durchfluss ({unit})"
        
        # Temperatur
        elif unit_lower in ["°c", "c", "celsius", "k", "kelvin"]:
            return f"Temperatur ({unit})"
        
        # Druck
        elif unit_lower in ["bar", "mbar", "pa", "kpa", "mpa"]:
            return f"Druck ({unit})"
        
        # Zeit
        elif unit_lower in ["s", "min", "h", "d"]:
            return f"Zeit ({unit})"
        
        # Fallback: Einheit als Name verwenden
        else:
            return f"Messwert ({unit})"
    
    def set_device_offline(self, device_id: str):
        """Markiert ein Gerät als offline"""
        with self._lock:
            if device_id in self.devices:
                self.devices[device_id].set_offline()
                self.update_device_attribute(device_id, "status", "offline", "", "binary_sensor")
                
                # MQTT State Update senden (falls MQTT Client verfügbar)
                if self.mqtt_client:
                    device = self.devices[device_id]
                    try:
                        self.mqtt_client.publish_device_state(device)
                    except Exception as e:
                        print(f"[WARN] MQTT State Update fehlgeschlagen für {device_id}: {e}")
                
                print(f"[INFO] Gerät {device_id} als offline markiert")
    
    def get_device(self, device_id: str) -> Optional[Device]:
        """Holt ein Gerät anhand der ID"""
        with self._lock:
            return self.devices.get(device_id)
    
    def get_all_devices(self) -> Dict[str, Device]:
        """Holt alle Geräte (Thread-safe Copy)"""
        with self._lock:
            return self.devices.copy()
    
    def get_devices_by_type(self, device_type: str) -> List[Device]:
        """Holt alle Geräte eines bestimmten Typs"""
        with self._lock:
            return [device for device in self.devices.values() if device.device_type == device_type]
    
    def update_gateway_ip(self):
        """Aktualisiert die Gateway IP-Adresse"""
        old_ip = None
        if self.gateway_id in self.devices:
            old_ip = self.devices[self.gateway_id].get_attribute_value("ip_address")
        
        new_ip = self._get_local_ip()
        self.update_device_attribute(self.gateway_id, "ip_address", new_ip)
        
        # MQTT State Update nur bei IP-Änderung senden
        if self.mqtt_client and old_ip != new_ip and self.gateway_id in self.devices:
            device = self.devices[self.gateway_id]
            try:
                self.mqtt_client.publish_device_state(device)
                print(f"[INFO] Gateway IP geändert: {old_ip} → {new_ip}")
            except Exception as e:
                print(f"[WARN] MQTT State Update fehlgeschlagen für Gateway: {e}")
    
    def update_gateway_uptime(self, uptime_seconds: int):
        """Aktualisiert die Gateway Uptime"""
        self.update_device_attribute(self.gateway_id, "uptime", uptime_seconds, "seconds")
        
        # Status auch aktualisieren
        self.update_device_attribute(self.gateway_id, "status", "online", "", "binary_sensor")
        
        # Bridge State Heartbeat - sicherstellen dass Bridge online bleibt
        if self.mqtt_client and uptime_seconds % 30 == 0:  # Alle 30 Sekunden
            try:
                self.mqtt_client.publish("mbus/bridge/state", "online", retain=True)
            except Exception as e:
                print(f"[WARN] Bridge Heartbeat fehlgeschlagen: {e}")
        
        # MQTT State Update für Gateway senden (alle 60 Sekunden für Lebenszeichen)
        if self.mqtt_client and uptime_seconds % 60 == 0 and self.gateway_id in self.devices:
            device = self.devices[self.gateway_id]
            try:
                self.mqtt_client.publish_device_state(device, check_new_attributes=False)
                # print(f"[DEBUG] Gateway Status Update gesendet (Uptime: {uptime_seconds}s)")
            except Exception as e:
                print(f"[WARN] MQTT State Update fehlgeschlagen für Gateway: {e}")
    
    def print_status(self):
        """Gibt eine Übersicht aller Geräte und deren Status aus"""
        with self._lock:
            print("\n" + "="*60)
            print("DEVICE MANAGER STATUS")
            print("="*60)
            
            for device_id, device in self.devices.items():
                status = "🟢 ONLINE" if device.online else "🔴 OFFLINE"
                last_seen = datetime.fromtimestamp(device.last_seen).strftime("%H:%M:%S")
                
                print(f"\n📱 {device.name} ({device_id})")
                print(f"   Type: {device.device_type} | Status: {status} | Last seen: {last_seen}")
                print(f"   Manufacturer: {device.manufacturer} | Model: {device.model}")
                
                if device.attributes:
                    print("   Attributes:")
                    for attr_name, attr in device.attributes.items():
                        attr_time = datetime.fromtimestamp(attr.last_updated).strftime("%H:%M:%S")
                        unit_str = f" {attr.unit}" if attr.unit else ""
                        print(f"     • {attr_name}: {attr.value}{unit_str} (updated: {attr_time})")
            
            print("\n" + "="*60)

# Globale Instanz des DeviceManagers
device_manager = DeviceManager()
