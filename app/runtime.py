"""A Python that travels inside the package, so the other computer needs none.

    python app/runtime.py win runtime-out/      fetch, verify and unpack one

The builds are python-build-standalone (github.com/astral-sh/python-build-
standalone): CPython compiled to run from any folder, which the python.org
installers are not. One release is pinned, so every package built from this
repository carries the same interpreter, and every download is checked against
the SHA-256 the release publishes before a single byte of it is unpacked.

Standard library only: this runs before any environment exists.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

RELEASE = "20260924"
VERSION = "3.14.7"
TRIPLES = {
    "win": "x86_64-pc-windows-msvc",
    "mac-arm": "aarch64-apple-darwin",
    "mac-intel": "x86_64-apple-darwin",
    "linux": "x86_64-unknown-linux-gnu",
}
BASE = f"https://github.com/astral-sh/python-build-standalone/releases/download/{RELEASE}"
CACHE = Path(__file__).resolve().parent.parent / "build" / "runtime"


def _tls():
    """certifi's roots when present: a python.org build on macOS has none of its own."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, context=_tls(), timeout=120) as r, tmp.open("wb") as out:
        shutil.copyfileobj(r, out, 1 << 20)
    tmp.replace(dest)


def asset(target: str) -> str:
    return f"cpython-{VERSION}+{RELEASE}-{TRIPLES[target]}-install_only_stripped.tar.gz"


def fetch(target: str) -> Path:
    """The verified archive for one target, downloaded once and cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    name = asset(target)
    sums = CACHE / f"SHA256SUMS-{RELEASE}"
    if not sums.exists():
        _download(f"{BASE}/SHA256SUMS", sums)
    expected = next((line.split()[0] for line in sums.read_text().splitlines()
                     if line.strip().endswith(name)), None)
    if expected is None:
        raise SystemExit(f"{name} is not listed in release {RELEASE}'s checksums")
    archive = CACHE / name
    if not archive.exists():
        print(f"  downloading {name}", flush=True)
        _download(f"{BASE}/{name}", archive)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        archive.unlink()
        raise SystemExit(f"{name} failed its checksum ({actual} != {expected}); "
                         "it was deleted, run again to re-download")
    return archive


def members(target: str):
    """Every file of the runtime: (path under 'python/', mode, bytes, link target).

    Links are kept as links (python3 -> python3.14 on macOS and Linux): storing
    a copy per name tripled the interpreter. Windows builds contain none.
    """
    with tarfile.open(fetch(target), "r:gz") as tar:
        for m in tar.getmembers():
            if m.issym():
                yield m.name, 0o777, b"", m.linkname
            elif m.isfile():
                yield m.name, m.mode, tar.extractfile(m).read(), None


def unpack(target: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name, mode, data, link in members(target):
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if link:
            path.unlink(missing_ok=True)
            path.symlink_to(link)
        else:
            path.write_bytes(data)
            path.chmod(mode & 0o777 or 0o644)
    return dest / "python"


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in TRIPLES:
        raise SystemExit(f"usage: python app/runtime.py {{{','.join(TRIPLES)}}} DEST")
    print(unpack(sys.argv[1], Path(sys.argv[2])))
