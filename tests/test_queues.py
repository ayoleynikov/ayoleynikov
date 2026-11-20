"""Queue manifest and asyncio/Celery boundary tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pulse.workers.boundaries import STREAM_REFUSAL_MESSAGE, assert_not_asyncio_workload
from pulse.workers.queues import ALL_QUEUES, QueueName
from pulse.workers.retry import PermanentTaskError


REQUIRED_QUEUES = {
    "source.discovery",
    "source.poll",
    "source.fetch",
    "source.stream",
    "ingestion.normalize",
    "ingestion.dedupe",
    "matching.brand",
    "processing.ai",
    "analytics.aggregate",
    "alerts.dispatch",
    "maintenance.cleanup",
    "dead_letter",
}


def test_all_master_spec_queues_present() -> None:
    assert REQUIRED_QUEUES <= set(ALL_QUEUES)
    assert QueueName.SOURCE_POLL.value == "source.poll"


def test_asyncio_workload_refused() -> None:
    with pytest.raises(PermanentTaskError) as exc:
        assert_not_asyncio_workload("bluesky.jetstream")
    assert "pulse-jetstream" in str(exc.value)
    assert STREAM_REFUSAL_MESSAGE in str(exc.value)


def test_queues_api(client: TestClient) -> None:
    response = client.get("/api/v1/workers/queues")
    assert response.status_code == 200
    body = response.json()
    assert REQUIRED_QUEUES <= set(body["queues"])
    assert "bluesky.jetstream" in body["asyncio_only"]
