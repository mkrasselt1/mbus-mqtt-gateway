from multiprocessing import Process
from app.mbus import MBusClient
from app.mqtt import MQTTClient
from app.web import app
from app.config import Config
import json

def start_mbus_to_mqtt():
    config = Config()
    mqtt_client = MQTTClient(
        config.data["mqtt_broker"],
        config.data["mqtt_port"],
        username=config.data["mqtt_username"],
        password=config.data["mqtt_password"],
        topic_prefix=config.data["mqtt_topic"]
    )
    mqtt_client.connect()

    # Pass the mqtt_client to MBusClient
    mbus_client = MBusClient(config.data["mbus_port"], mqtt_client)

    while True:
        data = mbus_client.read_data()
        mqtt_client.publish(json.dumps(data))
        
if __name__ == "__main__":
    Process(target=start_mbus_to_mqtt).start()
    app.run(host="0.0.0.0", port=5000)
