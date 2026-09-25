"""Build one zip that runs WhyChain on another computer by double-click.

    make package                         code, data, demo cache and the .env key
    make package ARGS="--wheels win"     plus Windows wheels, for a PC with no internet
                                         (also: mac, linux; several at once)
    make package ARGS="--no-key"         safe to share: no API key, AI stays off
    make package-offline                 one zip per machine type with Python and every
                                         dependency inside: unzip, double-click, no internet

A `git clone` is not enough to demo from, because four things a demo needs are
deliberately not in git: the warehouse (300MB, generated), the model cache that
makes the AI answer instantly and offline, the calibration curve's inputs, and
the API key. This puts them in one file.

**The zip holds the API key unless --no-key is given. Copy it by USB or
AirDrop; never upload it anywhere public.** It is written to dist/, which git
ignores.

What is left out, on purpose: the virtualenv (it is per operating system and
the launcher builds it), the answer key in data/ground_truth (no runtime path
reads it), the public real-data download, feedback written by test runs, and
scratch files.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "WhyChain-portable.zip"

# Untracked files in the working tree that are experiments, not the product.
SKIP_PREFIXES = ("scratch/", "_internal", "brag-output/", "dist/", "WhyChain.app/",
                 "ui/variant_", "ui/_compare", "wheels/", "data/ground_truth/", "data/app/",
                 "data/audit/", "data/feedback/", "data/archive/", "runtime/", "build/")
SKIP_SUFFIXES = (".orig", ".zip")
# Gitignored, and needed to run the demo exactly as it runs here.
RUNTIME = ("data/warehouse", "data/llm_cache", "data/demo", "data/docs")
# Every platform tag a real machine of each kind accepts. One tag per target was
# the defect: pip matches the tag exactly, and scipy's Apple-silicon wheels are
# tagged macOS 12 and later, so `--wheels mac` failed to resolve at all. Each
# group is one machine, resolved on its own, since a Mac is one of the two.
WHEEL_TARGETS = {
    "win": (("win_amd64",),),
    "mac": (tuple(f"macosx_{m}_0_{a}" for m in (11, 12, 13, 14, 15) for a in ("arm64", "universal2")),
            tuple(f"macosx_{m}_{a}" for m in ("10_9", "10_13", "10_15", "11_0", "12_0", "13_0", "14_0")
                  for a in ("x86_64", "universal2", "intel"))),
    "linux": (("manylinux_2_17_x86_64", "manylinux2014_x86_64", "manylinux_2_28_x86_64"),),
}
PYTHONS = ("3.12", "3.13", "3.14")


START_HERE = """WhyChain

BEFORE YOU START
  * Unzip the whole zip first. Do not run it from inside the zip.
  * Put the WhyChain folder somewhere short and local, e.g. C:\\WhyChain or
    your home folder. Not inside OneDrive, iCloud Drive or Dropbox: they lock
    and re-upload the 800MB data folder while the app is reading it.
  * You need Python 3.12, 3.13 or 3.14 (python.org). On Windows tick
    "Add python.exe to PATH" in the installer.
  * The first run needs internet for a few minutes, unless this package came
    with a "wheels" folder. After that it runs offline.

START
  Windows  double-click "Start WhyChain.bat"
  macOS    first time: right-click "Start WhyChain.command", choose Open, then
           Open again. A Terminal window shows the install. After the first
           run, WhyChain.app opens it directly.
  Linux    run ./start-whychain.sh

It opens in its own window. Close the window to stop it. The first run
installs itself (a few minutes, with progress shown); later runs take seconds.
If a first run is interrupted, just start it again: it repairs itself.

CHECK IT BEFORE A DEMO
  From this folder:  python app/launch.py --check   (python3 on macOS/Linux)
  It should end with "... checks pass on this computer. Ready."
  Without an API key in .env it says AI is off; everything else still runs.

IF SOMETHING GOES WRONG
  The reason is shown on screen. The full logs are in data/app/:
  install.log (setting up), engine.log (the engine), launcher.log (macOS app).
