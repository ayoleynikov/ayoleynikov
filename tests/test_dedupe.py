"""Dedup L1–L3 tests + L4 scaffold."""

from __future__ import annotations

from datetime import UTC, datetime

from pulse.ingestion.dedupe import DedupIndex, DedupLevel, dedupe_batch, evaluate_dedup
from pulse.ingestion.normalize import normalize_mention


def _m(**kwargs):
    base = {
        "source": "rss",
        "external_id": "id-1",
        "collected_at": datetime(2024, 1, 1, tzinfo=UTC),
        "content": "alpha beta",
        "title": "T",
    }
    base.update(kwargs)
    return normalize_mention(base)


def test_l1_source_external_id() -> None:
    first = _m(external_id="same")
    index = DedupIndex()
    index.observe(first)
    second = _m(external_id="same", content="changed text")
    decision = evaluate_dedup(second, index)
    assert decision.is_duplicate
    assert decision.hits[0].level == DedupLevel.L1_SOURCE_EXTERNAL_ID


def test_l2_canonical_url() -> None:
    first = _m(external_id="a", source_url="https://example.com/post")
    index = DedupIndex()
    index.observe(first)
    second = _m(external_id="b", source_url="https://example.com/post#frag")
    decision = evaluate_dedup(second, index)
    assert any(h.level == DedupLevel.L2_CANONICAL_URL for h in decision.hits)


def test_l3_content_fingerprint() -> None:
    first = _m(external_id="a", title="Hello", content="World")
    index = DedupIndex()
    index.observe(first)
    second = _m(external_id="b", title=" hello ", content="WORLD", source_url=None)
    decision = evaluate_dedup(second, index)
    assert any(h.level == DedupLevel.L3_CONTENT_FINGERPRINT for h in decision.hits)
    assert decision.suggested_cluster_key is not None
    assert decision.suggested_cluster_key.startswith("cluster:fp:")


def test_batch_dedupe_keeps_unique() -> None:
    mentions = [
        _m(external_id="1", content="one"),
        _m(external_id="1", content="one again"),
        _m(external_id="2", content="two"),
    ]
    unique, dupes = dedupe_batch(mentions)
    assert len(unique) == 2
    assert len(dupes) == 1
