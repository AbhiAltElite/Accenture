#!/usr/bin/env bash
# Linux: open WhyChain in its own window (Chrome, Chromium or Edge app mode).
# Close the window to stop the engine. Everything it does is in launch.py.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
exec "$PY" app/launch.py