"""


def _script(z: zipfile.ZipFile, name: str, text: str, mode: int = 0o755) -> None:
    """A generated file, unzipped with the permissions it needs (executable or not)."""
    info = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    info.external_attr = ((0o100000 | mode) << 16)
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, text)


def files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    keep = [f for f in listed
            if not f.startswith(SKIP_PREFIXES) and not f.endswith(SKIP_SUFFIXES)
            and (ROOT / f).is_file()]
    for folder in RUNTIME:
        keep += [str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob("*")
                 if p.is_file() and not p.name.endswith((".wal", ".tmp"))]
    return sorted(set(keep))


def fetch_wheels(targets: list[str]) -> None:
    folder = ROOT / "wheels"
    folder.mkdir(exist_ok=True)
    for target in targets:
        for tags in WHEEL_TARGETS[target]:
            for version in PYTHONS:
                print(f"  wheels for {target} ({tags[0]}...), Python {version}", flush=True)
                platform = [arg for tag in tags for arg in ("--platform", tag)]
                subprocess.run([sys.executable, "-m", "pip", "download", "-q",
                                "--only-binary=:all:", *platform,
                                "--python-version", version, "--dest", str(folder),
                                "-r", str(ROOT / "requirements.txt")], check=True)


# Per bundle: the one machine type it is for, and the wheel tags that machine accepts.
BUNDLE_TAGS = {"win": WHEEL_TARGETS["win"][0], "mac-arm": WHEEL_TARGETS["mac"][0],
               "mac-intel": WHEEL_TARGETS["mac"][1], "linux": WHEEL_TARGETS["linux"][0]}
BUNDLE_NAMES = {"win": "Windows", "mac-arm": "Mac with Apple silicon (M1 and later)",
                "mac-intel": "Mac with an Intel processor", "linux": "Linux (x86-64)"}

START_WINDOWS = """WhyChain for Windows. Everything it needs is inside this folder,
Python included. No installing, no internet.

1. Unzip first: right-click the zip, Extract All. Do not run it from inside the zip.
   Put the folder somewhere short and local, such as C:\\WhyChain. Not inside
   OneDrive: it locks and re-uploads the data while WhyChain reads it.
2. Double-click "Start WhyChain.bat".
   If Windows says "Windows protected your PC", click More info, then Run anyway.
   That happens once: the file came from another computer and is not signed.
3. The first start sets itself up in about a minute, in a window that shows
   progress, then WhyChain opens in its own window. Later starts take seconds.
   Close the WhyChain window to stop it.
"""

START_MAC = """WhyChain for {machine}. Everything it needs is inside this folder,
Python included. No installing, no internet.

HOW IT GOT HERE DECIDES THE FIRST STEP
macOS marks files that arrive by AirDrop, a browser, Slack or email as
downloaded, and will not open anything marked that way until you say so.
Files copied from a USB stick or a shared drive in Finder are not marked.

  Copied by USB or a shared drive:
    Double-click the zip to unzip it, then double-click "Start WhyChain.command".

  Arrived by AirDrop, download or chat:
    1. Double-click the zip to unzip it.
    2. Double-click "Start WhyChain.command". macOS says it was not opened.
    3. Open System Settings, then Privacy & Security, and scroll down.
       Click "Open Anyway" beside "Start WhyChain.command", then Open.
       (macOS 14 and earlier: right-click the file, choose Open, then Open.)
    That is the only approval. The first start then clears the downloaded mark
    from this folder, so its Python and WhyChain.app open without asking again.

    Or, once, in Terminal: type  xattr -dr com.apple.quarantine  and a space,
    drag the WhyChain folder into the window, press Return. Then double-click.

