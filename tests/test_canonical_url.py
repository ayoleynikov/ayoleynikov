"""Canonical URL helpers."""

from __future__ import annotations

import pytest

from pulse.connectors.types import ConnectorError, canonicalize_url


def test_canonicalize_strips_fragment_and_normalizes() -> None:
    url = "HTTPS://Example.COM/Blog/Post/?b=2&a=1#frag"
    assert canonicalize_url(url) == "https://example.com/Blog/Post?a=1&b=2"


def test_canonicalize_rejects_invalid() -> None:
    with pytest.raises(ConnectorError):
        canonicalize_url("not-a-url")
