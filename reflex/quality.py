"""
REFLEX UC Quality Checker — Rule-based + LLM-augmented.

Validates Use Cases against 11 quality criteria (Zirkel 1).
Works standalone (rule-based) or with LLM for deeper analysis.

Usage:
    from reflex.quality import UCQualityChecker
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    checker = UCQualityChecker(config)
    result = checker.check(uc_text)
"""

from __future__ import annotations

import re

from reflex.config import ReflexConfig
from reflex.types import QualityCriterion, UCQualityResult

__all__ = ["UCQualityChecker"]


class UCQualityChecker:
    """Rule-based UC quality checker (Zirkel 1).

    Checks 11 criteria. LLM augmentation is optional —
    the checker works fully offline with regex-based rules.
    """

    def __init__(self, config: ReflexConfig):
        self.config = config

    def check(self, uc_text: str, uc_slug: str = "", iteration: int = 1) -> UCQualityResult:
        """Check UC text against all quality criteria."""
        criteria = [
            self._check_actor(uc_text),
            self._check_goal(uc_text),
            self._check_steps(uc_text),
            self._check_step_count(uc_text),
            self._check_error_cases(uc_text),
            self._check_acceptance_criteria(uc_text),
            self._check_no_implementation(uc_text),
            self._check_no_soft_language(uc_text),
            self._check_testable_criteria(uc_text),
            self._check_scope_defined(uc_text),
            self._check_preconditions(uc_text),
        ]

        passed_count = sum(1 for c in criteria if c.passed)
        total = len(criteria)
        score = passed_count / total if total > 0 else 0.0

        return UCQualityResult(
            uc_slug=uc_slug,
            criteria=criteria,
            overall_score=score,
            passed=passed_count == total,
            iteration=iteration,
        )

    def _check_actor(self, text: str) -> QualityCriterion:
        """C-01: Actor must be specifically named."""
        actor_patterns = [
            r"(?:Akteur|Actor|Benutzer|User|Autor|Admin|Redakteur|Prüfer)",
            r"(?:Als\s+(?:ein(?:e)?|der|die)\s+\w+)",
        ]
        found = any(re.search(p, text, re.IGNORECASE) for p in actor_patterns)
        vague = bool(
            re.search(
                r"\b(jemand|(?<!\w)man(?!\w)|(?:^|\.\s+)einer\s+(?:sollte|muss|kann|könnte|macht))\b",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
        )

        return QualityCriterion(
            name="C-01: Spezifischer Akteur",
            description="Akteur ist konkret benannt (nicht 'jemand' oder 'man')",
            passed=found and not vague,
            evidence=f"Akteur-Pattern gefunden: {found}, Vage Sprache: {vague}",
            suggestion="Akteur spezifisch benennen: 'Der Redakteur', 'Ein SDS-Prüfer'",
        )

    def _check_goal(self, text: str) -> QualityCriterion:
        """C-02: Goal must be clearly formulated."""
        goal_patterns = [
            r"(?:Ziel|Goal|möchte|will|soll)\s*[:.]?\s*\w+",
            r"(?:damit|um zu|so dass|sodass)",
        ]
        found = any(re.search(p, text, re.IGNORECASE) for p in goal_patterns)

        return QualityCriterion(
            name="C-02: Ziel formuliert",
            description="UC hat ein klar formuliertes Ziel",
            passed=found,
            evidence=f"Ziel-Pattern gefunden: {found}",
            suggestion="Ziel formulieren: 'damit...', 'um zu...'",
        )

    def _check_steps(self, text: str) -> QualityCriterion:
        """C-03: Steps must be present."""
        step_patterns = [
            r"^\s*\d+\.\s+",
            r"(?:Schritt|Step)\s+\d+",
            r"^\s*-\s+(?:Der|Die|Das|Ein)",
        ]
        found = any(re.search(p, text, re.MULTILINE) for p in step_patterns)

        return QualityCriterion(
            name="C-03: Schritte vorhanden",
            description="UC enthält nummerierte Schritte",
            passed=found,
            evidence=f"Schritte-Pattern gefunden: {found}",
            suggestion="Schritte als '1. ...' nummerieren",
        )

    def _check_step_count(self, text: str) -> QualityCriterion:
        """C-04: Max N steps (configurable)."""
        steps = re.findall(r"^\s*\d+\.\s+", text, re.MULTILINE)
        count = len(steps)
        max_steps = self.config.quality.max_uc_steps

        return QualityCriterion(
            name=f"C-04: Max {max_steps} Schritte",
            description=f"UC hat maximal {max_steps} Hauptschritte",
            passed=0 < count <= max_steps,
            evidence=f"Gefundene Schritte: {count}",
            suggestion=f"Auf max. {max_steps} Schritte kürzen oder in Sub-UCs aufteilen",
        )

    def _check_error_cases(self, text: str) -> QualityCriterion:
        """C-05: Error cases must be defined."""
        error_patterns = [
            r"(?:Fehlerfall|Fehler|Error|Exception|Ausnahme)",
            r"(?:falls|wenn|if).*(?:nicht|fehl|ungültig|invalid|scheitert)",
            r"(?:Alternative|Alternativ)",
        ]
        found = any(re.search(p, text, re.IGNORECASE) for p in error_patterns)

        return QualityCriterion(
            name="C-05: Fehlerfälle definiert",
            description="UC beschreibt mindestens einen Fehlerfall",
            passed=found or not self.config.quality.require_error_cases,
            evidence=f"Fehlerfall-Pattern gefunden: {found}",
            suggestion="Fehlerfälle ergänzen: 'Falls die Eingabe ungültig ist...'",
        )

    def _check_acceptance_criteria(self, text: str) -> QualityCriterion:
        """C-06: Minimum N acceptance criteria."""
        ak_patterns = [
            r"(?:Akzeptanzkriteri(?:um|en)|AK|Acceptance Criteria)",
            r"(?:GIVEN|WHEN|THEN)",
            r"(?:Erwartet|Expected|Soll-Ergebnis)",
        ]
        matches = sum(len(re.findall(p, text, re.IGNORECASE)) for p in ak_patterns)
        min_ak = self.config.quality.min_acceptance_criteria

        return QualityCriterion(
            name=f"C-06: Min. {min_ak} Akzeptanzkriterien",
            description=f"UC hat mindestens {min_ak} testbare Akzeptanzkriterien",
            passed=matches >= min_ak,
            evidence=f"Gefundene AK-Pattern: {matches}",
            suggestion=f"Mindestens {min_ak} AK ergänzen (GIVEN/WHEN/THEN Format)",
        )

    def _check_no_implementation(self, text: str) -> QualityCriterion:
        """C-07: No implementation details."""
        impl_patterns = [
            r"\b(?:HTMX|hx-|Django|PostgreSQL|Celery|Redis|docker)\b",
            r"\b(?:queryset|migration|serializer|endpoint|API)\b",
            r"\b(?:class|def|import)\s+\w+\s*[:\(]",
            r"\b(?:\.py|\.html|\.css|\.js)\b",
        ]
        violations = [m.group() for p in impl_patterns for m in re.finditer(p, text, re.IGNORECASE)]

        return QualityCriterion(
            name="C-07: Keine Implementierungsdetails",
            description="UC beschreibt WAS, nicht WIE",
            passed=len(violations) == 0 or not self.config.quality.forbid_implementation_details,
            evidence=f"Gefundene Implementierungsdetails: {violations[:5]}",
            suggestion="Technische Details entfernen, nur fachliche Sprache",
        )

    def _check_no_soft_language(self, text: str) -> QualityCriterion:
        """C-08: No vague/soft language."""
        soft_patterns = [
            r"\b(?:vielleicht|eventuell|möglicherweise|ggf\.?)\b",
            r"\b(?:könnte|sollte|würde|dürfte)\b",
            r"\b(?:irgendwie|irgendwo|irgendwann)\b",
            r"\b(?:etc\.?|usw\.?|und so weiter)\b",
        ]
        violations = [m.group() for p in soft_patterns for m in re.finditer(p, text, re.IGNORECASE)]

        return QualityCriterion(
            name="C-08: Keine weiche Sprache",
            description="UC verwendet verbindliche Formulierungen",
            passed=len(violations) == 0 or not self.config.quality.forbid_soft_language,
            evidence=f"Gefundene weiche Sprache: {violations[:5]}",
            suggestion="'sollte' → 'muss', 'vielleicht' → entfernen",
        )

    def _check_testable_criteria(self, text: str) -> QualityCriterion:
        """C-09: Criteria must be testable (measurable)."""
        testable_patterns = [
            r"\b(?:sichtbar|angezeigt|erscheint|zeigt|enthält)\b",
            r"\b(?:navigiert|klickt|tippt|wählt|eingibt)\b",
            r"\b(?:Fehlermeldung|Erfolgsmeldung|Bestätigung)\b",
            r"\b(?:Status|Zustand|wird zu|ändert sich)\b",
        ]
        matches = sum(len(re.findall(p, text, re.IGNORECASE)) for p in testable_patterns)

        return QualityCriterion(
            name="C-09: Testbare Kriterien",
            description="Akzeptanzkriterien sind messbar und beobachtbar",
            passed=matches >= 2,
            evidence=f"Testbare Formulierungen: {matches}",
            suggestion="Messbare Verben verwenden: 'zeigt', 'enthält', 'navigiert'",
        )

    def _check_scope_defined(self, text: str) -> QualityCriterion:
        """C-10: Scope/boundaries are defined."""
        scope_patterns = [
            r"(?:Scope|Umfang|Geltungsbereich|Bereich)",
            r"(?:nicht Teil|out of scope|ausgenommen|nicht enthalten)",
            r"(?:beschränkt auf|nur für|gilt für)",
        ]
        found = any(re.search(p, text, re.IGNORECASE) for p in scope_patterns)

        return QualityCriterion(
            name="C-10: Scope definiert",
            description="UC grenzt ab was nicht enthalten ist",
            passed=found,
            evidence=f"Scope-Pattern gefunden: {found}",
            suggestion="Scope ergänzen: 'Nicht Teil dieses UC: ...'",
        )

    def _check_preconditions(self, text: str) -> QualityCriterion:
        """C-11: Preconditions are stated."""
        pre_patterns = [
            r"(?:Voraussetzung|Precondition|Vorbedingung)",
            r"(?:Vorher|Zuvor|Bevor)",
            r"(?:eingeloggt|angemeldet|authentifiziert|berechtigt)",
            r"(?:GIVEN)",
        ]
        found = any(re.search(p, text, re.IGNORECASE) for p in pre_patterns)

        return QualityCriterion(
            name="C-11: Vorbedingungen genannt",
            description="UC nennt Voraussetzungen (Login, Rolle, Zustand)",
            passed=found,
            evidence=f"Vorbedingung-Pattern gefunden: {found}",
            suggestion="Vorbedingungen ergänzen: 'Der Benutzer ist eingeloggt als...'",
        )
