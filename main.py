#!/usr/bin/env python3
"""Voice-controlled CLI multiplexer for macOS using tmux + OpenAI Whisper."""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ─── Config ───────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
FRAME_MS = 30  # ms per VAD frame
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

# VAD thresholds
ENERGY_THRESHOLD = 500        # RMS energy to consider as speech
SILENCE_FRAMES = 30           # ~900ms of silence to end utterance
MIN_SPEECH_FRAMES = 5         # minimum frames to count as speech (~150ms)
MAX_RECORD_SECONDS = 15       # max single utterance

SESSIONS = [f"cli{i}" for i in range(1, 6)]
DEFAULT_SESSION = "cli1"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key

    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            return cfg.get("messages", {}).get("tts", {}).get("openai", {}).get("apiKey", "").strip()
        except Exception:
            return ""

    return ""


def ensure_runtime_dependencies() -> bool:
    missing = []
    if np is None:
        missing.append("numpy")
    if sd is None:
        missing.append("sounddevice")
    if load_dotenv is None:
        missing.append("python-dotenv")
    if OpenAI is None:
        missing.append("openai")

    if not missing:
        return True

    print(f"❌ Missing dependencies: {', '.join(missing)}")
    print("Run `python3 main.py setup` to install everything.")
    return False


def read_env_var(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ""

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        var_name, value = stripped.split("=", 1)
        if var_name.strip() == key:
            value = value.strip().strip("'").strip('"')
            return value
    return ""


def upsert_env_var(env_path: Path, key: str, value: str):
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            lines[idx] = f"{key}={value}"
            updated = True
            break

    if not updated:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please answer y or n.")


def mask_secret(secret: str) -> str:
    if len(secret) <= 10:
        return "*" * len(secret)
    return f"{secret[:6]}...{secret[-4:]}"

# ─── Command patterns ─────────────────────────────────────────────────────────

# Map spoken words to session names (English + Norwegian)
SESSION_PATTERNS = {
    r"\bcli\s*(one|1|en)\b": "cli1",
    r"\bcli\s*(two|2|to)\b": "cli2",
    r"\bcli\s*(three|3|tre)\b": "cli3",
    r"\bcli\s*(four|4|fire)\b": "cli4",
    r"\bcli\s*(five|5|fem)\b": "cli5",
}

# Special commands → tmux keys
SPECIAL_COMMANDS = {
    r"^(send it|enter|kjør|send|trykk enter)$": "Enter",
    r"^(clear it|clear|avbryt|stopp)$": "C-c",
    r"^(tab|tabb)$": "Tab",
    r"^(up|opp|pil opp)$": "Up",
    r"^(down|ned|pil ned)$": "Down",
    r"^(escape|esc)$": "Escape",
    r"^(undo|angre)$": "C-z",
    r"^(save|lagre)$": "C-s",
    r"^(delete line|slett linje)$": "C-u",
}


# ─── Display ──────────────────────────────────────────────────────────────────

class Display:
    """Terminal status display."""

    def __init__(self):
        self.active_session = DEFAULT_SESSION
        self.status = "Ready"
        self.last_text = ""
        self.lock = threading.Lock()

    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                setattr(self, k, v)
            self._render()

    def _render(self):
        sessions_str = "  ".join(
            f"\033[1;32m[{s}]\033[0m" if s == self.active_session else s
            for s in SESSIONS
        )
        sys.stdout.write(
            f"\r\033[K🎙  {self.status} │ {sessions_str} │ {self.last_text[-60:]}"
        )
        sys.stdout.flush()


# ─── VAD (energy-based) ──────────────────────────────────────────────────────

class EnergyVAD:
    """Simple energy-based voice activity detection."""

    def __init__(self, threshold=ENERGY_THRESHOLD):
        self.threshold = threshold

    def is_speech(self, frame: np.ndarray) -> bool:
        rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2))
        return rms > self.threshold


# ─── Audio recorder ───────────────────────────────────────────────────────────

