"""Dead-letter recording and PulseTask failure hooks."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from pulse.models.dead_letter import DeadLetter
from pulse.workers.base_task import PulseTask
from pulse.workers.celery_app import celery_app
from pulse.workers.dlq import list_open_dead_letters, record_dead_letter
from pulse.workers.retry import PermanentTaskError, TransientTaskError


class _FakeSession:
    def __init__(self) -> None:
        self.rows: list[DeadLetter] = []
        self.committed = False

    def add(self, row: DeadLetter) -> None:
        self.rows.append(row)

    def commit(self) -> None:
        self.committed = True

    def scalars(self, _stmt):  # type: ignore[no-untyped-def]
        return SimpleNamespace(all=lambda: [r for r in self.rows if r.status == "open"])

    def get(self, _model, _id):  # type: ignore[no-untyped-def]
        return None


def test_record_dead_letter_persists_open_row() -> None:
    session = _FakeSession()
    row = record_dead_letter(
        session,  # type: ignore[arg-type]
        task_name="pulse.workers.tasks.flaky_demo_task",
        task_id="abc",
        queue="maintenance.cleanup",
        args=[],
        kwargs={"fail_times": 9},
        exc=PermanentTaskError("gave up"),
        retries=5,
        idempotency_key="key-1",
        tb="traceback",
    )
    assert session.committed is True
    assert row.status == "open"
    assert row.exception_type == "PermanentTaskError"
    assert row.retries == 5
    assert len(session.rows) == 1


def test_list_open_dead_letters() -> None:
    session = _FakeSession()
    record_dead_letter(
        session,  # type: ignore[arg-type]
        task_name="t",
        task_id=None,
        queue="dead_letter",
        args=[],
        kwargs={},
        exc=RuntimeError("x"),
        retries=1,
    )
    open_rows = list_open_dead_letters(session)  # type: ignore[arg-type]
    assert len(open_rows) == 1


def test_pulse_task_on_failure_records_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict] = []

    class _Sess:
        def close(self) -> None:
            return None

    def fake_record(session, **kwargs):  # type: ignore[no-untyped-def]
        recorded.append(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr("pulse.workers.base_task._sync_session", lambda: _Sess())
    monkeypatch.setattr("pulse.workers.base_task.record_dead_letter", fake_record)

    @celery_app.task(bind=True, base=PulseTask, name="pulse.workers.tasks._dlq_test_demo")
    def _demo(self: PulseTask) -> dict[str, str]:
        return {"status": "ok"}

    _demo.push_request(retries=5, delivery_info={"routing_key": "maintenance.cleanup"})
    try:
        _demo.on_failure(
            PermanentTaskError("exhausted"),
            "task-id-1",
            ("arg",),
            {"idempotency_key": "idem-1"},
            einfo="tb",
        )
    finally:
        _demo.pop_request()

    assert len(recorded) == 1
    assert recorded[0]["task_name"] == "pulse.workers.tasks._dlq_test_demo"
    assert recorded[0]["retries"] == 5


def test_pulse_task_on_failure_skips_dlq_while_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        raise AssertionError("should not persist DLQ yet")

    monkeypatch.setattr("pulse.workers.base_task.record_dead_letter", boom)

    @celery_app.task(bind=True, base=PulseTask, name="pulse.workers.tasks._dlq_skip_demo")
    def _demo(self: PulseTask) -> dict[str, str]:
        return {"status": "ok"}

    _demo.push_request(retries=1, delivery_info={})
    try:
        _demo.on_failure(TransientTaskError("later"), "id", (), {}, einfo=None)
    finally:
        _demo.pop_request()
    assert calls["n"] == 0
