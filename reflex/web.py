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
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from reflex.types import SDSData, WebPage

logger = logging.getLogger(__name__)


__all__ = ["HttpxWebProvider", "PubChemAdapter", "GESTISAdapter", "PDFDocumentProvider"]

_DEFAULT_UA = "Mozilla/5.0 (REFLEX/0.2; SDS Research Bot; +https://github.com/achimdehnert/iil-reflex)"
_DEFAULT_TIMEOUT = 30

_RETRYABLE_STATUS: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def _retry_get(client, url: str, **kwargs):
    """GET with exponential-backoff retry on transient HTTP/network errors.

    Activates automatically when *tenacity* is installed (``pip install iil-reflex[web]``).
    Falls back to a single undecorated attempt when *tenacity* is absent.
    """
    try:
        import httpx
        from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter
    except ImportError:
        return client.get(url, **kwargs)

    def _is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRYABLE_STATUS
        return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=8.0),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _do():
        return client.get(url, **kwargs)

    return _do()


def _make_rate_limiter(rate_per_second: float):
    """Return a no-arg callable that enforces *rate_per_second* requests/s.

    Uses *pyrate-limiter* when available; falls back to ``time.sleep``.
    Handles fractional rates (e.g. 2.5/s) without int-truncation by
    expressing the limit as 1 request per N milliseconds.
    """
    try:
        from pyrate_limiter import Duration, Limiter, Rate

        interval_ms = max(1, int(1000.0 / rate_per_second))
        _rate = Rate(1, Duration.MILLISECOND * interval_ms)
        _lim = Limiter(_rate, raise_when_fail=False, max_delay=Duration.SECOND * 30)

        def _acquire() -> None:
            _lim.try_acquire("default")

        return _acquire
    except ImportError:
        _delay = 1.0 / rate_per_second

        def _sleep() -> None:
            time.sleep(_delay)

        return _sleep


