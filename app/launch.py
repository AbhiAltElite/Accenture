"""Open WhyChain as an application window. No terminal, no browser chrome.

    python app/launch.py            what WhyChain.app, WhyChain.bat and whychain.sh run
    python app/launch.py --check    start the engine, prove it works on this PC, stop

Standard library only, so it runs under any Python 3.9+ before the virtualenv
exists and builds it. In order:

1. builds the virtualenv on first run, from bundled wheels when the portable
   package carries them, so a venue with no internet still works
2. generates the warehouse only if it is missing (the portable package ships it)
3. starts the engine hidden on its own port, and waits until it is healthy
4. opens the console in an Edge, Chrome or Chromium app window: no address bar,
   no tabs, its own profile so it never touches the reader's own browser
5. stops the engine when that window is closed

Why its own port and a fingerprint rather than "reuse whatever answers": an
engine left running from an earlier day serves the code it started with. It
answers the health check, so `run.sh` reuses it, and a demo then runs on code
that is days old while every file on disk says otherwise. Here the engine is
restarted whenever any source file is newer than the one that started it.

There is no terminal to read, so every failure is also shown as a dialog.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The first port tried. If something else holds it (another copy of the app, a
# leftover engine, an unrelated program) the next free one is used instead, so a
# busy port is never a reason the app fails to open.
PORT = int(os.environ.get("WHYCHAIN_APP_PORT", "8765"))
PORT_RANGE = 20
APPDATA = ROOT / "data" / "app"
STATE = APPDATA / "engine.json"
LOG = APPDATA / "engine.log"
PROFILE = APPDATA / "window-profile"
WINDOWS = os.name == "nt"
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
WHEELS = ROOT / "wheels"
SOURCES = ("api", "whychain", "ui", "contracts", "data/calibration.json", ".env")
WAREHOUSES = ("whychain.duckdb", "petroleum.duckdb", "power.duckdb")
# Every pinned dependency ships wheels for these. Older Pythons fail to install
# and newer ones may need a compiler; both are refused up front with a reason.
SUPPORTED = ((3, 12), (3, 13), (3, 14))
PYTHON_URL = "https://www.python.org/downloads/release/python-3129/"
# UTF-8 mode for every child. Windows otherwise reads and prints as cp1252,
# which cannot encode the rupee sign the whole console is written in.
CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
             "PYTHONPATH": str(ROOT)}
# Under pythonw every console child flashes a window of its own on Windows.
NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}


class Stop(Exception):
    """A failure the reader must be told about, in words they can act on."""


def say(text: str) -> None:
    print(text, flush=True)
    if sys.platform == "darwin" and os.environ.get("WHYCHAIN_APP_QUIET") != "1":
        subprocess.run(["osascript", "-e",
                        f'display notification "{text}" with title "WhyChain"'],
                       check=False, capture_output=True)


def alert(text: str) -> None:
    """A dialog, because a double-clicked app has nowhere else to say it failed."""
    print(text, file=sys.stderr, flush=True)
    if os.environ.get("WHYCHAIN_APP_QUIET") == "1":
        return
    try:
        if WINDOWS:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "WhyChain", 0x10)
        elif sys.platform == "darwin":
            safe = text.replace('"', "'")
            subprocess.run(["osascript", "-e",
                            f'display dialog "{safe}" with title "WhyChain" '
                            f'buttons {{"OK"}} with icon stop'],
                           check=False, capture_output=True)
        elif shutil.which("zenity"):
            subprocess.run(["zenity", "--error", "--text", text], check=False)
    except Exception:
        pass


# --- processes ---------------------------------------------------------------

def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if WINDOWS:
        # Not os.kill(pid, 0): on Windows that is TerminateProcess, and it
        # would kill the engine this is asking about.
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop(pid: int) -> None:
    if not alive(pid):
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, check=False, **NOWIN)
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not alive(pid):
            return
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)


def fingerprint() -> float:
    """The newest modification time across everything the engine reads at start."""
    newest = 0.0
    for name in SOURCES:
        path = ROOT / name
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts:
                    newest = max(newest, f.stat().st_mtime)
    return newest


def get(path: str, timeout: float = 5) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def healthy() -> bool:
    return get("/api/health", timeout=2)[1].get("status") == "ok"


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port(first: int) -> int:
    for port in range(first, first + PORT_RANGE):
        if port_free(port):
            return port
    raise Stop(f"Ports {first} to {first + PORT_RANGE - 1} are all in use. Close some "
               "programs, or set WHYCHAIN_APP_PORT to a free port.")


# --- first run -----------------------------------------------------------------

def _version(python: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [python, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=20, check=True, **NOWIN).stdout.split()
        return int(out[0]), int(out[1])
    except Exception:
        return None


def base_python() -> str:
    """A Python the pinned dependencies install on, found without a PATH."""
    candidates = [sys.executable]
    if WINDOWS:
        py = shutil.which("py")
        for major, minor in reversed(SUPPORTED):
            if py:
                try:
                    found = subprocess.run([py, f"-{major}.{minor}", "-c",
                                            "import sys; print(sys.executable)"],
                                           capture_output=True, text=True, timeout=20, **NOWIN)
                    if found.returncode == 0:
                        candidates.append(found.stdout.strip())
                except Exception:
                    pass
            local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
            candidates.append(str(local / f"Python{major}{minor}" / "python.exe"))
    else:
        for major, minor in reversed(SUPPORTED):
            for folder in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin",
                           f"/Library/Frameworks/Python.framework/Versions/{major}.{minor}/bin"):
                candidates.append(f"{folder}/python{major}.{minor}")
        candidates += [shutil.which("python3") or "", "/opt/homebrew/bin/python3",
                       "/usr/local/bin/python3"]
    for candidate in candidates:
        if candidate and Path(candidate).exists() and _version(candidate) in SUPPORTED:
            # A venv of a venv works, but is fragile if the outer one moves.
            return candidate
    raise Stop(
        "WhyChain needs Python 3.12, 3.13 or 3.14 installed on this computer, and "
        f"none was found. Install it from {PYTHON_URL} (tick 'Add python.exe to "
        "PATH' on Windows), then open WhyChain again."
    )


def ensure_environment() -> None:
    """First run only: the virtualenv, then the warehouse. Seconds once done."""
    if not VENV_PY.exists() or _version(str(VENV_PY)) not in SUPPORTED:
        shutil.rmtree(ROOT / ".venv", ignore_errors=True)
        python = base_python()
        offline = WHEELS.is_dir() and any(WHEELS.glob("*.whl"))
        say("First run: installing WhyChain" +
            (" from the bundled files." if offline else ", about two minutes."))
        subprocess.run([python, "-m", "venv", str(ROOT / ".venv")], check=True, **NOWIN)
        pip = [str(VENV_PY), "-m", "pip", "install", "-q", "--disable-pip-version-check"]
        requirements = ["-r", str(ROOT / "requirements.txt")]
        done = False
        if offline:
            done = subprocess.run([*pip, "--no-index", "--find-links", str(WHEELS),
                                   *requirements], env=CHILD_ENV, **NOWIN).returncode == 0
        if not done:
            result = subprocess.run([*pip, "--only-binary=:all:", *requirements],
                                    env=CHILD_ENV, capture_output=True, text=True, **NOWIN)
            if result.returncode != 0:
                shutil.rmtree(ROOT / ".venv", ignore_errors=True)
                raise Stop(
                    "Installing WhyChain's dependencies failed. This needs an internet "
                    "connection the first time, unless the portable package included "
                    f"the wheels folder.\n\n{result.stderr.strip()[-600:]}"
                )

    missing = [w for w in WAREHOUSES if not (ROOT / "data" / "warehouse" / w).exists()]
    if missing:
        say("First run: generating the warehouse, about two minutes.")
        subprocess.run([str(VENV_PY), "-m", "datagen.build", "all"],
                       cwd=ROOT, env=CHILD_ENV, check=True, **NOWIN)
    # Idempotent and a second when already done. An unprepared warehouse still
    # answers correctly, only slower, so a failure here does not stop anything.
    subprocess.run([str(VENV_PY), "scripts/prepare.py"], cwd=ROOT, env=CHILD_ENV,
                   check=False, capture_output=True, **NOWIN)

    if not (ROOT / ".env").exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", ROOT / ".env")


# --- the engine ----------------------------------------------------------------

def start_engine() -> int:
    """Start the engine, or reuse ours if it is running the code on disk now."""
    global PORT
    APPDATA.mkdir(parents=True, exist_ok=True)
    stamp = fingerprint()
    if STATE.exists():
        try:
            prior = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            prior = {}
        pid = int(prior.get("pid", 0))
        if alive(pid):
            PORT = int(prior.get("port", PORT))
            if prior.get("fingerprint") == stamp and healthy():
                return pid
            # Ours, but started before the latest edit, or not answering.
            # Restarted, never reused.
            stop(pid)
        STATE.unlink(missing_ok=True)

    # Whatever holds the usual port is not this copy's engine (that case was
    # handled above), so it is left alone and the next free port is used.
    PORT = pick_port(int(os.environ.get("WHYCHAIN_APP_PORT", "8765")))

    flags = ({"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS
             else {"start_new_session": True})
    with LOG.open("ab") as log:
        proc = subprocess.Popen(
            [str(VENV_PY), "-m", "uvicorn", "api.main:app",
             "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT, env=CHILD_ENV, stdout=log, stderr=log, **flags)
    STATE.write_text(json.dumps({"pid": proc.pid, "port": PORT, "fingerprint": stamp}),
                     encoding="utf-8")
    for _ in range(180):
        if healthy():
            return proc.pid
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    stop(proc.pid)
    STATE.unlink(missing_ok=True)
    tail = LOG.read_text(encoding="utf-8", errors="replace")[-800:]
    raise Stop(f"The engine did not start.\n\n{tail}")


def app_browser() -> str | None:
    """A Chromium-family browser that can open an --app window, if installed."""
    if WINDOWS:
        roots = [os.environ.get(v, "") for v in
                 ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        candidates = [str(Path(r) / p) for r in roots if r for p in (
            r"Microsoft\Edge\Application\msedge.exe",
            r"Google\Chrome\Application\chrome.exe")]
    elif sys.platform == "darwin":
        candidates = [f"/Applications/{a}.app/Contents/MacOS/{a}" for a in (
            "Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser")]
    else:
        candidates = []
    found = [c for c in candidates if Path(c).exists()]
    found += [w for n in ("google-chrome", "google-chrome-stable", "chromium",
                          "chromium-browser", "microsoft-edge") if (w := shutil.which(n))]
    return found[0] if found else None


# --- the self-check ----------------------------------------------------------

def check() -> int:
    """Everything a demo depends on, asked of the running engine on this PC."""
    results: list[tuple[bool, str]] = []

    def expect(ok: bool, what: str) -> None:
        results.append((ok, what))
        print(("  pass  " if ok else "  FAIL  ") + what, flush=True)

    print(f"  engine on port {PORT}" + ("" if PORT == 8765 else " (8765 was busy)"), flush=True)
    code, health = get("/api/health")
    expect(code == 200 and health.get("warehouse") == "connected",
           f"engine up, warehouse {health.get('warehouse')}")
    for industry in ("retail", "petroleum", "power"):
        code, body = get(f"/api/overview?industry={industry}", timeout=60)
        expect(code == 200 and bool(body.get("kpis")),
               f"{industry}: {len(body.get('kpis', []))} metrics")

    # CI has no API key. It can prove everything else on a clean Windows
    # machine, so it may skip the model checks, and the output says it did.
    no_ai = os.environ.get("WHYCHAIN_CHECK_NO_AI") == "1"
    code, models = get("/api/models")
    hosted = [b for b in models.get("backends", []) if b.get("available") and b["id"] != "none"]
    if no_ai:
        print("  skip  model backend (WHYCHAIN_CHECK_NO_AI=1)", flush=True)
    else:
        expect(bool(hosted), "model backend reachable: " +
               (", ".join(f"{b['id']} {b['model']}" for b in hosted) or "none (no key in .env?)"))

    trap = ("/api/diagnose?kpi=net_revenue&start=2026-08-13&end=2026-08-15"
            "&region=West&persona=analyst&industry=retail")
    began = time.perf_counter()
    code, body = get(trap, timeout=240)
    took = time.perf_counter() - began
    totals = (body.get("telemetry") or {}).get("totals", {})
    expect(code == 200 and body.get("signal_gap", {}).get("verdict") == "gap_found",
           f"headline diagnosis: {len(body.get('causes') or body.get('verified') or [])} "
           f"causes, gap found, {took:.1f}s")
    used_model = (totals.get("model_calls", 0) + totals.get("cache_hits", 0)) > 0
    if not no_ai:
        expect(used_model, f"AI stages ran: {totals.get('model_calls', 0)} live, "
                           f"{totals.get('cache_hits', 0)} from the demo cache")
    code, _ = get(trap.replace("&persona=analyst", "&entitled=South"))
    expect(code == 403, "entitlement refusal (South reader asking about West)")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10) as r:
            expect(r.status == 200 and b"WhyChain" in r.read(), "console page served")
    except Exception:
        expect(False, "console page served")

    failed = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks pass on this computer.")
    return 1 if failed else 0


# --- main ------------------------------------------------------------------------

def main() -> int:
    os.chdir(ROOT)
    checking = "--check" in sys.argv
    try:
        ensure_environment()
        pid = start_engine()
    except Stop as exc:
        alert(str(exc))
        return 1
    except subprocess.CalledProcessError as exc:
        alert(f"Setting up WhyChain failed at: {' '.join(map(str, exc.cmd))[:300]}")
        return 1

    if checking:
        try:
            return check()
        finally:
            stop(pid)
            STATE.unlink(missing_ok=True)

    url = f"http://127.0.0.1:{PORT}/"
    browser = app_browser()
    if browser is None:
        webbrowser.open(url)
        say("Opened in your browser. The engine keeps running in the background.")
        return 0

    PROFILE.mkdir(parents=True, exist_ok=True)
    began = time.monotonic()
    # A separate profile is what makes this call block until the window closes,
    # and what keeps the reader's own tabs, extensions and sign-ins out of it.
    subprocess.run([browser, f"--app={url}", f"--user-data-dir={PROFILE}",
                    "--window-size=1440,900", "--no-first-run",
                    "--no-default-browser-check"], check=False, capture_output=True, **NOWIN)
    # A browser that hands the window to an already-running copy of itself
    # returns at once, with the window still open. Stopping the engine then
    # would blank a page the reader is looking at, so it is left running and
    # reused by the next launch instead.
    if time.monotonic() - began < 8 or os.environ.get("WHYCHAIN_APP_KEEP_ENGINE") == "1":
        return 0
    stop(pid)
    STATE.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
