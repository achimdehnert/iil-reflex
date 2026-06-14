# REFLEX — Development Roadmap

> Grounded suggestions from a 2026-06 codebase analysis. Each item states the
> **evidence** (verified fact), the **why**, and a **first step**. Ordered by
> value-to-effort, not by size.

Status legend: 🔵 ready (no decision needed) · 🟢 needs a call · 🟡 larger strand.

---

## R1 · Close the test-coverage debt on risky modules 🔵

**Evidence:** `infra.py` 22%, `__main__.py` 41%, `permission_runner.py` 47%,
`web.py` 60%, `platform_runner.py` 71% (vs `cycle.py` now 98%, `quality`/`config`/
`providers` at 100%).

**Why:** `infra.py` is the largest gap (231 uncovered lines) and it runs **SSH +
docker** commands — exactly the code where an untested edge case does real damage.
`permission_runner` is a security-adjacent surface (who-can-reach-what) and should be
the best-tested module, not a middling one.

**First step:** apply the `cycle.py` pattern (mock `subprocess`/`httpx`, assert the
`PhaseResult`/report shape) to `permission_runner.py` first, then `infra.py`. Target a
per-module floor of ~85%.

---

## R2 · Make `[web]` installable from PyPI without GitHub 🟢

**Evidence:** `pyproject.toml` declares
`iil-ingest[pdf,ocr] @ git+https://github.com/achimdehnert/iil-ingest.git` and needs
`allow-direct-references = true` to build.

**Why:** `pip install iil-reflex[web]` from PyPI then depends on GitHub being reachable
and the branch existing — it cannot be mirrored, pinned by hash in a lockfile cleanly,
or installed in an air-gapped CI. Direct VCS refs in a *published* package are a known
supply-chain/reproducibility smell.

**The call:** either (a) publish `iil-ingest` to PyPI and pin a version, or (b) split
PDF/OCR into a deeper-optional extra so the common `[web]` path (httpx + SDS scraping)
has no VCS dependency.

---

## R3 · Ship a `py.typed` marker 🔵

**Evidence:** the package is fully type-annotated (`from __future__ import annotations`
everywhere, Protocols, dataclasses) but `reflex/py.typed` does **not** exist.

**Why:** without the PEP-561 marker, downstream `mypy`/`pyright` users get **none** of
these types — the annotation effort is invisible to consumers. One empty file + a
`hatch` include unlocks it.

**First step:** `touch reflex/py.typed`; add it to the wheel via
`[tool.hatch.build.targets.wheel]` (or `force-include`).

---

## R4 · Harden CI: coverage floor + packaging smoke 🔵

**Evidence:** `.github/workflows/ci.yml` runs lint + `pytest` on 3.12 only — no
coverage threshold, no wheel build, no extra-install check.

**Why:** the coverage gains from this analysis (e.g. `cycle.py` 50→98%) aren't *locked* —
nothing fails a PR that regresses them. And no job verifies the package actually builds
and installs with its extras, so a broken `[web]`/`[metrics]` ships silently.

**First step:** add `--cov=reflex --cov-fail-under=80` to the test job, plus a small job
that runs `python -m build` and `pip install dist/*.whl` (core) to catch packaging
breakage early.

---

## R5 · Unify the two report-printing helpers 🟢

**Evidence:** `platform_runner.print_report` writes via `print()`; `cycle.print_result`
writes the equivalent report via `logger.info()`.

**Why:** for output the user explicitly requested (`reflex platform`, `reflex cycle`),
`print` is correct — `logging.info` is silent unless a handler is configured. The two
helpers should agree; today one of them can swallow its report depending on logging setup.

**The call:** standardise on `print` for user-facing reports (keep `logging` for
diagnostics), and add one regression test that asserts the report reaches stdout.

---

## Already addressed in this analysis cycle ✅

- Removed 893 LOC of dead `dashboard.py` (shadowed by the `dashboard/` package).
- `MetricsWriter` brought from 0% to fully tested.
- `cycle.py` 50% → 98%; fixed two real bugs (`final_status` never `FAILED`,
  `print_result` `TypeError`).
- Python version metadata unified to 3.12.
- Dropped a redundant `except (ImportError, Exception)` in `llm_providers`.

---

*Pick R1, R3, R4 for low-risk wins; R2 and R5 need a product/maintainer decision.*