def _require_httpx():
    """Lazy import httpx — only needed at runtime, not at import time."""
    try:
        import httpx

        return httpx
    except ImportError as exc:
        raise ImportError(
            "httpx is required for web scraping. Install with: pip install iil-reflex[web]  or  pip install httpx"
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
        cache: bool = True,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_pages = max_pages
        self.allowed_domains = allowed_domains or []
        self.cache = cache
        self._client: Any = None
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def _get_client(self):
        """Thread-safe lazy-init of the shared ``httpx.Client`` (connection pool reuse).

        Uses *hishel* ``CacheTransport`` when available and ``cache=True``
        to avoid redundant network requests for identical URLs (PubChem, GESTIS).
        """
        if self._client is None:
            with self._lock:
                if self._client is None:
                    httpx = _require_httpx()
                    transport = None
                    if self.cache:
                        try:
                            import hishel
                            transport = hishel.CacheTransport(
                                transport=httpx.HTTPTransport(),
                                storage=hishel.FileStorage(),
                            )
                        except ImportError:
                            pass
                    self._client = httpx.Client(
                        headers={"User-Agent": self.user_agent},
                        timeout=self.timeout,
                        follow_redirects=True,
                        transport=transport,
                    )
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client and release connection pool."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # -- WebProvider protocol -----------------------------------------------

    def fetch(self, url: str) -> WebPage:
        """Fetch a URL and return structured WebPage."""
        if self.allowed_domains:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc
            if not any(d in domain for d in self.allowed_domains):
                logger.warning("Domain %s not in allowed list, skipping", domain)
                return WebPage(url=url, title="Blocked", text="", status_code=403)

        try:
            resp = _retry_get(self._get_client(), url)
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
        try:
            resp = _retry_get(
                self._get_client(),
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
                    results.append(
                        WebPage(
                            url=href,
                            title=title,
                            text=snippet,
                            scraped_at=datetime.now(UTC).isoformat(),
                        )
                    )

            return results[:limit]

        except Exception as e:
            logger.error("Web search failed: %s", e)
            return []

    @staticmethod
    def _extract_pdf_from_bytes(content: bytes) -> str:
        """Extract text from PDF bytes via iil-ingest (pdfplumber + Tesseract OCR fallback)."""
        try:
            from ingest.extractors.pdf import PDFExtractor

            result = PDFExtractor(ocr_fallback=True).extract(content)
            for err in result.extraction_errors:
                logger.warning("PDF extraction: %s", err)
            return result.text
        except ImportError:
            logger.warning("iil-ingest not installed — cannot extract PDF text")
            return "[PDF content — install iil-ingest[pdf] to extract text]"
        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            return f"[PDF extraction error: {e}]"


# ── SDS-Specific Adapters ─────────────────────────────────────────────────


def _collect_info(node: dict, out: list) -> None:
    """Recursively collect all Information items from PUG View JSON."""
    if "Information" in node:
        out.extend(node["Information"])
    for sec in node.get("Section", []):
        _collect_info(sec, out)


class PubChemAdapter:
    """Fetch substance data from PubChem REST API.

    https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
    """

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def __init__(self, web: HttpxWebProvider | None = None):
        self.web = web or HttpxWebProvider()
        self._limiter = _make_rate_limiter(5.0)

    def lookup_by_name(self, name: str) -> SDSData | None:
        """Look up substance by name -> structured SDS data.

        Uses CID -> properties + synonyms (for CAS) + GHS data.
        """
        cid = self._get_cid(name)
        if not cid:
            logger.warning("PubChem: no CID for %s", name)
            return None
        return self._build_sds(cid, name)

    def lookup_by_cas(self, cas: str) -> SDSData | None:
        """Look up substance by CAS number."""
        cid = self._get_cid(cas)
        if not cid:
            return None
        sds = self._build_sds(cid, cas)
        if sds and not sds.cas_number:
            return SDSData(
                substance_name=sds.substance_name,
                cas_number=cas,
                h_statements=sds.h_statements,
                p_statements=sds.p_statements,
                flash_point=sds.flash_point,
                signal_word=sds.signal_word,
                ghs_pictograms=sds.ghs_pictograms,
                source_url=sds.source_url,
                raw_text=sds.raw_text,
            )
        return sds

    def _build_sds(self, cid: int, query: str) -> SDSData | None:
        """Build SDSData from multiple PubChem endpoints."""
        props = self._get_properties(cid)
        self._limiter()
        iupac = props.get("IUPACName", query)
        cas = self._get_cas_from_synonyms(cid)
        self._limiter()
        ghs = self._get_ghs_classification(cid)
        url = f"{self.BASE_URL}/compound/cid/{cid}/JSON"

        return SDSData(
            substance_name=iupac,
            cas_number=cas,
            h_statements=ghs.get("h_statements", []),
            p_statements=ghs.get("p_statements", []),
            signal_word=ghs.get("signal_word", ""),
            ghs_pictograms=ghs.get("pictograms", []),
            source_url=url,
            raw_text=json.dumps(props, indent=2)[:2000],
        )

    def _get_properties(self, cid: int) -> dict[str, Any]:
        """Get computed properties for a CID."""
        url = f"{self.BASE_URL}/compound/cid/{cid}/property/IUPACName,MolecularFormula,MolecularWeight/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return {}
        try:
            data = json.loads(page.text)
            return data.get("PropertyTable", {}).get("Properties", [{}])[0]
        except (json.JSONDecodeError, IndexError):
            return {}

    def _get_cas_from_synonyms(self, cid: int) -> str:
        """Extract CAS number from PubChem synonyms."""
        url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return ""
        try:
            data = json.loads(page.text)
            synonyms = data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
            cas_pat = re.compile(r"^\d{2,7}-\d{2}-\d$")
            for s in synonyms:
                if cas_pat.match(s):
                    return s
            return ""
        except (json.JSONDecodeError, IndexError):
            return ""

    def _get_ghs_classification(self, cid: int) -> dict[str, Any]:
        """Get GHS hazard data from PubChem PUG View."""
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return {}
        return self._parse_ghs_view(page.text)

    @staticmethod
    def _parse_ghs_view(text: str) -> dict[str, Any]:
        """Parse PUG View GHS section.

        PubChem nests: Record > Section > Section > Section(GHS Classification)
        with Information items keyed by 'Name' field.
        """
        result: dict[str, Any] = {
            "h_statements": [],
            "p_statements": [],
            "signal_word": "",
            "pictograms": [],
        }
        try:
            data = json.loads(text)
            # Collect all Information items from any nesting depth
            all_info: list[dict] = []
            _collect_info(data.get("Record", {}), all_info)

            for info in all_info:
                name = info.get("Name", "")
                strings = [item.get("String", "") for item in info.get("Value", {}).get("StringWithMarkup", [])]
                full = " ".join(strings)

                if "Hazard Statements" in name:
                    result["h_statements"].extend(re.findall(r"H\d{3}", full))
                elif "Precautionary" in name:
                    result["p_statements"].extend(re.findall(r"P\d{3}", full))
                elif name == "Signal":
                    for s in strings:
                        s = s.strip()
                        if s and s != " ":
                            result["signal_word"] = s
                elif "Pictogram" in name:
                    result["pictograms"].extend(re.findall(r"GHS\d{2}", full))

            result["h_statements"] = sorted(set(result["h_statements"]))
            result["p_statements"] = sorted(set(result["p_statements"]))
            result["pictograms"] = sorted(set(result["pictograms"]))
        except (json.JSONDecodeError, KeyError):
            pass
        return result

    def _get_cid(self, name: str) -> int | None:
        """Get PubChem CID for a substance name."""
        url = f"{self.BASE_URL}/compound/name/{quote(name, safe='')}/cids/JSON"
        page = self.web.fetch(url)
        if page.status_code != 200:
            return None
        try:
            data = json.loads(page.text)
            cids = data.get("IdentifierList", {}).get("CID", [])
            return cids[0] if cids else None
        except (json.JSONDecodeError, IndexError):
            return None


class GESTISAdapter:
    """Fetch substance data from GESTIS (IFA) substance database.

    https://gestis.dguv.de/ — German occupational safety substance DB.
    """

    BASE_URL = "https://gestis-api.dguv.de/api"
    SEARCH_URL = "https://gestis-api.dguv.de/api/search"

    def __init__(self, web: HttpxWebProvider | None = None):
        self.web = web or HttpxWebProvider()
        self._limiter = _make_rate_limiter(5.0)

    def search(self, query: str) -> list[dict[str, str]]:
        """Search GESTIS for substances matching query."""
        url = f"{self.SEARCH_URL}?exact=false&query={quote(query, safe='')}"
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
        """Extract text from a local PDF file via iil-ingest (pdfplumber + OCR fallback)."""
        try:
            from ingest.extractors.pdf import PDFExtractor
        except ImportError as exc:
            raise ImportError(
                "iil-ingest[pdf] is required for PDF reading. Install with: "
                "pip install iil-reflex[web]"
            ) from exc

        with open(path, "rb") as fh:
            data = fh.read()
        result = PDFExtractor(ocr_fallback=True).extract(data)
        for err in result.extraction_errors:
            logger.warning("PDF read_file: %s", err)
        return result.text

    def read_url(self, url: str) -> str:
        """Download and extract text from a PDF URL."""
        page = self.web.fetch(url)
        return page.text

    def search(self, query: str, limit: int = 5) -> list:
        """DocumentProvider protocol — not applicable for single-file PDFs."""
        return []
