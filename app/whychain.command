#!/bin/bash
# macOS fallback if WhyChain.app is blocked: double-click this instead.
cd "$(cd "$(dirname "$0")/.." && pwd)"
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
exec "$PY" app/launch.py
