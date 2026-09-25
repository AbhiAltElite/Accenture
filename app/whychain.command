#!/bin/bash
# macOS: double-click (the first time: right-click, Open). Opens Terminal so
# the first install can be watched, then WhyChain in its own window.
cd "$(cd "$(dirname "$0")/.." && pwd)"
PY=""
for CANDIDATE in .venv/bin/python /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
  if command -v "$CANDIDATE" >/dev/null 2>&1 && "$CANDIDATE" -c "import sys" >/dev/null 2>&1; then
    PY="$CANDIDATE"; break
  fi
done
if [ -z "$PY" ]; then
  echo "WhyChain needs Python 3.12 or newer. Install it from https://www.python.org/downloads/macos/"
  open "https://www.python.org/downloads/macos/"
  [ -n "$WHYCHAIN_APP_QUIET" ] || read -r -n 1 -p "Press any key to close."; exit 1
fi
"$PY" app/launch.py "$@" && exit 0
echo
echo "WhyChain did not start. The reason is above; the full log is in $(pwd)/data/app/"
[ -n "$WHYCHAIN_APP_QUIET" ] || read -r -n 1 -p "Press any key to close."
exit 1
