"""Stub queue tasks return explicit not_implemented (no fake success)."""

from __future__ import annotations

import pytest

from pulse.workers.retry import PermanentTaskError
from pulse.workers.stub_tasks import match_brands, normalize_batch
from pulse.workers.tasks import refuse_stream_on_celery


def test_normalize_stub_is_explicit() -> None:
    result = normalize_batch.run(batch_id="b1")
    assert result["status"] == "not_implemented"
    assert result["phase"] == "phase-5"
    assert result["stage"] == "ingestion.normalize"


def test_match_brands_stub_is_explicit() -> None:
    result = match_brands.run(project_id="p1")
    assert result["status"] == "not_implemented"
    assert "matching.brand" in result["stage"]


def test_refuse_stream_on_celery() -> None:
    with pytest.raises(PermanentTaskError) as exc:
        refuse_stream_on_celery.run()
    assert "pulse-jetstream" in str(exc.value)
