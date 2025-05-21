from multiprocessing import Process
from app.mbus import MBusClient
from app.mqtt import MQTTClient
from app.web import app
from app.config import Config
import json
import socket
import time
import uuid

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

    #while True:
        #data = mbus_client.read_data()
        #mqtt_client.publish(json.dumps(data))
        
def get_local_ip():
    """Ermittelt die lokale IP-Adresse."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_mac():
    """Gibt die MAC-Adresse des ersten Netzwerkadapters als String zurück."""
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> ele) & 0xff:02x}' for ele in range(40, -1, -8))

def publish_ha_ip_discovery(mqtt_client, topic_prefix, mac):
    """Veröffentlicht Home Assistant Discovery für die IP-Adresse."""
    discovery_topic = f"homeassistant/sensor/{topic_prefix}_{mac}_ip/config"
    payload = {
        "name": "Gateway IP",
        "state_topic": f"{topic_prefix}/system/{mac}/ip",
        "unique_id": f"{topic_prefix}_{mac}_ip",
        "icon": "mdi:ip-network",
        "device": {
            "identifiers": [f"{topic_prefix}_{mac}_gateway"],
            "name": "MBus MQTT Gateway",
            "manufacturer": "Custom",
            "model": "mbus-mqtt-gateway"
        }
    }
    mqtt_client.publish(discovery_topic, json.dumps(payload))

def publish_ip_loop():
    config = Config()
    mqtt_client = MQTTClient(
        config.data["mqtt_broker"],
        config.data["mqtt_port"],
        username=config.data["mqtt_username"],
        password=config.data["mqtt_password"],
        topic_prefix=config.data["mqtt_topic"]
    )
    mqtt_client.connect()
    mac = get_mac().replace(":", "")
    publish_ha_ip_discovery(mqtt_client, config.data["mqtt_topic"], mac)
    while True:
        ip = get_local_ip()
        mqtt_client.publish(f"{config.data['mqtt_topic']}/system/{mac}/ip", ip)
        time.sleep(60)

if __name__ == "__main__":
    Process(target=start_mbus_to_mqtt).start()
    Process(target=publish_ip_loop).start()
    app.run(host="0.0.0.0", port=5000)
