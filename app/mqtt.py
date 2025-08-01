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
        
        # Home Assistant Status Tracking
        self.ha_online = False
        self.pending_discovery = []  # Queue für Discovery-Nachrichten bis HA online ist

        # MQTT Callbacks setzen
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
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
            
            # Home Assistant Status abonnieren
            self.client.subscribe("homeassistant/status")
            print("[INFO] Abonniert: homeassistant/status")
            
            # Bei Wiederverbindung: Discovery-Nachrichten erneut senden
            # Prüfe ob neue Session (flags kann dict oder Objekt sein)
            session_present = False
            if isinstance(flags, dict):
                session_present = flags.get('session_present', False)
            else:
                session_present = getattr(flags, 'session_present', False)
                
            if not session_present:  # Neue Session
                print("[INFO] Neue MQTT-Session")
                # Warte auf Home Assistant Online-Status bevor Discovery gesendet wird
                if self.ha_online:
                    print("[INFO] Home Assistant bereits online - sende Discovery-Nachrichten erneut...")
                    self._resend_discovery_messages()
                else:
                    print("[INFO] Warte auf Home Assistant Online-Status...")
        else:
            self.connected = False
            print(f"[ERROR] MQTT-Verbindung fehlgeschlagen: Code {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback für empfangene MQTT-Nachrichten"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            # Home Assistant Status überwachen
            if topic == "homeassistant/status":
                if payload == "online":
                    print("[INFO] Home Assistant ist online - sende wartende Discovery-Nachrichten...")
                    self.ha_online = True
                    self._send_pending_discovery()
                elif payload == "offline":
                    print("[INFO] Home Assistant ist offline")
                    self.ha_online = False
                    
        except Exception as e:
            print(f"[ERROR] Fehler beim Verarbeiten der MQTT-Nachricht: {e}")

    def _send_pending_discovery(self):
        """Sende alle wartenden Discovery-Nachrichten"""
        if not self.ha_online:
            return
            
        for discovery_data in self.pending_discovery:
            topic = discovery_data['topic']
            payload = discovery_data['payload']
            self.client.publish(topic, payload)
            print(f"[DEBUG] Wartende Discovery gesendet: {topic}")
            
        # Cache für Reconnect aktualisieren
        for discovery_data in self.pending_discovery:
            self.discovery_messages[discovery_data['topic']] = discovery_data['payload']
            
        self.pending_discovery.clear()
        print(f"[INFO] {len(self.discovery_messages)} Discovery-Nachrichten gesendet")
        
        # Callback für externe Discovery-Wiederholung (z.B. M-Bus Devices) auch ausführen
        if self.reconnect_callback:
            try:
                self.reconnect_callback()
                print("[INFO] Externe Discovery-Nachrichten auch gesendet")
            except Exception as e:
                print(f"[ERROR] Fehler beim Senden externer Discovery-Nachrichten: {e}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback für MQTT-Verbindungsabbruch"""
        self.connected = False
        if rc != 0:
            reason_codes = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier", 
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorised",
                7: "Connection lost"
            }
            reason = reason_codes.get(rc, f"Unknown error ({rc})")
            print(f"[WARN] MQTT-Verbindung unerwartet getrennt: {reason}")
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
        """Sende alle gecachten Discovery-Nachrichten erneut (nur wenn HA online)"""
        if not self.ha_online:
            print("[INFO] Home Assistant nicht online - Discovery-Wiederholung wartet...")
            return
            
        for topic, payload in self.discovery_messages.items():
            self.client.publish(topic, payload)
            print(f"[DEBUG] Discovery wiederholt: {topic}")
        
        # Auch Reconnect-Callback ausführen wenn HA online ist
        if self.reconnect_callback:
            try:
                self.reconnect_callback()
                print("[INFO] Discovery-Nachrichten erfolgreich wiederholt")
            except Exception as e:
                print(f"[ERROR] Fehler beim Wiederholen der Discovery-Nachrichten: {e}")

    def _start_reconnect_thread(self):
        """Startet Wiederverbindungsthread falls noch nicht aktiv"""
        if self.reconnect_thread is None or not self.reconnect_thread.is_alive():
            self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self.reconnect_thread.start()

    def _reconnect_loop(self):
        """Kontinuierliche Wiederverbindungsschleife"""
        retry_delay = 5  # Start mit 5 Sekunden
        max_delay = 60   # Maximum 1 Minute (nicht 5 Minuten)
        attempt = 1
        
        while self.should_reconnect:
            if self.connected:
                # Verbindung ist da, kurz schlafen und dann prüfen
                time.sleep(5)
                continue
                
            try:
                print(f"[INFO] MQTT-Wiederverbindungsversuch #{attempt}...")
                
                # Neuen Client erstellen falls der alte problematisch ist
                if attempt > 5:
                    print("[INFO] Erstelle neuen MQTT-Client...")
                    try:
                        self.client.loop_stop()
                    except:
                        pass
                    self.client = mqtt.Client()
                    self.client.on_connect = self._on_connect
                    self.client.on_disconnect = self._on_disconnect
                    self.client.on_log = self._on_log
                    if self.username and self.password:
                        self.client.username_pw_set(self.username, self.password)
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_start()
                    attempt = 1  # Reset attempt counter nach Client-Neustart
                else:
                    self.client.reconnect()
                
                # Kurz warten um zu sehen ob Verbindung erfolgreich
                time.sleep(3)
                
                if self.connected:
                    print(f"[INFO] MQTT-Wiederverbindung erfolgreich!")
                    retry_delay = 5  # Reset delay nach erfolgreicher Verbindung
                else:
                    # Sanftes exponential backoff
                    retry_delay = min(retry_delay * 1.2, max_delay)
                    attempt += 1
                    print(f"[INFO] Warte {retry_delay:.1f} Sekunden vor nächstem Versuch...")
                    time.sleep(retry_delay)
                    
            except Exception as e:
                print(f"[ERROR] MQTT-Wiederverbindungsversuch fehlgeschlagen: {e}")
                retry_delay = min(retry_delay * 1.2, max_delay)
                attempt += 1
                time.sleep(retry_delay)

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

    def is_connected(self):
        """Prüfe aktuelle Verbindung"""
        return self.connected and self.client.is_connected()

    def ensure_connection(self):
        """Stelle sicher, dass eine Verbindung besteht - versucht kontinuierlich"""
        if not self.is_connected():
            print("[INFO] MQTT-Verbindung verloren, starte kontinuierliche Wiederverbindung...")
            if self.should_reconnect:
                self._start_reconnect_thread()
                
                # Kurz warten ob Wiederverbindung klappt
                timeout = 15
                start_time = time.time()
                while not self.is_connected() and (time.time() - start_time) < timeout:
                    time.sleep(0.5)
                    
                return self.is_connected()
            else:
                return False
        return True

    def publish(self, topic, payload, retain=False):
        """Publiziere Nachricht mit kontinuierlicher Wiederverbindung"""
        # Ständige Wiederverbindungsversuche bis erfolgreich
        while True:
            # Stelle sicher, dass eine gültige Verbindung besteht
            if not self.ensure_connection():
                print(f"[INFO] Warte auf MQTT-Verbindung für Topic: {topic}")
                time.sleep(5)  # 5 Sekunden warten vor nächstem Versuch
                continue
            
            # Verbindung ist da, versuche zu publizieren
            try:
                full_topic = f"{self.topic_prefix}/{topic}"
                result = self.client.publish(full_topic, payload, retain=retain)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"[DEBUG] Published to topic {full_topic}: {payload}")
                    return True
                else:
                    print(f"[WARN] MQTT publish fehlgeschlagen ({topic}): Code {result.rc}")
                    # Markiere Verbindung als verloren und versuche erneut
                    self.connected = False
                    time.sleep(2)
                    continue
                    
            except Exception as e:
                print(f"[ERROR] MQTT publish Fehler ({topic}): {e}")
                self.connected = False
                time.sleep(2)
                continue

    def publish_discovery(self, component, object_id, payload):
        """
        Veröffentlicht eine allgemeine Home Assistant Discovery-Nachricht.
        Wartet auf Home Assistant Online-Status bevor gesendet wird.
        component: z.B. 'sensor', 'switch', 'binary_sensor'
        object_id: z.B. 'mbus_gateway_ip'
        payload: dict mit den Discovery-Informationen
        """
        discovery_topic = f"homeassistant/{component}/{object_id}/config"
        payload_json = json.dumps(payload)
        
        if self.ha_online:
            # Home Assistant ist online - sofort senden
            print(f"[DEBUG] Sende Home Assistant Discovery an {discovery_topic}")
            self.client.publish(discovery_topic, payload_json)
            print(f"[DEBUG] Discovery gesendet und gecacht.")
            
            # Discovery-Nachricht cachen für Wiederholung bei Reconnect
            self.discovery_messages[discovery_topic] = payload_json
        else:
            # Home Assistant noch nicht online - in Warteschlange einreihen
            print(f"[INFO] Home Assistant noch nicht online - Discovery in Warteschlange: {discovery_topic}")
            self.pending_discovery.append({
                'topic': discovery_topic,
                'payload': payload_json
            })

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
