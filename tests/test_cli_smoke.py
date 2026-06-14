"""End-to-end CLI smoke — the INSTALLED entry-point actually runs (subprocess).

Unlike test_cli.py (which calls `main()` in-process), these spawn a real process,
so a broken `pyproject` console-script entry-point or a `__main__` import error
would be caught here but not there. (KONZ-iil-reflex-001 D3'.)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _reflex_cmd() -> list[str]:
    """Prefer the installed `reflex` console script (next to the interpreter);
    fall back to PATH, then to `python -m reflex`."""
    candidate = os.path.join(os.path.dirname(sys.executable), "reflex")
    if os.path.exists(candidate):
        return [candidate]
    found = shutil.which("reflex")
    if found:
        return [found]
    return [sys.executable, "-m", "reflex"]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_reflex_cmd() + list(args), capture_output=True, text=True, timeout=60)


class TestCliSmoke:
    def test_help_exits_zero(self):
        r = _run("--help")
        assert r.returncode == 0
        assert "REFLEX" in r.stdout

    def test_classify_runs_offline_with_real_output(self):
        # classify is fully offline + deterministic — real code path, no mocks.
        r = _run("classify", "test_should_show_error", "AssertionError: heading 'Neues Projekt'")
        assert r.returncode == 0
        assert "Classification" in r.stdout
        assert "Type:" in r.stdout

    def test_unknown_command_is_rejected(self):
        r = _run("definitely-not-a-command")
        assert r.returncode != 0  # argparse rejects with exit 2
