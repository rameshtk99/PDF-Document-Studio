#!/bin/bash

echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-tk python3-pip

echo "Installing Python packages..."
pip3 install -r requirements.txt

echo "Setup complete! You can now run: python3 main.py"
