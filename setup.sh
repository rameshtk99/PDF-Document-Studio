#!/bin/bash

echo "Installing system dependencies..."
# Use pkexec instead of sudo for better desktop integration
pkexec apt-get update
pkexec apt-get install -y python3-tk python3-pip

echo "Installing Python packages..."
pip3 install --user -r requirements.txt

echo "Setup complete! You can now run: python3 main.py"
