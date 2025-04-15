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
        print(f"Published to topic {full_topic}: {payload}")
