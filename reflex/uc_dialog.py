"""
REFLEX UC Dialog Engine — Interactive Use Case creation with feedback loop.

Generates UC skeletons from user prompts, validates against 11 quality
criteria, and produces targeted follow-up questions for missing criteria.
Iterates until all criteria pass or max iterations reached.

Architecture:
    - Pure Python, no Django dependency
    - Uses UCQualityChecker for validation
    - Uses LLMProvider for UC generation + refinement
    - Structured I/O via UCDialogState dataclass

Usage (programmatic):
    from reflex.uc_dialog import UCDialogEngine
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    engine = UCDialogEngine(config=config, llm=llm)

    # Phase 1: Generate skeleton from user prompt
    state = engine.start("SDS hochladen und validieren")

    # Phase 2: Get follow-up questions for missing criteria
    questions = engine.get_questions(state)

    # Phase 3: Refine UC with user answers
    state = engine.refine(state, answers={"actor": "Der SDS-Prüfer", ...})

    # Phase 4: Check if done
    if state.quality_result.passed:
        print(state.uc_text)  # Final UC ready

Usage (CLI — interactive):
    python -m reflex uc-create "SDS hochladen"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from reflex.config import ReflexConfig
from reflex.providers import LLMProvider
from reflex.quality import UCQualityChecker
from reflex.types import QualityCriterion, UCQualityResult

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class UCDialogState:
    """Tracks the state of an interactive UC creation session."""

    topic: str
    uc_text: str = ""
    quality_result: UCQualityResult | None = None
    iteration: int = 0
    max_iterations: int = 5
    history: list[dict[str, str]] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.quality_result is not None and self.quality_result.passed

    @property
    def failed_criteria(self) -> list[QualityCriterion]:
        if self.quality_result is None:
            return []
        return self.quality_result.failed_criteria

    @property
    def can_iterate(self) -> bool:
        return self.iteration < self.max_iterations and not self.is_complete


class UCDialogEngine:
    """Interactive UC creation engine with quality feedback loop.

    Flow:
        1. start(topic) → generates UC skeleton via LLM
        2. UCQualityChecker validates → identifies gaps
        3. get_questions(state) → targeted questions for failed criteria
        4. refine(state, answers) → LLM improves UC with user input
        5. Repeat 2-4 until 11/11 pass or max iterations
    """

    # Map quality criterion names to question templates
    QUESTION_MAP: dict[str, str] = {
        "C-01": "Wer ist der konkrete Akteur? (z.B. 'Der Sicherheitsingenieur', 'Ein SDS-Prüfer')",
        "C-02": "Was ist das Ziel des Use Cases? Was soll am Ende erreicht sein?",
        "C-03": "Beschreibe die Hauptschritte (max. 7): Was passiert der Reihe nach?",
        "C-04": "Der UC hat zu viele Schritte. Welche Schritte können zusammengefasst oder in Sub-UCs ausgelagert werden?",
        "C-05": "Was kann schiefgehen? Nenne mindestens einen Fehlerfall (z.B. ungültige Eingabe, fehlende Berechtigung).",
        "C-06": "Formuliere testbare Akzeptanzkriterien im GIVEN/WHEN/THEN Format.",
        "C-07": "Der UC enthält technische Details. Bitte nur beschreiben WAS passiert, nicht WIE (kein HTMX, Django, etc.).",
        "C-08": "Bitte 'sollte/könnte/vielleicht' durch verbindliche Formulierungen ersetzen ('muss', 'wird').",
        "C-09": "Die Kriterien sind nicht messbar. Verwende beobachtbare Verben: 'zeigt', 'enthält', 'navigiert zu'.",
        "C-10": "Was gehört NICHT zum Scope dieses UC? (z.B. 'Nicht Teil: Löschung, Export')",
        "C-11": "Welche Vorbedingungen müssen erfüllt sein? (Login-Status, Rolle, vorhandene Daten)",
    }

    def __init__(
        self,
        config: ReflexConfig,
        llm: LLMProvider | None = None,
        max_iterations: int = 5,
    ):
        self.config = config
        self.llm = llm
        self.checker = UCQualityChecker(config)
        self.max_iterations = max_iterations

    def start(self, topic: str, context: str = "") -> UCDialogState:
        """Phase 1: Generate initial UC skeleton from topic.

        Args:
            topic: User's description (e.g. "SDS hochladen und validieren")
            context: Optional domain context (e.g. from DomainAgent.research())

        Returns:
            UCDialogState with generated UC text and initial quality check
        """
        state = UCDialogState(
            topic=topic,
            max_iterations=self.max_iterations,
        )

        if self.llm:
            uc_text = self._generate_skeleton(topic, context)
        else:
            uc_text = self._generate_template(topic)

        state.uc_text = uc_text
        state.iteration = 1
        state.history.append({"role": "system", "content": f"UC generated for: {topic}"})

        # Run quality check
        state.quality_result = self.checker.check(
            uc_text, uc_slug=self._topic_to_slug(topic), iteration=1
        )

        return state

    def get_questions(self, state: UCDialogState) -> list[dict[str, str]]:
        """Phase 2: Generate targeted questions for failed criteria.

        Returns list of dicts with 'criterion', 'question', 'hint' keys.
        Only asks about criteria that actually failed.
        """
        if state.is_complete:
            return []

        questions = []
        for criterion in state.failed_criteria:
            # Extract criterion code (e.g. "C-01" from "C-01: Spezifischer Akteur")
            code = criterion.name.split(":")[0].strip()
            question_text = self.QUESTION_MAP.get(
                code,
                f"Bitte ergänze: {criterion.description}",
            )
            questions.append({
                "criterion": code,
                "criterion_name": criterion.name,
                "question": question_text,
                "hint": criterion.suggestion,
                "evidence": criterion.evidence,
            })

        return questions

    def refine(
        self,
        state: UCDialogState,
        answers: dict[str, str],
    ) -> UCDialogState:
        """Phase 3: Refine UC with user answers and re-check quality.

        Args:
            state: Current dialog state
            answers: Dict mapping criterion codes (e.g. "C-01") to user answers

        Returns:
            Updated UCDialogState with refined UC and new quality check
        """
        if not state.can_iterate:
            logger.warning("Max iterations reached or UC already complete")
            return state

        state.answers.update(answers)
        state.iteration += 1

        if self.llm:
            refined_text = self._refine_with_llm(state, answers)
        else:
            refined_text = self._refine_manually(state, answers)

        state.uc_text = refined_text
        state.history.append({
            "role": "user",
            "content": f"Iteration {state.iteration}: {len(answers)} answers provided",
        })

        # Re-check quality
        state.quality_result = self.checker.check(
            refined_text,
            uc_slug=self._topic_to_slug(state.topic),
            iteration=state.iteration,
        )

        return state

    def format_uc_markdown(self, state: UCDialogState) -> str:
        """Export the final UC as clean Markdown file content."""
        slug = self._topic_to_slug(state.topic)
        header = (
            f"# {slug.upper()}: {state.topic}\n\n"
            f"**Status:** {'Approved' if state.is_complete else 'Draft'}\n"
            f"**Modul:** {self.config.vertical}\n"
            f"**Erstellt:** via REFLEX UC Dialog (Iteration {state.iteration})\n"
            f"**Qualität:** {state.quality_result.score_percent}% "
            f"({sum(1 for c in state.quality_result.criteria if c.passed)}"
            f"/{len(state.quality_result.criteria)} Kriterien)\n\n"
        )
        return header + state.uc_text

    # ── Private: Generation ─────────────────────────────────────────────────

    def _generate_skeleton(self, topic: str, context: str) -> str:
        """Generate UC skeleton via LLM."""
        prompt = self._build_generation_prompt(topic, context)
        response = self.llm.complete(
            [{"role": "user", "content": prompt}],
            action_code="reflex.uc-dialog-generate",
        )
        # Extract markdown from response (strip code fences if present)
        return self._clean_llm_response(response)

    def _generate_template(self, topic: str) -> str:
        """Generate a basic UC template without LLM."""
        return (
            f"## Akteur\n\n"
            f"Der [Rolle] (z.B. Sicherheitsingenieur, Administrator)\n\n"
            f"## Ziel\n\n"
            f"Der Akteur möchte {topic}, damit [Nutzen].\n\n"
            f"## Vorbedingung\n\n"
            f"- Der Benutzer ist eingeloggt\n"
            f"- [Weitere Vorbedingungen]\n\n"
            f"## Scope\n\n"
            f"Nur {topic}. Nicht Teil: [Abgrenzung].\n\n"
            f"## Schritte\n\n"
            f"1. Der Akteur navigiert zu [Bereich]\n"
            f"2. Der Akteur [Aktion]\n"
            f"3. Das System [Reaktion]\n"
            f"4. Der Akteur [Bestätigung]\n"
            f"5. Das System [Ergebnis]\n\n"
            f"## Fehlerfälle\n\n"
            f"- Falls [Bedingung], erscheint die Meldung [Fehlermeldung]\n\n"
            f"## Akzeptanzkriterien\n\n"
            f"GIVEN ein eingeloggter Benutzer mit [Rolle]\n"
            f"WHEN er [Aktion] ausführt\n"
            f"THEN wird [erwartetes Ergebnis] angezeigt\n\n"
            f"GIVEN [Fehlerszenario]\n"
            f"WHEN [fehlerhafte Aktion]\n"
            f"THEN wird eine Fehlermeldung angezeigt\n"
        )

    def _refine_with_llm(
        self, state: UCDialogState, answers: dict[str, str]
    ) -> str:
        """Refine UC with LLM using user answers."""
        answers_text = "\n".join(
            f"- **{code}**: {answer}" for code, answer in answers.items()
        )
        failed_text = "\n".join(
            f"- {c.name}: {c.suggestion}" for c in state.failed_criteria
        )

        prompt = (
            f"Verbessere diesen Use Case basierend auf dem Feedback.\n\n"
            f"## Aktueller UC:\n\n{state.uc_text}\n\n"
            f"## Fehlende Kriterien:\n\n{failed_text}\n\n"
            f"## User-Antworten:\n\n{answers_text}\n\n"
            f"## Regeln:\n"
            f"- Behalte alle bestehenden guten Teile bei\n"
            f"- Ergänze NUR die fehlenden Abschnitte\n"
            f"- Verwende die Fachsprache des Verticals: {self.config.vertical}\n"
            f"- Keine technischen Details (kein HTMX, Django, SQL etc.)\n"
            f"- Max {self.config.quality.max_uc_steps} Hauptschritte\n"
            f"- Akzeptanzkriterien im GIVEN/WHEN/THEN Format\n\n"
            f"Gib NUR den verbesserten UC-Text als Markdown zurück, ohne Erklärungen."
        )

        response = self.llm.complete(
            [{"role": "user", "content": prompt}],
            action_code="reflex.uc-dialog-refine",
        )
        return self._clean_llm_response(response)

    def _refine_manually(
        self, state: UCDialogState, answers: dict[str, str]
    ) -> str:
        """Manually insert answers into UC template sections (no LLM)."""
        text = state.uc_text

        for code, answer in answers.items():
            if code == "C-01" and "## Akteur" in text:
                # Replace placeholder actor
                text = text.replace(
                    "Der [Rolle] (z.B. Sicherheitsingenieur, Administrator)",
                    answer,
                )
            elif code == "C-05" and "## Fehlerfälle" in text:
                # Append error case
                text = text.replace(
                    "- Falls [Bedingung], erscheint die Meldung [Fehlermeldung]",
                    f"- {answer}",
                )
            elif code == "C-10" and "## Scope" in text:
                # Replace scope placeholder
                text = text.replace("[Abgrenzung]", answer)
            elif code == "C-11" and "## Vorbedingung" in text:
                # Append precondition
                text = text.replace(
                    "- [Weitere Vorbedingungen]",
                    f"- {answer}",
                )

        return text

    def _build_generation_prompt(self, topic: str, context: str) -> str:
        """Build LLM prompt for initial UC generation."""
        context_section = ""
        if context:
            context_section = f"\n## Domain-Kontext:\n{context}\n"

        return (
            f"Erstelle einen Use Case im folgenden Format für: {topic}\n"
            f"Vertical/Fachgebiet: {self.config.vertical}\n"
            f"Hub: {self.config.hub_name}\n"
            f"Domain-Keywords: {', '.join(self.config.domain_keywords[:10])}\n"
            f"{context_section}\n"
            f"## Pflicht-Sektionen (alle müssen vorhanden sein):\n"
            f"1. **Akteur** — konkret benannt (z.B. 'Der Sicherheitsingenieur')\n"
            f"2. **Ziel** — was soll erreicht werden, mit 'damit...'\n"
            f"3. **Vorbedingung** — Login, Rolle, vorhandene Daten\n"
            f"4. **Scope** — was gehört NICHT dazu\n"
            f"5. **Schritte** — max. {self.config.quality.max_uc_steps} nummerierte Schritte\n"
            f"6. **Fehlerfälle** — mindestens 2 Fehlerszenarien\n"
            f"7. **Akzeptanzkriterien** — min. {self.config.quality.min_acceptance_criteria} "
            f"im GIVEN/WHEN/THEN Format\n\n"
            f"## Verboten:\n"
            f"- Keine technischen Details (kein HTMX, Django, SQL, .py)\n"
            f"- Keine weiche Sprache (kein 'sollte', 'könnte', 'vielleicht')\n"
            f"- Nur messbare, beobachtbare Verben in Akzeptanzkriterien\n\n"
            f"Gib NUR den UC als Markdown zurück, ohne Erklärungen."
        )

    @staticmethod
    def _clean_llm_response(response: str) -> str:
        """Strip code fences and leading/trailing whitespace."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```markdown or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()

    @staticmethod
    def _topic_to_slug(topic: str) -> str:
        """Convert topic to UC slug (e.g. 'SDS hochladen' → 'uc-sds-hochladen')."""
        import re
        slug = re.sub(r"[^a-zA-Z0-9äöüÄÖÜß\s-]", "", topic.lower())
        slug = re.sub(r"\s+", "-", slug.strip())
        return f"uc-{slug}"
