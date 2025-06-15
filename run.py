from multiprocessing import Process
from app.mbus import MBusClient
from app.mqtt import MQTTClient
from app.web import app
from app.config import Config
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
    )
    mqtt_client.connect()

    # Pass the mqtt_client to MBusClient
    mbus_client = MBusClient(
        port=config.data["mbus_port"],
        baudrate=config.data["mbus_baudrate"],
        mqtt_client=mqtt_client,)
    mbus_client.start()
        
def get_local_ip():
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
    mac = uuid.getnode()
    return ':'.join(f'{(mac >> ele) & 0xff:02x}' for ele in range(40, -1, -8))

def publish_ip_loop():
    config = Config()
    mqtt_client = MQTTClient(
        config.data["mqtt_broker"],
        config.data["mqtt_port"],
        username=config.data["mqtt_username"],
        password=config.data["mqtt_password"]
    )
    print(f"[DEBUG] Verbinde zu MQTT-Broker {config.data['mqtt_broker']}:{config.data['mqtt_port']} ...")
    mqtt_client.connect()
    print("[DEBUG] MQTT-Verbindung hergestellt.")
    mac = get_mac().replace(":", "")
    print(f"[DEBUG] Verwende MAC-Adresse: {mac}")
    mqtt_client.publish_ip_discovery(mac)
    print("[DEBUG] Home Assistant Discovery für IP veröffentlicht.")
    while True:
        ip = get_local_ip()
        topic = f"mbus/system/{mac}/ip"
        print(f"[DEBUG] Sende IP {ip} an Topic {topic}")
        mqtt_client.publish(topic, ip)
        time.sleep(60)

if __name__ == "__main__":
    Process(target=start_mbus_to_mqtt).start()
    Process(target=publish_ip_loop).start()
    app.run(host="0.0.0.0", port=5000)
