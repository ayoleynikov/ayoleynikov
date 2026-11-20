"""Ingestion — normalize, dedupe, store, pipeline."""

from pulse.ingestion.dedupe import DedupDecision, DedupIndex, DedupLevel, dedupe_batch, evaluate_dedup
from pulse.ingestion.normalize import NormalizationError, normalize_mention
from pulse.ingestion.pipeline import PipelineResult, run_ingestion_pipeline
from pulse.ingestion.store import MentionStore, PollOutcome, poll_rss_feed

__all__ = [
    "DedupDecision",
    "DedupIndex",
    "DedupLevel",
    "MentionStore",
    "NormalizationError",
    "PipelineResult",
    "PollOutcome",
    "dedupe_batch",
    "evaluate_dedup",
    "normalize_mention",
    "poll_rss_feed",
    "run_ingestion_pipeline",
]
