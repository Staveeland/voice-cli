#!/usr/bin/env python3
"""Voice-controlled CLI multiplexer for macOS using tmux + OpenAI Whisper."""

import io
import os
import re
import sys
import time
import wave
import struct
import signal
import subprocess
import threading
from collections import deque
from pathlib import Path

import numpy as np
import sounddevice as sd
from openai import OpenAI

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

API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not API_KEY:
    _key_file = Path.home() / ".voice-cli-key"
    if _key_file.exists():
        API_KEY = _key_file.read_text().strip()

# Validate: must start with sk-
if not API_KEY or not API_KEY.startswith("sk-"):
    # Clear invalid saved key
    _key_file = Path.home() / ".voice-cli-key"
    if _key_file.exists():
        _key_file.unlink()

    print("🔑 OpenAI API key required (for Whisper speech-to-text)")
    print("   Get one at: https://platform.openai.com/api-keys\n")

    # Ensure we have a real TTY for input
    if not sys.stdin.isatty():
        print("❌ Cannot prompt for API key (not a terminal).")
        print("   Run this command first:")
        print(f'   echo "sk-your-key-here" > ~/.voice-cli-key')
        sys.exit(1)

    API_KEY = input("   Paste your API key: ").strip()
    if not API_KEY or not API_KEY.startswith("sk-"):
        print("❌ Invalid API key. Must start with 'sk-'.")
        sys.exit(1)

    _key_file.write_text(API_KEY)
    _key_file.chmod(0o600)
    print("   ✅ Saved to ~/.voice-cli-key\n")

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
                model="gpt-4o-transcribe",
                file=buf,
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
        self._needs_space = False

    def process(self, text: str):
        if not text or text.startswith("[ERROR"):
            self.display.update(status="⚠ Error", last_text=text)
            return

        normalized = text.lower().strip().rstrip(".")

        # Check session switch
        for pattern, session in SESSION_PATTERNS.items():
            if re.search(pattern, normalized, re.IGNORECASE):
                if self.tmux.switch(session):
                    self._needs_space = False
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
                self._needs_space = False  # reset after Enter, Ctrl+C, etc.
                self.display.update(status="Sent key", last_text=f"⌨ {key}")
                return

        # Default: type text literally (add space between utterances)
        if self._needs_space:
            self.tmux.send_keys(" ")
        self.tmux.send_keys(text)
        self._needs_space = True
        self.display.update(status="Typed", last_text=text)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\033[2J\033[H")  # clear screen
    print()
    print("  \033[1;36m██╗   ██╗ ██████╗ ██╗ ██████╗███████╗\033[0m")
    print("  \033[1;36m██║   ██║██╔═══██╗██║██╔════╝██╔════╝\033[0m")
    print("  \033[1;36m██║   ██║██║   ██║██║██║     █████╗  \033[0m")
    print("  \033[1;36m╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  \033[0m")
    print("  \033[1;36m ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗\033[0m")
    print("  \033[1;36m  ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝\033[0m")
    print("  \033[1;35m     ██████╗██╗     ██╗\033[0m")
    print("  \033[1;35m    ██╔════╝██║     ██║\033[0m")
    print("  \033[1;35m    ██║     ██║     ██║\033[0m")
    print("  \033[1;35m    ██║     ██║     ██║\033[0m")
    print("  \033[1;35m    ╚██████╗███████╗██║\033[0m")
    print("  \033[1;35m     ╚═════╝╚══════╝╚═╝\033[0m")
    print()
    print("  \033[1;37m── Voice-Controlled Terminal Multiplexer ──\033[0m")
    print("  \033[2mv1.2 · Created by Petter Staveland\033[0m")
    print("  \033[2mhttps://github.com/Staveeland/voice-cli\033[0m")
    print()
    print("  \033[33m🎙  Speak to type  │  \"cli one\"–\"cli five\" to switch\033[0m")
    print("  \033[33m⌨  \"send it\" = Enter  │  \"clear it\" = Ctrl+C\033[0m")
    print()
    print("  \033[2m─────────────────────────────────────────────\033[0m")
    print()

    # Init components
    display = Display()
    tmux = TmuxController()
    tmux.ensure_sessions()
    transcriber = Transcriber(API_KEY)
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


if __name__ == "__main__":
    main()
