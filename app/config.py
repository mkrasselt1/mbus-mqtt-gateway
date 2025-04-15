import json

class Config:
    CONFIG_FILE = "config.json"

    def __init__(self):
        self.data = {
            "mqtt_broker": "localhost",
            "mqtt_port": 1883,
            "mqtt_topic": "mbus",
            "mbus_port": "/dev/ttyUSB0",
            "mqtt_username": "",
            "mqtt_password": ""
        }
        self.load()
    def load(self):
        try:
            with open(self.CONFIG_FILE, "r") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.save()

    def save(self):
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=4)
