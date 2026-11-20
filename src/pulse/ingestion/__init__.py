"""Ingestion entry points — minimal Phase 2 path into Postgres storage."""

from pulse.ingestion.store import MentionStore, PollOutcome, poll_rss_feed

__all__ = ["MentionStore", "PollOutcome", "poll_rss_feed"]
