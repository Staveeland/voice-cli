# Voice CLI Multiplexer 🎙

Control multiple tmux CLI sessions with your voice — no keyboard needed.

## Features

- **5 tmux sessions** (cli1–cli5) controlled entirely by voice
- **OpenAI Whisper API** for accurate speech-to-text
- **Supports English and Norwegian** commands
- **Energy-based VAD** — detects when you start/stop speaking
- **Visual feedback** — shows active session and transcription status

## Quick Start

One command setup:

```bash
./setup.sh
```

Then run:

```bash
python3 main.py
```

`./setup.sh` runs guided setup and handles:

- Python dependency installation
- `tmux` + `portaudio` checks (and optional Homebrew install)
- API key entry (saved to `.env` as `OPENAI_API_KEY`)
- Optional `cli1`-`cli5` tmux session creation

## Voice Commands

| Command | Action |
|---|---|
| "cli one" / "cli en" | Switch to cli1 |
| "cli two" / "cli to" | Switch to cli2 |
| "cli three" / "cli tre" | Switch to cli3 |
| "cli four" / "cli fire" | Switch to cli4 |
| "cli five" / "cli fem" | Switch to cli5 |
| "execute" / "exectute" | Press Enter |
| "clear it" / "avbryt" | Ctrl+C |
| "tab" | Tab key |
| "up" / "opp" | Arrow up |
| "down" / "ned" | Arrow down |
| "escape" | Escape key |
| "undo" / "angre" | Ctrl+Z |
| "save" / "lagre" | Ctrl+S |
| "delete line" | Ctrl+U |
| anything else | Typed as text |

## Environment

`python3 main.py setup` will ask for your API key and save it to `.env`.

You can also set `OPENAI_API_KEY` manually:

```bash
export OPENAI_API_KEY=sk-...
```

## Requirements

- macOS with microphone access
- Python 3.10+
- tmux
- portaudio (`brew install portaudio`)

## How It Works

1. Continuously listens to microphone via `sounddevice`
2. Energy-based VAD detects speech start/stop
3. Audio sent to OpenAI Whisper API for transcription
4. Text matched against command patterns
5. Commands routed to active tmux session via `tmux send-keys`
