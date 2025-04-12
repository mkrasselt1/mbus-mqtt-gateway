#!/bin/bash

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo "Installing M-Bus to MQTT Gateway..."

# Update package list and install git if it's not already installed
if command_exists git; then
    echo "Git is already installed."
else
    echo "Git is not installed. Installing Git..."
    sudo apt update
    sudo apt install -y git
fi

# Clone the repository
REPO_URL="https://github.com/mkrasselt1/mbus-mqtt-gateway.git"
INSTALL_DIR="/opt/mbus-mqtt-gateway"

if [ -d "$INSTALL_DIR" ]; then
    echo "The repository already exists. Pulling the latest changes..."
    sudo git -C "$INSTALL_DIR" pull
else
    echo "Cloning the repository..."
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Install Python and pip if not already installed
if command_exists python3; then
    echo "Python 3 is already installed."
else
    echo "Python 3 is not installed. Installing Python 3..."
    sudo apt install -y python3
fi

if command_exists pip3; then
    echo "pip is already installed."
else
    echo "pip is not installed. Installing pip..."
    sudo apt install -y python3-pip
fi

# Install Python dependencies
echo "Installing Python dependencies..."
sudo pip3 install -r "$INSTALL_DIR/requirements.txt"

# Create a systemd service file
SERVICE_FILE="/etc/systemd/system/mbus-mqtt-gateway.service"

echo "Creating systemd service..."
sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=MBus to MQTT Gateway Service
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/run.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd, enable and start the service
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and starting the M-Bus to MQTT Gateway service..."
sudo systemctl enable mbus-mqtt-gateway
sudo systemctl start mbus-mqtt-gateway

# Display the service status
sudo systemctl status mbus-mqtt-gateway

echo "Installation complete. The M-Bus to MQTT Gateway service is now running."
echo "You can view logs using: sudo journalctl -u mbus-mqtt-gateway -f"
