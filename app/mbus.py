import time
import json
import serial
import meterbus
from app.mqtt import MQTTClient


class MBusClient:
    def __init__(self, port, baudrate=2400, mqtt_client = None):
        """
        Initialize the M-Bus client with the given serial port and baudrate.
        :param port: Serial port where the M-Bus master is connected (e.g., '/dev/ttyUSB0').
        :param mqtt_client: An instance of MQTTClient for publishing data.
        :param baudrate: Baudrate for the M-Bus communication (default: 2400).
        """
        self.port = port
        self.baudrate = baudrate
        self.devices = []  # List of detected M-Bus devices
        self.mqtt_client = mqtt_client
        print(f"Initializing M-Bus client on port {self.port} with baudrate {self.baudrate}")

    def scan_devices(self):
        """
        Scan for M-Bus devices on the network during startup.
        :return: A list of secondary addresses (device IDs) of detected devices.
        """
        print("Scanning for M-Bus devices...")
        try:
            with serial.serial_for_url(self.port,
                            self.baudrate, 8, 'E', 1, timeout=1) as ser:

                # Ensure we are at the beginning of the records
                self.init_slaves(ser, False)

                self.mbus_scan_secondary_address_range(ser, 0, "FFFFFFFFFFFFFFFF", False)

        except serial.serialutil.SerialException as e:
            print(e)

            if not self.devices:
                print("No devices found during startup scan.")
                return

    def read_data_from_device(self, address):
        """
        Read data from a specific M-Bus device.
        :param address: The secondary address of the M-Bus device.
        :return: Decoded data from the device.
        """
        try:
            self.mbus_master.connect()
            # Send a request to the device at the given address (assuming secondary addressing)
            # If your devices are using primary addressing, adjust accordingly.
            self.mbus_master.select_secondary_address(str(address))
            frame = self.mbus_master.send_request_frame()
            reply = self.mbus_master.recv_frame()
            # Parse the reply frame
            parsed = meterbus.frame_data_parse(reply)
            # Optionally, convert to dict if parsed is not already a dictionary
            if hasattr(parsed, 'to_JSON'):
                data = json.loads(parsed.to_JSON())
            elif isinstance(parsed, dict):
                data = parsed
            else:
                # Fallback: try to convert to string
                data = {"raw": str(parsed)}
            print(f"Data from device {address}: {data}")
            # Push the parsed data to MQTT
            self.publish_meter_data(address, data)
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
        self.scan_devices()
        
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

    
    def ping_address(self, ser, address, retries=5, read_echo=False):
        for i in range(0, retries + 1):
            meterbus.send_ping_frame(ser, address, read_echo)
            try:
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
                if isinstance(frame, meterbus.TelegramACK):
                    return True
            except meterbus.MBusFrameDecodeError:
                pass

            time.sleep(0.5)

        return False

    def init_slaves(self, ser, read_echo=False):
        if not self.ping_address(ser, meterbus.ADDRESS_NETWORK_LAYER, 0, read_echo):
            return self.ping_address(ser, meterbus.ADDRESS_BROADCAST_NOREPLY, 0, read_echo)
        else:
            return True

        return False

    def mbus_scan_secondary_address_range(self, ser, pos, mask, read_echo=False):
        # F character is a wildcard
        if mask[pos].upper() == 'F':
            l_start, l_end = 0, 9
        else:
            if pos < 15:
                self.mbus_scan_secondary_address_range(ser, pos+1, mask, read_echo)
            else:
                l_start = l_end = ord(mask[pos]) - ord('0')

        if mask[pos].upper() == 'F' or pos == 15:
            for i in range(l_start, l_end+1):  # l_end+1 is to include l_end val
                new_mask = (mask[:pos] + "{0:1X}".format(i) + mask[pos+1:]).upper()
                val, match, manufacturer = self.mbus_probe_secondary_address(ser, new_mask, read_echo)
                if val is True:
                    print("Device found with id {0} ({1}), using mask {2}".format(
                    match, manufacturer, new_mask))
                    self.devices.append(val)  # Store the found device
                elif val is False:  # Collision
                    self.mbus_scan_secondary_address_range(ser, pos+1, new_mask, read_echo)

    def mbus_probe_secondary_address(self, ser, mask, read_echo=False):
        # False -> Collision
        # None -> No reply
        # True -> Single reply
        meterbus.send_select_frame(ser, mask, read_echo)
        try:
            frame = meterbus.load(meterbus.recv_frame(ser, 1))
        except meterbus.MBusFrameDecodeError as e:
            frame = e.value

        if isinstance(frame, meterbus.TelegramACK):
            meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, read_echo=read_echo)
            time.sleep(0.5)

            frame = None
            try:
                frame = meterbus.load(
                    meterbus.recv_frame(ser))
            except meterbus.MBusFrameDecodeError:
                pass

            if isinstance(frame, meterbus.TelegramLong):
                return True, frame.secondary_address, frame.manufacturer

            return None, None, None

        return frame, None, None