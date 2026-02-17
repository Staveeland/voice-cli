# Voice CLI Multiplexer 🎙

Control multiple tmux CLI sessions with your voice — no keyboard needed.

## Features

- **5 tmux sessions** (cli1–cli5) controlled entirely by voice
- **OpenAI Whisper API** for accurate speech-to-text
- **Supports English and Norwegian** commands
- **Energy-based VAD** — detects when you start/stop speaking
- **Visual feedback** — shows active session and transcription status

## Quick Start

One command install (clone + dependencies + guided setup):

```bash
bash -lc 'set -euo pipefail; if ! command -v brew >/dev/null 2>&1; then NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; fi; if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi; command -v git >/dev/null 2>&1 || brew install git; if [ -d "$HOME/.voice-cli/.git" ]; then git -C "$HOME/.voice-cli" fetch origin && git -C "$HOME/.voice-cli" checkout main && git -C "$HOME/.voice-cli" pull --ff-only origin main; else git clone --branch main https://github.com/Staveeland/voice-cli.git "$HOME/.voice-cli"; fi; cd "$HOME/.voice-cli" && ./install.sh'
```

Non-interactive variant:

```bash
OPENAI_API_KEY=sk-... bash -lc 'set -euo pipefail; if ! command -v brew >/dev/null 2>&1; then NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; fi; if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi; command -v git >/dev/null 2>&1 || brew install git; if [ -d "$HOME/.voice-cli/.git" ]; then git -C "$HOME/.voice-cli" fetch origin && git -C "$HOME/.voice-cli" checkout main && git -C "$HOME/.voice-cli" pull --ff-only origin main; else git clone --branch main https://github.com/Staveeland/voice-cli.git "$HOME/.voice-cli"; fi; cd "$HOME/.voice-cli" && ./install.sh'
```

If the repo is private, GitHub will ask for auth during `git clone`.

Then run:

```bash
cd ~/.voice-cli && python3 main.py
```

`install.sh` does this automatically:

- Clones or updates `https://github.com/Staveeland/voice-cli` to `~/.voice-cli`
- Installs Homebrew if missing
- Python dependency installation
- Creates and uses a project virtualenv (`~/.voice-cli/.venv`)
- Installs `python3` (3.10+), `git`, `tmux`, and `portaudio` if missing
- Prompts for API key and saves it to `.env`
- Creates `cli1`-`cli5` tmux sessions

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

Installer asks for your API key and saves it to `.env`.

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
