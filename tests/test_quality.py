"""Tests for UC Quality Checker — rule-based, no LLM needed."""

import pytest

from reflex.quality import UCQualityChecker


@pytest.fixture
def checker(config) -> UCQualityChecker:
    return UCQualityChecker(config)


GOOD_UC = """
Akteur: SDS-Prüfer
Ziel: Ein neues Sicherheitsdatenblatt hochladen, damit es im System
verfügbar ist.

Vorbedingung: Der Benutzer ist eingeloggt als SDS-Prüfer.

1. Prüfer klickt auf "Neues SDS hochladen"
2. Prüfer wählt PDF-Datei aus
3. System validiert das PDF-Format
4. System extrahiert CAS-Nummer und Produktname
5. System zeigt Vorschau mit extrahierten Daten

Fehlerfall: Falls das PDF ungültig ist, zeigt das System eine
Fehlermeldung "Ungültiges PDF-Format".

Akzeptanzkriterium 1: Nach Upload wird die CAS-Nummer angezeigt.
Akzeptanzkriterium 2: Das SDS erscheint in der Substanzliste.

Scope: Nicht enthalten ist der Bulk-Upload mehrerer SDSs.
"""

BAD_UC = """
Jemand sollte vielleicht Daten hochladen können.
Das System könnte die Datei eventuell verarbeiten.
Dann wird mit Django ORM ein QuerySet erstellt.
"""


class TestUCQualityChecker:
    def test_should_pass_good_uc(self, checker):
        result = checker.check(GOOD_UC, uc_slug="sds-upload")

        assert result.passed
        assert result.score_percent == 100
        assert len(result.failed_criteria) == 0

    def test_should_fail_bad_uc(self, checker):
        result = checker.check(BAD_UC, uc_slug="bad-uc")

        assert not result.passed
        assert result.score_percent < 50
        assert len(result.failed_criteria) > 5

    def test_should_detect_vague_actor(self, checker):
        result = checker.check("Jemand lädt eine Datei hoch.", uc_slug="vague")

        actor_criterion = next(
            c for c in result.criteria if "Akteur" in c.name
        )
        assert not actor_criterion.passed

    def test_should_detect_soft_language(self, checker):
        result = checker.check(
            "Der Admin sollte vielleicht Daten exportieren können.",
            uc_slug="soft",
        )

        soft_criterion = next(
            c for c in result.criteria if "weiche" in c.name
        )
        assert not soft_criterion.passed

    def test_should_detect_implementation_details(self, checker):
        result = checker.check(
            "Als Admin: 1. Klickt auf Button. "
            "System erstellt Django QuerySet und führt Migration aus.",
            uc_slug="impl",
        )

        impl_criterion = next(
            c for c in result.criteria if "Implementierung" in c.name
        )
        assert not impl_criterion.passed

    def test_should_detect_missing_error_cases(self, checker):
        result = checker.check(
            "Akteur: Admin\n1. Admin klickt auf Export\n2. System exportiert",
            uc_slug="no-errors",
        )

        error_criterion = next(
            c for c in result.criteria if "Fehler" in c.name
        )
        assert not error_criterion.passed

    def test_should_detect_too_many_steps(self, checker):
        steps = "\n".join(f"{i}. Schritt {i}" for i in range(1, 12))
        result = checker.check(f"Akteur: Admin\n{steps}", uc_slug="many-steps")

        step_criterion = next(
            c for c in result.criteria if "Schritte" in c.name and "Max" in c.name
        )
        assert not step_criterion.passed

    def test_should_track_iteration(self, checker):
        result = checker.check(GOOD_UC, uc_slug="iter-test", iteration=3)
        assert result.iteration == 3

    def test_should_count_acceptance_criteria(self, checker):
        result = checker.check(GOOD_UC, uc_slug="ak-count")
        ak_criterion = next(
            c for c in result.criteria if "Akzeptanzkriterien" in c.name
        )
        assert ak_criterion.passed

    def test_should_not_flag_einer_as_vague_article(self, checker):
        uc = (
            "## Akteur\nDer Prüfer\n"
            "## Ziel\ndamit geprüft wird\n"
            "## Schritte\n1. Upload\n2. Check\n"
            "## Fehlerfälle\nFalls ungültig, erscheint einer verständlichen Fehlermeldung\n"
            "## AK\nGIVEN x WHEN y THEN z\nGIVEN a WHEN b THEN c\n"
            "## Vorbedingung\nUser eingeloggt\n"
            "## Scope\nNur Upload. Nicht Teil: Export"
        )
        result = checker.check(uc, uc_slug="article-einer")
        actor_criterion = next(c for c in result.criteria if "Akteur" in c.name)
        assert actor_criterion.passed, f"'einer' as article was falsely flagged: {actor_criterion.evidence}"
