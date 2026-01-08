# M-Bus to MQTT Gateway

## Overview

The **M-Bus to MQTT Gateway** is a Python-based application designed to enable seamless communication between M-Bus (Meter-Bus) devices and an MQTT broker. This gateway reads data from M-Bus devices and publishes it in real-time to an MQTT topic. Additionally, it includes a web-based interface for easy configuration of MQTT and M-Bus settings.

This project is ideal for IoT setups where meter readings (e.g., water, gas, electricity) need to be integrated into an MQTT-enabled ecosystem, such as Home Automation platforms or Cloud-based IoT systems.

---

## Features

- **M-Bus to MQTT Gateway**: Reads data from M-Bus devices and sends it to an MQTT broker.
- **Flexible Connectivity**: Supports both serial ports (COM/USB) and TCP/IP connections (Ethernet converters).
- **Web Interface**: Configure MQTT broker details, M-Bus port settings, and view logs through a user-friendly web interface.
- **Systemd Service**: Automatically starts the gateway as a systemd service on boot.
- **One-Line Installer**: Simplified installation process with a single command.
- **Cross-Platform**: Works on Windows and Linux systems.

---

## Installation

### Prerequisites
- A Linux-based or Windows system.
- Python 3.x installed on your system.
- M-Bus device connected:
  - **Serial**: via USB/COM port (e.g., `/dev/ttyUSB0` or `COM3`)
  - **TCP/IP**: via Ethernet converter (e.g., Waveshare RS485 to PoE)
- An MQTT broker (e.g., Mosquitto, AWS IoT, etc.) for publishing data.

### Installation Steps
1. **Run the One-Line Installer**:
   Open a terminal and execute the following command:
   ```bash
   curl -sSL https://raw.githubusercontent.com/mkrasselt1/mbus-mqtt-gateway/main/installer.sh | bash
   ```
   This will:
   - Clone the repository.
   - Install required dependencies.
   - Create a `systemd` service for the gateway.
   - Start the gateway service.

2. **Access the Web Interface**:
   After installation, open your browser and navigate to:
   ```
   http://<your-server-ip>:5000
   ```
   Use this interface to configure MQTT and M-Bus settings.

---

## Usage

### Running the Gateway
The gateway runs as a systemd service. It automatically starts on boot. You can control the service using the following commands:

- **Check Service Status**:
  ```bash
  sudo systemctl status mbus-mqtt-gateway
  ```

- **Start the Service**:
  ```bash
  sudo systemctl start mbus-mqtt-gateway
  ```

- **Stop the Service**:
  ```bash
  sudo systemctl stop mbus-mqtt-gateway
  ```

- **View Service Logs**:
  ```bash
  sudo journalctl -u mbus-mqtt-gateway -f
  ```

### Configuration Through the Web Interface
1. Navigate to the web interface: `http://<your-server-ip>:5000`.
2. Fill in the required fields for:
   - MQTT Broker Address
   - MQTT Broke (see configuration options below)
3. Click on "Save" to apply the changes.

### M-Bus Connection Options

The gateway supports multiple connection types:

**Serial Connection:**
- Windows: `COM3`, `COM4`, etc.
- Linux: `/dev/ttyUSB0`, `/dev/ttyAMA0`, etc.

**TCP/IP Connection (e.g., Waveshare RS485 to Ethernet):**
- Simple format: `192.168.1.100:8899`
- Explicit: `socket://192.168.1.100:8899`
- RFC2217: `rfc2217://192.168.1.100:8899`

📖 **Detailed TCP/IP Setup Guide**: See [TCP_SETUP.md](TCP_SETUP.md) for complete instructions on using Ethernet converter
   - M-Bus Port
3. Click on "Save" to apply the changes.

---

## Example Workflow

1. **Connect M-Bus Device**:
   Plug your M-Bus device into the system (e.g., via `/dev/ttyUSB0`).

2. **Configure MQTT in the Web Interface**:
   Enter your MQTT broker details (host, port, topic) and M-Bus port (e.g., `/dev/ttyUSB0`) through the web interface.

3. **Publish Data**:
   The gateway reads data from your M-Bus device and publishes it to the specified MQTT topic.

4. **Subscribe to MQTT Topic**:
   Use an MQTT client (e.g., `mosquitto_sub`) to subscribe to the configured topic and view the published data:
   ```bash
   mosquitto_sub -h <mqtt-broker-ip> -p <port> -t <topic>
   ```

---

## Development

### Local Setup
To run the application locally without a systemd service:
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/mbus-mqtt-gateway.git
   cd mbus-mqtt-gateway
   ```

2. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python3 run.py
   ```

### Testing
Unit tests are located in the `tests/` directory. Run the tests using:
```bash
pytest tests/
```

---

## Troubleshooting

- **Web Interface Not Accessible**:
  - Ensure the service is running:
    ```bash
    sudo systemctl status mbus-mqtt-gateway
    ```
  - Check if port `5000` is open on your firewall.

- **No Data Published to MQTT**:
  - Check the M-Bus port configuration in the web interface.
  - Verify the MQTT broker settings.

- **Logs**:
  View logs using:
  ```bash
  sudo journalctl -u mbus-mqtt-gateway -f
  ```

---

## Contributions

Contributions, bug reports, and feature requests are welcome! Feel free to open a pull request or an issue on the [GitHub repository](https://github.com/your-username/mbus-mqtt-gateway).

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
