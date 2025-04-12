#!/bin/bash
echo "Installing MBus to MQTT Gateway..."
sudo apt update
sudo apt install -y python3 python3-pip
pip3 install -r requirements.txt
echo "Installation complete. Run 'python3 run.py' to start the application."
