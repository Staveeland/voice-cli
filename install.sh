#!/bin/bash
set -e

# ─── Voice CLI Multiplexer — One-command installer ─────────────────────────
# Usage: curl -fsSL https://raw.githubusercontent.com/Staveeland/voice-cli/main/install.sh | bash

REPO="https://github.com/Staveeland/voice-cli.git"
INSTALL_DIR="$HOME/voice-cli"
CONFIG_FILE="$HOME/.voice-cli-key"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     🎙  Voice CLI Multiplexer — Installer    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── Check OS ──────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ This tool requires macOS (for microphone access)."
    exit 1
fi

# ─── Check/install Homebrew ────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo "📦 Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for this session
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
fi

# ─── Check/install Python 3 ───────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "📦 Installing Python 3..."
    brew install python3
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION"

# ─── Check/install tmux ───────────────────────────────────────────────────
if ! command -v tmux &>/dev/null; then
    echo "📦 Installing tmux..."
    brew install tmux
fi
echo "✅ tmux $(tmux -V | cut -d' ' -f2)"

# ─── Check/install portaudio ──────────────────────────────────────────────
if ! brew list portaudio &>/dev/null 2>&1; then
    echo "📦 Installing portaudio (needed for microphone access)..."
    brew install portaudio
fi
echo "✅ portaudio"

# ─── Clone or update repo ─────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "📥 Updating voice-cli..."
    cd "$INSTALL_DIR"
    git pull --quiet
else
    echo "📥 Downloading voice-cli..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ─── Create venv & install Python deps ────────────────────────────────────
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$INSTALL_DIR/.venv"
fi

echo "📦 Installing Python dependencies..."
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
echo "✅ Python dependencies installed"

# ─── API key setup ────────────────────────────────────────────────────────
if [ -f "$CONFIG_FILE" ]; then
    echo "✅ API key found at $CONFIG_FILE"
else
    echo ""
    echo "🔑 OpenAI API key required (for Whisper speech-to-text)"
    echo "   Get one at: https://platform.openai.com/api-keys"
    echo ""
    read -rp "   Paste your API key: " api_key
    if [[ -z "$api_key" ]]; then
        echo "❌ No API key provided. You can set it later by running voice-cli again."
    else
        echo "$api_key" > "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE"
        echo "✅ API key saved to $CONFIG_FILE"
    fi
fi

# ─── Create launcher script ───────────────────────────────────────────────
LAUNCHER="/usr/local/bin/voice-cli"
if [ -d "/opt/homebrew/bin" ]; then
    LAUNCHER="/opt/homebrew/bin/voice-cli"
fi

sudo tee "$LAUNCHER" > /dev/null << 'LAUNCHER_SCRIPT'
#!/bin/bash
INSTALL_DIR="$HOME/voice-cli"
CONFIG_FILE="$HOME/.voice-cli-key"

# Load API key
if [ -f "$CONFIG_FILE" ]; then
    export OPENAI_API_KEY=$(cat "$CONFIG_FILE")
elif [ -n "$OPENAI_API_KEY" ]; then
    : # already set
else
    echo "🔑 No API key found. Enter your OpenAI API key:"
    read -rp "   API key: " api_key
    if [[ -z "$api_key" ]]; then
        echo "❌ API key required. Get one at: https://platform.openai.com/api-keys"
        exit 1
    fi
    echo "$api_key" > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    export OPENAI_API_KEY="$api_key"
    echo "✅ Saved for next time."
fi

# Ensure tmux sessions exist
TMUX_BIN=$(which tmux 2>/dev/null || echo /opt/homebrew/bin/tmux)
for i in 1 2 3 4 5; do
    name="cli${i}"
    if ! $TMUX_BIN has-session -t "$name" 2>/dev/null; then
        $TMUX_BIN new-session -d -s "$name" -x 120 -y 30
    fi
done

# Open Terminal windows for each session
osascript -e '
tell application "Terminal"
    activate
    repeat with i from 1 to 5
        set sess to "cli" & i
        do script "tmux attach -t " & sess
        delay 0.3
    end repeat
end tell
' 2>/dev/null &

echo "🖥  Opening 5 terminal windows..."
sleep 1

# Start voice CLI
exec "$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/main.py"
LAUNCHER_SCRIPT

sudo chmod +x "$LAUNCHER"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     ✅  Installation complete!               ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Start anytime by typing:                    ║"
echo "║                                              ║"
echo "║    voice-cli                                 ║"
echo "║                                              ║"
echo "║  This will:                                  ║"
echo "║  • Open 5 terminal windows (cli1-cli5)       ║"
echo "║  • Start listening for voice commands        ║"
echo "║  • Say \"cli one\" to switch sessions          ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
read -rp "🎙 Start voice-cli now? [Y/n] " start_now
if [[ "$start_now" != "n" && "$start_now" != "N" ]]; then
    exec voice-cli
fi
