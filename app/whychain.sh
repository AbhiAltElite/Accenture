#!/usr/bin/env bash
# Linux: open WhyChain in its own window (Chrome, Chromium or Edge app mode).
# Close the window to stop the engine. Everything it does is in launch.py.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=""
for CANDIDATE in .venv/bin/python runtime/python/bin/python3 python3.14 python3.13 python3.12 python3; do
  if command -v "$CANDIDATE" >/dev/null 2>&1 && "$CANDIDATE" -c "import sys" >/dev/null 2>&1; then
    PY="$CANDIDATE"; break
  fi
done
if [ -z "$PY" ]; then
  echo "WhyChain needs Python 3.12 or newer, with its venv module (on Debian and"
  echo "Ubuntu: sudo apt install python3 python3-venv). Then run this again."
  exit 1
fi
exec "$PY" app/launch.py "$@"
