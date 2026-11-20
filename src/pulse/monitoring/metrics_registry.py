"""Prometheus metric definitions for Pulse (Phase 7)."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# Process-local registry so tests do not collide with the default collectors.
REGISTRY = CollectorRegistry()

# --- HTTP / API ---
HTTP_REQUESTS_TOTAL = Counter(
    "pulse_http_requests_total",
    "Total HTTP requests handled by Pulse API.",
    ["method", "path", "status"],
    registry=REGISTRY,
)

# --- Connectors ---
CONNECTOR_REQUESTS_TOTAL = Counter(
    "pulse_connector_requests_total",
    "Outbound connector HTTP/WebSocket request attempts.",
    ["source", "operation"],
    registry=REGISTRY,
)
CONNECTOR_BYTES_DOWNLOADED_TOTAL = Counter(
    "pulse_connector_bytes_downloaded_total",
    "Bytes downloaded by connectors.",
    ["source"],
    registry=REGISTRY,
)
CONNECTOR_ITEMS_FETCHED_TOTAL = Counter(
    "pulse_connector_items_fetched_total",
    "Items fetched by connectors before ingestion.",
    ["source"],
    registry=REGISTRY,
)
CONNECTOR_RETRIES_TOTAL = Counter(
    "pulse_connector_retries_total",
    "Connector-level retry attempts.",
    ["source"],
    registry=REGISTRY,
)
CONNECTOR_ERRORS_TOTAL = Counter(
    "pulse_connector_errors_total",
    "Connector failures by kind.",
    ["source", "kind"],
    registry=REGISTRY,
)

# --- Ingestion ---
INGESTION_ACCEPTED_TOTAL = Counter(
    "pulse_ingestion_accepted_total",
    "Mentions accepted by the ingestion pipeline.",
    ["source"],
    registry=REGISTRY,
)
INGESTION_REJECTED_TOTAL = Counter(
    "pulse_ingestion_rejected_total",
    "Mentions rejected by the ingestion pipeline.",
    ["source", "reason"],
    registry=REGISTRY,
)
INGESTION_DUPLICATES_TOTAL = Counter(
    "pulse_ingestion_duplicates_total",
    "Mentions marked duplicate during dedupe.",
    ["source", "level"],
    registry=REGISTRY,
)

# --- Queues / workers ---
QUEUE_JOBS_TOTAL = Counter(
    "pulse_queue_jobs_total",
    "Celery jobs by queue and outcome.",
    ["queue", "status"],
    registry=REGISTRY,
)
QUEUE_RETRIES_TOTAL = Counter(
    "pulse_queue_retries_total",
    "Celery task retries.",
    ["queue", "task"],
    registry=REGISTRY,
)
WORKER_DURATION_SECONDS = Histogram(
    "pulse_worker_duration_seconds",
    "Worker task wall time in seconds.",
    ["queue", "task"],
    registry=REGISTRY,
)

# --- Checkpoints ---
CHECKPOINT_LAG_SECONDS = Gauge(
    "pulse_checkpoint_lag_seconds",
    "Estimated lag between source watermark and last checkpoint.",
    ["source", "source_key"],
    registry=REGISTRY,
)

# --- Costs / usage ---
USAGE_RECORDS_TOTAL = Counter(
    "pulse_usage_records_total",
    "Usage records written.",
    ["source", "operation"],
    registry=REGISTRY,
)
USAGE_COST_USD_TOTAL = Counter(
    "pulse_usage_cost_usd_total",
    "Accumulated usage cost in USD (from configured pricing, not vendor truth).",
    ["source", "pricing_label"],
    registry=REGISTRY,
)
AI_TOKENS_TOTAL = Counter(
    "pulse_ai_tokens_total",
    "AI tokens consumed (stub-friendly counter).",
    ["source", "operation"],
    registry=REGISTRY,
)


def observe_connector_accounting(
    *,
    source: str,
    operation: str,
    http_requests: int = 0,
    bytes_downloaded: int = 0,
    items_fetched: int = 0,
    retries: int = 0,
) -> None:
    """Update connector Prometheus series from request accounting."""
    if http_requests:
        CONNECTOR_REQUESTS_TOTAL.labels(source=source, operation=operation).inc(http_requests)
    if bytes_downloaded:
        CONNECTOR_BYTES_DOWNLOADED_TOTAL.labels(source=source).inc(bytes_downloaded)
    if items_fetched:
        CONNECTOR_ITEMS_FETCHED_TOTAL.labels(source=source).inc(items_fetched)
    if retries:
        CONNECTOR_RETRIES_TOTAL.labels(source=source).inc(retries)


def observe_usage_record(
    *,
    source: str,
    operation: str,
    cost_usd: float | None,
    pricing_label: str | None,
    ai_tokens: int = 0,
) -> None:
    USAGE_RECORDS_TOTAL.labels(source=source, operation=operation).inc()
    if cost_usd is not None and pricing_label:
        USAGE_COST_USD_TOTAL.labels(source=source, pricing_label=pricing_label).inc(float(cost_usd))
    if ai_tokens:
        AI_TOKENS_TOTAL.labels(source=source, operation=operation).inc(ai_tokens)
