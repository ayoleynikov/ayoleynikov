"""SSRF protection tests — block private, metadata, localhost."""

from __future__ import annotations

import pytest

from pulse.connectors.rss.config import RSSConnectorConfig
from pulse.security.ssrf import SSRFError, validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/feed",
        "http://localhost/feed",
        "http://[::1]/feed",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ],
)
def test_blocks_dangerous_urls(url: str) -> None:
    with pytest.raises(SSRFError):
        validate_public_url(url, resolve_dns=False)


def test_allows_public_https() -> None:
    assert validate_public_url("https://example.com/feed.xml", resolve_dns=False).startswith(
        "https://"
    )


def test_rss_config_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="Blocked|localhost|loopback|127"):
        RSSConnectorConfig(feed_url="http://127.0.0.1/feed.xml", ssrf_resolve_dns=False)
