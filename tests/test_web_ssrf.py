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
