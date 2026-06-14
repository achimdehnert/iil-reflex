"""Tests for reflex.__main__ CLI commands."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        config.write_text("hub_name: test-hub\nvertical: chemical_safety\ndomain_keywords:\n  - Explosionsschutz\n")
        import sys

        sys.argv = ["reflex", "--config", str(config), "info"]
        result = main()
        assert result == 0

    def test_should_fail_without_config(self):
        import sys

        sys.argv = ["reflex", "info"]
        result = main()
        assert result == 1

    def test_should_show_htmx_and_permissions(self, monkeypatch, tmp_path):
        cfg = tmp_path / "reflex.yaml"
        cfg.write_text(
            "hub_name: h\n"
            "htmx_patterns:\n  banned:\n    - hx-boost\n"
            "permissions_matrix:\n  /a/:\n    anonymous: 200\n"
        )
        monkeypatch.setattr(sys, "argv", ["reflex", "-c", str(cfg), "info"])
        assert main() == 0


class TestCLIClassify:
    """Test 'python -m reflex classify' command."""

    def test_should_classify_infra_error(self):
        import sys

        sys.argv = [
            "reflex",
            "classify",
            "test_should_load_page",
            "TimeoutError: page.goto timeout 30000ms",
        ]
        result = main()
        assert result == 0

    def test_should_classify_with_uc_file(self, monkeypatch, tmp_path):
        uc = tmp_path / "uc.md"
        uc.write_text("## UC-001\n\n**Akteur:** X\n")
        monkeypatch.setattr(
            sys, "argv", ["reflex", "classify", "test_x", "AssertionError: heading", "--uc-file", str(uc)]
        )
        assert main() == 0


class TestCLINoCommand:
    def test_should_print_help_and_return_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["reflex"])
        assert main() == 0


class TestCLIResearch:
    def test_should_research_and_emit_json(self, monkeypatch):
        result = SimpleNamespace(
            topic="ATEX zones",
            vertical="chemical_safety",
            facts=["fact one"],
            gaps=["gap one"],
            contradictions=[],
            confidence=0.82,
            sources_used=["LLM"],
        )
        agent = MagicMock()
        agent.research.return_value = result
        with (
            patch("reflex.llm_providers.get_provider", return_value=MagicMock(model="groq/x")),
            patch("reflex.agent.DomainAgent", return_value=agent),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "research", "ATEX", "zones", "--json"])
            assert main() == 0
        agent.research.assert_called_once_with("ATEX zones")

    def test_should_research_with_web_and_contradictions(self, monkeypatch):
        result = SimpleNamespace(
            topic="t",
            vertical="v",
            facts=[],
            gaps=[],
            contradictions=["c1"],
            confidence=0.5,
            sources_used=[],
        )
        agent = MagicMock()
        agent.research.return_value = result
        with (
            patch("reflex.llm_providers.get_provider", return_value=MagicMock(model="m")),
            patch("reflex.agent.DomainAgent", return_value=agent),
            patch("reflex.web.HttpxWebProvider"),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "research", "topic", "--web"])
            assert main() == 0


class TestCLIScrape:
    def _web_returning(self, page):
        web = MagicMock()
        web.fetch.return_value = page
        return web

    def test_should_scrape_and_print(self, monkeypatch):
        from reflex.types import WebPage

        page = WebPage(url="http://x", title="T", text="body text", status_code=200, content_type="text/html")
        with patch("reflex.web.HttpxWebProvider", return_value=self._web_returning(page)):
            monkeypatch.setattr(sys, "argv", ["reflex", "scrape", "http://x"])
            assert main() == 0

    def test_should_scrape_json(self, monkeypatch):
        from reflex.types import WebPage

        page = WebPage(url="http://x", title="T", text="b", status_code=200, content_type="text/html")
        with patch("reflex.web.HttpxWebProvider", return_value=self._web_returning(page)):
            monkeypatch.setattr(sys, "argv", ["reflex", "scrape", "http://x", "--json"])
            assert main() == 0


class TestCLISds:
    def test_should_lookup_pubchem(self, monkeypatch):
        from reflex.types import SDSData

        adapter = MagicMock()
        adapter.lookup_by_name.return_value = SDSData(substance_name="Ethanol", cas_number="64-17-5")
        with (
            patch("reflex.web.PubChemAdapter", return_value=adapter),
            patch("reflex.web.HttpxWebProvider"),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "sds", "Ethanol", "--json"])
            assert main() == 0

    def test_should_report_pubchem_miss(self, monkeypatch):
        adapter = MagicMock()
        adapter.lookup_by_name.return_value = None
        with (
            patch("reflex.web.PubChemAdapter", return_value=adapter),
            patch("reflex.web.HttpxWebProvider"),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "sds", "Nope"])
            assert main() == 0

    def test_should_lookup_gestis(self, monkeypatch):
        from reflex.types import SDSData

        adapter = MagicMock()
        adapter.search.return_value = [{"name": "Ethanol", "cas": "64-17-5", "zvg": "011000"}]
        adapter.lookup.return_value = SDSData(substance_name="Ethanol")
        with (
            patch("reflex.web.GESTISAdapter", return_value=adapter),
            patch("reflex.web.HttpxWebProvider"),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "sds", "Ethanol", "--source", "gestis", "--json"])
            assert main() == 0

    def test_should_report_gestis_miss(self, monkeypatch):
        adapter = MagicMock()
        adapter.search.return_value = []
        with (
            patch("reflex.web.GESTISAdapter", return_value=adapter),
            patch("reflex.web.HttpxWebProvider"),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "sds", "Nope", "--source", "gestis"])
            assert main() == 0


class TestCLIInit:
    def test_should_scaffold(self, monkeypatch, tmp_path):
        out = tmp_path / "reflex.yaml"
        with patch("reflex.scaffold.scaffold", return_value=out):
            monkeypatch.setattr(sys, "argv", ["reflex", "init", "--hub", "risk-hub", "--tier", "1"])
            assert main() == 0

    def test_should_return_1_on_file_exists(self, monkeypatch):
        with patch("reflex.scaffold.scaffold", side_effect=FileExistsError("exists")):
            monkeypatch.setattr(sys, "argv", ["reflex", "init", "--hub", "x"])
            assert main() == 1


class TestCLIPlatform:
    def test_should_require_config(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["reflex", "platform"])
        assert main() == 1

    def test_should_run_and_emit_json(self, monkeypatch, tmp_path):
        cfg = tmp_path / "p.yaml"
        cfg.write_text("hubs: []")
        report = MagicMock(healthy_hubs=1, total_hubs=1)
        runner = MagicMock()
        runner.run_all.return_value = report
        with patch("reflex.platform_runner.PlatformRunner") as PR:
            PR.from_yaml.return_value = runner
            PR.to_json.return_value = "{}"
            monkeypatch.setattr(sys, "argv", ["reflex", "-c", str(cfg), "platform", "--json"])
            assert main() == 0

    def test_should_return_1_when_unhealthy(self, monkeypatch, tmp_path):
        cfg = tmp_path / "p.yaml"
        cfg.write_text("hubs: []")
        report = MagicMock(healthy_hubs=0, total_hubs=2)
        runner = MagicMock()
        runner.run_all.return_value = report
        with patch("reflex.platform_runner.PlatformRunner") as PR:
            PR.from_yaml.return_value = runner
            monkeypatch.setattr(sys, "argv", ["reflex", "-c", str(cfg), "platform"])
            assert main() == 1

    def test_should_write_markdown_report(self, monkeypatch, tmp_path):
        cfg = tmp_path / "p.yaml"
        cfg.write_text("hubs: []")
        out = tmp_path / "report.md"
        report = MagicMock(healthy_hubs=1, total_hubs=1)
        runner = MagicMock()
        runner.run_all.return_value = report
        with patch("reflex.platform_runner.PlatformRunner") as PR:
            PR.from_yaml.return_value = runner
            PR.to_markdown.return_value = "# report"
            monkeypatch.setattr(sys, "argv", ["reflex", "-c", str(cfg), "platform", "--report", str(out)])
            assert main() == 0
        assert out.read_text() == "# report"


class TestCLIDashboard:
    def test_should_start_dashboard(self, monkeypatch):
        with patch("reflex.dashboard.run_dashboard") as rd:
            monkeypatch.setattr(sys, "argv", ["reflex", "dashboard", "--dashboard-port", "9999"])
            assert main() == 0
        rd.assert_called_once()


class TestCLIReview:
    def test_should_list_plugins(self, monkeypatch):
        engine = MagicMock(available_plugins=["repo", "compose"])
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "list"])
            assert main() == 0

    def test_should_run_with_no_findings(self, monkeypatch):
        from reflex.review.types import ReviewResult

        engine = MagicMock()
        engine.run.return_value = [ReviewResult(repo="r", review_type="repo")]
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "repo", "r"])
            assert main() == 0

    def test_should_fail_on_block(self, monkeypatch):
        from reflex.review.types import Finding, ReviewResult, ReviewSeverity

        finding = Finding("rule.x", ReviewSeverity.BLOCK, "bad", adr_ref="ADR-1", fix_hint="do x", auto_fixable=True)
        res = ReviewResult(repo="r", review_type="repo", findings=[finding])
        engine = MagicMock()
        engine.run.return_value = [res]
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "repo", "r", "--fail-on", "block"])
            assert main() == 1

    def test_should_emit_json(self, monkeypatch):
        from reflex.review.types import ReviewResult

        engine = MagicMock()
        engine.run.return_value = [ReviewResult(repo="r", review_type="repo")]
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "all", "r", "--json"])
            assert main() == 0

    def test_should_json_fail_on_block(self, monkeypatch):
        from reflex.review.types import Finding, ReviewResult, ReviewSeverity

        res = ReviewResult(repo="r", review_type="repo", findings=[Finding("x", ReviewSeverity.BLOCK, "bad")])
        engine = MagicMock()
        engine.run.return_value = [res]
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "repo", "r", "--json", "--fail-on", "block"])
            assert main() == 1

    def test_should_init_baseline(self, monkeypatch):
        from reflex.review.types import ReviewResult

        engine = MagicMock()
        engine.run.return_value = [ReviewResult(repo="r", review_type="repo")]
        with patch("reflex.review.ReviewEngine", return_value=engine):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "repo", "r", "--init-baseline"])
            assert main() == 0

    def test_should_emit_metrics(self, monkeypatch):
        from reflex.review.types import ReviewResult

        engine = MagicMock()
        engine.run.return_value = [ReviewResult(repo="r", review_type="repo")]
        writer = MagicMock()
        writer.write_results.return_value = 1
        with (
            patch("reflex.review.ReviewEngine", return_value=engine),
            patch("reflex.review.metrics.MetricsWriter", return_value=writer),
        ):
            monkeypatch.setattr(sys, "argv", ["reflex", "review", "repo", "r", "--emit-metrics"])
            assert main() == 0
        writer.write_results.assert_called_once()


class TestCLIInfraDispatch:
    def test_should_dispatch_to_infra(self, monkeypatch):
        with patch("reflex.infra.cmd_infra", return_value=0) as ci:
            monkeypatch.setattr(sys, "argv", ["reflex", "infra", "risk-hub"])
            assert main() == 0
        ci.assert_called_once()
