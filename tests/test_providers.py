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
        entries = [KnowledgeEntry(term="ATEX", definition="Explosive Atmospheres")]
        provider = MockKnowledgeProvider(entries=entries)
        results = provider.search("ATEX")
        assert len(results) == 1
        assert results[0].term == "ATEX"


class TestMockDocumentProvider:
    """Test MockDocumentProvider implements DocumentProvider protocol."""

    def test_should_implement_protocol(self):
        provider = MockDocumentProvider()
        assert isinstance(provider, DocumentProvider)

    def test_should_return_empty_list(self):
        provider = MockDocumentProvider()
        results = provider.list_documents()
        assert results == []

    def test_should_return_configured_documents(self):
        docs = [DocumentEntry(path="docs/uc/UC-001.md", title="UC-001")]
        provider = MockDocumentProvider(documents=docs)
        results = provider.list_documents()
        assert len(results) == 1
        assert results[0].path == "docs/uc/UC-001.md"

    def test_should_read_document_content(self):
        provider = MockDocumentProvider(content="# UC-001\n\nTest content")
        content = provider.read("docs/uc/UC-001.md")
        assert "UC-001" in content


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
        provider = MockWebProvider(page=custom)
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
        provider = MockLLMProvider(response="ATEX is about explosive atmospheres.")
        response = provider.complete("What is ATEX?")
        assert "explosive atmospheres" in response
