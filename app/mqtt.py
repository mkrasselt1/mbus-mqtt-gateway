import json
import paho.mqtt.client as mqtt

class MQTTClient:
    def __init__(self, broker, port, username=None, password=None):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.client = mqtt.Client()
        self.connected = False

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

    def connect(self):
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            self.connected = True
        except Exception as e:
            print(f"[WARN] MQTT-Verbindung fehlgeschlagen: {e}")
            self.connected = False

    def publish(self, topic, payload):
        if not self.connected:
            try:
                self.connect()
            except Exception:
                print(f"[WARN] MQTT-Verbindung nicht möglich, Nachricht verworfen: {topic}")
                return
        try:
            self.client.publish(topic, payload)
            print(f"[DEBUG] Published to topic {topic}: {payload}")
        except Exception as e:
            print(f"[WARN] MQTT publish fehlgeschlagen ({topic}): {e}")

    def publish_discovery(self, component, object_id, payload):
        """
        Veröffentlicht eine allgemeine Home Assistant Discovery-Nachricht.
        component: z.B. 'sensor', 'switch', 'binary_sensor'
        object_id: z.B. 'mbus_gateway_ip'
        payload: dict mit den Discovery-Informationen
        """
        discovery_topic = f"homeassistant/{component}/{object_id}/config"
        print(f"[DEBUG] Sende Home Assistant Discovery an {discovery_topic}: {payload}")
        self.client.publish(discovery_topic, json.dumps(payload))
        print(f"[DEBUG] Discovery gesendet.")

    # Optional: Convenience-Methode für IP-Sensor
    def publish_ip_discovery(self, mac):
        object_id = f"mbus_{mac}_ip"
        payload = {
            "name": "Gateway IP",
            "state_topic": f"mbus/system/{mac}/ip",
            "unique_id": object_id,
            "icon": "mdi:ip-network",
            "device": {
                "identifiers": [f"mbus_{mac}_gateway"],
                "name": "MBus MQTT Gateway",
                "manufacturer": "Custom",
                "model": "mbus-mqtt-gateway"
            }
        }
        self.publish_discovery("sensor", object_id, payload)
