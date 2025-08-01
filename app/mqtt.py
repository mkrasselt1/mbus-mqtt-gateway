import json
import paho.mqtt.client as mqtt
import time
import threading

class MQTTClient:
    def __init__(self, broker, port, username=None, password=None, topic_prefix="mbus"):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client = mqtt.Client()
        self.connected = False
        self.reconnect_thread = None
        self.should_reconnect = True
        
        # Discovery-Cache für Wiederholung bei Reconnect
        self.discovery_messages = {}
        self.reconnect_callback = None

        # MQTT Callbacks setzen
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_log = self._on_log

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

    def set_reconnect_callback(self, callback):
        """
        Setze eine Callback-Funktion, die bei erfolgreicher Wiederverbindung aufgerufen wird.
        Diese sollte alle Discovery-Nachrichten erneut senden.
        """
        self.reconnect_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """Callback für erfolgreiche MQTT-Verbindung"""
        if rc == 0:
            self.connected = True
            print(f"[INFO] MQTT verbunden mit {self.broker}:{self.port}")
            
            # Bei Wiederverbindung: Discovery-Nachrichten erneut senden
            if flags.session_present == 0:  # Neue Session
                print("[INFO] Neue MQTT-Session - sende Discovery-Nachrichten erneut...")
                self._resend_discovery_messages()
                
                # Callback für externe Discovery-Wiederholung (z.B. M-Bus Devices)
                if self.reconnect_callback:
                    try:
                        self.reconnect_callback()
                        print("[INFO] Discovery-Nachrichten erfolgreich wiederholt")
                    except Exception as e:
                        print(f"[ERROR] Fehler beim Wiederholen der Discovery-Nachrichten: {e}")
        else:
            self.connected = False
            print(f"[ERROR] MQTT-Verbindung fehlgeschlagen: Code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungsabbruch"""
        self.connected = False
        if rc != 0:
            print(f"[WARN] MQTT-Verbindung unerwartet getrennt: Code {rc}")
            if self.should_reconnect:
                self._start_reconnect_thread()
        else:
            print("[INFO] MQTT-Verbindung ordnungsgemäß getrennt")

    def _on_log(self, client, userdata, level, buf):
        """Callback für MQTT-Logs (optional für Debugging)"""
        # Nur wichtige Logs anzeigen
        if level <= mqtt.MQTT_LOG_WARNING:
            print(f"[MQTT-LOG] {buf}")

    def _resend_discovery_messages(self):
        """Sende alle gecachten Discovery-Nachrichten erneut"""
        for topic, payload in self.discovery_messages.items():
            self.client.publish(topic, payload)
            print(f"[DEBUG] Discovery wiederholt: {topic}")

    def _start_reconnect_thread(self):
        """Startet Wiederverbindungsthread falls noch nicht aktiv"""
        if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()

    def _reconnect_loop(self):
        """Wiederverbindungsschleife mit exponential backoff"""
        retry_delay = 5  # Start mit 5 Sekunden
        max_delay = 300  # Maximum 5 Minuten
        
        while not self.connected and self.should_reconnect:
            try:
                print(f"[INFO] Versuche MQTT-Wiederverbindung in {retry_delay} Sekunden...")
                time.sleep(retry_delay)
                
                if not self.should_reconnect:
                    break
                    
                print(f"[INFO] Verbinde zu MQTT-Broker {self.broker}:{self.port}...")
                self.client.reconnect()
                
                # Warte kurz um zu sehen ob Verbindung erfolgreich
                time.sleep(2)
                
                if self.connected:
                    print("[INFO] MQTT-Wiederverbindung erfolgreich!")
                    break
                else:
                    # Exponential backoff: Verdopple delay bis zum Maximum
                    retry_delay = min(retry_delay * 2, max_delay)
                    
            except Exception as e:
                print(f"[ERROR] MQTT-Wiederverbindung fehlgeschlagen: {e}")
                retry_delay = min(retry_delay * 2, max_delay)

    def connect(self):
        """Verbinde zu MQTT-Broker mit automatischer Wiederverbindung"""
        try:
            print(f"[INFO] Verbinde zu MQTT-Broker {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Warte kurz auf Verbindungsbestätigung
            timeout = 10
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
                
            if self.connected:
                print("[INFO] MQTT-Verbindung erfolgreich hergestellt")
            else:
                print("[WARN] MQTT-Verbindung timeout - versuche weiter im Hintergrund")
                
        except Exception as e:
            print(f"[ERROR] MQTT-Verbindung fehlgeschlagen: {e}")
            self.connected = False
            if self.should_reconnect:
                self._start_reconnect_thread()

    def disconnect(self):
        """Ordnungsgemäß von MQTT-Broker trennen"""
        self.should_reconnect = False
        if self.connected:
            self.client.disconnect()
        self.client.loop_stop()
        print("[INFO] MQTT-Verbindung getrennt")

    def publish(self, topic, payload, retain=False):
        """Publiziere Nachricht mit automatischer Wiederverbindung"""
        if not self.connected:
            if self.should_reconnect:
                print(f"[WARN] MQTT nicht verbunden - starte Wiederverbindung für Topic: {topic}")
                self._start_reconnect_thread()
                
                # Kurz warten ob Wiederverbindung schnell klappt
                timeout = 5
                start_time = time.time()
                while not self.connected and (time.time() - start_time) < timeout:
                    time.sleep(0.1)
            
            if not self.connected:
                print(f"[WARN] MQTT-Verbindung nicht möglich, Nachricht verworfen: {topic}")
                return False
                
        try:
            full_topic = f"{self.topic_prefix}/{topic}"
            result = self.client.publish(full_topic, payload, retain=retain)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"[DEBUG] Published to topic {full_topic}: {payload}")
                return True
            else:
                print(f"[WARN] MQTT publish fehlgeschlagen ({topic}): Code {result.rc}")
                return False
                
        except Exception as e:
            print(f"[ERROR] MQTT publish Fehler ({topic}): {e}")
            self.connected = False
            return False

    def publish_discovery(self, component, object_id, payload):
        """
        Veröffentlicht eine allgemeine Home Assistant Discovery-Nachricht.
        component: z.B. 'sensor', 'switch', 'binary_sensor'
        object_id: z.B. 'mbus_gateway_ip'
        payload: dict mit den Discovery-Informationen
        """
        discovery_topic = f"homeassistant/{component}/{object_id}/config"
        payload_json = json.dumps(payload)
        
        # Discovery-Nachricht cachen für Wiederholung bei Reconnect
        self.discovery_messages[discovery_topic] = payload_json
        
        print(f"[DEBUG] Sende Home Assistant Discovery an {discovery_topic}")
        self.client.publish(discovery_topic, payload_json)
        print(f"[DEBUG] Discovery gesendet und gecacht.")

    # Optional: Convenience-Methode für IP-Sensor
    def publish_ip_discovery(self, mac):
        object_id = f"{self.topic_prefix}_{mac}_ip"
        payload = {
            "name": "Gateway IP",
            "state_topic": f"{self.topic_prefix}/system/{mac}/ip",
            "unique_id": object_id,
            "icon": "mdi:ip-network",
            "device": {
                "identifiers": [f"{self.topic_prefix}_{mac}_gateway"],
                "name": "MBus MQTT Gateway",
                "manufacturer": "Custom",
                "model": "mbus-mqtt-gateway"
            }
        }
        self.publish_discovery("sensor", object_id, payload)

    def publish_device_status_discovery(self, device_address, device_name, device_manufacturer):
        """
        Veröffentlicht Discovery für einen Device-Status-Sensor.
        """
        object_id = f"{self.topic_prefix}_{device_address}_status"
        payload = {
            "name": f"{device_name} Status",
            "state_topic": f"{self.topic_prefix}/device/{device_address}/status",
            "unique_id": object_id,
            "icon": "mdi:connection",
            "device": {
                "identifiers": [f"mbus_meter_{device_address}"],
                "name": device_name,
                "manufacturer": device_manufacturer,
                "model": "M-Bus Device"
            }
        }
        self.publish_discovery("sensor", object_id, payload)

    def publish_gateway_discovery(self, mac, connected_devices):
        """
        Veröffentlicht Discovery für den Gateway mit Liste der verbundenen Geräte.
        """
        object_id = f"{self.topic_prefix}_{mac}_devices"
        device_list = ", ".join([f"{dev['name']} ({dev['address']})" for dev in connected_devices])
        
        payload = {
            "name": "Connected M-Bus Devices",
            "state_topic": f"{self.topic_prefix}/gateway/{mac}/devices",
            "unique_id": object_id,
            "icon": "mdi:devices",
            "device": {
                "identifiers": [f"{self.topic_prefix}_{mac}_gateway"],
                "name": "MBus MQTT Gateway",
                "manufacturer": "Custom",
                "model": "mbus-mqtt-gateway"
            }
        }
        self.publish_discovery("sensor", object_id, payload)
        
        # Publiziere die aktuelle Geräteliste
        self.publish(f"gateway/{mac}/devices", device_list)
