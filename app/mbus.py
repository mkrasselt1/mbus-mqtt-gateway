import time
import json
import serial
import meterbus
from app.mqtt import MQTTClient


class MBusClient:
    def __init__(self, port, mqtt_client, baudrate=2400):
        """
        Initialize the M-Bus client with the given serial port and baudrate.
        :param port: Serial port where the M-Bus master is connected (e.g., '/dev/ttyUSB0').
        :param mqtt_client: An instance of MQTTClient for publishing data.
        :param baudrate: Baudrate for the M-Bus communication (default: 2400).
        """
        self.port = port
        self.baudrate = baudrate
        self.mbus_master = meterbus(self.port, self.baudrate)
        self.devices = []  # List of detected M-Bus devices
        self.mqtt_client = mqtt_client

    def scan_devices(self):
        """
        Scan for M-Bus devices on the network during startup.
        :return: A list of secondary addresses (device IDs) of detected devices.
        """
        print("Scanning for M-Bus devices...")
        self.mbus_master.connect()
        detected_devices = []

        # Iterate over potential secondary addresses (0-255)
        for address in range(256):
            try:
                self.mbus_master.select_secondary_address(str(address))
                print(f"Device found at address: {address}")
                detected_devices.append(address)
            except Exception:
                pass  # No device found at this address

        self.mbus_master.disconnect()
        return detected_devices

    def read_data_from_device(self, address):
        """
        Read data from a specific M-Bus device.
        :param address: The secondary address of the M-Bus device.
        :return: Decoded data from the device.
        """
        try:
            self.mbus_master.connect()
            self.mbus_master.select_secondary_address(str(address))
            frame = self.mbus_master.send_request_frame()
            data = self.mbus_master.interpret_response_frame(frame)
            print(f"Data from device {address}: {data}")
            return data
        except Exception as e:
            print(f"Failed to read data from device {address}: {e}")
        finally:
            self.mbus_master.disconnect()

    def publish_homeassistant_discovery(self, address, data):
        """
        Publish Home Assistant MQTT auto-discovery configuration for a specific device.
        :param address: The address of the M-Bus device.
        :param data: The data structure containing the meter's attributes.
        """
        for key, value in data.items():
            discovery_topic = f"homeassistant/sensor/mbus_meter_{address}_{key}/config"
            payload = {
                "name": f"MBus Meter {address} {key}",
                "state_topic": f"mbus/meter/{address}",
                "unit_of_measurement": value.get("unit", ""),
                "value_template": f"{{{{ value_json.{key} }}}}",
                "unique_id": f"mbus_meter_{address}_{key}",
                "device": {
                    "identifiers": [f"mbus_meter_{address}"],
                    "name": f"MBus Meter {address}",
                    "manufacturer": "Unknown",
                    "model": "Unknown",
                },
            }
            self.mqtt_client.publish(discovery_topic, json.dumps(payload))
            print(f"Published Home Assistant discovery for {key} on device {address}")

    def publish_meter_data(self, address, data):
        """
        Publish M-Bus meter data to MQTT.
        :param address: The address of the M-Bus device.
        :param data: The decoded data from the meter.
        """
        topic = f"mbus/meter/{address}"
        payload = json.dumps(data)
        self.mqtt_client.publish(topic, payload)
        print(f"Published data for device {address} to MQTT: {payload}")

    def start(self):
        """
        Perform a one-time scan for devices on startup, then continuously read data from all detected devices.
        """
        # Scan for devices on startup
        self.devices = self.scan_devices()

        if not self.devices:
            print("No devices found during startup scan.")
            return

        print(f"Detected devices: {self.devices}")

        # Publish Home Assistant auto-discovery for all detected devices
        for device in self.devices:
            data_sample = self.read_data_from_device(device)
            if data_sample:
                self.publish_homeassistant_discovery(device, data_sample)

        # Continuously read data from all detected devices
        while True:
            for device in self.devices:
                data = self.read_data_from_device(device)
                if data:
                    self.publish_meter_data(device, data)
            time.sleep(60)  # Wait 60 seconds before reading again
