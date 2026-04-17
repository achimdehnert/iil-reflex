"""
REFLEX Web Provider — httpx-based web scraping for domain research.

Provides:
    - HttpxWebProvider: General web scraping (HTML → text)
    - PubChemAdapter: CAS number → substance data from PubChem REST API
    - GESTISAdapter: Substance lookup on GESTIS (IFA)
    - PDFDocumentProvider: Extract text from PDF files/URLs

Usage:
    from reflex.web import HttpxWebProvider

    web = HttpxWebProvider()
    page = web.fetch("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/Ethanol/JSON")
    pages = web.search_web("Ethanol SDS safety data sheet")

Config (reflex.yaml):
    web:
      user_agent: "REFLEX/0.2 (SDS Research Bot)"
      timeout: 30
      max_pages: 10
      allowed_domains: []  # empty = all
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from reflex.types import SDSData, WebPage

logger = logging.getLogger(__name__)

_DEFAULT_UA = "Mozilla/5.0 (REFLEX/0.2; SDS Research Bot; +https://github.com/achimdehnert/iil-reflex)"
_DEFAULT_TIMEOUT = 30


def _require_httpx():
    """Lazy import httpx — only needed at runtime, not at import time."""
    try:
        import httpx
        return httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required for web scraping. Install with: "
            "pip install iil-reflex[web]  or  pip install httpx"
        ) from exc


def _require_bs4():
    """Lazy import BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError as exc:
        raise ImportError(
            "beautifulsoup4 is required for HTML parsing. Install with: "
            "pip install iil-reflex[web]  or  pip install beautifulsoup4"
        ) from exc


def _html_to_text(html: str) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    BeautifulSoup = _require_bs4()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_title(html: str) -> str:
    """Extract <title> from HTML."""
    BeautifulSoup = _require_bs4()
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


