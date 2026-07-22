"""SSRF hardening tests for chains/extract_trip_chain.py's URL-fetch path,
focused on the DNS-rebinding (TOCTOU) fix: `_assert_public_host` resolves +
validates once and returns a pinned IP, and `_fetch_url_text` connects to that
literal IP (via `_pinned_get`) rather than letting httpx re-resolve the
hostname between validation and connect.
"""
import socket

import httpx
import pytest

from chains import extract_trip_chain as etc
from chains.extract_trip_chain import _assert_public_host, _fetch_url_text, _UnsafeUrlError


def _addrinfo(*ips):
    """Mimic socket.getaddrinfo's return shape for the given IP string(s)."""
    out = []
    for ip in ips:
        if ":" in ip:
            out.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0)))
        else:
            out.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)))
    return out


def _resp(status, *, headers=None, text="", url="https://example.com/"):
    """A real httpx.Response with a request attached (raise_for_status needs one)."""
    return httpx.Response(status, headers=headers or {}, text=text, request=httpx.Request("GET", url))


class TestAssertPublicHost:
    def test_returns_host_and_pinned_ip(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo("93.184.216.34"))
        assert _assert_public_host("https://example.com/path") == ("example.com", "93.184.216.34")

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",      # loopback
            "10.0.0.5",       # private
            "192.168.1.1",    # private
            "172.16.0.1",     # private
            "169.254.169.254",  # link-local (cloud metadata)
            "0.0.0.0",        # unspecified
            "224.0.0.1",      # multicast
            "::1",            # ipv6 loopback
            "fc00::1",        # ipv6 unique-local (private)
        ],
    )
    def test_rejects_non_public(self, monkeypatch, ip):
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo(ip))
        with pytest.raises(_UnsafeUrlError):
            _assert_public_host("https://evil.test/")

    def test_rejects_when_any_resolved_ip_is_private(self, monkeypatch):
        # One public + one private → reject the whole URL (an attacker can't
        # smuggle a private target in via a multi-record response).
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo("93.184.216.34", "10.0.0.1"))
        with pytest.raises(_UnsafeUrlError):
            _assert_public_host("https://example.com/")

    def test_pins_first_public_ip(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo("93.184.216.34", "93.184.216.35"))
        _, ip = _assert_public_host("https://example.com/")
        assert ip == "93.184.216.34"

    def test_rejects_bad_scheme(self):
        with pytest.raises(_UnsafeUrlError):
            _assert_public_host("file:///etc/passwd")

    def test_rejects_missing_host(self):
        with pytest.raises(_UnsafeUrlError):
            _assert_public_host("https:///nohost")

    def test_rejects_unresolvable(self, monkeypatch):
        def _boom(h, p):
            raise socket.gaierror("name resolution failed")

        monkeypatch.setattr(socket, "getaddrinfo", _boom)
        with pytest.raises(_UnsafeUrlError):
            _assert_public_host("https://nonexistent.invalid/")


class TestPinnedGet:
    async def test_connects_to_ip_but_keeps_hostname_for_tls_and_host_header(self):
        captured = {}

        class _FakeClient:
            async def get(self, url, headers=None, extensions=None):
                captured.update(url=url, headers=headers, extensions=extensions)
                return _resp(200, text="ok")

        await etc._pinned_get(_FakeClient(), "https://example.com:8443/p?q=1", "example.com", "93.184.216.34")
        assert captured["url"].host == "93.184.216.34"          # TCP target is the pinned IP
        assert str(captured["url"]).startswith("https://93.184.216.34:8443/p")
        assert captured["headers"]["Host"] == "example.com:8443"  # non-default port preserved
        assert captured["extensions"]["sni_hostname"] == "example.com"  # TLS verifies real host

    async def test_default_port_host_header_has_no_port(self):
        captured = {}

        class _FakeClient:
            async def get(self, url, headers=None, extensions=None):
                captured.update(headers=headers)
                return _resp(200, text="ok")

        await etc._pinned_get(_FakeClient(), "https://example.com/p", "example.com", "1.2.3.4")
        assert captured["headers"]["Host"] == "example.com"

    async def test_ipv6_pinned_url_is_bracketed(self):
        captured = {}

        class _FakeClient:
            async def get(self, url, headers=None, extensions=None):
                captured.update(url=url)
                return _resp(200, text="ok")

        await etc._pinned_get(_FakeClient(), "https://example.com/p", "example.com", "2606:4700::1")
        assert "[2606:4700::1]" in str(captured["url"])


class TestFetchUrlTextPinning:
    async def test_fetch_connects_to_the_validated_ip(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo("93.184.216.34"))
        calls = []

        async def _fake_pinned_get(client, url, host, ip):
            calls.append((url, host, ip))
            return _resp(200, headers={"content-type": "text/html"}, text="<p>Hello <b>world</b></p>")

        monkeypatch.setattr(etc, "_pinned_get", _fake_pinned_get)
        out = await _fetch_url_text("https://evil.example/path")
        # The connection used the IP validated by _assert_public_host, not a re-resolution.
        assert calls == [("https://evil.example/path", "evil.example", "93.184.216.34")]
        assert "Hello world" in out

    async def test_fetch_blocks_private_ip_and_never_connects(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: _addrinfo("169.254.169.254"))
        connected = []

        async def _fake_pinned_get(client, url, host, ip):
            connected.append(ip)
            return _resp(200, text="SHOULD NOT HAPPEN")

        monkeypatch.setattr(etc, "_pinned_get", _fake_pinned_get)
        out = await _fetch_url_text("http://metadata.evil/latest/meta-data/")
        assert out == ""
        assert connected == []  # validation failed → no socket connect attempted

    async def test_redirect_to_private_host_is_revalidated_and_blocked(self, monkeypatch):
        def _gai(host, port):
            if host == "safe.example":
                return _addrinfo("93.184.216.34")
            if host == "internal.evil":
                return _addrinfo("10.0.0.5")  # a rebind / redirect to a private target
            raise socket.gaierror("nope")

        monkeypatch.setattr(socket, "getaddrinfo", _gai)

        async def _fake_pinned_get(client, url, host, ip):
            if host == "safe.example":
                return _resp(301, headers={"location": "http://internal.evil/secret"})
            return _resp(200, headers={"content-type": "text/html"}, text="LEAKED INTERNAL DATA")

        monkeypatch.setattr(etc, "_pinned_get", _fake_pinned_get)
        out = await _fetch_url_text("https://safe.example/")
        assert out == ""  # the redirect hop was re-validated and rejected before connecting

    async def test_safe_redirect_chain_pins_each_hop_ip(self, monkeypatch):
        def _gai(host, port):
            return {"a.example": _addrinfo("93.184.216.34"), "b.example": _addrinfo("93.184.216.99")}[host]

        monkeypatch.setattr(socket, "getaddrinfo", _gai)
        seen = []

        async def _fake_pinned_get(client, url, host, ip):
            seen.append((host, ip))
            if host == "a.example":
                return _resp(302, headers={"location": "https://b.example/final"})
            return _resp(200, headers={"content-type": "text/html"}, text="final page")

        monkeypatch.setattr(etc, "_pinned_get", _fake_pinned_get)
        out = await _fetch_url_text("https://a.example/start")
        assert seen == [("a.example", "93.184.216.34"), ("b.example", "93.184.216.99")]
        assert "final page" in out
