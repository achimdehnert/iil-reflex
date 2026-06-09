"""Tests for reflex.providers — Protocol compliance and mock implementations."""

from __future__ import annotations

from reflex.providers import (
    DocumentProvider,
    KnowledgeProvider,
    LLMProvider,
    MockDocumentProvider,
    MockKnowledgeProvider,
    MockLLMProvider,
    MockWebProvider,
    WebProvider,
)
from reflex.types import DocumentEntry, KnowledgeEntry, WebPage


class TestMockKnowledgeProvider:
    """Test MockKnowledgeProvider implements KnowledgeProvider protocol."""

    def test_should_implement_protocol(self):
        provider = MockKnowledgeProvider()
        assert isinstance(provider, KnowledgeProvider)

    def test_should_return_empty_search(self):
        provider = MockKnowledgeProvider()
        results = provider.search("ATEX")
        assert results == []

    def test_should_return_configured_results(self):
        entries = [KnowledgeEntry(title="ATEX", content="Explosive Atmospheres")]
        provider = MockKnowledgeProvider(entries=entries)
        results = provider.search("ATEX")
        assert len(results) == 1
        assert results[0].title == "ATEX"


class TestMockDocumentProvider:
    """Test MockDocumentProvider implements DocumentProvider protocol."""

    def test_should_implement_protocol(self):
        provider = MockDocumentProvider()
        assert isinstance(provider, DocumentProvider)

    def test_should_return_empty_list(self):
        provider = MockDocumentProvider()
        results = provider.search("anything")
        assert results == []

    def test_should_return_configured_documents(self):
        docs = [DocumentEntry(title="UC-001", snippet="docs/uc/UC-001.md")]
        provider = MockDocumentProvider(entries=docs)
        results = provider.search("UC-001")
        assert len(results) == 1
        assert results[0].title == "UC-001"


class TestMockWebProvider:
    """Test MockWebProvider implements WebProvider protocol."""

    def test_should_implement_protocol(self):
        provider = MockWebProvider()
        assert isinstance(provider, WebProvider)

    def test_should_return_page(self):
        provider = MockWebProvider()
        page = provider.fetch("https://example.com")
        assert isinstance(page, WebPage)
        assert page.url == "https://example.com"

    def test_should_return_configured_page(self):
        custom = WebPage(url="https://test.com", title="Custom", text="Hello")
        provider = MockWebProvider(pages=[custom])
        page = provider.fetch("https://test.com")
        assert page.title == "Custom"
        assert page.text == "Hello"


class TestMockLLMProvider:
    """Test MockLLMProvider implements LLMProvider protocol."""

    def test_should_implement_protocol(self):
        provider = MockLLMProvider()
        assert isinstance(provider, LLMProvider)

    def test_should_return_default_response(self):
        provider = MockLLMProvider()
        response = provider.complete("What is ATEX?")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_should_return_configured_response(self):
        provider = MockLLMProvider(responses={"explain_atex": "ATEX is about explosive atmospheres."})
        response = provider.complete([{"role": "user", "content": "What is ATEX?"}], action_code="explain_atex")
        assert "explosive atmospheres" in response
