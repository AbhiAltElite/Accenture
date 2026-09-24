"""Build one zip that runs WhyChain on another computer by double-click.

    make package                         code, data, demo cache and the .env key
    make package ARGS="--wheels win"     plus Windows wheels, for a PC with no internet
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
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "WhyChain-portable.zip"

# Untracked files in the working tree that are experiments, not the product.
SKIP_PREFIXES = ("scratch/", "_internal", "brag-output/", "dist/", "WhyChain.app/",
                 "ui/variant_", "ui/_compare", "wheels/")
SKIP_SUFFIXES = (".orig", ".zip")
# Gitignored, and needed to run the demo exactly as it runs here.
RUNTIME = ("data/warehouse", "data/llm_cache", "data/demo", "data/docs")
# Windows x64 and the Python versions the launcher accepts. Wheels are per
# version, so all three are fetched; a PC has exactly one of them installed.
WHEEL_TARGETS = {"win": ("win_amd64",), "mac": ("macosx_11_0_arm64", "macosx_10_13_x86_64")}
PYTHONS = ("3.12", "3.13", "3.14")


START_HERE = """WhyChain

Windows  double-click "Start WhyChain.bat"
macOS    double-click WhyChain.app. If macOS says it cannot verify the developer,
         right-click it, choose Open, then Open again. Once only.
Linux    run app/whychain.sh

It opens in its own window. Close the window to stop it.

The first time on a new computer it installs itself, which takes a few minutes
and needs Python 3.12 or newer (python.org) and, unless a wheels folder is
included, an internet connection. After that it opens in seconds.

To prove everything works on this computer before a demo, from this folder:
    python app/launch.py --check        (python3 on macOS and Linux)
It should end with "9 of 9 checks pass".
"""


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
        for platform in WHEEL_TARGETS[target]:
            for version in PYTHONS:
                print(f"  wheels for {platform}, Python {version}", flush=True)
                subprocess.run([sys.executable, "-m", "pip", "download", "-q",
                                "--only-binary=:all:", "--platform", platform,
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
        z.writestr("WhyChain/Start WhyChain.bat",
                   '@echo off\r\ncall "%~dp0app\\WhyChain.bat"\r\n')
        z.writestr("WhyChain/START HERE.txt", START_HERE)
        app = ROOT / "WhyChain.app"
        if app.is_dir():
            for f in sorted(app.rglob("*")):
                if f.is_file():
                    info = zipfile.ZipInfo.from_file(f, f"WhyChain/{f.relative_to(ROOT)}")
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, f.read_bytes())

    size = OUT.stat().st_size / 1e6
    print(f"\n{OUT.relative_to(ROOT)}  {size:.0f} MB, {len(names)} files")
    print("On the other computer: unzip, then double-click")
    print("  Windows  WhyChain/Start WhyChain.bat")
    print("  macOS    WhyChain/WhyChain.app")
    print("  Linux    WhyChain/app/whychain.sh")
    print("Check it there with:  python app/launch.py --check")
    if env.exists() and not args.no_key:
        print("\nThis zip contains the API key from .env. Share it by USB or AirDrop only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
