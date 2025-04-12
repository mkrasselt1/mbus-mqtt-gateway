import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(self, broker, port, topic_prefix="mbus"):
        self.broker = broker
        self.port = port
        self.topic_prefix = topic_prefix
        self.client = mqtt.Client()

    def connect(self):
        self.client.connect(self.broker, self.port)
        self.client.loop_start()

    def publish(self, topic, payload):
        full_topic = f"{self.topic_prefix}/{topic}"
        self.client.publish(full_topic, payload)
        print(f"Published to topic {full_topic}: {payload}")
