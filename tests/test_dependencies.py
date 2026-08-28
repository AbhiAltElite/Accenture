"""Every third-party import must be declared, or a clean machine cannot run this.

This exists because it has already happened once: `holidays` was installed by
hand during development, imported by two modules, and never pinned. Everything
worked locally and CI failed on a clean runner, which is exactly the failure
mode a lock file is meant to prevent.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("whychain", "datagen", "api", "bench", "scripts", "tests")

# Import name to distribution name, where they differ.
ALIASES = {
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "psycopg": "psycopg",          # optional, only for the pgvector backend
}
# Imported behind a try/except or only for one optional backend.
OPTIONAL = {"psycopg"}


def _top_level_imports() -> set[str]:
    found: set[str] = set()
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
    return found


def _declared() -> set[str]:
    lines = (ROOT / "requirements.txt").read_text().splitlines()
    return {
        line.split("==")[0].strip().lower()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }


@pytest.mark.invariant
def test_every_third_party_import_is_pinned():
    local = set(PACKAGES)
    declared = _declared()
    missing = sorted(
        name
        for name in _top_level_imports()
        if name not in local
        and name not in sys.stdlib_module_names
        and name not in OPTIONAL
        and ALIASES.get(name, name).lower() not in declared
    )
    assert not missing, (
        f"imported but not in requirements.txt: {missing}. "
        "A clean machine cannot install what is not declared."
    )