class AudioRecorder:
    """Records audio from mic, uses VAD to detect utterances."""

    def __init__(self, vad: EnergyVAD, on_utterance):
        self.vad = vad
        self.on_utterance = on_utterance
        self.running = False
        self._buffer = []
        self._silence_count = 0
        self._speech_count = 0
        self._recording = False

    def start(self):
        self.running = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=FRAME_SAMPLES,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        self.running = False
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass  # ignore xruns
        frame = indata[:, 0].copy()
        is_speech = self.vad.is_speech(frame)

        if not self._recording:
            if is_speech:
                self._speech_count += 1
                self._buffer.append(frame)
                if self._speech_count >= MIN_SPEECH_FRAMES:
                    self._recording = True
                    self._silence_count = 0
            else:
                self._speech_count = 0
                self._buffer.clear()
        else:
            self._buffer.append(frame)
            if not is_speech:
                self._silence_count += 1
                if self._silence_count >= SILENCE_FRAMES:
                    self._finish_utterance()
            else:
                self._silence_count = 0

            # Max length guard
            max_frames = int(MAX_RECORD_SECONDS * SAMPLE_RATE / FRAME_SAMPLES)
            if len(self._buffer) >= max_frames:
                self._finish_utterance()

    def _finish_utterance(self):
        audio = np.concatenate(self._buffer)
        self._buffer.clear()
        self._recording = False
        self._silence_count = 0
        self._speech_count = 0
        # Process in separate thread to not block audio
        threading.Thread(target=self.on_utterance, args=(audio,), daemon=True).start()


# ─── Whisper transcription ────────────────────────────────────────────────────

