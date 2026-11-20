"""Stub Celery tasks for queues not yet implemented (Phases 5+).

These return explicit ``not_implemented`` status — never fake success with invented data.
"""

from __future__ import annotations

from typing import Any

from pulse.workers.base_task import PulseTask
from pulse.workers.celery_app import celery_app
from pulse.workers.queues import QueueName


def _stub(stage: str, phase: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "stage": stage,
        "phase": phase,
        **extra,
    }


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.normalize_batch",
)
def normalize_batch(self: PulseTask, batch_id: str | None = None) -> dict[str, Any]:
    return _stub("ingestion.normalize", "phase-5", batch_id=batch_id)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.dedupe_batch",
)
def dedupe_batch(self: PulseTask, batch_id: str | None = None) -> dict[str, Any]:
    return _stub("ingestion.dedupe", "phase-5", batch_id=batch_id)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.match_brands",
)
def match_brands(self: PulseTask, project_id: str | None = None) -> dict[str, Any]:
    return _stub("matching.brand", "phase-5", project_id=project_id)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.run_ai_processing",
)
def run_ai_processing(self: PulseTask, mention_id: str | None = None) -> dict[str, Any]:
    return _stub("processing.ai", "phase-5", mention_id=mention_id)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.aggregate_analytics",
)
def aggregate_analytics(self: PulseTask, window: str | None = None) -> dict[str, Any]:
    return _stub("analytics.aggregate", "phase-6", window=window)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.dispatch_alerts",
)
def dispatch_alerts(self: PulseTask, alert_id: str | None = None) -> dict[str, Any]:
    return _stub("alerts.dispatch", "phase-7", alert_id=alert_id)


@celery_app.task(
    bind=True,
    base=PulseTask,
    name="pulse.workers.stub_tasks.maintenance_cleanup",
)
def maintenance_cleanup(self: PulseTask) -> dict[str, Any]:
    return _stub("maintenance.cleanup", "phase-4")
