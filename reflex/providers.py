"""
REFLEX Provider Protocols — Dependency Inversion for Knowledge Sources.

Providers are pluggable adapters for external knowledge sources.
The core DomainAgent depends only on these Protocols, not on concrete
implementations (Outline, Paperless, MCP, etc.).

Concrete implementations live outside this package:
    - OutlineProvider  → in MCP or hub code
    - PaperlessProvider → in MCP or hub code
    - MemoryProvider   → in orchestrator or hub code
    - MockProvider     → in tests (included here)

Usage:
    from reflex.providers import KnowledgeProvider, MockKnowledgeProvider

    agent = DomainAgent(
        config=config,
        knowledge=OutlineProvider(api_url="..."),
        documents=PaperlessProvider(api_url="..."),
    )
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reflex.types import DocumentEntry, KnowledgeEntry


# ── Protocols ──────────────────────────────────────────────────────────────


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Protocol for knowledge base search (Outline, Memory, Wiki, etc.)."""

    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        """Search knowledge base and return ranked entries."""
        ...


@runtime_checkable
class DocumentProvider(Protocol):
    """Protocol for document search (Paperless, S3, file system, etc.)."""

    def search(self, query: str, limit: int = 5) -> list[DocumentEntry]:
        """Search documents and return ranked entries."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM completion calls."""

    def complete(
        self,
        messages: list[dict[str, str]],
        action_code: str = "",
    ) -> str:
        """Send messages to LLM and return response text."""
        ...


# ── Mock Providers (for testing) ───────────────────────────────────────────


class MockKnowledgeProvider:
    """In-memory knowledge provider for testing."""

    def __init__(self, entries: list[KnowledgeEntry] | None = None):
        self._entries = entries or []

    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        return [
            e for e in self._entries
            if query.lower() in e.title.lower() or query.lower() in e.content.lower()
        ][:limit]

    def add(self, title: str, content: str, source: str = "mock") -> None:
        self._entries.append(
            KnowledgeEntry(title=title, content=content, source=source)
        )


class MockDocumentProvider:
    """In-memory document provider for testing."""

    def __init__(self, entries: list[DocumentEntry] | None = None):
        self._entries = entries or []

    def search(self, query: str, limit: int = 5) -> list[DocumentEntry]:
        return [
            e for e in self._entries
            if query.lower() in e.title.lower() or query.lower() in e.snippet.lower()
        ][:limit]

    def add(self, title: str, snippet: str, source: str = "mock") -> None:
        self._entries.append(
            DocumentEntry(title=title, snippet=snippet, source=source)
        )


class MockLLMProvider:
    """Deterministic LLM provider for testing.

    Returns pre-configured responses keyed by action_code.
    """

    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}
        self._default = '{"result": "mock response"}'
        self.call_log: list[dict] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        action_code: str = "",
    ) -> str:
        self.call_log.append({"action_code": action_code, "messages": messages})
        return self._responses.get(action_code, self._default)

    def set_response(self, action_code: str, response: str) -> None:
        self._responses[action_code] = response
