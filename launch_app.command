#!/bin/bash
# SafetyCulture Tools — Mac Launcher (Terminal fallback)
# Double-click this file if SafetyCulture Tools.app doesn't work on your system.

cd "$(dirname "$0")"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed."
    echo "Download it from https://www.python.org/downloads/ and try again."
    read -rp "Press Enter to close..."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Setting up virtual environment (first run only)..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies if needed
if ! python3 -c "import streamlit; import webview" 2>/dev/null; then
    echo "Installing dependencies (first run only)..."
    pip install -r requirements.txt --quiet
fi

echo "Starting SafetyCulture Tools..."

# Minimize the terminal window, then launch the native app window
osascript -e 'tell application "Terminal" to set miniaturized of front window to true' 2>/dev/null
python3 launcher.py
