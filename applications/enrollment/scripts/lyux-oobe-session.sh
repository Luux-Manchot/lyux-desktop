#!/usr/bin/env bash
# Lance l'assistant OOBE LyuX dans une session X11/XCB dédiée avant SDDM.
set -u

export QT_QPA_PLATFORM=xcb
export LYUX_OOBE_EXIT_ON_ENROLL=1
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/0}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Appliquer la disposition clavier système si disponible sous X11
if command -v setxkbmap >/dev/null 2>&1; then
    setxkbmap fr 2>/dev/null || true
fi

exec /usr/bin/python3 "${1:-/opt/lyux/apps/enrollment/src/oobe_gui.py}"
