# iil-reflex — Developer Makefile

.PHONY: install install-dev test test-v test-integration lint clean help

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

help:
	@echo "Available targets:"
	@echo "  install           — pip install -e .[dev,web]"
	@echo "  test              — pytest unit tests (no system deps needed)"
	@echo "  test-v            — pytest verbose"
	@echo "  test-integration  — pytest -m integration (requires tesseract + poppler)"
	@echo "  lint              — ruff check reflex/"
	@echo "  clean             — remove __pycache__ + .pytest_cache"

install:
	$(PIP) install -e ".[dev,web]"

test:
	$(PYTHON) -m pytest --tb=short -q

test-v:
	$(PYTHON) -m pytest --tb=short -v

test-integration:
	$(PYTHON) -m pytest -m integration -v --tb=short

lint:
	.venv/bin/ruff check reflex/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "Cleaned."
