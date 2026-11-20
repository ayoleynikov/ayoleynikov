"""Normalization tests — no invented metadata."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pulse.ingestion.normalize import NormalizationError, content_fingerprint, normalize_mention


def test_normalize_sets_identity_and_fingerprint() -> None:
    mention = normalize_mention(
        {
            "source": "rss",
            "external_id": "urn:1",
            "title": "Hello",
            "content": "World",
            "source_url": "https://Example.com/a/?b=1#x",
            "collected_at": datetime(2024, 1, 1, tzinfo=UTC),
            "metadata": {"feed_url": "https://example.com/feed", "unused": None},
        }
    )
    assert mention.mention_id
    assert mention.content_hash == content_fingerprint("Hello", "World")
    assert mention.canonical_url == "https://example.com/a?b=1"
    assert mention.metadata == {"feed_url": "https://example.com/feed"}
    assert "invented" not in mention.metadata


def test_normalize_rejects_naive_timestamps() -> None:
    with pytest.raises(NormalizationError):
        normalize_mention(
            {
                "source": "rss",
                "external_id": "x",
                "collected_at": datetime(2024, 1, 1),
            }
        )


def test_normalize_requires_source_external_id() -> None:
    with pytest.raises(NormalizationError):
        normalize_mention({"source": "", "external_id": "x"})
