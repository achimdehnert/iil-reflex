"""Tests for the SSRF guard in reflex.web (_assert_public_url).

Note: reflex.web is reloaded by test_web_pdf.py (importlib.reload to exercise the
PDF import fallback), which swaps class identities. We therefore reference
_assert_public_url / BlockedURLError through the live module at call time rather
than binding them at import — otherwise pytest.raises sees a stale class.
"""

from __future__ import annotations

import pytest

import reflex.web as web_mod


class TestAssertPublicUrl:
    """The SSRF guard must block non-public targets and bad schemes."""

    def test_should_allow_public_https_url(self):
        # example.com resolves to a public address — must pass.
        web_mod._assert_public_url("https://example.com/page")

    def test_should_block_loopback_ip(self):
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://127.0.0.1:9000/api/stop/risk-hub")

    def test_should_block_localhost_name(self):
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://localhost:8080/")

    def test_should_block_cloud_metadata_endpoint(self):
        # 169.254.169.254 — the classic AWS/GCP metadata SSRF target (link-local).
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://169.254.169.254/latest/meta-data/")

    def test_should_block_private_rfc1918_ip(self):
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://10.0.0.5/internal")
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://192.168.1.1/admin")

    def test_should_block_ipv6_loopback(self):
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("http://[::1]/")

    def test_should_block_non_http_scheme(self):
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("file:///etc/passwd")
        with pytest.raises(web_mod.BlockedURLError):
            web_mod._assert_public_url("ftp://example.com/x")

    def test_should_allow_private_when_opted_in(self):
        # allow_private=True is the explicit opt-out (e.g. internal wiki scrape).
        web_mod._assert_public_url("http://127.0.0.1:9000/", allow_private=True)

    def test_should_not_block_when_host_unresolvable(self):
        # A non-resolving host is left for the HTTP layer (keeps the guard
        # usable offline / under respx mocks); it must not raise here.
        web_mod._assert_public_url("https://this-host-does-not-resolve.invalid/")


class TestSearchWebSSRF:
    """search_web must route through the SSRF guard (regression for AD-3).

    Before the fix, search_web called _retry_get directly on a client with
    follow_redirects=True, so a DuckDuckGo redirect to a private/link-local IP
    would be followed unguarded.
    """

    def test_should_block_ddg_redirect_to_metadata_ip(self, monkeypatch):
        import respx

        # Keep the guard's hostname DNS check offline + deterministic: the DDG
        # host resolves to a public address, so the FIRST hop is allowed and the
        # redirect target (link-local metadata IP) is what gets blocked.
        monkeypatch.setattr(
            web_mod.socket,
            "getaddrinfo",
            lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
        )
        with respx.mock(assert_all_called=False):
            respx.get("https://html.duckduckgo.com/html/").respond(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
            meta = respx.get("http://169.254.169.254/latest/meta-data/").respond(200, text="SECRET")
            provider = web_mod.HttpxWebProvider()
            results = provider.search_web("anything")
            provider.close()
        assert results == []  # BlockedURLError is caught by search_web → empty result
        assert not meta.called  # guard blocked the hop before the metadata IP was contacted


class TestFetchSSRF:
    """fetch() must block an open-redirect hop to a private IP (proves the
    per-hop guard claim from PR #6 / KONZ-001 D2')."""

    def test_should_block_redirect_hop_to_metadata_ip(self, monkeypatch):
        import respx

        monkeypatch.setattr(
            web_mod.socket,
            "getaddrinfo",
            lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
        )
        with respx.mock(assert_all_called=False):
            respx.get("https://evil.test/").respond(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
            meta = respx.get("http://169.254.169.254/latest/meta-data/").respond(200, text="SECRET")
            provider = web_mod.HttpxWebProvider()
            page = provider.fetch("https://evil.test/")
            provider.close()
        # fetch() catches the BlockedURLError and returns an Error WebPage.
        assert page.status_code == 0
        assert page.title == "Error"
        assert not meta.called
