#!/usr/bin/env bash
#
# Build WhyChain.app in the repository root. Double-click it to open the console
# in its own window; close the window to stop the engine.
#
#     make app
#
# The bundle is a thin wrapper: everything it does is in app/launch.py, which is
# the same on every platform. It finds the repository from its own location, so
# keep it in the repository root (or drag an alias of it to the Dock).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(pwd)"
APP="$ROOT/WhyChain.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>WhyChain</string>
  <key>CFBundleDisplayName</key><string>WhyChain</string>
  <key>CFBundleIdentifier</key><string>in.ctrlaltreinvent.whychain</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>WhyChain</string>
  <key>CFBundleIconFile</key><string>WhyChain</string>
  <!-- The launcher has no window of its own; the console window is the app. -->
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

# Finder starts an app with a bare PATH, so the interpreter is looked for by
# path: the project's own virtualenv first, then the usual Python installs.
# Each is run, not just found, because /usr/bin/python3 exists on every Mac
# and may be a placeholder for tools that are not installed.
#
# The folder is found from the bundle's own location and nowhere else. It used
# to fall back to the path of the machine that built it, which on any other Mac
# does not exist, so the app did nothing at all. When it cannot see its folder
# the reason is almost always that macOS is running a quarantined copy from a
# hidden location, and the dialog says how to fix that once.
cat > "$APP/Contents/MacOS/WhyChain" <<'SH'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
dialog() {
  /usr/bin/osascript -e "display dialog \"$1\" with title \"WhyChain\" buttons {\"OK\"} default button 1 with icon stop" >/dev/null 2>&1
}
if [ ! -f "$DIR/app/launch.py" ]; then
  case "$DIR" in
    *AppTranslocation*)
      dialog "macOS opened WhyChain from a protected temporary copy, so it cannot see the rest of its folder.\n\nFix, once: open the WhyChain folder, right-click 'Start WhyChain.command', choose Open, then Open again. After that WhyChain.app opens normally." ;;
    *)
      dialog "WhyChain.app has to stay inside its WhyChain folder, next to the 'app' and 'data' folders. Move it back and open it again." ;;
  esac
  exit 1
fi
mkdir -p "$DIR/data/app"
# Opened, so approved: clear the downloaded mark from this folder before its
# bundled Python is run, or macOS stops that too.
/usr/bin/xattr -dr com.apple.quarantine "$DIR" 2>/dev/null
PY=""
for CANDIDATE in "$DIR/.venv/bin/python" "$DIR/runtime/python/bin/python3" /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
  if [ -x "$CANDIDATE" ] && "$CANDIDATE" -c "import sys" >/dev/null 2>&1; then PY="$CANDIDATE"; break; fi
done
if [ -z "$PY" ]; then
  dialog "WhyChain needs Python 3.12 or newer. Install it from python.org (the page opens now), then open WhyChain again."
  /usr/bin/open "https://www.python.org/downloads/macos/"
  exit 1
fi
exec "$PY" "$DIR/app/launch.py" >> "$DIR/data/app/launcher.log" 2>&1
SH
chmod +x "$APP/Contents/MacOS/WhyChain"

# The icon: drawn here rather than committed as a binary.
ICONSET="$(mktemp -d)/WhyChain.iconset"
mkdir -p "$ICONSET"
if .venv/bin/python app/icon.py "$ICONSET" 2>/dev/null; then
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/WhyChain.icns"
fi

# Tell Finder the bundle changed, or it keeps showing a cached generic icon.
touch "$APP"
echo "Built $APP"
