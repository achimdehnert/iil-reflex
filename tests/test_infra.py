"""Tests for reflex.infra — infrastructure info lookup."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reflex.infra import (
    _extract_db_info,
    _extract_healthcheck,
    _find_ports_yaml,
    _run_ssh,
    cmd_infra,
    format_all_live_table,
    format_all_table,
    format_info_card,
    format_live_card,
    get_all_services,
    get_live_status,
    get_service_info,
)


@pytest.fixture
def ports_yaml_content():
    return """
services:
  risk-hub:
    port: 8090
    container_name: risk_hub_web
    db: risk_hub_db
  travel-beat:
    port: 8001
    container_name: travel_beat_web
    db: travel_beat_db
"""


@pytest.fixture
def mock_ports_yaml(tmp_path, ports_yaml_content):
    """Create a mock ports.yaml file."""
    infra_dir = tmp_path / "platform" / "infra"
    infra_dir.mkdir(parents=True)
    ports_file = infra_dir / "ports.yaml"
    ports_file.write_text(ports_yaml_content)
    return ports_file


class TestGetServiceInfo:
    """Test get_service_info function."""

    def test_should_return_none_for_unknown_repo(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("nonexistent-repo", Path("/repos"))
        assert info is None

    def test_should_return_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub", Path("/repos"))
        assert info is not None
        # Result schema: per-environment ports (port_prod falls back to `port`),
        # container from `container_name`.
        assert info["port_prod"] == 8090
        assert info["container"] == "risk_hub_web"


class TestFormatInfoCard:
    """Test format_info_card output."""

    def test_should_format_service_info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            info = get_service_info("risk-hub", Path("/repos"))
        assert info is not None
        card = format_info_card(info)  # single-arg: name is taken from info["name"]
        assert "risk-hub" in card
        assert "8090" in card


COMPOSE = """
services:
  web:
    image: myapp:latest
    container_name: risk_hub_web
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8090/health/"]
  db:
    image: pgvector/pgvector:pg16
    container_name: risk_hub_db
    environment:
      POSTGRES_DB: risk_hub
      POSTGRES_USER: risk_user
    volumes:
      - risk_pgdata:/var/lib/postgresql/data
  cache:
    image: redis:7
