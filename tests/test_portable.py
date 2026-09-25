"""Moving WhyChain to another computer: the defects found doing it, held shut.

Each test names what went wrong on a real transfer (B-065). They read the
entry scripts as text because the failures were in the scripts, and the
machines they fail on (a fresh Windows laptop, a Mac that received the zip by
AirDrop) are not the machine these tests run on.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "app" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_windows_entry_keeps_windows_line_endings():
    """cmd.exe misreads labels and goto in a batch file with Unix line endings."""
    raw = (ROOT / "app" / "WhyChain.bat").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_the_windows_entry_runs_python_before_trusting_it():
    """The Microsoft Store placeholder is called python.exe and runs nothing."""
    bat = (ROOT / "app" / "WhyChain.bat").read_text()
    assert 'python -c "import sys"' in bat and "where python" not in bat
    # A failure is shown, not a window that vanishes; unattended runs never wait.
    for line in bat.splitlines():
        if line.strip().endswith("pause"):
            assert "WHYCHAIN_APP_QUIET" in line


def test_the_windows_fast_path_requires_a_verified_install():
    bat = (ROOT / "app" / "WhyChain.bat").read_text()
    fast = next(line for line in bat.splitlines() if "pythonw.exe" in line and "if " in line)
    assert "whychain-ready.json" in fast


def test_the_mac_app_carries_no_path_from_the_machine_that_built_it():
    """It fell back to /Users/<builder>/..., which exists on no other Mac."""
    script = (ROOT / "app" / "build_mac_app.sh").read_text()
    body = script.split("<<'SH'", 1)[1].split("\nSH\n", 1)[0]
    assert "$ROOT" not in body and "/Users/" not in body
    assert "AppTranslocation" in body


def test_nothing_starts_through_a_venv_entry_script():
    """.venv/bin/uvicorn names the folder the venv was built in, so it broke on a move."""
    for name in ("run.sh", "Makefile", "app/launch.py", "app/whychain.sh", "app/whychain.command"):
        text = "\n".join(line for line in (ROOT / name).read_text().splitlines()
                          if not line.lstrip().startswith("#"))
        assert not re.search(r"\.venv/bin/(uvicorn|pytest|ruff|pip)\b", text), name


def test_an_install_is_trusted_only_with_its_marker(tmp_path, monkeypatch):
    launch = _load("launch")
    monkeypatch.setattr(launch, "READY", tmp_path / "whychain-ready.json")
    monkeypatch.setattr(launch, "_version", lambda _py: (3, 14))
    monkeypatch.setattr(launch, "_imports_ok", lambda: True)
    monkeypatch.setattr(launch, "VENV_PY", tmp_path / "python")
    (tmp_path / "python").write_text("")
    assert not launch._ready(), "no marker: an interrupted install must not pass"
    launch.READY.write_text(json.dumps({"requirements": "stale"}))
    assert not launch._ready(), "requirements changed since install: must update"
    launch.READY.write_text(json.dumps({"requirements": launch._requirements_hash()}))
    assert launch._ready()


def test_a_missing_key_is_ai_off_not_a_failure(tmp_path, monkeypatch):
    launch = _load("launch")
    monkeypatch.setattr(launch, "ROOT", tmp_path)
    assert not launch._has_key()
    (tmp_path / ".env").write_text("WHYCHAIN_LLM_API_KEY=\n")
    assert not launch._has_key()
    (tmp_path / ".env").write_text("WHYCHAIN_LLM_API_KEY=sk-test\n")
    assert launch._has_key()


def test_mac_wheels_are_fetched_for_every_tag_a_mac_accepts():
    """One tag per target made `--wheels mac` unresolvable: scipy's Apple-silicon
    wheels are tagged macOS 12 and later."""
    package = _load("package")
    arm, intel = package.WHEEL_TARGETS["mac"]
    assert "macosx_12_0_arm64" in arm and "macosx_14_0_arm64" in arm
    assert any(t.endswith("x86_64") for t in intel)


@pytest.mark.parametrize("prefix", ["data/ground_truth/", "data/audit/", "data/feedback/"])
def test_the_package_leaves_out_what_a_demo_must_not_carry(prefix):
    assert prefix in _load("package").SKIP_PREFIXES
