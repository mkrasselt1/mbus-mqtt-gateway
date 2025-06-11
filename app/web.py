import serial.tools.list_ports
from flask import Flask, request, render_template
from app.config import Config

app = Flask(__name__)
config = Config()

def get_serial_ports():
    """Returns a list of available serial ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        config.data["mqtt_broker"] = request.form["mqtt_broker"]
        config.data["mqtt_port"] = int(request.form["mqtt_port"])
        config.data["mqtt_topic"] = request.form["mqtt_topic"]
        config.data["mbus_port"] = request.form["mbus_port"]
        config.data["mqtt_username"] = request.form.get("mqtt_username", "")
        config.data["mqtt_password"] = request.form.get("mqtt_password", "")
        config.save()
    serial_ports = get_serial_ports()
    serial_ports.append(config.data["mbus_port"]) # Ensure the current M-Bus port is included
    return render_template("index.html", config=config.data, serial_ports=serial_ports)
