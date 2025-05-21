import json
import paho.mqtt.client as mqtt

class MQTTClient:
    def __init__(self, broker, port, username=None, password=None, topic_prefix="mbus"):
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.client = mqtt.Client()

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, topic, payload):
        full_topic = f"{self.topic_prefix}/{topic}"
        self.client.publish(full_topic, payload)
        print(f"[DEBUG] Published to topic {full_topic}: {payload}")

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