class HttpxWebProvider:
    """Web scraping provider using httpx + BeautifulSoup.

    Implements the WebProvider protocol for DomainAgent integration.
    """

    def __init__(
        self,
        user_agent: str = _DEFAULT_UA,
        timeout: int = _DEFAULT_TIMEOUT,
        max_pages: int = 10,
        allowed_domains: list[str] | None = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_pages = max_pages
        self.allowed_domains = allowed_domains or []

    def fetch(self, url: str) -> WebPage:
        """Fetch a URL and return structured WebPage."""
        httpx = _require_httpx()

        if self.allowed_domains:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if not any(d in domain for d in self.allowed_domains):
                logger.warning("Domain %s not in allowed list, skipping", domain)
                return WebPage(url=url, title="Blocked", text="", status_code=403)

        try:
            with httpx.Client(
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)

            content_type = resp.headers.get("content-type", "")
            now = datetime.now(UTC).isoformat()

            if "application/pdf" in content_type:
                text = self._extract_pdf_from_bytes(resp.content)
                return WebPage(
                    url=url,
                    title=url.split("/")[-1],
                    text=text,
                    status_code=resp.status_code,
                    content_type=content_type,
                    scraped_at=now,
                )

            if "application/json" in content_type:
                return WebPage(
                    url=url,
                    title=url,
                    text=resp.text,
                    html="",
                    status_code=resp.status_code,
                    content_type=content_type,
                    scraped_at=now,
                )

            html = resp.text
            title = _extract_title(html)
            text = _html_to_text(html)

            return WebPage(
                url=url,
                title=title or url,
                text=text,
                html=html,
                status_code=resp.status_code,
                content_type=content_type,
                scraped_at=now,
            )

        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return WebPage(url=url, title="Error", text=str(e), status_code=0)

    def search_web(self, query: str, limit: int = 5) -> list[WebPage]:
        """Search via DuckDuckGo HTML (no API key needed) and scrape results."""
        httpx = _require_httpx()

        try:
            with httpx.Client(
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                )

            BeautifulSoup = _require_bs4()
            soup = BeautifulSoup(resp.text, "html.parser")

            results: list[WebPage] = []
            for link in soup.select("a.result__a")[:limit]:
                href = link.get("href", "")
                title = link.get_text(strip=True)
                snippet_el = link.find_parent("div", class_="result")
                snippet = ""
                if snippet_el:
                    snippet_tag = snippet_el.select_one(".result__snippet")
                    if snippet_tag:
                        snippet = snippet_tag.get_text(strip=True)

                if href and href.startswith("http"):
                    results.append(WebPage(
                        url=href,
                        title=title,
                        text=snippet,
                        scraped_at=datetime.now(UTC).isoformat(),
                    ))

            return results[:limit]

        except Exception as e:
            logger.error("Web search failed: %s", e)
            return []

    @staticmethod
    def _extract_pdf_from_bytes(content: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        try:
            import io

            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except ImportError:
            logger.warning("pdfplumber not installed — cannot extract PDF text")
            return "[PDF content — install pdfplumber to extract text]"
        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            return f"[PDF extraction error: {e}]"


# ── SDS-Specific Adapters ─────────────────────────────────────────────────


class PubChemAdapter:
    """Fetch substance data from PubChem REST API.

    https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
    """

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def __init__(self, web: HttpxWebProvider | None = None):
        self.web = web or HttpxWebProvider()

    def lookup_by_name(self, name: str) -> SDSData | None:
        """Look up substance by name → structured SDS data."""
        url = f"{self.BASE_URL}/compound/name/{name}/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            logger.warning("PubChem lookup failed for %s: HTTP %d", name, page.status_code)
            return None
        return self._parse_compound(page.text, name, url)

    def lookup_by_cas(self, cas: str) -> SDSData | None:
        """Look up substance by CAS number."""
        url = f"{self.BASE_URL}/compound/name/{cas}/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return None
        return self._parse_compound(page.text, cas, url)

    def get_ghs_info(self, name: str) -> dict[str, Any]:
        """Get GHS classification from PubChem."""
        cid = self._get_cid(name)
        if not cid:
            return {}
        url = (
            f"{self.BASE_URL}/compound/cid/{cid}/"
            "property/MolecularFormula,MolecularWeight,IUPACName/JSON"
        )
        page = self.web.fetch(url)
        if page.status_code != 200:
            return {}
        try:
            data = json.loads(page.text)
            props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
            return props
        except (json.JSONDecodeError, IndexError):
            return {}

    def _get_cid(self, name: str) -> int | None:
        """Get PubChem CID for a substance name."""
        url = f"{self.BASE_URL}/compound/name/{name}/cids/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return None
        try:
            data = json.loads(page.text)
            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except (json.JSONDecodeError, IndexError):
            return None

    @staticmethod
    def _parse_compound(text: str, name: str, url: str) -> SDSData | None:
        """Parse PubChem JSON response into SDSData."""
        try:
            data = json.loads(text)
            compound = data.get("PC_Compounds", [{}])[0]
            props = compound.get("props", [])

            cas = ""
            iupac = ""
            for p in props:
                urn = p.get("urn", {})
                label = urn.get("label", "")
                if label == "CAS":
                    cas = p.get("value", {}).get("sval", "")
                elif label == "IUPAC Name" and urn.get("name") == "Preferred":
                    iupac = p.get("value", {}).get("sval", "")

            return SDSData(
                substance_name=iupac or name,
                cas_number=cas,
                source_url=url,
                raw_text=text[:2000],
            )
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.error("PubChem parse failed: %s", e)
            return None


class GESTISAdapter:
    """Fetch substance data from GESTIS (IFA) substance database.

    https://gestis.dguv.de/ — German occupational safety substance DB.
    """

    BASE_URL = "https://gestis-api.dguv.de/api"
    SEARCH_URL = "https://gestis-api.dguv.de/api/search"

    def __init__(self, web: HttpxWebProvider | None = None):
        self.web = web or HttpxWebProvider()

    def search(self, query: str) -> list[dict[str, str]]:
        """Search GESTIS for substances matching query."""
        url = f"{self.SEARCH_URL}?exact=false&query={query}"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return []
        try:
            data = json.loads(page.text)
            return [
                {
                    "name": item.get("name", ""),
                    "cas": item.get("casNr", ""),
                    "zvg": item.get("zvgNr", ""),
                }
                for item in data
                if isinstance(item, dict)
            ][:10]
        except (json.JSONDecodeError, TypeError):
            return []

    def lookup(self, zvg_nr: str) -> SDSData | None:
        """Fetch full substance data by ZVG number."""
        url = f"{self.BASE_URL}/article/de/{zvg_nr}"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return None
        return self._parse_gestis(page.text, url)

    @staticmethod
    def _parse_gestis(text: str, url: str) -> SDSData | None:
        """Parse GESTIS JSON response into SDSData."""
        try:
            data = json.loads(text)
            name = ""
            cas = ""
            h_statements: list[str] = []
            p_statements: list[str] = []
            signal_word = ""
            ghs: list[str] = []

            for chapter in data.get("chapters", []):
                for section in chapter.get("sections", []):
                    field_id = section.get("fieldId", "")
                    text_val = section.get("text", "")

                    if field_id == "stoffname":
                        name = text_val
                    elif field_id == "casnr":
                        cas = text_val
                    elif field_id == "hstatements":
                        h_statements = re.findall(r"H\d{3}", text_val)
                    elif field_id == "pstatements":
                        p_statements = re.findall(r"P\d{3}", text_val)
                    elif field_id == "signalwort":
                        signal_word = text_val
                    elif field_id == "ghspiktogramme":
                        ghs = re.findall(r"GHS\d{2}", text_val)

            if not name:
                return None

            return SDSData(
                substance_name=name,
                cas_number=cas,
                h_statements=h_statements,
                p_statements=p_statements,
                signal_word=signal_word,
                ghs_pictograms=ghs,
                source_url=url,
                raw_text=text[:2000],
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("GESTIS parse failed: %s", e)
            return None


class PDFDocumentProvider:
    """Extract text from local PDF files or PDF URLs.

    Implements DocumentProvider protocol for PDF files.
    """

    def __init__(self, web: HttpxWebProvider | None = None):
        self.web = web or HttpxWebProvider()

    def read_file(self, path: str) -> str:
        """Extract text from a local PDF file."""
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except ImportError as exc:
            raise ImportError(
                "pdfplumber is required for PDF reading. Install with: "
                "pip install iil-reflex[web]  or  pip install pdfplumber"
            ) from exc

    def read_url(self, url: str) -> str:
        """Download and extract text from a PDF URL."""
        page = self.web.fetch(url)
        return page.text

    def search(self, query: str, limit: int = 5) -> list:
        """DocumentProvider protocol — not applicable for single-file PDFs."""
        return []
