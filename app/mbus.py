import time
import json
import serial
import meterbus
import threading
#from meterbus.telegram_short import TelegramShort
        #from meterbus.defines import CONTROL_MASK_REQ_UD1, CONTROL_MASK_DIR_M2S
        #from meterbus.serial import serial_send
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
        self.device_info = {}  # Dict to store device information
        self.mqtt_client = mqtt_client
        print(f"Initializing M-Bus client on port {self.port} with baudrate {self.baudrate}")
        
        # Setze Reconnect-Callback für MQTT-Client
        if self.mqtt_client:
            self.mqtt_client.set_reconnect_callback(self._on_mqtt_reconnect)
            # Registriere M-Bus Discovery-Callback
            self.mqtt_client.add_discovery_callback(self._send_mbus_discovery)

    def _send_mbus_discovery(self):
        """
        Sendet alle M-Bus Discovery-Nachrichten.
        Wird von der zentralen Discovery-Methode aufgerufen.
        """
        print("[INFO] Sende M-Bus Discovery-Nachrichten...")
        
        if not self.mqtt_client:
            print("[WARN] MQTT-Client nicht verfügbar für M-Bus Discovery")
            return
        
        # Discovery für alle bereits erkannten Geräte
        for device in self.devices:
            if device in self.device_info:
                # Sensor Discovery für jedes Gerät
                device_data = {
                    'manufacturer': self.device_info[device].get('manufacturer', 'Unknown'),
                    'records': self.device_info[device].get('records', [])
                }
                if device_data['records']:
                    self.publish_homeassistant_discovery(device, device_data)
                
                # Status Discovery
                device_name = self.device_info[device].get('name', f"MBus Meter {device}")
                device_manufacturer = self.device_info[device].get('manufacturer', 'Unknown')
                self.mqtt_client.publish_device_status_discovery(device, device_name, device_manufacturer)
        
        # Gateway Discovery
        if self.device_info:
            import uuid
            mac = ':'.join(f'{(uuid.getnode() >> ele) & 0xff:02x}' for ele in range(40, -1, -8)).replace(":", "")
            connected_devices = [
                {
                    'name': info['name'],
                    'address': info['address'],
                    'manufacturer': info['manufacturer']
                }
                for info in self.device_info.values()
            ]
            self.mqtt_client.publish_gateway_discovery(mac, connected_devices)

    def _on_mqtt_reconnect(self):
        """
        Wird aufgerufen, wenn MQTT-Verbindung wiederhergestellt wird.
        Sendet alle Discovery-Nachrichten erneut.
        """
        print("[INFO] MQTT wiederverbunden - sende M-Bus Discovery-Nachrichten erneut...")
        
        # Discovery für alle bereits erkannten Geräte wiederholen
        for device in self.devices:
            if device in self.device_info:
                # Status Discovery wiederholen
                device_name = self.device_info[device].get('name', f"MBus Meter {device}")
                device_manufacturer = self.device_info[device].get('manufacturer', 'Unknown')
                self.mqtt_client.publish_device_status_discovery(device, device_name, device_manufacturer)
        
        # Gateway Discovery wiederholen
        if self.device_info:
            import uuid
            mac = ':'.join(f'{(uuid.getnode() >> ele) & 0xff:02x}' for ele in range(40, -1, -8)).replace(":", "")
            connected_devices = [
                {
                    'name': info['name'],
                    'address': info['address'],
                    'manufacturer': info['manufacturer']
                }
                for info in self.device_info.values()
            ]
            self.mqtt_client.publish_gateway_discovery(mac, connected_devices)

    def start_periodic_scan(self, interval_minutes):
        """
        Startet regelmäßiges Scannen nach neuen M-Bus Geräten im Hintergrund.
        
        :param interval_minutes: Intervall in Minuten zwischen den Scans
        """
        def periodic_scan():
            while True:
                try:
                    time.sleep(interval_minutes * 60)  # Minuten in Sekunden
                    print(f"[INFO] Starte regelmäßigen M-Bus Scan (alle {interval_minutes} Min)...")
                    
                    # Alte Geräteliste merken
                    old_devices = set(self.devices)
                    
                    # Neuen Scan durchführen
                    self.scan_devices()
                    
                    # Neue Geräte identifizieren
                    new_devices = set(self.devices) - old_devices
                    
                    if new_devices:
                        print(f"[INFO] {len(new_devices)} neue M-Bus Geräte gefunden: {list(new_devices)}")
                        
                        # Für neue Geräte erst mal Daten lesen um device_info zu füllen
                        for device in new_devices:
                            data = self.read_data_from_device(device)
                            if data:
                                print(f"[INFO] Neues Gerät {device} erfolgreich initialisiert")
                        
                        # Discovery für neue Geräte auslösen
                        if self.mqtt_client:
                            print("[INFO] Starte Discovery für neue Geräte in 2 Sekunden...")
                            threading.Timer(2.0, self.mqtt_client.send_all_discovery).start()
                    else:
                        print(f"[INFO] Regelmäßiger M-Bus Scan abgeschlossen - keine neuen Geräte gefunden")
                        
                except Exception as e:
                    print(f"[ERROR] Fehler beim regelmäßigen M-Bus Scan: {e}")
        
        # Scan-Thread starten
        scan_thread = threading.Thread(target=periodic_scan, daemon=True, name="MBus-Scanner")
        scan_thread.start()
        print(f"[INFO] Regelmäßiger M-Bus Scan gestartet (alle {interval_minutes} Minuten)")

    def scan_devices(self):
        """
        Scan for M-Bus devices on the network.
        Thread-safe und vermeidet Dopplungen.
        """
        print("[INFO] Starte M-Bus Geräte-Scan...")
        initial_device_count = len(self.devices)
        
        try:
            with serial.serial_for_url(self.port,
                            self.baudrate, 8, 'E', 1, timeout=1) as ser:

                # Ensure we are at the beginning of the records
                self.init_slaves(ser, False)

                self.mbus_scan_secondary_address_range(ser, 0, "FFFFFFFFFFFFFFFF", False)

        except serial.SerialException as e:
            print(f"[ERROR] Serieller Fehler beim M-Bus Scan: {e}")
            return

        new_device_count = len(self.devices)
        devices_found = new_device_count - initial_device_count
        
        if devices_found > 0:
            print(f"[INFO] M-Bus Scan abgeschlossen: {devices_found} neue Geräte gefunden")
        elif initial_device_count == 0:
            print("[WARN] M-Bus Scan abgeschlossen: Keine Geräte gefunden")
        else:
            print(f"[INFO] M-Bus Scan abgeschlossen: Keine neuen Geräte (Total: {new_device_count})")

    def read_data_from_device(self, address):
        """
        Read data from a specific M-Bus device.
        :param address: The secondary address of the M-Bus device.
        :return: Decoded data from the device.
        """
        try:
            ibt = meterbus.inter_byte_timeout(self.baudrate)
            with serial.serial_for_url(self.port,
                            self.baudrate, 8, 'E', 1,
                            inter_byte_timeout=ibt,
                            timeout=1) as ser:
                
                # Erst die Standard-Daten lesen
                frame = self.read_standard_data(ser, address)
                if frame is None:
                    return None
                
                # Standard-Records sammeln
                recs = []
                for idx, rec in enumerate(frame.records):
                    # Bestimme Namen basierend auf der Einheit
                    name = self.get_sensor_name_from_unit(rec.unit, idx)
                    
                    # Wert auf 4 Nachkommastellen begrenzen falls es eine Zahl ist
                    value = rec.value
                    if isinstance(value, (float, int)):
                        value = round(float(value), 4)
                    
                    recs.append({
                        'value': value,
                        'unit': rec.unit,
                        'name': name,
                        'function': getattr(rec, 'function_field', {}).get('parts', [None])[0] if hasattr(rec, 'function_field') else None
                    })

                # print(f"Read {len(recs)} standard records from device {address}")

                ydata = {
                    'manufacturer': frame.body.bodyHeader.manufacturer_field.decodeManufacturer,
                    'identification': ''.join(map('{:02x}'.format, frame.body.bodyHeader.id_nr)),
                    'access_no': frame.body.bodyHeader.acc_nr_field.parts[0],
                    'medium':  frame.body.bodyHeader.measure_medium_field.parts[0],
                    'records': recs
                }

                # Speichere Device-Info und publiziere Status
                self.device_info[address] = {
                    'name': f"MBus Meter {address}",
                    'manufacturer': ydata['manufacturer'],
                    'address': address,
                    'last_seen': time.time(),
                    'records': recs  # Speichere Records für Discovery
                }
                
                # Publiziere Device-Status
                if self.mqtt_client:
                    self.mqtt_client.publish(f"device/{address}/status", "online")

                return ydata
            
        except serial.SerialException as e:
            print(e)
        return None

    def read_standard_data(self, ser, address):
        """
        Read standard data from device (REQ_UD1 or select frame)
        """
        frame = None
        
        if meterbus.is_primary_address(address):
            print(f"Reading data from primary address {address}")
            if self.ping_address(ser, address, 2, read_echo=False):
                self.send_request_frame_ud1(ser, address, read_echo=False)
                frame = meterbus.load(
                    meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
            else:
                print("no reply")

        elif meterbus.is_secondary_address(address):
            print(f"Reading data from secondary address {address}")
            meterbus.send_select_frame(ser, address, False)
            try:
                frame = meterbus.load(meterbus.recv_frame(ser, 1))
            except meterbus.MBusFrameDecodeError as e:
                frame = e.value

            # Ensure that the select frame request was handled by the slave
            assert isinstance(frame, meterbus.TelegramACK)

            meterbus.send_request_frame(ser, meterbus.ADDRESS_NETWORK_LAYER, read_echo=False)
            time.sleep(0.3)
            frame = meterbus.load(meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
        
        return frame

    def get_sensor_name_from_unit(self, unit, index):
        """
        Bestimmt einen aussagekräftigen Sensor-Namen basierend auf der Einheit.
        :param unit: Die Einheit des Sensors (z.B. "W", "kWh", "V", "A")
        :param index: Der Index falls kein Name gefunden wird
        :return: Ein aussagekräftiger Name für den Sensor
        """
        if not unit or unit.lower() == "none":
            return f"Zählerstand {index}"
        
        unit_lower = unit.lower()
        
        # Energie-Einheiten
        if unit_lower in ["kwh", "wh", "mwh", "gwh"]:
            return f"Energie ({unit})"
        elif unit_lower in ["kvarh", "varh"]:
            return f"Blindenergie ({unit})"
        
        # Leistungs-Einheiten
        elif unit_lower in ["w", "kw", "mw", "gw"]:
            return f"Wirkleistung ({unit})"
        elif unit_lower in ["var", "kvar", "mvar"]:
            return f"Blindleistung ({unit})"
        elif unit_lower in ["va", "kva", "mva"]:
            return f"Scheinleistung ({unit})"
        
        # Elektrische Größen
        elif unit_lower in ["v", "kv", "mv"]:
            return f"Spannung ({unit})"
        elif unit_lower in ["a", "ma", "ka"]:
            return f"Strom ({unit})"
        elif unit_lower in ["hz", "khz"]:
            return f"Frequenz ({unit})"
        elif unit_lower in ["°", "deg", "degree"]:
            return f"Phasenwinkel ({unit})"
        
        # Faktoren und Verhältnisse
        elif unit_lower in ["", "1", "none"] or "cos" in unit_lower:
            if "cos" in unit_lower:
                return "Leistungsfaktor (cos φ)"
            else:
                return f"Faktor {index}"
        
        # Volumetrische Einheiten
        elif unit_lower in ["m³", "m3", "l", "liter"]:
            return f"Volumen ({unit})"
        elif unit_lower in ["m³/h", "m3/h", "l/h", "l/min"]:
            return f"Volumenstrom ({unit})"
        
        # Temperatur
        elif unit_lower in ["°c", "°f", "k", "celsius", "fahrenheit", "kelvin"]:
            return f"Temperatur ({unit})"
        
        # Druck
        elif unit_lower in ["bar", "mbar", "pa", "kpa", "mpa"]:
            return f"Druck ({unit})"
        
        # Zeit
        elif unit_lower in ["s", "min", "h", "d", "sec", "hour", "day"]:
            return f"Zeit ({unit})"
        
        # Fallback: Generischer Name mit Einheit
        else:
            return f"Messwert {index} ({unit})"

    def publish_homeassistant_discovery(self, address, data):
        """
        Publish Home Assistant MQTT auto-discovery configuration for each record of a specific device.
        :param address: The address of the M-Bus device.
        :param data: The data structure containing the meter's attributes.
        """
        if self.mqtt_client is None:
            print("MQTT client is not initialized. Cannot publish discovery.")
            return
            
        records = data.get("records", [])
        for idx, record in enumerate(records):
            # Verwende den Namen falls vorhanden, sonst generischen Namen
            sensor_name = record.get("name", f"Record {idx}")
            key = f"record_{idx}"
            object_id = f"mbus_meter_{address}_{key}"
            
            # Unit of measurement: nur setzen wenn nicht 'none' oder leer
            unit = record.get("unit", "")
            
            payload = {
                "name": f"{sensor_name} ({address})",
                "state_topic": f"{self.mqtt_client.topic_prefix}/meter/{address}",
                "value_template": f"{{{{ value_json.records[{idx}].value }}}}",
                "unique_id": object_id,
                "device": {
                    "identifiers": [f"mbus_meter_{address}"],
                    "name": f"MBus Meter {address}",
                    "manufacturer": data.get("manufacturer", "Unknown"),
                    "model": data.get("medium", "Unknown"),
                    "sw_version": data.get("identification", ""),
                },
            }
            
            # Unit nur hinzufügen wenn sie nicht 'none' oder leer ist
            if unit and unit.lower() != "none":
                payload["unit_of_measurement"] = unit
            
            # Setze passende Icons basierend auf dem Sensor-Typ
            if "spannung" in sensor_name.lower() or "voltage" in sensor_name.lower():
                payload["icon"] = "mdi:lightning-bolt"
            elif "strom" in sensor_name.lower() or "current" in sensor_name.lower():
                payload["icon"] = "mdi:current-ac"
            elif "leistung" in sensor_name.lower() or "power" in sensor_name.lower():
                payload["icon"] = "mdi:flash"
            elif "energie" in sensor_name.lower() or "energy" in sensor_name.lower():
                payload["icon"] = "mdi:lightning-bolt-circle"
            elif "frequenz" in sensor_name.lower() or "frequency" in sensor_name.lower():
                payload["icon"] = "mdi:sine-wave"
            elif "cos" in sensor_name.lower():
                payload["icon"] = "mdi:cosine-wave"
            else:
                payload["icon"] = "mdi:gauge"
            
            self.mqtt_client.publish_discovery("sensor", object_id, payload)
            print(f"Published Home Assistant discovery for {sensor_name} on device {address}")

    def publish_meter_data(self, address, data):
        """
        Publish M-Bus meter data to MQTT.
        :param address: The address of the M-Bus device.
        :param data: The decoded data from the meter.
        """
        topic = f"meter/{address}"
        if isinstance(data, dict):
            import decimal
            class DecimalEncoder(json.JSONEncoder):
                def default(self, o):
                    if isinstance(o, decimal.Decimal):
                        return round(float(o), 4)
                    elif isinstance(o, float):
                        return round(o, 4)
                    return super().default(o)

            payload = json.dumps(data, cls=DecimalEncoder)
            if self.mqtt_client is not None:
                self.mqtt_client.publish(topic, payload)
                # print(f"Published data for device {address} to MQTT: {payload}")
            else:
                print("MQTT client is not initialized. Cannot publish data.")
        else:
            print(f"Data for device {address} is not in expected format, skipping publish.")
            print(f"Data({type(data)}): {data}")

    def start(self, scan_interval_minutes=60):
        """
        Perform a one-time scan for devices on startup, then continuously read data from all detected devices.
        Rescans for new devices every scan_interval_minutes.
        
        :param scan_interval_minutes: Intervall in Minuten für erneutes Scannen nach neuen Geräten (Standard: 60 Min)
        """
        # Initial scan for devices on startup
        self.scan_devices()
        
        print(f"Detected devices: {self.devices}")

        # Nach erfolgreichem Scan: Zentrale Discovery auslösen
        if self.mqtt_client and self.devices:
            print("[INFO] M-Bus Scan abgeschlossen - starte Discovery in 2 Sekunden...")
            threading.Timer(2.0, self.mqtt_client.send_all_discovery).start()

        # Starte regelmäßiges Scannen im Hintergrund
        self.start_periodic_scan(scan_interval_minutes)

        # Continuously read data from all detected devices
        try:
            last_data_read = {}  # Tracking für Datenänderungen
            
            while True:
                for device in self.devices:
                    data = self.read_data_from_device(device)
                    if data:
                        # Nur loggen wenn sich Daten geändert haben
                        current_values = [rec.get('value') for rec in data.get('records', [])]
                        if last_data_read.get(device) != current_values:
                            print(f"Received {len(data.get('records', []))} records from device {device}")
                            last_data_read[device] = current_values
                        
                        self.publish_meter_data(device, data)
                    else:
                        # Device offline - publiziere offline Status
                        if self.mqtt_client:
                            self.mqtt_client.publish(f"device/{device}/status", "offline")
                
                # Kurze Pause zwischen den Zyklen
                time.sleep(1)
        except KeyboardInterrupt:
            print("[INFO] M-Bus Datenlesung beendet durch Benutzer")
        except Exception as e:
            print(f"[ERROR] Fehler beim Lesen der M-Bus Daten: {e}")
            raise
        finally:
            print("[INFO] M-Bus Service wird beendet...")
            #time.sleep(10)  # Wait 10 seconds before reading again

    
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
                    if match not in self.devices:  # Duplikatsprüfung
                        print("Device found with id {0} ({1}), using mask {2}".format(
                        match, manufacturer, new_mask))
                        self.devices.append(match)  # Store the found device
                    else:
                        print("Device {0} already known, skipping".format(match))
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

    def send_request_frame_ud1(self, ser, address, read_echo=False):
        """
        Sende einen REQ_UD1 (Class 2 Data) Request-Frame an die angegebene Adresse.
        """
        frame = meterbus.TelegramShort()
        frame.header.cField.parts = [
            meterbus.CONTROL_MASK_REQ_UD1 | meterbus.CONTROL_MASK_DIR_M2S  # 0x53
        ]
        frame.header.aField.parts = [address]
        meterbus.serial_send(ser, frame, read_echo)
        return frame

    def send_selective_readout(self, ser, address, dib, vib):
        """
        Sende ein SND_UD-Frame mit gewünschtem DIB/VIB an das Gerät.
        """
        frame = meterbus.TelegramLong()
        frame.header.cField.parts = [
            meterbus.CONTROL_MASK_SND_UD | meterbus.CONTROL_MASK_DIR_M2S
        ]
        frame.header.aField.parts = [address]
        # DIB/VIB als User Data
        frame.body.bodyHeader.ci_field.parts = [0x51]  # CI-Field für "selective readout"
        # Versuche verschiedene Attributnamen für die Payload
        if hasattr(frame.body, 'bodyPayload'):
            frame.body.bodyPayload = bytes([dib, vib])
        elif hasattr(frame.body, 'payload'):
            frame.body.payload = bytes([dib, vib])
        elif hasattr(frame.body, 'body_payload'):
            frame.body.body_payload = bytes([dib, vib])
        else:
            print(f"Available attributes: {dir(frame.body)}")
            raise AttributeError("Could not find payload attribute")
        meterbus.serial_send(ser, frame, read_echo=False)
        return frame

    def read_register(self, ser, address, dib, vib):
        print(f"DIB: {dib} ({type(dib)}), VIB: {vib} ({type(vib)})")
        self.send_selective_readout(ser, address, dib, vib)
        # Jetzt REQ_UD2 senden und Antwort lesen
        meterbus.send_request_frame(ser, address, read_echo=False)
        frame = meterbus.load(meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
        return frame