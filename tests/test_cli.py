"""Tests for reflex.__main__ CLI commands."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from reflex.__main__ import main


class TestCLICheck:
    """Test 'python -m reflex check' command."""

    def test_should_pass_good_uc(self, tmp_path):
        uc = tmp_path / "uc-good.md"
        uc.write_text(
            "## UC-001: SDS hochladen\n\n"
            "**Akteur:** Der SDS-Prüfer\n\n"
            "**Ziel:** damit das Sicherheitsdatenblatt erfasst wird\n\n"
            "**Vorbedingung:** Der Benutzer ist eingeloggt als Prüfer\n\n"
            "**Scope:** Nur für Explosionsschutz-Modul, nicht Teil: Import\n\n"
            "**Schritte:**\n"
            "1. Der Prüfer navigiert zur Upload-Seite\n"
            "2. Der Prüfer wählt eine PDF-Datei aus\n"
            "3. Das System zeigt eine Vorschau an\n"
            "4. Der Prüfer klickt auf Speichern\n\n"
            "**Fehlerfälle:**\n"
            "Falls die Datei ungültig ist, erscheint eine Fehlermeldung\n\n"
            "**Akzeptanzkriterien:**\n"
            "GIVEN ein eingeloggter Prüfer\n"
            "WHEN er ein gültiges SDS hochlädt\n"
            "THEN wird das SDS gespeichert und der Status ändert sich zu 'erfasst'\n"
        )
        import sys
        sys.argv = ["reflex", "check", str(uc)]
        result = main()
        assert result == 0

    def test_should_fail_bad_uc(self, tmp_path):
        uc = tmp_path / "uc-bad.md"
        uc.write_text("Jemand sollte irgendwie etwas machen vielleicht.")
        import sys
        sys.argv = ["reflex", "check", str(uc)]
        result = main()
        assert result == 1

    def test_should_fail_missing_file(self):
        import sys
        sys.argv = ["reflex", "check", "/nonexistent/uc.md"]
        result = main()
        assert result == 1


class TestCLIInfo:
    """Test 'python -m reflex info' command."""

    def test_should_show_config(self, tmp_path):
        config = tmp_path / "reflex.yaml"
        config.write_text(
            "hub_name: test-hub\n"
            "vertical: chemical_safety\n"
            "domain_keywords:\n  - Explosionsschutz\n"
        )
        import sys
        sys.argv = ["reflex", "--config", str(config), "info"]
        result = main()
        assert result == 0

    def test_should_fail_without_config(self):
        import sys
        sys.argv = ["reflex", "info"]
        result = main()
        assert result == 1


class TestCLIClassify:
    """Test 'python -m reflex classify' command."""

    def test_should_classify_infra_error(self):
        import sys
        sys.argv = [
            "reflex", "classify",
            "test_should_load_page",
            "TimeoutError: page.goto timeout 30000ms",
        ]
        result = main()
        assert result == 0
