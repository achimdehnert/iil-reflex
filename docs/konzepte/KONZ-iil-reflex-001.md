---
concept_id: KONZ-iil-reflex-001
title: REFLEX beweist sich selbst — von asserted zu proven
pipeline_status: idea
tier: T2
owner: Achim Dehnert
spec_refs: []          # iil-reflex ist ein Standalone-PyPI-Paket, kein Spec/Klickdummy-Repo (ADR-211 n/a)
adr_threshold: kein ADR   # lokale Test-Additions + 1 CI-Smoke-Step; keine org-weite Boundary
review_by: 2026-07-15
kill_criteria: "Wenn der fetch()-Redirect-Hop-SSRF-Test nicht in 1 PR deterministisch grün ist (3× CI ohne Flake), wird die Integrations-Schiene verworfen und nur der CLI-Smoke behalten."
superseded_by_spec: null
evidence_manifest:
  - {claim_id: C1, source_path: reflex/review/plugins/security_plugin.py, commit_or_pr: "line 202 docker-compose.prod.yml", opened_in_session: true}
  - {claim_id: C2, source_path: reflex/review/plugins/repo_plugin.py, commit_or_pr: "line 30 docker-compose.prod.yml block", opened_in_session: true}
  - {claim_id: C3, source_path: "(ls reflex.yaml docker-compose*.yml docs/adr)", commit_or_pr: "all not found", opened_in_session: true}
  - {claim_id: C4, source_path: tests/test_web_ssrf.py, commit_or_pr: "#6, lines 19-54 (unit calls _assert_public_url)", opened_in_session: true}
  - {claim_id: C5, source_path: tests/test_dashboard_security.py, commit_or_pr: "#6, lines 16-61 (drives do_GET/do_POST in-process)", opened_in_session: true}
  - {claim_id: C6, source_path: "(grep redirect|302 in tests/test_web*.py)", commit_or_pr: "no match — fetch() redirect-hop untested", opened_in_session: true}
created: 2026-06-14
---

# KONZ-iil-reflex-001 — REFLEX beweist sich selbst

**Tier: T2** — berührt den Security-Perimeter (Auto-Eskalation ≥ T2) und schlägt einen CI-Smoke-Boundary vor; aber 1 Repo, kein SSoT-Reversal, kein Cross-Repo, keine neue Dependency → nicht T3.

## Kernthese
Der Wert liegt **nicht** in „mehr Tests", sondern darin, zwei Behauptungen vom Status *asserted* in *proven* zu heben: (a) `fetch()` blockt SSRF **auf jedem Redirect-Hop** (von PR #6 behauptet, ungetestet), und (b) das Tool läuft überhaupt end-to-end (nie verifiziert). Die ursprüngliche Idee #1 (`reflex review` auf das eigene Repo) ist **geerdet widerlegt** und wird ersetzt, nicht umgesetzt.

## Steelman (vor der Kritik)
Die Original-Idee war richtig in der *Diagnose*: ein „Evidenz-Qualitäts"-Tool wurde nach PyPI veröffentlicht, ohne je end-to-end zu laufen, und seine Security-Fixes wurden per Diff/CI-grün gemergt. „Das Tool soll sein erster Kunde sein" ist ein starkes Credibility-Argument, und Angriffstests sind echter als Assertions. Die Schwäche liegt nur in der *Umsetzung* (`reflex review` als Vehikel), nicht im Ziel.

## Decision-Ledger
| id | Aussage | Typ | Evidenz / Falsifikation | Status |
|----|---------|-----|--------------------------|--------|
| A1 | `reflex review`-Plugins prüfen Django-Hub-Artefakte (`docker-compose.prod.yml`, `Dockerfile`, `ports.yaml`, `.env`, 0.0.0.0-Bind) | Annahme | E2 C1 `security_plugin.py:202`, C2 `repo_plugin.py:30` | ✅ verifiziert |
| A2 | iil-reflex (Library) hat KEINEN dieser Inputs | Annahme | E2 C3 `ls` → reflex.yaml/compose/docs/adr alle not found | ✅ verifiziert |
| **D1** | **#1 (dogfood `reflex review` auf iil-reflex) = NO-GO** — Plugins sind hub-shaped; auf der Library findet das Tool ~nichts/Fehlalarme → beweist nichts; Inputs künstlich zu erzeugen wäre Theater | Entscheidung | folgt aus A1+A2 | ✅ gesetzt (killed) |
| A3 | `test_web_ssrf.py` testet `_assert_public_url` ISOLIERT (Angriffs-URL → `BlockedURLError`) — guter Klassifikator-Test | Annahme | E2 C4 `test_web_ssrf.py:31-44` | ✅ verifiziert |
| A4 | KEIN Test treibt `fetch()` durch einen echten Redirect auf eine blockierte IP → PR-#6-Claim „guard on **every redirect hop**" ist **ungetestet** | Risiko/Lücke | E2 C6 (grep redirect/302 = leer); fetch()-Tests nur gegen example.com | ✅ verifiziert |
| A5 | `test_dashboard_security.py` treibt echte `do_GET`/`do_POST`-Handler mit Angriffs-Inputs (foreign Host, GET-control) → näher am Angriff, aber in-process (`__new__` umgeht `__init__`, kein echter Socket) | Annahme | E2 C5 `test_dashboard_security.py:16-61` | ✅ verifiziert |
| **D2** | **#3 = GO, aber verengt** — nicht „Security-Tests fehlen" (existieren), sondern die EINE ungetestete Integrationslücke schließen: `fetch()`-Redirect-Hop-SSRF | Entscheidung | folgt aus A3-A5 | ✅ gesetzt |
| **D3** | **Ersatz für das gekillte #1:** CLI-Smoke (`reflex <cmd>` gegen Fixture, echter Exit+Output, kein Mock) schließt den Retro-Fund „nie end-to-end gelaufen" — das ist die *echte* Selbstanwendung, nicht `reflex review` | Entscheidung | E1 (Retro `…-release.md`/`…-pr7-16.md`) | ✅ gesetzt |
| R1 | Real-Socket-/Live-Server-Test ist langsamer/flakier in CI als Unit-Tests | Risiko | H | offen → Kill-Gate |

