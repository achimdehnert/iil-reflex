"""
REFLEX Domain Agent — LLM-powered variable domain expertise.

The DomainAgent orchestrates Zirkel 0: autonomous domain research,
expert interview generation, and KB distillation. It is parametrized
by hub_name and vertical — the same code works for any domain.

Architecture:
    - Pure Python, no Django dependency
    - Provider Protocol for knowledge sources (Dependency Inversion)
    - promptfw templates for LLM interaction
    - Structured output via promptfw.parsing

Usage:
    from reflex.agent import DomainAgent
    from reflex.config import ReflexConfig

    config = ReflexConfig.from_yaml("reflex.yaml")
    agent = DomainAgent(
        config=config,
        knowledge=OutlineProvider(...),
        documents=PaperlessProvider(...),
        llm=GroqProvider(...),
    )

    # Phase 1: Autonomous research
    research = agent.research("SDS Upload Pipeline")

    # Phase 2: Generate expert interview (only gaps)
    questions = agent.generate_interview(research)

    # Phase 3: Distill KB from research + expert answers
    kb = agent.distill_kb(research, expert_answers={...})

    # Phase 4: Validate UC against KB
    validation = agent.validate_uc(uc_text="...", kb=kb)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from reflex.config import ReflexConfig
from reflex.providers import (
    DocumentProvider,
    KnowledgeProvider,
    LLMProvider,
)
from reflex.types import (
    DomainKBResult,
    DomainResearchResult,
    InterviewQuestion,
    UCValidationResult,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class DomainAgent:
    """Variable Domain Agent for REFLEX Zirkel 0.

    Parametrized by config.vertical — works for any domain:
        chemical_safety, creative_writing, real_estate,
        tax_advisory, financial_trading, hr_recruiting, etc.
    """

    def __init__(
        self,
        config: ReflexConfig,
        llm: LLMProvider,
        knowledge: KnowledgeProvider | None = None,
        documents: DocumentProvider | None = None,
    ):
        self.config = config
        self.llm = llm
        self.knowledge = knowledge
        self.documents = documents

    def research(self, topic: str) -> DomainResearchResult:
        """Phase 1-2: Autonomous domain research from all sources.

        1. Search existing knowledge (Outline, Paperless, Memory)
        2. LLM synthesizes findings into structured result
        3. Identifies gaps and contradictions
        """
        context_parts: list[str] = []
        sources: list[str] = []

        if self.knowledge:
            entries = self.knowledge.search(topic, limit=5)
            for e in entries:
                context_parts.append(f"[{e.source}] {e.title}: {e.content}")
                sources.append(e.source)

        if self.documents:
            docs = self.documents.search(topic, limit=3)
            for d in docs:
                context_parts.append(f"[{d.source}] {d.title}: {d.snippet}")
                sources.append(d.source)

        existing_knowledge = "\n\n".join(context_parts) if context_parts else "Keine."

        messages = self._render_template(
            "domain_research",
            topic=topic,
            vertical=self.config.vertical,
            hub_name=self.config.hub_name,
            domain_keywords=", ".join(self.config.domain_keywords),
            existing_knowledge=existing_knowledge,
        )

        response = self.llm.complete(messages, action_code="reflex.domain-research")
        return self._parse_research_result(response, topic, sources)

    def generate_interview(
        self,
        research: DomainResearchResult,
    ) -> list[InterviewQuestion]:
        """Phase 3: Generate structured questions for domain expert.

        Only asks about gaps — not things already known from research.
        """
        if not research.has_gaps:
            logger.info("No gaps found — skipping interview generation")
            return []

        messages = self._render_template(
            "domain_interview",
            vertical=self.config.vertical,
            topic=research.topic,
            known_facts="\n".join(f"- {f}" for f in research.facts),
            gaps="\n".join(f"- {g}" for g in research.gaps),
            contradictions="\n".join(f"- {c}" for c in research.contradictions),
        )

        response = self.llm.complete(messages, action_code="reflex.domain-interview")
        return self._parse_interview(response)

    def distill_kb(
        self,
        research: DomainResearchResult,
        expert_answers: dict[str, str] | None = None,
    ) -> DomainKBResult:
        """Phase 5: Distill research + expert answers into structured KB.

        Output: domain/[hub]-kb.md with Glossar, Pflichtfelder,
        Invarianten, Scope-Grenzen.
        """
        answers_text = ""
        if expert_answers:
            answers_text = "\n".join(
                f"**{q}:** {a}" for q, a in expert_answers.items()
            )

        messages = self._render_template(
            "domain_kb_distill",
            vertical=self.config.vertical,
            hub_name=self.config.hub_name,
            facts="\n".join(f"- {f}" for f in research.facts),
            expert_answers=answers_text or "Keine Expert-Antworten vorhanden.",
            required_sections="Glossar, Pflichtfelder, Invarianten, Scope-Grenzen",
        )

        response = self.llm.complete(messages, action_code="reflex.domain-kb-distill")
        return self._parse_kb_result(response, research)

    def validate_uc(
        self,
        uc_text: str,
        kb: DomainKBResult,
    ) -> UCValidationResult:
        """Phase 4/6: Validate UC against KB + quality criteria + ADRs."""
        messages = self._render_template(
            "uc_quality_check",
            uc_text=uc_text,
            domain_kb=kb.markdown,
            vertical=self.config.vertical,
            quality_criteria=self._format_quality_criteria(),
        )

        response = self.llm.complete(messages, action_code="reflex.uc-quality-check")
        return self._parse_validation(response)

    # ── Template Rendering ─────────────────────────────────────────────────

    def _render_template(
        self,
        template_name: str,
        **context: str,
    ) -> list[dict[str, str]]:
        """Render a promptfw .jinja2 template from package templates/."""
        try:
            from promptfw.frontmatter import render_frontmatter_file
        except ImportError:
            return self._render_fallback(template_name, **context)

        template_path = TEMPLATES_DIR / f"{template_name}.jinja2"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        return render_frontmatter_file(str(template_path), **context)

    def _render_fallback(
        self,
        template_name: str,
        **context: str,
    ) -> list[dict[str, str]]:
        """Minimal fallback if promptfw is not installed."""
        template_path = TEMPLATES_DIR / f"{template_name}.jinja2"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        import yaml
        from jinja2 import Template

        raw = template_path.read_text()
        parts = raw.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid template format: {template_path}")

        frontmatter = yaml.safe_load(parts[1])
        messages = []
        for role in ("system", "user", "assistant"):
            if role in frontmatter:
                rendered = Template(str(frontmatter[role])).render(**context)
                if rendered.strip():
                    messages.append({"role": role, "content": rendered.strip()})
        return messages

    # ── Parsers ────────────────────────────────────────────────────────────

    def _parse_research_result(
        self,
        response: str,
        topic: str,
        sources: list[str],
    ) -> DomainResearchResult:
        """Parse LLM research response into structured result."""
        try:
            data = self._extract_json(response)
            return DomainResearchResult(
                topic=topic,
                vertical=self.config.vertical,
                facts=self._normalize_string_list(data.get("facts", [])),
                gaps=self._normalize_string_list(data.get("gaps", [])),
                contradictions=self._normalize_string_list(data.get("contradictions", [])),
                sources_used=sources,
                confidence=data.get("confidence", 0.5),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse research result, returning raw")
            return DomainResearchResult(
                topic=topic,
                vertical=self.config.vertical,
                facts=[response[:500]],
                gaps=["Parse-Fehler — manuelles Review nötig"],
                sources_used=sources,
                confidence=0.0,
            )

    def _parse_interview(self, response: str) -> list[InterviewQuestion]:
        """Parse LLM interview response into structured questions."""
        try:
            data = self._extract_json(response)
            questions = data if isinstance(data, list) else data.get("questions", [])
            return [
                InterviewQuestion(
                    question=q.get("question", ""),
                    category=q.get("category", "general"),
                    why_needed=q.get("why_needed", ""),
                    expected_format=q.get("expected_format", "free_text"),
                    priority=q.get("priority", "high"),
                )
                for q in questions
                if q.get("question")
            ]
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse interview questions")
            return []

    def _parse_kb_result(
        self,
        response: str,
        research: DomainResearchResult,
    ) -> DomainKBResult:
        """Parse LLM KB distillation into structured result."""
        try:
            data = self._extract_json(response)
            return DomainKBResult(
                hub_name=self.config.hub_name,
                vertical=self.config.vertical,
                glossary=data.get("glossary", {}),
                required_fields=data.get("required_fields", []),
                invariants=data.get("invariants", []),
                scope_boundaries=data.get("scope_boundaries", []),
                markdown=data.get("markdown", response),
            )
        except (json.JSONDecodeError, KeyError):
            return DomainKBResult(
                hub_name=self.config.hub_name,
                vertical=self.config.vertical,
                markdown=response,
            )

    def _parse_validation(self, response: str) -> UCValidationResult:
        """Parse UC validation result."""
        try:
            data = self._extract_json(response)
            return UCValidationResult(
                valid=data.get("valid", False),
                violations=data.get("violations", []),
                warnings=data.get("warnings", []),
                adr_conflicts=data.get("adr_conflicts", []),
            )
        except (json.JSONDecodeError, KeyError):
            return UCValidationResult(valid=False, violations=[response[:500]])

    def _format_quality_criteria(self) -> str:
        """Format quality config as criteria text for LLM."""
        qc = self.config.quality
        criteria = [
            f"- Akteur muss spezifisch benannt sein: {qc.require_specific_actor}",
            f"- Maximal {qc.max_uc_steps} Schritte",
            f"- Mindestens {qc.min_acceptance_criteria} testbare Akzeptanzkriterien",
            f"- Fehlerfälle erforderlich: {qc.require_error_cases}",
            f"- Keine Implementierungsdetails: {qc.forbid_implementation_details}",
            f"- Keine weiche Sprache: {qc.forbid_soft_language}",
        ]
        return "\n".join(criteria)

    @staticmethod
    def _normalize_string_list(items: list) -> list[str]:
        """Normalize a list of items to strings.

        LLMs sometimes return dicts (e.g. {"id": 1, "text": "..."})
        instead of plain strings. This extracts the text field or
        converts to string representation.
        """
        result: list[str] = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("description", "")
                result.append(str(text) if text else str(item))
            else:
                result.append(str(item))
        return result

    @staticmethod
    def _extract_json(text: str) -> dict | list:
        """Extract JSON from LLM response, stripping reasoning tags."""
        try:
            from promptfw.parsing import extract_json
            return extract_json(text)
        except ImportError:
            pass

        import re
        for pattern in [r"<think>.*?</think>", r"<reasoning>.*?</reasoning>"]:
            text = re.sub(pattern, "", text, flags=re.DOTALL)

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(text)
