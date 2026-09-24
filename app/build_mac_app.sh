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
# The repository is found from the bundle's location, with the build-time path
# as the fallback if the bundle has been moved.
cat > "$APP/Contents/MacOS/WhyChain" <<SH
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
[ -f "\$DIR/app/launch.py" ] || DIR="$ROOT"
mkdir -p "\$DIR/data/app"
for PY in "\$DIR/.venv/bin/python" /opt/homebrew/bin/python3 /usr/local/bin/python3 \\
          /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
  [ -x "\$PY" ] && break
done
exec "\$PY" "\$DIR/app/launch.py" >> "\$DIR/data/app/launcher.log" 2>&1
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
