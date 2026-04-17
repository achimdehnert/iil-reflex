"""Tests for REFLEX WebProvider, HttpxWebProvider, and SDS adapters."""

from __future__ import annotations

import json

from reflex.providers import MockWebProvider, WebProvider
from reflex.types import SDSData, WebPage

# ── WebPage tests ─────────────────────────────────────────────────────────


class TestWebPage:
    def test_should_detect_pdf_content_type(self):
        page = WebPage(url="test.pdf", title="", text="", content_type="application/pdf")
        assert page.is_pdf is True

    def test_should_not_detect_html_as_pdf(self):
        page = WebPage(url="test.html", title="", text="", content_type="text/html")
        assert page.is_pdf is False

    def test_should_truncate_text_snippet(self):
        long_text = "A" * 600
        page = WebPage(url="x", title="", text=long_text)
        assert page.text_snippet.endswith("...")
        assert len(page.text_snippet) == 503  # 500 + "..."

    def test_should_not_truncate_short_text(self):
        page = WebPage(url="x", title="", text="short")
        assert page.text_snippet == "short"


# ── SDSData tests ─────────────────────────────────────────────────────────


class TestSDSData:
    def test_should_create_sds_with_all_fields(self):
        sds = SDSData(
            substance_name="Ethanol",
            cas_number="64-17-5",
            h_statements=["H225", "H319"],
            flash_point="13°C",
            signal_word="Danger",
        )
        assert sds.substance_name == "Ethanol"
        assert sds.cas_number == "64-17-5"
        assert "H225" in sds.h_statements

    def test_should_have_default_empty_fields(self):
        sds = SDSData(substance_name="Test")
        assert sds.cas_number == ""
        assert sds.h_statements == []
        assert sds.source_url == ""


# ── MockWebProvider tests ─────────────────────────────────────────────────


class TestMockWebProvider:
    def test_should_implement_protocol(self):
        provider = MockWebProvider()
        assert isinstance(provider, WebProvider)

    def test_should_fetch_known_page(self):
        page = WebPage(url="https://example.com", title="Example", text="Hello")
        provider = MockWebProvider(pages=[page])
        result = provider.fetch("https://example.com")
        assert result.title == "Example"
        assert result.text == "Hello"

    def test_should_return_404_for_unknown(self):
        provider = MockWebProvider()
        result = provider.fetch("https://unknown.com")
        assert result.status_code == 404

    def test_should_search_by_title(self):
        provider = MockWebProvider(pages=[
            WebPage(url="https://a.com", title="Ethanol Safety", text=""),
            WebPage(url="https://b.com", title="Water Safety", text=""),
        ])
        results = provider.search_web("Ethanol")
        assert len(results) == 1
        assert results[0].title == "Ethanol Safety"

    def test_should_search_by_text(self):
        provider = MockWebProvider(pages=[
            WebPage(url="https://a.com", title="SDS", text="Contains ethanol data"),
        ])
        results = provider.search_web("ethanol")
        assert len(results) == 1

    def test_should_limit_results(self):
        provider = MockWebProvider(pages=[
            WebPage(url=f"https://{i}.com", title="Match", text="match")
            for i in range(10)
        ])
        results = provider.search_web("match", limit=3)
        assert len(results) == 3

    def test_should_add_page(self):
        provider = MockWebProvider()
        provider.add("https://new.com", "New Page", "New text")
        result = provider.fetch("https://new.com")
        assert result.title == "New Page"


# ── HttpxWebProvider (unit tests — no network) ───────────────────────────


class TestHtmlToText:
    def test_should_extract_text_from_html(self):
        from reflex.web import _html_to_text
        html = "<html><body><h1>Title</h1><p>Paragraph</p></body></html>"
        text = _html_to_text(html)
        assert "Title" in text
        assert "Paragraph" in text

    def test_should_strip_nav_and_script(self):
        from reflex.web import _html_to_text
        html = "<html><nav>Nav</nav><script>js()</script><p>Content</p></html>"
        text = _html_to_text(html)
        assert "Nav" not in text
        assert "js()" not in text
        assert "Content" in text

    def test_should_extract_title(self):
        from reflex.web import _extract_title
        html = "<html><head><title>My Page</title></head></html>"
        assert _extract_title(html) == "My Page"


# ── PubChem adapter (unit tests — mock JSON) ─────────────────────────────


class TestPubChemAdapter:
    def test_should_parse_ghs_view(self):
        from reflex.web import PubChemAdapter

        mock_ghs = json.dumps({
            "Record": {"Section": [{
                "Section": [{
                    "Section": [{
                        "TOCHeading": "GHS Classification",
                        "Information": [
                            {
                                "Name": "GHS Hazard Statements",
                                "Value": {
                                    "StringWithMarkup": [
                                        {"String": "H225: Highly flammable"},
                                        {"String": "H319: Eye irritation"},
                                    ]
                                },
                            },
                            {
                                "Name": "Signal",
                                "Value": {
                                    "StringWithMarkup": [
                                        {"String": "Danger"},
                                    ]
                                },
                            },
                        ],
                    }]
                }]
            }]}
        })
        result = PubChemAdapter._parse_ghs_view(mock_ghs)
        assert "H225" in result["h_statements"]
        assert "H319" in result["h_statements"]
        assert result["signal_word"] == "Danger"

    def test_should_handle_empty_ghs(self):
        from reflex.web import PubChemAdapter
        result = PubChemAdapter._parse_ghs_view("{}")
        assert result["h_statements"] == []
        assert result["signal_word"] == ""

    def test_should_handle_invalid_json(self):
        from reflex.web import PubChemAdapter
        result = PubChemAdapter._parse_ghs_view("not json")
        assert result["h_statements"] == []


# ── GESTIS adapter (unit tests — mock JSON) ──────────────────────────────


class TestGESTISAdapter:
    def test_should_parse_gestis_response(self):
        from reflex.web import GESTISAdapter

        mock_json = json.dumps({
            "chapters": [{
                "chapterNr": "1",
                "sections": [
                    {"fieldId": "stoffname", "text": "Ethanol"},
                    {"fieldId": "casnr", "text": "64-17-5"},
                    {"fieldId": "hstatements", "text": "H225 H319"},
                    {"fieldId": "signalwort", "text": "Gefahr"},
                ]
            }]
        })
        result = GESTISAdapter._parse_gestis(mock_json, "https://gestis.test")
        assert result is not None
        assert result.substance_name == "Ethanol"
        assert result.cas_number == "64-17-5"
        assert "H225" in result.h_statements
        assert result.signal_word == "Gefahr"

    def test_should_return_none_for_empty_name(self):
        from reflex.web import GESTISAdapter
        mock_json = json.dumps({"chapters": [{"chapterNr": "1", "sections": []}]})
        result = GESTISAdapter._parse_gestis(mock_json, "url")
        assert result is None
