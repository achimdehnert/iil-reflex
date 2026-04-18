"""
REFLEX CLI — Command-line interface for UC quality checks and domain research.

Usage:
    python -m reflex check <uc-file> [--config reflex.yaml]
    python -m reflex research <topic> [--config reflex.yaml] [--backend groq] [--web]
    python -m reflex scrape <url> [--pdf] [--json]
    python -m reflex sds <substance> [--source pubchem|gestis]
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

    web = None
    if args.web:
        from reflex.web import HttpxWebProvider
        web = HttpxWebProvider()

    agent = DomainAgent(config=config, llm=llm, web=web)
    topic = " ".join(args.topic)

    model_name = getattr(llm, "model", args.backend)
    print(f"\nResearching: {topic}")
    print(f"  Vertical: {config.vertical}")
    print(f"  Backend:  {args.backend} ({model_name})")
    print(f"  Web:      {'enabled' if args.web else 'disabled'}")
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
    print("  REFLEX Failure Classification")
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


def cmd_scrape(args: argparse.Namespace) -> int:
    """Scrape a URL and show extracted content."""
    from reflex.web import HttpxWebProvider

    web = HttpxWebProvider()
    page = web.fetch(args.url)

    print(f"\n{'='*60}")
    print("  REFLEX Web Scrape")
    print(f"{'='*60}")
    print(f"  URL:     {page.url}")
    print(f"  Title:   {page.title}")
    print(f"  Status:  {page.status_code}")
    print(f"  Type:    {page.content_type}")
    print(f"  Length:  {len(page.text)} chars")
    print(f"{'='*60}\n")

    if args.json:
        output = {
            "url": page.url,
            "title": page.title,
            "status_code": page.status_code,
            "content_type": page.content_type,
            "text": page.text[:5000],
            "scraped_at": page.scraped_at,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(page.text[:3000])
        if len(page.text) > 3000:
            print(f"\n  ... ({len(page.text) - 3000} more chars, use --json for full)")

    print()
    return 0


def cmd_sds(args: argparse.Namespace) -> int:
    """Look up SDS data for a substance."""
    from dataclasses import asdict

    from reflex.web import GESTISAdapter, HttpxWebProvider, PubChemAdapter

    substance = " ".join(args.substance)
    web = HttpxWebProvider()
    results: list[dict] = []

    print(f"\n{'='*60}")
    print(f"  REFLEX SDS Lookup: {substance}")
    print(f"{'='*60}")

    if args.source in ("pubchem", "all"):
        print("\n  Querying PubChem...")
        adapter = PubChemAdapter(web=web)
        sds = adapter.lookup_by_name(substance)
        if sds:
            print(f"  ✅ Found: {sds.substance_name}")
            print(f"     CAS:  {sds.cas_number or 'N/A'}")
            results.append({"source": "pubchem", **asdict(sds)})
        else:
            print("  ❌ Not found on PubChem")

    if args.source in ("gestis", "all"):
        print("\n  Querying GESTIS...")
        adapter = GESTISAdapter(web=web)
        hits = adapter.search(substance)
        if hits:
            print(f"  ✅ Found {len(hits)} match(es):")
            for h in hits[:3]:
                print(f"     • {h['name']} (CAS: {h.get('cas', 'N/A')}, ZVG: {h.get('zvg', '')})")
                if h.get("zvg"):
                    sds = adapter.lookup(h["zvg"])
                    if sds:
                        results.append({"source": "gestis", **asdict(sds)})
        else:
            print("  ❌ Not found on GESTIS")

    if args.json and results:
        print(f"\n{json.dumps(results, indent=2, ensure_ascii=False)}")

    print()
    return 0



def cmd_review(args: argparse.Namespace) -> int:
    """Run REFLEX review plugins on a repo (ADR-165)."""
    from reflex.review import ReviewEngine

    github_dir = args.github_dir or str(Path.home() / "github")
    engine = ReviewEngine(github_dir=github_dir)

    if args.review_type == "list":
        print("\nAvailable review plugins:")
        for name in engine.available_plugins:
            print(f"  - {name}")
        print()
        return 0

    types = None if args.review_type == "all" else [args.review_type]

    results = engine.run(
        repo=args.repo,
        types=types,
        triggered_by="cli",
        include_baseline=args.include_baseline,
        init_baseline=args.init_baseline,
    )

    if args.json:
        output = [r.to_dict() for r in results]
        print(json.dumps(output, indent=2, ensure_ascii=False))
        if args.fail_on and any(r.has_blockers for r in results):
            return 1
        return 0

    total_findings = sum(len(r.findings) for r in results)
    total_block = sum(len(r.findings_block) for r in results)
    total_warn = sum(len(r.findings_warn) for r in results)
    total_info = sum(len(r.findings_info) for r in results)

    print(f"\n{'=' * 60}")
    print(f"  REFLEX Review: {args.repo}")
    print(f"{'=' * 60}")

    if args.init_baseline:
        print(f"  Baseline initialized with {total_findings} findings.")
        print("  Future runs will only show NEW findings.")
        print()
        return 0

    for result in results:
        dur = f"{result.duration_s:.3f}s"
        print(f"\n  Plugin: {result.review_type} ({dur})")
        print(f"  Score:  {result.score_pct}%")
        if not result.findings:
            print("  No findings")
            continue
        print()
        for f in result.findings:
            sev = f.severity.value.upper()
            auto = " [auto-fixable]" if f.auto_fixable else ""
            print(f"    [{sev:5s}] {f.rule_id}{auto}")
            print(f"            {f.message}")
            if f.adr_ref:
                print(f"            Ref: {f.adr_ref}")
            if f.fix_hint:
                print(f"            Fix: {f.fix_hint}")

    sep = "-" * 60
    print(f"\n{sep}")
    total_msg = (
        f"  Total: {total_findings} findings"
        f" ({total_block} block, {total_warn} warn,"
        f" {total_info} info)"
    )
    print(total_msg)
    auto_count = sum(
        len(r.findings_auto_fixable) for r in results
    )
    if auto_count:
        print(f"  Auto-fixable: {auto_count}")
    print()

    # Emit metrics to PostgreSQL if requested
    if getattr(args, "emit_metrics", False):
        try:
            from reflex.review.metrics import MetricsWriter

            writer = MetricsWriter()
            written = writer.write_results(results)
            if written:
                print(f"  Metrics: {written} rows written to DB")
            writer.close()
        except Exception as e:
            print(f"  Metrics: failed — {e}", file=sys.stderr)

    if args.fail_on == "block" and total_block > 0:
        return 1
    return 0



def cmd_init(args: argparse.Namespace) -> int:
    """Generate reflex.yaml from scaffold template (ADR-163)."""
    from reflex.scaffold import ScaffoldOptions, scaffold, scaffold_force

    options = ScaffoldOptions(
        hub_name=args.hub,
        tier=args.tier,
        vertical=args.vertical or "general",
        port=args.port,
        output_path=args.output,
    )

    try:
        if args.force:
            path = scaffold_force(options)
        else:
            path = scaffold(options)
    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"\n  REFLEX Scaffold: Tier {options.tier}")
    print(f"  Hub:      {options.hub_name}")
    print(f"  Vertical: {options.vertical}")
    print(f"  Port:     {options.port}")
    print(f"  Output:   {path}")
    print(f"\n  Created {path} successfully.\n")
    return 0


def cmd_platform(args: argparse.Namespace) -> int:
    """Run platform-wide REFLEX checks (ADR-163)."""
    from reflex.platform_runner import PlatformRunner

    if not args.config:
        print("ERROR: --config is required for platform command", file=sys.stderr)
        return 1

    runner = PlatformRunner.from_yaml(args.config)
    report = runner.run_all()

    if args.json:
        print(PlatformRunner.to_json(report))
    elif args.report:
        md = PlatformRunner.to_markdown(report)
        Path(args.report).write_text(md, encoding="utf-8")
        print(f"  Report written to {args.report}")
    else:
        PlatformRunner.print_report(report)

    # Exit code: 0 if all healthy, 1 if any errors
    return 0 if report.healthy_hubs == report.total_hubs else 1




def cmd_dashboard(args: argparse.Namespace) -> int:
    """Start local development dashboard (ADR-163)."""
    from reflex.dashboard import run_dashboard

    github_dir = args.github_dir or str(Path.home() / 'github')
    run_dashboard(port=args.dashboard_port, github_dir=github_dir)
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
    print("\n  Quality Rules:")
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
    p_research.add_argument("--web", "-w", action="store_true", help="Enable web search")

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape a URL (HTML or PDF)")
    p_scrape.add_argument("url", help="URL to scrape")
    p_scrape.add_argument("--json", "-j", action="store_true", help="Output JSON")

    # sds
    p_sds = sub.add_parser("sds", help="Look up SDS data for a substance")
    p_sds.add_argument("substance", nargs="+", help="Substance name or CAS number")
    p_sds.add_argument(
        "--source", "-s", default="pubchem",
        choices=["pubchem", "gestis", "all"],
        help="Data source",
    )
    p_sds.add_argument("--json", "-j", action="store_true", help="Output JSON")

    # classify
    p_classify = sub.add_parser("classify", help="Classify test failure")
    p_classify.add_argument("test_name", help="Test function name")
    p_classify.add_argument("error_message", help="Error message")
    p_classify.add_argument("--uc-file", help="UC file for context")

    # init (ADR-163)
    p_init = sub.add_parser("init", help="Generate reflex.yaml scaffold (ADR-163)")
    p_init.add_argument("--hub", required=True, help="Hub name (e.g. risk-hub)")
    p_init.add_argument(
        "--tier", type=int, default=2, choices=[1, 2],
        help="Tier level: 1 (full) or 2 (light)",
    )
    p_init.add_argument("--vertical", default="general", help="Domain vertical")
    p_init.add_argument("--port", type=int, default=8000, help="Local dev port")
    p_init.add_argument("--output", "-o", default="reflex.yaml", help="Output path")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing file")

    # platform (ADR-163)
    p_platform = sub.add_parser("platform", help="Platform-wide health report (ADR-163)")
    p_platform.add_argument("--json", "-j", action="store_true", help="Output JSON")
    p_platform.add_argument("--report", "-r", help="Write Markdown report to file")


    # dashboard (ADR-163)
    p_dash = sub.add_parser("dashboard", help="Local dev dashboard — app tiles + docker control")
    p_dash.add_argument("--dashboard-port", type=int, default=9000, help="Dashboard port (default: 9000)")
    p_dash.add_argument("--github-dir", default="", help="Path to github repos directory")

    # review (ADR-165)
    p_review = sub.add_parser(
        "review", help="Run infrastructure review plugins (ADR-165)",
    )
    p_review.add_argument(
        "review_type",
        help="Plugin: repo, compose, adr, port, all, list",
    )
    p_review.add_argument(
        "repo", nargs="?", default=".",
        help="Repo name (default: current dir)",
    )
    p_review.add_argument(
        "--json", "-j", action="store_true", help="Output JSON",
    )
    p_review.add_argument(
        "--fail-on", choices=["block", "warn"],
        help="Exit 1 if findings of this severity exist",
    )
    p_review.add_argument(
        "--include-baseline", action="store_true",
        help="Include baseline findings in output",
    )
    p_review.add_argument(
        "--init-baseline", action="store_true",
        help="Save current findings as baseline",
    )
    p_review.add_argument(
        "--github-dir", default="",
        help="Path to github repos directory",
    )
    p_review.add_argument(
        "--emit-metrics", action="store_true",
        help="Write results to PostgreSQL metrics DB",
    )
    p_review.add_argument(
        "--outline-sync", action="store_true",
        help="Sync UC overview to Outline wiki",
    )


    # infra (infrastructure lookup)
    p_infra = sub.add_parser("infra", help="Infrastructure lookup — server, port, DB, domain")
    p_infra.add_argument("repo", nargs="?", default=".", help="Repo name (default: current dir)")
    p_infra.add_argument("--all", "-a", action="store_true", help="Show all services")
    p_infra.add_argument("--json", "-j", action="store_true", help="Output JSON")
    p_infra.add_argument("--github-dir", default="", help="Path to github repos directory")

    # info
    sub.add_parser("info", help="Show config info")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "check": cmd_check,
        "research": cmd_research,
        "scrape": cmd_scrape,
        "sds": cmd_sds,
        "classify": cmd_classify,
        "init": cmd_init,
        "platform": cmd_platform,
        "dashboard": cmd_dashboard,
        "review": cmd_review,
        "infra": lambda a: __import__("reflex.infra", fromlist=["cmd_infra"]).cmd_infra(a),
        "info": cmd_info,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
