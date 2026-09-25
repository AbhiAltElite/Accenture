"""Build one zip that runs WhyChain on another computer by double-click.

    make package                         code, data, demo cache and the .env key
    make package ARGS="--wheels win"     plus Windows wheels, for a PC with no internet
                                         (also: mac, linux; several at once)
    make package ARGS="--no-key"         safe to share: no API key, AI stays off

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
                 "data/audit/", "data/feedback/", "data/archive/")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--no-key", action="store_true", help="leave the .env key out")
    parser.add_argument("--wheels", nargs="*", choices=sorted(WHEEL_TARGETS), default=[],
                        help="bundle dependency wheels so first run needs no internet")
    args = parser.parse_args()

    missing = [w for w in ("whychain", "petroleum", "power")
               if not (ROOT / "data" / "warehouse" / f"{w}.duckdb").exists()]
    if missing:
        print(f"Generate the warehouse first (make gen-all); missing: {missing}")
        return 1

    if args.wheels:
        print("Downloading wheels")
        fetch_wheels(args.wheels)

    OUT.parent.mkdir(exist_ok=True)
    names = files()
    if args.wheels:
        names += [str(p.relative_to(ROOT)) for p in (ROOT / "wheels").glob("*.whl")]
    env = ROOT / ".env"
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in names:
            if name == ".env":
                continue
            # Under one top-level folder, so unzipping never scatters files.
            info = zipfile.ZipInfo.from_file(ROOT / name, f"WhyChain/{name}")
            info.compress_type = zipfile.ZIP_DEFLATED
            # Keep the executable bit, or the macOS and Linux launchers will not run.
            with (ROOT / name).open("rb") as fh:
                z.writestr(info, fh.read())
        if env.exists() and not args.no_key:
            z.write(env, "WhyChain/.env")
        # Entry points at the top of the folder, where a reader looks first.
        _script(z, "WhyChain/Start WhyChain.bat",
                '@echo off\r\ncall "%~dp0app\\WhyChain.bat"\r\n', 0o644)
        # Double-clickable on a Mac, and shows the first install in Terminal.
        # A quarantined .app is run from a hidden copy; a .command is not.
        _script(z, "WhyChain/Start WhyChain.command",
                '#!/bin/bash\nexec "$(dirname "$0")/app/whychain.command" "$@"\n')
        _script(z, "WhyChain/start-whychain.sh",
                '#!/usr/bin/env bash\nexec "$(dirname "$0")/app/whychain.sh" "$@"\n')
        _script(z, "WhyChain/START HERE.txt", START_HERE.replace("\n", "\r\n"), 0o644)
        app = ROOT / "WhyChain.app"
        if app.is_dir():
            for f in sorted(app.rglob("*")):
                if f.is_file():
                    info = zipfile.ZipInfo.from_file(f, f"WhyChain/{f.relative_to(ROOT)}")
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, f.read_bytes())

    size = OUT.stat().st_size / 1e6
    # A 350MB file copied by USB or AirDrop can arrive truncated, and a
    # truncated zip fails in confusing ways. The checksum settles it in seconds.
    digest = hashlib.sha256()
    with OUT.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    (OUT.parent / (OUT.name + ".sha256")).write_text(f"{digest.hexdigest()}  {OUT.name}\n",
                                                     encoding="utf-8")
    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
    if bad:
        print(f"The zip failed its own integrity check at {bad}. Build it again.")
        return 1
    print(f"\n{OUT.relative_to(ROOT)}  {size:.0f} MB, {len(names)} files, verified")
    print(f"SHA-256 {digest.hexdigest()}")
    print("  compare on the other computer: shasum -a 256 (macOS/Linux) or "
          "certutil -hashfile <zip> SHA256 (Windows)")
    print("On the other computer: unzip, then double-click")
    print("  Windows  WhyChain/Start WhyChain.bat")
    print("  macOS    WhyChain/Start WhyChain.command (right-click, Open, the first time)")
    print("  Linux    WhyChain/start-whychain.sh")
    print("Check it there with:  python app/launch.py --check")
    if env.exists() and not args.no_key:
        print("\nThis zip contains the API key from .env. Share it by USB or AirDrop only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
