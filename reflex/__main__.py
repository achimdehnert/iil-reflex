"""
REFLEX CLI — Command-line interface for UC quality checks and domain research.

Usage:
    python -m reflex check <uc-file> [--config reflex.yaml]
    python -m reflex research <topic> [--config reflex.yaml] [--backend groq]
    python -m reflex classify <test-name> <error-msg> [--uc-file <path>]
    python -m reflex info [--config reflex.yaml]

Examples:
    python -m reflex check docs/uc/UC-001-sds-upload.md
    python -m reflex research "Zoneneinteilung nach ATEX" --config reflex.yaml
    python -m reflex classify "test_should_show_error" "AssertionError: heading"
    python -m reflex info --config reflex.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_check(args: argparse.Namespace) -> int:
    """Run UCQualityChecker on a UC file."""
    from reflex.config import ReflexConfig
    from reflex.quality import UCQualityChecker

    config = ReflexConfig.from_yaml(args.config) if args.config else ReflexConfig.from_dict({})
    checker = UCQualityChecker(config)

    uc_path = Path(args.uc_file)
    if not uc_path.exists():
        print(f"ERROR: UC file not found: {uc_path}", file=sys.stderr)
        return 1

    uc_text = uc_path.read_text(encoding="utf-8")
    result = checker.check(uc_text, uc_slug=uc_path.stem)

    print(f"\n{'='*60}")
    print(f"  REFLEX UC Quality Check: {uc_path.name}")
    print(f"{'='*60}")
    print(f"  Score: {result.score_percent}% ({sum(1 for c in result.criteria if c.passed)}/{len(result.criteria)} criteria)")
    print(f"  Passed: {'YES' if result.passed else 'NO'}")
    print(f"{'='*60}\n")

    for c in result.criteria:
        icon = "✅" if c.passed else "❌"
        print(f"  {icon} {c.name}")
        if not c.passed:
            print(f"     Evidence: {c.evidence}")
            print(f"     Fix: {c.suggestion}")
    print()

    if result.failed_criteria:
        print(f"  {len(result.failed_criteria)} criteria failed — see suggestions above.\n")
        return 1
    print("  All criteria passed!\n")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Run DomainAgent.research() on a topic."""
    from reflex.agent import DomainAgent
    from reflex.config import ReflexConfig
    from reflex.llm_providers import get_provider

    config = ReflexConfig.from_yaml(args.config) if args.config else ReflexConfig.from_dict({})

    provider_kwargs = {}
    if args.model and args.backend in ("litellm", "auto"):
        provider_kwargs["model"] = args.model
    llm = get_provider(backend=args.backend, **provider_kwargs)

    agent = DomainAgent(config=config, llm=llm)
    topic = " ".join(args.topic)

    model_name = getattr(llm, "model", args.backend)
    print(f"\nResearching: {topic}")
    print(f"  Vertical: {config.vertical}")
    print(f"  Backend:  {args.backend} ({model_name})")
    print(f"  {'─'*50}")

    result = agent.research(topic)

    print(f"\n  Confidence: {result.confidence:.0%}")
    print(f"  Sources: {', '.join(result.sources_used) or 'LLM only'}")

    if result.facts:
        print(f"\n  Facts ({len(result.facts)}):")
        for f in result.facts:
            print(f"    • {f}")

    if result.gaps:
        print(f"\n  Gaps ({len(result.gaps)}):")
        for g in result.gaps:
            print(f"    ? {g}")

    if result.contradictions:
        print(f"\n  Contradictions ({len(result.contradictions)}):")
        for c in result.contradictions:
            print(f"    ⚠ {c}")

    print()

    if args.json:
        output = {
            "topic": result.topic,
            "vertical": result.vertical,
            "facts": result.facts,
            "gaps": result.gaps,
            "contradictions": result.contradictions,
            "confidence": result.confidence,
            "sources_used": result.sources_used,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))

    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    """Run FailureClassifier on a test failure."""
    from reflex.classify import FailureClassifier

    uc_text = ""
    if args.uc_file:
        uc_path = Path(args.uc_file)
        if uc_path.exists():
            uc_text = uc_path.read_text(encoding="utf-8")

    classifier = FailureClassifier()
    result = classifier.classify(
        test_name=args.test_name,
        error_message=args.error_message,
        uc_text=uc_text,
    )

    print(f"\n{'='*60}")
    print(f"  REFLEX Failure Classification")
    print(f"{'='*60}")
    print(f"  Test:       {args.test_name}")
    print(f"  Type:       {result.failure_type.value}")
    print(f"  Confidence: {result.confidence:.0%}")
    print(f"  Reasoning:  {result.reasoning}")
    print(f"  Action:     {result.suggested_action}")
    if result.affected_criterion:
        print(f"  Criterion:  {result.affected_criterion}")
    print()

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Show REFLEX config info."""
    from reflex.config import ReflexConfig

    if not args.config:
        print("ERROR: --config is required for info command", file=sys.stderr)
        return 1

    config = ReflexConfig.from_yaml(args.config)

    print(f"\n{'='*60}")
    print(f"  REFLEX Config: {args.config}")
    print(f"{'='*60}")
    print(f"  Hub:       {config.hub_name}")
    print(f"  Vertical:  {config.vertical}")
    print(f"  Keywords:  {', '.join(config.domain_keywords[:8])}")
    print(f"  Viewports: {', '.join(v.name for v in config.viewports)}")
    print(f"\n  Quality Rules:")
    print(f"    Max steps:           {config.quality.max_uc_steps}")
    print(f"    Min AK:              {config.quality.min_acceptance_criteria}")
    print(f"    Require error cases: {config.quality.require_error_cases}")
    print(f"    Forbid impl details: {config.quality.forbid_implementation_details}")
    print(f"    Forbid soft lang:    {config.quality.forbid_soft_language}")

    if config.htmx_patterns.banned:
        print(f"\n  HTMX Banned: {', '.join(config.htmx_patterns.banned)}")

    if config.permissions_matrix:
        print(f"\n  Permission Matrix ({len(config.permissions_matrix)} URLs):")
        for url, roles in config.permissions_matrix.items():
            print(f"    {url}: {roles}")

    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="reflex",
        description="REFLEX — Reflexive Evidence-based Loop for UI Development",
    )
    parser.add_argument("--config", "-c", help="Path to reflex.yaml")

    sub = parser.add_subparsers(dest="command")

    # check
    p_check = sub.add_parser("check", help="Check UC quality (11 criteria)")
    p_check.add_argument("uc_file", help="Path to UC markdown file")

    # research
    p_research = sub.add_parser("research", help="Domain research via LLM")
    p_research.add_argument("topic", nargs="+", help="Research topic")
    p_research.add_argument(
        "--backend", "-b", default="litellm",
        help="LLM backend: auto (aifw if Django, else litellm), aifw, litellm",
    )
    p_research.add_argument(
        "--model", "-m", default="groq/llama-3.3-70b-versatile",
        help="litellm model string (e.g. groq/llama-3.3-70b-versatile, openai/gpt-4o-mini)",
    )
    p_research.add_argument("--json", "-j", action="store_true", help="Output JSON")

    # classify
    p_classify = sub.add_parser("classify", help="Classify test failure")
    p_classify.add_argument("test_name", help="Test function name")
    p_classify.add_argument("error_message", help="Error message")
    p_classify.add_argument("--uc-file", help="UC file for context")

    # info
    sub.add_parser("info", help="Show config info")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "check": cmd_check,
        "research": cmd_research,
        "classify": cmd_classify,
        "info": cmd_info,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
