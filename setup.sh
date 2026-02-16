#!/bin/bash
set -e
echo "=== Voice CLI Setup ==="

# Check Python
python3 --version || { echo "Python 3 required"; exit 1; }

# Check tmux
which tmux || { echo "Installing tmux..."; brew install tmux; }

# Install portaudio (needed by sounddevice)
brew list portaudio &>/dev/null || { echo "Installing portaudio..."; brew install portaudio; }

# Install Python deps
pip3 install -r requirements.txt

echo "✅ Setup complete! Run: ./tmux-setup.sh && python3 main.py"
