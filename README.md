# Voice CLI Multiplexer 🎙

Control 5 terminal sessions with your voice. No keyboard needed.

Say **"cli one"** to switch sessions, then speak commands — they get typed into the terminal automatically.

## Install (one command)

```bash
cd ~ && curl -fsSL https://raw.githubusercontent.com/Staveeland/voice-cli/main/install.sh | bash
```

This automatically:
- ✅ Installs all dependencies (Python, tmux, portaudio)
- ✅ Creates a virtual environment with Python packages
- ✅ Installs the `voice-cli` command globally

## Usage

```bash
voice-cli
```

On first run it asks for your OpenAI API key (saved for next time).

This will:
1. Open 5 fresh terminal windows (cli1–cli5)
2. Start listening for voice commands
3. Say "cli one" to switch, then speak to type

## Update

```bash
voice-cli update
```

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

## Uninstall

```bash
rm -rf ~/voice-cli ~/.voice-cli-key
sudo rm $(which voice-cli)
```

## Troubleshooting

**"No API key"** — Run `voice-cli` and paste your key, or set it manually:
```bash
echo "sk-your-key-here" > ~/.voice-cli-key
```

**Microphone not working** — Go to System Settings → Privacy & Security → Microphone → enable Terminal.

**tmux not found** — Run `brew install tmux`

## License

MIT
