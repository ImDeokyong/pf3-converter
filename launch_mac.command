#!/bin/bash
# PF3 Converter launcher for macOS. Double-click in Finder, or run: ./launch_mac.command
cd "$(dirname "$0")" || exit 1
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys, tkinter; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ with Tk was not found. Install it from https://www.python.org/downloads/macos/"
  read -r -p "Press Enter to close."; exit 1
fi
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv || exit 1
fi
.venv/bin/python -m pip install -q -r requirements.txt || { read -r -p "Install failed. Press Enter to close."; exit 1; }
exec .venv/bin/python app.py
