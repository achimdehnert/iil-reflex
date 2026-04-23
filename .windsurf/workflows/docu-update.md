---
description: iil-reflex Dokumentation aktualisieren — kurzfristig Review-fähiges Deliverable erzeugen
---

# /docu-update

> Erzeugt ein konsistentes, sofort review-fähiges Dokumentations-Paket für `iil-reflex`.
> Trigger: vor externem Review, nach Release, nach neuen Modulen/Commands.

---

## Phase 0: Ist-Stand erfassen (autonom, ~30s)

```bash
# Version
grep '__version__' reflex/__init__.py

# Module-Liste
ls reflex/*.py | grep -v __

# CLI-Commands (aus __main__.py)
grep 'sub.add_parser\|"command"' reflex/__main__.py | grep add_parser

# Test-Count
python -m pytest tests/ --collect-only -q 2>/dev/null | tail -3

# Git-Status
git log --oneline -5
```

→ Notiere: `VERSION`, `MODULE_LIST`, `CLI_COMMANDS`, `TEST_COUNT`

---

## Phase 1: README.md prüfen + ggf. updaten

Prüfe in `README.md`:

1. **Version** in der Headline (`> Version **X.Y.Z**`)
2. **CLI-Commands** — decken sich mit `__main__.py`? (keine Phantom-Commands)
3. **Architecture-Block** — alle `.py` Module aus `reflex/` gelistet?
4. **Dependencies-Tabelle** — deckt sich mit `pyproject.toml [web]`, `[llm]`, `[metrics]`?
5. **Documentation-Tabelle** — alle Outline-Links aktuell?

Falls Abweichung → README.md editieren, dann:

```bash
git add README.md
git commit -m "docs(README): update to v<VERSION> — <was geändert>"
git push
```

---

## Phase 2: Outline-Dokumente prüfen

### 2.1 CLI-Referenz aktualisieren

Falls neue CLI-Commands hinzugekommen:
→ `mcp3_update_document(document_id: "7c6af512-a077-4168-8fdd-1c2fe80fc416", content: ...)`

### 2.2 Funktionsbeschreibung aktualisieren

Falls neue Module oder Version-Bump:
→ `mcp3_update_document(document_id: "e11b463f-4bfc-4557-8019-1694e05b08f9", content: ...)`

### 2.3 Review Package updaten

Falls Module-Tabelle, Metriken oder Open-Items geändert:
→ `mcp3_update_document(document_id: "<review-package-id>", content: ...)`

Dokument-IDs (Stand 2026-04-23):

| Dokument | ID |
|---|---|
| CLI-Referenz | `7c6af512-a077-4168-8fdd-1c2fe80fc416` |
| Funktionsbeschreibung | `e11b463f-4bfc-4557-8019-1694e05b08f9` |
| Review Package | `558fb0f6-bbb5-4ccd-b0a8-38e601639f60` |
| Möglichkeiten & Arbeitsweise | `2ac94ec6-61ea-4297-adbe-709030958c0a` |
| HTTP Resilience Konzept | `ea1914f2-7dd6-4e76-bda5-ff25b373bd85` |

---

## Phase 3: CHANGELOG.md prüfen

```bash
head -20 CHANGELOG.md
```

Falls `[X.Y.Z] — Unreleased` noch vorhanden → Datum eintragen + Features ergänzen:

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v<VERSION>"
git push
```

---

## Phase 4: Deliverable bereitstellen

Das **Review Package** in Outline ist der primary shareable Link:

```
https://knowledge.iil.pet/doc/iil-reflex-review-package-deliverable-aBPs3xOqHG
```

Das **README.md** auf GitHub ist der primary deliverable für Code-Reviewer:

```
https://github.com/achimdehnert/iil-reflex#readme
```

---

## Checkliste (muss alles grün sein)

| # | Check |
|---|-------|
| 1 | README.md Version = `__version__` |
| 2 | README.md CLI-Commands = `__main__.py` (keine Phantom-Commands) |
| 3 | README.md Architecture = alle `.py` Module in `reflex/` |
| 4 | README.md Dependencies = `pyproject.toml` |
| 5 | CLI-Referenz Outline = `__main__.py` |
| 6 | Funktionsbeschreibung Outline = aktuell |
| 7 | Review Package Outline = aktuell |
| 8 | CHANGELOG.md = kein `Unreleased` wenn Version released |
| 9 | `git status` clean, gepusht |

---

## Trigger-Matrix (wann aufrufen?)

| Ereignis | /docu-update nötig? |
|---|---|
| Externer Review angefragt | ✅ sofort |
| `__version__` erhöht | ✅ |
| Neue `.py` Datei in `reflex/` | ✅ |
| Neues CLI-Command in `__main__.py` | ✅ |
| Neuer `[extra]` in `pyproject.toml` | ✅ |
| Bug-Fix ohne API-Änderung | ❌ |
| session-ende ohne Code-Änderung | ❌ |
