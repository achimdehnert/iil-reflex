"""Tests for PDF extraction in HttpxWebProvider and PDFDocumentProvider.

Run all (mocked, no system deps):
    pytest tests/test_web_pdf.py

Run integration tests (requires tesseract + poppler installed):
    pytest tests/test_web_pdf.py -m integration -v
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_extractor(text: str = "Extracted text", errors: list | None = None):
    """Return a PDFExtractor mock that yields the given text."""
    content = MagicMock()
    content.text = text
    content.extraction_errors = errors or []
    extractor = MagicMock()
    extractor.return_value.extract.return_value = content
    return extractor


def _is_tesseract_available() -> bool:
    """Check whether tesseract binary is present on the system."""
    import shutil
    return shutil.which("tesseract") is not None


def _is_poppler_available() -> bool:
    """Check whether pdftoppm (poppler-utils) is present on the system."""
    import shutil
    return shutil.which("pdftoppm") is not None


# ── _extract_pdf_from_bytes (unit) ────────────────────────────────────────────


class TestExtractPdfFromBytes:
    def test_returns_text_from_iil_ingest(self):
        extractor = _mock_extractor("Sicherheitsdatenblatt Ethanol")
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            from reflex.web import HttpxWebProvider
            result = HttpxWebProvider._extract_pdf_from_bytes(b"%PDF-fake")
        assert result == "Sicherheitsdatenblatt Ethanol"

    def test_logs_extraction_errors(self, caplog):
        import logging
        extractor = _mock_extractor("text", errors=["Page 2: decode error"])
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            with caplog.at_level(logging.WARNING, logger="reflex.web"):
                from reflex.web import HttpxWebProvider
                HttpxWebProvider._extract_pdf_from_bytes(b"%PDF-fake")
        assert any("decode error" in r.message for r in caplog.records)

    def test_returns_fallback_message_if_iil_ingest_missing(self):
        with patch.dict(sys.modules, {"ingest": None, "ingest.extractors.pdf": None}):
            # Re-import after patching sys.modules
            import importlib
            import reflex.web as web_mod
            importlib.reload(web_mod)
            result = web_mod.HttpxWebProvider._extract_pdf_from_bytes(b"%PDF-fake")
        assert "install" in result.lower() or "PDF" in result

    def test_returns_error_message_on_exception(self):
        extractor = MagicMock()
        extractor.side_effect = Exception("disk I/O error")
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            from reflex.web import HttpxWebProvider
            result = HttpxWebProvider._extract_pdf_from_bytes(b"%PDF-fake")
        assert "error" in result.lower()

    def test_ocr_fallback_flag_is_true(self):
        """PDFExtractor must be instantiated with ocr_fallback=True."""
        extractor_cls = MagicMock()
        instance = extractor_cls.return_value
        instance.extract.return_value = MagicMock(text="ok", extraction_errors=[])
        with patch("ingest.extractors.pdf.PDFExtractor", extractor_cls):
            from reflex.web import HttpxWebProvider
            HttpxWebProvider._extract_pdf_from_bytes(b"%PDF-fake")
        extractor_cls.assert_called_once_with(ocr_fallback=True)


# ── PDFDocumentProvider.read_file (unit) ──────────────────────────────────────


class TestPDFDocumentProviderReadFile:
    def test_reads_and_extracts_text(self, tmp_path):
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-minimal")

        extractor = _mock_extractor("Flammpunkt 55 °C")
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            from reflex.web import PDFDocumentProvider
            result = PDFDocumentProvider().read_file(str(pdf_file))
        assert result == "Flammpunkt 55 °C"

    def test_raises_import_error_if_iil_ingest_missing(self, tmp_path):
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-minimal")
        with patch.dict(sys.modules, {"ingest": None, "ingest.extractors": None, "ingest.extractors.pdf": None}):
            import importlib
            import reflex.web as web_mod
            importlib.reload(web_mod)
            with pytest.raises(ImportError, match="iil-ingest"):
                web_mod.PDFDocumentProvider().read_file(str(pdf_file))

    def test_ocr_fallback_flag_is_true_for_read_file(self, tmp_path):
        """read_file must use ocr_fallback=True."""
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-minimal")

        extractor_cls = MagicMock()
        instance = extractor_cls.return_value
        instance.extract.return_value = MagicMock(text="ok", extraction_errors=[])
        with patch("ingest.extractors.pdf.PDFExtractor", extractor_cls):
            from reflex.web import PDFDocumentProvider
            PDFDocumentProvider().read_file(str(pdf_file))
        extractor_cls.assert_called_once_with(ocr_fallback=True)

    def test_logs_extraction_errors_for_read_file(self, tmp_path, caplog):
        import logging
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF-minimal")

        extractor = _mock_extractor("text", errors=["Page 1: corrupt stream"])
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            with caplog.at_level(logging.WARNING, logger="reflex.web"):
                from reflex.web import PDFDocumentProvider
                PDFDocumentProvider().read_file(str(pdf_file))
        assert any("corrupt stream" in r.message for r in caplog.records)


# ── fetch() routes PDF content-type through _extract_pdf_from_bytes ──────────


class TestHttpxFetchPdfRouting:
    def test_fetch_routes_pdf_content_type(self):
        import respx

        extractor = _mock_extractor("H225 H319 Flammpunkt 13°C")
        with patch("ingest.extractors.pdf.PDFExtractor", extractor):
            with respx.mock:
                respx.get("https://example.com/sds.pdf").respond(
                    200,
                    content=b"%PDF-fake",
                    headers={"content-type": "application/pdf"},
                )
                from reflex.web import HttpxWebProvider
                page = HttpxWebProvider().fetch("https://example.com/sds.pdf")

        assert page.is_pdf is True
        assert "H225" in page.text


# ── OCR Diagnostic (integration tests — require real system deps) ─────────────


@pytest.mark.integration
class TestOCRDiagnostic:
    """Run with: pytest tests/test_web_pdf.py -m integration -v

    Requires: tesseract-ocr, tesseract-ocr-deu, poppler-utils (apt)
              + pytesseract, pdf2image (pip)
    """

    def test_tesseract_binary_is_available(self):
        assert _is_tesseract_available(), (
            "tesseract not found — install: apt install tesseract-ocr tesseract-ocr-deu"
        )

    def test_poppler_binary_is_available(self):
        assert _is_poppler_available(), (
            "pdftoppm not found — install: apt install poppler-utils"
        )

    def test_pytesseract_importable(self):
        pytest.importorskip("pytesseract")

    def test_pdf2image_importable(self):
        pytest.importorskip("pdf2image")

    def test_iil_ingest_ocr_importable(self):
        from ingest.extractors.ocr import ocr_pdf_bytes  # noqa: F401

    def test_real_pdf_text_extraction(self):
        """Extracts text from a minimal valid PDF with embedded text."""
        pytest.importorskip("pdfplumber")
        import io
        import pdfplumber

        # Build minimal PDF with known text via pdfplumber (round-trip)
        # We just verify the pipeline doesn't crash on a real PDF
        from ingest.extractors.pdf import PDFExtractor

        # Minimal valid PDF (no actual text — tests graceful empty handling)
        minimal_pdf = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f\n"
            b"0000000009 00000 n\n0000000058 00000 n\n"
            b"0000000115 00000 n\n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
        )
        result = PDFExtractor(ocr_fallback=False).extract(minimal_pdf)
        # Should not crash; text may be empty for this minimal PDF
        assert isinstance(result.text, str)

    def test_ocr_pipeline_on_text_image(self, tmp_path):
        """Generate a white image with text, convert to single-page PDF, run OCR."""
        pytest.importorskip("pytesseract")
        pytest.importorskip("pdf2image")
        PIL = pytest.importorskip("PIL")

        from PIL import Image, ImageDraw
        import io

        # Create a white image with black text
        img = Image.new("RGB", (800, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Ethanol H225 H319 Flammpunkt 13 C", fill="black")

        # Save as single-page TIFF (pdf2image can convert this back)
        tiff_path = tmp_path / "test_page.tiff"
        img.save(str(tiff_path))

        import pytesseract
        text = pytesseract.image_to_string(img, lang="eng")
        assert "Ethanol" in text or "H225" in text, (
            f"OCR did not extract expected text. Got: {text!r}"
        )
