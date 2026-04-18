"""
REFLEX Failure Classifier — Decision tree for test failure root cause.

Classifies test failures into UC_PROBLEM vs UI_PROBLEM using a
deterministic decision tree, optionally augmented by LLM analysis.

Decision Tree:
    Test fehlgeschlagen
    ├── Kriterium im UC als AK/Fehlerfall beschrieben?
    │   ├── NEIN → UC_PROBLEM (Zirkel 1 neu)
    │   └── JA → Im Wireframe technisch behebbar?
    │       ├── JA → UI_PROBLEM (Wireframe korrigieren)
    │       └── NEIN → UC_PROBLEM (Kriterium widersprüchlich)

Usage:
    from reflex.classify import FailureClassifier

    classifier = FailureClassifier()
    result = classifier.classify(
        test_name="test_should_show_error_on_empty_title",
        error_message="AssertionError: Expected heading 'Neues Projekt'",
        uc_text=uc_content,
        wireframe_path="templates/wireframes/...",
    )
    print(result.failure_type)  # FailureType.UI_PROBLEM
"""

from __future__ import annotations

import logging
import re

from reflex.providers import LLMProvider
from reflex.types import ClassifyResult, FailureType

logger = logging.getLogger(__name__)


__all__ = ["FailureClassifier"]