## MVC (konkret — Dateien/Felder/Gate)
1. **`tests/test_web_ssrf_integration.py`** *(schließt A4, die Kern-Lücke)*: respx-Route `http://evil.test/` → `302 Location: http://169.254.169.254/latest/meta-data/`; `HttpxWebProvider().fetch("http://evil.test/")`; assert (a) Ergebnis ist blockiertes/Error-`WebPage`, (b) die respx-Route auf `169.254.169.254` wurde **nie aufgerufen** (`assert not route.called`) → beweist, dass der Guard auf dem Hop greift, bevor die Metadata-IP kontaktiert wird.
2. **`tests/test_cli_smoke.py`** *(D3, ersetzt #1)*: für jeden Subcommand ein echter Lauf ohne Mock gegen eine Fixture, die offline+deterministisch ist — Minimum: `reflex --help` (Exit 0), `reflex classify <test> <error>` (Exit 0, Output enthält `failure_type`), `reflex check <fixture-uc.md>` (Exit-Code + Score im Output). Kein Provider-Mock — echte Code-Pfade.
3. *(optional, R1-gated)* **`tests/test_dashboard_boot.py`**: echten `HTTPServer` auf `127.0.0.1:0` im Daemon-Thread booten, reale HTTP-Anfrage mit foreign `Host`-Header + `GET /api/stop/...` senden, 403/Ablehnung asserten, server schließen → beweist S1/S3 am Socket statt am `__new__`-Handler.
4. **CI:** #1 und #2 laufen im bestehenden `test`-Job mit (kein neuer Job). Coverage-Gate bleibt; die Integrationstests zählen nicht künstlich zur Line-Coverage hoch — sie sind als `integration`-Marker führbar, falls sie CI-Zeit kosten.

## Befunde (inkl. Advocatus Diabolus)
| # | Befund / Diabolus-Frage | Antwort / Mitigation |
|---|--------------------------|----------------------|
| AD1 | „Der respx-Redirect-Test mockt httpx → du testest wieder den Mock." | respx simuliert nur die *Antwort*; die Redirect-/Guard-Logik in `fetch`/`_retry_get` ist **echter Code**. Geprüft wird die Guard-**Invocation** auf dem Hop (Code), plus `assert not called` auf der Metadata-Route — das ist Verhalten, kein Mock-Echo. |
| AD2 | „CLI-Smoke gegen `--help` beweist nur, dass argparse lädt." | Korrekt — deshalb gegen **Fixture mit echtem Output** (`classify`/`check` sind offline+deterministisch), nicht nur `--help`. |
| AD3 | „#1 zu killen lässt die Diabolus-Kritik ‚Tool nie auf sich angewandt' offen." | Ehrlich ja für `reflex review`. Aber das ist hub-spezifisch; es auf eine Library zu zwingen wäre genau das Theater, das die Erdung aufdeckte. Die *echte* Selbstanwendung ist CLI-Smoke (D3). |
| AD4 | „Wird hier eine zweite Wahrheitsquelle erzeugt (SSoT)?" | Nein — keine neuen Status/Felder/Scoreboards; nur Tests + 1 Fixture. Die SSoT (der Code) bleibt einzige Wahrheit; die Tests *beobachten* sie. |

## Alternativen
| Alt | Inhalt | Warum verworfen / deferred |
|-----|--------|----------------------------|
| ALT1 | Nichts tun — Unit-Tests reichen | Die „every redirect hop"-Behauptung bleibt unbewiesen; ein Refactor könnte die Guard-Invocation entfernen, ohne dass ein Test failt — genau die Bug-Klasse, die diese Session 8× fand. Abgelehnt. |
| ALT2 | Library-passende `reflex review`-Plugins bauen (py-package-Plugin: `py.typed`, Coverage-Floor, kein 0%-Modul) → macht #1 viabel | Größerer Scope (T2→T3, neue Plugins als Boundary) + Wette auf Nutzung. **Deferred** als OOTB-Backlog; erst die billige CLI-Smoke. |

## Entscheidung + Kill-Gate
**Empfehlung: GO für D2 (MVC #1) + D3 (MVC #2); D1 = killed; MVC #3 nur falls R1 es trägt.**
- **Kill-Gate (messbar):** Ist `test_web_ssrf_integration.py` nicht in **1 PR deterministisch grün** (3× CI-Re-Run ohne Flake), oder kostet der optionale Boot-Test (#3) **> 2 s** CI-Zeit → Integrations-Schiene verwerfen, nur CLI-Smoke (#2) behalten.
- **Exception-Budget:** bis `review_by: 2026-07-15`. Ohne Pflege → Auto-Sunset (I3).
- **Enforcement-Ehrlichkeit:** Dieses Doc *schreibt* `review_by`/`kill_criteria`, *erzwingt* sie nicht — sie wirken erst, wenn ein Lifecycle-Gate sie liest. Bis dahin Review-Gate, kein Exit-Code.
