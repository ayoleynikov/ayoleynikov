"""Request accounting helpers for connector HTTP activity."""

from __future__ import annotations

from pulse.connectors.types import RequestAccounting


class RequestCounter:
    """Mutable accumulator converted to ``RequestAccounting`` snapshots."""

    def __init__(self) -> None:
        self.http_requests = 0
        self.bytes_downloaded = 0
        self.items_fetched = 0
        self.retries = 0
        self.not_modified = False

    def record_http(self, *, bytes_downloaded: int = 0) -> None:
        self.http_requests += 1
        self.bytes_downloaded += max(0, bytes_downloaded)

    def record_items(self, count: int) -> None:
        self.items_fetched += max(0, count)

    def record_retry(self) -> None:
        self.retries += 1

    def mark_not_modified(self) -> None:
        self.not_modified = True

    def snapshot(self) -> RequestAccounting:
        return RequestAccounting(
            http_requests=self.http_requests,
            bytes_downloaded=self.bytes_downloaded,
            items_fetched=self.items_fetched,
            retries=self.retries,
            not_modified=self.not_modified,
        )

    def reset(self) -> None:
        self.http_requests = 0
        self.bytes_downloaded = 0
        self.items_fetched = 0
        self.retries = 0
        self.not_modified = False
