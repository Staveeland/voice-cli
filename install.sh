#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${VOICE_CLI_REPO_URL:-https://github.com/Staveeland/voice-cli.git}"
BRANCH="${VOICE_CLI_BRANCH:-main}"
INSTALL_DIR="${VOICE_CLI_INSTALL_DIR:-$HOME/.voice-cli}"
BREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

log() {
  printf '%s\n' "$1"
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

ensure_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "This installer currently supports macOS only."
  fi
}

find_brew() {
  if command -v brew >/dev/null 2>&1; then
    command -v brew
    return 0
  fi
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

brew_shellenv() {
  local brew_bin="$1"
  export PATH="$(dirname "$brew_bin"):$PATH"
  eval "$("$brew_bin" shellenv)"
}

ensure_homebrew() {
  local brew_bin
  if brew_bin="$(find_brew)"; then
    brew_shellenv "$brew_bin"
    log "Homebrew found: $brew_bin"
    return
  fi

  log "Homebrew not found. Installing..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL "$BREW_INSTALL_URL")"
  brew_bin="$(find_brew)" || fail "Homebrew installation failed."
  brew_shellenv "$brew_bin"
  log "Homebrew installed: $brew_bin"
}

python_is_310_plus() {
  local py_bin="$1"
  "$py_bin" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

ensure_python() {
  if command -v python3 >/dev/null 2>&1 && python_is_310_plus "$(command -v python3)"; then
    PYTHON_BIN="$(command -v python3)"
    log "Python ready: $("$PYTHON_BIN" --version 2>&1)"
    return
  fi

  log "Installing Python 3.10+..."
  brew install python
  local brew_prefix
  brew_prefix="$(brew --prefix)"
  if [[ -x "$brew_prefix/bin/python3" ]] && python_is_310_plus "$brew_prefix/bin/python3"; then
    PYTHON_BIN="$brew_prefix/bin/python3"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    fail "python3 not found after installation."
  fi

  python_is_310_plus "$PYTHON_BIN" || fail "Python 3.10+ is still unavailable."
  log "Python ready: $("$PYTHON_BIN" --version 2>&1)"
}

ensure_git() {
  if command -v git >/dev/null 2>&1; then
    return
  fi
  log "Installing git..."
  brew install git
  command -v git >/dev/null 2>&1 || fail "git installation failed."
}

clone_or_update_repo() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Updating existing repo at $INSTALL_DIR..."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
    return
  fi

  log "Cloning repo to $INSTALL_DIR..."
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
}

capture_api_key() {
  if [[ -n "${OPENAI_API_KEY:-}" ]]; then
    return
  fi

  if [[ -r /dev/tty ]]; then
    printf "Enter OPENAI_API_KEY: " > /dev/tty
    stty -echo < /dev/tty
    IFS= read -r OPENAI_API_KEY < /dev/tty || true
    stty echo < /dev/tty
    printf "\n" > /dev/tty
    export OPENAI_API_KEY
  fi

  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    fail "OPENAI_API_KEY is required. Re-run with OPENAI_API_KEY set."
  fi
}

run_project_setup() {
  cd "$INSTALL_DIR"
  log "Running automated project setup..."
  OPENAI_API_KEY="$OPENAI_API_KEY" "$PYTHON_BIN" main.py setup --auto
}

print_done() {
  log ""
  log "Install complete."
  log "Project location: $INSTALL_DIR"
  log "Start it with:"
  log "  cd \"$INSTALL_DIR\" && python3 main.py"
}

main() {
  ensure_macos
  ensure_homebrew
  ensure_git
  ensure_python
  clone_or_update_repo
  capture_api_key
  run_project_setup
  print_done
}

main "$@"
