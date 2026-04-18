"""
REFLEX Review Plugin: security — Repository security checks (ADR-165).

Scans repos for common security issues:
- Hardcoded secrets in code and config
- World-readable .env files
- Docker ports bound to 0.0.0.0
- Insecure Dockerfile patterns
- Missing .dockerignore (secret leakage)
- DEBUG=True in production configs
"""

from __future__ import annotations

import re
from pathlib import Path

from reflex.review.types import (
    Finding,
    FixComplexity,
    ReviewSeverity,
)


class SecurityPlugin:
    name = "security"
    applicable_tiers = [1, 2]

    # Patterns that indicate hardcoded secrets
    SECRET_PATTERNS = [
        (r"(?i)(password|passwd|secret|token|api_key|apikey)\s*=\s*[\"'][^\"'${\s]{8,}[\"']", "Hardcoded secret"),
        (r"ghp_[A-Za-z0-9_]{36}", "GitHub Personal Access Token"),
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI/Stripe secret key"),
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    ]

    # Files to skip when scanning for secrets
    SKIP_PATTERNS = [
        "*.pyc",
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "*.whl",
        "*.egg-info",
        "migrations",
        "staticfiles",
        ".windsurf",
    ]

    # Directories where hardcoded test passwords are expected
    TEST_DIRS = {"tests", "test", "testing", "fixtures"}

    # Extensions to scan
    SCAN_EXTENSIONS = {
        ".py",
        ".yml",
        ".yaml",
        ".toml",
        ".cfg",
        ".ini",
        ".conf",
        ".sh",
        ".bash",
        ".env.example",
        ".md",
    }

    def check(self, repo: str, context: dict) -> list[Finding]:
        repo_path = Path(context.get("repo_path", ""))
        if not repo_path.exists():
            return []

        findings: list[Finding] = []

        # 1. Check for .dockerignore
        findings.extend(self._check_dockerignore(repo_path))

        # 2. Check Dockerfile for security issues
        findings.extend(self._check_dockerfile(repo_path))

        # 3. Check docker-compose for exposed ports
        findings.extend(self._check_compose_ports(repo_path))

        # 4. Check for DEBUG=True in production settings
        findings.extend(self._check_debug_settings(repo_path))

        # 5. Check for hardcoded secrets in code
        findings.extend(self._check_hardcoded_secrets(repo_path))

        # 6. Check .env.example for real values
        findings.extend(self._check_env_example(repo_path))

        # 7. Check .gitignore for secret exclusions
        findings.extend(self._check_gitignore_secrets(repo_path))

        return findings

    def _check_dockerignore(self, repo_path: Path) -> list[Finding]:
        """Missing .dockerignore can leak .env, .git, secrets into image."""
        has_dockerfile = any((repo_path / p).exists() for p in ["Dockerfile", "docker/app/Dockerfile"])
        if not has_dockerfile:
            return []

        dockerignore = repo_path / ".dockerignore"
        if not dockerignore.exists():
            return [
                Finding(
                    rule_id="security.missing_dockerignore",
                    severity=ReviewSeverity.BLOCK,
                    message="Missing .dockerignore — .env, .git, secrets may leak into Docker image",
                    adr_ref="ADR-021 §3",
                    fix_hint="Create .dockerignore with: .env* .git .reflex __pycache__ *.pyc",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            ]

        content = dockerignore.read_text(encoding="utf-8", errors="ignore")
        findings = []
        if ".env" not in content:
            findings.append(
                Finding(
                    rule_id="security.dockerignore_missing_env",
                    severity=ReviewSeverity.WARN,
                    message=".dockerignore does not exclude .env files — secrets may leak into image",
                    fix_hint="Add '.env*' to .dockerignore",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            )
        if ".git" not in content:
            findings.append(
                Finding(
                    rule_id="security.dockerignore_missing_git",
                    severity=ReviewSeverity.WARN,
                    message=".dockerignore does not exclude .git — full history leaks into image",
                    fix_hint="Add '.git' to .dockerignore",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            )
        return findings

    def _check_dockerfile(self, repo_path: Path) -> list[Finding]:
        """Check Dockerfile for security anti-patterns."""
        findings = []
        for df_path in ["Dockerfile", "docker/app/Dockerfile"]:
            dockerfile = repo_path / df_path
            if not dockerfile.exists():
                continue
            content = dockerfile.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()

            # Running as root (no USER directive)
            has_user = any(line.strip().startswith("USER ") for line in lines)
            if not has_user:
                findings.append(
                    Finding(
                        rule_id="security.dockerfile_runs_as_root",
                        severity=ReviewSeverity.BLOCK,
                        message=f"{df_path}: No USER directive — container runs as root",
                        adr_ref="ADR-021 §3.2",
                        fix_hint="Add 'USER <appuser>' before CMD",
                        file_path=df_path,
                        fix_complexity=FixComplexity.SIMPLE,
                    )
                )

            # COPY of .env files
            for i, line in enumerate(lines, 1):
                if re.match(r"^\s*COPY\s+.*\.env", line):
                    findings.append(
                        Finding(
                            rule_id="security.dockerfile_copies_env",
                            severity=ReviewSeverity.BLOCK,
                            message=f"{df_path}:{i}: COPY of .env file — secrets baked into image",
                            fix_hint="Use env_file in docker-compose instead of COPY .env",
                            file_path=df_path,
                            fix_complexity=FixComplexity.SIMPLE,
                        )
                    )

            # Using latest tag
            for i, line in enumerate(lines, 1):
                if re.match(r"^\s*FROM\s+\S+:latest\s*$", line):
                    findings.append(
                        Finding(
                            rule_id="security.dockerfile_latest_tag",
                            severity=ReviewSeverity.WARN,
                            message=f"{df_path}:{i}: FROM uses :latest tag — not reproducible",
                            fix_hint="Pin to specific version, e.g. python:3.12-slim",
                            file_path=df_path,
                            fix_complexity=FixComplexity.TRIVIAL,
                        )
                    )
        return findings

    def _check_compose_ports(self, repo_path: Path) -> list[Finding]:
        """Check for ports exposed on all interfaces (0.0.0.0)."""
        findings = []
        compose_file = repo_path / "docker-compose.prod.yml"
        if not compose_file.exists():
            return []

        content = compose_file.read_text(encoding="utf-8", errors="ignore")

        # Find port bindings on 0.0.0.0 (explicit or implicit like "8080:8000")
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip().strip("- ").strip('"').strip("'")
            # Match "0.0.0.0:PORT:PORT" or bare "PORT:PORT" (no 127.0.0.1)
            if re.match(r"^0\.0\.0\.0:\d+:\d+$", stripped):
                findings.append(
                    Finding(
                        rule_id="security.compose_port_all_interfaces",
                        severity=ReviewSeverity.BLOCK,
                        message=f"docker-compose.prod.yml:{i}: Port bound to 0.0.0.0 — accessible from internet",
                        adr_ref="ADR-164 §5.1",
                        fix_hint="Change to 127.0.0.1:PORT:PORT",
                        file_path="docker-compose.prod.yml",
                        auto_fixable=True,
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )
            elif re.match(r"^\d{4,5}:\d{4,5}$", stripped) and not line.strip().startswith("#"):
                # Bare port binding like "8080:8000" — implicitly 0.0.0.0
                findings.append(
                    Finding(
                        rule_id="security.compose_port_implicit_bind",
                        severity=ReviewSeverity.WARN,
                        message=(f"docker-compose.prod.yml:{i}: Port '{stripped}' implicitly binds to all interfaces"),
                        adr_ref="ADR-164 §5.1",
                        fix_hint=f"Change to 127.0.0.1:{stripped}",
                        file_path="docker-compose.prod.yml",
                        auto_fixable=True,
                        fix_complexity=FixComplexity.TRIVIAL,
                    )
                )
        return findings

    def _check_debug_settings(self, repo_path: Path) -> list[Finding]:
        """Check for DEBUG=True in production settings."""
        findings = []
        prod_settings = repo_path / "config" / "settings" / "production.py"
        if not prod_settings.exists():
            return []

        content = prod_settings.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\s*DEBUG\s*=\s*True", content, re.MULTILINE):
            findings.append(
                Finding(
                    rule_id="security.debug_true_production",
                    severity=ReviewSeverity.BLOCK,
                    message="DEBUG=True in production settings — exposes stack traces and sensitive data",
                    fix_hint="Set DEBUG = False or use env: DEBUG = os.getenv('DEBUG', 'False') == 'True'",
                    file_path="config/settings/production.py",
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            )
        return findings

    def _check_hardcoded_secrets(self, repo_path: Path) -> list[Finding]:
        """Scan code files for hardcoded secrets."""
        findings = []
        seen_rules = set()

        for file_path in self._scan_files(repo_path):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path = str(file_path.relative_to(repo_path))

            # Skip example/template files and test files
            if ".example" in rel_path or "template" in rel_path.lower():
                continue
            parts = Path(rel_path).parts
            if any(p in self.TEST_DIRS for p in parts):
                continue

            for pattern, desc in self.SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    rule_key = f"security.hardcoded_secret:{rel_path}:{desc}"
                    if rule_key not in seen_rules:
                        seen_rules.add(rule_key)
                        findings.append(
                            Finding(
                                rule_id="security.hardcoded_secret",
                                severity=ReviewSeverity.BLOCK,
                                message=f"{rel_path}: {desc} detected in source code",
                                fix_hint="Move to .env file and use os.getenv()",
                                file_path=rel_path,
                                fix_complexity=FixComplexity.SIMPLE,
                            )
                        )
        return findings

    def _check_env_example(self, repo_path: Path) -> list[Finding]:
        """Check .env.example/.env.prod.example for accidentally included real values."""
        findings = []
        for env_name in [".env.example", ".env.prod.example"]:
            env_file = repo_path / env_name
            if not env_file.exists():
                continue
            content = env_file.read_text(encoding="utf-8", errors="ignore")
            for pattern, desc in self.SECRET_PATTERNS:
                if re.search(pattern, content):
                    findings.append(
                        Finding(
                            rule_id="security.env_example_has_secrets",
                            severity=ReviewSeverity.BLOCK,
                            message=f"{env_name}: Contains what looks like a real {desc}",
                            fix_hint=f"Replace real values in {env_name} with placeholders like 'change-me'",
                            file_path=env_name,
                            fix_complexity=FixComplexity.TRIVIAL,
                        )
                    )
        return findings

    def _check_gitignore_secrets(self, repo_path: Path) -> list[Finding]:
        """Check .gitignore excludes secret files."""
        gitignore = repo_path / ".gitignore"
        if not gitignore.exists():
            return []
        content = gitignore.read_text(encoding="utf-8", errors="ignore")

        findings = []
        if ".env" not in content and ".env*" not in content:
            findings.append(
                Finding(
                    rule_id="security.gitignore_missing_env",
                    severity=ReviewSeverity.BLOCK,
                    message=".gitignore does not exclude .env files — secrets may be committed",
                    fix_hint="Add '.env*' and '!.env.example' and '!.env.prod.example' to .gitignore",
                    auto_fixable=True,
                    fix_complexity=FixComplexity.TRIVIAL,
                )
            )
        return findings

    def _scan_files(self, repo_path: Path):
        """Yield files to scan, skipping binary/vendor/cache dirs."""
        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(repo_path))
            if any(skip in rel for skip in self.SKIP_PATTERNS):
                continue
            if path.suffix in self.SCAN_EXTENSIONS:
                yield path


plugin = SecurityPlugin()
