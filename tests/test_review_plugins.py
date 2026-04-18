"""Tests for reflex.review.plugins — repo, compose, adr, port plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from reflex.review.plugins.adr_plugin import ADRPlugin
from reflex.review.plugins.compose_plugin import ComposePlugin
from reflex.review.plugins.port_plugin import PortPlugin
from reflex.review.plugins.repo_plugin import RepoPlugin
from reflex.review.types import ReviewSeverity

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_repo(tmp_path: Path) -> Path:
    """Create a minimal repo with required files."""
    repo = tmp_path / "test-hub"
    repo.mkdir()
    (repo / "README.md").write_text("# Test Hub\n")
    (repo / ".gitignore").write_text(".env.prod\n__pycache__\n")
    (repo / "docker-compose.prod.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: ghcr.io/test/test-hub:latest\n"
        '    ports:\n      - "127.0.0.1:8080:8000"\n'
        "    env_file:\n      - .env.prod\n"
        "    restart: unless-stopped\n"
        "    logging:\n"
        '      driver: "json-file"\n'
        "    healthcheck:\n"
        "      test: python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/livez/\")'\n"
        "    deploy:\n"
        "      resources:\n"
        "        limits:\n"
        "          memory: 512M\n"
    )
    (repo / ".env.prod.example").write_text("SECRET_KEY=changeme\n")
    (repo / "docker" / "app").mkdir(parents=True)
    (repo / "docker" / "app" / "Dockerfile").write_text(
        "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\n"
    )
    (repo / "docs").mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    return repo


@pytest.fixture
def github_dir(tmp_path: Path, minimal_repo: Path) -> Path:
    """Return the parent dir that acts as github_dir."""
    return tmp_path


# ── RepoPlugin ───────────────────────────────────────────────────────────────


class TestRepoPlugin:
    def test_should_pass_complete_repo(self, minimal_repo: Path, github_dir: Path):
        plugin = RepoPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        # A complete repo should have no BLOCK findings
        block_findings = [f for f in findings if f.severity == ReviewSeverity.BLOCK]
        assert block_findings == [], [f.rule_id for f in block_findings]

    def test_should_detect_missing_readme(self, minimal_repo: Path):
        (minimal_repo / "README.md").unlink()
        plugin = RepoPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "repo.missing_readme" in rule_ids

    def test_should_detect_env_interpolation(self, minimal_repo: Path):
        compose = minimal_repo / "docker-compose.prod.yml"
        compose.write_text(
            "services:\n"
            "  web:\n"
            "    environment:\n"
            "      SECRET_KEY: ${SECRET_KEY}\n"
        )
        plugin = RepoPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "repo.env_interpolation" in rule_ids

    def test_should_detect_env_not_gitignored(self, minimal_repo: Path):
        (minimal_repo / ".gitignore").write_text("__pycache__\n")
        plugin = RepoPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "repo.env_not_gitignored" in rule_ids

    def test_should_detect_missing_dockerfile(self, minimal_repo: Path):
        import shutil
        shutil.rmtree(minimal_repo / "docker")
        plugin = RepoPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "repo.missing_dockerfile" in rule_ids

    def test_should_detect_nonexistent_repo(self, tmp_path: Path):
        plugin = RepoPlugin()
        findings = plugin.check("missing", {"repo_path": str(tmp_path / "missing")})
        assert any(f.rule_id == "repo.not_found" for f in findings)


# ── ComposePlugin ────────────────────────────────────────────────────────────


class TestComposePlugin:
    def test_should_pass_good_compose(self, minimal_repo: Path):
        plugin = ComposePlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        block_findings = [f for f in findings if f.severity == ReviewSeverity.BLOCK]
        assert block_findings == [], [f.rule_id for f in block_findings]

    def test_should_detect_missing_compose(self, minimal_repo: Path):
        (minimal_repo / "docker-compose.prod.yml").unlink()
        plugin = ComposePlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        assert any(f.rule_id == "compose.missing" for f in findings)

    def test_should_detect_healthcheck_in_dockerfile(self, minimal_repo: Path):
        df = minimal_repo / "docker" / "app" / "Dockerfile"
        df.write_text(
            "FROM python:3.12-slim\n"
            "HEALTHCHECK CMD curl -f http://localhost:8000/livez/ || exit 1\n"
        )
        plugin = ComposePlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        assert any(f.rule_id == "compose.healthcheck_in_dockerfile" for f in findings)

    def test_should_detect_no_restart_policy(self, minimal_repo: Path):
        compose = minimal_repo / "docker-compose.prod.yml"
        compose.write_text(
            "services:\n  web:\n    image: test\n    env_file:\n      - .env\n"
            "    logging:\n      driver: json-file\n"
            "    healthcheck:\n      test: echo ok\n"
        )
        plugin = ComposePlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "compose.no_restart_policy" in rule_ids

    def test_should_detect_port_all_interfaces(self, minimal_repo: Path):
        compose = minimal_repo / "docker-compose.prod.yml"
        compose.write_text(
            "services:\n  web:\n    image: test\n"
            '    ports:\n      - "8080:8000"\n'
            "    env_file:\n      - .env\n"
            "    restart: unless-stopped\n"
            "    logging:\n      driver: json-file\n"
            "    healthcheck:\n      test: echo ok\n"
        )
        plugin = ComposePlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "compose.port_exposed_all_interfaces" in rule_ids


# ── ADRPlugin ────────────────────────────────────────────────────────────────


class TestADRPlugin:
    def test_should_report_no_adr_directory(self, minimal_repo: Path):
        plugin = ADRPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "adr.no_adr_directory" in rule_ids

    def test_should_detect_missing_frontmatter(self, minimal_repo: Path):
        adr_dir = minimal_repo / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001-test.md").write_text("# ADR-001: Test\n\nSome content.\n")

        plugin = ADRPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "adr.missing_frontmatter_title" in rule_ids
        assert "adr.missing_frontmatter_status" in rule_ids
        assert "adr.missing_frontmatter_date" in rule_ids

    def test_should_pass_valid_adr(self, minimal_repo: Path):
        adr_dir = minimal_repo / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001-test.md").write_text(
            "---\n"
            "title: 'ADR-001: Test Decision'\n"
            "status: proposed\n"
            "date: 2026-01-01\n"
            "---\n\n"
            "# ADR-001: Test Decision\n\n"
            "## 1. Context\n\n"
            "## 2. Decision Drivers\n\n"
            "## 3. Considered Options\n\n"
            "## 4. Decision Outcome\n\n"
        )

        plugin = ADRPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        block_findings = [f for f in findings if f.severity == ReviewSeverity.BLOCK]
        assert block_findings == [], [f.rule_id for f in block_findings]

    def test_should_detect_missing_impl_status_for_accepted(self, minimal_repo: Path):
        adr_dir = minimal_repo / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002-accepted.md").write_text(
            "---\n"
            "title: 'ADR-002: Accepted'\n"
            "status: accepted\n"
            "date: 2026-01-01\n"
            "---\n\n"
            "# ADR-002\n"
        )

        plugin = ADRPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(minimal_repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "adr.missing_implementation_status" in rule_ids


# ── PortPlugin ───────────────────────────────────────────────────────────────


class TestPortPlugin:
    def test_should_report_missing_ports_yaml(self, tmp_path: Path):
        repo_path = tmp_path / "test-hub"
        repo_path.mkdir()
        plugin = PortPlugin()
        findings = plugin.check(
            "test-hub",
            {"repo_path": str(repo_path), "github_dir": str(tmp_path)},
        )
        assert any(f.rule_id == "port.ports_yaml_missing" for f in findings)

    def test_should_detect_port_drift(self, tmp_path: Path):
        # Create ports.yaml
        platform_dir = tmp_path / "platform" / "infra"
        platform_dir.mkdir(parents=True)
        (platform_dir / "ports.yaml").write_text(
            "services:\n"
            "  test-hub:\n"
            "    prod: 8080\n"
            "    staging: 8080\n"
            "    dev: 8080\n"
            "    container_name: test_hub_web\n"
            "    repo: achimdehnert/test-hub\n"
        )

        # Create repo with wrong port
        repo_path = tmp_path / "test-hub"
        repo_path.mkdir()
        (repo_path / "docker-compose.prod.yml").write_text(
            "services:\n"
            "  web:\n"
            '    ports:\n      - "127.0.0.1:9999:8000"\n'
        )

        plugin = PortPlugin()
        findings = plugin.check(
            "test-hub",
            {"repo_path": str(repo_path), "github_dir": str(tmp_path)},
        )
        assert any(f.rule_id == "port.port_drift" for f in findings)

    def test_should_pass_matching_port(self, tmp_path: Path):
        platform_dir = tmp_path / "platform" / "infra"
        platform_dir.mkdir(parents=True)
        (platform_dir / "ports.yaml").write_text(
            "services:\n"
            "  test-hub:\n"
            "    prod: 8080\n"
            "    repo: achimdehnert/test-hub\n"
        )

        repo_path = tmp_path / "test-hub"
        repo_path.mkdir()
        (repo_path / "docker-compose.prod.yml").write_text(
            "services:\n"
            "  web:\n"
            '    ports:\n      - "127.0.0.1:8080:8000"\n'
        )

        plugin = PortPlugin()
        findings = plugin.check(
            "test-hub",
            {"repo_path": str(repo_path), "github_dir": str(tmp_path)},
        )
        assert not any(f.rule_id == "port.port_drift" for f in findings)


# ── UC Plugin ─────────────────────────────────────────────────────────────────


class TestUCPlugin:
    """Tests for the UC completeness plugin."""

    def test_no_uc_directory(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        assert len(findings) == 1
        assert findings[0].rule_id == "uc.no_uc_directory"
        assert findings[0].severity == ReviewSeverity.WARN

    def test_empty_uc_directory(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        (tmp_path / "docs" / "use-cases").mkdir(parents=True)
        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        assert any(
            f.rule_id == "uc.no_uc_files" for f in findings
        )

    def test_valid_uc_file(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        uc_dir = tmp_path / "docs" / "use-cases"
        uc_dir.mkdir(parents=True)
        for i in range(1, 4):
            (uc_dir / f"UC-{i:03d}-test.md").write_text(
                f"# UC-{i:03d}: Test\n\n"
                "**Status:** Implemented\n\n"
                "## Akteur\n\nAdmin\n\n"
                "## Ziel\n\nEtwas testen\n\n"
                "## Vorbedingung\n\nUser eingeloggt\n\n"
                "## Hauptszenario\n\n1. Step\n2. Step\n\n"
                "## Nachbedingung\n\nDaten gespeichert\n"
            )
        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        assert len(findings) == 0

    def test_missing_required_section(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        uc_dir = tmp_path / "docs" / "use-cases"
        uc_dir.mkdir(parents=True)
        (uc_dir / "UC-001-bad.md").write_text(
            "# UC-001: Bad UC\n\n"
            "**Status:** Draft\n\n"
            "Some text without proper sections.\n"
        )
        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        block_findings = [
            f for f in findings
            if f.severity == ReviewSeverity.BLOCK
        ]
        assert len(block_findings) >= 3

    def test_all_draft_warning(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        uc_dir = tmp_path / "docs" / "use-cases"
        uc_dir.mkdir(parents=True)
        for i in range(1, 4):
            (uc_dir / f"UC-{i:03d}-test.md").write_text(
                f"# UC-{i:03d}: Test\n\n"
                "**Status:** Draft\n\n"
                "## Akteur\n\nUser\n\n"
                "## Ziel\n\nTest\n\n"
                "## Vorbedingung\n\nLogin\n\n"
                "## Hauptszenario\n\n1. Do\n\n"
                "## Nachbedingung\n\nDone\n"
            )
        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        assert any(
            f.rule_id == "uc.all_draft" for f in findings
        )

    def test_low_uc_count_info(self, tmp_path: Path):
        from reflex.review.plugins.uc_plugin import UCPlugin

        uc_dir = tmp_path / "docs" / "use-cases"
        uc_dir.mkdir(parents=True)
        (uc_dir / "UC-001-only.md").write_text(
            "# UC-001: Only UC\n\n"
            "**Status:** Implemented\n\n"
            "## Akteur\n\nAdmin\n\n"
            "## Ziel\n\nEinziger UC\n\n"
            "## Vorbedingung\n\nLogin\n\n"
            "## Hauptszenario\n\n1. Do\n\n"
            "## Nachbedingung\n\nDone\n"
        )
        plugin = UCPlugin()
        findings = plugin.check(
            "test-hub", {"repo_path": str(tmp_path)}
        )
        assert any(
            f.rule_id == "uc.low_uc_count" for f in findings
        )


# ── InfraPlugin ──────────────────────────────────────────────────────────────


class TestInfraPlugin:
    """Tests for the infrastructure health plugin."""

    def test_should_report_no_backup_script(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        repo.mkdir()
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.no_backup_script" in rule_ids

    def test_should_detect_backup_without_retention(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "backup.sh").write_text(
            "#!/bin/bash\n"
            "DATE=$(date +%Y-%m-%d)\n"
            "docker exec db pg_dump -U app app | gzip > /opt/backups/$DATE.sql.gz\n"
        )
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.backup_no_retention" in rule_ids

    def test_should_pass_backup_with_retention(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "backup.sh").write_text(
            "#!/bin/bash\n"
            "KEEP_DAYS=3\n"
            "DISK_PCT=$(df / --output=pcent | tail -1 | tr -d ' %')\n"
            "MAX_BACKUP_GB=10\n"
            "find /opt/backups -mtime +$KEEP_DAYS -delete\n"
        )
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.backup_no_retention" not in rule_ids
        assert "infra.backup_no_disk_check" not in rule_ids
        assert "infra.backup_no_size_limit" not in rule_ids

    def test_should_detect_backup_no_disk_check(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "backup.sh").write_text(
            "#!/bin/bash\n"
            "KEEP_DAYS=3\n"
            "find /opt/backups -mtime +$KEEP_DAYS -delete\n"
        )
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.backup_no_disk_check" in rule_ids

    def test_should_detect_export_without_cleanup(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "backup.sh").write_text(
            "#!/bin/bash\n"
            "KEEP_DAYS=1\n"
            "DISK_PCT=$(df / --output=pcent | tail -1)\n"
            "MAX_BACKUP_GB=15\n"
            "find /opt/backups -mtime +$KEEP_DAYS -delete\n"
            "cp $EXPORT_VOL/export-$DATE.zip $BACKUP_DIR/\n"
        )
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.backup_no_export_cleanup" in rule_ids

    def test_should_detect_no_health_endpoint(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        repo.mkdir()
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.no_health_endpoint" in rule_ids

    def test_should_pass_with_health_urls(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        config = repo / "config"
        config.mkdir(parents=True)
        (config / "urls.py").write_text(
            "from django.urls import path\n"
            "from common.views import liveness, readiness\n"
            "urlpatterns = [\n"
            "    path('livez/', liveness),\n"
            "    path('healthz/', readiness),\n"
            "]\n"
        )
        common = repo / "common"
        common.mkdir(parents=True)
        (common / "healthz.py").write_text(
            "import shutil\n"
            "def readiness(request):\n"
            "    total, used, free = shutil.disk_usage('/')\n"
            "    return JsonResponse({'disk': 'ok'})\n"
        )
        plugin = InfraPlugin()
        findings = plugin.check("test-hub", {"repo_path": str(repo)})
        rule_ids = {f.rule_id for f in findings}
        assert "infra.no_health_endpoint" not in rule_ids
        assert "infra.no_livez_url" not in rule_ids
        assert "infra.no_healthz_url" not in rule_ids

    def test_should_collect_metrics(self, tmp_path: Path):
        repo = tmp_path / "test-hub"
        scripts = repo / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "backup.sh").write_text(
            "#!/bin/bash\nKEEP_DAYS=1\nfind /opt -mtime +1 -delete\n"
        )
        plugin = InfraPlugin()
        plugin.check("test-hub", {"repo_path": str(repo)})
        assert hasattr(plugin, "last_metrics")
        assert plugin.last_metrics["backup_scripts"] == 1