"""


class TestFindPortsYaml:
    def test_should_find_in_infra_subdir(self, tmp_path):
        d = tmp_path / "platform" / "infra"
        d.mkdir(parents=True)
        (d / "ports.yaml").write_text("x: 1")
        assert _find_ports_yaml(tmp_path) is not None

    def test_should_return_none_when_absent(self, tmp_path):
        assert _find_ports_yaml(tmp_path) is None


class TestGetServiceInfoEnrichment:
    def test_should_enrich_with_compose_and_server(self, tmp_path):
        infra_dir = tmp_path / "platform" / "infra"
        infra_dir.mkdir(parents=True)
        (infra_dir / "ports.yaml").write_text(
            "servers:\n"
            "  prod:\n    ip: 1.2.3.4\n    ssh: user@host\n    name: hetzner\n"
            "services:\n"
            "  risk-hub:\n    prod: 8090\n    container_name: risk_hub_web\n"
            "    server: prod\n    domain_prod: risk.example.com\n    repo: org/risk-hub\n"
        )
        (tmp_path / "risk-hub").mkdir()
        (tmp_path / "risk-hub" / "docker-compose.prod.yml").write_text(COMPOSE)
        info = get_service_info("risk-hub", tmp_path)
        assert info["server_ip"] == "1.2.3.4"
        assert info["server_ssh"] == "user@host"
        assert info["db_name"] == "risk_hub"
        assert info["healthcheck"]

    def test_should_match_by_repo_field(self, tmp_path):
        infra_dir = tmp_path / "platform" / "infra"
        infra_dir.mkdir(parents=True)
        (infra_dir / "ports.yaml").write_text(
            "services:\n  some-key:\n    port: 8001\n    repo: org/my-actual-repo\n"
        )
        info = get_service_info("my-actual-repo", tmp_path)
        assert info is not None
        assert info["name"] == "some-key"


class TestFormatInfoCardFull:
    def test_should_render_full_card_with_db_drift_and_note(self):
        info = {
            "name": "risk-hub",
            "server_name": "hetzner",
            "server_ip": "1.2.3.4",
            "server_ssh": "u@h",
            "port_prod": 8090,
            "port_staging": 8190,
            "port_dev": 8290,
            "container": "risk_hub_web",
            "domain_prod": "risk.example.com",
            "domain_staging": "stg.example.com",
            "domain_aliases": ["a.com"],
            "db_image": "pgvector",
            "db_name": "risk_hub",
            "db_user": "u",
            "db_container": "risk_hub_db",
            "db_volume": "v",
            "redis": True,
            "healthcheck": "curl http://x/health",
            "repo": "org/risk-hub",
            "compose_drift": "port mismatch",
            "note": "some note",
        }
        card = format_info_card(info)
        assert "DRIFT" in card
        assert "some note" in card
        assert "Redis" in card
        assert "Aliases" in card
        assert "risk_hub_db" in card


class TestComposeExtraction:
    def _compose(self, tmp_path):
        p = tmp_path / "docker-compose.prod.yml"
        p.write_text(COMPOSE)
        return p

    def test_should_extract_db_info(self, tmp_path):
        info = _extract_db_info(self._compose(tmp_path))
        assert info["db_image"].startswith("pgvector")
        assert info["db_name"] == "risk_hub"
        assert info["db_user"] == "risk_user"
        assert info["db_container"] == "risk_hub_db"
        assert info["db_volume"] == "risk_pgdata"
        assert info["redis"] is True

    def test_should_return_empty_for_missing_compose(self, tmp_path):
        assert _extract_db_info(tmp_path / "nope.yml") == {}

    def test_should_extract_healthcheck(self, tmp_path):
        hc = _extract_healthcheck(self._compose(tmp_path))
        assert hc and "http://localhost:8090/health/" in hc

    def test_should_return_none_healthcheck_for_missing(self, tmp_path):
        assert _extract_healthcheck(tmp_path / "nope.yml") is None


class TestGetAllServices:
    def test_should_list_all_services(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            services = get_all_services(Path("/repos"))
        assert {s["name"] for s in services} == {"risk-hub", "travel-beat"}

    def test_should_return_empty_without_ports(self):
        with patch("reflex.infra._find_ports_yaml", return_value=None):
            assert get_all_services(Path("/repos")) == []


class TestFormatAllTable:
    def test_should_render_table(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            services = get_all_services(Path("/repos"))
        table = format_all_table(services)
        assert "risk-hub" in table
        assert "travel-beat" in table


class TestRunSsh:
    def test_should_return_stdout_on_success(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="output\n")):
            assert _run_ssh("user@host", "ls") == "output"

    def test_should_return_none_on_nonzero_exit(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
            assert _run_ssh("user@host", "ls") is None

    def test_should_return_none_on_exception(self):
        with patch("subprocess.run", side_effect=OSError("boom")):
            assert _run_ssh("user@host", "ls") is None

    def test_should_use_accept_new_host_key_policy(self):
        # S5: never blindly trust host keys (StrictHostKeyChecking=no = MITM-able).
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="")) as run:
            _run_ssh("user@host", "ls")
        argv = run.call_args[0][0]
        assert "StrictHostKeyChecking=accept-new" in argv
        assert "StrictHostKeyChecking=no" not in argv


class TestGetLiveStatus:
    def test_should_error_without_ssh_or_container(self):
        assert "error" in get_live_status({})
        assert "error" in get_live_status({"server_ssh": "x"})

    def test_should_collect_live_data(self):
        info = {
            "server_ssh": "user@host",
            "container": "risk_hub_web",
            "port_prod": 8090,
            "db_container": "risk_hub_db",
        }

        def fake_ssh(ssh, cmd, timeout=10):
            if "docker ps" in cmd and "risk_hub_web" in cmd:
                return "Up 2 hours (healthy)"
            if "docker stats" in cmd:
                return "1.5% 200MiB/2GiB 10%"
            if "docker ps" in cmd and "risk_hub_db" in cmd:
                return "Up 3 hours (healthy)"
            if "df -h" in cmd:
                return "42% 100G"
            if "curl" in cmd:
                return "200"
            return ""

        with patch("reflex.infra._run_ssh", side_effect=fake_ssh):
            live = get_live_status(info)
        assert live["container_status"].startswith("Up")
        assert live["cpu"] == "1.5%"
        assert live["db_status"].startswith("Up")
        assert live["disk"] == "42% 100G"
        assert live["http_status"] == "200"

    def test_should_mark_not_running_when_ssh_returns_none(self):
        with patch("reflex.infra._run_ssh", return_value=None):
            live = get_live_status({"server_ssh": "user@host", "container": "x"})
        assert live["container_status"] == "NOT RUNNING"


class TestFormatLiveCard:
    def _info(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            return get_service_info("risk-hub", Path("/repos"))

    def test_should_append_live_status(self, mock_ports_yaml):
        info = self._info(mock_ports_yaml)
        live = {
            "container_status": "Up 2 hours (healthy)",
            "http_status": "200",
            "cpu": "1%",
            "memory": "100MiB",
            "disk": "40% 100G",
            "db_status": "Up (healthy)",
        }
        card = format_live_card(info, live)
        assert "LIVE STATUS" in card
        assert "200" in card

    def test_should_show_error_in_card(self, mock_ports_yaml):
        card = format_live_card(self._info(mock_ports_yaml), {"error": "no ssh target"})
        assert "no ssh target" in card


class TestFormatAllLiveTable:
    def test_should_render_live_table(self, mock_ports_yaml):
        with patch("reflex.infra._find_ports_yaml", return_value=mock_ports_yaml):
            services = get_all_services(Path("/repos"))
        with patch(
            "reflex.infra.get_live_status",
            return_value={"container_status": "Up (healthy)", "http_status": "200"},
        ):
            table = format_all_live_table(services, Path("/repos"))
        assert "LIVE STATUS" in table
        assert "risk-hub" in table


class TestCmdInfra:
    def _args(self, **kw):
        defaults = {"github_dir": "/x", "all": False, "json": False, "repo": "risk-hub", "live": False}
        defaults.update(kw)
        return Namespace(**defaults)

    # Regression: these error paths used to crash with TypeError because
    # logger.error(..., file=...) is not a valid logging call.
    def test_should_return_1_when_no_services_for_all(self):
        with patch("reflex.infra.get_all_services", return_value=[]):
            assert cmd_infra(self._args(all=True)) == 1

    def test_should_return_1_for_unknown_repo(self):
        with patch("reflex.infra.get_service_info", return_value=None):
            assert cmd_infra(self._args(repo="ghost")) == 1

    def test_should_return_1_when_git_detection_fails(self):
        with patch("subprocess.run", side_effect=OSError("not a git repo")):
            assert cmd_infra(self._args(repo=".")) == 1

    def test_should_print_all_table(self):
        svc = [{"name": "risk-hub", "port_prod": 8090, "container": "c", "domain_prod": "d"}]
        with patch("reflex.infra.get_all_services", return_value=svc):
            assert cmd_infra(self._args(all=True)) == 0

    def test_should_output_all_json(self):
        svc = [{"name": "risk-hub", "port_prod": 8090}]
        with patch("reflex.infra.get_all_services", return_value=svc):
            assert cmd_infra(self._args(all=True, json=True)) == 0

    def test_should_print_single_info_card(self):
        with patch("reflex.infra.get_service_info", return_value={"name": "risk-hub", "port_prod": 8090}):
            assert cmd_infra(self._args(repo="risk-hub")) == 0

    def test_should_write_info_card_to_stdout(self, capsys):
        # Regression: report used logger.info, which is silent without a handler.
        with patch("reflex.infra.get_service_info", return_value={"name": "risk-hub", "port_prod": 8090}):
            cmd_infra(self._args(repo="risk-hub"))
        out = capsys.readouterr().out
        assert "risk-hub" in out
        assert "8090" in out

    def test_should_write_error_to_stderr(self, capsys):
        with patch("reflex.infra.get_service_info", return_value=None):
            assert cmd_infra(self._args(repo="ghost")) == 1
        assert "not found" in capsys.readouterr().err

    def test_should_output_single_json(self):
        with patch("reflex.infra.get_service_info", return_value={"name": "risk-hub", "port_prod": 8090}):
            assert cmd_infra(self._args(repo="risk-hub", json=True)) == 0

    def test_should_detect_repo_from_git_when_dot(self):
        with (
            patch("reflex.infra.get_service_info", return_value={"name": "risk-hub", "port_prod": 8090}) as gsi,
            patch("subprocess.run", return_value=MagicMock(stdout="/home/u/github/risk-hub\n")),
        ):
            assert cmd_infra(self._args(repo=".")) == 0
            assert gsi.call_args[0][0] == "risk-hub"

    def test_should_print_live_card(self):
        info = {"name": "risk-hub", "port_prod": 8090, "server_ssh": "", "container": ""}
        with (
            patch("reflex.infra.get_service_info", return_value=info),
            patch("reflex.infra.get_live_status", return_value={"error": "x"}),
        ):
            assert cmd_infra(self._args(repo="risk-hub", live=True)) == 0
