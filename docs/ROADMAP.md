# REFLEX — Development Roadmap

> Grounded suggestions from a 2026-06 codebase analysis. Each item states the
> **evidence** (verified fact), the **why**, and a **first step**. Ordered by
> value-to-effort, not by size.

Status legend: 🔵 ready (no decision needed) · 🟢 needs a call · 🟡 larger strand.

---

## R1 · Close the test-coverage debt on risky modules ✅ done

**Evidence (start):** `infra.py` 22%, `__main__.py` 41%, `permission_runner.py` 47%,
`web.py` 60%, `platform_runner.py` 71%. Total package coverage 77%.

**Done — all five modules lifted, total coverage 77% → 88%:**

| Module | Before | After |
|--------|--------|-------|
| `permission_runner.py` | 47% | 100% |
| `infra.py` | 22% | 95% |
| `cycle.py` | 50% | 98% |
| `platform_runner.py` | 71% | 99% |
| `__main__.py` (CLI) | 41% | 99% |
| `web.py` | 60% | 91% |

The work surfaced and fixed **five real bugs** (see CHANGELOG): `run_all`
`None.close()` crash, the `logger.error(file=…)` `TypeError` in `reflex infra`,
two `print_report`/`print_result` trailing-`logger.info()` crashes, and the
`run_full_cycle` `final_status` never-`FAILED` logic bug. The CI floor (R4) was
raised from 75% to **85%** to lock these gains in.

---

## R2 · Make `[web]` installable from PyPI without GitHub ✅ done (option b)

**Evidence:** `pyproject.toml` declared
`iil-ingest[pdf,ocr] @ git+https://github.com/achimdehnert/iil-ingest.git` inside `[web]`,
so `pip install iil-reflex[web]` from PyPI depended on GitHub being reachable — a known
supply-chain/reproducibility smell for a published package.

**Done (option b — split the extra):** PDF/OCR moved to a new `[web-pdf]` extra; the Git
reference now lives only there. `pip install iil-reflex[web]` (httpx + SDS scraping)
installs cleanly from PyPI with no VCS dependency; PDF extraction is opt-in via
`[web-pdf]`. Verified against the built wheel metadata (`[web]` has no Git requirement).

**Still open (option a, optional):** publishing `iil-ingest` to PyPI would let `[web-pdf]`
pin a version instead of a Git ref — a separate decision for the iil-ingest repo.

---

## R3 · Ship a `py.typed` marker ✅ done

**Evidence:** the package is fully type-annotated but `reflex/py.typed` did **not**
exist, so downstream `mypy`/`pyright` users got **none** of these types.

**Done:** added `reflex/py.typed`; hatchling already includes package data, verified
the marker ships in the built wheel (`reflex/py.typed` present in
`iil_reflex-0.5.0-py3-none-any.whl`).

---

## R4 · Harden CI: coverage floor + packaging smoke ✅ done

**Evidence:** `.github/workflows/ci.yml` ran lint + `pytest` on 3.12 only — no
coverage threshold, no wheel build, no install check.

**Done:** the test job now runs `pytest --cov=reflex --cov-fail-under=75` (current
total is 77%, measured both with `[dev,web]` and in a `[dev]`-only CI-equivalent env, so
the floor has headroom). A new `package` job builds the sdist+wheel, installs the wheel
into a clean venv, and smoke-tests it (`import reflex`, `reflex --help`, and asserts
`reflex/py.typed` ships in the wheel).

**Next:** raise the floor as R1's remaining modules (`__main__`, `web`,
`platform_runner`) gain coverage.

---

## R5 · Unify the report-printing helpers ✅ done

**Evidence:** `platform_runner.print_report` wrote via `print()`, but
`cycle.print_result`, `permission_runner.print_report`, and `infra.cmd_infra` wrote
their reports via `logger.info()`.

**Why it was a real bug, not just style:** the package configures **no logging handler**
(verified — no `basicConfig`/`setLevel` anywhere), so the root logger sits at `WARNING`
and every `logger.info` report line was silently dropped. `reflex infra <repo>` — a
CLI-wired command whose whole job is to print an info card — produced **no output**.

**Done:** user-facing report output now uses `print()` (stdout) and error messages use
`print(file=sys.stderr)`, matching the rest of the CLI; diagnostic `logger` calls are
untouched. Added `capsys` regression tests asserting each report reaches stdout (they
fail against the old `logger.info` code).

---

## Already addressed in this analysis cycle ✅

- Removed 893 LOC of dead `dashboard.py` (shadowed by the `dashboard/` package).
- `MetricsWriter` brought from 0% to fully tested.
- `cycle.py` 50% → 98%; fixed two real bugs (`final_status` never `FAILED`,
  `print_result` `TypeError`).
- Python version metadata unified to 3.12.
- Dropped a redundant `except (ImportError, Exception)` in `llm_providers`.

---

*All roadmap items (R1–R5) are addressed. The only remaining optional follow-up is
publishing `iil-ingest` to PyPI so `[web-pdf]` can pin a version instead of a Git ref.*