class FailureClassifier:
    """Deterministic + LLM-augmented failure classification."""

    # Patterns indicating infrastructure problems
    INFRA_PATTERNS = [
        r"TimeoutError",
        r"ConnectionRefused",
        r"ERR_CONNECTION",
        r"net::ERR_",
        r"ECONNREFUSED",
        r"playwright.*timeout",
        r"page\.goto.*timeout",
        r"Browser.*closed",
        r"Session.*expired",
    ]

    # Patterns indicating UI-level problems
    UI_PATTERNS = [
        r"AssertionError.*(?:visible|hidden|displayed|enabled|disabled)",
        r"AssertionError.*(?:text|content|innerText|innerHTML)",
        r"AssertionError.*(?:count|length|number of)",
        r"(?:locator|selector).*(?:not found|resolved to 0)",
        r"(?:aria|role|label).*(?:missing|not found|expected)",
        r"(?:heading|button|link|input).*(?:missing|not found)",
        r"(?:hx-|htmx).*(?:swap|target|trigger)",
    ]

    # Patterns indicating UC-level problems
    UC_PATTERNS = [
        r"(?:logic|workflow|flow|process).*(?:error|wrong|incorrect)",
        r"(?:permission|forbidden|403|unauthorized|401)",
        r"(?:redirect|navigation).*(?:unexpected|wrong)",
        r"(?:state|status|lifecycle).*(?:invalid|unexpected)",
        r"(?:data|model|field).*(?:missing|required|invalid)",
    ]

    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm

    def classify(
        self,
        test_name: str,
        error_message: str,
        uc_text: str = "",
        wireframe_html: str = "",
    ) -> ClassifyResult:
        """Classify a test failure using decision tree.

        Falls back to LLM analysis if the rule-based classifier
        returns UNKNOWN and an LLM provider is available.
        """
        result = self._rule_based_classify(test_name, error_message, uc_text)

        if result.failure_type == FailureType.UNKNOWN and self.llm:
            result = self._llm_classify(test_name, error_message, uc_text, wireframe_html)

        return result

    def _rule_based_classify(
        self,
        test_name: str,
        error_message: str,
        uc_text: str,
    ) -> ClassifyResult:
        """Rule-based classification using pattern matching."""
        combined = f"{test_name}\n{error_message}"

        # 1. Check infrastructure problems first
        if self._matches_any(combined, self.INFRA_PATTERNS):
            return ClassifyResult(
                failure_type=FailureType.INFRA_PROBLEM,
                confidence=0.9,
                reasoning="Infrastruktur-Fehler erkannt (Timeout, Connection, Browser)",
                suggested_action="Infrastruktur prüfen: Server, Browser, Netzwerk",
            )

        # 2. If no UC text, can't determine → UNKNOWN
        if not uc_text:
            return ClassifyResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.3,
                reasoning="Kein UC-Text vorhanden — Klassifikation nicht möglich",
                suggested_action="UC-Text bereitstellen für Klassifikation",
            )

        # 3. Check if the test criterion is described in the UC
        criterion_in_uc = self._criterion_covered_by_uc(test_name, error_message, uc_text)

        if not criterion_in_uc:
            # Not in UC → UC_PROBLEM (missing criterion)
            return ClassifyResult(
                failure_type=FailureType.UC_PROBLEM,
                confidence=0.8,
                reasoning="Getestetes Kriterium ist im UC nicht als AK oder Fehlerfall beschrieben",
                suggested_action="UC um fehlendes Kriterium erweitern → Zirkel 1 neu",
                affected_criterion=test_name,
            )

        # 3. Criterion IS in UC — is it a UI fix?
        if self._matches_any(combined, self.UI_PATTERNS):
            return ClassifyResult(
                failure_type=FailureType.UI_PROBLEM,
                confidence=0.85,
                reasoning="UI-Element fehlt oder falsch — im Wireframe behebbar",
                suggested_action="Wireframe korrigieren: Element ergänzen oder anpassen",
                affected_criterion=test_name,
            )

        # 4. Criterion IS in UC — is it a UC problem?
        if self._matches_any(combined, self.UC_PATTERNS):
            return ClassifyResult(
                failure_type=FailureType.UC_PROBLEM,
                confidence=0.7,
                reasoning="Logik-/Workflow-Fehler — UC-Kriterium widersprüchlich oder unklar",
                suggested_action="UC-Kriterium präzisieren → Zirkel 1 neu",
                affected_criterion=test_name,
            )

        # 5. Unknown — needs LLM or manual review
        return ClassifyResult(
            failure_type=FailureType.UNKNOWN,
            confidence=0.3,
            reasoning="Nicht eindeutig klassifizierbar — LLM oder manuelles Review nötig",
            suggested_action="Manuelles Review oder LLM-Klassifikation",
            affected_criterion=test_name,
        )

    def _criterion_covered_by_uc(
        self,
        test_name: str,
        error_message: str,
        uc_text: str,
    ) -> bool:
        """Check if the tested criterion is described in the UC."""
        if not uc_text:
            return False

        uc_lower = uc_text.lower()

        # Extract keywords from test name
        # test_should_show_error_on_empty_title → ["show", "error", "empty", "title"]
        keywords = re.findall(r"[a-z]+", test_name.lower().replace("test_should_", ""))
        # Filter very short words (articles, etc.)
        keywords = [kw for kw in keywords if len(kw) > 2]

        if not keywords:
            return False

        # At least 1 keyword must appear in UC text
        matches = sum(1 for kw in keywords if kw in uc_lower)
        return matches >= 1

    def _llm_classify(
        self,
        test_name: str,
        error_message: str,
        uc_text: str,
        wireframe_html: str,
    ) -> ClassifyResult:
        """LLM-augmented classification for ambiguous cases."""
        if not self.llm:
            return ClassifyResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.0,
                reasoning="Kein LLM-Provider verfügbar",
                suggested_action="Manuelles Review",
            )

        prompt = (
            "Klassifiziere diesen Test-Fehler:\n\n"
            f"Test: {test_name}\n"
            f"Fehler: {error_message}\n\n"
            f"Use Case:\n{uc_text[:2000]}\n\n"
            f"Wireframe:\n{wireframe_html[:2000]}\n\n"
            "Antwort als JSON: "
            '{"failure_type": "uc_problem|ui_problem|infra_problem", '
            '"confidence": 0.0-1.0, "reasoning": "...", "suggested_action": "..."}'
        )

        import json

        response = self.llm.complete(
            [{"role": "user", "content": prompt}],
            action_code="reflex.failure-classify",
        )

        try:
            data = json.loads(response)
            ft_map = {
                "uc_problem": FailureType.UC_PROBLEM,
                "ui_problem": FailureType.UI_PROBLEM,
                "infra_problem": FailureType.INFRA_PROBLEM,
            }
            return ClassifyResult(
                failure_type=ft_map.get(data.get("failure_type", ""), FailureType.UNKNOWN),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "LLM-Klassifikation"),
                suggested_action=data.get("suggested_action", "Review"),
                affected_criterion=test_name,
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            return ClassifyResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.2,
                reasoning=f"LLM-Antwort nicht parsebar: {response[:200]}",
                suggested_action="Manuelles Review",
            )

    @staticmethod
    def _matches_any(text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the given patterns."""
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)
