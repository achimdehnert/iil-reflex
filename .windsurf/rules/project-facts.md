---
trigger: always_on
---

# Project Facts: iil-reflex

> Web/PDF provider library — HttpxWebProvider, PubChemAdapter, GESTISAdapter

## Meta

- **Type**: `library`
- **GitHub**: `https://github.com/achimdehnert/iil-reflex`
- **Branch**: `main` — push: `git push` (SSH-Key konfiguriert)
- **PyPI**: `iil-reflex`
- **Venv**: `.venv/` — test: `.venv/bin/python -m pytest`

## System (Hetzner Server)

- devuser hat **KEIN sudo-Passwort** → System-Pakete immer via SSH als root:
  ```bash
  ssh root@localhost "apt-get install -y <package>"
  ```

## Secrets / Config

- **Secrets**: `.env` (nicht in Git) — Template: `.env.example`