class Transcriber:
    def __init__(self, api_key: str):
        if OpenAI is None:
            raise RuntimeError("openai dependency is missing")
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, audio: np.ndarray) -> str:
        """Send audio to Whisper API, return text."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # int16
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        buf.name = "audio.wav"

        try:
            result = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=buf,
                language=None,  # auto-detect (supports Norwegian + English)
                prompt="cli one, cli two, cli three, cli four, cli five, send it, clear it, tab, escape, undo, save, delete line",
            )
            return result.text.strip()
        except Exception as e:
            return f"[ERROR: {e}]"


# ─── Tmux controller ─────────────────────────────────────────────────────────

class TmuxController:
    def __init__(self):
        self.active = DEFAULT_SESSION

    def session_exists(self, name: str) -> bool:
        r = subprocess.run(["tmux", "has-session", "-t", name],
                           capture_output=True)
        return r.returncode == 0

    def send_keys(self, keys: str, literal: bool = True):
        cmd = ["tmux", "send-keys", "-t", self.active]
        if literal:
            cmd += ["-l", keys]
        else:
            cmd.append(keys)
        subprocess.run(cmd, capture_output=True)

    def send_special(self, key: str):
        self.send_keys(key, literal=False)

    def switch(self, session: str) -> bool:
        if self.session_exists(session):
            self.active = session
            return True
        return False

    def ensure_sessions(self):
        for s in SESSIONS:
            if not self.session_exists(s):
                subprocess.run(["tmux", "new-session", "-d", "-s", s],
                               capture_output=True)


# ─── Command processor ───────────────────────────────────────────────────────

class CommandProcessor:
    def __init__(self, tmux: TmuxController, display: Display):
        self.tmux = tmux
        self.display = display

    def process(self, text: str):
        if not text or text.startswith("[ERROR"):
            self.display.update(status="⚠ Error", last_text=text)
            return

        normalized = text.lower().strip().rstrip(".")

        # Check session switch
        for pattern, session in SESSION_PATTERNS.items():
            if re.search(pattern, normalized, re.IGNORECASE):
                if self.tmux.switch(session):
                    self.display.update(
                        active_session=session,
                        status="Switched",
                        last_text=f"→ {session}",
                    )
                return

        # Check special commands
        for pattern, key in SPECIAL_COMMANDS.items():
            if re.match(pattern, normalized, re.IGNORECASE):
                self.tmux.send_special(key)
                self.display.update(status="Sent key", last_text=f"⌨ {key}")
                return

        # Default: type text literally
        self.tmux.send_keys(text)
        self.display.update(status="Typed", last_text=text)


# ─── CLI / Main ───────────────────────────────────────────────────────────────

def run_setup() -> int:
    root = project_root()
    requirements_path = root / "requirements.txt"
    tmux_setup_script = root / "tmux-setup.sh"
    env_path = root / ".env"

    print("=== Voice CLI Interactive Setup ===")
    print(f"Project: {root}")
    print()

    if sys.version_info < (3, 10):
        print(f"❌ Python 3.10+ is required. Current version: {sys.version.split()[0]}")
        return 1
    print(f"✅ Python version: {sys.version.split()[0]}")

    if prompt_yes_no("Install Python dependencies from requirements.txt?", default=True):
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)]
        )
        if result.returncode != 0:
            print("❌ Failed to install Python dependencies.")
            return 1
        print("✅ Python dependencies installed.")

    brew_path = shutil.which("brew")
    tmux_path = shutil.which("tmux")
    if tmux_path:
        print(f"✅ tmux found: {tmux_path}")
    else:
        print("⚠ tmux not found.")
        if brew_path and prompt_yes_no("Install tmux with Homebrew now?", default=True):
            install_tmux = subprocess.run(["brew", "install", "tmux"])
            if install_tmux.returncode == 0:
                print("✅ tmux installed.")
            else:
                print("❌ tmux installation failed.")
        else:
            print("Install tmux manually: brew install tmux")

    if brew_path:
        portaudio_installed = (
            subprocess.run(
                ["brew", "list", "portaudio"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode == 0
        )
        if portaudio_installed:
            print("✅ portaudio already installed.")
        elif prompt_yes_no("Install portaudio with Homebrew now?", default=True):
            install_portaudio = subprocess.run(["brew", "install", "portaudio"])
            if install_portaudio.returncode == 0:
                print("✅ portaudio installed.")
            else:
                print("❌ portaudio installation failed.")
        else:
            print("Install portaudio manually: brew install portaudio")
    else:
        print("⚠ Homebrew not found. Install portaudio manually.")

    env_key = read_env_var(env_path, "OPENAI_API_KEY")
    shell_key = os.environ.get("OPENAI_API_KEY", "").strip()
    existing_key = shell_key or env_key
    if existing_key:
        print(f"Current OPENAI_API_KEY: {mask_secret(existing_key)}")

    while True:
        api_key = getpass.getpass("Enter your OPENAI_API_KEY (input hidden): ").strip()
        if not api_key:
            print("OPENAI_API_KEY cannot be empty.")
            continue
        if not api_key.startswith("sk-"):
            if not prompt_yes_no(
                "Key does not start with 'sk-'. Save it anyway?",
                default=False,
            ):
                continue
        upsert_env_var(env_path, "OPENAI_API_KEY", api_key)
        print(f"✅ Saved OPENAI_API_KEY to {env_path}")
        break

    if tmux_setup_script.exists() and prompt_yes_no(
        "Create tmux sessions (cli1-cli5) now?", default=True
    ):
        setup_tmux = subprocess.run(["bash", str(tmux_setup_script)])
        if setup_tmux.returncode != 0:
            print("❌ Failed to create tmux sessions.")
            return 1

    print("\nSetup complete.")
    print("Run `python3 main.py` to start the voice CLI.")
    return 0


def run_voice_cli() -> int:
    if not ensure_runtime_dependencies():
        return 1

    load_dotenv()
    api_key = resolve_api_key()
    if not api_key:
        print("❌ Set OPENAI_API_KEY first. Run `python3 main.py setup`.")
        return 1

    print("\033[2J\033[H")  # clear screen
    print("╔══════════════════════════════════════════════╗")
    print("║     🎙  Voice CLI Multiplexer v1.0          ║")
    print("║     Speak to control your tmux sessions     ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # Init components
    display = Display()
    tmux = TmuxController()
    tmux.ensure_sessions()
    transcriber = Transcriber(api_key)
    processor = CommandProcessor(tmux, display)
    vad = EnergyVAD()

    display.update(status="Listening...")

    def on_utterance(audio: np.ndarray):
        display.update(status="Transcribing...")
        text = transcriber.transcribe(audio)
        if text:
            processor.process(text)
        display.update(status="Listening...")

    recorder = AudioRecorder(vad, on_utterance)

    # Graceful shutdown
    def shutdown(sig, frame):
        print("\n\n👋 Shutting down...")
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        recorder.start()
        print("Press Ctrl+C to quit\n")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown(None, None)
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Voice-controlled tmux CLI"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run", "setup"],
        default="run",
        help="Use 'setup' for guided installation and API key setup.",
    )
    return parser.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    if args.command == "setup":
        return run_setup()
    return run_voice_cli()


if __name__ == "__main__":
    sys.exit(main())