The first start sets itself up in about a minute in a Terminal window, then
WhyChain opens in its own window. After that, double-click WhyChain.app.
Close the WhyChain window to stop it.
"""

START_LINUX = """WhyChain for Linux. Everything it needs is inside this folder, Python
included. Unzip, then run ./start-whychain.sh. The first start sets itself up in
about a minute; later starts take seconds.
"""

COMMON_TAIL = """
CHECK IT BEFORE A DEMO
  Run the starter with --check (Windows: open a Command Prompt in this folder
  and run  app\\WhyChain.bat  with WHYCHAIN_APP_CHECK=1 set, or use Python:
  runtime\\python\\python.exe app\\launch.py --check). It should end with
  "... checks pass on this computer. Ready."

IF SOMETHING GOES WRONG
  The reason is shown on screen. Full logs are in data/app/: install.log,
  engine.log, launcher.log. Starting again repairs an interrupted setup.
"""


def start_here(target: str | None) -> str:
    if target is None:
        return START_HERE
    if target == "win":
        text = START_WINDOWS
    elif target.startswith("mac"):
        text = START_MAC.format(machine=BUNDLE_NAMES[target])
    else:
        text = START_LINUX
    return text + COMMON_TAIL


def bundle_wheels(target: str) -> Path:
    """Every dependency as a wheel for one machine type, proven installable offline."""
    import shutil
    import tempfile

    sys.path.insert(0, str(ROOT / "app"))
    import runtime
    folder = ROOT / "build" / "wheels" / target
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    common = ["--only-binary=:all:", *[a for t in BUNDLE_TAGS[target] for a in ("--platform", t)],
              "--python-version", runtime.VERSION.rsplit(".", 1)[0],
              "-r", str(ROOT / "requirements.txt")]
    print(f"  wheels for {BUNDLE_NAMES[target]}", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "download", "-q", "--dest", str(folder),
                    *common], check=True)
    # The bundle's promise is "no internet". Held to it here, not discovered
    # at a venue: resolve the whole requirement set from this folder alone.
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "-q",
                        "--ignore-installed", "--no-index", "--find-links", str(folder),
                        "--target", tmp, *common], check=True)
    return folder


def _add_file(z: zipfile.ZipFile, path: Path, arcname: str) -> None:
    info = zipfile.ZipInfo.from_file(path, arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    # Keep the executable bit, or the macOS and Linux launchers will not run.
    with path.open("rb") as fh:
        z.writestr(info, fh.read())


def _add_runtime(z: zipfile.ZipFile, target: str) -> int:
    sys.path.insert(0, str(ROOT / "app"))
    import runtime
    count = 0
    for name, mode, data, link in runtime.members(target):
        info = zipfile.ZipInfo(f"WhyChain/runtime/{name}", date_time=time.localtime()[:6])
        info.create_system = 3          # Unix modes and links are read from here
        info.compress_type = zipfile.ZIP_DEFLATED
        if link:
            info.external_attr = (0o120777 << 16)
            z.writestr(info, link)
        else:
            info.external_attr = ((0o100000 | (mode & 0o777 or 0o644)) << 16)
            z.writestr(info, data)
        count += 1
    return count


def build(out: Path, target: str | None, names: list[str], key: bool,
          wheels: Path | None) -> int:
    env = ROOT / ".env"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in names:
            if name == ".env":
                continue
            # Under one top-level folder, so unzipping never scatters files.
            _add_file(z, ROOT / name, f"WhyChain/{name}")
        if env.exists() and key:
            z.write(env, "WhyChain/.env")
        # Entry points at the top of the folder, where a reader looks first.
        if target in (None, "win"):
            _script(z, "WhyChain/Start WhyChain.bat",
                    '@echo off\r\ncall "%~dp0app\\WhyChain.bat"\r\n', 0o644)
        # Double-clickable on a Mac, and shows the first install in Terminal.
        # A quarantined .app is run from a hidden copy; a .command is not.
        if target is None or target.startswith("mac"):
            _script(z, "WhyChain/Start WhyChain.command",
                    '#!/bin/bash\nexec "$(dirname "$0")/app/whychain.command" "$@"\n')
            app = ROOT / "WhyChain.app"
            if app.is_dir():
                for f in sorted(app.rglob("*")):
                    if f.is_file():
                        _add_file(z, f, f"WhyChain/{f.relative_to(ROOT)}")
        if target in (None, "linux"):
            _script(z, "WhyChain/start-whychain.sh",
                    '#!/usr/bin/env bash\nexec "$(dirname "$0")/app/whychain.sh" "$@"\n')
        _script(z, "WhyChain/START HERE.txt", start_here(target).replace("\n", "\r\n"), 0o644)
        if wheels is not None:
            for whl in sorted(wheels.glob("*.whl")):
                _add_file(z, whl, f"WhyChain/wheels/{whl.name}")
        if target is not None:
            _add_runtime(z, target)

    # A 350MB file copied by USB or AirDrop can arrive truncated, and a
    # truncated zip fails in confusing ways. The checksum settles it in seconds.
    digest = hashlib.sha256()
    with out.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    (out.parent / (out.name + ".sha256")).write_text(f"{digest.hexdigest()}  {out.name}\n",
                                                     encoding="utf-8")
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
    if bad:
        print(f"{out.name} failed its own integrity check at {bad}. Build it again.")
        return 1
    print(f"\n{out.relative_to(ROOT)}  {out.stat().st_size / 1e6:.0f} MB, verified"
          + (f", for {BUNDLE_NAMES[target]}, Python and every dependency inside" if target else ""))
    print(f"  SHA-256 {digest.hexdigest()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--no-key", action="store_true", help="leave the .env key out")
    parser.add_argument("--wheels", nargs="*", choices=sorted(WHEEL_TARGETS), default=[],
                        help="bundle dependency wheels so first run needs no internet")
    parser.add_argument("--stage", choices=sorted(BUNDLE_TAGS),
                        help="put one machine type's Python and wheels into this folder, "
                             "as its package would carry them, without zipping (for CI)")
    parser.add_argument("--bundle", nargs="*", choices=sorted(BUNDLE_TAGS), default=[],
                        help="one self-contained zip per machine type: Python, every "
                             "dependency and the data; nothing to install, no internet")
    args = parser.parse_args()

    if args.stage:
        import shutil
        sys.path.insert(0, str(ROOT / "app"))
        import runtime
        shutil.rmtree(ROOT / "runtime", ignore_errors=True)
        shutil.rmtree(ROOT / "wheels", ignore_errors=True)
        runtime.unpack(args.stage, ROOT / "runtime")
        shutil.copytree(bundle_wheels(args.stage), ROOT / "wheels")
        print(f"Staged the {BUNDLE_NAMES[args.stage]} runtime and wheels in this folder.")
        return 0

    missing = [w for w in ("whychain", "petroleum", "power")
               if not (ROOT / "data" / "warehouse" / f"{w}.duckdb").exists()]
    if missing:
        print(f"Generate the warehouse first (make gen-all); missing: {missing}")
        return 1

    OUT.parent.mkdir(exist_ok=True)
    names = files()
    if args.bundle:
        for target in args.bundle:
            print(f"Building the {BUNDLE_NAMES[target]} package", flush=True)
            wheels = bundle_wheels(target)
            if build(OUT.parent / f"WhyChain-{target}.zip", target, names,
                     not args.no_key, wheels):
                return 1
    else:
        wheels = None
        if args.wheels:
            print("Downloading wheels")
            fetch_wheels(args.wheels)
            wheels = ROOT / "wheels"
        if build(OUT, None, names, not args.no_key, wheels):
            return 1

    print("\nSend the zip that matches the other computer. There, follow START HERE.txt.")
    print("  Compare the SHA-256 there: shasum -a 256 <zip> (macOS/Linux), "
          "certutil -hashfile <zip> SHA256 (Windows)")
    if (ROOT / ".env").exists() and not args.no_key:
        print("\nThese zips contain the API key from .env. Share them by USB or AirDrop only;"
              " use --no-key for anyone outside the team.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
