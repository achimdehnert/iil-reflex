---
trigger: always_on
---

# Project Facts: iil-reflex

## Package

- PyPI name: `iil-reflex`
- Version: see `pyproject.toml`
- Build: `hatchling`
- Python: ≥3.12
- Venv: `.venv/` (activate: `source .venv/bin/activate`)
- Test runner: `.venv/bin/python -m pytest`

## Extras

| Extra | Deps |
|-------|------|
| `web` | httpx, tenacity, hishel, pyrate-limiter, beautifulsoup4, iil-ingest[pdf,ocr] |
| `llm` | litellm |
| `playwright` | playwright |
| `metrics` | psycopg[binary] |
| `dev` | pytest, ruff, respx, pytest-mock |
| `all` | all of the above |

## Key Modules

- `reflex/web.py` — HttpxWebProvider, PubChemAdapter, GESTISAdapter, PDFDocumentProvider
- `reflex/types.py` — WebPage, SDSData
- `reflex/providers.py` — MockWebProvider, MockLLMProvider, etc.
- `reflex/config.py` — ReflexConfig (reflex.yaml)

## Tests

```bash
make test              # unit tests only
make test-integration  # requires tesseract + poppler (see below)
make lint
```

## System Dependencies (Hetzner Server)

- **Tesseract**: v5.3.4 — `tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng`
- **Poppler**: `poppler-utils` (pdftoppm)
- **Install ohne sudo**: `ssh root@localhost "apt-get install -y <package>"`
- devuser hat KEIN sudo-Passwort → System-Pakete immer via `ssh root@localhost`

## Git / GitHub

- Repo: `https://github.com/achimdehnert/iil-reflex`
- Branch: `main`
- Push: `git push` (SSH-Key bereits konfiguriert)

## Abhängige Repos

- `iil-ingest` — PDF/OCR-Extraktion (iil-ingest[pdf,ocr])
- `iil-promptfw` — LLM-Prompt-Framework (Pflichtdep)
- `risk-hub` — nutzt iil-reflex[web] für SDS-Recherche

## Secrets / Config

- Keine Laufzeit-Secrets in iil-reflex (reine Library)
- API-Keys (LiteLLM, etc.) kommen vom Consumer (z.B. risk-hub via .env)
- `.env.example` zeigt was Consumer-Repos brauchen
