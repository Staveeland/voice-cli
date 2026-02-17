#!/bin/bash
# Create or attach to voice-cli tmux sessions
set -e

# Avoid colliding with tmux's own TMUX env variable.
unset TMUX

SESSION_PREFIX="cli"
TMUX_BIN="$(command -v tmux 2>/dev/null || echo /opt/homebrew/bin/tmux)"

for i in 1 2 3 4 5; do
    name="${SESSION_PREFIX}${i}"
    if ! "$TMUX_BIN" has-session -t "$name" 2>/dev/null; then
        "$TMUX_BIN" new-session -d -s "$name" -x 120 -y 30
        echo "Created session: $name"
    else
        echo "Session exists: $name"
    fi
done

echo "✅ All 5 CLI sessions ready"
echo "Attach manually: tmux attach -t cli1"
