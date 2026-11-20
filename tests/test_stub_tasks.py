"""Remaining stub queue tasks return explicit not_implemented."""

from __future__ import annotations

import pytest

from pulse.workers.retry import PermanentTaskError
from pulse.workers.stub_tasks import aggregate_analytics, run_ai_processing
from pulse.workers.tasks import refuse_stream_on_celery


def test_ai_stub_is_explicit() -> None:
    result = run_ai_processing.run(mention_id="m1")
    assert result["status"] == "not_implemented"
    assert result["stage"] == "processing.ai"


def test_analytics_stub_is_explicit() -> None:
    result = aggregate_analytics.run(window="1h")
    assert result["status"] == "not_implemented"


def test_refuse_stream_on_celery() -> None:
    with pytest.raises(PermanentTaskError) as exc:
        refuse_stream_on_celery.run()
    assert "pulse-jetstream" in str(exc.value)
