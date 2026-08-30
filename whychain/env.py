"""Read `.env` into the environment, if there is one.

`.env.example` documents `WHYCHAIN_LLM_API_KEY` and its neighbours, and the
obvious reading of a file called `.env.example` is that copying it to `.env`
makes those settings take effect. Nothing loaded it. The code reads `os.environ`
directly, so a key written into `.env` was silently ignored and the console went
on reporting no reachable backend, with nothing anywhere saying why. Docker
Compose reads `.env` on its own, which is exactly why this went unnoticed: the
containerised path worked and the local one did not.

Deliberately not `python-dotenv`. This is a dozen lines of standard library
against a file format we already control, and `requirements.txt` carrying a
dependency for it would be a worse trade than the lines.

**A real environment variable always wins.** `export WHYCHAIN_LLM_MODEL=...`
before `make demo` must override the file, or the file becomes a thing you have
to remember to edit before every experiment. The file fills gaps; it does not
overwrite decisions.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PATH = Path(".env")


def load_env(path: Path | str = DEFAULT_PATH) -> dict[str, str]:
    """Set any variable named in `path` that is not already set. Returns what it set.

    Missing file is not an error: running without one is the normal case and the
    engine has a deterministic path for exactly that.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}

    applied: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        # Quotes are stripped so a key pasted with them still works; a value
        # containing a `#` is left alone, because an API key may legitimately
        # contain one and guessing at comments would corrupt it.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not name or name in os.environ:
            continue
        os.environ[name] = value
        applied[name] = value
    return applied
