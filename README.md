# Voice CLI Multiplexer 🎙

Control 5 terminal sessions with your voice. No keyboard needed.

Say **"cli one"** to switch sessions, then speak commands — they get typed into the terminal automatically.

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/Staveeland/voice-cli/main/install.sh | bash
```

This automatically:
- ✅ Installs all dependencies (Python, tmux, portaudio)
- ✅ Asks for your OpenAI API key (saved securely for next time)
- ✅ Opens 5 terminal windows ready to use
- ✅ Starts listening for voice commands

## Start (after install)

```bash
voice-cli
```

That's it. 5 terminal windows open, voice control starts.

## Voice Commands

| Say this | What happens |
|---|---|
| **"cli one"** / "cli en" | Switch to terminal 1 |
| **"cli two"** / "cli to" | Switch to terminal 2 |
| **"cli three"** / "cli tre" | Switch to terminal 3 |
| **"cli four"** / "cli fire" | Switch to terminal 4 |
| **"cli five"** / "cli fem" | Switch to terminal 5 |
| **"send it"** / "enter" | Press Enter |
| **"clear it"** / "avbryt" | Ctrl+C |
| **"tab"** | Tab (autocomplete) |
| **"up"** / "opp" | Arrow up (previous command) |
| **"down"** / "ned" | Arrow down |
| **"escape"** | Escape key |
| **"undo"** / "angre" | Ctrl+Z |
| **"save"** / "lagre" | Ctrl+S |
| **"delete line"** | Clear current line |
| Anything else | Gets typed as text |

Works in both **English** and **Norwegian**.

## Requirements

- macOS (for microphone access)
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))

Everything else is installed automatically.

## Manual Install

If you prefer to set up manually:

```bash
git clone https://github.com/Staveeland/voice-cli.git
cd voice-cli
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install tmux portaudio
.venv/bin/python3 main.py
```

## How It Works

1. Listens to your microphone continuously
2. Detects when you start/stop speaking (energy-based VAD)
3. Sends audio to OpenAI Whisper for transcription
4. Matches text against voice commands
5. Routes commands to the active tmux session

## Troubleshooting

**"No API key"** — Run `voice-cli` and paste your key when prompted, or:
```bash
echo "sk-your-key-here" > ~/.voice-cli-key
```

**Microphone not working** — macOS may ask for permission. Go to System Settings → Privacy & Security → Microphone → enable Terminal.

**tmux not found** — Run `brew install tmux`

## License

MIT
